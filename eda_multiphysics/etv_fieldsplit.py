"""FieldSplit research example for the coupled electro-thermal solve.

ASM/block-Jacobi (`etv_distributed`) have no coarse grid -> the KSP iteration count grows with
problem size (~340 @132k DOF -> ~1200 @526k). The fix is **PCFIELDSPLIT**: split the interleaved
(phi, T) system into its two scalar fields and precondition EACH with **GAMG** (algebraic
multigrid). GAMG mis-coarsens the *coupled* 2-field block (it assumes a scalar elliptic operator),
but each *single field* is a scalar elliptic operator, and the outer GMRES
handles the inter-field coupling. Final-revision scaling behavior remains to be
measured with retained raw evidence.

This assembles the COMPILED coupled tangent (codegen kernel, no Python element loop) and compares
the GMRES iteration count of ASM vs FieldSplit(GAMG/GAMG) on the same system,
serially. It is a preconditioner proof of concept, not a current 1M+ or
rank/size-independent performance claim.

    python -m eda_multiphysics.etv_fieldsplit [grid_n]
"""
from __future__ import annotations

import os
import sys

import numpy as np
from petsc4py import PETSc

from .etv_distributed import PROPS, V0, _dirichlet_fn, _kernel, build_grid


def assemble(n):
    """Compiled-batch assembly of the coupled tangent + RHS (one Newton step), with symmetric
    Dirichlet, as a sequential PETSc system. Returns (A, b, ndof)."""
    from coupfe import ElementGroup, assemble_residual, assemble_tangent
    from coupfe.runtime.compiled_element import CompiledElement
    nodes, elems = build_grid(n)
    mod = _kernel(os.path.join(os.path.dirname(__file__), "_etk_fs"))
    elem = CompiledElement(mod, props=PROPS, dof_per_node=2, n_svars=0, mcrd=2, n_elem=len(elems))
    group = ElementGroup(elem, nodes, elems, dof_per_node=2, comps=(0, 1))
    ndof = len(nodes) * 2
    d = _dirichlet_fn(nodes, V0)(1.0)
    drows = np.array(sorted(d)); dvals = np.array([d[i] for i in drows])
    U = np.zeros(ndof); U[drows] = dvals
    R, _ = assemble_residual([group], U, None, 1.0, 1.0, ndof)
    K = assemble_tangent([group], U, None, 1.0, 1.0, ndof).tocsr()
    A = PETSc.Mat().createAIJ(size=K.shape, comm=PETSc.COMM_SELF,
                              csr=(K.indptr.astype(PETSc.IntType),
                                   K.indices.astype(PETSc.IntType), K.data))
    A.assemble()
    b = PETSc.Vec().createWithArray(-np.asarray(R), comm=PETSc.COMM_SELF)
    xbc = b.duplicate(); xbc.set(0.0)                       # zero increment at Dirichlet dofs
    A.zeroRowsColumns(drows.astype(PETSc.IntType), diag=1.0, x=xbc, b=b)
    return A, b, ndof


def solve(A, b, kind, ndof, rtol=1e-10):
    """Solve with GMRES + (ASM | FieldSplit-GAMG-per-field). Returns (x, iters, reason)."""
    ksp = PETSc.KSP().create(PETSc.COMM_SELF)
    ksp.setOperators(A)
    ksp.setType("gmres")
    ksp.setTolerances(rtol=rtol, max_it=3000)
    pc = ksp.getPC()
    if kind == "fieldsplit":
        is_phi = PETSc.IS().createGeneral(np.arange(0, ndof, 2).astype(PETSc.IntType),
                                          comm=PETSc.COMM_SELF)
        is_T = PETSc.IS().createGeneral(np.arange(1, ndof, 2).astype(PETSc.IntType),
                                        comm=PETSc.COMM_SELF)
        pc.setType("fieldsplit")
        pc.setFieldSplitIS(("phi", is_phi), ("T", is_T))
        pc.setFieldSplitType(PETSc.PC.CompositeType.ADDITIVE)
        ksp.setUp()
        for sub in pc.getFieldSplitSubKSP():               # GAMG on each scalar field
            sub.setType("preonly"); sub.getPC().setType("gamg")
    else:
        pc.setType(kind)
    x = b.duplicate()
    ksp.solve(b, x)
    return x, ksp.getIterationNumber(), int(ksp.getConvergedReason())


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 256
    A, b, ndof = assemble(n)
    print(f"Coupled electro-thermal linear system: {ndof:,} DOF ({n}x{n}, 2 fields, compiled kernel)")
    xa, ia, ra = solve(A, b, "asm", ndof)
    xf, iff, rf = solve(A, b, "fieldsplit", ndof)
    match = float(np.max(np.abs(xa.getArray() - xf.getArray())) /
                  max(1e-30, np.max(np.abs(xa.getArray()))))
    print(f"  GMRES + ASM                 : {ia:4d} iters  (reason {ra})")
    print(f"  GMRES + FieldSplit(GAMG/GAMG): {iff:4d} iters  (reason {rf})")
    print(f"  -> FieldSplit cuts iterations {ia/max(iff,1):.0f}x; same solution (rel {match:.1e})")
    print("  This run compares the two PCs at one checked size; retain a final-revision")
    print("  size/rank sweep before making scalability or mesh-independence claims.")


if __name__ == "__main__":
    main()
