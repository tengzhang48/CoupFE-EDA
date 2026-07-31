"""Steady scalar-diffusion Quad4 on the CoupFE operator contract.

One operator serves BOTH physics of the electrothermal PDN problem, because
steady electrical conduction and steady heat conduction are the *same* Laplacian
with a different coefficient:

    electrical:  -div( sigma(T) grad V ) = 0          (DC conduction / IR-drop)
    thermal:     -div( k      grad T ) = Q            (Joule source Q)

The element residual is the only source of truth; the tangent is derived from it
by complex step (`coupfe.operators.base.complex_step_tangent`), exactly the
CoupFE pattern (cf. `examples/linear_bar/bar.py`).

Weak form (one field phi, per-element coefficient c, per-element source s):

    R_i = integral( c grad(phi).grad(N_i) ) - integral( s N_i )

This is experimental EDA-multiphysics prototype code; see
`open_source_eda_multiphysics_integration_plan.md` (Phases 3-5).
"""

from __future__ import annotations

import numpy as np

from coupfe import newton_solve
from coupfe.operators.base import Residual, Tangent, complex_step_tangent

# --- Quad4 reference element (CCW nodes) + 2x2 Gauss ---
_XI = np.array([-1.0, 1.0, 1.0, -1.0])
_ETA = np.array([-1.0, -1.0, 1.0, 1.0])
_G = 1.0 / np.sqrt(3.0)
_GAUSS = [(xi, eta, 1.0) for xi in (-_G, _G) for eta in (-_G, _G)]


def _shape(xi, eta):
    """Bilinear shape funcs N (4,) and reference gradients dN (2,4)."""
    N = 0.25 * (1.0 + _XI * xi) * (1.0 + _ETA * eta)
    dNdxi = 0.25 * _XI * (1.0 + _ETA * eta)
    dNdeta = 0.25 * _ETA * (1.0 + _XI * xi)
    return N, np.vstack([dNdxi, dNdeta])


def _elem_residual(phi_e, coords_e, c, s, rxn=0.0):
    """One element's residual contribution (the single source of truth).

    `phi_e` (4,) may be complex (complex-step); `coords_e` (4,2) real; `c`, `s`,
    `rxn` scalars (coefficient, source, zeroth-order reaction). The reaction term
    `rxn * phi` models a distributed sink to ambient (vertical thermal conductance
    in the compact chip model: -div(c grad T) + g_v T = s).
    """
    R = np.zeros(4, dtype=phi_e.dtype)
    for xi, eta, w in _GAUSS:
        N, dN = _shape(xi, eta)
        J = dN @ coords_e                       # (2,2)
        detJ = J[0, 0] * J[1, 1] - J[0, 1] * J[1, 0]
        invJ = np.array([[J[1, 1], -J[0, 1]], [-J[1, 0], J[0, 0]]]) / detJ
        B = invJ @ dN                           # (2,4) physical grad(N)
        gradphi = B @ phi_e                      # (2,)
        R = (R + c * (B.T @ gradphi) * detJ * w - s * N * detJ * w
             + rxn * N * (N @ phi_e) * detJ * w)
    return R


def _elem_gradient(phi_e, coords_e, xi=0.0, eta=0.0):
    """grad(phi) at a reference point (default element centre)."""
    _, dN = _shape(xi, eta)
    J = dN @ coords_e
    detJ = J[0, 0] * J[1, 1] - J[0, 1] * J[1, 0]
    invJ = np.array([[J[1, 1], -J[0, 1]], [-J[1, 0], J[0, 0]]]) / detJ
    return (invJ @ dN) @ phi_e


class StructuredQuadMesh:
    """A regular nx-by-ny Quad4 grid on [0,Lx] x [0,Ly]. One DOF per node."""

    def __init__(self, nx, ny, Lx=1.0, Ly=1.0):
        xs = np.linspace(0.0, Lx, nx + 1)
        ys = np.linspace(0.0, Ly, ny + 1)
        X, Y = np.meshgrid(xs, ys)              # 'xy': X[j,i]=xs[i]
        self.coords = np.column_stack([X.ravel(), Y.ravel()])  # id = j*(nx+1)+i
        elems = []
        for j in range(ny):
            for i in range(nx):
                n0 = j * (nx + 1) + i
                elems.append([n0, n0 + 1, n0 + 1 + (nx + 1), n0 + (nx + 1)])
        self.elems = np.array(elems, dtype=int)
        self.nnode = (nx + 1) * (ny + 1)
        self.nx, self.ny, self.Lx, self.Ly = nx, ny, Lx, Ly

    # node selectors
    def left(self):
        return np.where(np.isclose(self.coords[:, 0], 0.0))[0]

    def right(self):
        return np.where(np.isclose(self.coords[:, 0], self.Lx))[0]

    def elem_centroids(self):
        return self.coords[self.elems].mean(axis=1)

    def elem_areas(self):
        a = np.empty(len(self.elems))
        for e, conn in enumerate(self.elems):
            ce = self.coords[conn]
            a[e] = 0.5 * abs(
                (ce[2, 0] - ce[0, 0]) * (ce[3, 1] - ce[1, 1])
                - (ce[3, 0] - ce[1, 0]) * (ce[2, 1] - ce[0, 1])
            )
        return a


class ScalarDiffusion:
    """CoupFE Operator: steady diffusion with per-element coeff `c` and source `s`."""

    def __init__(self, mesh: StructuredQuadMesh, coeff_elem, source_elem=None,
                 node_source=None, reaction_elem=None):
        self.mesh = mesh
        self.c = np.asarray(coeff_elem, dtype=float)
        ne = len(mesh.elems)
        self.s = np.zeros(ne) if source_elem is None else np.asarray(source_elem, float)
        self.rxn = (np.zeros(ne) if reaction_elem is None
                    else np.asarray(reaction_elem, float))
        # external nodal load (e.g. an injected current), subtracted from residual
        self.f = (np.zeros(mesh.nnode) if node_source is None
                  else np.asarray(node_source, float))
        self.ndof = mesh.nnode

    def residual(self, U, state, t, dt):
        R = np.zeros(self.ndof, dtype=U.dtype)
        for e, conn in enumerate(self.mesh.elems):
            R[conn] += _elem_residual(U[conn], self.mesh.coords[conn],
                                      self.c[e], self.s[e], self.rxn[e])
        R -= self.f
        return Residual(gdofs=np.arange(self.ndof), values=R)

    def tangent(self, U, state, t, dt):
        rows, cols, vals = [], [], []
        for e, conn in enumerate(self.mesh.elems):
            ce, se, re, xy = self.c[e], self.s[e], self.rxn[e], self.mesh.coords[conn]
            Ke = complex_step_tangent(lambda ue: _elem_residual(ue, xy, ce, se, re), U[conn])
            for i in range(4):
                for j in range(4):
                    rows.append(conn[i])
                    cols.append(conn[j])
                    vals.append(Ke[i, j])
        return Tangent(rows=np.array(rows), cols=np.array(cols), values=np.array(vals))

    def commit(self, U, state, t, dt):
        return state


def solve_field(mesh, coeff_elem, source_elem, dirichlet, node_source=None,
                reaction_elem=None, **newton_kw):
    """Solve one steady diffusion field through CoupFE's `newton_solve`."""
    op = ScalarDiffusion(mesh, coeff_elem, source_elem, node_source, reaction_elem)
    U0 = np.zeros(mesh.nnode)
    U, _, nit = newton_solve([op], U0, None, mesh.nnode, dirichlet, **newton_kw)
    return U, op, nit


def electrode_current(op: ScalarDiffusion, U, electrode_nodes):
    """Net flux (reaction) through a Dirichlet electrode = total current/heat-flow.

    At the converged solution the internal residual K.phi at constrained nodes is
    the reaction; summed over an electrode it is the total flux leaving it.
    """
    Rint = op.residual(U, None, 1.0, 1.0).values   # source already in op.s
    return float(np.sum(Rint[electrode_nodes]))


def elem_gradients(mesh, U):
    """Centre grad(phi) per element (2-vector each)."""
    return np.array([_elem_gradient(U[conn], mesh.coords[conn]) for conn in mesh.elems])
