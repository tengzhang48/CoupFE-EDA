"""Plane-strain Anand material and elastic finite-element checks.

This module checks the tensor return map against the same closed-form saturation
relation used by :mod:`eda_multiphysics.anand`, then checks the surrounding Quad4
assembly with an elastic affine patch test.

Evidence chain (claim boundary stated per stage):
  1. Anand material point vs closed-form saturation stress      (anand.py)
  2. plane-strain J2 return map vs the same relation in shear   (this file)
  3. FE elastic patch test for an affine displacement field     (this file)

The earlier nonlinear multi-element thermal-cycle driver is intentionally not
part of the public example surface: its modified-Newton solve did not meet the
stated convergence tolerance.  Git history retains it for future research.

Run:  python -m eda_multiphysics.solder_joint
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import brentq

from .anand import SNPB, sat_stress
from .anand_3d import _resistance_update_exact

SNPB = dict(SNPB, nu=0.40)   # solder Poisson ratio (near-incompressible)


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
        rate = p["A"] * np.exp(-p["QR"] / T) * np.sinh(p["xi"] * max(q, 0.0) / s_of(dg)) ** (1.0 / p["m"])
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
    point. `T`, `dt` set by the driver each increment. Tangent = elastic (modified
    Newton; robust for the small thermal increments). Optional `elastic_only` for
    the patch test.
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
        if self._K is None:
            D = _Del(self.p)
            rows, cols, vals = [], [], []
            for e, conn in enumerate(self.m.elems):
                ed = self._edofs(conn)
                xy = self.m.coords[conn]
                Ke = np.zeros((8, 8))
                for xi, eta in _GP2:
                    B, detJ = _B_detJ(xy, xi, eta)
                    Ke += B.T @ D @ B * detJ
                for i in range(8):
                    for j in range(8):
                        rows.append(ed[i]); cols.append(ed[j]); vals.append(Ke[i, j])
            self._K = (np.array(rows), np.array(cols), np.array(vals))
        return Tangent(rows=self._K[0], cols=self._K[1], values=self._K[2])

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


if __name__ == "__main__":
    import sys
    ok = validate_return_map()
    ok &= patch_test()
    sys.exit(0 if ok else 1)
