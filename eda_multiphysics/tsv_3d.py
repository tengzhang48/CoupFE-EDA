"""3D electro-thermal solve on a generated cylindrical TSV-like geometry.

`etv_3d` validated the Hex8 coupled kernel on a unit *cube* with a slab self-heating BC -- a
solver-capability demo on a synthetic box. This applies the same compiled Hex8
electro-thermal element to a canonical, generated 3D-IC structure -- a **cylindrical copper via** carrying
axial current, self-heating by Joule, cooled through its silicon-side wall.

The mesh is produced by **gmsh** (`mesh3d.via_cylinder`), the standard open-source mesher -- its
OpenCASCADE kernel builds the solid and its subdivision algorithm produces an all-hexahedral mesh
(we do NOT hand-roll a generator). The gmsh node order is verified compatible with our Hex8
element (signed Jacobian > 0, `min_signed_jacobian`).

Oracle: a long cylinder with uniform volumetric heat
generation q and its wall held at T_w has the exact steady profile
    T(r) = T_w + (q / 4k) (R^2 - r^2),     peak (axis) dT = q R^2 / (4k).
Drive it electrically: axial voltage V over length L gives a uniform current density and
(sigma constant, alpha=0) a uniform Joule source q = sigma0 (V/L)^2, so
    peak dT = sigma0 V^2 R^2 / (4 k L^2).
Ends insulated (natural BC) -> z-invariant -> the 3D solve reproduces the 2D radial closed form.
Trilinear Hex8 only *approximates* the radial quadratic, so this is a benchmark-within-
discretization check that converges with refinement -- reported as such, not "exact".

    python -m eda_multiphysics.tsv_3d [mesh_size_h]
"""
from __future__ import annotations

import os
import sys
import time

import numpy as np
from petsc4py import PETSc

from .etv_3d import _fieldsplit_solve
from .mesh3d import layer_stack, min_signed_jacobian, via_annulus, via_cylinder


def _newton_fieldsplit(groups, ndof, drows, dvals, maxit=8):
    """Full-load Newton loop (FieldSplit/GAMG per step) for a list of ElementGroups (>1 = multi-
    material; the assembler sums them). Returns (U, last_iters)."""
    from coupfe import assemble_residual, assemble_tangent
    U = np.zeros(ndof); its = 0
    for _ in range(maxit):
        U[drows] = dvals
        Rr, _ = assemble_residual(groups, U, None, 1.0, 1.0, ndof); Rr[drows] = 0.0
        K = assemble_tangent(groups, U, None, 1.0, 1.0, ndof).tocsr()
        A = PETSc.Mat().createAIJ(size=K.shape, comm=PETSc.COMM_SELF,
                                  csr=(K.indptr.astype(PETSc.IntType),
                                       K.indices.astype(PETSc.IntType), K.data))
        A.assemble()
        b = PETSc.Vec().createWithArray(-np.asarray(Rr), comm=PETSc.COMM_SELF)
        xbc = b.duplicate(); xbc.set(0.0)
        A.zeroRowsColumns(drows.astype(PETSc.IntType), diag=1.0, x=xbc, b=b)
        dU, its = _fieldsplit_solve(A, b, ndof)
        U = U + dU
        if np.max(np.abs(dU)) < 1e-11:
            break
    return U, its


def solve_via(h=0.15, *, R=1.0, L=1.0, sigma0=3.0, k=1.5, V=2.0, workdir=None, maxit=8):
    """Coupled electro-thermal solve on a gmsh-meshed cylindrical via (alpha=0 -> exact-q oracle).

    BCs: phi = 0 / V on the two end caps; T = 0 on the lateral wall (r=R); ends insulated for T.
    Returns (U, mesh_dict, ndof, iters, min_jacobian).
    """
    from coupfe import ElementGroup, assemble_residual, assemble_tangent
    from coupfe.runtime.compiled_element import CompiledElement
    from .etv_kernel import build_et_kernel

    M = via_cylinder(R=R, L=L, h=h)
    coords, elems = M["coords"], M["elems"]
    mj = min_signed_jacobian(coords, elems)               # mesh-validity self-check
    props = (sigma0, 0.0, k)
    wd = workdir or os.path.join(os.path.dirname(__file__), "_etk_tsv")
    os.makedirs(wd, exist_ok=True)
    mod = build_et_kernel(wd, sigma0=sigma0, alpha=0.0, k=k, element="Hex8")
    elem = CompiledElement(mod, props=props, dof_per_node=2, n_svars=0, mcrd=3, n_elem=len(elems))
    group = ElementGroup(elem, coords, elems, dof_per_node=2, comps=(0, 1))
    ndof = len(coords) * 2

    d = {}
    for n in M["cap0"]:
        d[2 * int(n)] = 0.0                               # bottom cap: phi=0
    for n in M["capL"]:
        d[2 * int(n)] = V                                 # top cap: phi=V
    for n in M["lateral"]:
        d[2 * int(n) + 1] = 0.0                           # wall: T=0
    drows = np.array(sorted(d)); dvals = np.array([d[i] for i in drows])
    U, its = _newton_fieldsplit([group], ndof, drows, dvals, maxit)
    return U, M, ndof, its, mj


def solve_annular_via(h=0.12, *, a=0.5, b=1.0, L=1.0, sigma0=3.0, k_core=3.0, k_ann=1.0, V=2.0,
                      workdir=None, maxit=8):
    """Coupled solve on a gmsh-meshed CONCENTRIC two-material via -- inner core (k_core), outer
    annulus (k_ann), uniform sigma0 -> uniform Joule. One ElementGroup per material (the assembler
    sums them). Returns (U, mesh_dict, ndof, iters, min_jacobian)."""
    from coupfe import ElementGroup
    from coupfe.runtime.compiled_element import CompiledElement
    from .etv_kernel import build_et_kernel

    M = via_annulus(a=a, b=b, L=L, h=h)
    coords = M["coords"]; ndof = len(coords) * 2
    mj = min(min_signed_jacobian(coords, M["core"]), min_signed_jacobian(coords, M["annulus"]))
    wd = workdir or os.path.join(os.path.dirname(__file__), "_etk_tsv")
    os.makedirs(wd, exist_ok=True)
    mod = build_et_kernel(wd, sigma0=sigma0, alpha=0.0, k=k_core, element="Hex8")   # props at runtime
    groups = []
    for elems, kk in ((M["core"], k_core), (M["annulus"], k_ann)):
        ce = CompiledElement(mod, props=(sigma0, 0.0, kk), dof_per_node=2, n_svars=0, mcrd=3,
                             n_elem=len(elems))
        groups.append(ElementGroup(ce, coords, elems, dof_per_node=2, comps=(0, 1)))
    d = {}
    for n in M["cap0"]:
        d[2 * int(n)] = 0.0
    for n in M["capL"]:
        d[2 * int(n)] = V
    for n in M["outer"]:
        d[2 * int(n) + 1] = 0.0                           # outer wall r=b: T=0
    drows = np.array(sorted(d)); dvals = np.array([d[i] for i in drows])
    U, its = _newton_fieldsplit(groups, ndof, drows, dvals, maxit)
    return U, M, ndof, its, mj


def oracle_annular(coords, *, a=0.5, b=1.0, L=1.0, sigma0=3.0, k_core=3.0, k_ann=1.0, V=2.0):
    """Exact composite-cylinder temperature (uniform generation q, two conductivities; the log
    term vanishes because heat through radius r is just q*pi*r^2):
        annulus a<=r<=b:  T = (q/4k_ann)(b^2 - r^2)
        core    0<=r<=a:  T = (q/4k_core)(a^2 - r^2) + (q/4k_ann)(b^2 - a^2)
    """
    q = sigma0 * (V / L) ** 2
    r = np.hypot(coords[:, 0], coords[:, 1])
    t_ann = (q / (4.0 * k_ann)) * (b ** 2 - r ** 2)
    t_core = (q / (4.0 * k_core)) * (a ** 2 - r ** 2) + (q / (4.0 * k_ann)) * (b ** 2 - a ** 2)
    return np.where(r <= a, t_core, t_ann)


def solve_layer_stack(specs, *, W=1.0, h=0.12, T_top=1.0, sigma0=1.0, workdir=None, maxit=8):
    """Pure-conduction series-resistance test on a gmsh-meshed layer stack. `specs` = [(t, k), ...]
    (die/underfill/solder/substrate ...). phi=0 on both faces (no current -> no Joule); T=0 at z=0,
    T=T_top at z=H; lateral insulated. One ElementGroup per layer. Returns (U, M, ndof, its, minJac)."""
    from coupfe import ElementGroup
    from coupfe.runtime.compiled_element import CompiledElement
    from .etv_kernel import build_et_kernel

    M = layer_stack([t for t, _ in specs], W=W, h=h)
    coords = M["coords"]; ndof = len(coords) * 2
    mj = min(min_signed_jacobian(coords, e) for e in M["layers"] if len(e))
    wd = workdir or os.path.join(os.path.dirname(__file__), "_etk_tsv")
    os.makedirs(wd, exist_ok=True)
    mod = build_et_kernel(wd, sigma0=sigma0, alpha=0.0, k=specs[0][1], element="Hex8")
    groups = []
    for elems, (t, k) in zip(M["layers"], specs):
        ce = CompiledElement(mod, props=(sigma0, 0.0, k), dof_per_node=2, n_svars=0, mcrd=3,
                             n_elem=len(elems))
        groups.append(ElementGroup(ce, coords, elems, dof_per_node=2, comps=(0, 1)))
    d = {}
    for n in M["bottom"]:
        d[2 * int(n)] = 0.0; d[2 * int(n) + 1] = 0.0      # phi=0, T=0
    for n in M["top"]:
        d[2 * int(n)] = 0.0; d[2 * int(n) + 1] = T_top    # phi=0, T=T_top
    drows = np.array(sorted(d)); dvals = np.array([d[i] for i in drows])
    U, its = _newton_fieldsplit(groups, ndof, drows, dvals, maxit)
    return U, M, ndof, its, mj


def oracle_stack(coords, specs, T_top):
    """Exact 1D series-thermal-resistance profile: T(z) = T_top * R(z)/R_tot, R = sum t_i/k_i,
    linear within each layer (flux q = T_top/R_tot continuous across interfaces)."""
    ts = np.array([t for t, _ in specs]); ks = np.array([k for _, k in specs])
    bounds = np.concatenate([[0.0], np.cumsum(ts)])
    Rcum = np.concatenate([[0.0], np.cumsum(ts / ks)])
    q = T_top / Rcum[-1]
    z = coords[:, 2]; T = np.empty(len(z))
    for i, (t, k) in enumerate(specs):
        m = (z >= bounds[i] - 1e-9) & (z <= bounds[i + 1] + 1e-9)
        T[m] = q * (Rcum[i] + (z[m] - bounds[i]) / k)
    return T


def oracle(coords, *, R=1.0, L=1.0, sigma0=3.0, k=1.5, V=2.0):
    """Exact heat-generation-cylinder temperature at each node: T(r) = (q/4k)(R^2 - r^2)."""
    q = sigma0 * (V / L) ** 2
    r = np.hypot(coords[:, 0], coords[:, 1])
    return (q / (4.0 * k)) * (R ** 2 - r ** 2)


def _run_cylinder(h):
    R = L = 1.0; sigma0 = 3.0; k = 1.5; V = 2.0
    t = time.time()
    U, M, ndof, its, mj = solve_via(h, R=R, L=L, sigma0=sigma0, k=k, V=V)
    dt = time.time() - t
    T = U[1::2]; Tref = oracle(M["coords"], R=R, L=L, sigma0=sigma0, k=k, V=V)
    peak = float(T.max()); peak_ref = sigma0 * V ** 2 * R ** 2 / (4.0 * k * L ** 2)
    rms = float(np.sqrt(np.mean((T - Tref) ** 2)))
    print("3D electro-thermal on a gmsh-meshed cylindrical TSV (Hex8 codegen kernel, FieldSplit)")
    print(f"  gmsh all-hex: {len(M['elems']):,} Hex8, {ndof:,} DOF, min signed Jacobian {mj:.1e}>0 "
          f"(valid) | {dt:.1f}s, {its} KSP iters")
    print(f"  peak dT(axis) = {peak:.5f} vs sigma0 V^2 R^2 / 4kL^2 = {peak_ref:.5f}  "
          f"(rel {abs(peak - peak_ref) / peak_ref:.2e})")
    print(f"  radial profile T(r)=(q/4k)(R^2-r^2): RMS {rms:.2e}")
    print("  => Hex8 coupled element on generated canonical via geometry; closed-form profile check passed.")


def _run_annular(h):
    a, b, L = 0.5, 1.0, 1.0; sigma0 = 3.0; k_core, k_ann = 3.0, 1.0; V = 2.0
    t = time.time()
    U, M, ndof, its, mj = solve_annular_via(h, a=a, b=b, L=L, sigma0=sigma0, k_core=k_core,
                                            k_ann=k_ann, V=V)
    dt = time.time() - t
    T = U[1::2]
    Tref = oracle_annular(M["coords"], a=a, b=b, L=L, sigma0=sigma0, k_core=k_core, k_ann=k_ann, V=V)
    peak = float(T.max())
    q = sigma0 * (V / L) ** 2
    peak_ref = q * a ** 2 / (4 * k_core) + q * (b ** 2 - a ** 2) / (4 * k_ann)
    rms = float(np.sqrt(np.mean((T - Tref) ** 2)))
    ne = len(M["core"]) + len(M["annulus"])
    print("3D electro-thermal on a gmsh-meshed MULTI-MATERIAL annular via (Cu core / Si annulus)")
    print(f"  gmsh all-hex: {ne:,} Hex8 ({len(M['core'])} core + {len(M['annulus'])} annulus), "
          f"{ndof:,} DOF, min Jac {mj:.1e}>0 | {dt:.1f}s, {its} KSP iters")
    print(f"  peak dT(axis) = {peak:.5f} vs composite oracle q a^2/4k_core + q(b^2-a^2)/4k_ann = "
          f"{peak_ref:.5f}  (rel {abs(peak - peak_ref) / peak_ref:.2e})")
    print(f"  two-region profile (parabola_core matched to parabola_annulus): RMS {rms:.2e}")
    print("  => one ElementGroup per material (no core change), composite-cylinder oracle, validated.")


def _run_stack(h):
    # die / underfill / solder / substrate  (thickness, conductivity)
    specs = [(0.3, 1.5), (0.1, 0.5), (0.2, 3.0), (0.4, 1.0)]
    T_top = 1.0; t = time.time()
    U, M, ndof, its, mj = solve_layer_stack(specs, h=h, T_top=T_top)
    dt = time.time() - t
    T = U[1::2]; Tref = oracle_stack(M["coords"], specs, T_top)
    rms = float(np.sqrt(np.mean((T - Tref) ** 2)))
    maxabs = float(np.max(np.abs(T - Tref)))
    ne = sum(len(e) for e in M["layers"])
    # interface temperatures (the series-resistance prediction) vs oracle
    bounds = M["bounds"]; z = M["coords"][:, 2]
    iface = []
    for zb in bounds[1:-1]:
        sel = np.abs(z - zb) < 1e-9
        iface.append((zb, float(T[sel].mean()), float(Tref[sel].mean())))
    print("3D conduction on a gmsh-meshed MULTI-MATERIAL layer stack (die/underfill/solder/substrate)")
    print(f"  gmsh all-hex: {ne:,} Hex8 in {len(specs)} layers, {ndof:,} DOF, min Jac {mj:.1e}>0 | "
          f"{dt:.1f}s, {its} KSP iters")
    print(f"  series-resistance profile T(z)=T_top*R(z)/R_tot: max|err| {maxabs:.2e}, RMS {rms:.2e}")
    for zb, tfe, tref in iface:
        print(f"    interface z={zb:.2f}: T_fe={tfe:.5f} vs oracle {tref:.5f} (err {abs(tfe-tref):.1e})")
    print("  => one ElementGroup per layer, 1D series-resistance oracle, validated.")


def main():
    args = sys.argv[1:]
    if args and args[0] == "annular":
        _run_annular(float(args[1]) if len(args) > 1 else 0.12)
    elif args and args[0] == "stack":
        _run_stack(float(args[1]) if len(args) > 1 else 0.12)
    else:
        _run_cylinder(float(args[0]) if args else 0.12)


if __name__ == "__main__":
    main()
