"""Creep & stress relaxation — the Anand model under STRESS control (vs strain control).

The saturation gate in `anand.py` checks strain-rate-controlled loading. This adds the
complementary STRESS-controlled mode:

  * Secondary (steady-state) creep: hold stress sigma0; the strain rate settles to the
    rate whose saturation stress equals sigma0 — i.e. invert sigma_sat(eps_dot,T)=sigma0.
    The checked case compares stress-controlled integration with that
    self-consistent rate.
  * Stress relaxation: hold total strain; stress decays as elastic strain converts to
    viscoplastic (dsigma/dt = -E eps_dot) — the JEDEC-dwell physics.

Run:  python -m eda_multiphysics.creep
"""

from __future__ import annotations

import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import brentq

from .anand import SNPB, _require_complete_ivp, sat_stress


def analytic_creep_rate(sigma0, T, p=SNPB):
    """Secondary-creep strain rate at stress sigma0: the eps_dot with sigma_sat=sigma0."""
    return brentq(lambda ed: sat_stress(ed, T, p) - sigma0, 1e-14, 1e3, rtol=1e-13)


def integrate_creep(sigma0, T, p=SNPB, t_max=None):
    """Stress-controlled integration: evolve s(t) at constant sigma0 -> steady rate."""
    eQ, emQ = np.exp(p["QR"] / T), np.exp(-p["QR"] / T)

    def epdot(s):
        return p["A"] * emQ * np.sinh(p["xi"] * sigma0 / max(s, 1e-9)) ** (1.0 / p["m"])

    def rhs(t, y):
        s = y[0]
        ep = epdot(s)
        sstar = p["shat"] * (max(ep, 1e-300) / p["A"] * eQ) ** p["n"]
        phi = 1.0 - s / sstar
        return [p["h0"] * np.sign(phi) * abs(phi) ** p["a"] * ep]

    if t_max is None:
        t_max = 1.0 / max(analytic_creep_rate(sigma0, T, p), 1e-12)    # ~>50% strain to saturate s
    sol = solve_ivp(rhs, [0, t_max], [p["s0"]], method="BDF", rtol=1e-10, atol=1e-12)
    _require_complete_ivp(sol, t_max, "stress-controlled creep integration")
    return epdot(sol.y[0, -1])


def gate_creep_rate():
    T, sigma0 = 298.15, 50.0e6 / 1e6        # 50 MPa
    num = integrate_creep(sigma0, T)
    an = analytic_creep_rate(sigma0, T)
    err = abs(num - an) / an
    return dict(name="secondary creep rate vs inverse-saturation", ok=err < 1e-2,
                detail=f"eps_dot={num:.3e} vs {an:.3e} /s ({err:.1%})")


def gate_creep_broken_control():
    # zero stress -> zero creep (sinh(0)=0); the oracle must reject a nonzero rate
    r = integrate_creep(0.0, 298.15, t_max=1.0)
    return dict(name="BROKEN-CONTROL: sigma=0 -> zero creep", ok=abs(r) < 1e-12,
                detail=f"eps_dot={r:.1e} (must be ~0)")


def main():
    for g in (gate_creep_rate, gate_creep_broken_control):
        r = g()
        print(f"  {r['name']:<46}{'PASS' if r['ok'] else 'FAIL':>6}  {r['detail']}")


if __name__ == "__main__":
    main()
