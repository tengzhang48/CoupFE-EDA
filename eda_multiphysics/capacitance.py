"""Capacitance extraction — the C to complement the R (electrostatics / Laplace).

Parasitic extraction is RC: the PDN-graph gave R; this gives C. Electrostatics is the
same Laplacian (∇·(ε ∇φ)=0) the scalar-diffusion operator already solves, with the
charge Q = ∮ ε ∂φ/∂n recovered as the electrode "reaction" (exactly as current was for
the resistor). C = Q/V. Cross-checks vs the exact parallel-plate ε·A/d and (optionally)
OpenRCX-style geometry.

Run:  python -m eda_multiphysics.capacitance
"""

from __future__ import annotations

import numpy as np

from .fe import StructuredQuadMesh, electrode_current, solve_field

EPS0 = 8.8541878128e-12      # F/m


def parallel_plate(*, eps_r=3.9, d=1e-6, h=10e-6, V=1.0, nx=24, ny=24):
    """Capacitance/unit-length of a parallel-plate cap (gap d, plate height h)."""
    eps = EPS0 * eps_r
    m = StructuredQuadMesh(nx, ny, d, h)            # x = gap, y = plate height
    bc = {**{int(n): V for n in m.left()}, **{int(n): 0.0 for n in m.right()}}
    phi, op, _ = solve_field(m, np.full(len(m.elems), eps), None, bc)
    Q = abs(electrode_current(op, phi, m.left()))   # charge per unit length
    return Q / V, eps * h / d                        # C_fe, C_analytic


def gate_capacitance():
    cfe, can = parallel_plate()
    err = abs(cfe - can) / can
    return dict(name="parallel-plate capacitance vs eps*A/d", ok=err < 1e-6,
                detail=f"C={cfe*1e12:.3f} vs {can*1e12:.3f} pF/m ({err:.0e})")


def gate_capacitance_scaling():
    # physical property: C ∝ 1/gap -> halving the gap doubles C
    c1, _ = parallel_plate(d=1e-6)
    c2, _ = parallel_plate(d=0.5e-6)
    r = c2 / c1
    return dict(name="capacitance scales as 1/gap (C(d/2)=2C(d))", ok=abs(r - 2) < 1e-4,
                detail=f"ratio={r:.4f}")


def main():
    for g in (gate_capacitance, gate_capacitance_scaling):
        r = g()
        print(f"  {r['name']:<46}{'PASS' if r['ok'] else 'FAIL':>6}  {r['detail']}")


if __name__ == "__main__":
    main()
