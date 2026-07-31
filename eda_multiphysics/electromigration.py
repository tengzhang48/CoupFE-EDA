"""Electromigration reliability: Black's equation + Blech immortality.

Extends the demonstration arc (IR-drop → thermal → TSV stress → solder fatigue →
**EM**) with compact screening equations. EM lifetime is driven by current density J (from the
PDN-graph / PDNSim) and temperature T (from the electrothermal solve):

  Black's equation (Black 1969; JEDEC JEP119):  MTTF = A · J^(-n) · exp(Ea / kB T)
  Blech immortality (Blech 1976):  a segment is EM-immortal if  j·L < (j·L)_crit,
    where (j·L)_crit = Ω · σ_crit / (Z* · e · ρ)  (back-stress balances the e-wind).

These are established closed-form models; this module applies them to J,T fields
supplied by the demonstration workflow. Gates check the Black-equation arithmetic
and a published Blech-product range; they do not qualify a device or its fields.

Run:  python -m eda_multiphysics.electromigration
"""

from __future__ import annotations

import numpy as np

KB_EV = 8.617333e-5      # Boltzmann constant [eV/K]
E_CHG = 1.602177e-19     # elementary charge [C]

# representative Cu interconnect EM parameters (JEDEC-class; Hu/Lloyd literature)
CU_EM = dict(n=1.0, Ea=0.9,                 # void-growth limited: n≈1, Ea≈0.9 eV
             Omega=1.18e-29, Zstar=5.0, rho=2.2e-8, sigma_crit=5.0e8)  # SI


def black_mttf(J, T, *, A=1.0, n=1.0, Ea=0.9):
    """Black's MTTF (arbitrary units via A). J [A/m^2], T [K]."""
    return A * J ** (-n) * np.exp(Ea / (KB_EV * T))


def acceleration_factor(J_use, T_use, J_str, T_str, *, n=1.0, Ea=0.9):
    """MTTF(use)/MTTF(stress) — the standard EM qualification acceleration factor."""
    return (J_use / J_str) ** (-n) * np.exp(Ea / KB_EV * (1.0 / T_use - 1.0 / T_str))


def blech_product_crit(p=CU_EM):
    """Critical (j·L) for EM immortality [A/m]  = Ω σ_crit / (Z* e ρ)."""
    return p["Omega"] * p["sigma_crit"] / (p["Zstar"] * E_CHG * p["rho"])


def em_screen(J, L, T, *, p=CU_EM, A=1e30):
    """Per-segment EM screen. J [A/m^2], L [m], T [K]. Returns dict with immortal
    mask and MTTF (Black, hours) for the mortal segments."""
    J, L, T = np.atleast_1d(J), np.atleast_1d(L), np.atleast_1d(T)
    jL_crit = blech_product_crit(p)
    immortal = (J * L) < jL_crit
    mttf = black_mttf(J, T, A=A, n=p["n"], Ea=p["Ea"])
    mttf = np.where(immortal, np.inf, mttf)
    return dict(jL_crit=jL_crit, immortal=immortal, mttf=mttf,
                worst_mttf=float(np.min(mttf)), n_immortal=int(immortal.sum()))


# ---- gates (closed-form and published-range checks) ----
def gate_black_acceleration():
    """Black-equation temperature acceleration factor (Ea=0.9 eV, equal J):
    a 110→150 C stress change gives ~13.1x for these assumptions."""
    af = acceleration_factor(1.0, 110 + 273.15, 1.0, 150 + 273.15, n=1.0, Ea=0.9)
    # closed-form check: exp(Ea/kB (1/T_use - 1/T_str))
    ref = np.exp(0.9 / KB_EV * (1 / 383.15 - 1 / 423.15))
    err = abs(af - ref) / ref
    ok = err < 1e-12 and abs(af - 13.14) / 13.14 < 0.01
    return dict(name="EM Black temp accel factor (110->150C)", ok=ok,
                detail=f"AF={af:.2f} (closed form ~13.1x)")


def gate_blech_product():
    """Blech product from Cu microscopic parameters must land in the published
    empirical range ~1000-6000 A/cm."""
    jL = blech_product_crit(CU_EM) / 100.0      # A/m -> A/cm
    ok = 1000.0 < jL < 6000.0
    return dict(name="EM Blech product in published range", ok=ok,
                detail=f"(jL)_crit={jL:.0f} A/cm (range 1000-6000)")


def gate_em_broken_control():
    """Broken control: ignoring the Blech immortality filter would flag a short
    high-current segment as failing; the screen must mark it immortal instead."""
    r = em_screen(J=2e9, L=1e-6, T=400.0)        # high J, very short segment
    return dict(name="BROKEN-CONTROL: Blech immortality applied", ok=bool(r["immortal"][0]),
                detail="short high-J segment is immortal")


def main():
    print("Electromigration (Black + Blech) — standard-model gates:")
    for g in (gate_black_acceleration, gate_blech_product, gate_em_broken_control):
        r = g()
        print(f"  {r['name']:<46}{'PASS' if r['ok'] else 'FAIL':>6}  {r['detail']}")
    # tiny illustrative screen of a few PDN-like segments
    print("\n  illustrative EM screen (J[A/cm^2], L[um], T[C]):")
    Js = np.array([5e5, 2e6, 1e7]) * 1e4         # A/cm^2 -> A/m^2
    Ls = np.array([50.0, 5.0, 0.5]) * 1e-6
    Ts = np.array([85.0, 110.0, 110.0]) + 273.15
    r = em_screen(Js, Ls, Ts)
    print(f"    (jL)_crit = {r['jL_crit']/100:.0f} A/cm; immortal segments: {r['n_immortal']}/3")


if __name__ == "__main__":
    main()
