"""Anisotropic small-strain Tet4 foundation for a Cu/oxide/Si TSV local submodel.

This module supplies constitutive, assembly, stress-recovery, and Raman-depth
extraction functions for the generated local model described in
``docs/GEOMETRY.md``. It reports ``release_validation=False``: the numerical
mechanics checks are not an experimental Raman comparison.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import spsolve

from .tsv_device import cubic_stiffness_tensor, rotate_fourth_order


# Jiang et al. 2013, Section 2.4 for Cu/oxide; Ryu et al. 2012 for cubic Si.
DEFAULT_MATERIALS = {
    "copper": {"kind": "isotropic", "E_GPa": 110.0, "nu": 0.35, "alpha_per_K": 17.0e-6},
    "oxide": {"kind": "isotropic", "E_GPa": 70.0, "nu": 0.16, "alpha_per_K": 0.55e-6},
    "silicon": {
        "kind": "cubic", "C11_GPa": 166.2, "C12_GPa": 64.4, "C44_GPa": 79.8,
        "alpha_per_K": 2.3e-6,
    },
}
VOIGT_ORDER = ("xx", "yy", "zz", "xy", "yz", "xz")


@dataclass(frozen=True)
class LocalTSVResult:
    displacement_m: np.ndarray
    element_stress_mpa: dict[str, np.ndarray]
    reactions_n: np.ndarray
    constrained_dofs: np.ndarray
    free_residual_relative: float
    dT_K: float
    boundary_condition: str
    crystal_to_global: np.ndarray
    coordinate_frame: dict
    material_sha256: str
    mesh_sha256: str
    constraint_sha256: str | None
    constraint_error_max: float
    macro_gradient: np.ndarray | None
    periodic_pair_mismatch_m: float | None
    reduced_dofs: int
    release_validation: bool = False
    claim_boundary: str = (
        "Numerical anisotropic local-TSV result; curvature/Raman experimental validation pending."
    )


def _strain_tensor(engineering_strain):
    e = np.asarray(engineering_strain)
    return np.array([
        [e[0], 0.5 * e[3], 0.5 * e[5]],
        [0.5 * e[3], e[1], 0.5 * e[4]],
        [0.5 * e[5], 0.5 * e[4], e[2]],
    ], dtype=e.dtype)


def _stress_voigt(stress):
    return np.asarray([stress[0, 0], stress[1, 1], stress[2, 2],
                       stress[0, 1], stress[1, 2], stress[0, 2]])


def fourth_order_to_engineering_voigt(stiffness):
    """Convert ``C_ijkl`` to a 6x6 matrix acting on engineering shear strain."""
    C = np.asarray(stiffness, dtype=float)
    if C.shape != (3, 3, 3, 3) or not np.all(np.isfinite(C)):
        raise ValueError("stiffness must be finite with shape (3,3,3,3)")
    D = np.empty((6, 6), dtype=float)
    for column in range(6):
        strain = np.zeros(6)
        strain[column] = 1.0
        D[:, column] = _stress_voigt(np.einsum("ijkl,kl->ij", C, _strain_tensor(strain)))
    if not np.allclose(D, D.T, atol=1.0e-10):
        raise ValueError("stiffness does not produce a symmetric Voigt matrix")
    return D


def isotropic_voigt(E_GPa, nu):
    """Small-strain isotropic stiffness in Pa for the project engineering-Voigt order."""
    E, nu = float(E_GPa) * 1.0e9, float(nu)
    if not np.isfinite(E) or E <= 0.0 or not np.isfinite(nu) or not (-1.0 < nu < 0.5):
        raise ValueError("E_GPa and nu must define a stable isotropic material")
    lam = E * nu / ((1.0 + nu) * (1.0 - 2.0 * nu))
    mu = E / (2.0 * (1.0 + nu))
    D = np.zeros((6, 6))
    D[:3, :3] = lam
    np.fill_diagonal(D[:3, :3], lam + 2.0 * mu)
    np.fill_diagonal(D[3:, 3:], mu)
    return D


def material_voigt(material, *, crystal_to_global=None):
    """Return ``(D_Pa, alpha_per_K)`` for an isotropic or cubic material manifest."""
    if not isinstance(material, dict) or "kind" not in material or "alpha_per_K" not in material:
        raise ValueError("material must contain kind and alpha_per_K")
    alpha = float(material["alpha_per_K"])
    if not np.isfinite(alpha):
        raise ValueError("alpha_per_K must be finite")
    if material["kind"] == "isotropic":
        D = isotropic_voigt(material["E_GPa"], material["nu"])
    elif material["kind"] == "cubic":
        C = cubic_stiffness_tensor(
            material["C11_GPa"], material["C12_GPa"], material["C44_GPa"]
        )
        if crystal_to_global is not None:
            C = rotate_fourth_order(C, crystal_to_global)
        D = fourth_order_to_engineering_voigt(C) * 1.0e9
    else:
        raise ValueError("material kind must be 'isotropic' or 'cubic'")
    if np.linalg.eigvalsh(D).min() <= 0.0:
        raise ValueError("material stiffness must be positive definite")
    return D, alpha


def tet4_B_volume(coords_m):
    """Return the constant engineering-strain matrix and positive Tet4 volume in SI units."""
    xyz = np.asarray(coords_m, dtype=float)
    if xyz.shape != (4, 3) or not np.all(np.isfinite(xyz)):
        raise ValueError("coords_m must be finite with shape (4,3)")
    A = np.column_stack([np.ones(4), xyz])
    detA = np.linalg.det(A)
    volume = abs(detA) / 6.0
    edge_scale = max(np.linalg.norm(xyz[i] - xyz[0]) for i in range(1, 4))
    if edge_scale == 0.0 or volume <= 100.0 * np.finfo(float).eps * edge_scale ** 3:
        raise ValueError("Tet4 is degenerate")
    gradients = np.linalg.inv(A)[1:, :].T
    B = np.zeros((6, 12))
    for node, (dx, dy, dz) in enumerate(gradients):
        j = 3 * node
        B[0, j] = dx
        B[1, j + 1] = dy
        B[2, j + 2] = dz
        B[3, j] = dy; B[3, j + 1] = dx
        B[4, j + 1] = dz; B[4, j + 2] = dy
        B[5, j] = dz; B[5, j + 2] = dx
    return B, volume


def _region_materials(materials):
    data = DEFAULT_MATERIALS if materials is None else materials
    if set(data) != {"copper", "oxide", "silicon"}:
        raise ValueError("materials must contain exactly copper, oxide, and silicon")
    return data


def _material_sha256(materials):
    payload = json.dumps(materials, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _mesh_sha256(mesh):
    digest = hashlib.sha256()
    coords = np.ascontiguousarray(mesh["coords"], dtype="<f8")
    digest.update(coords.tobytes())
    for name in sorted(mesh["regions"]):
        digest.update(name.encode("utf-8"))
        digest.update(np.ascontiguousarray(mesh["regions"][name], dtype="<i8").tobytes())
    metadata = {
        "geometry": mesh.get("geometry"), "mesh_refinement": mesh.get("mesh_refinement"),
        "coordinate_frame": mesh.get("coordinate_frame"), "tsv_id": mesh.get("tsv_id"),
        "crystal_to_global": np.asarray(
            mesh.get("crystal_to_global", np.eye(3)), dtype=float
        ).tolist(),
        "periodic_box": None,
        "periodic_pair_sha256": {
            axis: record.get("sha256")
            for axis, record in sorted(mesh.get("periodic_node_pairs", {}).items())
        },
    }
    if mesh.get("periodic_box") is not None:
        box = mesh["periodic_box"]
        metadata["periodic_box"] = {
            "origin_um": np.asarray(box["origin_um"], dtype=float).tolist(),
            "lattice_um": np.asarray(box["lattice_um"], dtype=float).tolist(),
            "periodic": list(box["periodic"]), "sha256": box.get("sha256"),
        }
    digest.update(json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    return digest.hexdigest()


def _validate_rotation(rotation):
    R = np.asarray(rotation, dtype=float)
    if (R.shape != (3, 3) or not np.all(np.isfinite(R))
            or not np.allclose(R @ R.T, np.eye(3), atol=1.0e-12)
            or not np.isclose(np.linalg.det(R), 1.0, atol=1.0e-12)):
        raise ValueError("crystal_to_global must be a finite proper orthonormal 3x3 rotation")
    return R


def assemble_linear_thermoelastic(mesh, dT_K, *, materials=None, crystal_to_global=None):
    """Assemble ``K u = f_thermal`` for named Tet4 regions; coordinates are read in µm."""
    coords_um = np.asarray(mesh["coords"], dtype=float)
    regions = mesh.get("regions")
    if coords_um.ndim != 2 or coords_um.shape[1] != 3 or not np.all(np.isfinite(coords_um)):
        raise ValueError("mesh coords must be a finite (N,3) array in micrometers")
    if not isinstance(regions, dict) or set(regions) != {"copper", "oxide", "silicon"}:
        raise ValueError("mesh regions must contain exactly copper, oxide, and silicon")
    if not np.isfinite(float(dT_K)):
        raise ValueError("dT_K must be finite")
    coords_m = coords_um * 1.0e-6
    ndof = 3 * len(coords_m)
    rows, cols, values = [], [], []
    force = np.zeros(ndof)
    matrices = {}
    for name, material in _region_materials(materials).items():
        matrices[name] = material_voigt(
            material, crystal_to_global=crystal_to_global if name == "silicon" else None
        )
        D, alpha = matrices[name]
        thermal = alpha * float(dT_K) * np.array([1.0, 1.0, 1.0, 0.0, 0.0, 0.0])
        for tet in np.asarray(regions[name], dtype=np.int64):
            if tet.shape != (4,) or np.any(tet < 0) or np.any(tet >= len(coords_m)):
                raise ValueError(f"region {name} contains invalid Tet4 connectivity")
            B, volume = tet4_B_volume(coords_m[tet])
            Ke = B.T @ D @ B * volume
            fe = B.T @ D @ thermal * volume
            dofs = (3 * tet[:, None] + np.arange(3)).ravel()
            rows.extend(np.repeat(dofs, 12)); cols.extend(np.tile(dofs, 12)); values.extend(Ke.ravel())
            np.add.at(force, dofs, fe)
    K = coo_matrix((values, (rows, cols)), shape=(ndof, ndof)).tocsr()
    return K, force, matrices


def minimal_rigid_constraints(mesh):
    """Six zero-displacement constraints that remove only rigid modes from the isolated model."""
    coords = np.asarray(mesh["coords"], dtype=float)
    bottom = np.asarray(mesh.get("bottom", []), dtype=np.int64)
    if len(bottom) < 3:
        zmin = coords[:, 2].min()
        bottom = np.flatnonzero(np.isclose(coords[:, 2], zmin, atol=1.0e-8))
    if len(bottom) < 3:
        raise ValueError("mesh needs at least three bottom nodes to remove rigid modes")
    rb = np.hypot(coords[bottom, 0], coords[bottom, 1])
    a = int(bottom[np.argmin(rb)])
    b = int(bottom[np.argmax(coords[bottom, 0])])
    c = int(bottom[np.argmax(coords[bottom, 1])])
    if len({a, b, c}) < 3:
        raise ValueError("could not select three independent rigid-mode anchor nodes")
    return {3 * a: 0.0, 3 * a + 1: 0.0, 3 * a + 2: 0.0,
            3 * b + 1: 0.0, 3 * b + 2: 0.0, 3 * c + 2: 0.0}


def silicon_far_field_constraints(mesh, dT_K, *, alpha_per_K=2.3e-6):
    """Prescribe free Si thermal contraction on the local model's outer and bottom boundaries."""
    coords_m = np.asarray(mesh["coords"], dtype=float) * 1.0e-6
    nodes = np.unique(np.r_[np.asarray(mesh.get("outer", []), dtype=np.int64),
                            np.asarray(mesh.get("bottom", []), dtype=np.int64)])
    if not len(nodes):
        raise ValueError("mesh needs named outer/bottom nodes for a silicon far-field boundary")
    if not np.isfinite(dT_K) or not np.isfinite(alpha_per_K):
        raise ValueError("dT_K and alpha_per_K must be finite")
    target = float(alpha_per_K) * float(dT_K) * coords_m[nodes]
    return {int(3 * node + component): float(target[i, component])
            for i, node in enumerate(nodes) for component in range(3)}


def periodic_mpc_setup(mesh, macro_gradient):
    """Build SI-unit affine MPC relations and one anchor for a periodic TSV slab."""
    from eda_multiphysics.periodic import (
        PeriodicBox,
        _index_array,
        periodic_relations,
    )
    H = np.asarray(macro_gradient, dtype=float)
    if H.shape != (3, 3) or not np.all(np.isfinite(H)):
        raise ValueError("periodic macro_gradient must be a finite 3x3 matrix")
    if mesh.get("periodic_pairing_status") != "matching_nodes_verified":
        raise ValueError("mesh does not carry verified matching periodic node pairs")
    box_data = mesh.get("periodic_box")
    faces = mesh.get("periodic_faces", {})
    records = mesh.get("periodic_node_pairs", {})
    if box_data is None or set(faces) != {"x_minus", "x_plus", "y_minus", "y_plus"}:
        raise ValueError("periodic mesh is missing box or opposite-face metadata")
    coords_um = np.asarray(mesh["coords"], dtype=float)
    origin_um = np.asarray(box_data["origin_um"], dtype=float)
    lattice_um = np.asarray(box_data["lattice_um"], dtype=float)
    coords_m = coords_um * 1.0e-6
    box_um = PeriodicBox(
        origin_um,
        lattice_um,
        tuple(box_data["periodic"]),
        coordinate_frame=mesh.get("coordinate_frame"),
    )
    box = PeriodicBox(
        origin_um * 1.0e-6,
        lattice_um * 1.0e-6,
        tuple(box_data["periodic"]),
        coordinate_frame=mesh.get("coordinate_frame"),
    )
    pair_sets = []
    for axis, minus, plus, axis_index in (
        ("x", "x_minus", "x_plus", 0), ("y", "y_minus", "y_plus", 1)
    ):
        record = records.get(axis)
        if record is None:
            raise ValueError(f"periodic mesh is missing {axis}-pair provenance")
        tolerance_um = float(record["tolerance_um"])
        provenance_pairs = box_um.pair_faces(
            coords_um,
            faces[minus],
            faces[plus],
            axis_index,
            atol=tolerance_um,
        )
        recorded_masters = _index_array(
            record["master_nodes"], name=f"{axis} recorded master_nodes"
        )
        recorded_slaves = _index_array(
            record["slave_nodes"], name=f"{axis} recorded slave_nodes"
        )
        if (
            not np.array_equal(provenance_pairs.master_nodes, recorded_masters)
            or not np.array_equal(provenance_pairs.slave_nodes, recorded_slaves)
        ):
            raise ValueError(f"periodic {axis}-pair nodes differ from mesh provenance")
        if str(record.get("sha256", "")) != provenance_pairs.sha256:
            raise ValueError(
                f"periodic {axis}-pair provenance hash differs from recomputed pairing"
            )
        pairs = box.pair_faces(
            coords_m,
            faces[minus],
            faces[plus],
            axis_index,
            atol=tolerance_um * 1.0e-6,
        )
        if (
            not np.array_equal(pairs.master_nodes, provenance_pairs.master_nodes)
            or not np.array_equal(pairs.slave_nodes, provenance_pairs.slave_nodes)
        ):
            raise ValueError(
                f"periodic {axis}-pair identity changed under SI conversion"
            )
        pair_sets.append(pairs)
    relations = periodic_relations(
        pair_sets, dof_per_node=3, components=(0, 1, 2),
        coords=coords_m, macro_gradient=H, label="tsv_periodic",
    )

    origin_distance = np.linalg.norm(coords_m - box.origin, axis=1)
    anchor_node = int(np.argmin(origin_distance))
    tolerance_m = max(float(record["tolerance_um"]) for record in records.values()) * 1.0e-6
    if origin_distance[anchor_node] > tolerance_m:
        raise ValueError("periodic mesh has no node at the declared box origin for its anchor")
    slave_dofs = {relation.slave for relation in relations}
    anchor_target = H @ (coords_m[anchor_node] - box.origin)
    anchor = {3 * anchor_node + component: float(anchor_target[component]) for component in range(3)}
    if any(dof in slave_dofs for dof in anchor):
        raise ValueError("periodic anchor was compiled as an MPC slave instead of a representative")
    mismatch = max(pairs.max_mismatch for pairs in pair_sets)
    return relations, anchor, H, float(mismatch)


def solve_local_tsv(mesh, dT_K, *, materials=None, crystal_to_global=None, dirichlet=None,
                    boundary_condition="minimal_rigid", macro_gradient=None):
    """Solve the anisotropic linear Tet4 local model and recover full element stress tensors."""
    material_data = _region_materials(materials)
    rotation = _validate_rotation(
        mesh.get("crystal_to_global", np.eye(3)) if crystal_to_global is None else crystal_to_global
    )
    K, force, matrices = assemble_linear_thermoelastic(
        mesh, dT_K, materials=material_data, crystal_to_global=rotation
    )
    transform = None
    constraint_sha256 = None
    constraint_error_max = 0.0
    periodic_pair_mismatch_m = None
    recorded_macro_gradient = None
    if dirichlet is not None:
        if macro_gradient is not None:
            raise ValueError("macro_gradient is only valid with periodic_macro_gradient")
        constraints = dict(dirichlet)
        boundary_label = "user_dirichlet"
    elif boundary_condition == "minimal_rigid":
        constraints = minimal_rigid_constraints(mesh)
        boundary_label = boundary_condition
    elif boundary_condition == "silicon_free_expansion":
        constraints = silicon_far_field_constraints(
            mesh, dT_K, alpha_per_K=material_data["silicon"]["alpha_per_K"]
        )
        boundary_label = boundary_condition
    elif boundary_condition == "periodic_macro_gradient":
        if macro_gradient is None:
            raise ValueError("periodic_macro_gradient requires an explicit macro_gradient")
        relations, constraints, recorded_macro_gradient, periodic_pair_mismatch_m = (
            periodic_mpc_setup(mesh, macro_gradient)
        )
        from coupfe.constraints.affine import compile_affine_constraints
        transform = compile_affine_constraints(K.shape[0], relations, dirichlet=constraints)
        boundary_label = boundary_condition
    else:
        raise ValueError(
            "boundary_condition must be 'minimal_rigid', 'silicon_free_expansion', or "
            "'periodic_macro_gradient'"
        )
    if not constraints:
        raise ValueError("dirichlet constraints are required to remove rigid modes")
    ndof = K.shape[0]
    if transform is not None:
        reduced_K, reduced_force = transform.reduce_linear_system(K, force)
        q = spsolve(reduced_K, reduced_force) if transform.reduced_ndof else np.zeros(0)
        u = transform.lift(q)
        fixed = np.array([relation.slave for relation in transform.relations], dtype=np.int64)
        free = transform.independent_dofs
        constraint_sha256 = transform.sha256
        constraint_error_max = float(np.max(np.abs(transform.constraint_error(u))))
    else:
        fixed = np.array(sorted(int(dof) for dof in constraints), dtype=np.int64)
        if np.any(fixed < 0) or np.any(fixed >= ndof):
            raise ValueError("dirichlet contains an out-of-range degree of freedom")
        u = np.zeros(ndof)
        u[fixed] = [float(constraints[dof]) for dof in fixed]
        free = np.setdiff1d(np.arange(ndof), fixed)
        if len(free):
            rhs = force[free] - K[free][:, fixed] @ u[fixed]
            u[free] = spsolve(K[free][:, free], rhs)
    if not np.all(np.isfinite(u)):
        raise RuntimeError("local TSV linear solve produced non-finite displacement")
    residual = K @ u - force
    if transform is not None:
        reduced_residual = transform.restrict_residual(residual)
        scale = max(np.linalg.norm(transform.restrict_residual(force)), 1.0e-30)
        free_relative = float(np.linalg.norm(reduced_residual) / scale)
    else:
        scale = max(np.linalg.norm(force[free]), 1.0e-30) if len(free) else 1.0
        free_relative = float(np.linalg.norm(residual[free]) / scale) if len(free) else 0.0
    coords_m = np.asarray(mesh["coords"], dtype=float) * 1.0e-6
    stresses = {}
    for name, tets in mesh["regions"].items():
        D, alpha = matrices[name]
        thermal = alpha * float(dT_K) * np.array([1.0, 1.0, 1.0, 0.0, 0.0, 0.0])
        region_stress = []
        for tet in np.asarray(tets, dtype=np.int64):
            B, _ = tet4_B_volume(coords_m[tet])
            dofs = (3 * tet[:, None] + np.arange(3)).ravel()
            sv = D @ (B @ u[dofs] - thermal) / 1.0e6
            region_stress.append(np.array([
                [sv[0], sv[3], sv[5]], [sv[3], sv[1], sv[4]], [sv[5], sv[4], sv[2]]
            ]))
        stresses[name] = np.asarray(region_stress)
    return LocalTSVResult(
        displacement_m=u.reshape(-1, 3), element_stress_mpa=stresses,
        reactions_n=residual[fixed], constrained_dofs=fixed,
        free_residual_relative=free_relative, dT_K=float(dT_K),
        boundary_condition=boundary_label,
        crystal_to_global=rotation.copy(),
        coordinate_frame=dict(mesh.get("coordinate_frame", {})),
        material_sha256=_material_sha256(material_data), mesh_sha256=_mesh_sha256(mesh),
        constraint_sha256=constraint_sha256,
        constraint_error_max=constraint_error_max,
        macro_gradient=(None if recorded_macro_gradient is None else recorded_macro_gradient.copy()),
        periodic_pair_mismatch_m=periodic_pair_mismatch_m,
        reduced_dofs=(len(free) if transform is None else transform.reduced_ndof),
    )


def raman_scan_points(distances_from_si_interface_um, *, diameter_um=10.0, oxide_um=0.4,
                      depth_um=0.2, direction=(1.0, 1.0), surface_z_um=0.0):
    """Return scan coordinates at the exact Raman depth along an in-plane crystal direction."""
    distances = np.asarray(distances_from_si_interface_um, dtype=float)
    direction = np.asarray(direction, dtype=float)
    if distances.ndim != 1 or not len(distances) or not np.all(np.isfinite(distances)):
        raise ValueError("distances must be a non-empty finite 1-D array")
    if np.any(distances < 0.0):
        raise ValueError("distances from the Si interface must be non-negative")
    if direction.shape != (2,) or not np.all(np.isfinite(direction)) or np.linalg.norm(direction) == 0:
        raise ValueError("direction must be a finite nonzero in-plane vector")
    if not np.isfinite(depth_um) or depth_um <= 0.0:
        raise ValueError("depth_um must be positive and finite")
    if (not np.isfinite(diameter_um) or diameter_um <= 0.0 or not np.isfinite(oxide_um)
            or oxide_um < 0.0 or not np.isfinite(surface_z_um)):
        raise ValueError("diameter, oxide thickness, and surface coordinate must be physical")
    unit = direction / np.linalg.norm(direction)
    radius = 0.5 * float(diameter_um) + float(oxide_um) + distances
    return np.column_stack([radius[:, None] * unit[None, :],
                            np.full(len(distances), float(surface_z_um) - float(depth_um))])


def sample_element_field(points_um, coords_um, tets, element_values, *, strict=True, tol=1.0e-9):
    """Sample a piecewise-constant Tet4 element field by barycentric point location."""
    points = np.asarray(points_um, dtype=float)
    coords = np.asarray(coords_um, dtype=float)
    tets = np.asarray(tets, dtype=np.int64)
    values = np.asarray(element_values)
    if points.ndim != 2 or points.shape[1] != 3 or not np.all(np.isfinite(points)):
        raise ValueError("points_um must be finite with shape (N,3)")
    if coords.ndim != 2 or coords.shape[1] != 3 or not np.all(np.isfinite(coords)):
        raise ValueError("coords_um must be a finite (N,3) array")
    if tets.ndim != 2 or tets.shape[1] != 4 or len(values) != len(tets):
        raise ValueError("tets must be (E,4) and element_values must have length E")
    if np.any(tets < 0) or np.any(tets >= len(coords)) or not np.all(np.isfinite(values)):
        raise ValueError("connectivity and element_values must be finite and valid")
    vertices = coords[tets]
    lo, hi = vertices.min(axis=1) - tol, vertices.max(axis=1) + tol
    found = np.full(len(points), -1, dtype=np.int64)
    for pindex, point in enumerate(points):
        candidates = np.flatnonzero(np.all((point >= lo) & (point <= hi), axis=1))
        for eindex in candidates:
            v = vertices[eindex]
            bary123 = np.linalg.solve((v[1:] - v[0]).T, point - v[0])
            bary = np.r_[1.0 - bary123.sum(), bary123]
            if np.all(bary >= -tol) and np.all(bary <= 1.0 + tol):
                found[pindex] = eindex
                break
    if strict and np.any(found < 0):
        missing = np.flatnonzero(found < 0).tolist()
        raise ValueError(f"sample points outside Tet4 field: indices {missing}")
    output = np.full((len(points),) + values.shape[1:], np.nan, dtype=np.result_type(values, float))
    valid = found >= 0
    output[valid] = values[found[valid]]
    return output, found


def element_to_nodal_field(coords_um, tets, element_values):
    """Volume-average a Tet4 element field to nodes within one material region."""
    coords = np.asarray(coords_um, dtype=float)
    tets = np.asarray(tets, dtype=np.int64)
    values = np.asarray(element_values)
    if coords.ndim != 2 or coords.shape[1] != 3 or not np.all(np.isfinite(coords)):
        raise ValueError("coords_um must be a finite (N,3) array")
    if tets.ndim != 2 or tets.shape[1] != 4 or len(values) != len(tets):
        raise ValueError("tets must be (E,4) and element_values must have length E")
    if np.any(tets < 0) or np.any(tets >= len(coords)) or not np.all(np.isfinite(values)):
        raise ValueError("connectivity and element_values must be finite and valid")
    vertices = coords[tets]
    volumes = np.abs(np.einsum(
        "ei,ei->e", np.cross(vertices[:, 1] - vertices[:, 0], vertices[:, 2] - vertices[:, 0]),
        vertices[:, 3] - vertices[:, 0],
    )) / 6.0
    if np.any(volumes <= 0.0):
        raise ValueError("cannot recover a nodal field from degenerate Tet4 elements")
    nodal = np.zeros((len(coords),) + values.shape[1:], dtype=np.result_type(values, float))
    weights = np.zeros(len(coords))
    value_weights = volumes.reshape((len(volumes),) + (1,) * (values.ndim - 1))
    for local in range(4):
        np.add.at(nodal, tets[:, local], values * value_weights)
        np.add.at(weights, tets[:, local], volumes)
    active = weights > 0.0
    nodal[active] /= weights[active].reshape((-1,) + (1,) * (values.ndim - 1))
    nodal[~active] = np.nan
    return nodal, weights


def project_element_field_l2(coords_um, tets, element_values):
    """Consistent P1 L2 projection of a piecewise-constant Tet4 field to material-region nodes."""
    coords = np.asarray(coords_um, dtype=float)
    tets = np.asarray(tets, dtype=np.int64)
    values = np.asarray(element_values)
    if coords.ndim != 2 or coords.shape[1] != 3 or not np.all(np.isfinite(coords)):
        raise ValueError("coords_um must be a finite (N,3) array")
    if tets.ndim != 2 or tets.shape[1] != 4 or len(values) != len(tets):
        raise ValueError("tets must be (E,4) and element_values must have length E")
    if np.any(tets < 0) or np.any(tets >= len(coords)) or not np.all(np.isfinite(values)):
        raise ValueError("connectivity and element_values must be finite and valid")
    active = np.unique(tets)
    local = np.full(len(coords), -1, dtype=np.int64)
    local[active] = np.arange(len(active))
    ltets = local[tets]
    vertices = coords[tets]
    volumes = np.abs(np.einsum(
        "ei,ei->e", np.cross(vertices[:, 1] - vertices[:, 0], vertices[:, 2] - vertices[:, 0]),
        vertices[:, 3] - vertices[:, 0],
    )) / 6.0
    if np.any(volumes <= 0.0):
        raise ValueError("cannot project a field from degenerate Tet4 elements")
    rows, cols, mass_values = [], [], []
    rhs = np.zeros((len(active), int(np.prod(values.shape[1:]) or 1)))
    flat_values = values.reshape(len(values), -1)
    for a in range(4):
        ia = ltets[:, a]
        np.add.at(rhs, ia, flat_values * (volumes / 4.0)[:, None])
        for b in range(4):
            rows.extend(ia)
            cols.extend(ltets[:, b])
            mass_values.extend(volumes * (2.0 if a == b else 1.0) / 20.0)
    mass = coo_matrix((mass_values, (rows, cols)), shape=(len(active), len(active))).tocsr()
    projected = spsolve(mass, rhs)
    if projected.ndim == 1:
        projected = projected[:, None]
    nodal = np.full((len(coords),) + values.shape[1:], np.nan, dtype=np.result_type(values, float))
    nodal[active] = projected.reshape((len(active),) + values.shape[1:])
    return nodal, active


def sample_nodal_field(points_um, coords_um, tets, nodal_values, *, strict=True, tol=1.0e-9):
    """Interpolate a Tet4 nodal field using barycentric coordinates and fail closed outside."""
    points = np.asarray(points_um, dtype=float)
    coords = np.asarray(coords_um, dtype=float)
    tets = np.asarray(tets, dtype=np.int64)
    values = np.asarray(nodal_values)
    if points.ndim != 2 or points.shape[1] != 3 or not np.all(np.isfinite(points)):
        raise ValueError("points_um must be finite with shape (N,3)")
    if coords.ndim != 2 or coords.shape[1] != 3 or values.shape[0] != len(coords):
        raise ValueError("coords_um and nodal_values must share a valid node dimension")
    if tets.ndim != 2 or tets.shape[1] != 4 or np.any(tets < 0) or np.any(tets >= len(coords)):
        raise ValueError("tets must contain valid (E,4) connectivity")
    vertices = coords[tets]
    lo, hi = vertices.min(axis=1) - tol, vertices.max(axis=1) + tol
    found = np.full(len(points), -1, dtype=np.int64)
    output = np.full((len(points),) + values.shape[1:], np.nan, dtype=np.result_type(values, float))
    for pindex, point in enumerate(points):
        candidates = np.flatnonzero(np.all((point >= lo) & (point <= hi), axis=1))
        for eindex in candidates:
            v = vertices[eindex]
            bary123 = np.linalg.solve((v[1:] - v[0]).T, point - v[0])
            bary = np.r_[1.0 - bary123.sum(), bary123]
            if np.all(bary >= -tol) and np.all(bary <= 1.0 + tol):
                if not np.all(np.isfinite(values[tets[eindex]])):
                    continue
                output[pindex] = np.tensordot(bary, values[tets[eindex]], axes=(0, 0))
                found[pindex] = eindex
                break
    if strict and np.any(found < 0):
        missing = np.flatnonzero(found < 0).tolist()
        raise ValueError(f"sample points outside Tet4 nodal field: indices {missing}")
    return output, found


def gaussian_spot_quadrature(centers_um, spot_sigma_um, *, direction=(1.0, 1.0), order=3):
    """Deterministic 2-D Gaussian quadrature about scan centers at a fixed physical depth.

    ``spot_sigma_um`` is mandatory because Jiang et al. report only sub-micron resolution, not an
    exact spot width.  The function therefore supplies a sensitivity operator, never a hidden
    experimental calibration.
    """
    centers = np.asarray(centers_um, dtype=float)
    direction = np.asarray(direction, dtype=float)
    if centers.ndim != 2 or centers.shape[1] != 3 or not np.all(np.isfinite(centers)):
        raise ValueError("centers_um must be finite with shape (N,3)")
    if not np.isfinite(spot_sigma_um) or spot_sigma_um <= 0.0:
        raise ValueError("spot_sigma_um must be positive and explicit")
    if direction.shape != (2,) or not np.all(np.isfinite(direction)) or np.linalg.norm(direction) == 0:
        raise ValueError("direction must be a finite nonzero in-plane vector")
    if int(order) != order or not 2 <= int(order) <= 8:
        raise ValueError("Gaussian quadrature order must be an integer from 2 through 8")
    along = direction / np.linalg.norm(direction)
    across = np.array([-along[1], along[0]])
    nodes, weights_1d = np.polynomial.hermite.hermgauss(int(order))
    offsets = []
    weights = []
    for i, xi in enumerate(nodes):
        for j, eta in enumerate(nodes):
            offsets.append(np.sqrt(2.0) * float(spot_sigma_um) * (xi * along + eta * across))
            weights.append(weights_1d[i] * weights_1d[j] / np.pi)
    offsets = np.asarray(offsets)
    points = np.repeat(centers[:, None, :], len(offsets), axis=1)
    points[:, :, :2] += offsets[None, :, :]
    return points, np.asarray(weights)


def silicon_raman_profile(mesh, result, distances_um, *, direction=(1.0, 1.0),
                          recovery="l2_nodal"):
    """Extract silicon stress and ``sigma_xx+sigma_yy`` on the manifest Raman plane."""
    geometry = mesh["geometry"]
    points = raman_scan_points(
        distances_um, diameter_um=geometry["diameter_um"], oxide_um=geometry["oxide_um"],
        depth_um=geometry["raman_depth_um"], direction=direction,
        surface_z_um=mesh["wafer_surface_z_um"],
    )
    silicon_tets = mesh["regions"]["silicon"]
    if recovery == "l2_nodal":
        nodal, _ = project_element_field_l2(
            mesh["coords"], silicon_tets, result.element_stress_mpa["silicon"]
        )
        stress, elements = sample_nodal_field(points, mesh["coords"], silicon_tets, nodal, strict=True)
    elif recovery == "volume_weighted_nodal":
        nodal, _ = element_to_nodal_field(
            mesh["coords"], silicon_tets, result.element_stress_mpa["silicon"]
        )
        stress, elements = sample_nodal_field(points, mesh["coords"], silicon_tets, nodal, strict=True)
    elif recovery == "element_constant":
        stress, elements = sample_element_field(
            points, mesh["coords"], silicon_tets, result.element_stress_mpa["silicon"], strict=True
        )
    else:
        raise ValueError("recovery must be 'l2_nodal', 'volume_weighted_nodal', or 'element_constant'")
    observable = stress[:, 0, 0] + stress[:, 1, 1]
    return {"points_um": points, "stress_mpa": stress, "raman_stress_sum_mpa": observable,
            "silicon_element_indices": elements, "recovery": recovery,
            "release_validation": False}


def silicon_raman_spot_profile(mesh, result, distances_um, *, spot_sigma_um,
                               direction=(1.0, 1.0), quadrature_order=3,
                               recovery="l2_nodal"):
    """Gaussian-spot sensitivity of the recovered silicon Raman observable at fixed depth."""
    geometry = mesh["geometry"]
    centers = raman_scan_points(
        distances_um, diameter_um=geometry["diameter_um"], oxide_um=geometry["oxide_um"],
        depth_um=geometry["raman_depth_um"], direction=direction,
        surface_z_um=mesh["wafer_surface_z_um"],
    )
    points, weights = gaussian_spot_quadrature(
        centers, spot_sigma_um, direction=direction, order=quadrature_order
    )
    silicon_tets = mesh["regions"]["silicon"]
    if recovery == "l2_nodal":
        nodal, _ = project_element_field_l2(
            mesh["coords"], silicon_tets, result.element_stress_mpa["silicon"]
        )
    elif recovery == "volume_weighted_nodal":
        nodal, _ = element_to_nodal_field(
            mesh["coords"], silicon_tets, result.element_stress_mpa["silicon"]
        )
    else:
        raise ValueError("spot recovery must be 'l2_nodal' or 'volume_weighted_nodal'")
    flat_stress, elements = sample_nodal_field(
        points.reshape(-1, 3), mesh["coords"], silicon_tets, nodal, strict=True
    )
    stress = flat_stress.reshape(points.shape[:2] + (3, 3))
    observable_samples = stress[:, :, 0, 0] + stress[:, :, 1, 1]
    averaged = observable_samples @ weights
    return {
        "centers_um": centers, "sample_points_um": points, "quadrature_weights": weights,
        "raman_stress_sum_mpa": averaged, "sample_stress_sum_mpa": observable_samples,
        "silicon_element_indices": elements.reshape(points.shape[:2]),
        "spot_sigma_um": float(spot_sigma_um), "quadrature_order": int(quadrature_order),
        "recovery": recovery,
        "release_validation": False,
        "claim_boundary": "Spatial-resolution sensitivity; exact experimental spot width pending.",
    }
