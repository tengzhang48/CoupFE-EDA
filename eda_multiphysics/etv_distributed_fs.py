"""Large distributed coupled solve with FieldSplit, intended for scaling studies.

`etv_distributed` solves the coupled system with ASM (the only PC `solve_distributed` offers
for coupled fields), whose iteration count grows with size (no coarse grid) -> impractical at
millions of DOF. This driver assembles the COMPILED coupled kernel into a distributed PETSc
system and solves with **PCFIELDSPLIT (GAMG per scalar field)**. Checked-size
correctness is tested; multi-million-DOF performance and mesh-independent
iteration behavior require retained reruns on the final revisions.

Assembly is **fully vectorized -- no Python per-element loop**:
  * a **node-aligned** contiguous row partition (rank r owns nodes [na,nb) -> rows [2na,2nb));
  * each rank evaluates the elements TOUCHING its owned nodes (owned + a one-layer ghost) in
    ONE batched compiled call (`element_rk_batch`, the f2py kernel -- the "batch f2py");
  * it keeps only the OWNED-ROW triplets and builds a local CSR with `scipy` (vectorized
    `coo_matrix(...).tocsr()`), then `createAIJ(csr=...)` -- a plain AIJ block, no off-process
    routing, no Python loop. The residual is summed with `np.bincount` (vectorized).

Why not PETSc's `setValuesCOO` (the obvious vectorized stamp)? It works numerically, but
assembling via the COO interface **corrupts global PETSc state** (a confirmed upstream bug --
reproduced in ~30 lines of pure petsc4py, `docs/petsc_coo_gamg_bug_repro.py`, failing identically
on pip-wheel 3.25.2 AND conda-forge 3.24.2): the FIRST solve in the process works, every
SUBSEQUENT one fails (GAMG stagnates, ILU/bjacobi PC-setup fails, `MatConvert` segfaults) -- so a
Newton loop diverges at iter 1. The owned-row CSR path above sidesteps the COO interface entirely
(see `docs/lessons_learned.md`).

    OMP_NUM_THREADS=1 mpirun -n 48 python -m eda_multiphysics.etv_distributed_fs 1580
    # add --validate (serial scipy oracle; only feasible for small n)
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
    U = np.zeros(ndof)                                  # replicated (40 MB at 5M DOF)

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
        x = A.createVecLeft(); ksp.solve(b, x); its = ksp.getIterationNumber()
        # gather increment to every rank, update the replicated U
        sc, seq = PETSc.Scatter.toAll(x)
        sc.scatter(x, seq, addv=PETSc.InsertMode.INSERT_VALUES, mode=PETSc.ScatterMode.FORWARD)
        dU = np.asarray(seq.getArray()).copy()
        U = U + dU
        if rank == 0 and "--dbg" in sys.argv:
            print(f"  [iter {step}] ksp_its={its} reason={int(ksp.getConvergedReason())} "
                  f"max|dU|={np.max(np.abs(dU)):.3e} peakT={U[1::2].max():.4f}", flush=True)
        A.destroy(); ksp.destroy()
        if np.max(np.abs(dU)) < 1e-11:                  # Newton converged
            break
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
            print(f"  serial==N-rank: max rel = {err:.2e}  {'PASS' if err < 1e-6 else 'CHECK'}")
        print(f"SCALEFS {ndof} {size} {dt:.4f} {its}")


if __name__ == "__main__":
    main()
