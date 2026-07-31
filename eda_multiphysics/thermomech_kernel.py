"""Coupled thermo-mechanical (displacement + temperature) Hex8 codegen kernel.

The 3D escalation of the project's thermo-elastic work (`tsv_stress`, `thermomech` are 2D/
axisymmetric Python): a compiled **Hex8** element with displacement `u` (3 dof/node) AND
temperature `T` (1 dof/node) = 4 dof/node, the coupling tangent from complex step (no hand-coded
Jacobian). The weak form mirrors CoupFE core's `examples/thermo_mechanics_quad8` (a compressible
neo-Hookean solid with an isotropic thermal pressure -K*alpha*T and Fourier conduction), promoted
to 3D for generated reference geometries.

Closed-form oracles for this material (uniform temperature T = dT, reference T=0):
  * constrained block (u=0, F=I):    sigma = stress_PK1(I, dT) = -K*alpha*dT * I  (hydrostatic)
  * free isotropic expansion (P=0):  F = lambda*I with  G(lambda^2-1) + 3K ln(lambda) = K*alpha*dT,
                                      so u(X) = (lambda-1) X  (linear -> trilinear Hex8 is EXACT)

    python -m eda_multiphysics.thermomech_kernel    # build + verify the Hex8 kernel
"""
from __future__ import annotations

import os

import numpy as np

import coupfe.codegen as au
from coupfe.codegen.core.tensor import det, inv, log


class ThermoElasticMaterial(au.Material):
    """Compressible neo-Hookean mechanics + isotropic thermal pressure + Fourier conduction."""

    props = dict(G=1.0, K=100.0, alpha=1.0e-3, kappa=0.25, cT=1.0)

    def stress_PK1(self, F, T):
        finv_t = inv(F).T
        J = det(F)
        P_mech = self.G * (F - finv_t) + self.K * log(J) * finv_t
        P_thermal = -self.K * self.alpha * T * finv_t
        return P_mech + P_thermal

    def solvent_flux(self, F, T, grad_T):
        Cinv = inv(F.T @ F)
        return -self.kappa * (Cinv @ grad_T)

    def solvent_storage(self, F, F_old, T, T_old, dt):
        return self.cT * (T - T_old) / dt


class ThermoElastic(au.WeakForm):
    """Coupled u (VectorField) + T (ScalarField) thermo-mechanics."""

    material = ThermoElasticMaterial
    ndim = 3

    def define_fields(self):
        self.u = au.VectorField("u", degree=1)
        self.T = au.ScalarField("T", degree=1, test="theta")

    def momentum_equation(self, v, F, T):
        return self.material.stress_PK1(F, T)

    def transport_equation(self, theta, F, T, grad_T, F_old, T_old, dt):
        storage = self.material.solvent_storage(F, F_old, T, T_old, dt)
        flux = self.material.solvent_flux(F, T, grad_T)
        return storage, flux


DEFAULT_PROPS = (1.0, 100.0, 1.0e-3, 0.25, 1.0)        # G, K, alpha, kappa, cT


def _vstate(ndim):
    F = np.array([[1.08, 0.04, 0.0],
                  [0.02, 1.05, 0.0],
                  [0.0, 0.0, 1.03]])
    return dict(F=F, F_old=0.98 * F, T=15.0, T_old=10.0,
                grad_T=np.array([2.0, -1.0, 0.5]), dt=0.1)


def build_thermomech_kernel(workdir, *, element="Hex8", compile=True, verify=True):
    """Generate (and f2py-compile) the coupled thermo-mechanical kernel. props at RUNTIME are
    (G, K, alpha, kappa, cT)."""
    from coupfe.codegen.generators.uel_gen import generate_uel
    from coupfe.runtime.compiled_element import build_element_kernel
    key = element.lower()
    ndim = 3 if key.startswith(("hex", "tet")) else 2
    problem = ThermoElastic(ndim=ndim)
    if verify:
        problem.verify(state=_vstate(ndim), verbose=False)
    os.makedirs(workdir, exist_ok=True)
    forp = os.path.join(workdir, f"thermomech_{element.lower()}.for")
    if key.startswith("tet"):
        from .tet_element import TET4_CONFIG
        generate_uel(problem, forp, element_config=TET4_CONFIG, formulation="standard")
    else:
        generate_uel(problem, forp, element=element, formulation="standard")
    if not compile:
        return forp
    return build_element_kernel(forp, f"thermomech_{element.lower()}_kernel", workdir=workdir)


def free_expansion_lambda(dT, *, G=1.0, K=100.0, alpha=1.0e-3):
    """Solve G(lambda^2-1) + 3K ln(lambda) = K*alpha*dT for the stress-free isotropic stretch."""
    from scipy.optimize import brentq
    f = lambda lam: G * (lam ** 2 - 1.0) + 3.0 * K * np.log(lam) - K * alpha * dT
    return brentq(f, 0.5, 2.0)


if __name__ == "__main__":
    wd = os.path.join(os.path.dirname(__file__), "_tm_hex")
    mod = build_thermomech_kernel(wd, element="Hex8")
    print("thermo-mechanical Hex8 kernel built and checked (codegen complex-step tangent).")
    print(f"  free-expansion stretch at dT=10: lambda = {free_expansion_lambda(10.0):.8f}")
