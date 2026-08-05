"""Render the retained TSV load sweep as a provenance-described VP9 WebM.

The renderer uses only the nine solver states present in ``field.json``.  It
holds each state, visits them in forward/reverse order, and never interpolates
between solved load states or treats the prescribed load sweep as physical time.

Optional media dependencies are deliberately not imported at module import
time.  Install them before rendering with::

    python -m pip install "Pillow>=10" "imageio-ffmpeg>=0.5"

Run::

    python examples/tsv_axisymmetric_field/render_video.py \
        field.json --output load-sweep.webm
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Any

import numpy as np


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


CASE_ID = "axisymmetric_tsv_thermoelastic_field_v1"
CLAIM_BOUNDARY = (
    "Axisymmetric plane-strain thermoelastic component verification against the "
    "declared Lamé equation. It is not a finite-depth 3-D TSV, near-surface "
    "device field, experimental validation, keep-out-zone signoff, or transient "
    "cooling simulation."
)
EXPECTED_LOADS_K = (0.0, -50.0, -100.0, -150.0, -200.0, -250.0, -300.0, -350.0, -400.0)
WIDTH = 960
HEIGHT = 540
FPS = 12
FRAMES_PER_SOLVED_STATE = 4
CROP_RADIUS_UM = 60.0
CURVE_RADIUS_MAX_UM = 80.0
PALETTE_NAME = "cividis_restrained_sequential_v1"
PALETTE_RGB = (
    (0, 32, 77),
    (40, 52, 110),
    (74, 74, 113),
    (107, 95, 112),
    (140, 116, 107),
    (173, 139, 100),
    (203, 165, 88),
    (229, 195, 76),
    (253, 231, 69),
)
_FIELD_KEYS = {
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
_SOLVER_KEYS = {
    "newton_iterations",
    "relative_tolerance",
    "absolute_residual_tolerance_N_per_m",
    "initial_free_residual_norm_N_per_m",
    "final_free_residual_norm_N_per_m",
    "final_relative_residual",
    "residual_fraction_of_acceptance_limit",
    "converged",
}
_RESULT_KEYS = {
    "sigma_rr_at_20um_MPa",
    "sigma_theta_at_20um_MPa",
    "max_abs_displacement_nm",
    "silicon_sigma_rr_min_MPa",
    "silicon_sigma_rr_max_MPa",
}
_COMPARISON_KEYS = {
    "reference",
    "query_radius_um",
    "fe_sigma_rr_MPa",
    "lame_sigma_rr_MPa",
    "absolute_error_MPa",
    "relative_error",
    "acceptance_threshold",
    "passed",
}
_NOT_TRANSIENT = re.compile(
    r"\b(?:not\s+(?:a\s+)?transient|non[-\s]?transient)\b",
    flags=re.IGNORECASE,
)


class RenderInputError(ValueError):
    """Raised when retained field evidence is unsafe or internally inconsistent."""


class MediaDependencyError(RuntimeError):
    """Raised when the optional reproducible-media dependencies are unavailable."""


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    record: dict[str, Any] = {}
    for key, value in pairs:
        if key in record:
            raise RenderInputError(f"field evidence repeats JSON key {key!r}")
        record[key] = value
    return record


def _reject_constant(value: str) -> None:
    raise RenderInputError(f"field evidence contains non-finite constant {value!r}")


def load_field(path: str | Path) -> dict[str, Any]:
    """Load strict JSON and validate the complete renderer-facing field contract."""

    field_path = Path(path)
    if field_path.is_symlink() or not field_path.is_file():
        raise RenderInputError(f"field path must be a regular non-symlink file: {path}")
    try:
        text = field_path.read_text(encoding="utf-8")
        record = json.loads(
            text,
            object_pairs_hook=_strict_object,
            parse_constant=_reject_constant,
        )
    except UnicodeDecodeError as exc:
        raise RenderInputError("field evidence must be UTF-8") from exc
    except json.JSONDecodeError as exc:
        raise RenderInputError(f"field evidence is not strict JSON: {exc}") from exc
    if not isinstance(record, dict):
        raise RenderInputError("field evidence root must be an object")
    validate_field_record(record)
    return record


def _object(value: Any, location: str, expected: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RenderInputError(f"{location} must be an object")
    keys = set(value)
    missing = sorted(expected - keys)
    extra = sorted(keys - expected)
    if missing or extra:
        raise RenderInputError(
            f"{location} key mismatch: missing={missing}, extra={extra}"
        )
    return value


def _list(value: Any, location: str, *, length: int | None = None) -> list[Any]:
    if not isinstance(value, list):
        raise RenderInputError(f"{location} must be a list")
    if length is not None and len(value) != length:
        raise RenderInputError(
            f"{location} length mismatch: expected={length}, actual={len(value)}"
        )
    return value


def _string(value: Any, location: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise RenderInputError(f"{location} must be a non-empty NUL-free string")
    return value


def _integer(value: Any, location: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise RenderInputError(f"{location} must be an integer >= {minimum}")
    return value


def _number(value: Any, location: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RenderInputError(f"{location} must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise RenderInputError(f"{location} must be a finite number")
    return number


def _numeric_array(
    value: Any,
    location: str,
    *,
    length: int,
) -> np.ndarray:
    items = _list(value, location, length=length)
    numbers = np.asarray(
        [
            _number(item, f"{location}[{index}]")
            for index, item in enumerate(items)
        ]
    )
    if numbers.ndim != 1 or not np.all(np.isfinite(numbers)):
        raise RenderInputError(f"{location} must be one finite one-dimensional array")
    return numbers


def _validate_solver(value: Any, location: str) -> None:
    solver = _object(value, location, _SOLVER_KEYS)
    _integer(solver["newton_iterations"], f"{location}.newton_iterations")
    for key in _SOLVER_KEYS - {"newton_iterations", "converged"}:
        number = _number(solver[key], f"{location}.{key}")
        if number < 0.0:
            raise RenderInputError(f"{location}.{key} must be nonnegative")
    if solver["converged"] is not True:
        raise RenderInputError(f"{location}.converged must be true")


def _validate_results(value: Any, location: str) -> None:
    results = _object(value, location, _RESULT_KEYS)
    for key in _RESULT_KEYS:
        _number(results[key], f"{location}.{key}")


def _validate_comparison(value: Any, location: str, delta_temperature: float) -> None:
    comparison = _object(value, location, _COMPARISON_KEYS)
    if comparison["reference"] != "published_Lame_equation":
        raise RenderInputError(
            f"{location}.reference must equal 'published_Lame_equation'"
        )
    for key in _COMPARISON_KEYS - {"reference", "relative_error", "passed"}:
        number = _number(comparison[key], f"{location}.{key}")
        if key in {"absolute_error_MPa", "acceptance_threshold"} and number < 0.0:
            raise RenderInputError(f"{location}.{key} must be nonnegative")
    relative_error = comparison["relative_error"]
    if delta_temperature == 0.0:
        if relative_error is not None:
            raise RenderInputError(
                f"{location}.relative_error must be null for the zero-load state"
            )
    else:
        if _number(relative_error, f"{location}.relative_error") < 0.0:
            raise RenderInputError(f"{location}.relative_error must be nonnegative")
    if comparison["passed"] is not True:
        raise RenderInputError(f"{location}.passed must be true")


def _validate_field_arrays(
    value: Any,
    location: str,
    *,
    node_count: int,
    element_count: int,
) -> dict[str, np.ndarray]:
    field = _object(
        value,
        location,
        {"radial_displacement_nm", "sigma_rr_MPa", "sigma_theta_MPa"},
    )
    return {
        "radial_displacement_nm": _numeric_array(
            field["radial_displacement_nm"],
            f"{location}.radial_displacement_nm",
            length=node_count,
        ),
        "sigma_rr_MPa": _numeric_array(
            field["sigma_rr_MPa"],
            f"{location}.sigma_rr_MPa",
            length=element_count,
        ),
        "sigma_theta_MPa": _numeric_array(
            field["sigma_theta_MPa"],
            f"{location}.sigma_theta_MPa",
            length=element_count,
        ),
    }


def validate_field_record(record: dict[str, Any]) -> None:
    """Fail closed unless ``record`` matches the fixed nine-solve field schema."""

    root = _object(record, "field", _FIELD_KEYS)
    if root["schema_version"] != 1 or isinstance(root["schema_version"], bool):
        raise RenderInputError("field.schema_version must equal 1")
    if root["case_id"] != CASE_ID:
        raise RenderInputError(f"field.case_id must equal {CASE_ID!r}")
    if root["claim_boundary"] != CLAIM_BOUNDARY:
        raise RenderInputError("field.claim_boundary differs from the reviewed boundary")

    units = _object(
        root["units"],
        "field.units",
        {"radius", "radial_displacement", "stress", "temperature_change", "residual_norm"},
    )
    expected_units = {
        "radius": "um",
        "radial_displacement": "nm",
        "stress": "MPa",
        "temperature_change": "K",
        "residual_norm": "N/m",
    }
    if units != expected_units:
        raise RenderInputError(f"field.units must equal {expected_units!r}")

    inputs = _object(
        root["inputs"],
        "field.inputs",
        {
            "diameter_um",
            "delta_temperature_K",
            "outer_radius_um",
            "mesh_points_requested",
            "liner_nm",
            "formulation",
            "load",
        },
    )
    diameter = _number(inputs["diameter_um"], "field.inputs.diameter_um")
    final_delta = _number(
        inputs["delta_temperature_K"], "field.inputs.delta_temperature_K"
    )
    outer_radius = _number(
        inputs["outer_radius_um"], "field.inputs.outer_radius_um"
    )
    _integer(inputs["mesh_points_requested"], "field.inputs.mesh_points_requested", minimum=2)
    liner = _number(inputs["liner_nm"], "field.inputs.liner_nm")
    if diameter <= 0.0 or outer_radius <= diameter / 2.0 or liner != 0.0:
        raise RenderInputError("field.inputs geometry must describe the unlined positive TSV case")
    if final_delta != EXPECTED_LOADS_K[-1]:
        raise RenderInputError("field.inputs.delta_temperature_K must equal -400 K")
    if inputs["formulation"] != "axisymmetric_plane_strain":
        raise RenderInputError("field.inputs.formulation is not the reviewed formulation")
    if inputs["load"] != "uniform_thermal_eigenstrain":
        raise RenderInputError("field.inputs.load is not the reviewed load")

    topology = _object(
        root["topology"],
        "field.topology",
        {"type", "spatial_dimension", "dof_per_node"},
    )
    if topology != {"type": "Line2", "spatial_dimension": 1, "dof_per_node": 1}:
        raise RenderInputError("field.topology must be scalar-DOF one-dimensional Line2")

    mesh = _object(
        root["mesh"],
        "field.mesh",
        {
            "radius_nodes_um",
            "element_centers_um",
            "connectivity",
            "region_by_element",
            "region_element_indices",
            "via_radius_um",
            "outer_radius_um",
        },
    )
    radius_items = _list(mesh["radius_nodes_um"], "field.mesh.radius_nodes_um")
    if len(radius_items) < 2:
        raise RenderInputError("field.mesh.radius_nodes_um needs at least two nodes")
    node_count = len(radius_items)
    element_count = node_count - 1
    radius = _numeric_array(
        radius_items,
        "field.mesh.radius_nodes_um",
        length=node_count,
    )
    centers = _numeric_array(
        mesh["element_centers_um"],
        "field.mesh.element_centers_um",
        length=element_count,
    )
    if radius[0] != 0.0 or not np.all(np.diff(radius) > 0.0):
        raise RenderInputError("field.mesh.radius_nodes_um must start at zero and increase")
    if not np.allclose(centers, 0.5 * (radius[:-1] + radius[1:]), rtol=0.0, atol=1e-10):
        raise RenderInputError("field.mesh.element_centers_um must be Line2 midpoints")

    via_radius = _number(mesh["via_radius_um"], "field.mesh.via_radius_um")
    mesh_outer = _number(mesh["outer_radius_um"], "field.mesh.outer_radius_um")
    if not math.isclose(via_radius, diameter / 2.0, rel_tol=0.0, abs_tol=1e-12):
        raise RenderInputError("field.mesh.via_radius_um disagrees with diameter_um")
    if not math.isclose(mesh_outer, outer_radius, rel_tol=0.0, abs_tol=1e-12):
        raise RenderInputError("field.mesh.outer_radius_um disagrees with inputs")
    if not math.isclose(radius[-1], mesh_outer, rel_tol=0.0, abs_tol=1e-10):
        raise RenderInputError("field.mesh radius endpoint disagrees with outer radius")
    if not np.any(np.isclose(radius, via_radius, rtol=0.0, atol=1e-10)):
        raise RenderInputError("field.mesh must contain an interface node at the via radius")

    connectivity = _list(
        mesh["connectivity"], "field.mesh.connectivity", length=element_count
    )
    for index, pair in enumerate(connectivity):
        if (
            not isinstance(pair, list)
            or len(pair) != 2
            or any(isinstance(item, bool) or not isinstance(item, int) for item in pair)
            or pair != [index, index + 1]
        ):
            raise RenderInputError(
                f"field.mesh.connectivity[{index}] must equal [{index}, {index + 1}]"
            )

    regions = _list(
        mesh["region_by_element"],
        "field.mesh.region_by_element",
        length=element_count,
    )
    if any(region not in {"copper", "silicon"} for region in regions):
        raise RenderInputError("field.mesh.region_by_element has an unsupported region")
    expected_regions = ["copper" if center < via_radius else "silicon" for center in centers]
    if regions != expected_regions:
        raise RenderInputError("field.mesh region labels disagree with the via interface")

    region_indices = _object(
        mesh["region_element_indices"],
        "field.mesh.region_element_indices",
        {"copper", "silicon"},
    )
    claimed: list[int] = []
    for name in ("copper", "silicon"):
        indices = _list(
            region_indices[name], f"field.mesh.region_element_indices.{name}"
        )
        for position, index in enumerate(indices):
            _integer(
                index,
                f"field.mesh.region_element_indices.{name}[{position}]",
            )
            if index >= element_count or regions[index] != name:
                raise RenderInputError(
                    f"field.mesh.region_element_indices.{name} is inconsistent"
                )
        claimed.extend(indices)
    if Counter(claimed) != Counter(range(element_count)):
        raise RenderInputError("field.mesh region indices must cover each element once")

    final_field = _object(
        root["final_field"],
        "field.final_field",
        {"delta_temperature_K", "radial_displacement_nm", "sigma_rr_MPa", "sigma_theta_MPa"},
    )
    if _number(
        final_field["delta_temperature_K"], "field.final_field.delta_temperature_K"
    ) != final_delta:
        raise RenderInputError("field.final_field has the wrong prescribed load")
    final_arrays = _validate_field_arrays(
        {
            key: final_field[key]
            for key in ("radial_displacement_nm", "sigma_rr_MPa", "sigma_theta_MPa")
        },
        "field.final_field",
        node_count=node_count,
        element_count=element_count,
    )
    _validate_solver(root["solver"], "field.solver")
    _validate_comparison(root["comparison"], "field.comparison", final_delta)

    sweep = _object(
        root["load_sweep"],
        "field.load_sweep",
        {"sweep_kind", "is_transient", "description", "delta_temperature_K", "steps"},
    )
    if sweep["sweep_kind"] != "independent_static_prescribed_load_cases":
        raise RenderInputError("field.load_sweep.sweep_kind is not the reviewed sweep")
    if sweep["is_transient"] is not False:
        raise RenderInputError("field.load_sweep.is_transient must be false")
    description = _string(sweep["description"], "field.load_sweep.description")
    if _NOT_TRANSIENT.search(description) is None:
        raise RenderInputError("field.load_sweep.description must say it is not transient")
    loads = _numeric_array(
        sweep["delta_temperature_K"],
        "field.load_sweep.delta_temperature_K",
        length=len(EXPECTED_LOADS_K),
    )
    if not np.array_equal(loads, np.asarray(EXPECTED_LOADS_K)):
        raise RenderInputError("field.load_sweep must contain the reviewed nine loads")

    steps = _list(
        sweep["steps"], "field.load_sweep.steps", length=len(EXPECTED_LOADS_K)
    )
    last_arrays: dict[str, np.ndarray] | None = None
    for position, value in enumerate(steps):
        location = f"field.load_sweep.steps[{position}]"
        step = _object(
            value,
            location,
            {
                "step_index",
                "delta_temperature_K",
                "solve_kind",
                "is_transient",
                "solver",
                "results",
                "comparison",
                "field",
            },
        )
        if step["step_index"] != position or isinstance(step["step_index"], bool):
            raise RenderInputError(f"{location}.step_index must equal {position}")
        delta = _number(step["delta_temperature_K"], f"{location}.delta_temperature_K")
        if delta != EXPECTED_LOADS_K[position]:
            raise RenderInputError(f"{location} has an unexpected prescribed load")
        if step["solve_kind"] != "independent_static_coupfe_solve":
            raise RenderInputError(f"{location}.solve_kind is not an actual static solve")
        if step["is_transient"] is not False:
            raise RenderInputError(f"{location}.is_transient must be false")
        _validate_solver(step["solver"], f"{location}.solver")
        _validate_results(step["results"], f"{location}.results")
        _validate_comparison(step["comparison"], f"{location}.comparison", delta)
        last_arrays = _validate_field_arrays(
            step["field"],
            f"{location}.field",
            node_count=node_count,
            element_count=element_count,
        )

    assert last_arrays is not None
    for name, array in final_arrays.items():
        if not np.array_equal(array, last_arrays[name]):
            raise RenderInputError(
                f"field.final_field.{name} must equal the final solved sweep state"
            )


def frame_step_indices(step_count: int) -> tuple[int, ...]:
    """Return exact forward/reverse state indices, with no interpolated indices."""

    if isinstance(step_count, bool) or not isinstance(step_count, int) or step_count < 2:
        raise ValueError("step_count must be an integer >= 2")
    return tuple(range(step_count)) + tuple(range(step_count - 2, 0, -1))


def _require_media_dependencies():
    try:
        import PIL
        from PIL import Image, ImageDraw, ImageFont
        import imageio_ffmpeg
    except ImportError as exc:
        raise MediaDependencyError(
            "Rendering requires optional media dependencies. Install them with "
            "`python -m pip install \"Pillow>=10\" \"imageio-ffmpeg>=0.5\"`."
        ) from exc
    try:
        font_probe = ImageFont.load_default(size=12)
    except TypeError as exc:
        raise MediaDependencyError(
            "Rendering requires Pillow>=10 for a versioned scalable bundled font."
        ) from exc
    del font_probe
    versions = {
        "pillow": str(PIL.__version__),
        "imageio_ffmpeg": str(imageio_ffmpeg.__version__),
        "ffmpeg": str(imageio_ffmpeg.get_ffmpeg_version()),
        "numpy": str(np.__version__),
    }
    return Image, ImageDraw, ImageFont, imageio_ffmpeg, versions


def _palette(values: np.ndarray, lower: float, upper: float) -> np.ndarray:
    if not upper > lower:
        raise RenderInputError("fixed color scale must have a positive span")
    palette = np.asarray(PALETTE_RGB, dtype=float)
    scaled = np.clip((values - lower) / (upper - lower), 0.0, 1.0)
    positions = scaled * (len(PALETTE_RGB) - 1)
    indices = np.minimum(np.floor(positions).astype(int), len(PALETTE_RGB) - 2)
    local = (positions - indices)[..., None]
    colors = palette[indices] * (1.0 - local) + palette[indices + 1] * local
    return np.rint(colors).astype(np.uint8)


def _render_scales(field: dict[str, Any]) -> dict[str, list[float]]:
    centers = np.asarray(field["mesh"]["element_centers_um"], dtype=float)
    via = float(field["mesh"]["via_radius_um"])
    silicon = centers >= via
    contour_values = []
    curve_values = []
    from eda_multiphysics.tsv_stress import lame_sigma_r

    curve_mask = silicon & (centers <= CURVE_RADIUS_MAX_UM)
    for step in field["load_sweep"]["steps"]:
        sigma = np.asarray(step["field"]["sigma_rr_MPa"], dtype=float)
        contour_values.extend(sigma[silicon & (centers <= CROP_RADIUS_UM)])
        curve_values.extend(sigma[curve_mask])
        lame = lame_sigma_r(
            centers[curve_mask],
            float(field["inputs"]["diameter_um"]),
            float(step["delta_temperature_K"]),
        ) / 1e6
        curve_values.extend(lame)
    color_lower = float(np.min(contour_values))
    color_upper = float(np.max(contour_values))
    curve_lower = float(np.min(curve_values))
    curve_upper = float(np.max(curve_values))
    if not color_upper > color_lower or not curve_upper > curve_lower:
        raise RenderInputError("retained sweep does not span a renderable stress range")
    curve_pad = 0.04 * (curve_upper - curve_lower)
    return {
        "color_range_mpa": [color_lower, color_upper],
        "curve_range_mpa": [curve_lower - curve_pad, curve_upper + curve_pad],
    }


def renderer_configuration(
    field: dict[str, Any],
    *,
    frames_per_state: int = FRAMES_PER_SOLVED_STATE,
) -> dict[str, Any]:
    """Return every renderer choice and dependency version used by the encoder."""

    validate_field_record(field)
    _integer(frames_per_state, "frames_per_state", minimum=1)
    _Image, _ImageDraw, _ImageFont, _imageio_ffmpeg, versions = (
        _require_media_dependencies()
    )
    scales = _render_scales(field)
    indices = frame_step_indices(len(field["load_sweep"]["steps"]))
    return {
        "output": {
            "width_px": WIDTH,
            "height_px": HEIGHT,
            "fps": FPS,
            "container": "webm",
            "codec": "libvpx-vp9",
            "pixel_format": "yuv420p",
            "audio": "none",
            "bitrate": "1200k",
        },
        "temporal_mapping": {
            "source": "field.json#load_sweep.steps",
            "state_order": "forward_then_reverse_exact_solved_states",
            "step_indices": list(indices),
            "frames_per_solved_state": frames_per_state,
            "interpolation": "none",
            "is_transient": False,
        },
        "axisymmetric_reconstruction": {
            "field": "sigma_rr_MPa",
            "region": "silicon",
            "radial_crop_um": CROP_RADIUS_UM,
            "mapping": "radial value revolved about the TSV axis for display only",
            "spatial_sampling": (
                "piecewise-linear display sampling between retained element centers"
            ),
            "physical_dimension": "axisymmetric plane-strain component model",
        },
        "color_scale": {
            "palette": PALETTE_NAME,
            "palette_rgb": [list(color) for color in PALETTE_RGB],
            "normalization": "linear",
            "range_mpa": scales["color_range_mpa"],
            "scope": "all retained silicon solved states",
            "fixed_across_frames": True,
        },
        "radial_curve": {
            "fields": ["FE sigma_rr_MPa", "published Lame sigma_rr_MPa"],
            "radius_range_um": [float(field["mesh"]["via_radius_um"]), CURVE_RADIUS_MAX_UM],
            "stress_range_mpa": scales["curve_range_mpa"],
            "fixed_across_frames": True,
        },
        "labels": {
            "case_id": field["case_id"],
            "diameter_um": field["inputs"]["diameter_um"],
            "degrees_of_freedom": len(field["mesh"]["radius_nodes_um"]),
            "interpretation": "prescribed load sweep — not transient",
            "font": "Pillow bundled default scalable font",
        },
        "encoder_options": {
            "deadline": "good",
            "cpu_used": 0,
            "threads": 1,
            "row_multithreading": False,
            "tile_columns": 0,
            "frame_parallel": False,
            "metadata": "fixed",
        },
        "software_versions": versions,
    }


def _font(ImageFont, size: int):
    return ImageFont.load_default(size=size)


def _text(draw, position, text, *, font, fill=(223, 232, 246), anchor=None):
    draw.text(position, text, font=font, fill=fill, anchor=anchor)


def _centered_text_with_drawn_em_dash(draw, position, text, *, font, fill):
    """Draw a centered label even when the bundled font lacks an em-dash glyph."""

    if text.count("—") != 1:
        raise ValueError("drawn em-dash labels must contain exactly one em dash")
    before, after = text.split("—")
    before_box = draw.textbbox((0, 0), before, font=font)
    after_box = draw.textbbox((0, 0), after, font=font)
    before_width = before_box[2] - before_box[0]
    after_width = after_box[2] - after_box[0]
    dash_width = 15
    gap = 5
    total_width = before_width + after_width + dash_width + 2 * gap
    start_x = position[0] - total_width / 2.0
    draw.text((start_x, position[1]), before, font=font, fill=fill, anchor="lm")
    dash_start = start_x + before_width + gap
    draw.line(
        (dash_start, position[1], dash_start + dash_width, position[1]),
        fill=fill,
        width=2,
    )
    draw.text(
        (dash_start + dash_width + gap, position[1]),
        after,
        font=font,
        fill=fill,
        anchor="lm",
    )


def _draw_dashed_line(draw, points, *, fill, width=2):
    for start in range(0, len(points) - 1, 2):
        draw.line(points[start : start + 2], fill=fill, width=width)


def _render_frame(field: dict[str, Any], step_index: int, configuration, media):
    Image, ImageDraw, ImageFont, _imageio_ffmpeg = media
    image = Image.new("RGB", (WIDTH, HEIGHT), (8, 15, 27))
    draw = ImageDraw.Draw(image)
    title_font = _font(ImageFont, 24)
    label_font = _font(ImageFont, 15)
    small_font = _font(ImageFont, 12)
    metric_font = _font(ImageFont, 14)

    step = field["load_sweep"]["steps"][step_index]
    nodes = np.asarray(field["mesh"]["radius_nodes_um"], dtype=float)
    centers = np.asarray(field["mesh"]["element_centers_um"], dtype=float)
    sigma = np.asarray(step["field"]["sigma_rr_MPa"], dtype=float)
    via = float(field["mesh"]["via_radius_um"])
    color_lower, color_upper = configuration["color_scale"]["range_mpa"]
    curve_lower, curve_upper = configuration["radial_curve"]["stress_range_mpa"]

    draw.rounded_rectangle((18, 16, 942, 82), radius=12, fill=(15, 28, 47))
    _text(
        draw,
        (34, 27),
        f"CoupFE solver field | {field['case_id']}",
        font=title_font,
        fill=(239, 245, 255),
    )
    _text(
        draw,
        (34, 58),
        (
            f"D={field['inputs']['diameter_um']:.0f} um | "
            f"dT={step['delta_temperature_K']:.0f} K | "
            f"DOF={len(nodes):,} | solved state {step_index + 1}/9"
        ),
        font=small_font,
        fill=(164, 184, 211),
    )

    panel_left, panel_top, panel_size = 30, 112, 352
    yy, xx = np.mgrid[0:panel_size, 0:panel_size]
    center_px = (panel_size - 1) / 2.0
    radius_px = np.sqrt((xx - center_px) ** 2 + (yy - center_px) ** 2)
    radius_um = radius_px / (panel_size * 0.46) * CROP_RADIUS_UM
    panel = np.full((panel_size, panel_size, 3), (13, 24, 39), dtype=np.uint8)
    silicon_mask = (radius_um >= via) & (radius_um <= CROP_RADIUS_UM)
    silicon_centers = centers[centers >= via]
    silicon_sigma = sigma[centers >= via]
    sampled = np.interp(radius_um[silicon_mask], silicon_centers, silicon_sigma)
    panel[silicon_mask] = _palette(sampled, color_lower, color_upper)
    copper_mask = radius_um < via
    panel[copper_mask] = np.asarray((95, 73, 51), dtype=np.uint8)
    image.paste(Image.fromarray(panel, mode="RGB"), (panel_left, panel_top))
    draw.ellipse(
        (panel_left, panel_top, panel_left + panel_size, panel_top + panel_size),
        outline=(72, 94, 122),
        width=2,
    )
    via_px = via / CROP_RADIUS_UM * panel_size * 0.46
    cx = panel_left + center_px
    cy = panel_top + center_px
    draw.ellipse(
        (cx - via_px, cy - via_px, cx + via_px, cy + via_px),
        outline=(238, 242, 248),
        width=2,
    )
    _text(draw, (cx, cy), "Cu", font=label_font, anchor="mm")
    _text(draw, (panel_left + 10, panel_top + 10), "silicon sigma_rr", font=label_font)
    _text(
        draw,
        (panel_left + 10, panel_top + panel_size - 22),
        f"axisymmetric display crop: r <= {CROP_RADIUS_UM:.0f} um",
        font=small_font,
    )

    bar_x, bar_y, bar_w, bar_h = 398, 151, 14, 240
    gradient_values = np.linspace(color_upper, color_lower, bar_h)
    gradient = _palette(gradient_values, color_lower, color_upper).reshape(bar_h, 1, 3)
    gradient = np.repeat(gradient, bar_w, axis=1)
    image.paste(Image.fromarray(gradient, mode="RGB"), (bar_x, bar_y))
    _text(draw, (bar_x - 3, bar_y - 25), "MPa (fixed)", font=small_font)
    _text(
        draw,
        (bar_x + bar_w + 6, bar_y),
        f"{color_upper:.1f}",
        font=small_font,
        anchor="lm",
    )
    _text(
        draw,
        (bar_x + bar_w + 6, bar_y + bar_h),
        f"{color_lower:.1f}",
        font=small_font,
        anchor="lm",
    )

    graph_left, graph_top, graph_width, graph_height = 505, 142, 420, 252
    draw.rectangle(
        (graph_left, graph_top, graph_left + graph_width, graph_top + graph_height),
        fill=(12, 22, 37),
        outline=(63, 82, 108),
        width=1,
    )
    for fraction in (0.0, 0.25, 0.5, 0.75, 1.0):
        y = graph_top + graph_height * (1.0 - fraction)
        value = curve_lower + fraction * (curve_upper - curve_lower)
        draw.line((graph_left, y, graph_left + graph_width, y), fill=(35, 49, 68), width=1)
        _text(draw, (graph_left - 8, y), f"{value:.0f}", font=small_font, anchor="rm")
    for radius_tick in (20.0, 40.0, 60.0, 80.0):
        x = graph_left + (radius_tick - via) / (CURVE_RADIUS_MAX_UM - via) * graph_width
        draw.line((x, graph_top, x, graph_top + graph_height), fill=(35, 49, 68), width=1)
        _text(
            draw,
            (x, graph_top + graph_height + 8),
            f"{radius_tick:.0f}",
            font=small_font,
            anchor="ma",
        )

    curve_mask = (centers >= via) & (centers <= CURVE_RADIUS_MAX_UM)
    curve_radius = centers[curve_mask]
    curve_fe = sigma[curve_mask]
    from eda_multiphysics.tsv_stress import lame_sigma_r

    curve_lame = lame_sigma_r(
        curve_radius,
        float(field["inputs"]["diameter_um"]),
        float(step["delta_temperature_K"]),
    ) / 1e6

    def points(values):
        x = graph_left + (curve_radius - via) / (CURVE_RADIUS_MAX_UM - via) * graph_width
        y = graph_top + (curve_upper - values) / (curve_upper - curve_lower) * graph_height
        return [(float(xx), float(yy)) for xx, yy in zip(x, y)]

    fe_points = points(curve_fe)
    lame_points = points(curve_lame)
    if len(fe_points) >= 2:
        draw.line(fe_points, fill=(72, 188, 225), width=3, joint="curve")
        _draw_dashed_line(draw, lame_points, fill=(236, 196, 92), width=2)
    _text(draw, (graph_left, graph_top - 28), "FE / Lame radial sigma_rr", font=label_font)
    draw.line(
        (graph_left + 210, graph_top - 21, graph_left + 238, graph_top - 21),
        fill=(72, 188, 225),
        width=3,
    )
    _text(draw, (graph_left + 244, graph_top - 27), "FE", font=small_font)
    draw.line(
        (graph_left + 286, graph_top - 21, graph_left + 314, graph_top - 21),
        fill=(236, 196, 92),
        width=2,
    )
    _text(draw, (graph_left + 320, graph_top - 27), "Lame", font=small_font)
    _text(
        draw,
        (graph_left + graph_width / 2, graph_top + graph_height + 15),
        "radius (um)",
        font=small_font,
        anchor="ma",
    )

    comparison = step["comparison"]
    relative = comparison["relative_error"]
    relative_text = "0-load exact" if relative is None else f"{relative:.3%} error"
    draw.rounded_rectangle((505, 438, 925, 481), radius=8, fill=(16, 33, 52))
    _text(
        draw,
        (519, 449),
        (
            f"at 20 um: FE {comparison['fe_sigma_rr_MPa']:.3f} MPa | "
            f"Lame {comparison['lame_sigma_rr_MPa']:.3f} MPa | {relative_text}"
        ),
        font=metric_font,
    )
    _centered_text_with_drawn_em_dash(
        draw,
        (480, 515),
        "prescribed load sweep — not transient",
        font=label_font,
        fill=(244, 207, 102),
    )
    return image


def render_video(
    field_path: str | Path,
    output_path: str | Path,
    *,
    frames_per_state: int = FRAMES_PER_SOLVED_STATE,
) -> dict[str, Any]:
    """Validate ``field.json``, render exact states, and atomically write WebM."""

    field = load_field(field_path)
    configuration = renderer_configuration(field, frames_per_state=frames_per_state)
    Image, ImageDraw, ImageFont, imageio_ffmpeg, _versions = _require_media_dependencies()
    target = Path(output_path)
    if target.suffix.casefold() != ".webm":
        raise RenderInputError("video output must use the .webm suffix")
    if target.is_symlink() or target.exists():
        raise RenderInputError("video output must be a new non-symlink path")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.parent.is_symlink() or not target.parent.is_dir():
        raise RenderInputError("video output parent must be a regular directory")

    with tempfile.NamedTemporaryFile(
        prefix=".load-sweep-",
        suffix=".webm",
        dir=target.parent,
        delete=False,
    ) as temporary:
        temporary_path = Path(temporary.name)
    try:
        writer = imageio_ffmpeg.write_frames(
            temporary_path,
            (WIDTH, HEIGHT),
            pix_fmt_in="rgb24",
            pix_fmt_out="yuv420p",
            fps=FPS,
            quality=None,
            bitrate="1200k",
            codec="libvpx-vp9",
            macro_block_size=2,
            ffmpeg_log_level="error",
            output_params=[
                "-deadline",
                "good",
                "-cpu-used",
                "0",
                "-threads",
                "1",
                "-row-mt",
                "0",
                "-tile-columns",
                "0",
                "-frame-parallel",
                "0",
                "-map_metadata",
                "-1",
                "-metadata",
                "title=CoupFE prescribed load sweep",
                "-metadata",
                "creation_time=1970-01-01T00:00:00Z",
            ],
        )
        writer.send(None)
        try:
            media = (Image, ImageDraw, ImageFont, imageio_ffmpeg)
            for step_index in configuration["temporal_mapping"]["step_indices"]:
                frame = _render_frame(field, step_index, configuration, media)
                payload = np.asarray(frame, dtype=np.uint8).tobytes(order="C")
                for _repeat in range(frames_per_state):
                    writer.send(payload)
        finally:
            writer.close()
        if not temporary_path.is_file() or temporary_path.stat().st_size == 0:
            raise RuntimeError("ffmpeg did not produce a non-empty WebM")
        os.replace(temporary_path, target)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()
    return configuration


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("field", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        configuration = render_video(args.field, args.output)
    except (MediaDependencyError, RenderInputError, RuntimeError) as exc:
        print(f"visual rendering failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(configuration, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
