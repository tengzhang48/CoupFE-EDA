"""Serial coupled-Newton driver shared by selected 3D and thermo-mechanical solves.

``coupled_newton(groups, ndof, dirichlet, linsolve)`` centralizes Dirichlet
application, residual/tangent assembly, update, and increment checking. The
linear backend has the contract ``linsolve(K_csr, R, drows) -> (dU, info)``.
See ``docs/api.md`` for the public boundary and ``docs/VALIDATION_GUIDE.md``
for the checked cases.
"""
from __future__ import annotations

import time

import numpy as np
import scipy.sparse.linalg as spla


def coupled_newton(
    groups,
    ndof,
    dirichlet,
    linsolve,
    *,
    maxit=20,
    tol=1e-11,
    residual_rtol=1e-8,
    residual_atol=1e-10,
):
    """Serial Newton for a list of ElementGroups (the assembler sums them -> multi-material is
    just >1 group). `dirichlet` maps dof -> value. `linsolve(K_csr, R, drows) -> (dU, info)`.
    Returns (U, n_newton, info) where info carries the last solve's keys plus `t_asm`/`t_solve`
    (so callers that report timing keep their public return unchanged)."""
    from coupfe import assemble_residual, assemble_tangent
    drows = np.array(sorted(dirichlet), dtype=int)
    dvals = np.array([dirichlet[int(i)] for i in drows], dtype=float)
    free = np.ones(ndof, dtype=bool)
    free[drows] = False

    def free_norm(values):
        values = np.asarray(values)
        return float(np.max(np.abs(values[free]))) if np.any(free) else 0.0

    U = np.zeros(ndof)
    n_newton = 0
    info: dict = {}
    t_asm = 0.0
    t_sol = 0.0
    residual_scale = None
    increment_norm = float("inf")
    for _ in range(maxit):
        U[drows] = dvals
        ta = time.time()
        R, _ = assemble_residual(groups, U, None, 1.0, 1.0, ndof)
        K = assemble_tangent(groups, U, None, 1.0, 1.0, ndof).tocsr()
        t_asm += time.time() - ta
        if residual_scale is None:
            residual_scale = max(1.0, free_norm(R))
        ts = time.time()
        dU, info = linsolve(K, np.asarray(R), drows)
        t_sol += time.time() - ts
        dU = np.asarray(dU, dtype=float)
        if not np.all(np.isfinite(dU)):
            raise RuntimeError("coupled Newton linear solve produced a non-finite increment")
        U = U + dU
        if not np.all(np.isfinite(U)):
            raise RuntimeError("coupled Newton update produced a non-finite solution")
        increment_norm = float(np.max(np.abs(dU))) if dU.size else 0.0
        n_newton += 1
        if increment_norm < tol:
            break

    U[drows] = dvals
    ta = time.time()
    R_final, _ = assemble_residual(groups, U, None, 1.0, 1.0, ndof)
    t_asm += time.time() - ta
    residual_norm = free_norm(R_final)
    residual_limit = max(residual_atol, residual_rtol * (residual_scale or 1.0))
    if not np.isfinite(residual_norm) or not (
        increment_norm < tol and residual_norm <= residual_limit
    ):
        raise RuntimeError(
            "coupled Newton solve did not converge: "
            f"iterations={n_newton}/{maxit}, increment_norm={increment_norm:.6e}, "
            f"increment_tolerance={tol:.6e}, residual_norm={residual_norm:.6e}, "
            f"residual_limit={residual_limit:.6e}"
        )
    info = {
        **info,
        "converged": True,
        "increment_norm": increment_norm,
        "residual_norm": residual_norm,
        "t_asm": t_asm,
        "t_solve": t_sol,
    }
    return U, n_newton, info


def direct_linsolve(K, R, drows):
    """scipy SuperLU with symmetric-RHS Dirichlet (zero the BC rows, set increment 0)."""
    Kl = K.tolil(); rhs = -np.asarray(R, float); rhs[drows] = 0.0
    for r in drows:
        Kl.rows[int(r)] = [int(r)]; Kl.data[int(r)] = [1.0]
    return spla.spsolve(Kl.tocsr(), rhs), {}
