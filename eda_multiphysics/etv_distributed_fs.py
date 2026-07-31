"""Distributed coupled electrothermal research driver using PETSc FieldSplit.

This driver assembles the compiled coupled kernel into a distributed PETSc
system and solves with PCFIELDSPLIT and a GAMG sub-preconditioner for each
scalar field. Public evidence is limited to the checked-size serial-versus-rank
comparisons in ``tests/test_toolchain.py``.

The assembly path uses a node-aligned contiguous row partition. Each rank
evaluates elements touching its owned nodes in a batched compiled call, keeps
owned-row triplets, builds local CSR with SciPy, and creates a PETSc AIJ matrix.
The current Newton update gathers a replicated solution vector, which bounds
the interpretation of larger local experiments.

Owned-row CSR is the implementation used by this driver; no claim about other
PETSc insertion paths is part of the public evidence.

    OMP_NUM_THREADS=1 mpirun -n 2 \
      python -m eda_multiphysics.etv_distributed_fs 24 --validate
"""
from __future__ import annotations

import os
import sys
import time

import numpy as np
import scipy.sparse as sp

from .etv_distributed import PROPS, V0, _dirichlet_fn, _kernel, build_grid


def main():
    from petsc4py import PETSc
    from coupfe.runtime.compiled_element import CompiledElement

    comm = PETSc.COMM_WORLD
    rank, size = comm.getRank(), comm.getSize()
    n = int(sys.argv[1]) if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else 512

    nodes, elems = build_grid(n)
    nnodes = len(nodes)
    ndof = nnodes * 2
    mod = _kernel(os.path.join(os.path.dirname(__file__), f"_etk_fs_r{rank}"))

    # --- node-aligned contiguous partition: rank owns nodes [na,nb) -> rows [2na,2nb) ---
    na = (rank * nnodes) // size
    nb = ((rank + 1) * nnodes) // size
    rs, re = 2 * na, 2 * nb
    nloc = re - rs
    # elements touching my owned nodes (owned + one ghost layer); vectorized mask
    mask = ((elems >= na) & (elems < nb)).any(axis=1)
    my_elems = elems[mask]
    my_coords = nodes[my_elems].astype(float)
    # interleaved (phi,T) dof map for each element: node k -> dofs (2k, 2k+1)
    my_gm = (2 * my_elems[:, :, None] + np.array([0, 1])).reshape(len(my_elems), 8)
    elem = CompiledElement(mod, props=PROPS, dof_per_node=2, n_svars=0, mcrd=2,
                           n_elem=len(my_elems))

    # COO triplet pattern for this rank's element blocks (vectorized, computed ONCE);
    # keep only OWNED rows -> a (nloc x ndof) local CSR, no off-process entries, no loop.
    ndofel = my_gm.shape[1]
    coo_i = np.repeat(my_gm, ndofel, axis=1).ravel()
    coo_j = np.tile(my_gm, (1, ndofel)).ravel()
    gm_flat = my_gm.ravel()
    own = (coo_i >= rs) & (coo_i < re)
    ii, jj = coo_i[own] - rs, coo_j[own]
    rown = (gm_flat >= rs) & (gm_flat < re)
    rii = gm_flat[rown] - rs

    # field index sets: each rank's LOCALLY-OWNED dofs per field (phi=even, T=odd).
    loc = np.arange(rs, re)
    is_phi = PETSc.IS().createGeneral(loc[loc % 2 == 0].astype(PETSc.IntType), comm=comm)
    is_T = PETSc.IS().createGeneral(loc[loc % 2 == 1].astype(PETSc.IntType), comm=comm)

    dfn = _dirichlet_fn(nodes)
    d = dfn(1.0)                                        # full load
    drows = np.array(sorted(d), dtype=PETSc.IntType)
    dvals = np.array([d[int(i)] for i in drows])
    U = np.zeros(ndof)                                  # replicated solution vector

    def assemble(U):
        Ug = U[my_gm]
        R_all, K_all = elem.element_rk_batch(my_coords, Ug, np.zeros_like(Ug))
        Kv = np.asarray(K_all, float).ravel()[own]
        Cloc = sp.coo_matrix((Kv, (ii, jj)), shape=(nloc, ndof)).tocsr()
        A = PETSc.Mat().createAIJ(size=((nloc, ndof), (nloc, ndof)),
                                  csr=(Cloc.indptr.astype(PETSc.IntType),
                                       Cloc.indices.astype(PETSc.IntType), Cloc.data),
                                  comm=comm)
        A.assemble()
        rloc = np.bincount(rii, weights=np.asarray(R_all, float).ravel()[rown], minlength=nloc)
        Rv = PETSc.Vec().createMPI((nloc, ndof), comm=comm)
        Rv.getArray()[:] = rloc
        Rv.assemble()
        return A, Rv

    t0 = time.time()
    its = 0
    converged = False
    last_update = float("inf")
    for step in range(8):                               # Newton loop (quadratic Joule term)
        U[drows] = dvals
        A, Rv = assemble(U)
        b = Rv.copy(); b.scale(-1.0)
        xbc = b.duplicate(); xbc.set(0.0)               # zero increment at Dirichlet
        A.zeroRowsColumns(drows, diag=1.0, x=xbc, b=b)
        # --- FieldSplit (GAMG per field) ---
        ksp = PETSc.KSP().create(comm); ksp.setOperators(A)
        ksp.setType("gmres"); ksp.setTolerances(rtol=1e-10, max_it=500)
        pc = ksp.getPC(); pc.setType("fieldsplit")
        pc.setFieldSplitIS(("phi", is_phi), ("T", is_T))
        pc.setFieldSplitType(PETSc.PC.CompositeType.ADDITIVE)
        ksp.setUp()
        for sub in pc.getFieldSplitSubKSP():
            sub.setType("preonly"); sub.getPC().setType("gamg")
        x = A.createVecLeft()
        ksp.solve(b, x)
        its = ksp.getIterationNumber()
        reason = int(ksp.getConvergedReason())
        ksp_residual = float(ksp.getResidualNorm())
        if reason <= 0:
            A.destroy()
            ksp.destroy()
            raise RuntimeError(
                "distributed FieldSplit linear solve failed: "
                f"reason={reason}, iterations={its}, residual_norm={ksp_residual:.6e}"
            )
        # gather increment to every rank, update the replicated U
        sc, seq = PETSc.Scatter.toAll(x)
        sc.scatter(x, seq, addv=PETSc.InsertMode.INSERT_VALUES, mode=PETSc.ScatterMode.FORWARD)
        dU = np.asarray(seq.getArray()).copy()
        if not np.all(np.isfinite(dU)):
            A.destroy()
            ksp.destroy()
            raise RuntimeError("distributed FieldSplit produced a non-finite increment")
        U = U + dU
        last_update = float(np.max(np.abs(dU)))
        if rank == 0 and "--dbg" in sys.argv:
            print(f"  [iter {step}] ksp_its={its} reason={int(ksp.getConvergedReason())} "
                  f"max|dU|={np.max(np.abs(dU)):.3e} peakT={U[1::2].max():.4f}", flush=True)
        A.destroy(); ksp.destroy()
        if last_update < 1e-11:                         # Newton converged
            converged = True
            break
    if not converged:
        raise RuntimeError(
            "distributed FieldSplit Newton solve did not converge: "
            f"iterations=8, last_update={last_update:.6e}, tolerance=1.0e-11"
        )
    comm.barrier(); dt = time.time() - t0

    if rank == 0:
        peakT = float(U[1::2].max())
        print(f"DISTRIBUTED FieldSplit coupled electro-thermal | {n}x{n} = {ndof:,} DOF | "
              f"{size} rank(s) | my_ne={len(my_elems)}")
        print(f"  wall={dt:.2f}s | last KSP iters={its} | peak dT={peakT:.4f}")
        if "--validate" in sys.argv:
            from .etv_distributed import serial_solve
            Us = serial_solve(n)
            err = float(np.max(np.abs(U - Us)) / max(1e-30, np.max(np.abs(Us))))
            print(f"  serial==N-rank: max rel = {err:.2e}  {'PASS' if err < 1e-6 else 'FAIL'}")
            if not np.isfinite(err) or err >= 1e-6:
                raise RuntimeError(
                    f"distributed-versus-serial comparison failed: relative_error={err:.6e}"
                )
        print(f"SCALEFS {ndof} {size} {dt:.4f} {its}")


if __name__ == "__main__":
    main()
