"""Fast numerical and provenance gates for the TSV-to-device preview foundation."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_cubic_silicon_stiffness_and_fourfold_rotation():
    from eda_multiphysics.tsv_device import cubic_stiffness_tensor, rotate_fourth_order

    C = cubic_stiffness_tensor()
    assert C[0, 0, 0, 0] == pytest.approx(166.2)
    assert C[0, 0, 1, 1] == pytest.approx(64.4)
    assert C[0, 1, 0, 1] == pytest.approx(79.8)
    R90 = np.array([[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
    assert np.allclose(rotate_fourth_order(C, R90), C, atol=1e-12)


def test_cubic_thermal_free_expansion_has_zero_stress():
    from eda_multiphysics.tsv_device import stress_from_strain

    alpha, dT = 2.3e-6, -270.0
    stress_gpa = stress_from_strain(alpha * dT * np.eye(3), alpha=alpha, dT=dT)
    assert np.max(np.abs(stress_gpa)) < 1e-14


def test_rotation_validation_fails_closed():
    from eda_multiphysics.tsv_device import cubic_stiffness_tensor, rotate_fourth_order

    with pytest.raises(ValueError, match="orthonormal"):
        rotate_fourth_order(cubic_stiffness_tensor(), np.diag([1.0, 1.0, 2.0]))
    with pytest.raises(ValueError, match=r"determinant \+1"):
        rotate_fourth_order(cubic_stiffness_tensor(), np.diag([1.0, 1.0, -1.0]))


def test_mobility_units_and_110_rotation_match_published_equations():
    from eda_multiphysics.tsv_device import mobility_change

    stress = np.array([[100.0, 20.0, 0.0], [20.0, -30.0, 0.0], [0.0, 0.0, 10.0]])
    assert mobility_change(stress, carrier="n", channel_degrees=0.0) == pytest.approx(0.11294)
    pi11, pi12, pi44 = np.array([-102.2, 53.7, -13.6]) * 1e-11
    expected_110 = -(
        0.5 * (pi11 + pi12) * (stress[0, 0] + stress[1, 1])
        + pi44 * stress[0, 1]
        + 0.5 * (pi11 + pi12 - pi44) * stress[2, 2]
    ) * 1e6
    assert mobility_change(stress, carrier="n", channel_degrees=45.0) == pytest.approx(expected_110)


def test_raman_observable_uses_in_plane_stress_sum_at_requested_field_point():
    from eda_multiphysics.tsv_device import raman_shift_cm_inv, raman_stress_sum_mpa

    stress = np.diag([55.0, 35.0, -2.0])
    assert raman_stress_sum_mpa(stress) == pytest.approx(90.0)
    assert raman_shift_cm_inv(stress) == pytest.approx(-90.0 / 470.0)


def test_device_screen_preserves_ids_coordinates_and_threshold():
    from eda_multiphysics.tsv_device import lame_far_field_stress, screen_devices

    ids = ["U1", "U2"]
    xy = np.array([[7.5, 1.0], [15.0, -2.0]])
    stress = lame_far_field_stress(xy, diameter_um=10.0, dT=-250.0)
    rows = screen_devices(ids, xy, stress, carrier=["n", "p"],
                          channel_degrees=[0.0, 45.0], tsv_id="TSV_A",
                          source_object_ids=["X1/MN0", "X1/MP0"])
    assert [row.device_id for row in rows] == ids
    assert {row.tsv_id for row in rows} == {"TSV_A"}
    assert [row.source_object_id for row in rows] == ["X1/MN0", "X1/MP0"]
    assert np.allclose([[row.x_um, row.y_um] for row in rows], xy)
    assert all(np.isfinite(row.mobility_change) for row in rows)
    with pytest.raises(ValueError, match="outside the TSV radius"):
        lame_far_field_stress([[4.9, 0.0]], diameter_um=10.0)


def test_real_dimension_device_preview_is_deterministic_and_honestly_labeled():
    from examples.tsv_00_device_screening.run import run

    expected = json.loads((ROOT / "examples/tsv_00_device_screening/expected_metrics.json").read_text())
    baseline, optimized, scorecard = run()
    assert len(baseline) == len(optimized) == expected["n_devices"]
    assert scorecard["baseline_violations"] == expected["baseline_violations"]
    assert scorecard["optimized_violations"] == expected["optimized_violations"]
    assert scorecard["baseline_peak_abs_mobility_change"] == pytest.approx(
        expected["baseline_peak_abs_mobility_change"], abs=expected["tolerance"]["absolute"]
    )
    assert scorecard["optimized_peak_abs_mobility_change"] == pytest.approx(
        expected["optimized_peak_abs_mobility_change"], abs=expected["tolerance"]["absolute"]
    )
    assert scorecard["release_validation"] is False
    assert scorecard["device_site_provenance"] == "synthetic_radial_angular_sampling"
    assert scorecard["runtime_inputs"] == ["device_sites.csv"]
    assert "threshold" in scorecard["fixed_in_code"]
    assert "does not validate" in scorecard["claim_boundary"]


def test_device_preview_writes_identity_preserving_svg(tmp_path):
    import xml.etree.ElementTree as ET

    from examples.tsv_00_device_screening.run import _write_outputs, run

    baseline, optimized, scorecard = run()
    _write_outputs(tmp_path, baseline, optimized, scorecard)
    svg = (tmp_path / "device_screening.svg").read_text()
    assert "CELL_0000 / STD_CELL_0000" in svg
    assert "Baseline [100] channels" in svg
    assert "Orientation-screening action" in svg
    ET.fromstring(svg)
    assert (tmp_path / "device_screening.csv").exists()
    assert (tmp_path / "evidence.json").exists()


def test_benchmark_manifests_hash_and_release_scorecard_fail_closed():
    from eda_multiphysics.tsv_validation import load_benchmark_manifest, load_release_scorecard

    paths = sorted((ROOT / "benchmarks").glob("tsv_*/manifest.json"))
    assert len(paths) == 4
    manifests = [load_benchmark_manifest(path) for path in paths]
    assert {manifest["calibration_role"] for manifest in manifests} == {
        "calibration", "validation", "model_verification", "external_comparison"
    }
    _raw, result = load_release_scorecard(ROOT / "benchmarks/tsv_release_scorecard.json")
    assert result == {
        "evidence_status": "declared_tsv_evidence_incomplete",
        "allowed_claim": "TSV numerical/device-screening demonstration; experimental evidence incomplete",
        "passed": 0,
        "blocked": 7,
        "failed": 0,
        "not_started": 3,
        "evidence_complete": False,
    }
