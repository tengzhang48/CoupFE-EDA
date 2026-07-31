#!/usr/bin/env python
"""Minimal reproducer: PETSc `MatSetValuesCOO` corrupts global state for later solves.

Discovered 2026-06-27 while removing the per-element `setValues` stamp loop from the
distributed coupled solve (`eda_multiphysics/etv_distributed_fs.py`). Documented in
`docs/lessons_learned.md`.

WHAT IT SHOWS (no application code, no FieldSplit -- a trivial scalar 2D Laplacian):
  * Assemble an MPIAIJ matrix the ordinary way (`setValues`) and solve A x = b with KSP+GAMG
    three times (fresh KSP each) -> converges every time (~11 iters).
  * Assemble the IDENTICAL matrix via the COO interface (`setPreallocationCOO`/`setValuesCOO`)
    and do the same -> the FIRST solve converges, EVERY SUBSEQUENT one fails.

The numerical values are identical (the two matrices match to ~1e-15). The failure is therefore
not numerical -- it is global *state* corruption triggered by the COO assembly path:
  * with GAMG, later solves stagnate at max_it (KSP reason -3, DIVERGED_ITS);
  * with ILU or bjacobi, later PC *setups* fail (reason -11, DIVERGED_PC_FAILED);
  * `MatConvert` of a COO-assembled matrix outright SEGFAULTs;
  * a CLEAN (`setValues`-built) matrix's GAMG solve also fails once *any* COO solve has run in
    the process -> the poison is GLOBAL, not tied to the COO matrix object.
First-solve-works-then-everything-fails + PC-setup failures + a segfault are the signature of a
heap/memory-corruption bug inside the COO code path.

CONFIRMED ACROSS BUILDS AND VERSIONS (so it is an upstream PETSc bug, not a packaging artifact):
  * pip  petsc4py 3.25.2  (PETSc 3.25.2)  -- FAILS
  * conda-forge petsc4py 3.24.2 (PETSc 3.24.2) -- FAILS (identical signature)

WORKAROUND (used by `etv_distributed_fs.py`): never call `setValuesCOO`. Assemble each rank's
OWNED rows into a local CSR with scipy (vectorized, no Python element loop) and hand PETSc a plain
AIJ block via `createAIJ(csr=...)` -- a node-aligned row partition + a one-layer element ghost makes
this exact and off-process-free. That path keeps GAMG healthy across an arbitrary Newton loop.

Run:  python docs/petsc_coo_gamg_bug_repro.py      (1 process is enough; exits 1 if the bug is present)
"""
import sys

import numpy as np
from petsc4py import PETSc


def laplacian_triplets(N):
    """Vectorized COO triplets for an N x N 5-point Dirichlet-ish Laplacian (diag 4, nbr -1)."""
    ii = np.arange(N * N).reshape(N, N)
    r = ii.ravel()
    rows, cols, vals = [r], [r], [4.0 * np.ones(N * N)]
    for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
        rr = np.roll(np.roll(ii, dr, 0), dc, 1)
        mask = np.ones((N, N), bool)
        if dr == -1: mask[0, :] = False
        if dr == 1:  mask[-1, :] = False
        if dc == -1: mask[:, 0] = False
        if dc == 1:  mask[:, -1] = False
        m = mask.ravel()
        rows.append(r[m]); cols.append(rr.ravel()[m]); vals.append(-1.0 * np.ones(m.sum()))
    return (np.concatenate(rows).astype(PETSc.IntType),
            np.concatenate(cols).astype(PETSc.IntType),
            np.concatenate(vals))


def main():
    comm = PETSc.COMM_WORLD
    N = 60
    ndof = N * N
    R, C, V = laplacian_triplets(N)
    b = PETSc.Vec().createMPI(ndof, comm=comm); b.set(1.0); b.assemble()

    def build(coo):
        A = PETSc.Mat().createAIJ([ndof, ndof], comm=comm)
        if coo:
            A.setPreallocationCOO(R, C)
            A.setValuesCOO(V)
        else:
            A.setPreallocationNNZ(5)
            A.setOption(PETSc.Mat.Option.NEW_NONZERO_ALLOCATION_ERR, False)
            for k in range(len(R)):
                A.setValues([int(R[k])], [int(C[k])], [V[k]], addv=PETSc.InsertMode.ADD_VALUES)
        A.assemble()
        return A

    def solve(A):
        ksp = PETSc.KSP().create(comm); ksp.setOperators(A)
        ksp.setType("gmres"); ksp.setTolerances(rtol=1e-10, max_it=500)
        ksp.getPC().setType("gamg"); ksp.setUp()
        x = A.createVecLeft(); ksp.solve(b, x)
        res = (ksp.getIterationNumber(), int(ksp.getConvergedReason()))
        A.destroy(); ksp.destroy()
        return res

    import petsc4py
    print(f"petsc4py {petsc4py.__version__}  PETSc {PETSc.Sys.getVersion()}")
    sv = [solve(build(False)) for _ in range(3)]
    print(f"setValues + GAMG x3:    {sv}")
    coo = [solve(build(True)) for _ in range(3)]
    print(f"setValuesCOO + GAMG x3: {coo}")

    sv_ok = all(reason == 2 for _, reason in sv)
    coo_first_ok = coo[0][1] == 2
    coo_later_fail = all(reason < 0 for _, reason in coo[1:])
    bug = sv_ok and coo_first_ok and coo_later_fail
    print(f"\nsetValues path healthy: {sv_ok} | COO 1st-solve OK then later FAIL: "
          f"{coo_first_ok and coo_later_fail}")
    print("BUG PRESENT" if bug else "bug NOT reproduced in this build")
    sys.exit(1 if bug else 0)


if __name__ == "__main__":
    main()
