"""Phase 7 (solver-side proxy): hotspot -> reinforcement -> verified improvement.

The full plan routes the modification back through OpenROAD (absent here), but the
*decision and verification* are solver-side and fully demonstrable. We use the
physical PDN scenario: a load draws a FIXED current through the grid; a locally
under-provisioned power strap (reduced metal conductance) then causes both a
larger IR drop and a Joule hotspot. "Reinforcing" the strap (widen / add vias =
higher local conductance) is verified by re-running the coupled electrothermal
solve at the same delivered current.

Run:  python -m eda_multiphysics.design_loop_demo
"""

from __future__ import annotations

import numpy as np

from .electrothermal import solve_electrothermal
from .fe import StructuredQuadMesh


def _strap_scale(mesh, x_lo, x_hi, factor):
    xc = mesh.elem_centroids()[:, 0]
    scale = np.ones(len(mesh.elems))
    scale[(xc >= x_lo) & (xc <= x_hi)] = factor
    return scale


def _hotspot_x(mesh, T):
    return float(mesh.coords[np.argmax(T), 0])


def main():
    m = StructuredQuadMesh(100, 4, 1.0, 1.0)
    # fixed current demand; ground on the right; heat-sunk ends
    common = dict(sigma0=1.0, alpha=0.6, k=1.0, Tsink=0.0, relax=0.6, tol=1e-10,
                  I_inject=1.0)

    weak = _strap_scale(m, 0.45, 0.55, 0.35)          # under-provisioned strap
    reinforced = _strap_scale(m, 0.45, 0.55, 1.6)     # widened / via-reinforced

    base = solve_electrothermal(m, sigma_scale=weak, **common)
    mod = solve_electrothermal(m, sigma_scale=reinforced, **common)

    def line(tag, r):
        print(f"  {tag:<26} peakT={r['peakT']:.5f}  hotspot x={_hotspot_x(m, r['T']):.3f}"
              f"  IRdrop={r['Vdrop']:.5f}  I={abs(r['current']):.3f}  iters={r['iters']}")

    print("\nPhase-7 closed-loop electrothermal design modification (fixed current):")
    line("C  baseline (weak strap)", base)
    line("D  reinforced strap", mod)
    dT = 100.0 * (mod["peakT"] - base["peakT"]) / base["peakT"]
    dV = 100.0 * (mod["Vdrop"] - base["Vdrop"]) / base["Vdrop"]
    print(f"\n  VERIFIED IMPROVEMENT after reinforcement (same delivered current):")
    print(f"    peak temperature : {base['peakT']:.5f} -> {mod['peakT']:.5f}  ({dT:+.2f}%)")
    print(f"    worst IR drop    : {base['Vdrop']:.5f} -> {mod['Vdrop']:.5f}  ({dV:+.2f}%)")
    improved = mod["peakT"] < base["peakT"] and mod["Vdrop"] < base["Vdrop"]
    print(f"    result: {'IMPROVED (lower hotspot AND lower IR drop)' if improved else 'NO IMPROVEMENT'}")
    return improved


if __name__ == "__main__":
    import sys
    sys.exit(0 if main() else 1)
