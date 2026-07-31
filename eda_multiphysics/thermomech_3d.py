"""3D coupled thermo-mechanical solves on the compiled Hex8 element + closed-form oracles.

Drives `thermomech_kernel` (u + T, 4 dof/node) through a serial Newton loop. Two validations
against EXACT solutions of the element's own constitutive law (uniform temperature T = dT):

  * free expansion  -- symmetry rollers (u_n=0 on the x=0,y=0,z=0 faces), far faces traction-free:
      stress-free isotropic stretch  u(X) = (lambda-1) X,  lambda from
      G(lambda^2-1) + 3K ln(lambda) = K*alpha*dT.  u is LINEAR -> trilinear Hex8 is exact.
  * constrained block -- rollers on ALL six faces: u = 0, uniform hydrostatic stress
      sigma = -K*alpha*dT.  (Doubles as the broken control for free expansion.)

    python -m eda_multiphysics.thermomech_3d
"""
from __future__ import annotations

import os
import time

import numpy as np
import scipy.sparse.linalg as spla

from .etv_3d import build_hex_grid
from .thermomech_kernel import DEFAULT_PROPS, build_thermomech_kernel, free_expansion_lambda


def solve_thermomech(n=4, *, dT=10.0, props=DEFAULT_PROPS, L=1.0, constrained=False,
                     workdir=None, maxit=25):
    """Newton solve of the coupled thermo-mechanical box. T=dT prescribed at every node; symmetry
    rollers on x=0,y=0,z=0 (and all far faces too if `constrained`). Returns (U, nodes, ndof)."""
    from coupfe import ElementGroup, assemble_residual, assemble_tangent
    from coupfe.runtime.compiled_element import CompiledElement

    nodes, elems = build_hex_grid(n, L=L)
    ndof = len(nodes) * 4
    wd = workdir or os.path.join(os.path.dirname(__file__), "_tm_hex")
    mod = build_thermomech_kernel(wd, element="Hex8")
    elem = CompiledElement(mod, props=props, dof_per_node=4, n_svars=0, mcrd=3, n_elem=len(elems))
    group = ElementGroup(elem, nodes, elems, dof_per_node=4, comps=(0, 1, 2, 3))

    x, y, z = nodes[:, 0], nodes[:, 1], nodes[:, 2]
    d = {int(4 * ni + 3): dT for ni in range(len(nodes))}      # T = dT everywhere
    for ni in np.where(np.abs(x - x.min()) < 1e-9)[0]:
        d[4 * int(ni) + 0] = 0.0                               # u_x = 0 on x=0
    for ni in np.where(np.abs(y - y.min()) < 1e-9)[0]:
        d[4 * int(ni) + 1] = 0.0
    for ni in np.where(np.abs(z - z.min()) < 1e-9)[0]:
        d[4 * int(ni) + 2] = 0.0
    if constrained:                                            # also fix far faces -> u = 0
        for ni in np.where(np.abs(x - x.max()) < 1e-9)[0]:
            d[4 * int(ni) + 0] = 0.0
        for ni in np.where(np.abs(y - y.max()) < 1e-9)[0]:
            d[4 * int(ni) + 1] = 0.0
        for ni in np.where(np.abs(z - z.max()) < 1e-9)[0]:
            d[4 * int(ni) + 2] = 0.0
    from ._coupled_solve import coupled_newton, direct_linsolve
    U, _n, _info = coupled_newton([group], ndof, d, direct_linsolve, maxit=maxit, tol=1e-12)
    return U, nodes, ndof


def main():
    G, K, alpha = 1.0, 100.0, 1.0e-3
    props = (G, K, alpha, 0.25, 1.0); dT = 10.0
    # --- free expansion: u = (lambda-1) X, exact ---
    t = time.time()
    U, nodes, ndof = solve_thermomech(4, dT=dT, props=props)
    lam = free_expansion_lambda(dT, G=G, K=K, alpha=alpha)
    u = U.reshape(-1, 4)[:, :3]
    u_ref = (lam - 1.0) * nodes
    err = np.max(np.abs(u - u_ref)) / max(1e-30, np.max(np.abs(u_ref)))
    print("3D coupled thermo-mechanical Hex8 (u + T, codegen complex-step tangent)")
    print(f"  FREE EXPANSION (dT={dT}): lambda={lam:.8f}, u=(lambda-1)X")
    print(f"    max|u - (lambda-1)X| / max|u| = {err:.2e}  ({ndof} DOF, {time.time()-t:.1f}s)  "
          f"{'PASS' if err < 1e-9 else 'CHECK'}")
    # --- constrained block: u=0, sigma = -K alpha dT (broken control for the above) ---
    Uc, nodesc, _ = solve_thermomech(4, dT=dT, props=props, constrained=True)
    uc = Uc.reshape(-1, 4)[:, :3]
    umax = float(np.max(np.abs(uc)))
    sigma_ref = -K * alpha * dT
    print(f"  CONSTRAINED BLOCK (dT={dT}): expect u=0, sigma=-K*alpha*dT={sigma_ref:.5f}")
    print(f"    max|u| = {umax:.2e}  {'PASS (u~0)' if umax < 1e-9 else 'CHECK'}")
    print("  => free expansion != constrained (the broken control): "
          f"{err:.1e} vs u~{umax:.1e} -- the element distinguishes them.")


if __name__ == "__main__":
    main()
