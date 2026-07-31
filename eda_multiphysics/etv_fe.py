"""Monolithic electrothermal FE element on the CoupFE operator contract.

The material-point study (``etv_solder.py``) supplies a reduced comparison for
this spatially resolved finite element: one
residual carrying multiple fields, the cross-field tangent obtained by COMPLEX STEP (not hand-
coded), solved with `coupfe.newton_solve`. No separate FE library -- the same operator contract
as `fe.py`, extended to a coupled multi-DOF element.

Stage A (this module): the monolithic ELECTRO-THERMAL element -- phi and T in one Newton
system, with the two-way coupling captured automatically by the complex-step tangent:
    phi:  R_phi = integral( sigma(T) grad(phi) . grad(N) )                = 0
    T:    R_T   = integral( k grad(T).grad(N) - sigma(T)|grad phi|^2 N
                            + h_vol T N )                                  = 0
sigma(T) = sigma0/(1 + alpha (T)) makes the phi-block depend on T (thermal->electrical);
the Joule term sigma|grad phi|^2 makes the T-block depend on phi (electrical->thermal). A
staggered scheme splits these into two solves; here they are one block system.

The checked examples compare this implementation with the exact 1D self-heating
limit ``dT = sigma V0^2/8k`` and with the staggered Picard implementation in
``etv_solder.solve_et``. DOFs are interleaved per node: ``[phi, T]``.

An earlier transient thermo-viscoplastic mesh extension is not included because
its modified-Newton increments did not meet the stated convergence tolerance.
The material-point coupling study remains in :mod:`eda_multiphysics.etv_solder`.
"""

from __future__ import annotations

import numpy as np

from coupfe import newton_solve
from coupfe.operators.base import Residual, Tangent, complex_step_tangent

from .fe import StructuredQuadMesh, _GAUSS, _shape

NF = 2          # fields per node: 0 = phi (electric potential), 1 = T (temperature rise)


def _coupled_et_resid(ue, xy, sigma0, alpha_sig, k, h_vol):
    """Element residual of the coupled electro-thermal Q4 (ue = [phi0,T0,phi1,T1,...], 8).

    Complex-safe (the Joule term uses a holomorphic dot, no conjugate) so the cross-field
    tangent comes straight from `complex_step_tangent`.
    """
    R = np.zeros(2 * 4, dtype=ue.dtype)
    phi = ue[0::NF]
    T = ue[1::NF]
    for xi, eta, w in _GAUSS:
        N, dN = _shape(xi, eta)
        J = dN @ xy
        detJ = J[0, 0] * J[1, 1] - J[0, 1] * J[1, 0]
        invJ = np.array([[J[1, 1], -J[0, 1]], [-J[1, 0], J[0, 0]]]) / detJ
        B = invJ @ dN                                    # (2,4) physical grad(N)
        gphi = B @ phi
        gT = B @ T
        Tg = N @ T                                       # local temperature rise
        sig = sigma0 / (1.0 + alpha_sig * Tg)            # sigma(T): thermal->electrical
        Q = sig * (gphi @ gphi)                          # Joule: electrical->thermal (holo.)
        R[0::NF] += sig * (B.T @ gphi) * detJ * w
        R[1::NF] += (k * (B.T @ gT) - Q * N + h_vol * Tg * N) * detJ * w
    return R


class CoupledET:
    """CoupFE Operator: monolithic electro-thermal Q4 (2 DOF/node, phi & T)."""

    def __init__(self, mesh, *, sigma0, alpha_sig=0.0, k=1.0, h_vol=0.0):
        self.mesh = mesh
        self.sigma0, self.alpha_sig, self.k, self.h_vol = sigma0, alpha_sig, k, h_vol
        self.ndof = NF * mesh.nnode

    def _gd(self, conn):
        return np.array([NF * n + f for n in conn for f in range(NF)])

    def residual(self, U, state, t, dt):
        R = np.zeros(self.ndof, dtype=U.dtype)
        for conn in self.mesh.elems:
            gd = self._gd(conn)
            R[gd] += _coupled_et_resid(U[gd], self.mesh.coords[conn],
                                       self.sigma0, self.alpha_sig, self.k, self.h_vol)
        return Residual(gdofs=np.arange(self.ndof), values=R)

    def tangent(self, U, state, t, dt):
        rows, cols, vals = [], [], []
        for conn in self.mesh.elems:
            gd = self._gd(conn)
            xy = self.mesh.coords[conn]
            Ke = complex_step_tangent(
                lambda ue: _coupled_et_resid(ue, xy, self.sigma0, self.alpha_sig,
                                             self.k, self.h_vol), U[gd])
            for i in range(8):
                for j in range(8):
                    rows.append(gd[i]); cols.append(gd[j]); vals.append(Ke[i, j])
        return Tangent(rows=np.array(rows), cols=np.array(cols), values=np.array(vals))

    def commit(self, U, state, t, dt):
        return state


def solve_coupled_et(mesh, *, sigma0, alpha_sig=0.0, k=1.0, h_vol=0.0, dirichlet,
                     **newton_kw):
    """Solve the monolithic electro-thermal block system; returns (phi, Trise, n_iters)."""
    from coupfe import assemble_residual

    op = CoupledET(mesh, sigma0=sigma0, alpha_sig=alpha_sig, k=k, h_vol=h_vol)
    residual_rtol = float(newton_kw.pop("residual_rtol", 1e-8))
    residual_atol = float(newton_kw.pop("residual_atol", 1e-10))
    constrained = np.array(sorted(dirichlet), dtype=int)
    free = np.ones(op.ndof, dtype=bool)
    free[constrained] = False

    initial = np.zeros(op.ndof)
    for dof, value in dirichlet.items():
        initial[int(dof)] = float(value)
    initial_residual, _ = assemble_residual(
        [op], initial, None, 1.0, 1.0, op.ndof
    )
    initial_norm = (
        float(np.max(np.abs(initial_residual[free]))) if np.any(free) else 0.0
    )

    U, _, nit = newton_solve(
        [op], np.zeros(op.ndof), None, op.ndof, dirichlet, **newton_kw
    )
    final_residual, _ = assemble_residual([op], U, None, 1.0, 1.0, op.ndof)
    final_norm = float(np.max(np.abs(final_residual[free]))) if np.any(free) else 0.0
    residual_limit = max(residual_atol, residual_rtol * max(1.0, initial_norm))
    if not np.all(np.isfinite(U)) or not np.isfinite(final_norm) or final_norm > residual_limit:
        raise RuntimeError(
            "monolithic electrothermal solve did not satisfy the final residual check: "
            f"iterations={nit}, residual_norm={final_norm:.6e}, "
            f"residual_limit={residual_limit:.6e}"
        )
    return U[0::NF], U[1::NF], nit


def verify_selfheating_fe(sigma0=3.0, V0=2.0, k=1.5, L=1.0, n=48):
    """Monolithic FE element vs the exact self-heating limit dT = sigma V0^2/8k."""
    m = StructuredQuadMesh(n, 4, L, 0.2 * L)
    d = {}
    for i in m.left():
        d[NF * int(i)] = 0.0; d[NF * int(i) + 1] = 0.0      # phi=0, T=0 (cold face)
    for i in m.right():
        d[NF * int(i)] = V0; d[NF * int(i) + 1] = 0.0       # phi=V0, T=0 (cold face)
    _, T, nit = solve_coupled_et(m, sigma0=sigma0, k=k, dirichlet=d)
    peak = float(T.max())
    exact = sigma0 * V0 ** 2 / (8.0 * k)
    return peak, exact, abs(peak - exact) / exact, nit


def consistency_vs_staggered(sigma0=3.0, V0=2.0, alpha_sig=0.05, k=1.5, L=1.0, n=32):
    """Monolithic (one Newton block) == staggered Picard (two alternating solves), with the
    sigma(T) feedback on -> compares the two implementations at the selected case."""
    from .etv_solder import solve_et
    m = StructuredQuadMesh(n, 4, L, 0.2 * L)
    d = {}
    for i in m.left():
        d[NF * int(i)] = 0.0; d[NF * int(i) + 1] = 0.0
    for i in m.right():
        d[NF * int(i)] = V0; d[NF * int(i) + 1] = 0.0
    _, T_mono, nit = solve_coupled_et(m, sigma0=sigma0, alpha_sig=alpha_sig, k=k, dirichlet=d)
    Vbc = {**{int(i): 0.0 for i in m.left()}, **{int(i): V0 for i in m.right()}}
    Tbc = {**{int(i): 0.0 for i in m.left()}, **{int(i): 0.0 for i in m.right()}}
    r = solve_et(m, Vbc, sigma0=sigma0, alpha_sig=alpha_sig, k=k, T_bc=Tbc)
    T_stag = r["T"]
    rel = float(np.max(np.abs(T_mono - T_stag)) / max(1e-30, np.max(np.abs(T_stag))))
    return T_mono.max(), T_stag.max(), rel, nit


def main():
    peak, exact, err, nit = verify_selfheating_fe()
    print("Monolithic coupled electro-thermal FE element (CoupFE contract)")
    print(f"  self-heating: peak dT = {peak:.5f} vs sigma V0^2/8k = {exact:.5f}  "
          f"err {err:.1e}  ({nit} Newton iters)  {'PASS' if err < 2e-3 else 'CHECK'}")
    tm, ts, rel, nit2 = consistency_vs_staggered()
    print(f"  monolithic == staggered Picard (sigma(T) on): peak {tm:.4f} vs {ts:.4f}  "
          f"rel {rel:.1e}  (monolithic took {nit2} Newton iters)")
    print("  one block Newton system with cross-field terms supplied by the")
    print("  complex-step tangent.")


if __name__ == "__main__":
    main()
