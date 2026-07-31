"""One serial coupled-Newton driver shared by the 3D / thermo-mechanical solves.

`etv_3d`, `thermomech_3d`, `thermomech_tsv`, `reliability_3d` each re-implemented the same loop
(set Dirichlet → assemble residual+tangent → apply BCs → linear solve → update → check ‖dU‖). This
factors it into `coupled_newton(groups, ndof, dirichlet, linsolve)` with a **pluggable linear
backend** `linsolve(K_csr, R, drows) -> (dU, info)`, so the only per-problem difference (direct vs
FieldSplit, scalar vs rigid-body) lives in the backend. Public solver behaviour is unchanged --
see `docs/REFACTOR_CONTRACT.md`.
"""
from __future__ import annotations

import time

import numpy as np
import scipy.sparse.linalg as spla


def coupled_newton(groups, ndof, dirichlet, linsolve, *, maxit=20, tol=1e-11):
    """Serial Newton for a list of ElementGroups (the assembler sums them -> multi-material is
    just >1 group). `dirichlet` maps dof -> value. `linsolve(K_csr, R, drows) -> (dU, info)`.
    Returns (U, n_newton, info) where info carries the last solve's keys plus `t_asm`/`t_solve`
    (so callers that report timing keep their public return unchanged)."""
    from coupfe import assemble_residual, assemble_tangent
    drows = np.array(sorted(dirichlet))
    dvals = np.array([dirichlet[int(i)] for i in drows])
    U = np.zeros(ndof); n_newton = 0; info: dict = {}; t_asm = 0.0; t_sol = 0.0
    for _ in range(maxit):
        U[drows] = dvals
        ta = time.time()
        R, _ = assemble_residual(groups, U, None, 1.0, 1.0, ndof)
        K = assemble_tangent(groups, U, None, 1.0, 1.0, ndof).tocsr()
        t_asm += time.time() - ta
        ts = time.time()
        dU, info = linsolve(K, np.asarray(R), drows)
        t_sol += time.time() - ts
        U = U + dU; n_newton += 1
        if np.max(np.abs(dU)) < tol:
            break
    info = {**info, "t_asm": t_asm, "t_solve": t_sol}
    return U, n_newton, info


def direct_linsolve(K, R, drows):
    """scipy SuperLU with symmetric-RHS Dirichlet (zero the BC rows, set increment 0)."""
    Kl = K.tolil(); rhs = -np.asarray(R, float); rhs[drows] = 0.0
    for r in drows:
        Kl.rows[int(r)] = [int(r)]; Kl.data[int(r)] = [1.0]
    return spla.spsolve(Kl.tocsr(), rhs), {}
