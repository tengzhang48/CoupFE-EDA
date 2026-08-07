"""Regression coverage for reviewed integration and CLI defects."""

from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest


@pytest.mark.parametrize(
    "example",
    [
        "solder_plane_cycle",
        "etv_partitioned_cycle",
        "solder_3d_cycle",
        "design_linked_solder_screening",
    ],
)
def test_guided_stateful_example_matches_retained_oracle(example):
    """The public runner must execute read-only and accept its retained result."""
    repository = Path(__file__).resolve().parents[1]
    runner = repository / "examples" / example / "run.py"
    before = {
        path.relative_to(runner.parent): (path.stat().st_size, path.stat().st_mtime_ns)
        for path in runner.parent.iterdir()
        if path.is_file()
    }
    process = subprocess.run(
        [sys.executable, str(runner), "--check"],
        cwd=repository,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert process.returncode == 0, process.stderr or process.stdout
    record = json.loads(process.stdout)
    verification = record.get("verification", record.get("check"))
    assert verification["passed"] is True
    if example in {"solder_3d_cycle", "design_linked_solder_screening"}:
        field = np.asarray(record["results"]["dW_element_MPa"], dtype=float)
        assert len(field) == record["configuration"]["n_elements"]
        assert np.all(np.isfinite(field))
        assert np.all(field >= 0.0)
        assert float(np.max(field)) == pytest.approx(
            record["results"]["dW_peak_MPa"], rel=1.0e-10, abs=1.0e-12
        )
        assert float(np.mean(field)) == pytest.approx(
            record["results"]["dW_mean_MPa"], rel=1.0e-10, abs=1.0e-12
        )
    if example == "etv_partitioned_cycle":
        mesh = record["inputs"]["mesh"]
        assert mesh["nodes"] == 9
        assert mesh["elements"] == 4
        assert mesh["top_element_indices"] == [2, 3]
        for model in ("quasisteady", "lumped_transient"):
            result = record["results"]["fast_cycle"][model]
            retained = result["last_cycle"]
            assert retained["step"] == list(range(9))
            assert retained["phase_fraction"] == pytest.approx(
                np.linspace(0.0, 1.0, 9)
            )
            assert len(retained["displacement_m"]) == 9
            assert np.asarray(retained["displacement_m"]).shape == (9, 18)
            assert np.asarray(retained["increment_dW_element_MPa"]).shape == (
                9,
                4,
            )
            field = np.asarray(retained["dW_element_MPa"], dtype=float)
            assert field.shape == (4,)
            assert float(np.mean(field[mesh["top_element_indices"]])) == pytest.approx(
                result["dW_last_MPa"], rel=1.0e-10, abs=1.0e-12
            )
            peak_index = retained["peak_temperature_state_index"]
            assert retained["local_temperature_C"][peak_index] == pytest.approx(
                result["temperature_C_max"]
            )
        quasisteady_states = record["results"]["fast_cycle"]["quasisteady"][
            "last_cycle"
        ]
        transient_states = record["results"]["fast_cycle"]["lumped_transient"][
            "last_cycle"
        ]
        assert transient_states["phase_fraction"] == quasisteady_states["phase_fraction"]
        assert (
            transient_states["chamber_temperature_C"]
            == quasisteady_states["chamber_temperature_C"]
        )
    after = {
        path.relative_to(runner.parent): (path.stat().st_size, path.stat().st_mtime_ns)
        for path in runner.parent.iterdir()
        if path.is_file()
    }
    assert after == before


def test_scaling_harness_retains_bound_run_and_rejects_bad_machine_record(
    tmp_path, monkeypatch
):
    """Scaling records must preserve launch metadata and fail on ambiguous output."""
    from types import SimpleNamespace

    from eda_multiphysics import scaling_bench

    commands = []
    launch_kwargs = []

    def completed(command, **kwargs):
        commands.append(command)
        launch_kwargs.append(kwargs)
        return SimpleNamespace(
            returncode=0,
            stdout="solver output\nSCALEFS 18 4 0.1250 7\n",
            stderr="rank binding recorded\n",
        )

    monkeypatch.setattr(scaling_bench.subprocess, "run", completed)
    run_directory = tmp_path / "runs"
    run_directory.mkdir()
    record = scaling_bench.run_one(
        2,
        4,
        1,
        run_directory,
        open_mpi=True,
        bind_cores=True,
        cpu_list="32-35",
    )
    assert record["status"] == "passed"
    assert record["observed"] == {
        "ndof": 18,
        "ranks": 4,
        "wall_seconds": 0.125,
        "last_ksp_iterations": 7,
    }
    assert commands[0][:4] == [
        "mpirun",
        "--rankfile",
        str(run_directory / "rank-0004-repeat-001.rankfile.txt"),
        "--report-bindings",
    ]
    assert (run_directory / "rank-0004-repeat-001.rankfile.txt").read_text() == (
        "rank 0=localhost slot=32\n"
        "rank 1=localhost slot=33\n"
        "rank 2=localhost slot=34\n"
        "rank 3=localhost slot=35\n"
    )
    assert record["command"][:4] == [
        "mpirun",
        "--rankfile",
        "runs/rank-0004-repeat-001.rankfile.txt",
        "--report-bindings",
    ]
    assert record["rankfile"]["path"] == "runs/rank-0004-repeat-001.rankfile.txt"
    assert (run_directory / "rank-0004-repeat-001.stdout.txt").is_file()
    assert (run_directory / "rank-0004-repeat-001.stderr.txt").is_file()
    for key in scaling_bench._FORCED_SINGLE_THREAD_KEYS:
        assert launch_kwargs[0]["env"][key] == "1"
    scrubbed = scaling_bench._redact(
        f"{Path.home()} {scaling_bench.platform.node()} ACCESS_TOKEN=example-secret"
    )
    assert str(Path.home()) not in scrubbed
    if scaling_bench.platform.node():
        assert scaling_bench.platform.node() not in scrubbed
    assert "example-secret" not in scrubbed

    with pytest.raises(ValueError, match="exactly one SCALEFS"):
        scaling_bench._parse_scalefs(
            "SCALEFS 18 4 0.1 7\nSCALEFS 18 4 0.2 7\n", 18, 4
        )
    with pytest.raises(ValueError, match="does not match expected"):
        scaling_bench._parse_scalefs("SCALEFS 20 4 0.1 7\n", 18, 4)
    with pytest.raises(ValueError, match="does not match requested"):
        scaling_bench._parse_scalefs("SCALEFS 18 2 0.1 7\n", 18, 4)
    with pytest.raises(scaling_bench.argparse.ArgumentTypeError, match="ascending order"):
        scaling_bench._rank_list("4,2")
    assert scaling_bench._cpu_list("32-35,40") == "32-35,40"
    assert scaling_bench._cpu_list_size("32-35,40") == 5
    assert scaling_bench._expand_cpu_list("32-35,40") == [32, 33, 34, 35, 40]
    with pytest.raises(scaling_bench.argparse.ArgumentTypeError, match="ascending"):
        scaling_bench._cpu_list("35-32")

    def failed(_command, **_kwargs):
        return SimpleNamespace(returncode=9, stdout="partial output\n", stderr="failure\n")

    monkeypatch.setattr(scaling_bench.subprocess, "run", failed)
    with pytest.raises(scaling_bench.BenchmarkRunError, match="status 9") as error:
        scaling_bench.run_one(2, 1, 2, run_directory)
    assert error.value.record["status"] == "failed"
    assert (run_directory / "rank-0001-repeat-002.stdout.txt").read_text() == (
        "partial output\n"
    )
    assert (run_directory / "rank-0001-repeat-002.stderr.txt").read_text() == "failure\n"


def test_scaling_manifest_matches_harness_and_json_is_strict():
    """The public benchmark schema and release JSON parser fail closed."""
    import importlib.util

    from eda_multiphysics import scaling_bench

    repository = Path(__file__).resolve().parents[1]
    manifest = json.loads(
        (repository / "benchmarks/solver_scaling/manifest.json").read_text()
    )
    assert manifest["driver"]["module"] == scaling_bench.DRIVER_MODULE
    assert manifest["metric"]["name"] == (
        "driver_reported_synchronized_max_rank_solve_wall_seconds"
    )
    assert manifest["solver_configuration"] == scaling_bench.SOLVER_CONFIGURATION
    assert manifest["driver"]["machine_record_fields"][-1] == (
        "last_ksp_iterations"
    )

    guard_path = repository / ".github/scripts/check_release_artifacts.py"
    spec = importlib.util.spec_from_file_location("release_guard_for_test", guard_path)
    guard = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(guard)
    artifact = Path("test-artifact")
    with pytest.raises(SystemExit, match="duplicate object key"):
        guard._validate_text("duplicate.json", b'{"key": 1, "key": 2}', artifact)
    with pytest.raises(SystemExit, match="non-finite JSON"):
        guard._validate_text("nonfinite.json", b'{"key": NaN}', artifact)
    sensitive_samples = [
        "github_pat_" + "A" * 30,
        "sk-" + "A" * 30,
        "AKIA" + "A" * 16,
        "Authorization: Bearer " + "A" * 30,
        "-----BEGIN OPENSSH " + "PRIVATE KEY-----",
    ]
    for index, sample in enumerate(sensitive_samples):
        with pytest.raises(SystemExit, match="credential material"):
            guard._validate_text(
                f"credential-{index}.txt", sample.encode(), artifact
            )


def test_current_scaling_bundle_is_complete_and_self_consistent():
    """The published local sweep must retain and bind every accepted launch."""
    from eda_multiphysics import scaling_bench

    repository = Path(__file__).resolve().parents[1]
    bundle = (
        repository
        / "benchmarks"
        / "solver_scaling"
        / "current_526338dof_20260801"
    )
    summary = json.loads((bundle / "summary.json").read_text())
    provenance = json.loads((bundle / "provenance.json").read_text())
    assert summary["status"] == "complete"
    assert summary["error"] is None
    assert summary["configuration"]["rank_order"] == [1, 2, 4, 8]
    assert summary["configuration"]["repeats_per_rank"] == 3
    assert len(summary["runs"]) == 12
    assert provenance["coupfe_eda"] == {
        "commit": "5d34894e05b597baba3dcffaad0b2f097b2f7117",
        "dirty": False,
    }
    assert provenance["coupfe_core"] == {
        "commit": "454f73ce2de284262b214a2b37bd676c6aca3c0a",
        "dirty": False,
    }

    for record in summary["runs"]:
        assert record["status"] == "passed"
        assert record["returncode"] == 0
        assert record["timed_out"] is False
        ranks = record["requested_ranks"]
        for stream in ("rankfile", "stdout", "stderr"):
            metadata = record[stream]
            data = (bundle / metadata["path"]).read_bytes()
            assert len(data) == metadata["bytes"]
            assert hashlib.sha256(data).hexdigest() == metadata["sha256"]
        rankfile = (bundle / record["rankfile"]["path"]).read_text().splitlines()
        assert rankfile == [
            f"rank {rank}=localhost slot={48 + rank}" for rank in range(ranks)
        ]
        stdout = (bundle / record["stdout"]["path"]).read_text()
        assert stdout.count("SCALEFS ") == 1
        assert scaling_bench._parse_scalefs(stdout, 526338, ranks) == record["observed"]

    expected_table = scaling_bench.markdown_table(
        summary["runs"], summary["configuration"]["rank_order"]
    )
    assert (bundle / "table.md").read_text() == expected_table + "\n"


def test_solver_side_design_feedback_preserves_current_and_improves_case():
    """The bounded design-loop case must compare at the same delivered current."""
    from eda_multiphysics.design_loop_demo import compare_design

    result = compare_design(nx=20, ny=4)
    assert result["delivered_current_relative_difference"] < 1.0e-12
    assert result["reinforced"]["peak_temperature"] < result["baseline"][
        "peak_temperature"
    ]
    assert result["reinforced"]["voltage_drop"] < result["baseline"][
        "voltage_drop"
    ]
    assert result["improved"] is True
    assert "no live EDA database" in result["scope"]


def test_repaired_stateful_fe_demonstrations_meet_residual_rule_and_report_scope():
    """Retained cycle/BVP examples must meet the residual rule before output."""
    from eda_multiphysics import anand_3d, etv_fe, reliability_3d, solder_joint

    plane = solder_joint.solder_joint_cycle(
        nx=2, ny=2, ncyc=1, steps_per_cyc=8
    )
    assert plane["dW_last"] == pytest.approx(0.3510639484, rel=1.0e-5)
    assert "top-layer Gauss-point mean" in plane["dW_aggregation"]
    assert plane["max_residual_fraction_of_limit"] < 1.0

    etv = etv_fe.thermoviscoplastic_cycle(
        temperature_model="lumped_transient",
        nx=2,
        ny=2,
        ncyc=1,
        steps_per_cyc=8,
    )
    assert etv["dW_last"] == pytest.approx(0.5446577390, rel=1.0e-5)
    assert "top-layer Gauss-point mean" in etv["dW_aggregation"]
    assert etv["inelastic_heat_fraction"] == pytest.approx(1.0)
    assert etv["max_residual_fraction_of_limit"] < 1.0

    bvp = anand_3d.solder_joint_bvp_3d()
    assert bvp["dW_peak"] == pytest.approx(0.3890213548, rel=1.0e-5)
    assert bvp["peak_to_mean"] == pytest.approx(1.1329701222, rel=1.0e-5)
    assert bvp["max_residual_fraction_of_limit"] < 1.0

    assert hasattr(anand_3d, "prescribed_hex8_cycle")
    assert hasattr(reliability_3d, "critical_joint_bvp_screening")


def test_stateful_increment_commits_once_and_fails_closed():
    """A converged increment commits once; a rejected increment commits nothing."""
    from coupfe.operators.base import Residual, Tangent

    from eda_multiphysics._stateful_solve import solve_stateful_increment

    class LinearOperator:
        ndof = 1

        def __init__(self, *, constant_residual=False):
            self.commits = 0
            self.constant_residual = constant_residual

        def residual(self, U, state, t, dt):
            value = 1.0 if self.constant_residual else float(U[0] - 1.0)
            return Residual(gdofs=np.array([0]), values=np.array([value]))

        def tangent(self, U, state, t, dt):
            return Tangent(
                rows=np.array([0]),
                cols=np.array([0]),
                values=np.array([1.0]),
            )

        def commit(self, U, state, t, dt):
            self.commits += 1
            return state

    convergent = LinearOperator()
    U, info = solve_stateful_increment(convergent, np.zeros(1), {})
    assert U[0] == pytest.approx(1.0)
    assert info["residual_fraction_of_limit"] < 1.0
    assert convergent.commits == 1

    rejected = LinearOperator(constant_residual=True)
    with pytest.raises(RuntimeError, match="material state was not committed"):
        solve_stateful_increment(rejected, np.zeros(1), {}, maxit=2)
    assert rejected.commits == 0


@pytest.mark.parametrize(
    "operator_kind,seeds",
    [("quad4-plane-strain", (1, 2, 3)), ("hex8-3d", (4, 5, 6))],
)
def test_stateful_tangent_matches_residual_direction_without_mutation(
    operator_kind, seeds
):
    """The assembled numerical tangent matches a separate residual derivative."""
    from eda_multiphysics.anand_3d import AnandHex8, SAC305_3D, StructuredHexMesh
    from eda_multiphysics.fe import StructuredQuadMesh
    from eda_multiphysics.solder_joint import AnandPlaneStrain, SNPB

    if operator_kind == "quad4-plane-strain":
        op = AnandPlaneStrain(StructuredQuadMesh(2, 2, 1.0e-4, 1.0e-4), SNPB)
    else:
        op = AnandHex8(
            StructuredHexMesh(1, 1, 1, 1.0e-4, 1.0e-4, 1.0e-4), SAC305_3D
        )
    op.T = 350.0
    op.dt = 100.0

    preload_seed, trial_seed, direction_seed = seeds
    preload = np.random.default_rng(preload_seed).normal(
        scale=1.0e-7, size=op.ndof
    )
    op.commit(preload, None, 1.0, op.dt)
    assert np.linalg.norm(op.epp) > 0.0

    U = preload + np.random.default_rng(trial_seed).normal(
        scale=5.0e-8, size=op.ndof
    )
    direction = np.random.default_rng(direction_seed).normal(size=op.ndof)
    direction /= np.linalg.norm(direction)
    committed = (op.epp.copy(), op.s.copy(), op.dW.copy())

    tangent = op.tangent(U, None, 1.0, op.dt)
    K = np.zeros((op.ndof, op.ndof))
    np.add.at(K, (tangent.rows, tangent.cols), tangent.values)

    def residual_vector(displacement):
        contribution = op.residual(displacement, None, 1.0, op.dt)
        result = np.zeros(op.ndof)
        np.add.at(result, contribution.gdofs, contribution.values)
        return result

    h = 1.0e-9
    derivative = (
        residual_vector(U + h * direction) - residual_vector(U - h * direction)
    ) / (2.0 * h)
    relative_error = np.linalg.norm(K @ direction - derivative) / max(
        np.linalg.norm(derivative), 1.0e-30
    )
    assert relative_error < 1.0e-4

    np.testing.assert_array_equal(op.epp, committed[0])
    np.testing.assert_array_equal(op.s, committed[1])
    np.testing.assert_array_equal(op.dW, committed[2])


def test_stateful_bvp_screening_preserves_design_identity():
    """The repaired stateful block keeps the selected design object and scope."""
    from eda_multiphysics.reliability_3d import (
        SYED_W,
        critical_joint_bvp_screening,
        design_joints,
    )

    joints = design_joints()
    critical = int(np.argmax(joints["dnp"]))
    result = critical_joint_bvp_screening(
        nx=2, ny=2, nz=2, ncyc=1, steps_per_cyc=4
    )
    assert result["joint_id"] == str(joints["joint_ids"][critical])
    assert result["source_object_id"] == str(
        joints["source_object_ids"][critical]
    )
    assert result["net"] == str(joints["nets"][critical])
    assert result["coordinate_frame"] == joints["coordinate_frame"]
    assert result["joint_geometry_fidelity"] == joints["geometry_fidelity"]
    assert result["joint_map_path"] == joints["path"]
    maximum = float(np.max(joints["dnp"]))
    tied = np.flatnonzero(
        np.isclose(joints["dnp"], maximum, rtol=1.0e-12, atol=1.0e-12)
    )
    assert result["maximum_dnp_tie_count"] == len(tied)
    assert result["maximum_dnp_tied_joint_ids"] == [
        str(joints["joint_ids"][index]) for index in tied
    ]
    assert "first tied object" in result["critical_joint_selection_policy"]
    assert result["L_D"] == pytest.approx(float(joints["dnp"][critical]))
    assert result["ldnp_over_h"] == pytest.approx(result["L_D"] / 50.0)
    assert result["screening_height_um"] == pytest.approx(50.0)
    assert result["Nf_screen_peak"] == pytest.approx(
        1.0 / (SYED_W * result["dW_peak"])
    )
    assert result["max_residual_fraction_of_limit"] < 1.0


def test_time_integrators_reject_failed_or_incomplete_solutions(monkeypatch):
    """Do not consume partial SciPy histories as completed material-point results."""
    from types import SimpleNamespace

    from eda_multiphysics import anand, creep, etv_solder

    def failed_solver(_rhs, interval, *_args, **_kwargs):
        return SimpleNamespace(
            success=False,
            message="forced regression failure",
            t=np.asarray(interval, dtype=float),
            y=np.empty((0, 2)),
        )

    monkeypatch.setattr(anand, "solve_ivp", failed_solver)
    with pytest.raises(RuntimeError, match="uniaxial Anand integration"):
        anand.integrate_uniaxial(1e-3, 298.15, anand.SNPB)
    with pytest.raises(RuntimeError, match="Anand thermal-cycle integration"):
        anand.thermal_cycle(anand.SNPB, ncyc=1)

    monkeypatch.setattr(etv_solder, "solve_ivp", failed_solver)
    with pytest.raises(RuntimeError, match="electro-thermo-viscoplastic"):
        etv_solder.etv_cycle(coupled=False, ncyc=1)

    monkeypatch.setattr(creep, "solve_ivp", failed_solver)
    with pytest.raises(RuntimeError, match="stress-controlled creep"):
        creep.integrate_creep(0.0, 298.15, t_max=1.0)

    truncated = SimpleNamespace(
        success=True,
        message="terminal event",
        t=np.array([0.0, 0.5]),
    )
    with pytest.raises(RuntimeError, match="requested final time"):
        anand._require_complete_ivp(truncated, 1.0, "truncated integration")
    empty = SimpleNamespace(success=True, message="empty", t=np.array([]))
    with pytest.raises(RuntimeError, match="last_time=None"):
        anand._require_complete_ivp(empty, 1.0, "empty integration")


def test_iterative_solvers_fail_closed_on_exhaustion(monkeypatch):
    """Checked iterative wrappers must not return an unconverged last iterate."""
    import scipy.sparse as sp
    import coupfe

    from eda_multiphysics._coupled_solve import coupled_newton
    from eda_multiphysics.electrothermal import solve_electrothermal
    from eda_multiphysics.etv_solder import solve_et
    from eda_multiphysics.fe import StructuredQuadMesh

    monkeypatch.setattr(
        coupfe,
        "assemble_residual",
        lambda *_args, **_kwargs: (np.array([1.0]), None),
    )
    monkeypatch.setattr(
        coupfe,
        "assemble_tangent",
        lambda *_args, **_kwargs: sp.eye(1, format="csr"),
    )
    with pytest.raises(RuntimeError, match="coupled Newton solve did not converge"):
        coupled_newton(
            [],
            1,
            {},
            lambda _K, _R, _rows: (np.array([1.0]), {}),
            maxit=1,
        )

    mesh = StructuredQuadMesh(2, 1, 1.0, 0.2)
    with pytest.raises(RuntimeError, match="Picard iteration did not converge"):
        solve_electrothermal(
            mesh,
            sigma0=1.0,
            alpha=0.1,
            k=1.0,
            Tsink=0.0,
            V0=1.0,
            tol=0.0,
            maxit=1,
        )

    voltage_bc = {
        **{int(node): 0.0 for node in mesh.left()},
        **{int(node): 1.0 for node in mesh.right()},
    }
    temperature_bc = {
        **{int(node): 0.0 for node in mesh.left()},
        **{int(node): 0.0 for node in mesh.right()},
    }
    with pytest.raises(RuntimeError, match="Picard iteration did not converge"):
        solve_et(
            mesh,
            voltage_bc,
            sigma0=1.0,
            alpha_sig=0.1,
            k=1.0,
            T_bc=temperature_bc,
            tol=0.0,
            maxit=1,
        )


def _write_joint_map(tmp_path, rows, **metadata_overrides):
    csv_path = tmp_path / "joints.csv"
    csv_path.write_text(
        "joint_id,x,y,z,diameter,height,net,source_object_id\n" + "\n".join(rows) + "\n"
    )
    metadata = {
        "schema_version": 1,
        "coordinate_unit": "mm",
        "dimension_unit": "mm",
        "coordinate_frame": "package",
        "source": "test_export",
        "geometry_fidelity": "design_export",
        "transform_to_die_um": {
            "matrix": [[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]],
            "offset_um": [10.0, 20.0, 30.0],
        },
    }
    metadata.update(metadata_overrides)
    (tmp_path / "joints.meta.json").write_text(json.dumps(metadata))
    return csv_path


def test_joint_map_normalizes_units_and_applies_affine_transform(tmp_path):
    from eda_multiphysics.joint_map import load_joint_map

    path = _write_joint_map(
        tmp_path,
        ["J1,0.001,0.002,0.003,0.0005,0.0004,VDD,BUMP_A"],
        neutral_point_um=[8.0, 21.0, 33.0],
    )
    joints = load_joint_map(path)
    assert joints.ids == ("J1",)
    assert np.allclose(joints.xyz_um[0], [8.0, 21.0, 33.0])
    assert joints.diameter_um[0] == pytest.approx(0.5)
    assert joints.height_um[0] == pytest.approx(0.4)
    assert joints.nets == ("VDD",)
    assert joints.source_object_ids == ("BUMP_A",)
    assert joints.geometry_fidelity == "design_export"
    assert joints.dnp_um[0] == pytest.approx(0.0)


def test_joint_map_rejects_duplicate_stable_ids(tmp_path):
    from eda_multiphysics.joint_map import load_joint_map

    path = _write_joint_map(tmp_path, ["J1,0,0,0,,,,", "J1,1,1,0,,,,"])
    with pytest.raises(ValueError, match="duplicate joint_id"):
        load_joint_map(path)
    path = _write_joint_map(
        tmp_path,
        ["J1,0,0,0,,,,"],
        transform_to_die_um={
            "matrix": [[1.0, 0.0, 0.0], [0.0, 0.0, 0.0], [0.0, 0.0, 1.0]],
            "offset_um": [0.0, 0.0, 0.0],
        },
    )
    with pytest.raises(ValueError, match="must be nonsingular"):
        load_joint_map(path)
    path = _write_joint_map(
        tmp_path,
        ["J1,0,0,0,,,,"],
        geometry_fidelity="universal",
    )
    with pytest.raises(ValueError, match="geometry_fidelity must be one of"):
        load_joint_map(path)


def test_design_joints_prefers_explicit_map(tmp_path):
    from eda_multiphysics.reliability_3d import design_joints

    path = _write_joint_map(tmp_path, ["EXPLICIT_1,0,0,0,,,,BUMP_1"])
    joints = design_joints(tmp_path / "absent.sp", joint_map_path=path)
    assert joints["explicit"] is True
    assert joints["source"] == "test_export"
    assert joints["joint_ids"].tolist() == ["EXPLICIT_1"]


def test_design_joints_labels_pdn_fallback(tmp_path):
    from eda_multiphysics.reliability_3d import design_joints

    spice = tmp_path / "pdn.sp"
    spice.write_text("R1 VDD_0_0_1 VDD_2000_0_1 1.0\n")
    (tmp_path / "manifest.json").write_text(json.dumps({"dbu_per_micron": 2000}))
    joints = design_joints(spice)
    assert joints["explicit"] is False
    assert joints["source"] == "pdn_node_proxy_fallback"
    assert joints["joint_ids"].tolist() == ["PDN_PROXY_0000", "PDN_PROXY_0001"]


def test_bundled_synthetic_joint_map_is_an_explicit_labeled_proxy():
    from eda_multiphysics.reliability_3d import design_joints

    joints = design_joints()
    assert len(joints["xy"]) == 9
    assert len(set(joints["joint_ids"])) == 9
    assert joints["explicit"] is True
    assert joints["source"] == "project_authored_synthetic_joint_map"
    assert joints["geometry_fidelity"] == "proxy"
    assert np.allclose(np.ptp(joints["xy"], axis=0), [60.0, 60.0], atol=1e-12)
    assert np.isclose(joints["dnp"].max(), np.sqrt(1800.0), atol=1e-12)


def test_design_grid_reads_dbu_from_case_manifest():
    from eda_multiphysics.reliability_3d import design_grid

    xy, _center, dnp = design_grid()
    assert np.allclose(np.ptp(xy, axis=0), [60.0, 60.0], atol=1e-12)
    assert np.isclose(dnp.max(), np.sqrt(1800.0), atol=1e-12)


def test_design_grid_requires_units_for_standalone_netlist(tmp_path):
    from eda_multiphysics.reliability_3d import design_grid

    spice = tmp_path / "pdn.sp"
    spice.write_text("R1 VDD_0_0_1 VDD_2000_0_1 1.0\n")
    with pytest.raises(ValueError, match="pass dbu_per_um explicitly"):
        design_grid(spice)
    xy, _center, _dnp = design_grid(spice, dbu_per_um=2000)
    assert np.allclose(np.ptp(xy, axis=0), [1.0, 0.0])


def test_bundled_case_power_is_explicitly_synthetic_and_balanced(tmp_path):
    from eda_multiphysics.reliability_pipeline import (
        DEFAULT_CASE,
        _case_total_power,
        _case_voltage_reference,
        run as run_pipeline,
    )

    power = _case_total_power(DEFAULT_CASE)
    assert power["total_power_W"] == pytest.approx(8.9982e-3)
    assert power["provenance"] == "project_authored_synthetic_scenario"
    assert power["instance_power_model"] == "closed_form_dc_load_power"
    assert power["power_by_id"]["SYNTH_U11"] == pytest.approx(1.0e-3)
    assert power["power_by_id"]["SYNTH_U00"] == pytest.approx(0.99975e-3)

    result = run_pipeline(nx=4, ncyc=2, verbose=False)
    assert result["electrothermal_power_mode"] == "pdn_iv"
    assert result["release_validation"] is False
    assert result["analysis_role"] == "synthetic_integration_demonstration"
    assert result["source_power_coupled_W"] == pytest.approx(9.0e-3, abs=1e-12)
    assert result["thermal_power_coupled_W"] == pytest.approx(9.0e-3, abs=1e-12)
    assert abs(result["power_balance_error_W"]) < 1e-12

    default_spice = Path(DEFAULT_CASE) / "pdn_vdd.sp"
    reference = _case_voltage_reference(DEFAULT_CASE, 1.0, default_spice)
    assert reference["source"] == "closed_form_symmetric_resistor_grid"
    alternate_spice = tmp_path / "alternate.sp"
    alternate_spice.write_text(default_spice.read_text() + "* changed netlist identity\n")
    assert _case_voltage_reference(DEFAULT_CASE, 1.0, alternate_spice) is None
    alternate_result = run_pipeline(
        spice=alternate_spice, nx=4, ncyc=2, verbose=False
    )
    assert alternate_result["ir_reference"] is None
    assert alternate_result["electrothermal_power_mode"] == "fixed_instance"
    assert "No direct composed-case oracle" in alternate_result["claim_boundary"]


def test_em_screen_uses_upstream_temperature():
    from eda_multiphysics.reliability_3d import DEFAULT_SPICE
    from eda_multiphysics.reliability_pipeline import _em_screen_pdn

    ambient = _em_screen_pdn(DEFAULT_SPICE, 298.15, T_ref=298.15)
    hot = _em_screen_pdn(DEFAULT_SPICE, 348.15, T_ref=298.15)
    assert ambient["temp_acceleration"] == pytest.approx(1.0)
    assert hot["temp_acceleration"] > ambient["temp_acceleration"]
    assert hot["relative_lifetime"] < ambient["relative_lifetime"]


def test_tet_element_strain_reproduces_affine_field():
    from eda_multiphysics.reliability_3d import tet_element_strain

    coords = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0],
                       [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
    tets = np.array([[0, 1, 2, 3]])
    grad_u = np.array([[0.10, 0.02, -0.03],
                       [0.04, -0.05, 0.01],
                       [0.00, 0.06, 0.08]])
    U = np.zeros((4, 4))
    U[:, :3] = coords @ grad_u.T
    strain = tet_element_strain(coords, tets, U.ravel())[0]
    assert np.allclose(strain, 0.5 * (grad_u + grad_u.T), atol=1e-14)


def test_chip_vtu_has_one_entry_guard_and_two_intentional_regimes(monkeypatch):
    import eda_multiphysics.chip_vtu as chip_vtu

    tree = ast.parse(Path(chip_vtu.__file__).read_text())
    entry_guards = [
        node for node in tree.body
        if isinstance(node, ast.If) and "__name__" in ast.unparse(node.test)
        and "__main__" in ast.unparse(node.test)
    ]
    assert len(entry_guards) == 1

    calls = []
    monkeypatch.setattr(chip_vtu, "run", lambda *args, **kwargs: calls.append((args, kwargs)))
    chip_vtu.main(["case", "pdn.sp", "0.005"])
    assert len(calls) == 2
    assert {call[1]["t_si"] for call in calls} == {100e-6, 20e-6}


@pytest.mark.parametrize("module_name", [
    "eda_multiphysics.chip_vtu",
    "eda_multiphysics.electrothermal_chip",
    "eda_multiphysics.pdn_graph",
])
def test_required_argument_clis_report_usage(module_name, capsys):
    module = __import__(module_name, fromlist=["main"])
    with pytest.raises(SystemExit) as exc:
        module.main([])
    assert exc.value.code == 2
    assert "usage:" in capsys.readouterr().err


def test_case_thermal_defaults_to_synthetic_case_without_writing(monkeypatch):
    import eda_multiphysics.case_thermal as case_thermal

    calls = []
    monkeypatch.setattr(case_thermal, "run", lambda *args, **kwargs: calls.append((args, kwargs)))
    case_thermal.main([])
    assert calls == [((case_thermal.DEFAULT_CASE, None),
                      {"output_path": None, "power_provenance": None})]


def test_case_thermal_writes_power_metadata(tmp_path):
    from eda_multiphysics.case_thermal import DEFAULT_CASE, run

    output = tmp_path / "instance_temperature.csv"
    run(DEFAULT_CASE, 1e-5, output_path=output, power_provenance="test_scenario")
    metadata = json.loads((tmp_path / "instance_temperature.meta.json").read_text())
    assert metadata["total_power_W"] == pytest.approx(1e-5)
    assert metadata["total_power_provenance"] == "test_scenario"
    assert metadata["instance_power_model"] == "area_distributed_proxy"
    assert metadata["release_validation"] is False
    assert metadata["analysis_role"] == "integration_demonstration"
    assert "not real-device thermal validation or signoff" in metadata["claim_boundary"]
    assert metadata["source_case"] == str(Path(DEFAULT_CASE).resolve())
    assert metadata["thermal_boundary_condition"] == {
        "type": "dirichlet",
        "field": "temperature_rise",
        "boundary": "all_die_edges",
        "value_K": 0.0,
    }
    assert metadata["mesh_size"] == {
        "element_type": "Quad4",
        "nx": 72,
        "ny": 72,
        "n_elements": 72 * 72,
        "n_nodes": 73 * 73,
    }
    assert metadata["k_si_W_per_m_K"] == pytest.approx(148.0)
    assert metadata["thickness_m"] == pytest.approx(100e-6)
    assert output.exists()
