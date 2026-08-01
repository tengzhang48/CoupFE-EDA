"""Synthetic design-loop example: hotspot -> reinforcement -> checked change.

A possible extension would route the modification back through OpenROAD, which
this example does not do. The current comparison is solver-side. We use the
physical PDN scenario: a load draws a FIXED current through the grid; a locally
under-provisioned power strap (reduced metal conductance) then causes both a
larger IR drop and a Joule hotspot. "Reinforcing" the strap (widen / add vias =
higher local conductance) is evaluated by re-running the coupled electrothermal
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


def compare_design(nx=100, ny=4):
    """Return the fixed-current weak/reinforced-strap comparison."""
    m = StructuredQuadMesh(nx, ny, 1.0, 1.0)
    # fixed current demand; ground on the right; heat-sunk ends
    common = dict(sigma0=1.0, alpha=0.6, k=1.0, Tsink=0.0, relax=0.6, tol=1e-10,
                  I_inject=1.0)

    weak = _strap_scale(m, 0.45, 0.55, 0.35)          # under-provisioned strap
    reinforced = _strap_scale(m, 0.45, 0.55, 1.6)     # widened / via-reinforced

    base = solve_electrothermal(m, sigma_scale=weak, **common)
    mod = solve_electrothermal(m, sigma_scale=reinforced, **common)

    base_current = abs(float(base["current"]))
    modified_current = abs(float(mod["current"]))
    current_difference = abs(modified_current - base_current) / max(
        base_current, 1.0e-30
    )
    peak_change = 100.0 * (mod["peakT"] - base["peakT"]) / base["peakT"]
    drop_change = 100.0 * (mod["Vdrop"] - base["Vdrop"]) / base["Vdrop"]
    improved = (
        mod["peakT"] < base["peakT"]
        and mod["Vdrop"] < base["Vdrop"]
        and current_difference < 1.0e-10
    )
    return {
        "mesh": {"nx": nx, "ny": ny},
        "baseline": {
            "peak_temperature": float(base["peakT"]),
            "hotspot_x": _hotspot_x(m, base["T"]),
            "voltage_drop": float(base["Vdrop"]),
            "delivered_current": base_current,
            "iterations": int(base["iters"]),
        },
        "reinforced": {
            "peak_temperature": float(mod["peakT"]),
            "hotspot_x": _hotspot_x(m, mod["T"]),
            "voltage_drop": float(mod["Vdrop"]),
            "delivered_current": modified_current,
            "iterations": int(mod["iters"]),
        },
        "peak_temperature_change_percent": float(peak_change),
        "voltage_drop_change_percent": float(drop_change),
        "delivered_current_relative_difference": float(current_difference),
        "improved": bool(improved),
        "scope": (
            "Synthetic solver-side perturbation at fixed current; no live EDA "
            "database modification or design-tool rerun."
        ),
    }


def main():
    result = compare_design()

    def line(tag, record):
        print(
            f"  {tag:<26} peakT={record['peak_temperature']:.5f}  "
            f"hotspot x={record['hotspot_x']:.3f}  "
            f"IRdrop={record['voltage_drop']:.5f}  "
            f"I={record['delivered_current']:.3f}  "
            f"iters={record['iterations']}"
        )

    print("\nSynthetic electrothermal design modification (fixed current):")
    line("C  baseline (weak strap)", result["baseline"])
    line("D  reinforced strap", result["reinforced"])
    print(f"\n  checked result after reinforcement (same delivered current):")
    print(
        "    peak temperature : "
        f"{result['baseline']['peak_temperature']:.5f} -> "
        f"{result['reinforced']['peak_temperature']:.5f}  "
        f"({result['peak_temperature_change_percent']:+.2f}%)"
    )
    print(
        "    worst IR drop    : "
        f"{result['baseline']['voltage_drop']:.5f} -> "
        f"{result['reinforced']['voltage_drop']:.5f}  "
        f"({result['voltage_drop_change_percent']:+.2f}%)"
    )
    print(
        "    delivered-current relative difference: "
        f"{result['delivered_current_relative_difference']:.3e}"
    )
    print(
        "    result: "
        + (
            "IMPROVED (lower hotspot AND lower IR drop)"
            if result["improved"]
            else "NO IMPROVEMENT"
        )
    )
    return result["improved"]


if __name__ == "__main__":
    import sys
    sys.exit(0 if main() else 1)
