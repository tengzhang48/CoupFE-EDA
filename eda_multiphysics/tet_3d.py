"""Tet4 electro-thermal on gmsh all-tet meshes using CoupFE's native linear tetrahedron.

Why it matters: tetrahedral meshes are a practical route for non-blocky CAD, while
the all-hex subdivision path is limited to roughly blocky solids. On a compatible
CoupFE Core revision, this module checks native Tet4 on generated box and cylinder
meshes against the same analytic oracles used by the Hex8 path. It does not by
itself demonstrate imported package, TSV-array, or solder CAD.

Checks:
  * ``patch_test``     -- a linear temperature field reproduced to MACHINE PRECISION (Tet4 is
                          linear-complete): the element-correctness gate.
  * ``solve_selfheat`` -- Joule self-heating peak ``dT = sigma V0^2 / 8k`` (the exact oracle
                          ``etv_3d``'s Hex8 hits), on a tet box AND a tet cylinder (curved CAD),
                          within tet discretization error and converging with refinement.
"""
import os

import numpy as np

from .mesh3d import min_signed_tet_volume, tet_box, tet_cylinder


def _kernel(props, workdir):
    from .etv_kernel import build_et_kernel
    wd = workdir or os.path.join(os.path.dirname(__file__), "_etk_tet")
    os.makedirs(wd, exist_ok=True)
    return build_et_kernel(wd, sigma0=props[0], alpha=props[1], k=props[2], element="Tet4")


def _solve(coords, tets, props, bc, mod, maxit=12):
    from coupfe import ElementGroup
    from coupfe.runtime.compiled_element import CompiledElement
    from ._coupled_solve import coupled_newton, direct_linsolve
    elem = CompiledElement(mod, props=props, dof_per_node=2, n_svars=0, mcrd=3, n_elem=len(tets))
    group = ElementGroup(elem, coords, tets, dof_per_node=2, comps=(0, 1))
    ndof = len(coords) * 2
    U, _n, _info = coupled_newton([group], ndof, bc, direct_linsolve, maxit=maxit, tol=1e-12)
    return U


def oracle_selfheat(props, V0=2.0):
    """Peak self-heating temperature rise for a 1-D voltage drop: ``dT = sigma V0^2 / 8k``."""
    return props[0] * V0 ** 2 / (8.0 * props[2])


def solve_selfheat(mesh="box", h=0.18, props=(3.0, 0.0, 1.5), V0=2.0, workdir=None):
    """Self-heating on a gmsh tet mesh. Voltage ``V0`` across the x-faces (box) or the z-caps
    (cylinder); ``T`` pinned 0 there. Returns ``(peak_dT, min_signed_vol, n_nodes, n_tets)``."""
    mod = _kernel(props, workdir)
    if mesh == "cylinder":
        m = tet_cylinder(R=1.0, L=1.0, h=h)
        coords, tets, lo, hi = m["coords"], m["tets"], m["cap0"], m["capL"]
    else:
        coords, tets = tet_box(1.0, h)
        x = coords[:, 0]
        lo = np.where(np.abs(x - x.min()) < 1e-9)[0]
        hi = np.where(np.abs(x - x.max()) < 1e-9)[0]
    bc = {}
    for n in lo:
        bc[2 * int(n)] = 0.0; bc[2 * int(n) + 1] = 0.0
    for n in hi:
        bc[2 * int(n)] = V0; bc[2 * int(n) + 1] = 0.0
    U = _solve(coords, tets, props, bc, mod)
    return float(U[1::2].max()), min_signed_tet_volume(coords, tets), len(coords), len(tets)


def patch_test(h=0.25, props=(3.0, 0.0, 1.5), coeffs=(1.0, 2.0, -3.0, 0.5), workdir=None):
    """Linear-completeness gate. With ``phi`` pinned 0 (no current -> no Joule source), impose a
    linear ``T = a + b.x + c.y + d.z`` on the boundary; the interior must reproduce it EXACTLY
    (Tet4 is linear-complete). Returns ``max|T - exact|`` (~1e-16 == pass)."""
    mod = _kernel(props, workdir)
    coords, tets = tet_box(1.0, h)
    a, b, c, d = coeffs
    tlin = a + b * coords[:, 0] + c * coords[:, 1] + d * coords[:, 2]
    onb = np.zeros(len(coords), bool)
    for j in range(3):
        onb |= np.abs(coords[:, j] - coords[:, j].min()) < 1e-9
        onb |= np.abs(coords[:, j] - coords[:, j].max()) < 1e-9
    bc = {2 * n: 0.0 for n in range(len(coords))}          # phi = 0 everywhere -> no current
    for n in np.where(onb)[0]:
        bc[2 * int(n) + 1] = float(tlin[int(n)])
    U = _solve(coords, tets, props, bc, mod)
    return float(np.max(np.abs(U[1::2] - tlin)))


def main():
    props = (3.0, 0.0, 1.5)
    err = patch_test()
    print(f"Tet4 patch test (linear T, machine precision): max|err| = {err:.2e}  "
          f"{'PASS' if err < 1e-11 else 'FAIL'}")
    ex = oracle_selfheat(props)
    for mesh in ("box", "cylinder"):
        pk, mv, nn, ne = solve_selfheat(mesh=mesh, props=props)
        print(f"Tet4 self-heating [{mesh:8s}]: peak={pk:.4f} vs sigmaV0^2/8k={ex:.4f}  "
              f"rel={abs(pk - ex) / ex:.2e}  (minVol={mv:.1e}, {nn} nodes, {ne} tets)")


if __name__ == "__main__":
    main()
