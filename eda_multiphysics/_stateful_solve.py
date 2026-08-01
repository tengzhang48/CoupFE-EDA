"""Fail-closed increment solve for EDA's path-dependent demonstration models.

Core intentionally returns an iterate and commits operators after its Newton
loop; its iteration count is not a convergence flag.  The stateful solder
examples need a stricter transaction boundary: solve without committing,
evaluate the same residual criterion used by Core, and commit exactly once only
after that criterion is met.
"""

from __future__ import annotations

import numpy as np

from coupfe import assemble_residual, newton_solve


class _DeferredCommit:
    """Delegate an operator while suppressing Core's automatic commit."""

    def __init__(self, operator):
        self._operator = operator

    def __getattr__(self, name):
        return getattr(self._operator, name)

    def commit(self, U, state, t, dt):
        return state


def solve_stateful_increment(
    operator,
    U0,
    dirichlet,
    *,
    t=1.0,
    dt=1.0,
    rtol=1.0e-9,
    maxit=60,
):
    """Solve one path-dependent increment and commit it only if converged.

    The acceptance rule is Core's documented Newton rule:
    ``||R_free|| < rtol*||R0_free||`` or ``||R_free|| < 1e-14``.  No separate
    application tolerance is introduced.  A failed increment raises before any
    material state is advanced.

    Returns ``(U, info)`` where ``info`` records the initial/final free-residual
    norms and the Core iteration count.
    """

    U_start = np.asarray(U0, dtype=float).copy()
    constrained = np.asarray(sorted(dirichlet), dtype=int)
    for dof, value in dirichlet.items():
        U_start[int(dof)] = float(value)
    free = np.ones(operator.ndof, dtype=bool)
    free[constrained] = False

    R0, _ = assemble_residual(
        [operator], U_start, None, t, dt, operator.ndof
    )
    initial_norm = float(np.linalg.norm(R0[free])) if np.any(free) else 0.0
    reference_norm = max(initial_norm, 1.0e-300)

    trial = _DeferredCommit(operator)
    U, _, iterations = newton_solve(
        [trial],
        U0,
        None,
        operator.ndof,
        dirichlet,
        t=t,
        dt=dt,
        rtol=rtol,
        maxit=maxit,
    )
    R, _ = assemble_residual([operator], U, None, t, dt, operator.ndof)
    final_norm = float(np.linalg.norm(R[free])) if np.any(free) else 0.0
    residual_limit = max(rtol * reference_norm, 1.0e-14)
    converged = (
        np.all(np.isfinite(U))
        and np.isfinite(final_norm)
        and final_norm < residual_limit
    )
    if not converged:
        raise RuntimeError(
            "stateful Newton increment did not converge; material state was not committed: "
            f"iterations={iterations}, initial_residual={initial_norm:.6e}, "
            f"final_residual={final_norm:.6e}, Core_limit={residual_limit:.6e}"
        )

    operator.commit(U, None, t, dt)
    return U, {
        "iterations": int(iterations),
        "initial_residual": initial_norm,
        "final_residual": final_norm,
        "relative_residual": final_norm / reference_norm,
        "residual_limit": residual_limit,
        "residual_fraction_of_limit": final_norm / residual_limit,
    }
