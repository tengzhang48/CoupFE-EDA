"""Generate solver-derived axisymmetric TSV field evidence."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import re
import subprocess
import sys

import numpy as np

sys.dont_write_bytecode = True

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from eda_multiphysics.source_identity import resolve_coupfe_identity
from eda_multiphysics.tsv_stress import lame_sigma_r, sigma_at, solve_tsv_field


CASE_ID = "axisymmetric_tsv_thermoelastic_field_v1"
DIAMETER_UM = 30.0
DELTA_TEMPERATURE_K = -400.0
OUTER_RADIUS_UM = 300.0
MESH_POINTS = 2400
QUERY_RADIUS_UM = 20.0
LAME_ACCEPTANCE_THRESHOLD = 0.03
LOADS_K = (0.0, -50.0, -100.0, -150.0, -200.0, -250.0, -300.0, -350.0, -400.0)
CLAIM_BOUNDARY = (
    "Axisymmetric plane-strain thermoelastic component verification against the "
    "declared Lamé equation. It is not a finite-depth 3-D TSV, near-surface device "
    "field, experimental validation, keep-out-zone signoff, or transient cooling "
    "simulation."
)
UNITS = {
    "radius": "um",
    "radial_displacement": "nm",
    "stress": "MPa",
    "temperature_change": "K",
    "residual_norm": "N/m",
}
_OUTPUT_FILENAMES = ("field.json", "summary.json", "contour.svg")
_REVISION_RE = re.compile(r"[0-9a-f]{40}")


def _inputs(mesh_points):
    return {
        "diameter_um": DIAMETER_UM,
        "delta_temperature_K": DELTA_TEMPERATURE_K,
        "outer_radius_um": OUTER_RADIUS_UM,
        "mesh_points_requested": int(mesh_points),
        "liner_nm": 0.0,
        "formulation": "axisymmetric_plane_strain",
        "load": "uniform_thermal_eigenstrain",
    }


def _solver_record(telemetry):
    return {
        "newton_iterations": telemetry.newton_iterations,
        "relative_tolerance": telemetry.relative_tolerance,
        "absolute_residual_tolerance_N_per_m": (
            telemetry.absolute_residual_tolerance_n_per_m
        ),
        "initial_free_residual_norm_N_per_m": (
            telemetry.initial_free_residual_norm_n_per_m
        ),
        "final_free_residual_norm_N_per_m": (
            telemetry.final_free_residual_norm_n_per_m
        ),
        "final_relative_residual": telemetry.final_relative_residual,
        "residual_fraction_of_acceptance_limit": (
            telemetry.residual_fraction_of_acceptance_limit
        ),
        "converged": telemetry.converged,
    }


def _results_record(result):
    centers = result.mesh.element_centers_m
    sigma_rr_20 = sigma_at(centers, result.element_sigma_rr_pa, QUERY_RADIUS_UM) / 1e6
    sigma_theta_20 = (
        sigma_at(centers, result.element_sigma_theta_pa, QUERY_RADIUS_UM) / 1e6
    )
    silicon = result.regions["silicon"]
    silicon_rr = result.element_sigma_rr_pa[silicon] / 1e6
    return {
        "sigma_rr_at_20um_MPa": sigma_rr_20,
        "sigma_theta_at_20um_MPa": sigma_theta_20,
        "max_abs_displacement_nm": float(np.max(np.abs(result.node_displacement_m)))
        * 1e9,
        "silicon_sigma_rr_min_MPa": float(np.min(silicon_rr)),
        "silicon_sigma_rr_max_MPa": float(np.max(silicon_rr)),
    }


def _comparison_record(result):
    fe_mpa = sigma_at(
        result.mesh.element_centers_m,
        result.element_sigma_rr_pa,
        QUERY_RADIUS_UM,
    ) / 1e6
    lame_mpa = lame_sigma_r(
        QUERY_RADIUS_UM,
        DIAMETER_UM,
        result.delta_temperature_k,
    ) / 1e6
    absolute_error = abs(fe_mpa - lame_mpa)
    if lame_mpa == 0.0:
        relative_error = None
        passed = absolute_error <= 1e-12
    else:
        relative_error = absolute_error / abs(lame_mpa)
        passed = relative_error < LAME_ACCEPTANCE_THRESHOLD
    return {
        "reference": "published_Lame_equation",
        "query_radius_um": QUERY_RADIUS_UM,
        "fe_sigma_rr_MPa": fe_mpa,
        "lame_sigma_rr_MPa": lame_mpa,
        "absolute_error_MPa": absolute_error,
        "relative_error": relative_error,
        "acceptance_threshold": LAME_ACCEPTANCE_THRESHOLD,
        "passed": bool(passed),
    }


def _field_arrays(result):
    return {
        "radial_displacement_nm": (result.node_displacement_m * 1e9).tolist(),
        "sigma_rr_MPa": (result.element_sigma_rr_pa / 1e6).tolist(),
        "sigma_theta_MPa": (result.element_sigma_theta_pa / 1e6).tolist(),
    }


def _git_revision(repository):
    completed = subprocess.run(
        ["git", "-C", str(repository), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    revision = completed.stdout.strip()
    if _REVISION_RE.fullmatch(revision) is None:
        raise RuntimeError(f"Git returned a non-canonical revision for {repository}")
    return revision


def _provenance():
    eda_root = Path(__file__).resolve().parents[2]
    core = resolve_coupfe_identity()
    return {
        "eda_revision": _git_revision(eda_root),
        "core_revision": core.revision,
        "application_module": "eda_multiphysics.tsv_stress",
        "operator": "AxisymThermoelastic",
        "solver": "coupfe.newton_solve",
        "command": [
            "python",
            "examples/tsv_axisymmetric_field/run.py",
            "--output-dir",
            "<OUTPUT_DIR>",
        ],
    }


def _assert_finite_json(value, location="record"):
    if value is None or isinstance(value, (str, bool)):
        return
    if isinstance(value, int):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise FloatingPointError(f"{location} contains a non-finite value")
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            _assert_finite_json(child, f"{location}[{index}]")
        return
    if isinstance(value, dict):
        for key, child in value.items():
            _assert_finite_json(child, f"{location}.{key}")
        return
    raise TypeError(f"{location} contains a non-JSON value: {type(value).__name__}")


def _json_text(record):
    _assert_finite_json(record)
    return json.dumps(record, indent=2, sort_keys=True, allow_nan=False) + "\n"


def _color(value, lower, upper):
    palette = (
        (10, 18, 42),
        (24, 73, 154),
        (14, 165, 233),
        (34, 197, 94),
        (250, 204, 21),
        (249, 115, 22),
        (220, 38, 38),
    )
    fraction = 0.0 if upper <= lower else (value - lower) / (upper - lower)
    fraction = min(1.0, max(0.0, fraction)) * (len(palette) - 1)
    index = min(int(fraction), len(palette) - 2)
    local = fraction - index
    rgb = tuple(
        round(palette[index][channel] * (1.0 - local) + palette[index + 1][channel] * local)
        for channel in range(3)
    )
    return "#%02x%02x%02x" % rgb


def _profile_points(radius_um, values_mpa, x0, y0, width, height, x_max, y_limit):
    mask = radius_um <= x_max
    x = x0 + radius_um[mask] / x_max * width
    y = y0 + (y_limit - values_mpa[mask]) / (2.0 * y_limit) * height
    return " ".join(f"{xx:.2f},{yy:.2f}" for xx, yy in zip(x, y))


def _contour_svg(result, comparison):
    centers_um = result.mesh.element_centers_m * 1e6
    sigma_rr_mpa = result.element_sigma_rr_pa / 1e6
    sigma_theta_mpa = result.element_sigma_theta_pa / 1e6
    lower = float(np.min(sigma_rr_mpa))
    upper = float(np.max(sigma_rr_mpa))
    crop_um = 60.0
    cx, cy, disk_radius = 305.0, 380.0, 245.0
    circles = []
    ring_edges = np.linspace(crop_um, 0.0, 121)
    for outer, inner in zip(ring_edges[:-1], ring_edges[1:]):
        sample_radius = 0.5 * (outer + inner)
        value = float(np.interp(sample_radius, centers_um, sigma_rr_mpa))
        circles.append(
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" '
            f'r="{outer / crop_um * disk_radius:.3f}" fill="{_color(value, lower, upper)}"/>'
        )

    graph_x, graph_y, graph_w, graph_h = 680.0, 220.0, 450.0, 315.0
    y_limit = max(abs(float(np.min(sigma_theta_mpa))), upper) * 1.05
    radial_points = _profile_points(
        centers_um, sigma_rr_mpa, graph_x, graph_y, graph_w, graph_h, 80.0, y_limit
    )
    hoop_points = _profile_points(
        centers_um, sigma_theta_mpa, graph_x, graph_y, graph_w, graph_h, 80.0, y_limit
    )
    via_screen_radius = result.mesh.via_radius_m * 1e6 / crop_um * disk_radius
    ticks = []
    for fraction in (-1.0, -0.5, 0.0, 0.5, 1.0):
        value = fraction * y_limit
        y = graph_y + (1.0 - fraction) * 0.5 * graph_h
        ticks.append(
            f'<line x1="{graph_x:.1f}" y1="{y:.2f}" x2="{graph_x + graph_w:.1f}" '
            'y2="{:.2f}" stroke="#24334f" stroke-width="1"/>'.format(y)
        )
        ticks.append(
            f'<text x="{graph_x - 12:.1f}" y="{y + 5:.2f}" text-anchor="end" '
            f'class="tick">{value:.0f}</text>'
        )
    for value in (0, 20, 40, 60, 80):
        x = graph_x + value / 80.0 * graph_w
        ticks.append(
            f'<line x1="{x:.2f}" y1="{graph_y:.1f}" x2="{x:.2f}" '
            f'y2="{graph_y + graph_h:.1f}" stroke="#24334f" stroke-width="1"/>'
        )
        ticks.append(
            f'<text x="{x:.2f}" y="{graph_y + graph_h + 24:.1f}" '
            f'text-anchor="middle" class="tick">{value}</text>'
        )

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="720" viewBox="0 0 1200 720" role="img" aria-labelledby="title desc" data-source="field.json#final_field">
  <title id="title">CoupFE TSV radial stress field</title>
  <desc id="desc">{CLAIM_BOUNDARY} The contour is an axisymmetric reconstruction of the recovered sigma rr field.</desc>
  <defs>
    <linearGradient id="background" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#07101f"/><stop offset="1" stop-color="#101b34"/></linearGradient>
    <linearGradient id="legend" x1="0" y1="1" x2="0" y2="0"><stop offset="0" stop-color="#0a122a"/><stop offset=".17" stop-color="#18499a"/><stop offset=".34" stop-color="#0ea5e9"/><stop offset=".5" stop-color="#22c55e"/><stop offset=".67" stop-color="#facc15"/><stop offset=".84" stop-color="#f97316"/><stop offset="1" stop-color="#dc2626"/></linearGradient>
    <style>.title{{font:700 29px system-ui,sans-serif;fill:#f8fafc}}.sub{{font:500 15px system-ui,sans-serif;fill:#9fb2cf}}.label{{font:600 14px system-ui,sans-serif;fill:#dbeafe}}.tick{{font:12px ui-monospace,monospace;fill:#8fa4c2}}.metric{{font:600 14px ui-monospace,monospace;fill:#e2e8f0}}</style>
  </defs>
  <rect width="1200" height="720" fill="url(#background)"/>
  <text x="54" y="54" class="title">Solver-derived TSV stress field</text>
  <text x="54" y="82" class="sub">CoupFE newton_solve · Line2 radial mesh · ΔT = −400 K · 2,400 DOFs</text>
  <g data-component="sigma_rr_MPa">{''.join(circles)}</g>
  <circle cx="{cx}" cy="{cy}" r="{via_screen_radius:.3f}" fill="none" stroke="#f8fafc" stroke-width="2" stroke-dasharray="6 5"/>
  <line x1="{cx}" y1="{cy}" x2="{cx + disk_radius}" y2="{cy}" stroke="#f8fafc" stroke-opacity=".55"/>
  <text x="{cx}" y="{cy + 5}" text-anchor="middle" class="label">Cu</text>
  <text x="{cx + via_screen_radius + 14}" y="{cy - 12}" class="label">Si</text>
  <text x="60" y="660" class="sub">Axisymmetric reconstruction, cropped to r = 60 µm (full solved domain: 300 µm)</text>
  <rect x="596" y="253" width="18" height="250" rx="9" fill="url(#legend)"/>
  <text x="605" y="235" text-anchor="middle" class="label">σrr</text>
  <text x="624" y="263" class="tick">{upper:.0f}</text><text x="624" y="503" class="tick">{lower:.0f} MPa</text>
  <text x="{graph_x}" y="190" class="label">Recovered element-center stress profile</text>
  {''.join(ticks)}
  <polyline points="{radial_points}" fill="none" stroke="#38bdf8" stroke-width="3"/>
  <polyline points="{hoop_points}" fill="none" stroke="#fb7185" stroke-width="3"/>
  <text x="{graph_x + 18}" y="{graph_y + 27}" class="label" fill="#38bdf8">σrr</text>
  <text x="{graph_x + 67}" y="{graph_y + 27}" class="label" fill="#fb7185">σθθ</text>
  <text x="{graph_x + graph_w / 2}" y="{graph_y + graph_h + 52}" text-anchor="middle" class="sub">radius r (µm)</text>
  <text x="{graph_x}" y="610" class="metric">FE σrr(20 µm)  {comparison['fe_sigma_rr_MPa']:.3f} MPa</text>
  <text x="{graph_x}" y="635" class="metric">Lamé reference    {comparison['lame_sigma_rr_MPa']:.3f} MPa</text>
  <text x="{graph_x}" y="660" class="metric">relative error    {comparison['relative_error']:.4%}</text>
  <text x="1142" y="699" text-anchor="end" class="sub">Axisymmetric component verification · not 3-D · not transient</text>
</svg>
'''


def _prepare_output_directory(output_dir):
    output_dir = Path(output_dir)
    if output_dir.is_symlink():
        raise ValueError("output directory must not be a symbolic link")
    output_dir.mkdir(parents=True, exist_ok=True)
    if not output_dir.is_dir():
        raise ValueError("output path must be a directory")
    for filename in _OUTPUT_FILENAMES:
        target = output_dir / filename
        if target.is_symlink():
            raise ValueError(f"refusing to replace symbolic link: {filename}")
        if target.exists() and not target.is_file():
            raise ValueError(f"refusing to replace non-regular path: {filename}")
    return output_dir


def run_evidence_case(output_dir, *, mesh_points=MESH_POINTS):
    """Run nine independent CoupFE solves and write the three fixed artifacts."""
    output_dir = _prepare_output_directory(output_dir)
    solved_steps = []
    for step_index, delta_temperature in enumerate(LOADS_K):
        result = solve_tsv_field(
            DIAMETER_UM,
            delta_temperature,
            R_out_um=OUTER_RADIUS_UM,
            n=mesh_points,
        )
        comparison = _comparison_record(result)
        if not comparison["passed"]:
            raise RuntimeError(
                f"Lamé comparison failed at prescribed load {delta_temperature} K"
            )
        solved_steps.append(
            {
                "step_index": step_index,
                "delta_temperature_K": delta_temperature,
                "solve_kind": "independent_static_coupfe_solve",
                "is_transient": False,
                "solver": _solver_record(result.telemetry),
                "results": _results_record(result),
                "comparison": comparison,
                "field": _field_arrays(result),
                "_result": result,
            }
        )

    final_result = solved_steps[-1].pop("_result")
    for step in solved_steps[:-1]:
        step.pop("_result")
    final_solver = _solver_record(final_result.telemetry)
    final_results = _results_record(final_result)
    final_comparison = _comparison_record(final_result)
    mesh = final_result.mesh
    inputs = _inputs(mesh_points)
    sweep_summary = {
        "steps": len(solved_steps),
        "kind": "independent_static_prescribed_load_cases",
        "is_transient": False,
        "delta_temperature_K": list(LOADS_K),
    }
    summary = {
        "schema_version": 1,
        "case_id": CASE_ID,
        "claim_boundary": CLAIM_BOUNDARY,
        "provenance": _provenance(),
        "inputs": inputs,
        "units": UNITS,
        "mesh": {
            "topology": "Line2",
            "nodes": mesh.node_count,
            "elements": mesh.element_count,
            "degrees_of_freedom": final_result.degrees_of_freedom,
            "dof_per_node": 1,
        },
        "solver": final_solver,
        "results": final_results,
        "comparison": final_comparison,
        "load_sweep": sweep_summary,
    }
    field = {
        "schema_version": 1,
        "case_id": CASE_ID,
        "claim_boundary": CLAIM_BOUNDARY,
        "units": UNITS,
        "inputs": inputs,
        "topology": {
            "type": "Line2",
            "spatial_dimension": 1,
            "dof_per_node": 1,
        },
        "mesh": {
            "radius_nodes_um": (mesh.radius_nodes_m * 1e6).tolist(),
            "element_centers_um": (mesh.element_centers_m * 1e6).tolist(),
            "connectivity": mesh.connectivity.tolist(),
            "region_by_element": final_result.region_by_element.tolist(),
            "region_element_indices": {
                name: indices.tolist() for name, indices in final_result.regions.items()
            },
            "via_radius_um": mesh.via_radius_m * 1e6,
            "outer_radius_um": mesh.outer_radius_m * 1e6,
        },
        "final_field": {
            "delta_temperature_K": DELTA_TEMPERATURE_K,
            **_field_arrays(final_result),
        },
        "solver": final_solver,
        "comparison": final_comparison,
        "load_sweep": {
            "sweep_kind": "independent_static_prescribed_load_cases",
            "is_transient": False,
            "description": (
                "Nine independent actual CoupFE static solves at prescribed temperature "
                "changes; this ordered load sweep is not a transient simulation."
            ),
            "delta_temperature_K": list(LOADS_K),
            "steps": solved_steps,
        },
    }

    field_text = _json_text(field)
    summary_text = _json_text(summary)
    contour_text = _contour_svg(final_result, final_comparison)
    (output_dir / "field.json").write_text(field_text, encoding="utf-8")
    (output_dir / "summary.json").write_text(summary_text, encoding="utf-8")
    (output_dir / "contour.svg").write_text(contour_text, encoding="utf-8")
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    summary = run_evidence_case(args.output_dir)
    print(_json_text(summary), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
