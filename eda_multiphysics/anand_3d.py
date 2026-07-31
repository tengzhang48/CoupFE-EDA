"""Small-strain 3D Hex8 Anand viscoplastic solder element.

This module places Anand state at Hex8 Gauss points. The implementation mirrors
the return-map and operator structure in ``solder_joint.py``:

* J2 radial-return Anand update with the same closed-form saturation oracle.
* A stateful CoupFE ``Operator`` with residual/tangent/commit.
* Elastic modified-Newton tangent; the return map uses abs/sign/Brent and is not
  complex-analytic.

Checked comparisons and controls:
  1. 3D pure-shear return map saturates to ``anand.sat_stress``.
  2. 3D uniaxial-stress transient matches ``anand.integrate_uniaxial``.
  3. Hex8 elastic patch test reproduces an affine strain field exactly.
  4. A fully prescribed one-Hex8 constitutive cycle returns finite SAC305/Syed
     screening output; zero thermal swing is the broken control.

The earlier multi-element cyclic boundary-value driver is not included because
its modified-Newton increments did not meet the stated convergence tolerance.

Run:  python -m eda_multiphysics.anand_3d
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import brentq

from coupfe import newton_solve
from coupfe.operators.base import Residual, Tangent

from .anand import SAC305, SNPB, sat_stress

SAC305_3D = dict(SAC305, nu=0.40)
SNPB_3D = dict(SNPB, nu=0.40)
# Syed (ECTC 2004) single-power ACSE life: N_f = 1/(W' dW), dW in MPa. W' 0.0015-0.0019 (creep-model
# dependent; 0.0019 the corrected hyperbolic-sine value).
SYED_W_SAC305 = 0.0019

# --- Darveaux (2000) two-part energy life + the Motalab (Auburn 2013) EXPERIMENTAL anchor ---
# Motalab, PhD dissertation, Auburn 2013 (Suhling; ASME InterPACK2013-73230): 19 mm PBGA, 288-ball,
# SAC305, -40/+125 C (JEDEC-G / IPC-9701 TC3). MEASURED characteristic life N63.2 = 4719 cycles
# (Zhang/CAVE3 Weibull); their ANSYS-Anand FE predicted 4722 (0.06%); volume-averaged dW ~ 0.20 MPa
# /cycle (Fig 6.21). Darveaux's OWN stated accuracy is +/-2x absolute (JEP 2002), and this is an
# *in-sample* calibration -- so the honest bar is "within 2x of measured", not sub-percent.
DARVEAUX_SAC305 = dict(K1=37.97, K2=-2.8, K3=3.99e-6, K4=2.05, a_c=0.46e-3)   # dW in MPa, lengths m
MOTALAB_2013 = dict(dW=0.20, N_measured=4719.0, N_fe=4722.0,
                    package="19mm PBGA SAC305", cycle="-40/+125C (IPC-9701 TC3)")


def darveaux_life(dW, c=DARVEAUX_SAC305):
    """Darveaux (2000) two-part energy-based solder life: N_f = N0 + a_c/(da/dN), with initiation
    N0 = K1 dW^K2 and crack growth da/dN = K3 dW^K4 (dW in MPa). Returns (N_f, N0, N_growth)."""
    N0 = c["K1"] * dW ** c["K2"]
    dadN = c["K3"] * dW ** c["K4"]
    return N0 + c["a_c"] / dadN, N0, c["a_c"] / dadN

_HEX_XI = np.array([[-1.0, -1.0, -1.0], [1.0, -1.0, -1.0],
                    [1.0, 1.0, -1.0], [-1.0, 1.0, -1.0],
                    [-1.0, -1.0, 1.0], [1.0, -1.0, 1.0],
                    [1.0, 1.0, 1.0], [-1.0, 1.0, 1.0]])
_G = 1.0 / np.sqrt(3.0)
_GAUSS3 = [(xi, eta, zeta, 1.0)
           for xi in (-_G, _G) for eta in (-_G, _G) for zeta in (-_G, _G)]


class StructuredHexMesh:
    """Regular Hex8 grid on ``[0,Lx] x [0,Ly] x [0,Lz]``."""

    def __init__(self, nx, ny, nz, Lx=1.0, Ly=1.0, Lz=1.0):
        nnx, nny = nx + 1, ny + 1
        nnode = nnx * nny * (nz + 1)
        ids = np.arange(nnode)
        i = ids % nnx
        j = (ids // nnx) % nny
        k = ids // (nnx * nny)
        self.coords = np.column_stack([i * (Lx / nx), j * (Ly / ny), k * (Lz / nz)]).astype(float)
        sx, sy, sz = 1, nnx, nnx * nny
        elems = []
        for k in range(nz):
            for j in range(ny):
                for i in range(nx):
                    n0 = k * sz + j * sy + i
                    elems.append([n0, n0 + sx, n0 + sx + sy, n0 + sy,
                                  n0 + sz, n0 + sx + sz, n0 + sx + sy + sz,
                                  n0 + sy + sz])
        self.elems = np.asarray(elems, dtype=int)
        self.nnode = len(self.coords)
        self.nx, self.ny, self.nz = nx, ny, nz
        self.Lx, self.Ly, self.Lz = Lx, Ly, Lz

    def boundary(self):
        x, y, z = self.coords.T
        on = (np.isclose(x, 0.0) | np.isclose(x, self.Lx)
              | np.isclose(y, 0.0) | np.isclose(y, self.Ly)
              | np.isclose(z, 0.0) | np.isclose(z, self.Lz))
        return np.where(on)[0]

    def top(self):
        return np.where(np.isclose(self.coords[:, 2], self.Lz))[0]

    def bottom(self):
        return np.where(np.isclose(self.coords[:, 2], 0.0))[0]


def _lame(p):
    E, nu = p["E"], p["nu"]
    return E * nu / ((1.0 + nu) * (1.0 - 2.0 * nu)), E / (2.0 * (1.0 + nu))


def elastic_matrix_3d(p):
    """Isotropic small-strain elasticity matrix for engineering shear strains."""
    lam, G = _lame(p)
    D = np.array([[lam + 2 * G, lam, lam, 0, 0, 0],
                  [lam, lam + 2 * G, lam, 0, 0, 0],
                  [lam, lam, lam + 2 * G, 0, 0, 0],
                  [0, 0, 0, G, 0, 0],
                  [0, 0, 0, 0, G, 0],
                  [0, 0, 0, 0, 0, G]], dtype=float)
    return D


def _log_sinh(x):
    if x < 1e-8:
        return np.log(max(x, 1e-300))
    if x < 40.0:
        return np.log(np.sinh(x))
    return x - np.log(2.0)


def _flow_rate_from_q(q, s, T, p):
    if q <= 0.0:
        return 0.0
    x = p["xi"] * q / max(s, 1e-12)
    log_rate = np.log(p["A"]) - p["QR"] / T + (1.0 / p["m"]) * _log_sinh(x)
    if log_rate > 690.0:
        return 1e300
    return float(np.exp(log_rate))


def _resistance_update_exact(s_n, sstar, dg, p):
    """Exact-in-gamma update for Anand resistance with fixed ``sstar``.

    This avoids the explicit hardening overshoot that can drive high-h0 SAC305
    fits to a nonphysical zero resistance during large implicit increments.
    """
    sstar = max(float(sstar), 1e-12)
    y0 = max(float(s_n), 1e-12) / sstar
    gap = abs(1.0 - y0)
    if gap < 1e-14 or dg <= 0.0:
        return max(float(s_n), 1e-12)
    H = p["h0"] / sstar
    a = p["a"]
    if abs(a - 1.0) < 1e-12:
        gap_new = gap * np.exp(-H * dg)
    else:
        val = gap ** (1.0 - a) - (1.0 - a) * H * dg
        gap_new = 0.0 if val <= 0.0 else val ** (1.0 / (1.0 - a))
    y = 1.0 - gap_new if y0 < 1.0 else 1.0 + gap_new
    return max(sstar * y, 1e-12)


def anand_return_map_3d(eps_eng, epp_n, s_n, T, dt, p):
    """3D J2 Anand update.

    ``eps_eng`` is ``[exx, eyy, ezz, gamma_xy, gamma_yz, gamma_xz]``.
    The plastic strain state stores tensor shear components:
    ``[xx, yy, zz, xy, yz, xz]``.  Returns
    ``(sigma_eng, epp_new, s_new, dW)`` with stress order matching
    ``eps_eng`` and ``dW = q dgamma`` in MPa.
    """
    lam, G = _lame(p)
    eps = np.array([eps_eng[0], eps_eng[1], eps_eng[2],
                    0.5 * eps_eng[3], 0.5 * eps_eng[4], 0.5 * eps_eng[5]], dtype=float)
    ee = eps - epp_n
    tr = ee[0] + ee[1] + ee[2]
    sig = np.array([lam * tr + 2 * G * ee[0],
                    lam * tr + 2 * G * ee[1],
                    lam * tr + 2 * G * ee[2],
                    2 * G * ee[3], 2 * G * ee[4], 2 * G * ee[5]], dtype=float)
    ph = (sig[0] + sig[1] + sig[2]) / 3.0
    sdev = np.array([sig[0] - ph, sig[1] - ph, sig[2] - ph,
                     sig[3], sig[4], sig[5]], dtype=float)
    j2norm = (sdev[0] ** 2 + sdev[1] ** 2 + sdev[2] ** 2
              + 2.0 * (sdev[3] ** 2 + sdev[4] ** 2 + sdev[5] ** 2))
    qtr = np.sqrt(1.5 * j2norm)
    if qtr < 1e-12:
        return sig, epp_n.copy(), float(s_n), 0.0

    def s_of(dg):
        epdot = max(dg / dt, 1e-300)
        z = max(epdot / p["A"], 1e-300) * np.exp(p["QR"] / T)
        sstar = max(p["shat"] * z ** p["n"], 1e-12)
        return _resistance_update_exact(s_n, sstar, dg, p)

    upper = qtr / (3.0 * G)

    def g(dg):
        q = 0.0 if dg >= upper else 3.0 * G * (upper - dg)
        return dg - dt * _flow_rate_from_q(q, s_of(dg), T, p)

    if g(0.0) >= 0.0:
        dg = 0.0
    else:
        dg = brentq(g, 0.0, upper, xtol=1e-16, rtol=1e-13, maxiter=200)
    s_new = s_of(dg)
    fac = 3.0 * G * dg / qtr
    sig_new = sig - fac * sdev
    depp = 1.5 * dg * sdev / qtr
    q = max(qtr - 3.0 * G * dg, 0.0)
    return sig_new, epp_n + depp, s_new, q * dg


def drive_homogeneous_3d(strain_path, T, p, dt):
    """Drive the 3D return map through a prescribed engineering-strain history."""
    epp = np.zeros(6)
    s = p["s0"]
    hist = []
    for eps in strain_path:
        sig, epp, s, _ = anand_return_map_3d(eps, epp, s, T, dt, p)
        hist.append(sig.copy())
    return np.asarray(hist), s


def _shape_hex8(xi, eta, zeta):
    r = np.array([xi, eta, zeta])
    N = 0.125 * np.prod(1.0 + _HEX_XI * r, axis=1)
    dN = np.empty((3, 8))
    dN[0] = 0.125 * _HEX_XI[:, 0] * (1.0 + _HEX_XI[:, 1] * eta) * (1.0 + _HEX_XI[:, 2] * zeta)
    dN[1] = 0.125 * (1.0 + _HEX_XI[:, 0] * xi) * _HEX_XI[:, 1] * (1.0 + _HEX_XI[:, 2] * zeta)
    dN[2] = 0.125 * (1.0 + _HEX_XI[:, 0] * xi) * (1.0 + _HEX_XI[:, 1] * eta) * _HEX_XI[:, 2]
    return N, dN


def _B_detJ_hex8(coords, xi, eta, zeta):
    _, dNdr = _shape_hex8(xi, eta, zeta)
    J = dNdr @ coords
    detJ = np.linalg.det(J)
    dNdx = np.linalg.solve(J.T, dNdr)
    B = np.zeros((6, 24))
    for a in range(8):
        ix = 3 * a
        dNx, dNy, dNz = dNdx[:, a]
        B[0, ix] = dNx
        B[1, ix + 1] = dNy
        B[2, ix + 2] = dNz
        B[3, ix] = dNy
        B[3, ix + 1] = dNx
        B[4, ix + 1] = dNz
        B[4, ix + 2] = dNy
        B[5, ix] = dNz
        B[5, ix + 2] = dNx
    return B, detJ


class AnandHex8:
    """Stateful small-strain Hex8 Anand operator, 3 displacement DOFs per node."""

    def __init__(self, mesh, p, elastic_only=False):
        self.m = mesh
        self.p = p
        self.elastic = elastic_only
        ne = len(mesh.elems)
        self.epp = np.zeros((ne, 8, 6))
        self.s = np.full((ne, 8), p["s0"])
        self.dW = np.zeros((ne, 8))
        self.T = 300.0
        self.dt = 1.0
        self.ndof = 3 * mesh.nnode
        self._K = None

    def _edofs(self, conn):
        return np.array([[3 * n, 3 * n + 1, 3 * n + 2] for n in conn]).ravel()

    def _stress(self, eps_eng, e, g):
        if self.elastic:
            return elastic_matrix_3d(self.p) @ eps_eng, None, None, 0.0
        return anand_return_map_3d(eps_eng, self.epp[e, g], self.s[e, g],
                                   self.T, self.dt, self.p)

    def residual(self, U, state, t, dt):
        R = np.zeros(self.ndof)
        for e, conn in enumerate(self.m.elems):
            ed = self._edofs(conn)
            ue = U[ed]
            xy = self.m.coords[conn]
            re = np.zeros(24)
            for g, (xi, eta, zeta, w) in enumerate(_GAUSS3):
                B, detJ = _B_detJ_hex8(xy, xi, eta, zeta)
                sig, _, _, _ = self._stress(B @ ue, e, g)
                re += B.T @ sig * detJ * w
            R[ed] += re
        return Residual(gdofs=np.arange(self.ndof), values=R)

    def tangent(self, U, state, t, dt):
        if self._K is None:
            D = elastic_matrix_3d(self.p)
            rows, cols, vals = [], [], []
            for conn in self.m.elems:
                ed = self._edofs(conn)
                xy = self.m.coords[conn]
                Ke = np.zeros((24, 24))
                for xi, eta, zeta, w in _GAUSS3:
                    B, detJ = _B_detJ_hex8(xy, xi, eta, zeta)
                    Ke += B.T @ D @ B * detJ * w
                for i in range(24):
                    for j in range(24):
                        rows.append(ed[i]); cols.append(ed[j]); vals.append(Ke[i, j])
            self._K = (np.asarray(rows), np.asarray(cols), np.asarray(vals))
        return Tangent(rows=self._K[0], cols=self._K[1], values=self._K[2])

    def commit(self, U, state, t, dt):
        for e, conn in enumerate(self.m.elems):
            ue = U[self._edofs(conn)]
            xy = self.m.coords[conn]
            for g, (xi, eta, zeta, _w) in enumerate(_GAUSS3):
                B, _ = _B_detJ_hex8(xy, xi, eta, zeta)
                _, epp_new, s_new, dW = self._stress(B @ ue, e, g)
                if epp_new is not None:
                    self.epp[e, g] = epp_new
                    self.s[e, g] = s_new
                    self.dW[e, g] = dW
        return state


def validate_return_map_3d():
    """3D pure shear must saturate to Anand's closed-form flow stress."""
    p = SNPB_3D
    worst = 0.0
    for TC, gamma_dot in ((25.0, 2e-3), (125.0, 2e-3)):
        T = TC + 273.15
        dgamma = 1.2 / 1200
        dt = dgamma / gamma_dot
        path = [[0.0, 0.0, 0.0, k * dgamma, 0.0, 0.0] for k in range(1200)]
        hist, _ = drive_homogeneous_3d(path, T, p, dt)
        q_fe = np.sqrt(3.0) * abs(hist[-1, 3])
        q_an = float(sat_stress(gamma_dot / np.sqrt(3.0), T, p))
        worst = max(worst, abs(q_fe - q_an) / q_an)
    return worst


def validate_return_map_transient_3d(eps_max=0.04, nsteps=120, p=None, oracle_p=None):
    """Compare the 3D map under uniaxial stress with the checked 1D transient.

    The saturation comparison checks the asymptotic response. This transient
    comparison constrains the implemented hardening path: for each axial strain increment, solve
    the lateral strain that enforces ``sigma_yy = sigma_zz = 0``, then compare
    the full stress-strain curve to ``anand.integrate_uniaxial``.
    """
    from .anand import integrate_uniaxial

    p = SAC305_3D if p is None else p
    oracle_p = p if oracle_p is None else oracle_p
    worst = 0.0
    cases = [(1e-3, 125.0), (1e-2, 25.0), (1e-4, 75.0), (1e-3, 25.0)]
    for eps_dot, TC in cases:
        T = TC + 273.15
        dt = eps_max / eps_dot / nsteps
        epp = np.zeros(6)
        s = p["s0"]
        e3, s3 = [], []
        for k in range(1, nsteps + 1):
            exx = eps_max * k / nsteps

            def resid(elat):
                sig, _, _, _ = anand_return_map_3d(
                    [exx, elat, elat, 0.0, 0.0, 0.0], epp, s, T, dt, p)
                return sig[1]

            elat = brentq(resid, -exx, 0.5 * exx, xtol=1e-14)
            sig, epp, s, _ = anand_return_map_3d(
                [exx, elat, elat, 0.0, 0.0, 0.0], epp, s, T, dt, p)
            e3.append(exx)
            s3.append(sig[0])
        e3 = np.asarray(e3)
        s3 = np.asarray(s3)
        e1, s1, _ = integrate_uniaxial(eps_dot, T, oracle_p, eps_max=eps_max)
        s1i = np.interp(e3, e1, s1)
        mask = e3 > 0.004
        err = np.max(np.abs(s3[mask] - s1i[mask]) / np.maximum(np.abs(s1i[mask]), 1e-9))
        worst = max(worst, float(err))
    return worst


def patch_test_3d():
    """Hex8 elastic patch test: affine displacement reproduced at the interior."""
    m = StructuredHexMesh(2, 2, 2, 1.0, 1.0, 1.0)
    op = AnandHex8(m, SNPB_3D, elastic_only=True)
    A = np.array([[1.0e-3, 2.0e-4, -1.0e-4],
                  [0.0, -5.0e-4, 1.5e-4],
                  [2.5e-4, 0.0, 7.0e-4]])
    bc = {}
    for n in m.boundary():
        u = A @ m.coords[n]
        for c in range(3):
            bc[3 * int(n) + c] = float(u[c])
    U, _, _ = newton_solve([op], np.zeros(op.ndof), None, op.ndof, bc)
    e = 0
    B, _ = _B_detJ_hex8(m.coords[m.elems[e]], 0.0, 0.0, 0.0)
    eps = B @ U[op._edofs(m.elems[e])]
    exact = np.array([A[0, 0], A[1, 1], A[2, 2],
                      A[0, 1] + A[1, 0], A[1, 2] + A[2, 1],
                      A[0, 2] + A[2, 0]])
    return float(np.max(np.abs(eps - exact)))


def prescribed_hex8_cycle(*, Tlo=-40.0, Thi=125.0,
                          dalpha=14.4e-6, ldnp_over_h=6.0, ncyc=3,
                          steps_per_cyc=24, p=SAC305_3D):
    """Fully prescribed one-Hex8 Anand constitutive cycle.

    Every node is on a prescribed face, so this checks the stateful material
    update through the FE operator/commit path. It is not a multi-element
    boundary-value solution or a predictive solder-joint life calculation.
    """
    H = 0.1e-3
    m = StructuredHexMesh(1, 1, 1, H, H, H)
    op = AnandHex8(m, p)
    top, bot = m.top(), m.bottom()
    TloK, ThiK = Tlo + 273.15, Thi + 273.15
    Tref = 0.5 * (TloK + ThiK)
    period = 1600.0
    dt = period / steps_per_cyc
    U = np.zeros(op.ndof)
    Wc = [0.0]
    Wacc = 0.0
    for _cyc in range(ncyc):
        for k in range(steps_per_cyc):
            frac = k / steps_per_cyc
            tri = 1.0 - abs(2.0 * frac - 1.0)
            T = TloK + (ThiK - TloK) * tri
            gamma = dalpha * (T - Tref) * ldnp_over_h
            op.T = T
            op.dt = dt
            bc = {}
            for n in bot:
                bc[3 * int(n)] = 0.0
                bc[3 * int(n) + 1] = 0.0
                bc[3 * int(n) + 2] = 0.0
            for n in top:
                bc[3 * int(n)] = gamma * H
                bc[3 * int(n) + 1] = 0.0
                bc[3 * int(n) + 2] = 0.0
            U, _, _ = newton_solve([op], U, None, op.ndof, bc, dt=dt, maxit=25)
            Wacc += float(op.dW.mean())
        Wc.append(Wacc)
    dW_cyc = [Wc[i] - Wc[i - 1] for i in range(1, ncyc + 1)]
    dW = dW_cyc[-1]
    Nf = 1.0 / (SYED_W_SAC305 * max(dW, 1e-30))
    return dict(dW_cyc=dW_cyc, dW_stab=dW, Nf=Nf,
                gamma_range=dalpha * (ThiK - TloK) * ldnp_over_h)


def main():
    err = validate_return_map_3d()
    print("3D Anand Hex8 viscoplastic solder")
    print(f"  return map vs closed-form saturation: max err {err:.2%} "
          f"{'PASS' if err < 0.02 else 'CHECK'}")
    terr = validate_return_map_transient_3d()
    print(f"  return map vs 1D transient: max err {terr:.2%} "
          f"{'PASS' if terr < 0.005 else 'CHECK'}")
    perr = patch_test_3d()
    print(f"  Hex8 elastic patch test: max|err| {perr:.1e} "
          f"{'PASS' if perr < 1e-10 else 'CHECK'}")
    r = prescribed_hex8_cycle()
    print(f"  prescribed one-Hex8 SAC305 cycle: dW={r['dW_stab']:.4f} MPa, "
          f"Nf={r['Nf']:,.0f} cycles, gamma_range={r['gamma_range']*100:.2f}%")
    z = prescribed_hex8_cycle(Tlo=25.0, Thi=25.0, ncyc=1)
    print(f"  broken control (no thermal swing): dW={z['dW_stab']:.1e}")


if __name__ == "__main__":
    main()
