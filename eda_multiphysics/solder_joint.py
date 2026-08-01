"""Plane-strain SnPbAg Anand checks and a thermal-cycle demonstration.

This module checks the tensor return map against the same closed-form saturation
relation used by :mod:`eda_multiphysics.anand`, then checks the surrounding Quad4
assembly with an elastic affine patch test.

Evidence chain:
  1. Anand material point vs closed-form saturation stress      (anand.py)
  2. plane-strain J2 return map vs the same relation in shear   (this file)
  3. FE elastic patch test for an affine displacement field     (this file)
  4. a fail-closed, multi-element thermal-cycle demonstration   (this file)

The cycle is an idealized demonstration, not package-life validation.  Each
increment uses a numerical material tangent, is checked against Core's Newton
residual rule, and advances material state exactly once only after convergence.

Run:  python -m eda_multiphysics.solder_joint
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import brentq

from .anand import SAC305, SNPB, sat_stress
from .anand_3d import _flow_rate_from_q, _resistance_update_exact

SNPB = dict(SNPB, nu=0.40)   # solder Poisson ratio (near-incompressible)
SAC305_PLANE = dict(SAC305, nu=0.40)


def _lame(p):
    E, nu = p["E"], p["nu"]
    return E * nu / ((1 + nu) * (1 - 2 * nu)), E / (2 * (1 + nu))


def anand_return_map(eps2d, epp_n, s_n, T, dt, p):
    """Plane-strain Anand viscoplastic update at a material point.

    eps2d = [exx, eyy, exy(tensor)] total strain (ezz=0). State: plastic strain
    epp_n = [xx,yy,zz,xy] (deviatoric) and deformation resistance s_n.
    Returns (sigma[xx,yy,zz,xy], epp_new, s_new, dW) where dW = q*dgamma.
    """
    lam, G = _lame(p)
    eps = np.array([eps2d[0], eps2d[1], 0.0, eps2d[2]])
    ee = eps - epp_n                                   # elastic strain (ezz_e=-epp_zz)
    tr = ee[0] + ee[1] + ee[2]
    sig = np.array([lam * tr + 2 * G * ee[0], lam * tr + 2 * G * ee[1],
                    lam * tr + 2 * G * ee[2], 2 * G * ee[3]])
    ph = (sig[0] + sig[1] + sig[2]) / 3.0
    sdev = np.array([sig[0] - ph, sig[1] - ph, sig[2] - ph, sig[3]])
    qtr = np.sqrt(1.5 * (sdev[0] ** 2 + sdev[1] ** 2 + sdev[2] ** 2 + 2 * sdev[3] ** 2))
    if qtr < 1e-12:
        return sig, epp_n, s_n, 0.0

    def s_of(dg):                                      # resistance at this dgamma
        epdot = max(dg / dt, 1e-300)
        sstar = p["shat"] * ((epdot / p["A"]) * np.exp(p["QR"] / T)) ** p["n"]
        return _resistance_update_exact(s_n, sstar, dg, p)

    def g(dg):
        q = qtr - 3 * G * dg
        rate = _flow_rate_from_q(max(q, 0.0), s_of(dg), T, p)
        return dg - dt * rate

    dg = brentq(g, 0.0, qtr / (3 * G) * (1 - 1e-12), xtol=1e-16, rtol=1e-13, maxiter=200)
    s_new = s_of(dg)
    fac = 3 * G * dg / qtr
    sig_new = sig - fac * sdev
    depp = 1.5 * dg * sdev / qtr                       # plastic strain increment (tensor)
    q = qtr - 3 * G * dg
    return sig_new, epp_n + depp, s_new, q * dg


def _drive_homogeneous(strain_path, T, p, dt):
    """Integrate the return map through a prescribed homogeneous strain history."""
    epp = np.zeros(4)
    s = p["s0"]
    sig = np.zeros(4)
    hist = []
    for eps2d in strain_path:
        sig, epp, s, _ = anand_return_map(eps2d, epp, s, T, dt, p)
        hist.append(sig.copy())
    return np.array(hist), s


def validate_return_map():
    """Pure-shear monotonic loading: q must saturate to the closed-form sat_stress
    (the same oracle anand.py uses), validating the multiaxial radial return."""
    p = SNPB
    print("Stage 1 -- plane-strain J2 return map vs closed-form saturation (pure shear):")
    print(f"{'T(C)':>6}{'gamma_dot(1/s)':>16}{'FE tau_sat(MPa)':>18}{'closed-form(MPa)':>18}{'err':>9}")
    worst = 0.0
    for TC in (25.0, 125.0):
        T = TC + 273.15
        for exy_dot in (1e-3, 1e-2):                   # tensor shear-strain rate
            eps_eq_dot = 2.0 / np.sqrt(3.0) * exy_dot   # equivalent strain rate
            deps = 0.6 / 2000
            dt = deps / exy_dot
            path = [[0.0, 0.0, k * deps] for k in range(2000)]
            hist, _ = _drive_homogeneous(path, T, p, dt)
            tau = hist[-1, 3]
            q_fe = np.sqrt(3.0) * abs(tau)
            q_an = float(sat_stress(eps_eq_dot, T, p))
            err = abs(q_fe - q_an) / q_an
            worst = max(worst, err)
            print(f"{TC:>6.0f}{exy_dot:>16.0e}{abs(tau):>18.3f}{q_an/np.sqrt(3):>18.3f}{err:>8.2%}")
    print(f"\n  max rel err (von Mises) vs analytic saturation = {worst:.2%}  "
          f"{'PASS' if worst < 0.02 else 'CHECK'}")
    return worst < 0.02


# ----------------------------------------------------------------------------
# Stage 2/3: plane-strain Quad4 FE with the Anand material
# ----------------------------------------------------------------------------
from coupfe import newton_solve                                    # noqa: E402
from coupfe.operators.base import Residual, Tangent                # noqa: E402

_G2 = 1.0 / np.sqrt(3.0)
_GP2 = [(-_G2, -_G2), (_G2, -_G2), (_G2, _G2), (-_G2, _G2)]
_XI = np.array([-1.0, 1.0, 1.0, -1.0])
_ETA = np.array([-1.0, -1.0, 1.0, 1.0])


def _B_detJ(coords, xi, eta):
    dNdxi = 0.25 * _XI * (1 + _ETA * eta)
    dNdeta = 0.25 * _ETA * (1 + _XI * xi)
    J = np.array([dNdxi, dNdeta]) @ coords
    detJ = J[0, 0] * J[1, 1] - J[0, 1] * J[1, 0]
    invJ = np.array([[J[1, 1], -J[0, 1]], [-J[1, 0], J[0, 0]]]) / detJ
    dN = invJ @ np.array([dNdxi, dNdeta])                          # (2,4) dN/dx,dN/dy
    B = np.zeros((3, 8))
    for i in range(4):
        B[0, 2 * i] = dN[0, i]
        B[1, 2 * i + 1] = dN[1, i]
        B[2, 2 * i] = dN[1, i]
        B[2, 2 * i + 1] = dN[0, i]                                 # gamma_xy = du/dy+dv/dx
    return B, detJ


def _Del(p):
    lam, G = _lame(p)
    return np.array([[lam + 2 * G, lam, 0], [lam, lam + 2 * G, 0], [0, 0, G]])


class AnandPlaneStrain:
    """Plane-strain Quad4 FE operator with the Anand viscoplastic material.

    Stateful: committed plastic strain epp[e,g,4] and resistance s[e,g] per Gauss
    point. ``T`` and ``dt`` are set by the driver each increment.  Nonlinear
    solves use a numerical material tangent of the return map; ``elastic_only``
    retains the exact elastic tangent for the patch test.
    """

    def __init__(self, mesh, p, elastic_only=False):
        self.m = mesh
        self.p = p
        self.elastic = elastic_only
        ne = len(mesh.elems)
        self.epp = np.zeros((ne, 4, 4))
        self.s = np.full((ne, 4), p["s0"])
        self.dW = np.zeros((ne, 4))            # last-committed inelastic energy incr
        self.T = 300.0
        self.dt = 1.0
        self.ndof = 2 * mesh.nnode
        self._K = None

    def _edofs(self, conn):
        return np.array([[2 * n, 2 * n + 1] for n in conn]).ravel()

    def _stress(self, eps_eng, e, g, commit):
        if self.elastic:
            return _Del(self.p) @ eps_eng, None, None, 0.0
        eps2d = [eps_eng[0], eps_eng[1], eps_eng[2] / 2.0]         # tensor exy
        sig, epp_new, s_new, dW = anand_return_map(
            eps2d, self.epp[e, g], self.s[e, g], self.T, self.dt, self.p)
        return np.array([sig[0], sig[1], sig[3]]), epp_new, s_new, dW

    def residual(self, U, state, t, dt):
        R = np.zeros(self.ndof)
        for e, conn in enumerate(self.m.elems):
            ed = self._edofs(conn)
            ue = U[ed]
            xy = self.m.coords[conn]
            re = np.zeros(8)
            for g, (xi, eta) in enumerate(_GP2):
                B, detJ = _B_detJ(xy, xi, eta)
                sig_v, _, _, _ = self._stress(B @ ue, e, g, False)
                re += B.T @ sig_v * detJ
            R[ed] += re
        return Residual(gdofs=np.arange(self.ndof), values=R)

    def tangent(self, U, state, t, dt):
        if self.elastic and self._K is not None:
            return Tangent(rows=self._K[0], cols=self._K[1], values=self._K[2])

        rows, cols, vals = [], [], []
        for e, conn in enumerate(self.m.elems):
            ed = self._edofs(conn)
            ue = U[ed]
            xy = self.m.coords[conn]
            Ke = np.zeros((8, 8))
            for g, (xi, eta) in enumerate(_GP2):
                B, detJ = _B_detJ(xy, xi, eta)
                eps = B @ ue
                if self.elastic:
                    D = _Del(self.p)
                else:
                    D = np.zeros((3, 3))
                    for j in range(3):
                        h = 1.0e-7 * max(1.0, abs(float(eps[j])))
                        ep = eps.copy(); ep[j] += h
                        em = eps.copy(); em[j] -= h
                        sp, _, _, _ = self._stress(ep, e, g, False)
                        sm, _, _, _ = self._stress(em, e, g, False)
                        D[:, j] = (sp - sm) / (2.0 * h)
                Ke += B.T @ D @ B * detJ
            for i in range(8):
                for j in range(8):
                    rows.append(ed[i]); cols.append(ed[j]); vals.append(Ke[i, j])
        data = (np.asarray(rows), np.asarray(cols), np.asarray(vals))
        if self.elastic:
            self._K = data
        return Tangent(rows=data[0], cols=data[1], values=data[2])

    def commit(self, U, state, t, dt):
        for e, conn in enumerate(self.m.elems):
            ue = U[self._edofs(conn)]
            xy = self.m.coords[conn]
            for g, (xi, eta) in enumerate(_GP2):
                B, _ = _B_detJ(xy, xi, eta)
                _, epp_new, s_new, dW = self._stress(B @ ue, e, g, True)
                if epp_new is not None:
                    self.epp[e, g] = epp_new
                    self.s[e, g] = s_new
                    self.dW[e, g] = dW
        return state


def patch_test():
    """Stage 2: elastic patch test -- an affine field is the exact FE solution."""
    from .fe import StructuredQuadMesh
    m = StructuredQuadMesh(3, 3, 1.0, 1.0)
    op = AnandPlaneStrain(m, SNPB, elastic_only=True)
    eps0 = 1e-3
    # prescribe affine u = (eps0*x, 0) on ALL boundary nodes -> uniform strain
    bc = {}
    for n in range(m.nnode):
        x, y = m.coords[n]
        on = np.isclose(x, 0) or np.isclose(x, 1) or np.isclose(y, 0) or np.isclose(y, 1)
        if on:
            bc[2 * n] = eps0 * x
            bc[2 * n + 1] = 0.0
    U, _, _ = newton_solve([op], np.zeros(op.ndof), None, op.ndof, bc)
    # interior strain should equal eps0 exactly; stress = D[:,0]*eps0
    B, _ = _B_detJ(m.coords[m.elems[4]], 0.0, 0.0)
    eps = B @ U[op._edofs(m.elems[4])]
    err = abs(eps[0] - eps0) / eps0
    print(f"\nStage 2 -- elastic patch test: interior eps_xx={eps[0]:.6e} "
          f"(exact {eps0:.0e}), rel err {err:.1e}  {'PASS' if err < 1e-9 else 'FAIL'}")
    return err < 1e-9


def solder_joint_cycle(*, nx=3, ny=2, Tlo=-40.0, Thi=125.0, dalpha=20e-6,
                       ldnp_over_h=6.0, ncyc=1, steps_per_cyc=12,
                       maxit=30):
    """Run an idealized plane-strain SnPbAg thermal-cycle demonstration.

    The bottom pad is fixed, the top pad follows the CTE-mismatch displacement,
    and the lateral faces are traction-free.  This is a runnable mechanics and
    state-transfer example; its geometry, loading, and local energy extraction
    are not a qualified package prediction.

    Every increment must satisfy Core's Newton residual rule or the function
    raises before committing that increment.  The reported cycle ``dW`` is the
    sum over increments of the equal-volume mean of Gauss-point values over
    the top element layer; it is a deliberately local example observable, not
    a whole-mesh average.
    """
    from ._stateful_solve import solve_stateful_increment
    from .fe import StructuredQuadMesh

    if nx < 1 or ny < 1 or ncyc < 1 or maxit < 1:
        raise ValueError("mesh counts, ncyc, and maxit must be positive")
    if steps_per_cyc < 2 or steps_per_cyc % 2:
        raise ValueError("steps_per_cyc must be a positive even integer")
    if Thi < Tlo:
        raise ValueError("Thi must be greater than or equal to Tlo")

    H = 0.1e-3
    m = StructuredQuadMesh(nx, ny, H, H)
    op = AnandPlaneStrain(m, SNPB)
    TloK, ThiK = Tlo + 273.15, Thi + 273.15
    Tref = 0.5 * (TloK + ThiK)
    top = np.where(np.isclose(m.coords[:, 1], H))[0]
    bot = np.where(np.isclose(m.coords[:, 1], 0.0))[0]
    top_elems = [
        e for e, conn in enumerate(m.elems)
        if np.isclose(m.coords[conn][:, 1].max(), H)
    ]
    dt = 1600.0 / steps_per_cyc
    U = np.zeros(op.ndof)
    cycle_energy = []
    convergence = []

    def boundary_conditions(gamma):
        bc = {}
        for node in bot:
            bc[2 * int(node)] = 0.0
            bc[2 * int(node) + 1] = 0.0
        for node in top:
            bc[2 * int(node)] = gamma * H
            bc[2 * int(node) + 1] = 0.0
        return bc

    # Establish the cold-end state once; its work is initialization and is not
    # counted as a thermal cycle. Each reported cycle then runs cold -> hot -> cold.
    op.T = TloK
    op.dt = dt
    cold_gamma = dalpha * (TloK - Tref) * ldnp_over_h
    U, info = solve_stateful_increment(
        op, U, boundary_conditions(cold_gamma), dt=dt, maxit=maxit
    )
    convergence.append(info)
    for _cyc in range(ncyc):
        accumulated = 0.0
        for step in range(1, steps_per_cyc + 1):
            fraction = step / steps_per_cyc
            triangle = 1.0 - abs(2.0 * fraction - 1.0)
            T = TloK + (ThiK - TloK) * triangle
            gamma = dalpha * (T - Tref) * ldnp_over_h
            op.T = T
            op.dt = dt
            U, info = solve_stateful_increment(
                op, U, boundary_conditions(gamma), dt=dt, maxit=maxit
            )
            convergence.append(info)
            accumulated += float(op.dW[top_elems].mean())
        cycle_energy.append(accumulated)

    return {
        "dW_cyc": cycle_energy,
        "dW_last": cycle_energy[-1],
        "dW_aggregation": "increment sum of equal-volume top-layer Gauss-point mean",
        "gamma_range": dalpha * (ThiK - TloK) * ldnp_over_h,
        "n_elem": int(len(m.elems)),
        "max_iterations": max(i["iterations"] for i in convergence),
        "max_relative_residual": max(i["relative_residual"] for i in convergence),
        "max_residual_fraction_of_limit": max(
            i["residual_fraction_of_limit"] for i in convergence
        ),
    }


def cycle_demo():
    """Print the bounded public cycle result."""
    result = solder_joint_cycle()
    print("\nPlane-strain SnPbAg solder thermal-cycle demonstration")
    print(
        f"  {result['n_elem']} Quad4 elements; shear range "
        f"{100.0 * result['gamma_range']:.2f}%"
    )
    print(
        "  inelastic energy increments by cycle: "
        + ", ".join(f"{value:.5f} MPa" for value in result["dW_cyc"])
    )
    print(
        f"  all increments met Core's residual rule before commit; max Newton iterations "
        f"{result['max_iterations']}"
    )
    print("  scope: idealized demonstration, not package-life validation")


if __name__ == "__main__":
    import sys
    ok = validate_return_map()
    ok &= patch_test()
    cycle_demo()
    sys.exit(0 if ok else 1)
