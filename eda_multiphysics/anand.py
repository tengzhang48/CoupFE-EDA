"""Anand unified viscoplastic model -- the INDUSTRY-STANDARD solder constitutive law.

The Anand model (Anand 1985; Brown, Kim, Anand 1989) is the de-facto industrial
standard for solder/interconnect viscoplasticity, built into ANSYS, Abaqus, and
Simcenter for electronic-packaging thermal-cycling reliability. Nine constants:
A, Q/R, xi, m (flow) and s0, h0, s-hat, n, a (deformation-resistance evolution).

Flow rule (equivalent plastic strain rate):
    eps_p_dot = A exp(-Q/RT) [ sinh(xi sigma / s) ]^(1/m)
Deformation-resistance evolution:
    s_dot = h0 |1 - s/s*|^a sign(1 - s/s*) eps_p_dot,
    s* = s_hat [ (eps_p_dot / A) exp(Q/RT) ]^n

TRUST GATE (exact analytic oracle, derived from the published model): at constant
strain rate and temperature the response saturates (s->s*, eps_p_dot->eps_dot) to a
steady-state flow stress with the CLOSED FORM
    z = (eps_dot/A) exp(Q/RT);  s* = s_hat z^n;  sigma_sat = (s*/xi) asinh(z^m).
A correct integrator must reproduce sigma_sat. This is the standard verification for
viscoplastic constitutive integrators -- the model's own analytic steady state.

Parameter set: 62Sn36Pb2Ag eutectic-class solder, Cheng, Wang, Chen, Wilde, Becker,
"Viscoplastic Anand model for solder alloys and its application," Soldering &
Surface Mount Technology 12(2), 2000 (the canonical, widely-reproduced set).

Run:  python -m eda_multiphysics.anand
"""

from __future__ import annotations

import numpy as np
from scipy.integrate import solve_ivp

# Anand constants (62Sn36Pb2Ag; Cheng/Wang et al. 2000)
SNPB = dict(A=4.0e6, QR=9400.0, xi=1.5, m=0.303,
            s0=12.41, h0=1378.95, shat=13.79, n=0.07, a=1.3, E=3.0e4)

# Anand constants (SAC305 = Sn-3.0Ag-0.5Cu, the modern lead-free industry standard).
# Motalab, Cai, Suhling, Lall, ITherm 2012 (DOI 10.1109/ITHERM.2012.6231522) /
# Motalab PhD dissertation (Auburn 2013), Table 4.1, *non-aged stress-strain fit* --
# cross-checked against arXiv:2204.05583 Table 2 and MDPI Materials 2023 16(14):4922.
# NOTE h0=180000 (the MDPI table drops a zero -> 18000; the dissertation value is
# 180000). E only sets the elastic ramp (the saturation oracle is E-independent);
# 43 GPa is a representative published SAC305 room-T modulus.
SAC305 = dict(A=3501.0, QR=9320.0, xi=4.0, m=0.25,
              s0=21.0, h0=180000.0, shat=30.2, n=0.01, a=1.78, E=4.3e4)

# Published external oracle: peak (= saturation, per dissertation Sec 4.3) flow stress
# read from Motalab dissertation Fig 3.10(a), SAC305 non-aged (T degC, eps_dot 1/s,
# stress MPa). Figure-digitized, so +-1-2 MPa (a few %).
SAC305_FIG310 = [(25.0, 1e-3, 40.5), (50.0, 1e-3, 33.5), (100.0, 1e-3, 24.0),
                 (125.0, 1e-3, 21.5), (25.0, 1e-4, 35.5), (25.0, 1e-5, 29.5)]


def _z(eps_dot, T, p):
    return (eps_dot / p["A"]) * np.exp(p["QR"] / T)


def sat_resistance(eps_dot, T, p):
    return p["shat"] * _z(eps_dot, T, p) ** p["n"]


def sat_stress(eps_dot, T, p):
    """Closed-form Anand steady-state (saturation) flow stress [MPa]."""
    z = _z(eps_dot, T, p)
    s_star = p["shat"] * z ** p["n"]
    return (s_star / p["xi"]) * np.arcsinh(z ** p["m"])


def plastic_strain_rate(sig, s, T, p):
    """Signed equivalent viscoplastic strain rate (sign-safe for reversed loading)."""
    s = max(s, 1e-9)
    mag = p["A"] * np.exp(-p["QR"] / T) * np.sinh(p["xi"] * abs(sig) / s) ** (1.0 / p["m"])
    return mag * np.sign(sig)


def _rhs(t, y, eps_dot, T, p):
    """ODE d/dt[sigma, s] for a uniaxial material point at prescribed strain rate."""
    sig, s = y
    ep = plastic_strain_rate(sig, s, T, p)
    epm = abs(ep)
    z = max(epm / p["A"], 1e-300) * np.exp(p["QR"] / T)
    sstar = p["shat"] * z ** p["n"]
    phi = 1.0 - s / sstar
    sdot = p["h0"] * np.sign(phi) * abs(phi) ** p["a"] * epm
    return [p["E"] * (eps_dot - ep), sdot]


def integrate_uniaxial(eps_dot, T, p, eps_max=0.10):
    """Constant-strain-rate uniaxial integration (stiff BDF) -> stress/strain history.

    Integrates the industry-standard Anand constitutive ODE (the law CoupFE's
    viscoplastic codegen emits as a UMAT); a stiff integrator handles the
    rate-stiffness robustly.
    """
    tmax = eps_max / eps_dot
    te = np.linspace(0, tmax, 400)
    sol = solve_ivp(_rhs, [0, tmax], [0.0, p["s0"]], method="BDF",
                    args=(eps_dot, T, p), t_eval=te, rtol=1e-9, atol=1e-9)
    return sol.t * eps_dot, sol.y[0], sol.y[1][-1]


def verify():
    p = SNPB
    print("Anand integrator vs CLOSED-FORM saturation stress (62Sn36Pb2Ag, "
          "Cheng/Wang 2000):")
    print(f"{'T(C)':>6}{'eps_dot(1/s)':>14}{'integrated(MPa)':>18}{'closed-form(MPa)':>18}{'err':>9}")
    worst = 0.0
    for TC in (25.0, 75.0, 125.0):
        T = TC + 273.15
        for ed in (1e-4, 1e-3, 1e-2):
            _, sh, _ = integrate_uniaxial(ed, T, p, eps_max=0.6)
            num = float(sh[-1])
            an = float(sat_stress(ed, T, p))
            err = abs(num - an) / abs(an)
            worst = max(worst, err)
            print(f"{TC:>6.0f}{ed:>14.0e}{num:>18.3f}{an:>18.3f}{err:>8.2%}")
    print(f"\n  max rel err vs analytic saturation = {worst:.2%}  "
          f"{'PASS' if worst < 0.02 else 'CHECK'}")
    # broken control: a wrong activation energy must break the match
    pbad = dict(p, QR=p["QR"] * 1.1)
    _, shb, _ = integrate_uniaxial(1e-3, 298.15, pbad)
    broke = abs(float(shb[-1]) - float(sat_stress(1e-3, 298.15, p))) / sat_stress(1e-3, 298.15, p) > 0.05
    print(f"  broken control (Q/R x1.1) rejected: {broke}")
    return worst < 0.02


def verify_sac305():
    """Reproduce a PUBLISHED SAC305 benchmark (Motalab Fig 3.10), two ways.

    (1) integrator vs the model's closed-form saturation -> rigorous, exact;
    (2) closed-form vs the published figure readings -> external benchmark.
    """
    p = SAC305
    print("\nSAC305 (Sn-3.0Ag-0.5Cu, Motalab 2012/2013) -- the modern lead-free standard")
    print("  (a) integrator vs closed-form saturation:")
    worst = 0.0
    for TC in (25.0, 75.0, 125.0):
        T = TC + 273.15
        for ed in (1e-4, 1e-3, 1e-2):
            _, sh, _ = integrate_uniaxial(ed, T, p, eps_max=0.20)
            err = abs(float(sh[-1]) - float(sat_stress(ed, T, p))) / float(sat_stress(ed, T, p))
            worst = max(worst, err)
    print(f"      worst integrator-vs-closed-form err = {worst:.3%}  "
          f"{'PASS' if worst < 0.02 else 'CHECK'}")
    print("  (b) closed-form saturation vs published Fig 3.10(a) (+-1-2 MPa figure read):")
    print(f"      {'T(C)':>5}{'eps_dot':>10}{'closed-form':>13}{'published':>11}{'diff':>8}")
    wd = 0.0
    for TC, ed, pub in SAC305_FIG310:
        cf = float(sat_stress(ed, TC + 273.15, p))
        d = abs(cf - pub) / pub
        wd = max(wd, d)
        print(f"      {TC:>5.0f}{ed:>10.0e}{cf:>13.2f}{pub:>11.1f}{d:>7.1%}")
    anchor = float(sat_stress(1e-3, 298.15, p))   # room-T anchor
    print(f"      room-T anchor: {anchor:.1f} MPa vs published ~40-41 MPa  "
          f"(worst figure diff {wd:.1%})")
    return worst < 0.02 and wd < 0.12


def _cycle_T(t, P, ramp, dwell, Tlo, Thi):
    """JEDEC-style temperature profile: ramp/dwell/ramp/dwell. Returns (T, dT/dt)."""
    tt = t % P
    dT = Thi - Tlo
    if tt < ramp:
        return Tlo + dT * tt / ramp, dT / ramp
    tt -= ramp
    if tt < dwell:
        return Thi, 0.0
    tt -= dwell
    if tt < ramp:
        return Thi - dT * tt / ramp, -dT / ramp
    return Tlo, 0.0


def thermal_cycle(p, *, Tlo=-40.0, Thi=125.0, dalpha=20e-6, ramp=200.0, dwell=600.0,
                  ncyc=6):
    """JEDEC JESD22-A104 thermal cycling of a constrained solder joint.

    Mechanical strain from CTE mismatch eps = dalpha*(T - T_ref); the Anand law
    gives the cyclic viscoplastic hysteresis. Returns the stabilized inelastic
    strain-energy-density per cycle (the Darveaux/energy damage metric) and the
    plastic strain range (the Coffin-Manson metric).
    """
    TloK, ThiK = Tlo + 273.15, Thi + 273.15
    Tref = 0.5 * (TloK + ThiK)
    P = 2 * ramp + 2 * dwell

    def rhs(t, y):
        sig, s, W, epl = y
        T, Tdot = _cycle_T(t, P, ramp, dwell, TloK, ThiK)
        ep = plastic_strain_rate(sig, s, T, p)
        epm = abs(ep)
        z = max(epm / p["A"], 1e-300) * np.exp(p["QR"] / T)
        sstar = p["shat"] * z ** p["n"]
        phi = 1.0 - s / sstar
        sdot = p["h0"] * np.sign(phi) * abs(phi) ** p["a"] * epm
        return [p["E"] * (dalpha * Tdot - ep), sdot, sig * ep, ep]

    tmax = ncyc * P
    te = np.linspace(0, tmax, ncyc * 600)
    sol = solve_ivp(rhs, [0, tmax], [0.0, p["s0"], 0.0, 0.0], method="BDF",
                    t_eval=te, rtol=1e-8, atol=1e-11, max_step=ramp / 4)
    t, W, epl = sol.t, sol.y[2], sol.y[3]
    Wc = [float(np.interp(k * P, t, W)) for k in range(ncyc + 1)]
    dW = [Wc[k] - Wc[k - 1] for k in range(1, ncyc + 1)]
    last = t >= (ncyc - 1) * P
    dep_range = float(epl[last].max() - epl[last].min())
    return dict(dW_per_cycle=dW, dW_stab=dW[-1], dep_range=dep_range, P=P)


def cycling_demo():
    p = SNPB
    r = thermal_cycle(p)
    print("\nJEDEC JESD22-A104 thermal cycling (-40<->125 C) of a constrained "
          "62Sn36Pb2Ag joint:")
    print(f"  cycle: {r['P']/60:.0f} min (ramp+dwell); CTE mismatch dalpha=20 ppm/K")
    print(f"  inelastic strain-energy-density per cycle dW: "
          f"{', '.join(f'{w:.3f}' for w in r['dW_per_cycle'])} MJ/m^3")
    print(f"  -> stabilized dW = {r['dW_stab']:.3f} MJ/m^3 (Darveaux/energy damage metric)")
    print(f"  -> plastic strain range  = {r['dep_range']*100:.3f} %  (Coffin-Manson metric)")
    # Coffin-Manson life (representative published SnPb constants: eps_f'=0.325, c=-0.5)
    epsf, c = 0.325, -0.5
    Nf = 0.5 * (r["dep_range"] / (2 * epsf)) ** (1.0 / c)
    print(f"  -> Coffin-Manson N_f ~ {Nf:,.0f} cycles "
          f"(eps_f'={epsf}, c={c}; representative published SnPb constants)")
    print("  NOTE: cycle dW stabilizes after the first cycle (shakedown). It is a")
    print("  commonly used industrial damage metric, but it is not signoff here;")
    print("  life constants are illustrative/published.")


if __name__ == "__main__":
    import sys
    ok = verify()
    ok_sac = verify_sac305()
    cycling_demo()
    sys.exit(0 if (ok and ok_sac) else 1)
