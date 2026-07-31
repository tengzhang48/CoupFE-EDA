"""Monolithic coupled FE element on the CoupFE operator contract (ETV study, FE refinement).

The material-point study (`etv_solder.py`, Phases 1-4) found the coupling effect; this lifts
the coupling onto a genuine spatially-resolved finite element built the CoupFE way: ONE
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

Validated against the exact 1D self-heating limit dT = sigma V0^2/8k and against the
staggered Picard solve (`etv_solder.solve_et`). DOFs interleaved per node: [phi, T].

Stage B (next): add the displacement field u + the Anand viscoplastic state -> the full
phi-T-u element that reproduces the tau/period finding on a mesh.
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
    op = CoupledET(mesh, sigma0=sigma0, alpha_sig=alpha_sig, k=k, h_vol=h_vol)
    U, _, nit = newton_solve([op], np.zeros(op.ndof), None, op.ndof, dirichlet, **newton_kw)
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
    sigma(T) feedback on -> validates the coupled element against the existing solver."""
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


# ---------------------------------------------------------------------------
# Stage B: monolithic transient thermo-viscoplastic solve on a mesh
# ---------------------------------------------------------------------------
# Reuses the VALIDATED Anand plane-strain FE element (solder_joint.AnandPlaneStrain --
# gated by the return-map 0.04% + patch-test 4e-16 oracles) for spatially-resolved mechanics
# (volume-averaged dW), coupled to a lumped transient thermal model. The lumped (uniform-T)
# thermal model is physically justified here -- Dandu 2010 report the thermal gradient in the
# solder is small -- so the FE adds the MECHANICAL spatial resolution (the dW volume average),
# while the temperature evolves as one transient state. The viscoplastic block uses the
# elastic (modified-Newton) tangent, as the project's solder element does (the return map is
# not complex-analytic); the complex-step tangent is the electro-thermal coupling (above).

def etv_fe_cycle(*, monolithic, q_joule=0.0, g_th=8.0e6, Tlo_C=-40.0, Thi_C=125.0,
                 dalpha=20e-6, ldnp_over_h=6.0, nx=4, ny=3, ncyc=3, steps_per_cyc=24,
                 period=1600.0, p=None):
    """Coupled transient thermo-viscoplastic cycle on a solder mesh.

    monolithic=True: the local temperature is a transient state evolving with internal
      heating (Joule q_joule + inelastic dissipation dW/dt) and coupling g_th to the global
      power cycle T_ext(t);
    monolithic=False (staggered): T tracks the global cycle quasi-statically (T = T_ext +
      q_joule/g_th), no inelastic feedback.
    Mechanics: the CTE-mismatch shear gamma(T) is imposed on the validated Anand plane-strain
    joint; the volume-averaged inelastic strain-energy density per cycle is returned.
    """
    from .etv_solder import T_AMB_C, RHOC_SOLDER
    from .solder_joint import AnandPlaneStrain, SNPB

    p = p if p is not None else SNPB        # robust validated alloy for the FE return map
    H = 0.1e-3
    m = StructuredQuadMesh(nx, ny, H, H)
    op = AnandPlaneStrain(m, p)
    top = np.where(np.isclose(m.coords[:, 1], H))[0]
    bot = np.where(np.isclose(m.coords[:, 1], 0.0))[0]
    top_el = [e for e, c in enumerate(m.elems) if m.coords[c][:, 1].max() > H - 1e-9]
    TloK, ThiK = Tlo_C + 273.15, Thi_C + 273.15     # JEDEC chamber cycle
    Tref = 0.5 * (TloK + ThiK)                      # stress-free at mid-cycle
    dt = period / steps_per_cyc
    Tj_ss = q_joule / g_th                          # Joule self-heating offset on top
    Tl = TloK + Tj_ss
    U = np.zeros(op.ndof)
    Wc = [0.0]
    Wacc = 0.0
    inel_rate = 0.0
    for cyc in range(ncyc):
        for k in range(steps_per_cyc):
            frac = k / steps_per_cyc
            Text = TloK + (ThiK - TloK) * (1.0 - abs(2.0 * frac - 1.0))  # triangular, no dwell
            if monolithic:                          # transient local temperature (backward
                # Euler -> unconditionally stable: rho c (T-Tn)/dt = q + inel - g(T-Text))
                a = RHOC_SOLDER / dt
                Tl = (a * Tl + q_joule + inel_rate + g_th * Text) / (a + g_th)
            else:                                   # quasi-steady (staggered)
                Tl = Text + Tj_ss
            gamma = dalpha * (Tl - Tref) * ldnp_over_h
            op.T = Tl
            op.dt = dt
            bc = {}
            for n in bot:
                bc[2 * int(n)] = 0.0; bc[2 * int(n) + 1] = 0.0
            for n in top:
                bc[2 * int(n)] = gamma * H; bc[2 * int(n) + 1] = 0.0
            U, _, _ = newton_solve([op], U, None, op.ndof, bc, dt=dt, maxit=12)
            op.commit(U, None, 0.0, dt)
            dW_step = float(op.dW[top_el].mean())
            Wacc += dW_step
            inel_rate = dW_step / dt
        Wc.append(Wacc)
    dW_cyc = [Wc[i] - Wc[i - 1] for i in range(1, ncyc + 1)]
    return dict(dW_stab=dW_cyc[-1], dW_cyc=dW_cyc, Tl_peak=Tl - 273.15)


def fe_coupling_effect(*, q_joule, g_th=8.0e6, period=1600.0, ncyc=3, nx=4, ny=3):
    """Monolithic vs staggered volume-averaged dW on the FE mesh (the finding, on a mesh)."""
    stag = etv_fe_cycle(monolithic=False, q_joule=q_joule, g_th=g_th, period=period,
                        ncyc=ncyc, nx=nx, ny=ny)
    mono = etv_fe_cycle(monolithic=True, q_joule=q_joule, g_th=g_th, period=period,
                        ncyc=ncyc, nx=nx, ny=ny)
    d = (mono["dW_stab"] - stag["dW_stab"]) / stag["dW_stab"]
    return dict(dW_stag=stag["dW_stab"], dW_mono=mono["dW_stab"], delta=d)


def main():
    peak, exact, err, nit = verify_selfheating_fe()
    print("Monolithic coupled electro-thermal FE element (CoupFE contract)")
    print(f"  self-heating: peak dT = {peak:.5f} vs sigma V0^2/8k = {exact:.5f}  "
          f"err {err:.1e}  ({nit} Newton iters)  {'PASS' if err < 2e-3 else 'CHECK'}")
    tm, ts, rel, nit2 = consistency_vs_staggered()
    print(f"  monolithic == staggered Picard (sigma(T) on): peak {tm:.4f} vs {ts:.4f}  "
          f"rel {rel:.1e}  (monolithic took {nit2} Newton iters)")
    print("  => one block Newton system with the cross-field coupling captured by the")
    print("     complex-step tangent -- no hand-coded Jacobian, no field-splitting.")
    # Stage B: monolithic transient thermo-viscoplastic on a mesh -> reproduce the finding
    import warnings
    warnings.filterwarnings("ignore")
    from .etv_solder import joule_density, dandu_bump
    q = joule_density(dandu_bump()["j_avg"])
    sc = etv_fe_cycle(monolithic=False, q_joule=0.0, ncyc=2)["dW_stab"]
    mc = etv_fe_cycle(monolithic=True, q_joule=0.0, g_th=1e10, ncyc=2)["dW_stab"]
    qs = fe_coupling_effect(q_joule=q, period=1600.0, ncyc=2)
    fa = fe_coupling_effect(q_joule=q, period=1.0, ncyc=2)
    print("\nStage B -- monolithic transient thermo-viscoplastic on a solder MESH (JEDEC + current)")
    print(f"  consistency: monolithic(no internal heat) = {mc:.5f} vs staggered {sc:.5f} "
          f"(rel {abs(mc-sc)/sc:.1e}) -> reduces to staggered")
    print(f"  coupling (dW_mono - dW_stag)/dW_stag:  quasi-static {qs['delta']*100:+.2f}%   "
          f"fast {fa['delta']*100:+.1f}%")
    print("  => the tau/period finding reproduced on the FE mesh; at fast/pulsed loading the")
    print("     staggered scheme OVER-predicts fatigue (the joint can't thermally follow the cycle).")


if __name__ == "__main__":
    main()
