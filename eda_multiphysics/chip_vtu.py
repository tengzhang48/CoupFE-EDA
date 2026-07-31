"""Composed V-T-u research chain: case PDN -> thermal -> TSV mechanics.

Chains two separately checked components on a caller-supplied design case:
  V -> T : the compact coupled electrothermal solve (electrothermal_chip)
           gives an operating temperature field dT_op(x, y) over the die.
  T -> u : the Lamé-benchmarked axisymmetric thermoelastic relation
           maps each parametric TSV's local temperature to CTE-mismatch stress.

A TSV array is placed over the die; each via's stress is driven by the LOCAL
electrothermal temperature. Two physically-distinct, both-correct outputs:

  * operating thermal-cycling swing  (dT = dT_op, ambient->operating): the fatigue
    driver -- LARGEST where the chip is hottest (the electrothermal hotspot).
  * total static stress (dT = dT_op - dT_anneal): process residual + operating;
    the operating heat RELIEVES the cooling-induced residual, so it is LOWEST at
    the hotspot.

The composed three-field output has no single closed-form or experimental
oracle. Component evidence does not make it a qualified real-device prediction.

Run:  python -m eda_multiphysics.chip_vtu <case_dir> <pdn.sp> <P_total_W>
"""

from __future__ import annotations

import argparse
import os

import numpy as np

from .electrothermal_chip import run as run_et
from .tsv_stress import lame_sigma_r

DT_ANNEAL = 395.0   # 420C anneal -> 25C ambient stress-free cooling (K)


def _interp_dT(et, px, py):
    """Operating dT at die-local point (px,py) [m] (containing-element mean)."""
    mesh, dT = et["mesh"], et["dT"]
    nx, ny = mesh.nx, mesh.ny
    i = min(max(int(px / et["Lx"] * nx), 0), nx - 1)
    j = min(max(int(py / et["Ly"] * ny), 0), ny - 1)
    return float(dT[mesh.elems[j * nx + i]].mean())


def run(case_dir, spice, P_total, *, D_tsv=10.0, r_ko=20.0, ngrid=9,
        k_si=148.0, t_si=100e-6, h_v=1.0e4, label=""):
    et = run_et(case_dir, spice, P_total, k_si=k_si, t_si=t_si, h_v=h_v)
    Lx, Ly = et["Lx"], et["Ly"]
    spread_um = (k_si * t_si / h_v) ** 0.5 * 1e6      # lateral spreading length
    xs = np.linspace(0.08, 0.92, ngrid) * Lx
    ys = np.linspace(0.08, 0.92, ngrid) * Ly

    swing = np.zeros((ngrid, ngrid))     # operating cycling stress amplitude (MPa)
    total = np.zeros((ngrid, ngrid))     # residual + operating static stress (MPa)
    Tg = np.zeros((ngrid, ngrid))
    for j, py in enumerate(ys):
        for i, px in enumerate(xs):
            Top = _interp_dT(et, px, py)
            Tg[j, i] = Top
            swing[j, i] = abs(lame_sigma_r(r_ko, D_tsv, Top)) / 1e6
            total[j, i] = abs(lame_sigma_r(r_ko, D_tsv, Top - DT_ANNEAL)) / 1e6

    jhot = np.unravel_index(Tg.argmax(), Tg.shape)
    hx = xs[jhot[1]] * 1e6 + et["dx0"]
    hy = ys[jhot[0]] * 1e6 + et["dy0"]
    Tspan = 100.0 * (Tg.max() - Tg.min()) / Tg.max()
    sspan = 100.0 * (swing.max() - swing.min()) / swing.max()
    die_um = et["die_um"][0]

    design = os.path.basename(os.path.normpath(case_dir))
    print(f"\n=== Full V-T-u chain on {design}{label} "
          f"({et['n_inst']} cells, die {die_um}x{et['die_um'][1]} um, P={P_total*1e3:.1f} mW) ===")
    print(f"V->T (coupled electrothermal): peak dT_op={et['peakdT']:.2f} K, "
          f"worst IR {et['ir_coupled']:.3e} V (R(T) {et['pct_ir']:+.1f}%)")
    print(f"  lateral spreading length sqrt(k t / h_v) = {spread_um:.0f} um  "
          f"vs die {die_um:.0f} um -> {'near-isothermal' if spread_um > 2*die_um else 'real gradient'}")
    print(f"T->u ({ngrid}x{ngrid} TSV array, D={D_tsv:.0f} um, keep-out r={r_ko:.0f} um):")
    print(f"  dT_op across array       : {Tg.min():.2f}..{Tg.max():.2f} K  "
          f"({Tspan:.1f}% range; hotspot at ({hx:.0f},{hy:.0f}) um)")
    print(f"  operating cycling swing  : {swing.min():.3f}..{swing.max():.3f} MPa  "
          f"({sspan:.1f}% range, worst at hotspot)")
    print(f"  total static TSV stress  : {total.min():.2f}..{total.max():.2f} MPa  "
          f"(lowest at hotspot: operating heat relieves the cooling residual)")
    if sspan > 3:
        print("  => meaningful spatial variation: TSVs in the hotspot have the WORST")
        print("     cycling-fatigue amplitude but LOWEST static stress (opposite design")
        print("     implications) -- which a uniform/process-only estimate cannot reveal.")
        print("\n  operating-cycling-swing map (normalized; die x->, y^):")
        lo, hi = swing.min(), swing.max()
        ramp = " .:-=+*#%@"
        for j in range(ngrid - 1, -1, -1):
            print("    " + "".join(
                ramp[min(int((swing[j, i] - lo) / (hi - lo) * (len(ramp) - 1)), len(ramp) - 1)]
                for i in range(ngrid)))
    else:
        print("  => near-uniform: this die is laterally isothermal, so per-TSV thermal")
        print("     stress ~ a single uniform estimate; the chain shows the coupling")
        print("     matters only when the spreading length ~ die size (below).")
    return dict(swing=swing, total=total, Tg=Tg, sspan=sspan, spread_um=spread_um)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run the full V-T-u chip chain in two regimes.")
    parser.add_argument("case_dir", help="OpenROAD case directory")
    parser.add_argument("spice", help="PDNSim write_pg_spice netlist")
    parser.add_argument("total_power_W", type=float, help="total chip power in W")
    args = parser.parse_args(argv)
    # thick evenly-cooled die: laterally isothermal
    run(args.case_dir, args.spice, args.total_power_W, t_si=100e-6, h_v=1.0e4,
        label=" [thick die, conventional cooling]")
    # thinned 3D-IC die + microchannel cooling (the TSV-relevant regime)
    run(args.case_dir, args.spice, args.total_power_W, t_si=20e-6, h_v=1.0e5,
        label=" [thinned 3D-IC die, microchannel cooling]")


if __name__ == "__main__":
    main()
