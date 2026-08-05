"""Regression tests for retained, solver-derived TSV field evidence."""

from __future__ import annotations

import json
import math
from pathlib import Path
import re
import subprocess
import sys

import numpy as np
import pytest

from eda_multiphysics import tsv_stress
from eda_multiphysics.source_identity import APPROVED_COUPFE_REVISION
from examples.tsv_axisymmetric_field import run as field_runner


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "tsv_axisymmetric_field"


@pytest.fixture(scope="module")
def small_result():
    return tsv_stress.solve_tsv_field(30.0, -400.0, R_out_um=300.0, n=82)


@pytest.fixture(scope="module")
def fixed_result():
    return tsv_stress.solve_tsv_field(30.0, -400.0, R_out_um=300.0, n=2400)


def test_structured_solver_calls_real_coupfe_newton(monkeypatch):
    import coupfe

    actual_newton = coupfe.newton_solve
    calls = []

    def tracking_newton(operators, U0, state, ndof, dirichlet, **kwargs):
        calls.append((operators, ndof, dirichlet, kwargs))
        return actual_newton(operators, U0, state, ndof, dirichlet, **kwargs)

    monkeypatch.setattr(coupfe, "newton_solve", tracking_newton)
    result = tsv_stress.solve_tsv_field(30.0, -400.0, R_out_um=300.0, n=40)
    assert len(calls) == 1
    operators, ndof, dirichlet, kwargs = calls[0]
    assert len(operators) == 1
    assert isinstance(operators[0], tsv_stress.AxisymThermoelastic)
    assert ndof == result.degrees_of_freedom
    assert dirichlet == {0: 0.0}
    assert kwargs == {"rtol": 1e-9, "maxit": 60}


def test_structured_field_shapes_regions_and_residuals_are_finite(small_result):
    result = small_result
    mesh = result.mesh
    assert mesh.connectivity.shape == (mesh.element_count, 2)
    assert result.node_displacement_m.shape == (mesh.node_count,)
    assert result.element_sigma_rr_pa.shape == (mesh.element_count,)
    assert result.element_sigma_theta_pa.shape == (mesh.element_count,)
    assert result.region_by_element.shape == (mesh.element_count,)
    assert set(result.regions) == {"copper", "silicon"}
    assert sum(indices.size for indices in result.regions.values()) == mesh.element_count
    assert np.array_equal(mesh.connectivity[:, 0], np.arange(mesh.element_count))
    assert np.array_equal(mesh.connectivity[:, 1], np.arange(1, mesh.node_count))
    for array in (
        mesh.radius_nodes_m,
        mesh.element_centers_m,
        result.node_displacement_m,
        result.element_sigma_rr_pa,
        result.element_sigma_theta_pa,
    ):
        assert np.all(np.isfinite(array))
    telemetry = result.telemetry
    assert telemetry.converged is True
    assert telemetry.newton_iterations >= 1
    assert math.isfinite(telemetry.initial_free_residual_norm_n_per_m)
    assert math.isfinite(telemetry.final_free_residual_norm_n_per_m)
    assert 0.0 <= telemetry.residual_fraction_of_acceptance_limit < 1.0


def test_sigma_theta_is_recovered_from_the_solved_displacement(small_result):
    result = small_result
    centers = result.mesh.element_centers_m
    silicon = result.regions["silicon"]
    element = int(silicon[np.argmin(abs(centers[silicon] - 20.0e-6))])
    r1, r2 = result.mesh.radius_nodes_m[element:element + 2]
    u1, u2 = result.node_displacement_m[element:element + 2]
    E, nu, alpha = tsv_stress.SI["E"], tsv_stress.SI["nu"], tsv_stress.SI["a"]
    lam = E * nu / ((1.0 + nu) * (1.0 - 2.0 * nu))
    mu = E / (2.0 * (1.0 + nu))
    eps_rr = (u2 - u1) / (r2 - r1)
    eps_theta = 0.5 * (u1 + u2) / (0.5 * (r1 + r2))
    thermal = (3.0 * lam + 2.0 * mu) * alpha * result.delta_temperature_k
    expected = lam * (eps_rr + eps_theta) + 2.0 * mu * eps_theta - thermal
    assert result.element_sigma_theta_pa[element] == pytest.approx(
        expected, rel=1e-13, abs=1e-5
    )
    assert result.element_sigma_theta_pa[element] != pytest.approx(
        result.element_sigma_rr_pa[element], rel=1e-3
    )


def test_old_tuple_api_remains_numerically_compatible(small_result):
    legacy = tsv_stress.solve_tsv(
        30.0, -400.0, R_out_um=300.0, n=82
    )
    assert isinstance(legacy, tuple)
    assert len(legacy) == 4
    radius, centers, sigma_rr, via_radius = legacy
    np.testing.assert_allclose(radius, small_result.mesh.radius_nodes_m, rtol=0.0, atol=0.0)
    np.testing.assert_allclose(
        centers, small_result.mesh.element_centers_m, rtol=0.0, atol=0.0
    )
    np.testing.assert_allclose(
        sigma_rr, small_result.element_sigma_rr_pa, rtol=1e-13, atol=1e-5
    )
    assert via_radius == small_result.mesh.via_radius_m


def test_fixed_default_matches_retained_oracle_and_published_lame(fixed_result):
    oracle = json.loads((EXAMPLE / "expected_results.json").read_text(encoding="utf-8"))
    assert oracle["case_id"] == field_runner.CASE_ID
    assert oracle["claim_boundary"] == field_runner.CLAIM_BOUNDARY
    expected = oracle["expected"]
    tolerance = oracle["tolerances"]["relative_numeric"]
    result = fixed_result
    assert result.mesh.node_count == 2400
    assert result.mesh.element_count == 2399
    assert result.degrees_of_freedom == 2400
    rr20 = tsv_stress.sigma_at(
        result.mesh.element_centers_m, result.element_sigma_rr_pa, 20.0
    ) / 1e6
    lame20 = tsv_stress.lame_sigma_r(20.0, 30.0, -400.0) / 1e6
    silicon_rr = result.element_sigma_rr_pa[result.regions["silicon"]] / 1e6
    actual = {
        "sigma_rr_at_20um_MPa": rr20,
        "lame_sigma_rr_at_20um_MPa": lame20,
        "max_abs_displacement_nm": np.max(np.abs(result.node_displacement_m)) * 1e9,
        "silicon_sigma_rr_min_MPa": np.min(silicon_rr),
        "silicon_sigma_rr_max_MPa": np.max(silicon_rr),
    }
    for key, value in actual.items():
        assert float(value) == pytest.approx(expected[key], rel=tolerance, abs=1e-10)
    relative_error = abs(rr20 - lame20) / abs(lame20)
    assert relative_error < oracle["tolerances"]["lame_relative_error_max"]
    assert relative_error == pytest.approx(0.0006333590779226087, rel=1e-8)


def test_runner_retains_nine_actual_static_fields_and_honest_artifacts(
    tmp_path, monkeypatch
):
    import coupfe

    actual_newton = coupfe.newton_solve
    calls = []

    def tracking_newton(operators, U0, state, ndof, dirichlet, **kwargs):
        calls.append((operators[0].dT, ndof))
        return actual_newton(operators, U0, state, ndof, dirichlet, **kwargs)

    monkeypatch.setattr(coupfe, "newton_solve", tracking_newton)
    summary = field_runner.run_evidence_case(tmp_path, mesh_points=82)
    assert sorted(path.name for path in tmp_path.iterdir()) == [
        "contour.svg",
        "field.json",
        "summary.json",
    ]
    assert len(calls) == 9
    assert [call[0] for call in calls] == list(field_runner.LOADS_K)
    assert [call[1] for call in calls] == [82] * 9

    def reject_constant(value):
        raise AssertionError(f"non-finite JSON constant: {value}")

    field = json.loads(
        (tmp_path / "field.json").read_text(encoding="utf-8"),
        parse_constant=reject_constant,
    )
    retained_summary = json.loads(
        (tmp_path / "summary.json").read_text(encoding="utf-8"),
        parse_constant=reject_constant,
    )
    assert retained_summary == summary
    assert summary["case_id"] == field_runner.CASE_ID
    assert summary["claim_boundary"] == field_runner.CLAIM_BOUNDARY
    assert field["case_id"] == field_runner.CASE_ID
    assert field["claim_boundary"] == field_runner.CLAIM_BOUNDARY
    assert set(summary) == {
        "schema_version",
        "case_id",
        "claim_boundary",
        "provenance",
        "inputs",
        "units",
        "mesh",
        "solver",
        "results",
        "comparison",
        "load_sweep",
    }
    assert set(field) == {
        "schema_version",
        "case_id",
        "claim_boundary",
        "units",
        "inputs",
        "topology",
        "mesh",
        "final_field",
        "solver",
        "comparison",
        "load_sweep",
    }
    assert field["topology"] == {
        "type": "Line2",
        "spatial_dimension": 1,
        "dof_per_node": 1,
    }
    steps = field["load_sweep"]["steps"]
    assert field["load_sweep"]["is_transient"] is False
    assert field["load_sweep"]["sweep_kind"] == (
        "independent_static_prescribed_load_cases"
    )
    assert [step["step_index"] for step in steps] == list(range(9))
    assert [step["delta_temperature_K"] for step in steps] == list(
        field_runner.LOADS_K
    )
    assert all(step["solve_kind"] == "independent_static_coupfe_solve" for step in steps)
    assert all(step["is_transient"] is False for step in steps)
    assert all(step["solver"]["converged"] is True for step in steps)
    assert all(
        step["solver"]["residual_fraction_of_acceptance_limit"] < 1.0
        for step in steps
    )
    node_count = summary["mesh"]["nodes"]
    element_count = summary["mesh"]["elements"]
    for step in steps:
        assert len(step["field"]["radial_displacement_nm"]) == node_count
        assert len(step["field"]["sigma_rr_MPa"]) == element_count
        assert len(step["field"]["sigma_theta_MPa"]) == element_count
    assert steps[0]["comparison"]["relative_error"] is None
    assert np.count_nonzero(steps[0]["field"]["radial_displacement_nm"]) == 0
    assert field["final_field"]["radial_displacement_nm"] == steps[-1]["field"][
        "radial_displacement_nm"
    ]
    assert field["final_field"]["sigma_rr_MPa"] == steps[-1]["field"]["sigma_rr_MPa"]
    assert field["final_field"]["sigma_theta_MPa"] == steps[-1]["field"][
        "sigma_theta_MPa"
    ]
    assert re.fullmatch(r"[0-9a-f]{40}", summary["provenance"]["eda_revision"])
    assert summary["provenance"]["core_revision"] == APPROVED_COUPFE_REVISION
    assert summary["provenance"]["command"][-1] == "<OUTPUT_DIR>"
    assert "artifact" not in summary

    wording = " ".join(
        [
            json.dumps(field),
            (tmp_path / "contour.svg").read_text(encoding="utf-8"),
            (EXAMPLE / "README.md").read_text(encoding="utf-8"),
        ]
    ).lower()
    assert "axisymmetric reconstruction" in wording
    assert "not 3-d" in wording
    assert "not a transient" in wording or "not transient" in wording
    forbidden_keys = {"timing", "duration", "wall_seconds", "elapsed_seconds"}

    def keys(value):
        if isinstance(value, dict):
            for key, child in value.items():
                yield key
                yield from keys(child)
        elif isinstance(value, list):
            for child in value:
                yield from keys(child)

    assert forbidden_keys.isdisjoint(keys(field))


def test_runner_cli_has_only_the_required_output_option():
    completed = subprocess.run(
        [sys.executable, str(EXAMPLE / "run.py"), "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0
    assert "--output-dir" in completed.stdout
    assert "--mesh" not in completed.stdout
    assert "--check" not in completed.stdout


def test_serialization_and_output_paths_fail_closed(tmp_path):
    with pytest.raises(FloatingPointError, match="non-finite"):
        field_runner._json_text({"bad": float("nan")})
    output = tmp_path / "output"
    output.mkdir()
    target = tmp_path / "outside.json"
    target.write_text("do not replace", encoding="utf-8")
    (output / "field.json").symlink_to(target)
    with pytest.raises(ValueError, match="symbolic link"):
        field_runner.run_evidence_case(output, mesh_points=82)
    assert target.read_text(encoding="utf-8") == "do not replace"
