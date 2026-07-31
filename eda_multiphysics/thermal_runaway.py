"""Thermal runaway: temperature-dependent leakage bifurcation (the hard nonlinear case).

Leakage power rises ~exponentially with temperature, P_leak(T)=P0 exp(beta (T-T0)),
creating positive electrothermal feedback. Balanced against linear heat removal
G(T-Tamb), the steady state is a fixed point that can DISAPPEAR above a critical
dynamic power (a saddle-node bifurcation -> runaway, no steady solution).

Analytic oracle (tangency condition): the fixed point vanishes when the leakage slope
equals the removal slope, P0 beta exp(beta (Tc-T0)) = G, giving the critical
temperature Tc and critical power Pc = G(Tc-Tamb) - P0 exp(beta(Tc-T0)) (Bhat et al.,
ACM TECS 2017; a standard CMOS thermal-runaway criterion). This supplies a focused
analytic regression for fixed-point behavior around the model bifurcation: it is
not validation of a physical device.

Run:  python -m eda_multiphysics.thermal_runaway
"""

from __future__ import annotations

import numpy as np

PARAMS = dict(P0=0.5, beta=0.06, T0=298.0, G=0.1, Tamb=298.0)   # W, 1/K, K, W/K, K


def critical(*, P0, beta, T0, G, Tamb):
    """Analytic critical temperature and dynamic power (saddle-node tangency)."""
    Tc = T0 + np.log(G / (P0 * beta)) / beta
    Pc = G * (Tc - Tamb) - P0 * np.exp(beta * (Tc - T0))
    return Tc, Pc


def steady_T(Pdyn, *, P0, beta, T0, G, Tamb, relax=0.4, tol=1e-10, maxit=5000):
    """Fixed-point electrothermal solve. Returns (T, iters) or (None, iters) on runaway."""
    T = float(Tamb)
    for it in range(1, maxit + 1):
        f = Tamb + (Pdyn + P0 * np.exp(beta * (T - T0))) / G
        if not np.isfinite(f) or (f - Tamb) > 500.0:
            return None, it                                  # diverged -> runaway
        Tn = (1 - relax) * T + relax * f
        if abs(Tn - T) < tol:
            return Tn, it
        T = Tn
    return None, maxit


def gate_runaway_critical():
    Tc, Pc = critical(**PARAMS)
    Tsub, _ = steady_T(0.95 * Pc, **PARAMS)                  # below Pc -> converges
    Tsup, _ = steady_T(1.05 * Pc, **PARAMS)                  # above Pc -> runaway
    ok = (Tsub is not None) and (Tsub < Tc) and (Tsup is None)
    return dict(name="thermal-runaway critical power (tangency)", ok=ok,
                detail=f"Pc={Pc:.3f}W Tc={Tc:.1f}K; 0.95Pc->{Tsub:.1f}K, 1.05Pc->runaway")


def gate_runaway_balance():
    # the converged subcritical fixed point must satisfy the power balance exactly
    Tc, Pc = critical(**PARAMS)
    P = 0.9 * Pc
    T, _ = steady_T(P, **PARAMS)
    p = PARAMS
    resid = (P + p["P0"] * np.exp(p["beta"] * (T - p["T0"]))) - p["G"] * (T - p["Tamb"])
    return dict(name="runaway fixed point satisfies power balance", ok=abs(resid) < 1e-6,
                detail=f"residual={resid:.1e} W")


def main():
    for g in (gate_runaway_critical, gate_runaway_balance):
        r = g()
        print(f"  {r['name']:<46}{'PASS' if r['ok'] else 'FAIL':>6}  {r['detail']}")


if __name__ == "__main__":
    main()
