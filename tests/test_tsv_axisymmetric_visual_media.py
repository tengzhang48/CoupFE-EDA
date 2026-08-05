"""Focused tests for reproducible axisymmetric field media and provenance."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from eda_multiphysics.visual_evidence import validate_manifest
from examples.tsv_axisymmetric_field.build_visual_evidence import (
    NORMALIZED_RUNNER_COMMAND,
    _validate_summary,
    _write_json,
    construct_manifest,
)
from examples.tsv_axisymmetric_field.render_video import (
    CASE_ID,
    CLAIM_BOUNDARY,
    EXPECTED_LOADS_K,
    RenderInputError,
    frame_step_indices,
    render_video,
    renderer_configuration,
    validate_field_record,
)


def _solver():
    return {
        "newton_iterations": 1,
        "relative_tolerance": 1.0e-10,
        "absolute_residual_tolerance_N_per_m": 1.0e-12,
        "initial_free_residual_norm_N_per_m": 1.0,
        "final_free_residual_norm_N_per_m": 1.0e-12,
        "final_relative_residual": 1.0e-12,
        "residual_fraction_of_acceptance_limit": 0.01,
        "converged": True,
    }


def _comparison(delta_temperature):
    magnitude = abs(delta_temperature) * 0.75
    return {
        "reference": "published_Lame_equation",
        "query_radius_um": 20.0,
        "fe_sigma_rr_MPa": magnitude,
        "lame_sigma_rr_MPa": magnitude,
        "absolute_error_MPa": 0.0,
        "relative_error": None if delta_temperature == 0.0 else 0.0,
        "acceptance_threshold": 0.03,
        "passed": True,
    }


def _results(delta_temperature):
    scale = abs(delta_temperature) / 400.0
    return {
        "sigma_rr_at_20um_MPa": 300.0 * scale,
        "sigma_theta_at_20um_MPa": -300.0 * scale,
        "max_abs_displacement_nm": 2.0 * scale,
        "silicon_sigma_rr_min_MPa": 20.0 * scale,
        "silicon_sigma_rr_max_MPa": 320.0 * scale,
    }


def _arrays(delta_temperature):
    scale = abs(delta_temperature) / 400.0
    return {
        "radial_displacement_nm": [0.0, 0.5 * scale, scale, 0.5 * scale, 0.0],
        "sigma_rr_MPa": [80.0 * scale, 100.0 * scale, 320.0 * scale, 20.0 * scale],
        "sigma_theta_MPa": [60.0 * scale, 75.0 * scale, -320.0 * scale, -20.0 * scale],
    }


def _field():
    steps = []
    for index, delta_temperature in enumerate(EXPECTED_LOADS_K):
        steps.append(
            {
                "step_index": index,
                "delta_temperature_K": delta_temperature,
                "solve_kind": "independent_static_coupfe_solve",
                "is_transient": False,
                "solver": _solver(),
                "results": _results(delta_temperature),
                "comparison": _comparison(delta_temperature),
                "field": _arrays(delta_temperature),
            }
        )
    units = {
        "radius": "um",
        "radial_displacement": "nm",
        "stress": "MPa",
        "temperature_change": "K",
        "residual_norm": "N/m",
    }
    inputs = {
        "diameter_um": 30.0,
        "delta_temperature_K": -400.0,
        "outer_radius_um": 300.0,
        "mesh_points_requested": 5,
        "liner_nm": 0.0,
        "formulation": "axisymmetric_plane_strain",
        "load": "uniform_thermal_eigenstrain",
    }
    return {
        "schema_version": 1,
        "case_id": CASE_ID,
        "claim_boundary": CLAIM_BOUNDARY,
        "units": units,
        "inputs": inputs,
        "topology": {"type": "Line2", "spatial_dimension": 1, "dof_per_node": 1},
        "mesh": {
            "radius_nodes_um": [0.0, 7.5, 15.0, 30.0, 300.0],
            "element_centers_um": [3.75, 11.25, 22.5, 165.0],
            "connectivity": [[0, 1], [1, 2], [2, 3], [3, 4]],
            "region_by_element": ["copper", "copper", "silicon", "silicon"],
            "region_element_indices": {"copper": [0, 1], "silicon": [2, 3]},
            "via_radius_um": 15.0,
            "outer_radius_um": 300.0,
        },
        "final_field": {
            "delta_temperature_K": -400.0,
            **_arrays(-400.0),
        },
        "solver": _solver(),
        "comparison": _comparison(-400.0),
        "load_sweep": {
            "sweep_kind": "independent_static_prescribed_load_cases",
            "is_transient": False,
            "description": (
                "Nine independent static solved loads; this is not a transient simulation."
            ),
            "delta_temperature_K": list(EXPECTED_LOADS_K),
            "steps": steps,
        },
    }


def _summary(field, eda_revision="a" * 40, core_revision="b" * 40):
    return {
        "schema_version": 1,
        "case_id": CASE_ID,
        "claim_boundary": CLAIM_BOUNDARY,
        "provenance": {
            "eda_revision": eda_revision,
            "core_revision": core_revision,
            "application_module": "eda_multiphysics.tsv_stress",
            "operator": "AxisymThermoelastic",
            "solver": "coupfe.newton_solve",
            "command": list(NORMALIZED_RUNNER_COMMAND),
        },
        "inputs": field["inputs"],
        "units": field["units"],
        "mesh": {
            "topology": "Line2",
            "nodes": 5,
            "elements": 4,
            "degrees_of_freedom": 5,
            "dof_per_node": 1,
        },
        "solver": field["solver"],
        "results": field["load_sweep"]["steps"][-1]["results"],
        "comparison": field["comparison"],
        "load_sweep": {
            "steps": 9,
            "kind": "independent_static_prescribed_load_cases",
            "is_transient": False,
            "delta_temperature_K": list(EXPECTED_LOADS_K),
        },
    }


def test_exact_forward_reverse_sequence_has_no_synthesized_states():
    indices = frame_step_indices(9)
    assert indices == (0, 1, 2, 3, 4, 5, 6, 7, 8, 7, 6, 5, 4, 3, 2, 1)
    assert set(indices) == set(range(9))


def test_renderer_configuration_binds_output_and_no_temporal_interpolation():
    pytest.importorskip("PIL")
    pytest.importorskip("imageio_ffmpeg")
    configuration = renderer_configuration(_field(), frames_per_state=1)
    assert configuration["output"] == {
        "width_px": 960,
        "height_px": 540,
        "fps": 12,
        "container": "webm",
        "codec": "libvpx-vp9",
        "pixel_format": "yuv420p",
        "audio": "none",
        "bitrate": "1200k",
    }
    temporal = configuration["temporal_mapping"]
    assert temporal["interpolation"] == "none"
    assert temporal["is_transient"] is False
    assert temporal["step_indices"] == list(frame_step_indices(9))
    assert configuration["color_scale"]["fixed_across_frames"] is True
    assert configuration["axisymmetric_reconstruction"]["spatial_sampling"].startswith(
        "piecewise-linear"
    )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda field: field["load_sweep"]["steps"][2]["field"][
                "sigma_rr_MPa"
            ].pop(),
            "length mismatch",
        ),
        (
            lambda field: field["load_sweep"]["steps"][2].update(
                {"is_transient": True}
            ),
            "is_transient must be false",
        ),
        (
            lambda field: field["load_sweep"]["steps"][2]["field"][
                "sigma_rr_MPa"
            ].__setitem__(0, np.nan),
            "finite number",
        ),
        (
            lambda field: field["final_field"]["sigma_rr_MPa"].__setitem__(0, 999.0),
            "must equal the final solved sweep state",
        ),
    ],
)
def test_field_schema_rejects_broken_grain_and_semantics(mutation, message):
    field = _field()
    mutation(field)
    with pytest.raises(RenderInputError, match=message):
        validate_field_record(field)


def test_small_webm_has_fixed_metadata_and_exact_frame_count(tmp_path):
    imageio_ffmpeg = pytest.importorskip("imageio_ffmpeg")
    pytest.importorskip("PIL")
    field_path = tmp_path / "field.json"
    field_path.write_text(json.dumps(_field(), allow_nan=False), encoding="utf-8")
    output = tmp_path / "load-sweep.webm"
    configuration = render_video(field_path, output, frames_per_state=1)
    assert output.read_bytes().startswith(b"\x1aE\xdf\xa3")
    reader = imageio_ffmpeg.read_frames(output)
    try:
        metadata = next(reader)
    finally:
        reader.close()
    assert metadata["codec"] == "vp9"
    assert metadata["pix_fmt"].startswith("yuv420p")
    assert metadata["size"] == (960, 540)
    assert metadata["fps"] == pytest.approx(12.0)
    frame_count, _seconds = imageio_ffmpeg.count_frames_and_secs(output)
    assert frame_count == len(frame_step_indices(9))
    assert configuration["temporal_mapping"]["interpolation"] == "none"


def test_builder_manifest_binds_exact_four_artifacts(tmp_path):
    field = _field()
    summary = _summary(field)
    (tmp_path / "field.json").write_text(json.dumps(field), encoding="utf-8")
    (tmp_path / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    (tmp_path / "contour.svg").write_text("<svg/>", encoding="utf-8")
    (tmp_path / "load-sweep.webm").write_bytes(b"\x1aE\xdf\xa3test")
    configuration = {
        "temporal_mapping": {"interpolation": "none", "is_transient": False}
    }
    _validate_summary(
        summary,
        field,
        eda_revision="a" * 40,
        core_revision="b" * 40,
    )
    manifest = construct_manifest(
        tmp_path,
        field=field,
        summary=summary,
        eda_revision="a" * 40,
        core_revision="b" * 40,
        renderer_configuration=configuration,
    )
    manifest_path = tmp_path / "visual-evidence.json"
    _write_json(manifest_path, manifest)
    assert validate_manifest(manifest_path) == manifest
    assert {record["role"] for record in manifest["artifacts"]} == {
        "raw-field",
        "summary",
        "image",
        "video",
    }
