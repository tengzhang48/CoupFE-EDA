"""Global-local solder thermal-fatigue demonstration.

The capstone (`reliability_pipeline`) drives the SAC305 Anand life from a *compact* thermal model +
the Lame analytic stress. This exercises the stress link on **generated parametric 3D FE geometry**: a
gmsh-meshed **solder joint** under a standard thermal-cycling boundary condition -- the die/substrate CTE
mismatch imposes a distance-to-neutral-point (DNP) differential displacement du = dalpha*dT*L_D on
the joint, which shears it. The 3D FE computes the solder strain field; its equivalent-strain range
then drives the checked SAC305 Anand material-point cycle and a Syed energy-life mapping.

Evidence: the FE nominal shear reproduces the kinematic dgamma = du/h (the DNP shear). The FE's
added value over the analytic is the strain *concentration*. The frozen oracle uses a cylinder;
parametric barrel and hourglass profiles are available through ``joint_shape`` for geometry
sensitivity studies.
Scope: the profiled-joint/package path is a global-local chain (elastic 3D FE
for deformation plus a material-point viscoplastic mapping for dW/life). The
separate ``critical_joint_bvp_screening`` path drives a regular stateful Hex8
block from one maximum-DNP design object and reports any tie set; it is not the
profiled package mesh.
N_f is calibration-specific.
The measured-life gate is an in-sample calibration reproduction within +/-2x,
not independent validation; the reported dW is not a mesh-convergence result.

    python -m eda_multiphysics.reliability_3d
"""
from __future__ import annotations

import json
import os
import re

import numpy as np

from .anand import SAC305, thermal_cycle
from .joint_map import load_joint_map
from .mesh3d import min_signed_jacobian, solder_bump, solder_package, via_cylinder
from .thermomech_kernel import build_thermomech_kernel

SYED_W = 0.0019                               # Syed energy life: N_f = 1/(SYED_W * dW), dW in MPa
SOLDER = (19.0, 42.0)                          # SAC solder elastic constants (G=mu, K=lambda)
PACKAGE_MATERIALS = {
    "solder": SOLDER,
    "underfill": (2.0, 5.0),
    "bottom_ubm": (48.0, 140.0),
    "top_ubm": (48.0, 140.0),
    "bottom_pad": (48.0, 140.0),
    "top_pad": (48.0, 140.0),
}
DEFAULT_SPICE = os.path.join(os.path.dirname(__file__), "cases", "synthetic_pdn", "pdn_vdd.sp")

_XI = np.array([[-1, -1, -1], [1, -1, -1], [1, 1, -1], [-1, 1, -1],
                [-1, -1, 1], [1, -1, 1], [1, 1, 1], [-1, 1, 1]], float)


def element_strain(coords, elems, U):
    """Small-strain tensor at each Hex8 element centre: eps = sym(grad u). Returns (ne,3,3)."""
    dN = 0.125 * _XI                                   # dN_a/dxi at centre (8,3)
    J = np.einsum('ai,eaj->eij', dN, coords[elems])    # (ne,3,3)
    dNx = np.einsum('eij,aj->eai', np.linalg.inv(J), dN)            # dN_a/dX (ne,8,3)
    ue = U.reshape(-1, 4)[elems][:, :, :3]             # nodal displacements (ne,8,3)
    gradu = np.einsum('eai,eaj->eij', ue, dNx)         # du_i/dX_j
    return 0.5 * (gradu + np.transpose(gradu, (0, 2, 1)))


def tet_element_strain(coords, tets, U):
    """Constant small-strain tensor in each Tet4 element. Returns ``(ne, 3, 3)``."""
    xyz = coords[tets]
    A = np.concatenate([np.ones((len(tets), 4, 1)), xyz], axis=2)
    invA = np.linalg.inv(A)
    gradN = np.transpose(invA[:, 1:, :], (0, 2, 1))
    ue = U.reshape(-1, 4)[tets][:, :, :3]
    gradu = np.einsum("eac,ead->ecd", ue, gradN)
    return 0.5 * (gradu + np.transpose(gradu, (0, 2, 1)))


def _equiv(eps):
    """von Mises equivalent strain of a (…,3,3) strain tensor."""
    dev = eps - np.eye(3) * (np.trace(eps, axis1=-2, axis2=-1)[..., None, None] / 3.0)
    return np.sqrt(2.0 / 3.0 * np.einsum('...ij,...ij->...', dev, dev))


def solve_solder_joint(du, *, R=0.5, h=0.4, mesh_h=0.12, mat=SOLDER, workdir=None, mod=None,
                       maxit=20, joint_shape="cylinder", R_mid=None):
    """Solve a gmsh solder joint under thermal-cycling DNP shear.

    ``joint_shape`` is ``cylinder`` (the frozen validation oracle), ``barrel``, or ``hourglass``.
    For the profiled shapes, ``R`` is the pad radius and ``R_mid`` is the mid-height radius; when
    omitted, the mid-radius is 1.15×R for a barrel and 0.85×R for an hourglass. The bottom cap is
    fixed, the top cap is rigidly displaced by ``du`` in x, and the lateral surface is traction
    free. Returns ``(U, mesh_dict)``; the mesh dict records the actual geometry parameters.
    """
    from coupfe import ElementGroup, assemble_residual, assemble_tangent
    from coupfe.runtime.compiled_element import CompiledElement
    from .thermomech_tsv import _fieldsplit_tm_solve

    if joint_shape == "cylinder":
        if R_mid is not None and not np.isclose(R_mid, R):
            raise ValueError("cylindrical joint requires R_mid == R or R_mid=None")
        M = via_cylinder(R=R, L=h, h=mesh_h)
        M.update(shape="cylinder", R_pad=float(R), R_mid=float(R), L=float(h),
                 profile_z=np.array([0.0, 0.5 * h, h]),
                 profile_r=np.array([R, R, R], dtype=float))
    elif joint_shape in {"barrel", "hourglass"}:
        R_mid = R * (1.15 if joint_shape == "barrel" else 0.85) if R_mid is None else R_mid
        if joint_shape == "barrel" and R_mid <= R:
            raise ValueError("barrel joint requires R_mid > R")
        if joint_shape == "hourglass" and R_mid >= R:
            raise ValueError("hourglass joint requires R_mid < R")
        M = solder_bump(R_pad=R, R_mid=R_mid, L=h, h=mesh_h)
    else:
        raise ValueError("joint_shape must be 'cylinder', 'barrel', or 'hourglass'")
    coords = M["coords"]; ndof = len(coords) * 4
    if mod is None:
        mod = build_thermomech_kernel(workdir or os.path.join(os.path.dirname(__file__), "_tm_hex"),
                                      element="Hex8")
    G, K = mat
    elem = CompiledElement(mod, props=(G, K, 0.0, 1.0, 1.0), dof_per_node=4, n_svars=0, mcrd=3,
                           n_elem=len(M["elems"]))
    group = ElementGroup(elem, coords, M["elems"], dof_per_node=4, comps=(0, 1, 2, 3))
    d = {int(4 * n + 3): 0.0 for n in range(len(coords))}       # T = 0 (mechanical load only)
    for n in M["cap0"]:                                          # bottom face fully fixed
        d[4 * int(n) + 0] = 0.0; d[4 * int(n) + 1] = 0.0; d[4 * int(n) + 2] = 0.0
    for n in M["capL"]:                                          # top face: rigid lateral shift du
        d[4 * int(n) + 0] = du; d[4 * int(n) + 1] = 0.0; d[4 * int(n) + 2] = 0.0
    from ._coupled_solve import coupled_newton

    def backend(Kc, Rr, dr):
        dU, n = _fieldsplit_tm_solve(Kc, Rr, dr, coords)
        return dU, {"ksp_its": n}

    U, _n, _info = coupled_newton([group], ndof, d, backend, maxit=maxit, tol=1e-12)
    return U, M


def solve_solder_package_joint(du, *, R_pad=0.50, R_mid=0.575, h_joint=0.40,
                               mesh_h=0.25, materials=None, workdir=None, mod=None,
                               maxit=20, **geometry):
    """Solve the conformal solder/underfill/UBM/pad local model under DNP shear.

    The complex multiply connected assembly uses native Tet4 elements. ``materials`` maps each
    named region to ``(G, K)``; defaults are representative stiffness ratios for a sensitivity
    model, not a foundry-qualified material deck. Bottom pad nodes are fixed, top pad nodes receive
    rigid displacement ``du``, and every temperature DOF is zero for a mechanical-only solve.
    """
    from coupfe import ElementGroup
    from coupfe.runtime.compiled_element import CompiledElement
    from .thermomech_tsv import _fieldsplit_tm_solve
    from ._coupled_solve import coupled_newton

    mats = dict(PACKAGE_MATERIALS)
    if materials is not None:
        mats.update(materials)
    M = solder_package(R_pad=R_pad, R_mid=R_mid, L=h_joint, h=mesh_h, **geometry)
    missing = sorted(set(M["regions"]) - set(mats))
    if missing:
        raise ValueError(f"missing material properties for regions: {missing}")
    coords = M["coords"]
    ndof = len(coords) * 4
    if mod is None:
        mod = build_thermomech_kernel(
            workdir or os.path.join(os.path.dirname(__file__), "_tm_tet"), element="Tet4"
        )
    groups = []
    for name, elems in M["regions"].items():
        G, K = (float(v) for v in mats[name])
        if G <= 0.0 or K <= 0.0:
            raise ValueError(f"region {name!r} requires positive G and K")
        elem = CompiledElement(mod, props=(G, K, 0.0, 1.0, 1.0), dof_per_node=4,
                               n_svars=0, mcrd=3, n_elem=len(elems))
        groups.append(ElementGroup(elem, coords, elems, dof_per_node=4, comps=(0, 1, 2, 3)))
    d = {int(4 * n + 3): 0.0 for n in range(len(coords))}
    for n in M["bottom"]:
        d[4 * int(n)] = 0.0; d[4 * int(n) + 1] = 0.0; d[4 * int(n) + 2] = 0.0
    for n in M["top"]:
        d[4 * int(n)] = du; d[4 * int(n) + 1] = 0.0; d[4 * int(n) + 2] = 0.0

    def backend(Kc, Rr, dr):
        dU, n = _fieldsplit_tm_solve(Kc, Rr, dr, coords)
        return dU, {"ksp_its": n}

    U, _n, info = coupled_newton(groups, ndof, d, backend, maxit=maxit, tol=1e-12)
    M["materials"] = mats
    return U, M, info


def _layout_dbu_per_um(spice_path, dbu_per_um):
    """Resolve layout units explicitly, preferring the case manifest beside the netlist."""
    if dbu_per_um is not None:
        value = float(dbu_per_um)
    else:
        manifest_path = os.path.join(os.path.dirname(os.path.abspath(spice_path)), "manifest.json")
        if not os.path.exists(manifest_path):
            raise ValueError(
                f"cannot determine DBU scale for {spice_path!r}: no sibling manifest.json; "
                "pass dbu_per_um explicitly"
            )
        with open(manifest_path) as f:
            manifest = json.load(f)
        if "dbu_per_micron" not in manifest:
            raise ValueError(f"{manifest_path!r} does not define 'dbu_per_micron'")
        value = float(manifest["dbu_per_micron"])
    if not np.isfinite(value) or value <= 0.0:
        raise ValueError(f"dbu_per_um must be positive and finite, got {value!r}")
    return value


def design_grid(spice_path=DEFAULT_SPICE, dbu_per_um=None):
    """Parse a coordinate-labeled PDN SPICE netlist (``NET_x_y_layer``, x/y in DBU) into a
    power-grid footprint. This accepts PDNSim ``write_pg_spice`` output and the bundled synthetic
    fixture. Returns (xy_um[N,2], center_um[2], dnp_um[N]) -- each grid point's
    distance to the neutral point (die centre). By default the DBU scale is read from the sibling
    case ``manifest.json``; callers with a standalone netlist must pass ``dbu_per_um`` explicitly.
    This is the legacy PDN-node proxy, retained as a labeled fallback for cases without an explicit
    package-joint map. The layout footprint, not an assumed L_D, sets the distances."""
    dbu_per_um = _layout_dbu_per_um(spice_path, dbu_per_um)
    pts = set()
    with open(spice_path) as f:
        for line in f:
            for m in re.finditer(r"_(\d+)_(\d+)_\d+\b", line):
                pts.add((int(m.group(1)), int(m.group(2))))
    if not pts:
        raise ValueError(f"no NET_x_y_layer coordinates found in {spice_path!r}")
    xy = np.array(sorted(pts), float) / dbu_per_um
    cen = xy.mean(0)
    return xy, cen, np.hypot(xy[:, 0] - cen[0], xy[:, 1] - cen[1])


def design_joints(spice_path=DEFAULT_SPICE, *, joint_map_path=None, dbu_per_um=None):
    """Resolve joint locations, identity, DNP, dimensions, and provenance for a design.

    A caller-supplied ``joint_map_path`` takes priority. Otherwise a sibling ``joints.csv`` is used
    when present. If neither exists, PDN nodes are decoded by :func:`design_grid` and returned with
    stable generated IDs and ``pdn_node_proxy_fallback`` provenance. The fallback is intentionally
    explicit in the result; it must not be presented as measured or package-exported bump geometry.
    """
    candidate = os.fspath(joint_map_path) if joint_map_path is not None else os.path.join(
        os.path.dirname(os.path.abspath(spice_path)), "joints.csv"
    )
    if joint_map_path is not None or os.path.exists(candidate):
        joint_map = load_joint_map(candidate)
        xy = joint_map.xy_um
        dnp = joint_map.dnp_um
        return dict(
            xy=xy,
            xyz=joint_map.xyz_um,
            center=joint_map.neutral_point_um[:2],
            neutral_point=joint_map.neutral_point_um,
            dnp=dnp,
            joint_ids=np.asarray(joint_map.ids, dtype=object),
            diameter_um=joint_map.diameter_um,
            height_um=joint_map.height_um,
            nets=np.asarray(joint_map.nets, dtype=object),
            source_object_ids=np.asarray(joint_map.source_object_ids, dtype=object),
            source=joint_map.source,
            geometry_fidelity=joint_map.geometry_fidelity,
            coordinate_frame=joint_map.coordinate_frame,
            explicit=True,
            path=str(joint_map.path),
        )
    xy, center, dnp = design_grid(spice_path, dbu_per_um=dbu_per_um)
    n = len(xy)
    return dict(
        xy=xy,
        xyz=np.column_stack([xy, np.zeros(n)]),
        center=center,
        neutral_point=np.r_[center, 0.0],
        dnp=dnp,
        joint_ids=np.asarray([f"PDN_PROXY_{index:04d}" for index in range(n)], dtype=object),
        diameter_um=np.full(n, np.nan),
        height_um=np.full(n, np.nan),
        nets=np.full(n, "", dtype=object),
        source_object_ids=np.full(n, "", dtype=object),
        source="pdn_node_proxy_fallback",
        geometry_fidelity="proxy",
        coordinate_frame="die_um",
        explicit=False,
        path=os.fspath(spice_path),
    )


def from_design(spice_path=DEFAULT_SPICE, *, h_solder=50.0, R=25.0, dalpha=14.4e-6, dT=165.0,
                dbu_per_um=None, joint_map_path=None, joint_shape="cylinder", R_mid=None,
                include_package=False,
                package_geometry=None, package_materials=None, mod=None, package_mod=None):
    """Joint map -> 3D-FE -> calibration-specific screening map for a design.

    An explicit ``joints.csv`` location/identity map is preferred; otherwise
    the power-grid footprint is a labeled proxy. Diameter and height fields are
    retained as provenance but do not currently size the parametric FE model.
    The 3D FE solves a maximum-DNP-joint elastic response; a documented
    strain-versus-DNP mapping then gives calibration-dependent Anand/Syed output
    per joint. Returns a dict including IDs and source provenance.
    """
    joints = design_joints(spice_path, joint_map_path=joint_map_path, dbu_per_um=dbu_per_um)
    xy, cen, dnp = joints["xy"], joints["center"], joints["dnp"]
    L_D = float(dnp.max())                                  # maximum-DNP joint
    du = dalpha * dT * L_D
    if R_mid is None:
        R_mid = R * ({"cylinder": 1.0, "barrel": 1.15, "hourglass": 0.85}.get(
            joint_shape, np.nan))
    if not np.isfinite(R_mid):
        raise ValueError("joint_shape must be 'cylinder', 'barrel', or 'hourglass'")
    if joint_shape == "cylinder" and not np.isclose(R_mid, R):
        raise ValueError("cylindrical joint requires R_mid == R")
    if joint_shape == "barrel" and R_mid <= R:
        raise ValueError("barrel joint requires R_mid > R")
    if joint_shape == "hourglass" and R_mid >= R:
        raise ValueError("hourglass joint requires R_mid < R")
    if include_package:
        geometry = dict(R_ubm=1.16 * R, R_metal=1.40 * R, R_underfill=1.80 * R,
                        t_ubm=0.10 * h_solder, t_pad=0.16 * h_solder)
        if package_geometry:
            geometry.update(package_geometry)
        U, M, _info = solve_solder_package_joint(
            du, R_pad=R, R_mid=R_mid, h_joint=h_solder, mesh_h=0.625 * h_solder,
            materials=package_materials, mod=package_mod, **geometry
        )
        eps = tet_element_strain(M["coords"], M["regions"]["solder"], U)
        joint_model = "solder+underfill+UBM+pads"
    else:
        U, M = solve_solder_joint(du, R=R, h=h_solder, mesh_h=h_solder / 3.0, mod=mod,
                                  joint_shape=joint_shape, R_mid=R_mid)
        eps = element_strain(M["coords"], M["elems"], U)
        joint_model = "bare_solder"
    gamma_fe = float(np.median(2.0 * np.abs(eps[:, 0, 2])))
    eps_eq_crit = float(np.percentile(_equiv(eps), 95))
    # per-joint: elastic FE strain scales linearly with DNP -> Anand/Syed life per joint
    lives = []
    for d in dnp:
        eps_eq = eps_eq_crit * (d / max(L_D, 1e-30))
        dW = thermal_cycle(SAC305, Tlo=-40.0, Thi=125.0, dalpha=eps_eq / dT, ncyc=6)["dW_stab"]
        lives.append(1.0 / (SYED_W * max(dW, 1e-30)))
    lives = np.array(lives)
    return dict(xy=xy, xyz=joints["xyz"], dnp=dnp, L_D=L_D,
                gamma_fe=gamma_fe, gamma_dnp=du / h_solder,
                eps_eq_crit=eps_eq_crit, lives=lives, n_joints=len(xy), joint_shape=M["shape"],
                joint_model=joint_model,
                R_pad=M["R_pad"], R_mid=M["R_mid"],
                extent=(np.ptp(xy[:, 0]), np.ptp(xy[:, 1])),
                center=cen, neutral_point=joints["neutral_point"],
                joint_ids=joints["joint_ids"], diameter_um=joints["diameter_um"],
                height_um=joints["height_um"], nets=joints["nets"],
                source_object_ids=joints["source_object_ids"],
                joint_source=joints["source"], joint_map_explicit=joints["explicit"],
                joint_geometry_fidelity=joints["geometry_fidelity"],
                coordinate_frame=joints["coordinate_frame"], joint_map_path=joints["path"])


def critical_joint_bvp_screening(
    spice_path=DEFAULT_SPICE,
    *,
    h_solder=50.0,
    dalpha=14.4e-6,
    Tlo=-40.0,
    Thi=125.0,
    nx=3,
    ny=3,
    nz=2,
    ncyc=1,
    steps_per_cyc=8,
    dbu_per_um=None,
    joint_map_path=None,
):
    """Connect one maximum-DNP design object to the stateful block example.

    This retains source identity and the design-derived ``L_D`` while using the
    caller-supplied ``h_solder`` to form ``L_D/h`` for the regular Hex8 block in
    :func:`anand_3d.solder_joint_bvp_3d`.  Joint-map height metadata is retained
    but does not currently set the block height. Symmetric layouts can contain
    several maximum-DNP objects; ties are reported and resolved by stable
    joint-map row order.
    The Syed value is reported only as a calibration-specific screening output;
    it is not a package-life prediction.
    """
    from .anand_3d import solder_joint_bvp_3d

    if h_solder <= 0.0:
        raise ValueError("h_solder must be positive")

    joints = design_joints(
        spice_path,
        joint_map_path=joint_map_path,
        dbu_per_um=dbu_per_um,
    )
    maximum_dnp = float(np.max(joints["dnp"]))
    tied_indices = np.flatnonzero(
        np.isclose(joints["dnp"], maximum_dnp, rtol=1.0e-12, atol=1.0e-12)
    )
    # Joint-map row order is stable and therefore provides a deterministic,
    # reviewable tie break for symmetric layouts.
    critical_index = int(tied_indices[0])
    L_D = float(joints["dnp"][critical_index])
    result = solder_joint_bvp_3d(
        nx=nx,
        ny=ny,
        nz=nz,
        Tlo=Tlo,
        Thi=Thi,
        dalpha=dalpha,
        ldnp_over_h=L_D / h_solder,
        ncyc=ncyc,
        steps_per_cyc=steps_per_cyc,
    )
    return {
        **result,
        "L_D": L_D,
        "ldnp_over_h": L_D / h_solder,
        "joint_id": str(joints["joint_ids"][critical_index]),
        "source_object_id": str(joints["source_object_ids"][critical_index]),
        "net": str(joints["nets"][critical_index]),
        "diameter_um": float(joints["diameter_um"][critical_index]),
        "height_um": float(joints["height_um"][critical_index]),
        "screening_height_um": float(h_solder),
        "joint_source": joints["source"],
        "joint_map_explicit": bool(joints["explicit"]),
        "joint_geometry_fidelity": joints["geometry_fidelity"],
        "coordinate_frame": joints["coordinate_frame"],
        "joint_map_path": joints["path"],
        "maximum_dnp_tie_count": int(len(tied_indices)),
        "maximum_dnp_tied_joint_ids": [
            str(joints["joint_ids"][index]) for index in tied_indices
        ],
        "critical_joint_selection_policy": (
            "maximum DNP; first tied object in stable joint-map row order"
        ),
        "Nf_screen_peak": 1.0 / (SYED_W * max(result["dW_peak"], 1.0e-30)),
    }


def _run_design(joint_shape="cylinder", R_mid=None, include_package=False, joint_map_path=None):
    mod = package_mod = None
    if include_package:
        package_mod = build_thermomech_kernel(
            os.path.join(os.path.dirname(__file__), "_tm_tet"), element="Tet4"
        )
    else:
        mod = build_thermomech_kernel(
            os.path.join(os.path.dirname(__file__), "_tm_hex"), element="Hex8"
        )
    r = from_design(mod=mod, package_mod=package_mod, joint_shape=joint_shape, R_mid=R_mid,
                    include_package=include_package, joint_map_path=joint_map_path)
    print("Joint map -> 3D FE -> calibration-specific solder screening map")
    print(f"  geometry source: {r['joint_source']} ({'explicit map' if r['joint_map_explicit'] else 'fallback'})")
    print(f"  geometry fidelity: {r['joint_geometry_fidelity']}")
    print(f"  design: {r['n_joints']} joints, footprint {r['extent'][0]:.0f}x{r['extent'][1]:.0f} um "
          f"| critical DNP = {r['L_D']:.1f} um (maximum-DNP joint)")
    print(f"  joint geometry: {r['joint_shape']} / {r['joint_model']} "
          f"(pad radius {r['R_pad']:.2f} um, mid radius {r['R_mid']:.2f} um)")
    print(f"  critical joint 3D FE: shear gamma={r['gamma_fe']:.4f} vs DNP du/h={r['gamma_dnp']:.4f} "
          f"-> equiv-strain {r['eps_eq_crit']:.4f}")
    Nf = r["lives"]
    print(f"  calibration-specific Anand->Syed screen across the array: "
          f"minimum = {Nf.min():,.0f} cycles, maximum = {Nf.max():,.0e}, "
          f"median = {np.median(Nf):,.0f}")
    print("  the 3D-FE screening chain is driven by a versioned, provenance-labeled footprint,")
    print("     not an assumed L_D. The bundled coordinates are synthetic; caller-supplied")
    print("     package geometry, calibrated materials, and measured validation are required")
    print("     before treating the screening values as predictive life.")


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(
        description="3D solder-joint geometry and calibration-specific screening."
    )
    parser.add_argument(
        "mode",
        nargs="?",
        choices=("joint", "design", "stateful"),
        default="joint",
        help="single normalized joint, layout-driven map, or stateful block demonstration",
    )
    parser.add_argument("--shape", choices=("cylinder", "barrel", "hourglass"),
                        default="cylinder", help="joint radial profile")
    parser.add_argument("--mid-radius", type=float,
                        help="mid-height radius in the model's length unit")
    parser.add_argument("--package", action="store_true",
                        help="include conformal underfill, UBM, and pad regions (Tet4)")
    parser.add_argument("--joint-map",
                        help="schema-v1 joints.csv for design/stateful modes; defaults to case sibling")
    args = parser.parse_args(argv)
    if args.mode == "stateful":
        result = critical_joint_bvp_screening(joint_map_path=args.joint_map)
        print("Design-linked stateful 3D solder-block demonstration")
        print(
            f"  joint {result['joint_id']} from {result['joint_source']}; "
            f"L_D/h={result['ldnp_over_h']:.3f}"
        )
        print(
            f"  {result['n_elem']} Hex8; dW peak/mean="
            f"{result['peak_to_mean']:.3f}; max Newton iterations="
            f"{result['max_iterations']}"
        )
        print(
            f"  calibration-specific Syed screening value: "
            f"{result['Nf_screen_peak']:,.0f} cycles"
        )
        print("  scope: idealized demonstration, not crack-location or package-life validation")
        return
    if args.mode == "design":
        _run_design(args.shape, args.mid_radius, args.package, args.joint_map)
        return
    # JEDEC JESD22-A104 swing + a representative flip-chip joint (normalized lengths)
    dalpha = 14.4e-6                       # |alpha_substrate - alpha_die|
    dT = 165.0                             # -40 .. +125 C
    L_D = 5.0                              # distance to neutral point (joint pitch x count)
    R, h = 0.5, 0.4                        # solder joint radius, height
    du = dalpha * dT * L_D                 # DNP differential displacement on the joint
    gamma_dnp = du / h                     # textbook DNP shear strain
    if args.package:
        R_mid = args.mid_radius
        if R_mid is None:
            R_mid = R * {"cylinder": 1.0, "barrel": 1.15, "hourglass": 0.85}[args.shape]
        U, M, _info = solve_solder_package_joint(du, R_pad=R, R_mid=R_mid, h_joint=h)
        if M["shape"] != args.shape:
            raise ValueError(f"--shape {args.shape!r} conflicts with --mid-radius {R_mid:g}")
        elems_for_strain = M["regions"]["solder"]
        eps = tet_element_strain(M["coords"], elems_for_strain, U)
        from .mesh3d import min_signed_tet_volume
        mesh_quality = min_signed_tet_volume(M["coords"], M["tets"])
        element_name = "Tet4"
    else:
        U, M = solve_solder_joint(du, R=R, h=h, joint_shape=args.shape,
                                  R_mid=args.mid_radius)
        elems_for_strain = M["elems"]
        eps = element_strain(M["coords"], elems_for_strain, U)
        mesh_quality = min_signed_jacobian(M["coords"], M["elems"])
        element_name = "Hex8"
    gamma_fe = float(np.median(2.0 * np.abs(eps[:, 0, 2])))     # FE engineering shear (median)
    eps_eq = float(np.percentile(_equiv(eps), 95))             # near-peak equivalent strain
    print("3D solder global-local screening demonstration (elastic FE -> material-point Anand -> Syed mapping)")
    print(f"  JEDEC dT={dT} K, dalpha={dalpha:.1e}, L_D={L_D}, "
          f"joint={M['shape']} R_pad={M['R_pad']} R_mid={M['R_mid']} h={h} | "
          f"{len(M['elems'])} {element_name}, min quality {mesh_quality:.1e}")
    print(f"  imposed DNP shift du={du:.4f} -> FE shear gamma={gamma_fe:.4f} vs du/h={gamma_dnp:.4f} "
          f"(rel {abs(gamma_fe-gamma_dnp)/gamma_dnp:.2e})")
    # Drive the checked SAC305 Anand material-point cycle with an FE-resolved strain range.
    dalpha_eff = eps_eq / dT                                    # equiv-strain range -> eff CTE
    cyc = thermal_cycle(SAC305, Tlo=-40.0, Thi=125.0, dalpha=dalpha_eff, ncyc=6)
    dW = cyc["dW_stab"]; Nf = 1.0 / (SYED_W * max(dW, 1e-30))
    print(f"  FE 95th-percentile equiv-strain {eps_eq:.4f} -> Anand dW/cycle = {dW:.4f} MPa")
    print(f"  Syed energy life N_f = 1/(W'*dW) = {Nf:,.0f} cycles  "
          f"(W'={SYED_W}/MPa; calibration-specific, one in-sample ±2x anchor)")
    if args.package:
        print("  conformal package geometry drives the checked Anand->Syed component chain; region")
        print("     properties are representative sensitivity inputs, not a qualified package deck.")
    else:
        print("  a gmsh 3D solder joint drives the checked Anand->Syed component chain.")


if __name__ == "__main__":
    main()
