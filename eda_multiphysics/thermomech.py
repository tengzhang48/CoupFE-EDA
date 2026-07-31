"""Linear thermoelastic FE benchmarks: bimetallic strip + thermal-gradient cylinder.

Adds the BENDING validation mode (the existing mechanics gates are conduction /
uniaxial / shear) via two recognized closed-form oracles:

  * Bimetallic strip — Timoshenko (1925), "Analysis of Bi-Metal Thermostats",
    J. Opt. Soc. Am. 11:233. Exact curvature of two bonded CTE-mismatched layers
    heated by dT:  1/rho = 6 (a2-a1) dT (1+m)^2 /
                          [ h (3(1+m)^2 + (1+m n)(m^2 + 1/(m n))) ],  m=h1/h2, n=E1/E2.
  * (thermal-gradient cylinder oracle lives in `tsv_stress`-style axisym; see
    `gate_thermal_gradient_cylinder` for the Timoshenko-Goodier hollow-cylinder check.)

Run:  python -m eda_multiphysics.thermomech
"""

from __future__ import annotations

import numpy as np
import scipy.sparse as sp

from coupfe import newton_solve
from coupfe.operators.base import Residual, Tangent

from .fe import StructuredQuadMesh
from .solder_joint import _B_detJ, _GP2


def _Dps(E, nu):
    """Plane-stress isotropic elastic matrix for [exx, eyy, gxy] -> [sxx, syy, sxy]."""
    c = E / (1.0 - nu * nu)
    return np.array([[c, c * nu, 0], [c * nu, c, 0], [0, 0, c * (1 - nu) / 2]])


class ThermoelasticPS:
    """Plane-stress linear thermoelastic Quad4 (2 DOF/node) with per-element E, nu,
    alpha, dT. Assembles K and the thermal load once (the problem is linear)."""

    def __init__(self, mesh, E, nu, alpha, dT):
        self.m = mesh
        ne = len(mesh.elems)
        self.ndof = 2 * mesh.nnode
        rows, cols, vals = [], [], []
        F = np.zeros(self.ndof)
        for e, conn in enumerate(mesh.elems):
            ed = np.array([[2 * n, 2 * n + 1] for n in conn]).ravel()
            D = _Dps(E[e], nu[e])
            eps_th = alpha[e] * dT[e] * np.array([1.0, 1.0, 0.0])
            Ke = np.zeros((8, 8))
            Fe = np.zeros(8)
            xy = mesh.coords[conn]
            for xi, eta in _GP2:
                B, detJ = _B_detJ(xy, xi, eta)
                Ke += B.T @ D @ B * detJ
                Fe += B.T @ (D @ eps_th) * detJ
            for i in range(8):
                F[ed[i]] += Fe[i]
                for j in range(8):
                    rows.append(ed[i]); cols.append(ed[j]); vals.append(Ke[i, j])
        self.K = sp.csr_matrix((vals, (rows, cols)), shape=(self.ndof, self.ndof))
        self._coo = (np.array(rows), np.array(cols), np.array(vals))
        self.F = F

    def residual(self, U, state, t, dt):
        return Residual(gdofs=np.arange(self.ndof), values=self.K @ U - self.F)

    def tangent(self, U, state, t, dt):
        return Tangent(rows=self._coo[0], cols=self._coo[1], values=self._coo[2])

    def commit(self, U, state, t, dt):
        return state


def timoshenko_curvature(da, dT, h, m=1.0, n=1.0):
    """Exact bimetal curvature [1/m]. da=a2-a1, h=total thickness, m=h1/h2, n=E1/E2."""
    return 6 * da * dT * (1 + m) ** 2 / (h * (3 * (1 + m) ** 2 + (1 + m * n) * (m ** 2 + 1.0 / (m * n))))


def bimetal(*, L=20e-3, h=2e-3, nx=80, ny=8, E=100e9, nu=0.3, a1=12e-6, a2=22e-6, dT=100.0):
    """Free bilayer strip heated by dT; recover curvature from the neutral axis."""
    m = StructuredQuadMesh(nx, ny, L, h)
    ne = len(m.elems)
    yc = m.elem_centroids()[:, 1]
    Earr = np.full(ne, E)
    nuarr = np.full(ne, nu)
    aarr = np.where(yc < h / 2, a2, a1)            # bottom layer a2, top layer a1
    op = ThermoelasticPS(m, Earr, nuarr, aarr, np.full(ne, dT))
    # remove rigid body: pin one node (ux,uy) + one more uy
    nl = int(np.where((np.isclose(m.coords[:, 0], 0)) & (np.isclose(m.coords[:, 1], h / 2)))[0][0])
    nr = int(np.where((np.isclose(m.coords[:, 0], L)) & (np.isclose(m.coords[:, 1], h / 2)))[0][0])
    bc = {2 * nl: 0.0, 2 * nl + 1: 0.0, 2 * nr + 1: 0.0}
    U, _, _ = newton_solve([op], np.zeros(op.ndof), None, op.ndof, bc)
    # fit curvature from mid-thickness nodes: uy(x) ~ c0 + c1 x + (k/2) x^2
    mid = np.where(np.isclose(m.coords[:, 1], h / 2))[0]
    x = m.coords[mid, 0]
    uy = U[2 * mid + 1]
    k_fe = 2.0 * np.polyfit(x, uy, 2)[0]
    k_an = timoshenko_curvature(a2 - a1, dT, h)
    return abs(k_fe), abs(k_an)


def gate_bimetal():
    k_fe, k_an = bimetal()
    err = abs(k_fe - k_an) / k_an
    return dict(name="bimetal strip curvature vs Timoshenko 1925", ok=err < 0.03,
                detail=f"FE kappa={k_fe:.4f} vs {k_an:.4f} 1/m ({err:.1%})")


def gate_bimetal_broken_control():
    # equal CTE -> no bending; the oracle must reject a nonzero curvature
    k_fe, _ = bimetal(a1=12e-6, a2=12e-6)
    return dict(name="BROKEN-CONTROL: equal-CTE -> zero curvature", ok=k_fe < 1e-6,
                detail=f"kappa={k_fe:.1e} (must be ~0)")


# ----------------------------------------------------------------------------
# Thermal-gradient hollow cylinder -- Timoshenko & Goodier, Theory of Elasticity
# Art. 152 (the recognized analytic thermal-stress benchmark; basis of NAFEMS LE11).
# ----------------------------------------------------------------------------
from coupfe.operators.base import Residual as _R, Tangent as _T, complex_step_tangent  # noqa: E402
from .tsv_stress import _elem_residual as _axi_res, _lame_mu  # noqa: E402


class _AxisymGrad:
    """Axisymmetric radial thermoelasticity (plane strain) with a per-element dT."""

    def __init__(self, r, mat, dTe):
        self.r, self.mat, self.dTe = np.asarray(r, float), mat, np.asarray(dTe, float)
        self.ne = len(self.r) - 1
        self.ndof = len(self.r)

    def residual(self, U, s, t, dt):
        R = np.zeros(self.ndof, dtype=U.dtype)
        for e in range(self.ne):
            R[e:e + 2] += _axi_res(U[e:e + 2], self.r[e], self.r[e + 1], self.mat, self.dTe[e])
        return _R(gdofs=np.arange(self.ndof), values=R)

    def tangent(self, U, s, t, dt):
        rows, cols, vals = [], [], []
        for e in range(self.ne):
            r1, r2, dT = self.r[e], self.r[e + 1], self.dTe[e]
            Ke = complex_step_tangent(lambda ue: _axi_res(ue, r1, r2, self.mat, dT), U[e:e + 2])
            for i in range(2):
                for j in range(2):
                    rows.append(e + i); cols.append(e + j); vals.append(Ke[i, j])
        return _T(rows=np.array(rows), cols=np.array(cols), values=np.array(vals))

    def commit(self, U, s, t, dt):
        return s


def tg_cylinder_hoop(r_eval, a, b, Tfunc, E, nu, alpha):
    """T&G Art.152 plane-strain hoop stress at r_eval for a hollow cylinder, any T(r)."""
    from scipy.integrate import quad
    I_full = quad(lambda r: Tfunc(r) * r, a, b)[0]
    I_r = quad(lambda r: Tfunc(r) * r, a, r_eval)[0]
    c = alpha * E / (1.0 - nu)
    return c * ((1 / r_eval ** 2) * ((r_eval ** 2 + a ** 2) / (b ** 2 - a ** 2)) * I_full
                + (1 / r_eval ** 2) * I_r - Tfunc(r_eval))


def thermal_gradient_cylinder(*, a=10e-3, b=20e-3, Ta=100.0, E=200e9, nu=0.3,
                              alpha=12e-6, n=400):
    """Steady log temperature T(r)=Ta ln(b/r)/ln(b/a); compare FE hoop stress to T&G."""
    Tfunc = lambda r: Ta * np.log(b / r) / np.log(b / a)
    r = np.linspace(a, b, n + 1)
    rc = 0.5 * (r[:-1] + r[1:])
    mat = dict(E=E, nu=nu, a=alpha)
    op = _AxisymGrad(r, mat, Tfunc(rc))
    U, _, _ = newton_solve([op], np.zeros(op.ndof), None, op.ndof, {})
    lam, mu = _lame_mu(mat)
    # hoop stress at element centres
    s_tt = np.empty(op.ne)
    for e in range(op.ne):
        L = r[e + 1] - r[e]
        N = np.array([0.5, 0.5]); rr = N @ r[e:e + 2]
        e_rr = (np.array([-1.0, 1.0]) / L) @ U[e:e + 2]
        e_tt = (N @ U[e:e + 2]) / rr
        s_tt[e] = lam * (e_rr + e_tt) + 2 * mu * e_tt - (3 * lam + 2 * mu) * alpha * Tfunc(rr)
    rq = 0.5 * (a + b)
    fe = float(np.interp(rq, rc, s_tt))
    an = tg_cylinder_hoop(rq, a, b, Tfunc, E, nu, alpha)
    return fe, an


def gate_thermal_gradient_cylinder():
    fe, an = thermal_gradient_cylinder()
    err = abs(fe - an) / abs(an)
    return dict(name="cylinder thermal-gradient hoop vs Timoshenko-Goodier",
                ok=err < 1e-2, detail=f"FE={fe/1e6:.2f} vs {an/1e6:.2f} MPa ({err:.1%})")


# ----------------------------------------------------------------------------
# 2D axisymmetric (r-z) thermoelastic element (the element NAFEMS LE11 needs),
# validated against the exact Lame pressurized thick-cylinder benchmark.
# ----------------------------------------------------------------------------
from .fe import _shape as _q4_shape  # noqa: E402


def _B_axisym(coords, xi, eta):
    N, dNref = _q4_shape(xi, eta)                  # N(4,), dNref(2,4)
    J = dNref @ coords
    detJ = J[0, 0] * J[1, 1] - J[0, 1] * J[1, 0]
    invJ = np.array([[J[1, 1], -J[0, 1]], [-J[1, 0], J[0, 0]]]) / detJ
    dN = invJ @ dNref                              # (2,4): dN/dr, dN/dz
    r = float(N @ coords[:, 0])
    B = np.zeros((4, 8))
    for i in range(4):
        B[0, 2 * i] = dN[0, i]                      # e_rr
        B[1, 2 * i + 1] = dN[1, i]                  # e_zz
        B[2, 2 * i] = N[i] / r                      # e_theta = ur/r
        B[3, 2 * i] = dN[1, i]; B[3, 2 * i + 1] = dN[0, i]   # g_rz
    return B, detJ, r


def _D_axisym(E, nu):
    c = E / ((1 + nu) * (1 - 2 * nu))
    return c * np.array([[1 - nu, nu, nu, 0], [nu, 1 - nu, nu, 0],
                         [nu, nu, 1 - nu, 0], [0, 0, 0, (1 - 2 * nu) / 2]])


class Axisym2D:
    """Axisymmetric (r-z) Quad4 thermoelastic operator (2 DOF/node), external load F."""

    def __init__(self, mesh, E, nu, alpha, dT, F_ext=None):
        self.m = mesh
        self.ndof = 2 * mesh.nnode
        D = _D_axisym(E, nu)
        eps_th = alpha * dT * np.array([1.0, 1.0, 1.0, 0.0])
        rows, cols, vals = [], [], []
        F = np.zeros(self.ndof) if F_ext is None else np.asarray(F_ext, float).copy()
        for conn in mesh.elems:
            ed = np.array([[2 * n, 2 * n + 1] for n in conn]).ravel()
            xy = mesh.coords[conn]
            Ke = np.zeros((8, 8)); Fe = np.zeros(8)
            for xi, eta in _GP2:
                B, detJ, r = _B_axisym(xy, xi, eta)
                w = detJ * r                        # axisymmetric volume (2*pi dropped)
                Ke += B.T @ D @ B * w
                Fe += B.T @ (D @ eps_th) * w
            for i in range(8):
                F[ed[i]] += Fe[i]
                for j in range(8):
                    rows.append(ed[i]); cols.append(ed[j]); vals.append(Ke[i, j])
        self.K = sp.csr_matrix((vals, (rows, cols)), shape=(self.ndof, self.ndof))
        self._coo = (np.array(rows), np.array(cols), np.array(vals))
        self.F = F
        self.D = D
        self.alpha, self.dT = alpha, dT

    def residual(self, U, s, t, dt):
        return Residual(gdofs=np.arange(self.ndof), values=self.K @ U - self.F)

    def tangent(self, U, s, t, dt):
        return Tangent(rows=self._coo[0], cols=self._coo[1], values=self._coo[2])

    def commit(self, U, s, t, dt):
        return s


def lame_cylinder(*, a=10e-3, b=20e-3, H=2e-3, p=10e6, E=200e9, nu=0.3, nr=40, nz=4):
    """Pressurized thick cylinder (internal pressure p), plane strain -> hoop stress
    vs the exact Lame solution sigma_theta = p a^2/(b^2-a^2) (1 + b^2/r^2)."""
    m = StructuredQuadMesh(nr, nz, b - a, H)
    m.coords[:, 0] += a                             # shift radial coord to [a,b]
    # internal-pressure nodal load on the inner face r=a (radial, +r)
    F = np.zeros(2 * m.nnode)
    inner = np.where(np.isclose(m.coords[:, 0], a))[0]
    zc = m.coords[inner, 1]
    order = np.argsort(zc)
    inner, zc = inner[order], zc[order]
    for i in range(len(inner) - 1):                 # consistent edge load p*a*dz
        dz = zc[i + 1] - zc[i]
        F[2 * inner[i]] += 0.5 * p * a * dz
        F[2 * inner[i + 1]] += 0.5 * p * a * dz
    op = Axisym2D(m, E, nu, 0.0, 0.0, F_ext=F)
    bc = {}                                          # plane strain: uz=0 on both z-faces
    for n in np.where(np.isclose(m.coords[:, 1], 0) | np.isclose(m.coords[:, 1], H))[0]:
        bc[int(2 * n + 1)] = 0.0
    U, _, _ = newton_solve([op], np.zeros(op.ndof), None, op.ndof, bc)
    # recover hoop stress at element centres
    s_tt, rc = [], []
    for conn in m.elems:
        ed = np.array([[2 * n, 2 * n + 1] for n in conn]).ravel()
        B, _, r = _B_axisym(m.coords[conn], 0.0, 0.0)
        sig = op.D @ (B @ U[ed])
        s_tt.append(sig[2]); rc.append(r)
    rc, s_tt = np.array(rc), np.array(s_tt)
    rq = 0.5 * (a + b)
    fe = float(np.interp(rq, np.sort(rc), s_tt[np.argsort(rc)]))
    an = p * a ** 2 / (b ** 2 - a ** 2) * (1 + b ** 2 / rq ** 2)
    return fe, an


def gate_lame_cylinder():
    fe, an = lame_cylinder()
    err = abs(fe - an) / abs(an)
    return dict(name="axisym pressurized cylinder hoop vs Lame", ok=err < 1e-2,
                detail=f"FE={fe/1e6:.3f} vs {an/1e6:.3f} MPa ({err:.1%})")


def main():
    for g in (gate_bimetal, gate_bimetal_broken_control, gate_thermal_gradient_cylinder,
              gate_lame_cylinder):
        r = g()
        print(f"  {r['name']:<50}{'PASS' if r['ok'] else 'FAIL':>6}  {r['detail']}")


if __name__ == "__main__":
    main()
