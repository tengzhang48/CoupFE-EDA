"""Independent FEniCSx/DOLFINx reference solve of the declared package model.

Physics implemented from the written model contract only (README, the two driver
scripts' *declared* physics, materials and boundary conditions). Weak forms,
assembly, boundary conditions and solves here are UFL/DOLFINx; nothing is
imported from CoupFE / eda_multiphysics, no generated kernel is used, no matrix
or load vector is reused, and no original result field is read. The reference
thermal solution computed here is the only temperature that drives the
reference mechanical solve.

Steps
  1. read the original mesh arrays and geometry metadata (inputs only),
  2. recompute tetrahedron volumes geometrically and check them against the
     supplied ``volume_m3``,
  3. build a DOLFINx mesh from the same nodes/connectivity and establish an
     explicit, verified map back to the original node and cell IDs,
  4. steady isotropic conduction for theta = T - 40 C, top Robin + bottom
     Dirichlet, uniform per-body volumetric source,
  5. one-way small-strain isotropic linear thermoelasticity driven by that
     theta, 3-2-1 corner anchors, single factorization reused for both cases,
  6. write nodal / cell fields in the original input ordering plus a
     provenance record.

Scope: same P1 Tet4 mesh as the original run, on purpose - this isolates
implementation differences in the two independent codes for one declared linear
synthetic model. It is not an independent discretisation, not a mesh
convergence study and not validation of any real device.

Usage
  OMP_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4 MKL_NUM_THREADS=4 \
  python -u fenicsx_reference.py \
      --mesh-dir ../runs/h0.45 --out results
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
import time
from pathlib import Path

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

import basix.ufl
import dolfinx
import ufl
from dolfinx.fem import Function, dirichletbc, form, functionspace, locate_dofs_topological
from dolfinx.fem.petsc import assemble_matrix, assemble_vector

HERE = Path(__file__).resolve().parent

# ---------------------------------------------------------------- model data
REFERENCE_C = 40.0            # stress-free and reservoir temperature
H_TOP = 4000.0                # prescribed lid coupling, W/(m^2 K); not CFD
TOTAL_POWER_W = 16.0

CONDUCTIVITY_W_mK = {         # top_tim is the only varied parameter
    "organic": 0.8, "attach": 1.5, "silicon": 120.0,
    "mold": 0.8, "copper": 390.0, "solder": 50.0,
}
TOP_TIM_K = {"baseline": 1.0, "improved": 5.0}

# E [GPa], nu [-], linear CTE [1/K]
MATERIALS = {
    "organic": (20.0, 0.30, 16e-6),
    "silicon": (130.0, 0.28, 2.6e-6),
    "attach": (1.0, 0.35, 40e-6),
    "mold": (18.0, 0.30, 12e-6),
    "copper": (110.0, 0.34, 17e-6),
    "solder": (40.0, 0.35, 22e-6),
    "top_tim": (0.05, 0.35, 60e-6),
}

ANCHORS_M = [  # (target point, fixed components)
    ((-0.011, -0.011, -0.001), (0, 1, 2)),
    ((0.011, -0.011, -0.001), (1, 2)),
    ((-0.011, 0.011, -0.001), (2,)),
]

SUBSTRATE_TOP_Z = 0.0007
TOP_MARKER = 1
QDEG = 2  # exact for every integrand here (max polynomial degree 2)


def lame(E_GPa: float, nu: float) -> tuple[float, float]:
    E = E_GPa * 1e9
    return E / (2.0 * (1.0 + nu)), E * nu / ((1.0 + nu) * (1.0 - 2.0 * nu))


# ------------------------------------------------------------------ mesh I/O
def load_input(mesh_dir: Path) -> dict:
    """Original input arrays and metadata; no result field is touched."""
    mesh = np.load(mesh_dir / "mesh.npz", allow_pickle=False)
    meta = json.loads((mesh_dir / "geometry.json").read_text())
    points = np.ascontiguousarray(mesh["points_m"], dtype=np.float64)
    tets = np.ascontiguousarray(mesh["tets"], dtype=np.int64)
    data = dict(
        points=points, tets=tets,
        region_id=np.asarray(mesh["region_id"], dtype=np.int64),
        volume_in=np.asarray(mesh["volume_m3"], dtype=np.float64),
        top=np.asarray(mesh["top"], dtype=np.int64),
        bottom=np.asarray(mesh["bottom"], dtype=np.int64),
        objects=meta["objects"],
    )
    data["materials"] = np.array([o["material"] for o in data["objects"]])
    data["power_W"] = np.array([float(o["power_W"]) for o in data["objects"]])
    return data


def geometric_volumes(points: np.ndarray, tets: np.ndarray) -> np.ndarray:
    edge = points[tets[:, 1:]] - points[tets[:, 0], None, :]
    return np.abs(np.linalg.det(edge)) / 6.0


def build_mesh(points: np.ndarray, tets: np.ndarray):
    element = basix.ufl.element("Lagrange", "tetrahedron", 1, shape=(3,))
    return dolfinx.mesh.create_mesh(MPI.COMM_SELF, tets, ufl.Mesh(element), points)


def mesh_maps(msh, points: np.ndarray, tets: np.ndarray) -> dict:
    """Explicit DOLFINx <-> original ID maps, checked one-to-one.

    ``node_to_input[i]`` is the original node ID of DOLFINx P1 dof ``i``;
    ``cell_to_input[c]`` is the original cell ID of DOLFINx cell ``c``.
    """
    n_nodes, n_cells = len(points), len(tets)
    node_to_input = np.asarray(msh.geometry.input_global_indices, dtype=np.int64)
    cell_to_input = np.asarray(msh.topology.original_cell_index, dtype=np.int64)
    if len(node_to_input) != n_nodes or len(cell_to_input) != n_cells:
        raise RuntimeError("DOLFINx mesh size differs from the input mesh")
    for name, m, size in (("node", node_to_input, n_nodes), ("cell", cell_to_input, n_cells)):
        if not np.array_equal(np.sort(m), np.arange(size)):
            raise RuntimeError(f"{name} map is not a permutation of the input IDs")

    # P1 dof numbering must coincide with the geometry node numbering (serial,
    # affine simplices); assert it instead of assuming it.
    V = functionspace(msh, ("Lagrange", 1))
    geom_dofs = msh.geometry.dofmap.reshape(n_cells, 4)
    p1_dofs = V.dofmap.list.reshape(n_cells, 4)
    if not np.array_equal(geom_dofs, p1_dofs):
        raise RuntimeError("P1 dofmap does not coincide with the geometry dofmap")

    # coordinates: exact agreement expected, the same float64 values are reused
    coord_err = float(np.abs(msh.geometry.x[:, :3] - points[node_to_input]).max())
    if coord_err != 0.0:
        raise RuntimeError(f"node coordinate mismatch {coord_err}")

    # connectivity: cell vertex sets must agree after mapping to original IDs
    mapped = np.sort(node_to_input[geom_dofs], axis=1)
    expected = np.sort(tets[cell_to_input], axis=1)
    if not np.array_equal(mapped, expected):
        raise RuntimeError("cell connectivity mismatch after ID mapping")

    inv_node = np.empty(n_nodes, dtype=np.int64)
    inv_node[node_to_input] = np.arange(n_nodes)
    inv_cell = np.empty(n_cells, dtype=np.int64)
    inv_cell[cell_to_input] = np.arange(n_cells)
    return dict(node_to_input=node_to_input, cell_to_input=cell_to_input,
                inv_node=inv_node, inv_cell=inv_cell,
                node_coord_max_abs_error_m=coord_err)


def tag_top_facets(msh, top_tris: np.ndarray, node_to_input: np.ndarray):
    """Mark exactly the supplied top triangles, matched by original node IDs."""
    tdim = msh.topology.dim
    msh.topology.create_entities(tdim - 1)
    msh.topology.create_connectivity(tdim - 1, tdim)
    exterior = dolfinx.mesh.exterior_facet_indices(msh.topology)
    facet_nodes = dolfinx.mesh.entities_to_geometry(msh, tdim - 1, exterior)
    keys = np.sort(node_to_input[facet_nodes], axis=1)
    wanted = {tuple(k) for k in np.sort(top_tris, axis=1)}
    if len(wanted) != len(top_tris):
        raise RuntimeError("duplicate triangles in the supplied top face set")
    hit = np.array([tuple(k) in wanted for k in keys], dtype=bool)
    facets = exterior[hit]
    if len(facets) != len(top_tris):
        raise RuntimeError(f"matched {len(facets)} top facets, expected {len(top_tris)}")
    order = np.argsort(facets)
    tags = dolfinx.mesh.meshtags(msh, tdim - 1, facets[order].astype(np.int32),
                                 np.full(len(facets), TOP_MARKER, dtype=np.int32))
    return tags, len(facets), len(exterior)


def dg0_field(space, values_by_cell: np.ndarray) -> Function:
    f = Function(space)
    f.x.array[space.dofmap.list.ravel()] = values_by_cell
    return f


def lu_solver(A) -> PETSc.KSP:
    ksp = PETSc.KSP().create(MPI.COMM_SELF)
    ksp.setOperators(A)
    ksp.setType("preonly")
    pc = ksp.getPC()
    pc.setType("lu")
    for package in ("mumps", "superlu", "petsc"):
        try:
            pc.setFactorSolverType(package)
            pc.setUp()
            break
        except PETSc.Error:
            continue
    ksp.setUp()
    return ksp


def weighted_quantile(values: np.ndarray, weights: np.ndarray, q: float) -> float:
    """Weighted nearest-crossing quantile - the original reporting definition."""
    order = np.argsort(values)
    v, w = values[order], weights[order]
    return float(v[np.searchsorted(np.cumsum(w), q * np.sum(w))])


# ------------------------------------------------------- analytic patch tests
def patch_checks() -> dict:
    """Absolute checks of these weak forms on a 6-tetrahedron unit cube.

    Independent of the package model and of the other code: exact Fourier flux
    for a linear temperature field, exact free thermal expansion, and the exact
    fully constrained thermal stress -E alpha dT / (1 - 2 nu).
    """
    pts = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
                    [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]], dtype=np.float64)
    tets = np.array([[0, 1, 2, 6], [0, 2, 3, 6], [0, 3, 7, 6],
                     [0, 7, 4, 6], [0, 4, 5, 6], [0, 5, 1, 6]], dtype=np.int64)
    msh = build_mesh(pts, tets)
    maps = mesh_maps(msh, pts, tets)
    dx = ufl.Measure("dx", domain=msh, metadata={"quadrature_degree": QDEG})

    # 1. conduction: k = 2, T = x with only the x faces fixed removes 2 W.
    V = functionspace(msh, ("Lagrange", 1))
    k_cube = 2.0
    th = Function(V)
    th.x.array[:] = msh.geometry.x[:, 0]
    v = ufl.TestFunction(V)
    R = assemble_vector(form(ufl.inner(k_cube * ufl.grad(th), ufl.grad(v)) * dx)).array
    hot = maps["inv_node"][np.flatnonzero(pts[:, 0] == 1.0)]
    flux_W = float(R[hot].sum())
    flux_error = abs(flux_W - 2.0)

    # 2. thermoelasticity: unconstrained uniform heating gives u = alpha dT x.
    Vv = functionspace(msh, ("Lagrange", 1, (3,)))
    E_GPa, nu, alpha_c, dT = 10.0, 0.3, 1.3e-5, 10.0
    mu_c, lam_c = lame(E_GPa, nu)
    theta_c = Function(V)
    theta_c.x.array[:] = dT
    u, w = ufl.TrialFunction(Vv), ufl.TestFunction(Vv)
    ident = ufl.Identity(3)

    def eps(z):
        return ufl.sym(ufl.grad(z))

    a = form(ufl.inner(2.0 * mu_c * eps(u) + lam_c * ufl.tr(eps(u)) * ident, eps(w)) * dx)
    L = form((2.0 * mu_c + 3.0 * lam_c) * alpha_c * theta_c * ufl.div(w) * dx)
    origin = int(maps["inv_node"][int(np.argmin(np.linalg.norm(pts, axis=1)))])
    bcs = [dirichletbc(PETSc.ScalarType(0.0),
                       np.array([3 * origin + c], dtype=np.int32), Vv.sub(c))
           for c in range(3)]
    # remove the remaining rotations with the minimum extra 3-2-1 components
    nx = int(maps["inv_node"][1])   # (1,0,0): fix y, z
    ny = int(maps["inv_node"][3])   # (0,1,0): fix z
    bcs += [dirichletbc(PETSc.ScalarType(0.0), np.array([3 * nx + c], dtype=np.int32), Vv.sub(c))
            for c in (1, 2)]
    bcs += [dirichletbc(PETSc.ScalarType(0.0), np.array([3 * ny + 2], dtype=np.int32), Vv.sub(2))]
    A = assemble_matrix(a, bcs=bcs)
    A.assemble()
    b = assemble_vector(L)
    dolfinx.fem.petsc.apply_lifting(b, [a], bcs=[bcs])
    b.ghostUpdate(addv=PETSc.InsertMode.ADD, mode=PETSc.ScatterMode.REVERSE)
    dolfinx.fem.petsc.set_bc(b, bcs)
    uh = Function(Vv)
    ksp = lu_solver(A)
    ksp.solve(b, uh.x.petsc_vec)
    uh.x.scatter_forward()
    got = uh.x.array.reshape(-1, 3)[maps["inv_node"]]
    expected = alpha_c * dT * pts
    expansion_error = float(np.abs(got - expected).max() / np.abs(expected).max())

    # 3. fully constrained: sigma = -E alpha dT / (1 - 2 nu) on every component
    Qt = functionspace(msh, basix.ufl.element("DG", "tetrahedron", 0, shape=(3, 3)))
    zero = Function(Vv)
    e_th = eps(zero) - alpha_c * theta_c * ident
    sig = Function(Qt)
    sig.interpolate(dolfinx.fem.Expression(
        2.0 * mu_c * e_th + lam_c * ufl.tr(e_th) * ident, Qt.element.interpolation_points))
    stress = sig.x.array.reshape(-1, 3, 3)
    exact = -E_GPa * 1e9 * alpha_c * dT / (1.0 - 2.0 * nu)
    constrained_error = float(np.abs(stress - exact * np.eye(3)[None]).max())
    ksp.destroy(); A.destroy(); b.destroy()

    if flux_error > 1e-11 or expansion_error > 1e-9 or constrained_error > 1e-3:
        raise RuntimeError(f"patch checks failed: flux {flux_error}, "
                           f"expansion {expansion_error}, stress {constrained_error}")
    return dict(cube_exact_flux_W=2.0, cube_fe_flux_W=flux_W,
                cube_flux_absolute_error_W=flux_error,
                free_expansion_relative_error=expansion_error,
                constrained_stress_exact_Pa=exact,
                constrained_stress_absolute_error_Pa=constrained_error)


# -------------------------------------------------------------------- solves
def thermal_coefficients(Q, maps, data, volumes, case: str):
    """DG0 conductivity and volumetric source for one case."""
    cell_region = data["region_id"][maps["cell_to_input"]]
    k_values = np.array([CONDUCTIVITY_W_mK.get(m, TOP_TIM_K[case]) for m in data["materials"]])
    if not np.isclose(k_values[data["materials"] == "top_tim"], TOP_TIM_K[case]).all():
        raise RuntimeError("top_tim conductivity not applied")

    # uniform volumetric source per powered body, normalised by its meshed volume
    q_cell = np.zeros(len(cell_region))
    body_volume = {}
    for i, power in enumerate(data["power_W"]):
        if power <= 0.0:
            continue
        selected = data["region_id"] == i
        body_volume[data["objects"][i]["id"]] = float(volumes[selected].sum())
        q_cell[cell_region == i] = power / volumes[selected].sum()
    return dg0_field(Q, k_values[cell_region]), dg0_field(Q, q_cell), body_volume


def solve_thermal(msh, maps, data, volumes, facet_tags, case: str) -> dict:
    n = len(data["points"])
    V = functionspace(msh, ("Lagrange", 1))
    Q = functionspace(msh, ("DG", 0))
    k, f, body_volume = thermal_coefficients(Q, maps, data, volumes, case)

    theta, v = ufl.TrialFunction(V), ufl.TestFunction(V)
    dx = ufl.Measure("dx", domain=msh, metadata={"quadrature_degree": QDEG})
    ds_top = ufl.Measure("ds", domain=msh, subdomain_data=facet_tags,
                         metadata={"quadrature_degree": QDEG})(TOP_MARKER)
    a = form(ufl.inner(k * ufl.grad(theta), ufl.grad(v)) * dx + H_TOP * theta * v * ds_top)
    L = form(f * v * dx)

    bottom_nodes = np.unique(data["bottom"])
    bottom_dofs = maps["inv_node"][bottom_nodes].astype(np.int32)
    bc = dirichletbc(PETSc.ScalarType(0.0), np.sort(bottom_dofs), V)

    A = assemble_matrix(a, bcs=[bc])
    A.assemble()
    b = assemble_vector(L)
    dolfinx.fem.petsc.apply_lifting(b, [a], bcs=[[bc]])
    b.ghostUpdate(addv=PETSc.InsertMode.ADD, mode=PETSc.ScatterMode.REVERSE)
    dolfinx.fem.petsc.set_bc(b, [bc])

    th = Function(V, name="theta_K")
    ksp = lu_solver(A)
    ksp.solve(b, th.x.petsc_vec)
    th.x.scatter_forward()
    reason = ksp.getConvergedReason()
    if reason <= 0:
        raise RuntimeError(f"thermal LU solve failed, KSP reason {reason}")

    # discrete FE residual of the unconstrained equations at the solution
    res = form(ufl.inner(k * ufl.grad(th), ufl.grad(v)) * dx
               + H_TOP * th * v * ds_top - f * v * dx)
    R = assemble_vector(res).array.copy()
    total_power = float(assemble_vector(L).array.sum())

    free = np.ones(n, dtype=bool)
    free[bottom_dofs] = False
    load = assemble_vector(L).array
    rel_residual = float(np.linalg.norm(R[free]) / np.linalg.norm(load[free]))
    top_W = float(dolfinx.fem.assemble_scalar(form(H_TOP * th * ds_top)))
    bottom_W = float(-R[bottom_dofs].sum())
    balance = abs(top_W + bottom_W - total_power) / total_power

    if np.any(th.x.array[bottom_dofs] != 0.0):
        raise RuntimeError("bottom Dirichlet nodes are not exactly at the reservoir temperature")
    theta_in = th.x.array[maps["inv_node"]].copy()          # original node order
    T_in = REFERENCE_C + theta_in
    ksp.destroy(); A.destroy(); b.destroy()

    if not np.all(np.isfinite(T_in)):
        raise RuntimeError("non-finite temperature")
    return dict(field_theta_input_order=theta_in, field_T_input_order=T_in,
                theta_function=th,
                report=dict(
                    top_tim_k_W_mK=TOP_TIM_K[case],
                    assembled_total_power_W=total_power,
                    top_removed_W=top_W, board_removed_W=bottom_W,
                    balance_error_relative=float(balance),
                    free_residual_relative=rel_residual,
                    min_C=float(T_in.min()), peak_all_C=float(T_in.max()),
                    peak_location_m=data["points"][int(T_in.argmax())].tolist(),
                    ksp_converged_reason=int(reason),
                    powered_body_meshed_volume_m3=body_volume,
                ))


def material_fields(Q, cell_region: np.ndarray, materials: np.ndarray):
    mu = dg0_field(Q, np.array([lame(*MATERIALS[m][:2])[0] for m in materials])[cell_region])
    lam = dg0_field(Q, np.array([lame(*MATERIALS[m][:2])[1] for m in materials])[cell_region])
    alpha = dg0_field(Q, np.array([MATERIALS[m][2] for m in materials])[cell_region])
    return mu, lam, alpha


def solve_mechanics(msh, maps, data, volumes, thermal, cases: list[str]) -> dict:
    n = len(data["points"])
    Vv = functionspace(msh, ("Lagrange", 1, (3,)))
    Q = functionspace(msh, ("DG", 0))
    Qt = functionspace(msh, basix.ufl.element("DG", "tetrahedron", 0, shape=(3, 3)))
    cell_region = data["region_id"][maps["cell_to_input"]]
    materials = data["materials"]
    mu, lam, alpha = material_fields(Q, cell_region, materials)

    dx = ufl.Measure("dx", domain=msh, metadata={"quadrature_degree": QDEG})
    u, v = ufl.TrialFunction(Vv), ufl.TestFunction(Vv)
    ident = ufl.Identity(3)

    def eps(w):
        return ufl.sym(ufl.grad(w))

    def sigma_mech(w):
        return 2.0 * mu * eps(w) + lam * ufl.tr(eps(w)) * ident

    def sigma_total(w, th):
        e = eps(w) - alpha * th * ident
        return 2.0 * mu * e + lam * ufl.tr(e) * ident

    a = form(ufl.inner(sigma_mech(u), eps(v)) * dx)

    # 3-2-1 anchors: nearest input node to each target point, per-component.
    # dirichletbc on a blocked subspace takes *unrolled* dof indices (3*block+c).
    anchor_nodes, bcs, fixed_dofs = [], [], []
    anchor_components = {}
    for target, comps in ANCHORS_M:
        node = int(np.argmin(np.linalg.norm(data["points"] - np.asarray(target), axis=1)))
        anchor_nodes.append(node)
        anchor_components[node] = comps
        block = int(maps["inv_node"][node])
        for c in comps:
            dofs = np.array([3 * block + c], dtype=np.int32)
            bcs.append(dirichletbc(PETSc.ScalarType(0.0), dofs, Vv.sub(c)))
            fixed_dofs.append(3 * block + c)
    fixed_dofs = np.array(sorted(fixed_dofs))
    probe = Function(Vv)
    probe.x.array[:] = 1.0
    dolfinx.fem.set_bc(probe.x.array, bcs)
    got = np.flatnonzero(probe.x.array == 0.0)
    if not np.array_equal(np.sort(got), fixed_dofs):
        raise RuntimeError(f"anchor constraint landed on dofs {got}, expected {fixed_dofs}")
    free_dofs = np.setdiff1d(np.arange(3 * n), fixed_dofs)

    A = assemble_matrix(a, bcs=bcs)
    A.assemble()
    print(f"  mechanics: {3 * n} dofs, {len(fixed_dofs)} constrained; factorizing", flush=True)
    t0 = time.time()
    ksp = lu_solver(A)          # one factorization reused for both load cases
    factor_s = time.time() - t0
    print(f"  factorization {factor_s:.1f} s", flush=True)

    substrate_index = next(i for i, o in enumerate(data["objects"]) if o["id"] == "substrate")
    substrate_nodes = np.unique(data["tets"][data["region_id"] == substrate_index])
    top_nodes = substrate_nodes[np.isclose(data["points"][substrate_nodes, 2],
                                           SUBSTRATE_TOP_Z, atol=1e-10)]
    plane = np.column_stack([np.ones(len(top_nodes)), data["points"][top_nodes, :2]])
    active_cells_in = data["power_W"][data["region_id"]] > 0.0     # input ordering
    active_nodes_in = np.unique(data["tets"][active_cells_in])

    out = {}
    for case in cases:
        th = thermal[case]["theta_function"]
        L = form((2.0 * mu + 3.0 * lam) * alpha * th * ufl.div(v) * dx)
        b = assemble_vector(L)
        load = b.array.copy()
        dolfinx.fem.petsc.apply_lifting(b, [a], bcs=[bcs])
        b.ghostUpdate(addv=PETSc.InsertMode.ADD, mode=PETSc.ScatterMode.REVERSE)
        dolfinx.fem.petsc.set_bc(b, bcs)

        uh = Function(Vv, name="displacement_m")
        ksp.solve(b, uh.x.petsc_vec)
        uh.x.scatter_forward()
        reason = ksp.getConvergedReason()
        if reason <= 0:
            raise RuntimeError(f"mechanical LU solve failed, KSP reason {reason}")

        R = assemble_vector(form(ufl.inner(sigma_total(uh, th), eps(v)) * dx)).array.copy()
        rel_residual = float(np.linalg.norm(R[free_dofs]) / np.linalg.norm(load[free_dofs]))

        sig = Function(Qt)
        sig.interpolate(dolfinx.fem.Expression(
            sigma_total(uh, th), Qt.element.interpolation_points))
        stress = sig.x.array.reshape(-1, 3, 3)[Qt.dofmap.list.ravel()]
        stress_in = stress[maps["inv_cell"]]                       # input cell order
        dev = stress_in - np.trace(stress_in, axis1=1, axis2=2)[:, None, None] / 3.0 * np.eye(3)
        vm_in = np.sqrt(1.5 * np.sum(dev * dev, axis=(1, 2))) * 1e-6
        principal_in = np.linalg.eigvalsh(stress_in)[:, -1] * 1e-6

        disp_in = uh.x.array.reshape(n, 3)[maps["inv_node"]].copy()
        for node, comps in anchor_components.items():
            if np.any(disp_in[node, list(comps)] != 0.0):
                raise RuntimeError(f"anchor node {node} components {comps} not held at zero")
        uz = disp_in[top_nodes, 2]
        detrended = uz - plane @ np.linalg.lstsq(plane, uz, rcond=None)[0]

        report = dict(
            free_residual_relative=rel_residual,
            substrate_warpage_um=float(np.ptp(detrended) * 1e6),
            warpage_definition=("peak-to-valley z displacement after least-squares plane "
                                "removal on substrate top nodes"),
            active_die_mean_vm_MPa=float(np.average(vm_in[active_cells_in],
                                                    weights=volumes[active_cells_in])),
            active_die_p95_vm_MPa=weighted_quantile(vm_in[active_cells_in],
                                                    volumes[active_cells_in], 0.95),
            active_die_max_principal_MPa=float(principal_in[active_cells_in].max()),
            max_displacement_um=float(np.linalg.norm(disp_in, axis=1).max() * 1e6),
            anchors_node_ids=anchor_nodes,
            anchor_reactions_N=R[fixed_dofs].tolist(),
            net_force_N=np.sum(R.reshape(n, 3), axis=0).tolist(),
            ksp_converged_reason=int(reason),
        )
        out[case] = dict(displacement_m=disp_in, stress_MPa=stress_in * 1e-6,
                         von_mises_MPa=vm_in, principal_max_MPa=principal_in,
                         substrate_top_nodes=top_nodes,
                         substrate_detrended_w_um=detrended * 1e6,
                         residual_N=R.reshape(n, 3)[maps["inv_node"]].copy(),
                         report=report)
        print(f"  {case} mechanics {json.dumps(report)}", flush=True)
        b.destroy()

    ksp.destroy(); A.destroy()
    out["_shared"] = dict(anchor_nodes=anchor_nodes, fixed_dofs=fixed_dofs.tolist(),
                          factorization_s=factor_s,
                          active_nodes_input=active_nodes_in,
                          active_cells_input=active_cells_in,
                          substrate_top_nodes=top_nodes)
    return out


# ---------------------------------------------------------------------- main
def run(mesh_dir: Path, out_dir: Path, cases: list[str]) -> dict:
    started = time.time()
    out_dir.mkdir(parents=True, exist_ok=True)
    checks = patch_checks()
    print(f"patch checks: {json.dumps(checks)}", flush=True)
    data = load_input(mesh_dir)
    points, tets = data["points"], data["tets"]
    n, ncells = len(points), len(tets)
    print(f"input mesh: {n} nodes, {ncells} tets, {len(data['objects'])} bodies", flush=True)

    volumes = geometric_volumes(points, tets)
    vol_rel_each = float(np.abs(volumes / data["volume_in"] - 1.0).max())
    if vol_rel_each > 1e-10:
        raise RuntimeError(f"recomputed volumes disagree with the input: {vol_rel_each}")
    signed = np.linalg.det(points[tets[:, 1:]] - points[tets[:, 0], None, :])
    print(f"volumes: max rel diff {vol_rel_each:.3e}, "
          f"{int((signed <= 0).sum())} non-positive orientations", flush=True)

    msh = build_mesh(points, tets)
    maps = mesh_maps(msh, points, tets)
    facet_tags, n_top, n_ext = tag_top_facets(msh, data["top"], maps["node_to_input"])
    dx_check = ufl.Measure("dx", domain=msh, metadata={"quadrature_degree": QDEG})
    ds_top = ufl.Measure("ds", domain=msh, subdomain_data=facet_tags,
                         metadata={"quadrature_degree": QDEG})(TOP_MARKER)
    fe_volume = float(dolfinx.fem.assemble_scalar(form(1.0 * dx_check)))
    fe_top_area = float(dolfinx.fem.assemble_scalar(form(1.0 * ds_top)))
    print(f"mesh maps verified; top facets {n_top}/{n_ext} exterior, "
          f"area {fe_top_area:.9e} m^2, volume {fe_volume:.9e} m^3", flush=True)

    mesh_checks = dict(
        nodes=n, cells=ncells,
        recomputed_volume_max_relative_error=vol_rel_each,
        recomputed_volume_max_absolute_error_m3=float(np.abs(volumes - data["volume_in"]).max()),
        non_positive_orientations=int((signed <= 0).sum()),
        node_coord_max_abs_error_m=maps["node_coord_max_abs_error_m"],
        connectivity_one_to_one=True,
        dolfinx_total_volume_m3=fe_volume,
        input_total_volume_m3=float(volumes.sum()),
        total_volume_relative_error=float(abs(fe_volume - volumes.sum()) / volumes.sum()),
        top_facets_matched=n_top, exterior_facets=n_ext,
        dolfinx_top_area_m2=fe_top_area,
        nominal_top_area_m2=18e-3 ** 2,
        top_area_relative_error=float(abs(fe_top_area - 18e-3 ** 2) / 18e-3 ** 2),
        bottom_dirichlet_nodes=int(len(np.unique(data["bottom"]))),
    )
    if mesh_checks["total_volume_relative_error"] > 1e-12:
        raise RuntimeError("DOLFINx integrated volume disagrees with the input mesh")
    if mesh_checks["top_area_relative_error"] > 1e-9:
        raise RuntimeError("top Robin surface area disagrees with the nominal lid footprint")

    thermal = {}
    for case in cases:
        print(f"thermal {case} (top_tim k = {TOP_TIM_K[case]} W/(m K))", flush=True)
        thermal[case] = solve_thermal(msh, maps, data, volumes, facet_tags, case)
        rep = thermal[case]["report"]
        if abs(rep["assembled_total_power_W"] - TOTAL_POWER_W) > 1e-9:
            raise RuntimeError(f"assembled power {rep['assembled_total_power_W']} W")
        print(f"  {case} thermal {json.dumps(rep, default=str)}", flush=True)

    mech = solve_mechanics(msh, maps, data, volumes, thermal, cases)
    shared = mech.pop("_shared")
    active_nodes = shared["active_nodes_input"]
    active_cells = shared["active_cells_input"]

    results = {}
    for case in cases:
        T = thermal[case]["field_T_input_order"]
        rep = dict(thermal[case]["report"])
        rep["peak_active_die_node_C"] = float(T[active_nodes].max())
        rep["peak_active_die_node_id"] = int(active_nodes[int(T[active_nodes].argmax())])
        np.savez_compressed(out_dir / f"{case}_fenicsx_fields.npz",
                            temperature_C=T,
                            temperature_rise_K=thermal[case]["field_theta_input_order"])
        m = mech[case]
        np.savez_compressed(out_dir / f"{case}_fenicsx_mechanics.npz",
                            displacement_m=m["displacement_m"], stress_MPa=m["stress_MPa"],
                            von_mises_MPa=m["von_mises_MPa"],
                            principal_max_MPa=m["principal_max_MPa"],
                            substrate_top_nodes=m["substrate_top_nodes"],
                            substrate_detrended_w_um=m["substrate_detrended_w_um"],
                            residual_N=m["residual_N"])
        results[case] = dict(thermal=rep, mechanics=m["report"])

    record = dict(
        solver="FEniCSx / DOLFINx, independent UFL weak forms, direct LU (MUMPS)",
        independence=("weak forms, assembly, boundary conditions and solves implemented here "
                      "from the written model contract; no CoupFE/eda_multiphysics import, no "
                      "generated kernel, no reused matrix, no original result field read by "
                      "this script; the reference mechanical solve is driven by the reference "
                      "thermal solution only"),
        scope=("numerical implementation comparison for one declared linear synthetic model on "
               "the same P1 Tet4 mesh; not an independent discretisation, not mesh convergence, "
               "not device validation, no plasticity"),
        mesh_dir=str(mesh_dir),
        cases=cases,
        thermal_model=dict(equations="steady isotropic Fourier conduction, theta = T - 40 C",
                           conductivity_W_mK={**CONDUCTIVITY_W_mK, "top_tim": TOP_TIM_K},
                           source="uniform volumetric power per powered body, P_body / V_body_meshed",
                           total_power_W=TOTAL_POWER_W,
                           bottom="theta = 0 on the supplied bottom faces (T = 40 C)",
                           top=f"Robin h = {H_TOP} W/(m^2 K) against 40 C on the supplied top faces",
                           other="adiabatic (natural boundary condition)"),
        mechanical_model=dict(
            physics="one-way small-strain isotropic linear thermoelasticity, stress free at 40 C",
            stress="sigma = 2 mu (eps - alpha theta I) + lambda tr(eps - alpha theta I) I",
            materials_E_GPa_nu_alpha_per_K=MATERIALS,
            load="consistent thermal load integrated with the P1 reference theta",
            boundary="3-2-1 corner anchors only; every other face traction free",
            anchors_m=[list(a[0]) for a in ANCHORS_M],
            anchor_fixed_components=[list(a[1]) for a in ANCHORS_M],
            anchor_node_ids=shared["anchor_nodes"],
            factorization_reused=True,
            factorization_s=shared["factorization_s"],
            stress_output="cell centroid values on the original Tet4 cells; no nodal smoothing"),
        mesh_checks=mesh_checks,
        patch_checks=checks,
        reporting=dict(
            peak_active_die="max nodal T over nodes of cells in powered bodies",
            active_die_p95="volume-weighted nearest-crossing 95th percentile of cell von Mises",
            warpage=("substrate nodes at z = 0.0007 m, least-squares plane removed from uz, "
                     "peak-to-valley in micrometres"),
            active_die_cells=int(active_cells.sum()), active_die_nodes=int(len(active_nodes)),
            substrate_top_nodes=int(len(shared["substrate_top_nodes"]))),
        results=results,
        provenance=dict(
            mesh_sha256=hashlib.sha256((mesh_dir / "mesh.npz").read_bytes()).hexdigest(),
            geometry_sha256=hashlib.sha256((mesh_dir / "geometry.json").read_bytes()).hexdigest(),
            script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            dolfinx_version=dolfinx.__version__, ufl_version=ufl.__version__,
            basix_version=basix.__version__,
            petsc_version=".".join(str(i) for i in PETSc.Sys.getVersion()),
            petsc_scalar=str(PETSc.ScalarType.__name__),
            mpi_size=MPI.COMM_WORLD.size, comm="COMM_SELF (serial assembly and solve)",
            python=sys.version, executable=sys.executable, platform=platform.platform(),
            elapsed_s=time.time() - started),
    )
    (out_dir / "fenicsx_result.json").write_text(json.dumps(record, indent=2, default=str))
    print(f"reference complete in {record['provenance']['elapsed_s']:.1f} s", flush=True)
    return record


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mesh-dir", type=Path, default=HERE.parent / "runs" / "h0.45")
    ap.add_argument("--out", type=Path, default=HERE / "results")
    ap.add_argument("--cases", nargs="+", default=["baseline", "improved"],
                    choices=["baseline", "improved"])
    args = ap.parse_args()
    run(args.mesh_dir.resolve(), args.out.resolve(), list(args.cases))


if __name__ == "__main__":
    main()
