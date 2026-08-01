"""Distributed nonlinear coupled electrothermal research driver.

The implementation uses:
  * the coupled electro-thermal element is a COMPILED f2py kernel generated from its weak
    form by `coupfe.codegen` (see `etv_kernel.py`) -- one batched call per assembly;
  * the global NONLINEAR (sigma(T) + Joule) solve is run distributed by
    `coupfe.assembly.distributed.solve_distributed` -- each rank owns a slice of the
    elements, ghosts the U it needs via a PETSc VecScatter (no all-gather), assembles its
    rows of the distributed Mat/Vec, and a load-stepped Newton + KSP solves across ranks.

The formulation has 2 DOF/node (phi, T) and supports serial-versus-rank
comparisons and the ``alpha=0`` self-heating oracle. Retained current-release
multi-rank qualification is provided for ``etv_distributed_fs``; this module is
kept as a research driver pending an equivalent retained rank test.

    OMP_NUM_THREADS=1 mpirun -n 4 python -m eda_multiphysics.etv_distributed [grid_n]

Use ``--element-evaluation split`` to opt into the native residual-only entry
for convergence and line-search callbacks. Joint native R/K evaluation remains
the default.
"""

from __future__ import annotations

import argparse
import os
import time

import numpy as np

SIGMA0, ALPHA, K_TH, V0 = 3.0, 0.05, 1.5, 2.0   # alpha>0 -> NONLINEAR coupled
PROPS = (SIGMA0, ALPHA, K_TH)
ELEMENT_EVALUATION_MODES = ("joint", "split")


def build_grid(n, Lx=1.0, Ly=1.0):
    """n-by-n element structured grid: (n+1)^2 nodes, vectorized connectivity (CCW)."""
    nn = n + 1
    ids = np.arange(nn * nn).reshape(nn, nn)
    n0 = ids[:-1, :-1].ravel()
    elems = np.stack([n0, n0 + 1, n0 + 1 + nn, n0 + nn], axis=1)
    xs = np.linspace(0.0, Lx, nn); ys = np.linspace(0.0, Ly, nn)
    X, Y = np.meshgrid(xs, ys)
    nodes = np.column_stack([X.ravel(), Y.ravel()])
    return nodes, elems


def _kernel(workdir, *, backend="abaqus_uel"):
    """Build (or rebuild) the compiled electro-thermal kernel into `workdir`."""
    from .etv_kernel import build_et_kernel
    os.makedirs(workdir, exist_ok=True)
    return build_et_kernel(
        workdir, sigma0=SIGMA0, alpha=ALPHA, k=K_TH, backend=backend
    )


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("grid_n", nargs="?", type=int, default=160)
    parser.add_argument("--validate", action="store_true")
    parser.add_argument(
        "--element-evaluation",
        choices=ELEMENT_EVALUATION_MODES,
        default="joint",
        help=(
            "native element callback policy: joint retains fused R/K; split "
            "uses residual-only evaluation for residual-only solver callbacks"
        ),
    )
    return parser.parse_args(argv)


def _dirichlet_fn(nodes, V0=V0):
    """phi 0->V0 across x (ramped by load fraction), T=0 on both x-faces (cold)."""
    x = nodes[:, 0]
    left = np.where(np.abs(x - x.min()) < 1e-9)[0]
    right = np.where(np.abs(x - x.max()) < 1e-9)[0]

    def fn(frac):
        d = {}
        for nidx in left:
            d[int(nidx) * 2] = 0.0; d[int(nidx) * 2 + 1] = 0.0
        for nidx in right:
            d[int(nidx) * 2] = V0 * frac; d[int(nidx) * 2 + 1] = 0.0
        return d
    return fn


def serial_solve(
    n,
    props=PROPS,
    V0=V0,
    workdir=None,
    *,
    evaluation_mode="joint",
    kernel_backend=None,
):
    """Independent serial oracle: compiled ElementGroup assembly + scipy Newton."""
    import scipy.sparse.linalg as spla
    from coupfe import ElementGroup, assemble_residual, assemble_tangent
    from coupfe.runtime.compiled_element import CompiledElement
    nodes, elems = build_grid(n)
    if evaluation_mode not in ELEMENT_EVALUATION_MODES:
        raise ValueError("evaluation_mode must be 'joint' or 'split'")
    if kernel_backend is None:
        kernel_backend = "native" if evaluation_mode == "split" else "abaqus_uel"
    if evaluation_mode == "split" and kernel_backend != "native":
        raise ValueError("evaluation_mode='split' requires kernel_backend='native'")
    mod = _kernel(
        workdir or os.path.join(os.path.dirname(__file__), "_etk_serial"),
        backend=kernel_backend,
    )
    elem = CompiledElement(mod, props=props, dof_per_node=2, n_svars=0, mcrd=2,
                           n_elem=len(elems))
    group = ElementGroup(
        elem,
        nodes,
        elems,
        dof_per_node=2,
        comps=(0, 1),
        evaluation_mode=evaluation_mode,
    )
    ndof = len(nodes) * 2
    d = _dirichlet_fn(nodes, V0)(1.0)
    drows = np.array(sorted(d)); dvals = np.array([d[i] for i in drows])
    U = np.zeros(ndof)
    converged = False
    last_update = float("inf")
    for _ in range(12):
        U[drows] = dvals
        R, _ = assemble_residual([group], U, None, 1.0, 1.0, ndof); R[drows] = 0.0
        K = assemble_tangent([group], U, None, 1.0, 1.0, ndof).tolil()
        for r in drows:
            K.rows[r] = [r]; K.data[r] = [1.0]
        dU = spla.spsolve(K.tocsr(), -R)
        if not np.all(np.isfinite(dU)):
            raise RuntimeError("serial electrothermal comparison produced a non-finite increment")
        U = U + dU
        last_update = float(np.max(np.abs(dU)))
        if last_update < 1e-11:
            converged = True
            break
    if not converged:
        raise RuntimeError(
            "serial electrothermal comparison did not converge: "
            f"iterations=12, last_update={last_update:.6e}, tolerance=1.0e-11"
        )
    return U


def main():
    args = _parse_args()
    from petsc4py import PETSc
    from coupfe.assembly.distributed import element_partition, solve_distributed
    from coupfe.mesh import KernelMeshView
    from coupfe.runtime.compiled_element import CompiledElement
    comm = PETSc.COMM_WORLD
    rank, size = comm.getRank(), comm.getSize()
    n = args.grid_n

    nodes, elems = build_grid(n)
    view = KernelMeshView(nodes, elems, dof_per_node=2)
    ndof_total = len(nodes) * 2
    # each rank compiles the kernel into its own dir (no race), then partitions the elements
    wd = os.path.join(os.path.dirname(__file__), f"_etk_r{rank}")
    # This driver deliberately uses Core's native backend for both policies so
    # joint-versus-split changes callback work, not the element formulation or ABI.
    mod = _kernel(wd, backend="native")
    my_gm, my_coords, ndof = element_partition(view, rank, size)
    elem = CompiledElement(mod, props=PROPS, dof_per_node=2, n_svars=0, mcrd=2,
                           n_elem=len(my_gm))
    t0 = time.time()
    # Iterative GMRES + additive-Schwarz (ASM) on the 2-field coupled
    # (interleaved phi,T) system. Scalar-elliptic GAMG can mis-coarsen this
    # block, while ASM has no coarse grid. FieldSplit+AMG per field is the
    # implementation selected for future retained scaling studies.
    # (superlu_dist machine-precision distributed direct is conda-only here.)
    residual_options = {"evaluation_mode": args.element_evaluation}
    if args.element_evaluation == "split":
        residual_options["residual_batch_fn"] = elem.element_r_batch
    U_par, info = solve_distributed(
        ndof,
        my_gm,
        my_coords,
        2,
        elem.element_rk_batch,
        _dirichlet_fn(nodes),
        n_steps=3,
        pc="asm",
        ksp_type="gmres",
        rtol=1e-12,
        tol=1e-9,
        **residual_options,
    )
    comm.barrier(); dt = time.time() - t0

    if rank == 0:
        peakT = float(U_par[1::2].max())
        its = info.get("ksp_its", "?")
        print(f"DISTRIBUTED nonlinear coupled electro-thermal (COMPILED kernel + "
              f"solve_distributed)")
        print(f"  {n}x{n} grid = {ndof_total:,} DOF (2 fields) | {size} rank(s) | "
              f"my_ne={info['my_ne']} owned={info['n_owned']} ghost={info['n_ghost']}")
        print(f"  wall={dt:.2f}s | ksp_its={its} | peak dT={peakT:.4f} "
              f"(nonlinear coupled, alpha={ALPHA})")
        print(
            "  native element evaluation: "
            f"{info['evaluation_mode']} (Jacobian callbacks remain joint R/K)"
        )
        if args.validate:
            U_ser = serial_solve(
                n,
                evaluation_mode=args.element_evaluation,
                kernel_backend="native",
            )
            err = float(np.max(np.abs(U_par - U_ser)) / max(1e-30, np.max(np.abs(U_ser))))
            print(f"  serial==N-rank: max rel|U_dist - U_serial| = {err:.2e}  "
                  f"{'PASS' if err < 1e-6 else 'CHECK'}  (iterative ASM+GMRES)")
        # machine-readable line for the scaling sweep
        print(f"SCALE {ndof_total} {size} {dt:.4f} {its}")


if __name__ == "__main__":
    main()
