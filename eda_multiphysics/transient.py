"""Transient heat conduction — adds the time dimension (all prior examples were steady).

1D slab, ends held at 0, initialized to the first thermal eigenmode sin(pi x/L): it
decays purely exponentially with the EXACT rate lambda = (pi/L)^2 * (k/rho c) (single
mode, no series truncation). The checked comparison evaluates the backward-
Euler FE result (consistent mass M + conduction K) against that eigenvalue.

Run:  python -m eda_multiphysics.transient
"""

from __future__ import annotations

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla


def mode_decay(*, L=1e-3, k=148.0, rhoc=1.6e6, ne=60, nt=30, dt=5e-5):
    alpha = k / rhoc
    lam_exact = (np.pi / L) ** 2 * alpha
    x = np.linspace(0, L, ne + 1)
    le = np.diff(x)
    nn = ne + 1
    M = sp.lil_matrix((nn, nn))
    K = sp.lil_matrix((nn, nn))
    for e in range(ne):
        l = le[e]
        Me = rhoc * l / 6.0 * np.array([[2.0, 1.0], [1.0, 2.0]])    # consistent mass
        Ke = k / l * np.array([[1.0, -1.0], [-1.0, 1.0]])
        for i in range(2):
            for j in range(2):
                M[e + i, e + j] += Me[i, j]
                K[e + i, e + j] += Ke[i, j]
    A = (M / dt + K).tolil()
    fixed = [0, nn - 1]                                # Dirichlet T=0 both ends
    for f in fixed:
        A.rows[f] = [f]; A.data[f] = [1.0]
    A = A.tocsr()
    Mdt = (M / dt).tocsr()
    T = np.sin(np.pi * x / L)                          # first eigenmode
    mid = ne // 2
    ts, amps = [0.0], [T[mid]]
    for n in range(nt):
        b = Mdt @ T
        for f in fixed:
            b[f] = 0.0
        T = spla.spsolve(A, b)
        ts.append((n + 1) * dt)
        amps.append(T[mid])
    lam_fe = -np.polyfit(ts, np.log(np.abs(amps)), 1)[0]
    return lam_fe, lam_exact


def gate_transient():
    lf, le = mode_decay()
    err = abs(lf - le) / le
    return dict(name="transient conduction decay vs (pi/L)^2 alpha", ok=err < 0.03,
                detail=f"lambda={lf:.1f} vs {le:.1f} 1/s ({err:.1%})")


def gate_transient_broken_control():
    # broken control: with zero conductivity there is no conduction -> no decay
    lf, _ = mode_decay(k=0.0)
    return dict(name="BROKEN-CONTROL: k=0 -> no decay", ok=abs(lf) < 1e-6,
                detail=f"lambda={lf:.1e} (must be ~0)")


def main():
    for g in (gate_transient, gate_transient_broken_control):
        r = g()
        print(f"  {r['name']:<46}{'PASS' if r['ok'] else 'FAIL':>6}  {r['detail']}")


if __name__ == "__main__":
    main()
