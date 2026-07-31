"""Compiled (f2py) coupled electro-thermal Q4 element, via CoupFE's codegen.

This is the CoupFE way to remove the Python assembly loop: the element weak form is written
once in Python, `coupfe.codegen` translates it to a self-contained Fortran UEL (with the full
coupled tangent emitted by complex step), and `build_element_kernel` f2py-compiles it. An
`ElementGroup` then drives one BATCHED compiled call per assembly -- no per-element Python
loop -- and `coupfe.assembly.distributed.solve_distributed` runs it on PETSc/MPI.

Two scalar fields per node (phi = electric potential, T = temperature), both transport-type:
    phi:  storage = 0,                    flux = sigma(T) grad(phi)        (-div sigma grad phi = 0)
    T:    storage = -sigma(T)|grad phi|^2, flux = -k grad(T)               (-div k grad T = Joule)
sigma(T) = sigma0/(1 + alpha T) couples thermal->electrical; the Joule storage term couples
electrical->thermal. Both cross-blocks are in the generated complex-step tangent (one Newton
block system, not a field split).
"""
from __future__ import annotations

import numpy as np

import coupfe.codegen as au
from coupfe.codegen.generators.uel_gen import generate_uel
from coupfe.runtime.compiled_element import build_element_kernel

PROP_ORDER = ("sigma0", "alpha", "k")     # runtime props array order


class ElectroThermalMaterial(au.Material):
    props = dict(sigma0=3.0, alpha=0.0, k=1.5)

    def solvent_flux(self, phi, grad_phi, T):       # phi flux  = sigma(T) grad(phi)
        return (self.sigma0 / (1.0 + self.alpha * T)) * grad_phi

    def solvent_storage(self, phi, T):              # phi storage = 0 (steady electrical)
        return 0.0 * phi

    def species_flux(self, T, grad_T):              # T flux = -k grad(T)  (Fourier)
        return -self.k * grad_T

    def species_storage(self, phi, grad_phi, T):    # T storage = -Joule = -sigma|grad phi|^2
        sig = self.sigma0 / (1.0 + self.alpha * T)
        return -sig * (grad_phi[0] ** 2 + grad_phi[1] ** 2 + grad_phi[2] ** 2)


class ElectroThermalProblem(au.WeakForm):
    material = ElectroThermalMaterial
    ndim = 2          # overridable via __init__(ndim=3) for the Hex8 (3D) kernel

    def define_fields(self):
        self.phi = au.ScalarField("phi", degree=1, test="wphi")
        self.T = au.ScalarField("T", degree=1, test="wT")

    def transport_equation(self, wphi, phi, grad_phi, T):
        return (self.material.solvent_storage(phi, T),
                self.material.solvent_flux(phi, grad_phi, T))

    def species_transport_equation(self, wT, phi, grad_phi, T, grad_T):
        return (self.material.species_storage(phi, grad_phi, T),
                self.material.species_flux(T, grad_T))


def _verify_state():
    return dict(phi=1.0, grad_phi=np.array([2.0, -1.0, 0.0]),
                T=10.0, grad_T=np.array([1.0, 0.5, 0.0]))


def build_et_kernel(workdir, *, sigma0=3.0, alpha=0.0, k=1.5, element="Quad4",
                    compile=True, verify=True):
    """Generate (and f2py-compile) the coupled electro-thermal kernel.

    `element="Quad4"` (2D), `"Hex8"` (3D), or `"Tet4"` (3D linear tet for gmsh arbitrary-CAD
    meshes, supplied natively by CoupFE core) -- the weak form is dimension-agnostic. Returns the
    compiled module (or the .for path if compile=False). props at RUNTIME are (sigma0, alpha, k).
    """
    ndim = 3 if element.lower().startswith(("hex", "tet")) else 2
    p = ElectroThermalProblem(ndim=ndim, sigma0=sigma0, alpha=alpha, k=k)
    if verify:
        p.verify(state=_verify_state(), verbose=False)     # complex-step vs FD tangent check
    tag = element.lower()
    forp = f"{workdir}/et_{tag}.for"
    if tag.startswith("tet"):
        from .tet_element import TET4_CONFIG
        generate_uel(p, forp, element_config=TET4_CONFIG, formulation="standard")
    else:
        generate_uel(p, forp, element=element, formulation="standard")
    if not compile:
        return forp
    return build_element_kernel(forp, f"et_{tag}_kernel", workdir=workdir)


def main():
    """Demonstrate: generate + compile the kernel, then verify the batched COMPILED assembly
    against the exact self-heating limit dT = sigma V0^2 / 8k. Needs gfortran + meson + ninja
    (with the venv bin on PATH)."""
    import tempfile
    import numpy as np
    import scipy.sparse.linalg as spla
    from coupfe import ElementGroup, assemble_residual, assemble_tangent
    from coupfe.runtime.compiled_element import CompiledElement
    with tempfile.TemporaryDirectory() as wd:
        mod = build_et_kernel(wd, sigma0=3.0, alpha=0.0, k=1.5)
        n, V0 = 24, 2.0
        nn = n + 1
        xs = np.linspace(0, 1, nn); ys = np.linspace(0, 0.2, 5)
        nodes = np.array([(x, y) for y in ys for x in xs])
        elems = np.array([[j * nn + i, j * nn + i + 1, (j + 1) * nn + i + 1, (j + 1) * nn + i]
                          for j in range(4) for i in range(n)])
        elem = CompiledElement(mod, props=(3.0, 0.0, 1.5), dof_per_node=2, n_svars=0,
                               mcrd=2, n_elem=len(elems))
        group = ElementGroup(elem, nodes, elems, dof_per_node=2, comps=(0, 1))
        ndof = len(nodes) * 2
        d = {}
        for kk in range(len(nodes)):
            if abs(nodes[kk, 0]) < 1e-9:
                d[2 * kk] = 0.0; d[2 * kk + 1] = 0.0
            if abs(nodes[kk, 0] - 1) < 1e-9:
                d[2 * kk] = V0; d[2 * kk + 1] = 0.0
        drows = np.array(sorted(d)); dvals = np.array([d[i] for i in drows])
        U = np.zeros(ndof)
        for _ in range(3):
            U[drows] = dvals
            R, _ = assemble_residual([group], U, None, 1.0, 1.0, ndof); R[drows] = 0.0
            K = assemble_tangent([group], U, None, 1.0, 1.0, ndof).tolil()
            for r in drows:
                K.rows[r] = [r]; K.data[r] = [1.0]
            U = U + spla.spsolve(K.tocsr(), -R)
        peak, exact = U[1::2].max(), 3.0 * V0 ** 2 / (8 * 1.5)
        print("Compiled electro-thermal Q4 kernel (codegen -> f2py -> batched assembly)")
        print(f"  self-heating: peak dT = {peak:.6f} vs sigma V0^2/8k = {exact:.6f}  "
              f"err {abs(peak - exact) / exact:.1e}  (no Python element loop)")


if __name__ == "__main__":
    main()
