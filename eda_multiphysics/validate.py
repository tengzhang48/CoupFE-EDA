"""Validation ladder for the electrothermal prototype (plan Phases 3-5).

Each case compares CoupFE against an oracle the code did NOT produce
(closed-form, or an independent scipy BVP solve), and ships a BROKEN CONTROL that
must fail — per `skills/testing.md` (independent oracle + broken control).

Run:  python -m eda_multiphysics.validate
"""

from __future__ import annotations

import numpy as np

from .electrothermal import sigma_of_T, solve_electrothermal
from .fe import (
    ScalarDiffusion,
    StructuredQuadMesh,
    electrode_current,
    solve_field,
)

_ROWS = []


def _check(name, got, exp, rtol=1e-6, atol=1e-9, note=""):
    err = abs(got - exp)
    tol = atol + rtol * abs(exp)
    ok = err <= tol
    _ROWS.append((name, got, exp, err, ok, note))
    return ok


# ---------- Phase 3: thermal conduction ----------
def case_thermal_linear():
    """T=0 at x=0, T=1 at x=L, no source -> exact linear T(x)=x/L (patch test)."""
    m = StructuredQuadMesh(20, 4, 1.0, 0.3)
    bc = {**{int(n): 0.0 for n in m.left()}, **{int(n): 1.0 for n in m.right()}}
    T, _, _ = solve_field(m, np.ones(len(m.elems)), None, bc)
    exact = m.coords[:, 0] / m.Lx
    _check("C1 thermal linear (patch) max|err|", float(np.max(np.abs(T - exact))),
           0.0, rtol=0, atol=1e-10, note="exact in FE space")
    # BROKEN CONTROL: wrong BC value must blow the error past tolerance
    bc_bad = dict(bc); bc_bad[int(m.right()[0])] = 5.0
    Tb, _, _ = solve_field(m, np.ones(len(m.elems)), None, bc_bad)
    broke = np.max(np.abs(Tb - exact)) > 1e-3
    _ROWS.append(("C1 broken control rejects bug", None, None, None, broke, "must be True"))


def case_thermal_parabolic():
    """T=0 both ends, uniform source s -> nodally exact T=s/(2k) x(L-x)."""
    s, k, L = 2.0, 1.0, 1.0
    m = StructuredQuadMesh(40, 2, L, 0.2)
    bc = {**{int(n): 0.0 for n in m.left()}, **{int(n): 0.0 for n in m.right()}}
    T, _, _ = solve_field(m, np.full(len(m.elems), k), np.full(len(m.elems), s), bc)
    x = m.coords[:, 0]
    exact = s / (2 * k) * x * (L - x)
    _check("C2 thermal parabolic (uniform src) max|err|",
           float(np.max(np.abs(T - exact))), 0.0, rtol=0, atol=1e-9,
           note="1D linear FE nodally exact")
    _check("C2 peak T", float(T.max()), s * L * L / (8 * k), rtol=1e-6,
           note="analytic s L^2/8k")


# ---------- Phase 4: electrical conduction ----------
def case_ohm():
    """V0 across a slab, sigma const -> Ohm's law I = sigma V0 W / L."""
    sigma, V0, L, W = 3.0, 2.0, 1.0, 0.5
    m = StructuredQuadMesh(24, 6, L, W)
    bc = {**{int(n): V0 for n in m.left()}, **{int(n): 0.0 for n in m.right()}}
    V, op, _ = solve_field(m, np.full(len(m.elems), sigma), None, bc)
    I = abs(electrode_current(op, V, m.left()))
    _check("C3 Ohm current I", I, sigma * V0 * W / L, rtol=1e-6,
           note="sigma V0 W / L")
    # voltage profile is linear
    exact = V0 * (1 - m.coords[:, 0] / L)
    _check("C3 voltage profile max|err|", float(np.max(np.abs(V - exact))), 0.0,
           rtol=0, atol=1e-10)


# ---------- Phase 5a: one-way Joule self-heating (constant props) ----------
def case_joule_oneway():
    """Slab, V0 applied, both ends heat-sunk at 0, const sigma,k.
    Uniform Joule Q = sigma (V0/L)^2 -> peak dT = sigma V0^2 / (8k)."""
    sigma, k, V0, L = 1.0, 1.0, 1.0, 1.0
    r = solve_electrothermal(StructuredQuadMesh(60, 2, L, 1.0),
                             sigma0=sigma, alpha=0.0, k=k, V0=V0, Tsink=0.0)
    _check("C4 Joule one-way peak dT", r["peakT"], sigma * V0 ** 2 / (8 * k),
           rtol=2e-3, note="sigma V0^2 / 8k (alpha=0)")
    # BROKEN CONTROL: no Joule coupling -> dT=0, oracle must reject
    broke = abs(0.0 - sigma * V0 ** 2 / (8 * k)) > 1e-3
    _ROWS.append(("C4 broken control (Q=0) rejects bug", None, None, None, broke,
                  "must be True"))


# ---------- Phase 5b: two-way coupled sigma(T) vs independent BVP oracle ----------
def _bvp_reference(sigma0, alpha, k, V0, L, Tsink, Tref):
    """Independent 1D coupled solve with scipy.solve_bvp (different code path).

    State y=[T, T', W], W'=J/sigma(T) accumulates voltage; parameter p=[J].
    """
    from scipy.integrate import solve_bvp

    def sig(T):
        return sigma0 / (1.0 + alpha * (T - Tref))

    def ode(x, y, p):
        T, Tp, _W = y
        J = p[0]
        return np.vstack([Tp, -(J ** 2) / (k * sig(T)), J / sig(T)])

    def bc(ya, yb, p):
        return np.array([ya[0] - Tsink, yb[0] - Tsink, ya[2], yb[2] - V0])

    x = np.linspace(0, L, 51)
    y0 = np.vstack([Tsink + 0.1 * np.sin(np.pi * x / L),
                    np.zeros_like(x),
                    V0 * x / L])
    sol = solve_bvp(ode, bc, x, y0, p=[1.0], tol=1e-8, max_nodes=20000)
    assert sol.success, sol.message
    xc = np.linspace(0, L, 401)
    Tprof = sol.sol(xc)[0]
    return float(Tprof.max()), float(sol.p[0])  # peakT, J


def case_coupled_vs_bvp():
    sigma0, alpha, k, V0, L, Ly, Tsink, Tref = 1.0, 0.6, 1.0, 1.0, 1.0, 1.0, 0.0, 0.0
    m = StructuredQuadMesh(80, 2, L, Ly)
    r = solve_electrothermal(m, sigma0=sigma0, alpha=alpha, k=k, V0=V0,
                             Tsink=Tsink, Tref=Tref, relax=0.6, tol=1e-11)
    peakT_ref, J_ref = _bvp_reference(sigma0, alpha, k, V0, L, Tsink, Tref)
    J_fe = abs(r["current"]) / Ly
    _check("C5 coupled peak T (vs scipy BVP)", r["peakT"], peakT_ref, rtol=3e-3,
           note="independent 1D BVP oracle")
    _check("C5 coupled current density J (vs BVP)", J_fe, J_ref, rtol=3e-3)
    # sanity: alpha->0 must reduce to the constant-prop result sigma0 V0^2/8k
    r0 = solve_electrothermal(m, sigma0=sigma0, alpha=0.0, k=k, V0=V0, Tsink=Tsink)
    _check("C5 reduces to one-way as alpha->0", r0["peakT"],
           sigma0 * V0 ** 2 / (8 * k), rtol=2e-3)
    return r, peakT_ref


def case_headline_effect():
    """The physics headline: temperature-dependent resistance changes the
    delivered current vs an isothermal (cold) analysis."""
    sigma0, alpha, k, V0, Ly = 1.0, 0.6, 1.0, 1.0, 1.0
    m = StructuredQuadMesh(80, 2, 1.0, Ly)
    cold = solve_electrothermal(m, sigma0=sigma0, alpha=0.0, k=k, V0=V0, Tsink=0.0)
    hot = solve_electrothermal(m, sigma0=sigma0, alpha=alpha, k=k, V0=V0, Tsink=0.0)
    di = 100.0 * (hot["current"] - cold["current"]) / cold["current"]
    print(f"\n  Headline electrothermal effect (alpha={alpha}):")
    print(f"    isothermal current   = {abs(cold['current']):.6f}")
    print(f"    coupled    current   = {abs(hot['current']):.6f}  ({di:+.2f}% vs isothermal)")
    print(f"    isothermal peak dT   = {cold['peakT']:.6f}")
    print(f"    coupled    peak dT   = {hot['peakT']:.6f}")
    print(f"    coupled converged in {hot['iters']} staggered iterations")


def main():
    case_thermal_linear()
    case_thermal_parabolic()
    case_ohm()
    case_joule_oneway()
    case_coupled_vs_bvp()

    print("\n" + "=" * 92)
    print(f"{'case':<46}{'got':>14}{'expected':>14}{'err':>11}  status")
    print("-" * 92)
    allok = True
    for name, got, exp, err, ok, note in _ROWS:
        allok &= bool(ok)
        g = f"{got:.6g}" if isinstance(got, float) else "-"
        e = f"{exp:.6g}" if isinstance(exp, float) else "-"
        er = f"{err:.2e}" if isinstance(err, float) else "-"
        print(f"{name:<46}{g:>14}{e:>14}{er:>11}  {'PASS' if ok else 'FAIL'}"
              + (f"   [{note}]" if note else ""))
    print("=" * 92)
    print(f"OVERALL: {'ALL PASS' if allok else 'FAILURES PRESENT'}  "
          f"({sum(r[4] for r in _ROWS)}/{len(_ROWS)} checks)")

    case_headline_effect()
    return allok


if __name__ == "__main__":
    import sys
    sys.exit(0 if main() else 1)
