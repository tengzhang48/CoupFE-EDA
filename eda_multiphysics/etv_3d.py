"""3D coupled electro-thermal solve -- the Hex8 codegen kernel.

The distributed 2D work (`etv_distributed`) is large in DOF *count* but 2D. This
module uses the same coupled weak form (`etv_kernel.ElectroThermalProblem`,
dimension-agnostic), generated as a **Hex8** element on a 3D structured mesh and
solved with a **FieldSplit (GAMG per field)** research path. It is checked against
the exact self-heating limit dT = sigma V0^2 / 8k (a 1D problem through the
thickness, so the 3D peak is the same closed form).

    python -m eda_multiphysics.etv_3d [grid_n]
"""
from __future__ import annotations

import os
import sys
import time

import numpy as np
from petsc4py import PETSc


def build_hex_grid(n, L=1.0):
    """n^3 structured Hex8 mesh: (n+1)^3 nodes, standard Hex8 ordering (bottom CCW, top CCW)."""
    nn = n + 1
    m = np.arange(nn ** 3)
    i = m % nn; j = (m // nn) % nn; k = m // (nn * nn)
    coords = np.column_stack([i, j, k]).astype(float) * (L / n)        # node m at (i,j,k)
    sx, sy, sz = 1, nn, nn * nn                                        # strides for i,j,k
    base = np.arange(nn ** 3).reshape(nn, nn, nn)[:-1, :-1, :-1].ravel()  # (n^3,) corner ids (k,j,i)
    elems = np.stack([base, base + sx, base + sx + sy, base + sy,
                      base + sz, base + sx + sz, base + sx + sy + sz, base + sy + sz], axis=1)
    return coords, elems


def _fieldsplit_solve(A, b, ndof):
    ksp = PETSc.KSP().create(PETSc.COMM_SELF); ksp.setOperators(A)
    ksp.setType("gmres"); ksp.setTolerances(rtol=1e-11, max_it=3000)
    pc = ksp.getPC(); pc.setType("fieldsplit")
    is_phi = PETSc.IS().createGeneral(np.arange(0, ndof, 2).astype(PETSc.IntType), comm=PETSc.COMM_SELF)
    is_T = PETSc.IS().createGeneral(np.arange(1, ndof, 2).astype(PETSc.IntType), comm=PETSc.COMM_SELF)
    pc.setFieldSplitIS(("phi", is_phi), ("T", is_T))
    pc.setFieldSplitType(PETSc.PC.CompositeType.ADDITIVE)
    ksp.setUp()
    for sub in pc.getFieldSplitSubKSP():
        sub.setType("preonly"); sub.getPC().setType("gamg")
    x = b.duplicate()
    ksp.solve(b, x)
    reason = int(ksp.getConvergedReason())
    iterations = ksp.getIterationNumber()
    residual_norm = float(ksp.getResidualNorm())
    dU = x.getArray().copy()
    ksp.destroy()
    if reason <= 0 or not np.all(np.isfinite(dU)):
        raise RuntimeError(
            "electrothermal FieldSplit solve failed: "
            f"reason={reason}, iterations={iterations}, residual_norm={residual_norm:.6e}"
        )
    return dU, iterations


def solve(n, props, V0=2.0, workdir=None, maxit=8):
    """Build the Hex8 kernel + 3D mesh, then a Newton loop (the Joule term is quadratic in phi)
    with the FieldSplit PC each step. Returns (U, ndof, last_iters)."""
    from coupfe import ElementGroup, assemble_residual, assemble_tangent
    from coupfe.runtime.compiled_element import CompiledElement
    from .etv_kernel import build_et_kernel
    nodes, elems = build_hex_grid(n)
    wd = workdir or os.path.join(os.path.dirname(__file__), "_etk_hex")
    os.makedirs(wd, exist_ok=True)
    mod = build_et_kernel(wd, sigma0=props[0], alpha=props[1], k=props[2], element="Hex8")
    elem = CompiledElement(mod, props=props, dof_per_node=2, n_svars=0, mcrd=3, n_elem=len(elems))
    group = ElementGroup(elem, nodes, elems, dof_per_node=2, comps=(0, 1))
    ndof = len(nodes) * 2
    x = nodes[:, 0]
    d = {}
    for nidx in np.where(np.abs(x - x.min()) < 1e-9)[0]:
        d[2 * int(nidx)] = 0.0; d[2 * int(nidx) + 1] = 0.0
    for nidx in np.where(np.abs(x - x.max()) < 1e-9)[0]:
        d[2 * int(nidx)] = V0; d[2 * int(nidx) + 1] = 0.0
    from ._coupled_solve import coupled_newton

    def backend(K, R, dr):                                  # CSR -> SEQAIJ + zeroRowsColumns + FieldSplit
        A = PETSc.Mat().createAIJ(size=K.shape, comm=PETSc.COMM_SELF,
                                  csr=(K.indptr.astype(PETSc.IntType),
                                       K.indices.astype(PETSc.IntType), K.data))
        A.assemble()
        b = PETSc.Vec().createWithArray(-np.asarray(R), comm=PETSc.COMM_SELF)
        xbc = b.duplicate(); xbc.set(0.0)
        A.zeroRowsColumns(dr.astype(PETSc.IntType), diag=1.0, x=xbc, b=b)
        try:
            dU, its = _fieldsplit_solve(A, b, ndof)
        finally:
            A.destroy()
        return dU, {"ksp_its": its}

    U, _n, info = coupled_newton([group], ndof, d, backend, maxit=maxit, tol=1e-11)
    return U, ndof, info.get("ksp_its", 0)


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 24
    props = (3.0, 0.0, 1.5)                                 # alpha=0 -> exact self-heating check
    t = time.time()
    U, ndof, its = solve(n, props)
    dt = time.time() - t
    peak = float(U[1::2].max()); exact = 3.0 * 2.0 ** 2 / (8.0 * 1.5)
    print(f"3D coupled electro-thermal (Hex8 codegen kernel, FieldSplit GAMG/GAMG)")
    print(f"  {n}x{n}x{n} mesh = {ndof:,} DOF (2 fields) | {dt:.1f}s (Newton + FieldSplit, "
          f"last KSP {its} iters)")
    print(f"  self-heating: peak dT = {peak:.6f} vs sigma V0^2/8k = {exact:.6f}  "
          f"err {abs(peak - exact) / exact:.1e}  {'PASS' if abs(peak-exact)/exact < 2e-3 else 'CHECK'}")
    print("  the same coupled weak form is generated as Hex8 and checked on this 3D case.")


if __name__ == "__main__":
    main()
