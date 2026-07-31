"""Optional regression tier for the 3D, thermo-mechanical, and reliability toolchain.

These tests exercise the public interfaces described in ``docs/api.md`` and the
scoped checks in ``docs/VALIDATION_GUIDE.md``. They are guarded by
gmsh/petsc4py/gfortran availability and run via ``pytest -m toolchain``,
separate from the default numpy/scipy suite.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys

import numpy as np
import pytest

pytestmark = pytest.mark.toolchain


def _mpirun_cmd(*, oversubscribe=False):
    """Portable mpirun prefix; Open MPI needs --oversubscribe, MPICH does not support it."""
    cmd = ["mpirun"]
    if oversubscribe:
        try:
            ver = subprocess.run(["mpirun", "--version"], capture_output=True, text=True,
                                 timeout=10).stdout
        except Exception:  # pragma: no cover - environment-specific
            ver = ""
        if "Open MPI" in ver:
            cmd.append("--oversubscribe")
    return cmd


# ---------------------------------------------------------------------------
# etv_3d
# ---------------------------------------------------------------------------
def test_etv_3d_self_heating(etv_workdir):
    from eda_multiphysics.etv_3d import solve

    U, ndof, its = solve(16, (3.0, 0.0, 1.5), workdir=etv_workdir)
    peak = float(U[1::2].max())
    exact = 3.0 * 2.0 ** 2 / (8.0 * 1.5)
    rel_err = abs(peak - exact) / exact
    assert rel_err < 2e-3, f"peak dT {peak} vs exact {exact}, rel {rel_err:.2e}"


# ---------------------------------------------------------------------------
# tsv_3d
# ---------------------------------------------------------------------------
def test_tsv_3d_solid_cylinder(etv_workdir):
    from eda_multiphysics.tsv_3d import solve_via

    R = L = 1.0
    sigma0 = 3.0
    k = 1.5
    V = 2.0
    U, M, ndof, its, mj = solve_via(0.18, R=R, L=L, sigma0=sigma0, k=k, V=V, workdir=etv_workdir)
    T = U[1::2]
    peak = float(T.max())
    peak_ref = sigma0 * V ** 2 * R ** 2 / (4.0 * k * L ** 2)
    rel_err = abs(peak - peak_ref) / peak_ref
    assert mj > 0.0, f"mesh has non-positive min Jacobian {mj}"
    assert rel_err < 6e-3, f"solid via peak {peak} vs {peak_ref}, rel {rel_err:.2e}"


def test_tsv_3d_annular_via(etv_workdir):
    from eda_multiphysics.tsv_3d import solve_annular_via

    a, b, L = 0.5, 1.0, 1.0
    sigma0 = 3.0
    k_core, k_ann = 3.0, 1.0
    V = 2.0
    U, M, ndof, its, mj = solve_annular_via(
        0.18, a=a, b=b, L=L, sigma0=sigma0, k_core=k_core, k_ann=k_ann, V=V, workdir=etv_workdir
    )
    T = U[1::2]
    peak = float(T.max())
    q = sigma0 * (V / L) ** 2
    peak_ref = q * a ** 2 / (4 * k_core) + q * (b ** 2 - a ** 2) / (4 * k_ann)
    rel_err = abs(peak - peak_ref) / peak_ref
    assert mj > 0.0, f"mesh has non-positive min Jacobian {mj}"
    assert rel_err < 6e-3, f"annular via peak {peak} vs {peak_ref}, rel {rel_err:.2e}"


def test_tsv_3d_layer_stack(etv_workdir):
    from eda_multiphysics.tsv_3d import oracle_stack, solve_layer_stack

    specs = [(0.3, 1.5), (0.1, 0.5), (0.2, 3.0), (0.4, 1.0)]
    T_top = 1.0
    U, M, ndof, its, mj = solve_layer_stack(specs, h=0.18, T_top=T_top, workdir=etv_workdir)
    T = U[1::2]
    Tref = oracle_stack(M["coords"], specs, T_top)
    maxabs = float(np.max(np.abs(T - Tref)))
    assert mj > 0.0, f"mesh has non-positive min Jacobian {mj}"
    assert maxabs < 1e-12, f"layer stack max|err| {maxabs:.2e}"


# ---------------------------------------------------------------------------
# thermomech_3d
# ---------------------------------------------------------------------------
def test_thermomech_3d_free_expansion(tm_kernel_module):
    from eda_multiphysics.thermomech_3d import solve_thermomech
    from eda_multiphysics.thermomech_kernel import free_expansion_lambda

    G, K, alpha = 1.0, 100.0, 1.0e-3
    props = (G, K, alpha, 0.25, 1.0)
    dT = 10.0
    mod, wd = tm_kernel_module
    U, nodes, ndof = solve_thermomech(4, dT=dT, props=props, workdir=wd)
    lam = free_expansion_lambda(dT, G=G, K=K, alpha=alpha)
    u = U.reshape(-1, 4)[:, :3]
    u_ref = (lam - 1.0) * nodes
    err = np.max(np.abs(u - u_ref)) / max(1e-30, np.max(np.abs(u_ref)))
    assert err < 1e-9, f"free-expansion error {err:.2e}"


def test_thermomech_3d_constrained_block(tm_kernel_module):
    from eda_multiphysics.thermomech_3d import solve_thermomech

    G, K, alpha = 1.0, 100.0, 1.0e-3
    props = (G, K, alpha, 0.25, 1.0)
    dT = 10.0
    mod, wd = tm_kernel_module
    U, nodes, ndof = solve_thermomech(4, dT=dT, props=props, constrained=True, workdir=wd)
    u = U.reshape(-1, 4)[:, :3]
    umax = float(np.max(np.abs(u)))
    assert umax < 1e-9, f"constrained block max|u| {umax:.2e}"


# ---------------------------------------------------------------------------
# thermomech_tsv
# ---------------------------------------------------------------------------
def test_tsv_device_submodel_geometry_regions_and_interfaces():
    from eda_multiphysics.mesh3d import tsv_device_submodel, tsv_periodic_cell
    from eda_multiphysics.tsv_local_3d import (
        DEFAULT_MATERIALS, silicon_raman_profile, solve_local_tsv,
    )

    mesh = tsv_device_submodel(
        diameter_um=2.0, via_depth_um=2.0, oxide_um=0.1,
        si_radius_um=3.0, si_depth_um=3.0, h_um=0.4, raman_depth_um=0.05,
        tsv_id="TSV_TEST", h_near_um=0.2, refine_extent_um=1.5,
    )
    assert set(mesh["regions"]) == {"copper", "oxide", "silicon"}
    assert all(len(tets) for tets in mesh["regions"].values())
    assert mesh["min_signed_tet_volume_um3"] > 0.0
    assert all(len(nodes) for nodes in mesh["interfaces"].values())
    assert len(mesh["direct_copper_silicon_nodes"]) == 0
    cup_nodes = mesh["interfaces"]["copper_oxide"]
    cup_xyz = mesh["coords"][cup_nodes]
    on_copper_tip = np.isclose(cup_xyz[:, 2], -2.0)
    assert np.any(on_copper_tip)
    assert np.min(np.hypot(cup_xyz[on_copper_tip, 0], cup_xyz[on_copper_tip, 1])) < 0.5
    assert len(mesh["top"]) and len(mesh["bottom"]) and len(mesh["outer"])
    used = np.unique(np.concatenate(list(mesh["regions"].values())))
    assert len(used) == len(mesh["coords"]), "mesh contains orphan FE nodes"
    for name, exact in mesh["exact_volumes_um3"].items():
        rel = abs(mesh["mesh_volumes_um3"][name] - exact) / exact
        assert rel < 0.03, f"{name} discretized-volume error {rel:.2%}"
    assert mesh["raman_plane_z_um"] == pytest.approx(-0.05)
    assert mesh["copper_tip_z_um"] == pytest.approx(-2.0)
    assert mesh["liner_tip_z_um"] == pytest.approx(-2.1)
    assert mesh["tsv_id"] == "TSV_TEST"
    assert mesh["release_validation"] is False
    assert mesh["coordinate_frame"]["x_axis"] == "[100]"
    assert mesh["coordinate_frame"]["y_axis"] == "[010]"
    assert mesh["mesh_refinement"] == {
        "h_near_um": 0.2, "refine_extent_um": 1.5, "source_surface_count": 2
    }

    result = solve_local_tsv(mesh, -70.0, boundary_condition="silicon_free_expansion")
    assert result.free_residual_relative < 1.0e-10
    assert result.boundary_condition == "silicon_free_expansion"
    assert result.coordinate_frame == mesh["coordinate_frame"]
    assert np.array_equal(result.crystal_to_global, np.eye(3))
    assert len(result.material_sha256) == len(result.mesh_sha256) == 64
    assert all(np.all(np.isfinite(stress)) for stress in result.element_stress_mpa.values())
    profile = silicon_raman_profile(mesh, result, [0.1, 0.3, 0.6], direction=(1.0, 1.0))
    assert np.all(profile["points_um"][:, 2] == pytest.approx(-0.05))
    assert np.all(np.isfinite(profile["raman_stress_sum_mpa"]))
    assert profile["release_validation"] is False

    periodic = tsv_periodic_cell(
        pitch_110_um=6.0, pitch_1m10_um=8.0, diameter_um=2.0, via_depth_um=2.0,
        oxide_um=0.1, si_depth_um=3.0, h_um=0.5, raman_depth_um=0.05,
        h_near_um=0.2, refine_extent_um=1.5, tsv_id="TSV_PERIODIC_TEST",
    )
    assert periodic["periodic_pairing_status"] == "matching_nodes_verified"
    assert periodic["periodic_mechanics_status"] == "not_solved"
    assert all(len(nodes) for nodes in periodic["periodic_faces"].values())
    assert len(periodic["periodic_faces"]["x_minus"]) == len(periodic["periodic_faces"]["x_plus"])
    assert len(periodic["periodic_faces"]["y_minus"]) == len(periodic["periodic_faces"]["y_plus"])
    for axis, minus, plus in (("x", "x_minus", "x_plus"), ("y", "y_minus", "y_plus")):
        record = periodic["periodic_node_pairs"][axis]
        assert len(record["master_nodes"]) == len(periodic["periodic_faces"][minus])
        assert len(record["slave_nodes"]) == len(periodic["periodic_faces"][plus])
        assert record["max_mismatch_um"] == pytest.approx(0.0, abs=1.0e-13)
        assert periodic["gmsh_periodic_interior_node_counts"][axis] == len(record["master_nodes"])
    assert len(periodic["direct_copper_silicon_nodes"]) == 0
    assert periodic["coordinate_frame"]["x_axis"] == "[110]"
    assert periodic["coordinate_frame"]["y_axis"] == "[-110]"
    assert np.linalg.det(periodic["crystal_to_global"]) == pytest.approx(1.0)
    assert np.allclose(periodic["coords"].min(axis=0), [-3.0, -4.0, -3.0])
    assert np.allclose(periodic["coords"].max(axis=0), [3.0, 4.0, 0.0])
    periodic_used = np.unique(np.concatenate(list(periodic["regions"].values())))
    assert len(periodic_used) == len(periodic["coords"])
    for name, exact in periodic["exact_volumes_um3"].items():
        rel = abs(periodic["mesh_volumes_um3"][name] - exact) / exact
        assert rel < 0.03, f"periodic {name} discretized-volume error {rel:.2%}"

    # Periodic mechanics patch: make all three geometric regions the SAME cubic Si
    # material. The compatible free-expansion box jump must reproduce the affine
    # field and machine-zero stress. This catches units, jump sign, P/P.T, corners,
    # and element state/assembly together.
    dT = -70.0
    alpha_si = DEFAULT_MATERIALS["silicon"]["alpha_per_K"]
    H_free = alpha_si * dT * np.eye(3)
    homogeneous_si = {
        name: dict(DEFAULT_MATERIALS["silicon"])
        for name in ("copper", "oxide", "silicon")
    }
    free_periodic = solve_local_tsv(
        periodic, dT, materials=homogeneous_si,
        boundary_condition="periodic_macro_gradient", macro_gradient=H_free,
    )
    origin_m = np.asarray(periodic["periodic_box"]["origin_um"]) * 1.0e-6
    affine_reference = (periodic["coords"] * 1.0e-6 - origin_m) @ H_free.T
    assert np.max(np.abs(free_periodic.displacement_m - affine_reference)) < 1.0e-18
    assert max(np.max(np.abs(stress)) for stress in free_periodic.element_stress_mpa.values()) < 1e-8
    assert free_periodic.free_residual_relative < 1.0e-10
    assert free_periodic.constraint_error_max < 1.0e-18
    assert len(free_periodic.constraint_sha256) == 64
    assert np.array_equal(free_periodic.macro_gradient, H_free)
    assert free_periodic.periodic_pair_mismatch_m == pytest.approx(0.0, abs=1.0e-18)
    assert free_periodic.reduced_dofs < 3 * len(periodic["coords"])

    # Broken physical control: zero macro jump fixes the in-plane box during
    # cooling and must develop a clearly nonzero constrained thermal stress.
    fixed_box = solve_local_tsv(
        periodic, dT, materials=homogeneous_si,
        boundary_condition="periodic_macro_gradient", macro_gradient=np.zeros((3, 3)),
    )
    assert max(np.max(np.abs(stress)) for stress in fixed_box.element_stress_mpa.values()) > 1.0

    # Heterogeneous Cu/oxide/anisotropic-Si integration smoke. This checks
    # assembly/conservation at this case; it is not a Raman comparison or an
    # accepted macro boundary condition.
    periodic_result = solve_local_tsv(
        periodic, dT, boundary_condition="periodic_macro_gradient", macro_gradient=H_free,
    )
    assert periodic_result.free_residual_relative < 1.0e-10
    assert periodic_result.constraint_error_max < 1.0e-18
    assert all(np.all(np.isfinite(stress)) for stress in periodic_result.element_stress_mpa.values())
    assert periodic_result.release_validation is False


def test_thermomech_tsv_fieldsplit_vs_direct(tm_kernel_module):
    from eda_multiphysics.thermomech_tsv import (
        composite_ur,
        profile_error,
        solve_tsv_thermal_stress,
    )

    mod, wd = tm_kernel_module
    a, b, L, dT = 0.5, 1.0, 0.25, 100.0
    CU = (47.0, 137.0, 17.0e-6)
    SI = (66.0, 98.0, 2.6e-6)

    Ud, Md, *_ = solve_tsv_thermal_stress(
        0.18, a=a, b=b, L=L, mc=CU, ma=SI, dT=dT, mod=mod, solver="direct"
    )
    Uf, Mf, ndof, n_newton, ksp_its, mj, *_ = solve_tsv_thermal_stress(
        0.18, a=a, b=b, L=L, mc=CU, ma=SI, dT=dT, mod=mod, solver="fieldsplit"
    )

    # agreement between direct and fieldsplit
    rel_agree = float(np.linalg.norm(Ud - Uf) / max(1e-30, np.linalg.norm(Ud)))
    assert rel_agree < 1e-6, f"direct/fieldsplit disagreement {rel_agree:.2e}"

    # Keep the FieldSplit iteration count within the checked bound when the
    # displacement near-null-space is supplied.
    assert ksp_its < 40, f"fieldsplit KSP iterations {ksp_its} not < 40"

    # profile error vs composite-cylinder oracle
    coords = Mf["coords"]
    u = Uf.reshape(-1, 4)[:, :3]
    r = np.hypot(coords[:, 0], coords[:, 1])
    ur = (coords[:, 0] * u[:, 0] + coords[:, 1] * u[:, 1]) / np.maximum(r, 1e-30)
    ur_ref = composite_ur(r, a, b, CU, SI, dT)
    perr = profile_error(r, ur, ur_ref)
    assert perr < 6e-3, f"TSV radial profile error {perr:.2e}"
    assert mj > 0.0, f"mesh has non-positive min Jacobian {mj}"


# ---------------------------------------------------------------------------
# etv_distributed_fs
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("nranks", [2, 4])
def test_etv_distributed_fs_serial_matches_mpi(nranks):
    """Compare the distributed FieldSplit solve with serial SciPy at 2 and 4 ranks.

    The 4-rank case exercises interior ranks with neighbours on both sides. The
    assertion checks output agreement at one size; it is not a scaling study.
    """
    pytest.importorskip("petsc4py")
    pytest.importorskip("mpi4py")
    if not shutil.which("mpirun"):
        pytest.skip("mpirun not available")

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cmd = [
        *_mpirun_cmd(oversubscribe=True),  # Open MPI CI may need this; MPICH oversubscribes by default
        "-n",
        str(nranks),
        sys.executable,
        "-m",
        "eda_multiphysics.etv_distributed_fs",
        "24",
        "--validate",
    ]
    # If petsc4py has initialised MPI in this process, OpenMPI sets PMIx/OMPI
    # singleton variables in the C environment that are invisible to os.environ.
    # Passing env explicitly forces subprocess.run to use Python's view of the
    # environment, so mpirun does not mistake the child for a nested MPI job.
    proc = subprocess.run(
        cmd,
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=300,
        env=os.environ.copy(),
    )
    assert proc.returncode == 0, f"distributed fs (-n {nranks}) failed:\n{proc.stdout}\n{proc.stderr}"

    # Parse the 'serial==N-rank: max rel = X' line emitted by the CLI.
    match = None
    for line in proc.stdout.splitlines():
        if "serial==N-rank:" in line:
            parts = line.split("max rel =")
            if len(parts) == 2:
                match = float(parts[1].split()[0])
                break
    assert match is not None, f"did not find serial==N-rank line at -n {nranks}:\n{proc.stdout}"
    assert match < 1e-6, f"distributed(-n {nranks}) vs serial rel error {match:.2e}"


# ---------------------------------------------------------------------------
# reliability_3d
# ---------------------------------------------------------------------------
def test_solder_bump_profile_geometry():
    from eda_multiphysics.mesh3d import min_signed_jacobian, solder_bump

    for expected, r_pad, r_mid in (("barrel", 0.42, 0.50),
                                   ("hourglass", 0.50, 0.40)):
        m = solder_bump(R_pad=r_pad, R_mid=r_mid, L=0.4, h=0.18)
        used = np.unique(m["elems"])
        radial = np.hypot(m["coords"][:, 0], m["coords"][:, 1])
        assert m["shape"] == expected
        assert len(m["elems"]) > 0 and len(m["cap0"]) > 0 and len(m["capL"]) > 0
        assert len(m["lateral"]) > 0
        assert np.array_equal(used, np.arange(len(m["coords"]))), "orphan/disconnected mesh nodes"
        assert np.allclose(m["coords"][m["cap0"], 2], 0.0, atol=1e-10)
        assert np.allclose(m["coords"][m["capL"], 2], 0.4, atol=1e-10)
        assert np.isclose(radial.max(), max(r_pad, r_mid), atol=1e-8)
        assert min_signed_jacobian(m["coords"], m["elems"]) > 0.0
        assert np.isfinite(m["volume"]) and m["volume"] > 0.0


def test_solder_package_conformal_regions():
    from eda_multiphysics.mesh3d import min_signed_tet_volume, solder_package

    m = solder_package(h=0.25)
    assert m["element"] == "Tet4"
    assert set(m["regions"]) == {
        "solder", "underfill", "bottom_ubm", "top_ubm", "bottom_pad", "top_pad"
    }
    assert np.array_equal(np.unique(m["tets"]), np.arange(len(m["coords"])))
    assert min_signed_tet_volume(m["coords"], m["tets"]) > 0.0
    assert all(len(nodes) > 0 for nodes in m["interfaces"].values())
    assert np.allclose(m["coords"][m["bottom"], 2], -0.13, atol=1e-10)
    assert np.allclose(m["coords"][m["top"], 2], 0.53, atol=1e-10)
    # Exact OCC volume partition: solder + its complementary underfill shell = outer cylinder.
    outer_volume = np.pi * 0.90 ** 2 * 0.40
    assert np.isclose(m["volumes"]["solder"] + m["volumes"]["underfill"],
                      outer_volume, rtol=1e-12)
    assert np.isclose(m["volumes"]["bottom_pad"], np.pi * 0.70 ** 2 * 0.08, rtol=1e-12)
    assert np.isclose(m["volumes"]["bottom_ubm"], np.pi * 0.58 ** 2 * 0.05, rtol=1e-12)


def test_reliability_3d_solder_joint(tm_kernel_module):
    from eda_multiphysics.reliability_3d import SYED_W, element_strain, solve_solder_joint

    mod, wd = tm_kernel_module
    dalpha = 14.4e-6
    dT = 165.0
    L_D = 5.0
    R, h = 0.5, 0.4
    du = dalpha * dT * L_D
    gamma_dnp = du / h

    U, M = solve_solder_joint(du, R=R, h=h, mod=mod)
    eps = element_strain(M["coords"], M["elems"], U)
    gamma_fe = float(np.median(2.0 * np.abs(eps[:, 0, 2])))
    rel_err = abs(gamma_fe - gamma_dnp) / gamma_dnp
    assert rel_err < 0.15, f"FE shear {gamma_fe} vs DNP {gamma_dnp}, rel {rel_err:.2e}"

    eps_eq = float(np.percentile(np.sqrt(2.0 / 3.0 * np.einsum("...ij,...ij->...",
        eps - np.eye(3) * (np.trace(eps, axis1=-2, axis2=-1)[..., None, None] / 3.0),
        eps - np.eye(3) * (np.trace(eps, axis1=-2, axis2=-1)[..., None, None] / 3.0),
    )), 95))
    from eda_multiphysics.anand import thermal_cycle, SAC305
    cyc = thermal_cycle(SAC305, Tlo=-40.0, Thi=125.0, dalpha=eps_eq / dT, ncyc=6)
    dW = cyc["dW_stab"]
    Nf = 1.0 / (SYED_W * max(dW, 1e-30))
    assert np.isfinite(Nf) and Nf > 0, f"N_f not finite positive: {Nf}"


def test_reliability_3d_profile_changes_strain_field(tm_kernel_module):
    from eda_multiphysics.reliability_3d import _equiv, element_strain, solve_solder_joint

    mod, _wd = tm_kernel_module
    du = 14.4e-6 * 165.0 * 5.0
    upper_tail = {}
    for shape in ("cylinder", "hourglass"):
        U, m = solve_solder_joint(du, R=0.5, h=0.4, mesh_h=0.18, mod=mod,
                                  joint_shape=shape)
        eps_eq = _equiv(element_strain(m["coords"], m["elems"], U))
        upper_tail[shape] = float(np.percentile(eps_eq, 95))
        u = U.reshape(-1, 4)[:, :3]
        assert np.allclose(u[m["cap0"]], 0.0, atol=1e-12)
        assert np.allclose(u[m["capL"], 0], du, atol=1e-12)
    rel_change = abs(upper_tail["hourglass"] - upper_tail["cylinder"]) / upper_tail["cylinder"]
    assert rel_change > 0.02, f"joint profile changed 95th-percentile strain by only {rel_change:.2%}"


def test_solder_package_multimaterial_solve(tm_tet_kernel_module):
    from eda_multiphysics.reliability_3d import (
        _equiv,
        solve_solder_package_joint,
        tet_element_strain,
    )

    mod, _wd = tm_tet_kernel_module
    du = 0.01
    U, m, info = solve_solder_package_joint(du, mesh_h=0.25, mod=mod)
    u = U.reshape(-1, 4)[:, :3]
    assert np.allclose(u[m["bottom"]], 0.0, atol=1e-12)
    assert np.allclose(u[m["top"], 0], du, atol=1e-12)
    assert np.allclose(u[m["top"], 1:], 0.0, atol=1e-12)
    strain = tet_element_strain(m["coords"], m["regions"]["solder"], U)
    eps_eq = _equiv(strain)
    assert np.all(np.isfinite(eps_eq)) and np.percentile(eps_eq, 95) > 0.0
    assert info["ksp_its"] < 40


def test_reliability_design_map_with_package_regions(tm_tet_kernel_module):
    from eda_multiphysics.reliability_3d import from_design

    mod, _wd = tm_tet_kernel_module
    r = from_design(include_package=True, joint_shape="barrel", package_mod=mod)
    assert r["n_joints"] == 9
    assert r["joint_shape"] == "barrel"
    assert r["joint_model"] == "solder+underfill+UBM+pads"
    assert np.all(np.isfinite(r["lives"])) and np.all(r["lives"] > 0.0)
    assert r["lives"].min() < r["lives"].max()


def test_reliability_3d_design_map(tm_kernel_module):
    from eda_multiphysics.reliability_3d import from_design

    mod, wd = tm_kernel_module
    r = from_design(mod=mod)
    assert r["n_joints"] == 9, f"expected 9 joints, got {r['n_joints']}"
    extent = r["extent"]
    assert abs(extent[0] - 60.0) < 1e-12, f"die x extent {extent[0]}"
    assert abs(extent[1] - 60.0) < 1e-12, f"die y extent {extent[1]}"
    assert abs(r["L_D"] - np.sqrt(1800.0)) < 1e-12, f"critical DNP {r['L_D']}"
    assert r["lives"].min() < r["lives"].max(), "life array is constant"
    assert np.all(np.isfinite(r["lives"])), "non-finite life values"
    assert np.all(r["lives"] > 0), "non-positive life values"


# ---------------------------------------------------------------------------
# tet_3d -- native core linear tet (gmsh arbitrary-CAD meshing)
# ---------------------------------------------------------------------------
def test_tet4_patch_test(etv_workdir):
    """Check linear completeness on the selected irregular Gmsh Tet4 mesh."""
    from eda_multiphysics.tet_3d import patch_test

    err = patch_test(workdir=etv_workdir)
    assert err < 1e-11, f"tet4 patch-test max|err| {err:.2e} not < 1e-11"


def test_tet4_self_heating(etv_workdir):
    """Compare Tet4 box/cylinder self-heating with ``sigma V0^2/8k``.

    The comparison is bounded by the selected generated meshes and also checks
    that every tetrahedron has positive signed volume.
    """
    from eda_multiphysics.tet_3d import oracle_selfheat, solve_selfheat

    props = (3.0, 0.0, 1.5)
    exact = oracle_selfheat(props)
    for mesh in ("box", "cylinder"):
        peak, mv, _nn, _ne = solve_selfheat(mesh=mesh, h=0.18, props=props, workdir=etv_workdir)
        assert mv > 0.0, f"tet {mesh} mesh has non-positive min signed volume {mv}"
        rel = abs(peak - exact) / exact
        assert rel < 3e-2, f"tet {mesh} self-heat peak {peak} vs {exact}, rel {rel:.2e}"
