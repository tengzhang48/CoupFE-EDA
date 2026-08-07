"""Render website figures from checked CoupFE-EDA simulation runners.

The script executes the named EDA examples, verifies their retained numerical
oracles, and writes three accessible SVG figures, a portrait ETV variant, the
ETV state record used by those figures, and a checksum/source contract.
It deliberately does not consume CoupFE-Cardiac results; that project's
environment can be used to provide the shared pinned CoupFE Core dependency.

Run from the repository root with a Python environment containing CoupFE::

    python web/scripts/render-simulation-media.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any
from xml.sax.saxutils import escape

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "web/public/generated/simulation-media"
DEFAULT_CONTRACT = ROOT / "web/contracts/simulation-media.json"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eda_multiphysics.source_identity import SourceIdentityError, resolve_coupfe_identity
from examples.design_linked_solder_screening import run as design_solder_runner
from examples.etv_partitioned_cycle import run as etv_runner
from examples.solder_3d_cycle import run as solder_runner


class MediaBuildError(RuntimeError):
    """Raised when a simulation or its provenance cannot support a figure."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as stream:
        temporary = Path(stream.name)
        stream.write(content)
    os.replace(temporary, path)


def _git_revision(root: Path) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    revision = completed.stdout.strip()
    if len(revision) != 40 or any(character not in "0123456789abcdef" for character in revision):
        raise MediaBuildError("CoupFE-EDA Git revision is not canonical")
    return revision


def _core_identity() -> dict[str, str]:
    """Resolve the reviewed Core from a checkout or shared pinned environment."""

    return resolve_coupfe_identity().as_record()


def _verify_simulations() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    solder = solder_runner.run()
    solder_oracle = json.loads(
        (ROOT / "examples/solder_3d_cycle/expected_results.json").read_text(encoding="utf-8")
    )
    errors = solder_runner._compare(
        solder,
        solder_oracle["expected"],
        rtol=float(solder_oracle["relative_tolerance"]),
        atol=float(solder_oracle["absolute_tolerance"]),
    )
    errors.extend(solder_runner._check_bounds(solder, solder_oracle.get("bounds", [])))
    if errors:
        raise MediaBuildError("solder_3d_cycle failed its oracle: " + "; ".join(errors))

    design_solder = design_solder_runner.run()
    design_oracle = json.loads(
        (ROOT / "examples/design_linked_solder_screening/expected_results.json").read_text(
            encoding="utf-8"
        )
    )
    errors = design_solder_runner._compare(
        design_solder,
        design_oracle["expected"],
        rtol=float(design_oracle["relative_tolerance"]),
        atol=float(design_oracle["absolute_tolerance"]),
    )
    errors.extend(
        design_solder_runner._check_bounds(design_solder, design_oracle.get("bounds", []))
    )
    if errors:
        raise MediaBuildError(
            "design_linked_solder_screening failed its oracle: " + "; ".join(errors)
        )

    etv = etv_runner.run()
    verification = etv_runner._check(etv)
    if not verification["passed"]:
        raise MediaBuildError(
            "etv_partitioned_cycle failed its oracle: " + "; ".join(verification["failures"])
        )
    etv["verification"] = verification
    return solder, design_solder, etv


def _mix(left: tuple[int, int, int], right: tuple[int, int, int], amount: float) -> str:
    amount = min(1.0, max(0.0, amount))
    channels = [round(a + (b - a) * amount) for a, b in zip(left, right)]
    return "#" + "".join(f"{channel:02x}" for channel in channels)


def _svg_document(
    title: str,
    description: str,
    body: str,
    *,
    width: int = 960,
    height: int = 560,
) -> str:
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="figure-title figure-description">
  <title id="figure-title">{escape(title)}</title>
  <desc id="figure-description">{escape(description)}</desc>
  <rect width="{width}" height="{height}" fill="#08111f"/>
  <style>
    text {{ font-family: Inter, ui-sans-serif, system-ui, sans-serif; fill: #edf4ff; }}
    .muted {{ fill: #9eb0c8; }} .label {{ fill: #cbd8ea; font-size: 13px; }}
    .small {{ font-size: 12px; }} .value {{ font: 600 13px ui-monospace, SFMono-Regular, monospace; }}
    .axis {{ stroke: #52647e; stroke-width: 1; }}
  </style>
{body}
</svg>
'''


def _solder_svg(record: dict[str, Any]) -> str:
    values = [float(value) for value in record["results"]["dW_element_MPa"]]
    nx, ny, nz = record["configuration"]["mesh_elements_xyz"]
    if [nx, ny, nz] != [3, 3, 2] or len(values) != 18 or not all(math.isfinite(v) for v in values):
        raise MediaBuildError("solder dissipation field is not the reviewed 3x3x2 result")
    lower, upper = min(values), max(values)
    parts = [
        '<text x="42" y="46" font-size="24" font-weight="700">3-D solder accumulated inelastic dissipation</text>',
        '<text x="42" y="72" class="muted" font-size="13">18 accepted Hex8 element values · one idealized SAC305 cycle · 1 MPa = 1 MJ/m³</text>',
    ]
    panel_x = (74, 514)
    cell = 104
    for k in range(nz):
        x0 = panel_x[k]
        parts.append(f'<text x="{x0}" y="118" font-size="16" font-weight="650">Layer z{k + 1} / {nz}</text>')
        for j in range(ny):
            for i in range(nx):
                value = values[(k * ny + j) * nx + i]
                fraction = (value - lower) / (upper - lower)
                fill = _mix((21, 51, 88), (229, 187, 78), fraction)
                x = x0 + i * cell
                y = 138 + (ny - 1 - j) * cell
                is_peak = math.isclose(value, upper, rel_tol=0.0, abs_tol=1e-10)
                stroke = "#ffffff" if is_peak else "#7185a0"
                width = 3 if is_peak else 1
                parts.append(
                    f'<rect x="{x}" y="{y}" width="{cell - 8}" height="{cell - 8}" rx="8" '
                    f'fill="{fill}" stroke="{stroke}" stroke-width="{width}"/>'
                )
                parts.append(f'<text x="{x + 48}" y="{y + 43}" text-anchor="middle" class="value">{value:.6f}</text>')
                parts.append(f'<text x="{x + 48}" y="{y + 65}" text-anchor="middle" class="small muted">e{i + 1},{j + 1},{k + 1}</text>')
        parts.extend(
            [
                f'<line x1="{x0}" y1="466" x2="{x0 + 296}" y2="466" class="axis"/>',
                f'<text x="{x0 + 148}" y="490" text-anchor="middle" class="label">x element index →</text>',
            ]
        )
    parts.extend(
        [
            '<rect x="74" y="520" width="20" height="10" fill="#153358"/><text x="102" y="530" class="small muted">lower</text>',
            '<rect x="160" y="520" width="20" height="10" fill="#e5bb4e"/><text x="188" y="530" class="small muted">higher</text>',
            f'<text x="514" y="528" class="label">mean {record["results"]["dW_mean_MPa"]:.6f} MPa · peak {record["results"]["dW_peak_MPa"]:.6f} MPa</text>',
        ]
    )
    return _svg_document(
        "3-D solder accumulated inelastic dissipation",
        "Two 3 by 3 heatmaps show all 18 Hex8 element dissipation values from the checked CoupFE-EDA solder_3d_cycle runner. The center x-column has the peak values in both layers. The case is an idealized one-cycle study, not crack-location or package-life evidence.",
        "\n".join(f"  {part}" for part in parts),
    )


def _design_linked_solder_svg(record: dict[str, Any]) -> str:
    values = [float(value) for value in record["results"]["dW_element_MPa"]]
    nx, ny, nz = record["configuration"]["mesh_elements_xyz"]
    if [nx, ny, nz] != [3, 3, 2] or len(values) != 18 or not all(math.isfinite(v) for v in values):
        raise MediaBuildError("design-linked solder field is not the reviewed 3x3x2 result")

    selected = record["selected_design_object"]
    tied = set(selected["maximum_dnp_tied_joint_ids"])
    if selected["joint_id"] != "SYNTH_J00" or len(tied) != 4:
        raise MediaBuildError("design-linked solder selection is not the reviewed stable-ID result")

    lower, upper = min(values), max(values)
    parts = [
        '<text x="42" y="46" font-size="24" font-weight="700">Design-linked solder screening output</text>',
        '<text x="42" y="72" class="muted" font-size="13">Synthetic joint identity → distance-to-neutral-point handoff → checked 18-Hex8 SAC305 response</text>',
        '<rect x="42" y="104" width="286" height="402" rx="8" fill="#0d1b2e" stroke="#344862"/>',
        '<text x="62" y="136" font-size="16" font-weight="650">Synthetic 3 × 3 joint map</text>',
        '<text x="62" y="158" class="small muted">Maximum DNP; stable row-order tie break</text>',
    ]
    for row in range(3):
        for column in range(3):
            joint_id = f"SYNTH_J{row}{column}"
            x = 96 + column * 82
            y = 210 + row * 82
            selected_joint = joint_id == selected["joint_id"]
            tied_joint = joint_id in tied
            fill = "#d7a83e" if selected_joint else "#193a55"
            stroke = "#ffffff" if selected_joint else "#d7a83e" if tied_joint else "#71859b"
            width = 3 if selected_joint else 2 if tied_joint else 1
            parts.append(
                f'<circle cx="{x}" cy="{y}" r="20" fill="{fill}" stroke="{stroke}" stroke-width="{width}"/>'
            )
            parts.append(f'<text x="{x}" y="{y + 4}" text-anchor="middle" class="small">J{row}{column}</text>')
    parts.extend(
        [
            f'<text x="62" y="406" class="label">selected <tspan class="value">{escape(selected["joint_id"])}</tspan></text>',
            f'<text x="62" y="431" class="label">source <tspan class="value">{escape(selected["source_object_id"])}</tspan></text>',
            f'<text x="62" y="456" class="label">L_D <tspan class="value">{selected["L_D_um"]:.4f} µm</tspan></text>',
            f'<text x="62" y="481" class="label">L_D / h <tspan class="value">{record["configuration"]["L_D_over_h"]:.6f}</tspan></text>',
            '<text x="366" y="136" font-size="16" font-weight="650">Accepted Hex8 dissipation field</text>',
            '<text x="366" y="158" class="small muted">All element values · MPa = MJ/m³</text>',
        ]
    )

    cell = 67
    for layer in range(nz):
        x0 = 378 + layer * 277
        parts.append(f'<text x="{x0}" y="194" class="label">Layer z{layer + 1} / {nz}</text>')
        for row in range(ny):
            for column in range(nx):
                value = values[(layer * ny + row) * nx + column]
                fraction = (value - lower) / (upper - lower)
                fill = _mix((24, 54, 84), (221, 174, 67), fraction)
                x = x0 + column * cell
                y = 214 + (ny - 1 - row) * cell
                parts.append(
                    f'<rect x="{x}" y="{y}" width="{cell - 7}" height="{cell - 7}" rx="5" '
                    f'fill="{fill}" stroke="#71859b" stroke-width="1"/>'
                )
                parts.append(f'<text x="{x + 30}" y="{y + 27}" text-anchor="middle" class="value">{value:.6f}</text>')
                parts.append(f'<text x="{x + 30}" y="{y + 45}" text-anchor="middle" class="small muted">e{column + 1},{row + 1}</text>')

    parts.extend(
        [
            f'<text x="366" y="457" class="label">peak dissipation <tspan class="value">{record["results"]["dW_peak_MPa"]:.6f} MPa</tspan></text>',
            f'<text x="366" y="482" class="label">mean dissipation <tspan class="value">{record["results"]["dW_mean_MPa"]:.6f} MPa</tspan></text>',
            f'<text x="655" y="457" class="label">shear range <tspan class="value">{record["results"]["engineering_shear_range"]:.6f}</tspan></text>',
            f'<text x="655" y="482" class="label">calibration screen <tspan class="value">{record["results"]["Syed_calibration_screen_cycles"]:,.0f} cycles</tspan></text>',
            '<text x="42" y="548" class="small muted">Synthetic map and regular block. Only stable identity and L_D cross the handoff; the cycle count is calibration-specific, not predictive life.</text>',
        ]
    )
    return _svg_document(
        "Design-linked solder screening output",
        "A synthetic three-by-three joint map highlights stable joint SYNTH J00, then two three-by-three heatmaps show all 18 checked Hex8 dissipation values. The displayed cycle count is a calibration-specific screen, not predictive package life.",
        "\n".join(f"  {part}" for part in parts),
        height=580,
    )


def _line_points(
    values: list[float],
    phases: list[float],
    *,
    left: float,
    top: float,
    width: float,
    height: float,
    minimum: float,
    maximum: float,
) -> str:
    if len(values) != len(phases) or not values:
        raise MediaBuildError("ETV line series is empty or misaligned")
    if not all(math.isfinite(float(value)) for value in (*values, *phases)):
        raise MediaBuildError("ETV line series contains a non-finite value")
    points = []
    for phase, value in zip(phases, values):
        x = left + float(phase) * width
        y = top + (maximum - float(value)) / (maximum - minimum) * height
        points.append(f"{x:.2f},{y:.2f}")
    return " ".join(points)


def _etv_snapshot(
    mesh: dict[str, Any],
    result: dict[str, Any],
    *,
    left: float,
    top: float,
    label: str,
    color: str,
    size: float = 116.0,
) -> list[str]:
    coordinates = np.asarray(mesh["coordinates_m"], dtype=float)
    connectivity = np.asarray(mesh["connectivity"], dtype=int)
    retained = result["last_cycle"]
    displacement = np.asarray(retained["peak_displacement_m"], dtype=float).reshape(-1, 2)
    if coordinates.shape != (9, 2) or displacement.shape != coordinates.shape or connectivity.shape != (4, 4):
        raise MediaBuildError("ETV snapshot is not the reviewed nine-node, four-element state")
    if not np.all(np.isfinite(displacement)):
        raise MediaBuildError("ETV snapshot displacement contains a non-finite value")

    deformation_scale = 10.0
    width = float(np.ptp(coordinates[:, 0]))
    height = float(np.ptp(coordinates[:, 1]))
    deformed = coordinates + deformation_scale * displacement

    def point(node: int) -> tuple[float, float]:
        x = left + deformed[node, 0] / width * size
        y = top + size - deformed[node, 1] / height * size
        return x, y

    temperature = float(retained["peak_local_temperature_C"])
    # A neutral, uniform fill keeps the deformed mesh from reading as a
    # spatial temperature contour; temperature is scalar in this model.
    fill = "#26384c"
    parts = [
        f'<text x="{left}" y="{top - 18}" class="label" font-weight="650">{escape(label)}</text>',
        f'<rect x="{left}" y="{top}" width="{size}" height="{size}" fill="none" stroke="#647890" stroke-dasharray="4 4"/>',
    ]
    top_elements = {int(index) for index in mesh["top_element_indices"]}
    for element_index, nodes in enumerate(connectivity):
        polygon = " ".join(
            f"{x:.2f},{y:.2f}" for x, y in (point(int(node)) for node in nodes)
        )
        stroke = "#f4d27c" if element_index in top_elements else "#d8e5f4"
        stroke_width = "2" if element_index in top_elements else "1.2"
        parts.append(
            f'<polygon points="{polygon}" fill="{fill}" fill-opacity=".72" stroke="{stroke}" stroke-width="{stroke_width}"/>'
        )
    for node in range(len(coordinates)):
        x, y = point(node)
        parts.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="2.1" fill="{color}"/>')
    top_displacement_um = float(retained["peak_top_edge_displacement_x_m"]) * 1.0e6
    parts.extend(
        [
            f'<text x="{left}" y="{top + size + 22}" class="value">{temperature:.2f} °C</text>',
            f'<text x="{left}" y="{top + size + 42}" class="small muted">prescribed uₓ = {top_displacement_um:.3f} µm</text>',
        ]
    )
    return parts


def _etv_svg(record: dict[str, Any]) -> str:
    mesh = record["inputs"]["mesh"]
    slow = record["results"]["slow_cycle"]
    fast = record["results"]["fast_cycle"]
    quasi = fast["quasisteady"]
    transient = fast["lumped_transient"]
    phases = [float(value) for value in quasi["last_cycle"]["phase_fraction"]]
    chamber = [float(value) for value in quasi["last_cycle"]["chamber_temperature_C"]]
    quasi_temperature = [float(value) for value in quasi["last_cycle"]["local_temperature_C"]]
    transient_temperature = [float(value) for value in transient["last_cycle"]["local_temperature_C"]]
    plot_left, plot_top, plot_width, plot_height = 64.0, 148.0, 500.0, 226.0
    minimum_temperature, maximum_temperature = -40.0, 160.0

    parts = [
        '<text x="42" y="46" font-size="24" font-weight="700">One-second solder-cycle response</text>',
        '<text x="42" y="72" class="muted" font-size="13">Retained second-cycle states · 0.1 mm SAC305 plane-strain block · 2 × 2 Quad4</text>',
        '<line x1="42" y1="94" x2="918" y2="94" stroke="#33475f"/>',
        '<text x="42" y="119" font-size="16" font-weight="650">Computed local-temperature path</text>',
        '<text x="564" y="119" text-anchor="end" class="small muted">cycle phase</text>',
        '<text x="64" y="139" class="small muted">°C</text>',
    ]
    for tick in (-40, 0, 40, 80, 120, 160):
        y = plot_top + (maximum_temperature - tick) / (maximum_temperature - minimum_temperature) * plot_height
        parts.append(f'<line x1="{plot_left}" y1="{y:.2f}" x2="{plot_left + plot_width}" y2="{y:.2f}" stroke="#263852"/>')
        parts.append(f'<text x="{plot_left - 10}" y="{y + 4:.2f}" text-anchor="end" class="small muted">{tick}</text>')
    for tick in (0.0, 0.25, 0.5, 0.75, 1.0):
        x = plot_left + tick * plot_width
        parts.append(f'<line x1="{x:.2f}" y1="{plot_top}" x2="{x:.2f}" y2="{plot_top + plot_height}" stroke="#1c2e44"/>')
        parts.append(f'<text x="{x:.2f}" y="{plot_top + plot_height + 22}" text-anchor="middle" class="small muted">{tick:g}</text>')
    series = (
        (chamber, "#7d8fa6", "5 5", "Chamber input", None),
        (quasi_temperature, "#48a6da", "", "Quasisteady", "circle"),
        (transient_temperature, "#edc76a", "9 3 2 3", "Lumped transient", "square"),
    )
    for values, color, dash, _label, marker in series:
        points = _line_points(
            values,
            phases,
            left=plot_left,
            top=plot_top,
            width=plot_width,
            height=plot_height,
            minimum=minimum_temperature,
            maximum=maximum_temperature,
        )
        dash_attribute = f' stroke-dasharray="{dash}"' if dash else ""
        parts.append(f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="2.5"{dash_attribute}/>' )
        if marker:
            for point in points.split():
                x, y = point.split(",")
                if marker == "circle":
                    parts.append(f'<circle cx="{x}" cy="{y}" r="3" fill="#08111f" stroke="{color}" stroke-width="2"/>')
                else:
                    parts.append(f'<rect x="{float(x) - 3:.2f}" y="{float(y) - 3:.2f}" width="6" height="6" fill="#08111f" stroke="{color}" stroke-width="2"/>')
    legend_x = 66
    for _values, color, dash, label, marker in series:
        dash_attribute = f' stroke-dasharray="{dash}"' if dash else ""
        parts.append(f'<line x1="{legend_x}" y1="422" x2="{legend_x + 22}" y2="422" stroke="{color}" stroke-width="3"{dash_attribute}/>')
        if marker == "circle":
            parts.append(f'<circle cx="{legend_x + 11}" cy="422" r="3" fill="#08111f" stroke="{color}" stroke-width="2"/>')
        elif marker == "square":
            parts.append(f'<rect x="{legend_x + 8}" y="419" width="6" height="6" fill="#08111f" stroke="{color}" stroke-width="2"/>')
        parts.append(f'<text x="{legend_x + 30}" y="426" class="small muted">{label}</text>')
        legend_x += 145

    parts.extend(
        [
            '<text x="620" y="119" font-size="16" font-weight="650">Peak-temperature mechanics states</text>',
            '<text x="620" y="140" class="small muted">Free DOFs solved · top displacement prescribed</text>',
        ]
    )
    parts.extend(_etv_snapshot(mesh, quasi, left=620.0, top=181.0, label="Quasisteady", color="#48a6da"))
    parts.extend(_etv_snapshot(mesh, transient, left=790.0, top=181.0, label="Lumped transient", color="#edc76a"))
    parts.append('<text x="620" y="366" class="small muted">Dashed: undeformed · deformation ×10</text>')
    parts.append('<text x="620" y="388" class="small muted">Gold outline: sampled top-element row</text>')

    parts.extend(
        [
            '<rect x="42" y="458" width="876" height="190" rx="4" fill="#0e1c2d" stroke="#344961"/>',
            '<text x="62" y="486" font-size="15" font-weight="650">Second-cycle accumulated inelastic energy density</text>',
            '<text x="898" y="486" text-anchor="end" class="small muted">top-layer Gauss-point mean · MPa = MJ/m³</text>',
        ]
    )
    sensitivity = float(fast["relative_energy_difference_percent"])
    sensitivity_label = f"-{abs(sensitivity):.2f}%" if sensitivity < 0.0 else f"+{sensitivity:.2f}%"
    slow_sensitivity = float(slow["relative_energy_difference_percent"])
    slow_sensitivity_label = f"-{abs(slow_sensitivity):.4f}%" if slow_sensitivity < 0.0 else f"+{slow_sensitivity:.4f}%"
    cards = (
        (62, "Quasisteady · 1 s", f'{float(quasi["dW_last_MPa"]):.6f}', "MPa", "#48a6da"),
        (342, "Lumped transient · 1 s", f'{float(transient["dW_last_MPa"]):.6f}', "MPa", "#edc76a"),
        (622, "Energy-density change", sensitivity_label, "lumped relative to quasisteady", "#f0b35b"),
    )
    for left, label, value, unit, color in cards:
        parts.extend(
            [
                f'<rect x="{left}" y="506" width="256" height="82" rx="3" fill="#0a1524" stroke="#2e425a"/>',
                f'<text x="{left + 15}" y="530" class="small muted">{escape(label)}</text>',
                f'<text x="{left + 15}" y="560" font-size="23" font-weight="700" fill="{color}">{escape(value)}</text>',
                f'<text x="{left + 15}" y="579" class="small muted">{escape(unit)}</text>',
            ]
        )
    parts.extend(
        [
            f'<text x="62" y="618" class="small muted">Slow-cycle control · 1,600 s: {float(slow["quasisteady"]["dW_last_MPa"]):.6f} vs {float(slow["lumped_transient"]["dW_last_MPa"]):.6f} MPa ({slow_sensitivity_label})</text>',
            '<text x="42" y="681" class="small muted">Partitioned uniform-temperature sensitivity; not a spatial thermal field, monolithic φ–T–u solve, accuracy ranking, or measured-device result.</text>',
        ]
    )
    return _svg_document(
        "One-second partitioned solder-cycle response",
        "A retained second-cycle temperature path and two deformed-mesh solver snapshots compare quasisteady and backward-Euler lumped-temperature treatments for the same checked plane-strain SAC305 mechanics model. The temperature is uniform by construction, and deformation is magnified ten times.",
        "\n".join(f"  {part}" for part in parts),
        height=710,
    )


def _etv_mobile_svg(record: dict[str, Any]) -> str:
    mesh = record["inputs"]["mesh"]
    slow = record["results"]["slow_cycle"]
    fast = record["results"]["fast_cycle"]
    quasi = fast["quasisteady"]
    transient = fast["lumped_transient"]
    phases = [float(value) for value in quasi["last_cycle"]["phase_fraction"]]
    chamber = [float(value) for value in quasi["last_cycle"]["chamber_temperature_C"]]
    quasi_temperature = [float(value) for value in quasi["last_cycle"]["local_temperature_C"]]
    transient_temperature = [float(value) for value in transient["last_cycle"]["local_temperature_C"]]
    plot_left, plot_top, plot_width, plot_height = 48.0, 142.0, 328.0, 210.0
    minimum_temperature, maximum_temperature = -40.0, 160.0
    parts = [
        '<style>.small { font-size: 14px; } .label { font-size: 15px; } .value { font-size: 15px; } .mobile-note { font-size: 13px; }</style>',
        '<text x="22" y="40" font-size="21" font-weight="700">One-second solder-cycle output</text>',
        '<text x="22" y="66" class="muted" font-size="14">Second-cycle states · 0.1 mm SAC305 · 2 × 2 Quad4</text>',
        '<line x1="22" y1="88" x2="378" y2="88" stroke="#33475f"/>',
        '<text x="22" y="118" font-size="18" font-weight="650">Computed local-temperature path</text>',
        '<text x="48" y="136" class="small muted">°C</text>',
        '<text x="376" y="136" text-anchor="end" class="small muted">cycle phase</text>',
    ]
    for tick in (-40, 0, 40, 80, 120, 160):
        y = plot_top + (maximum_temperature - tick) / (maximum_temperature - minimum_temperature) * plot_height
        parts.append(f'<line x1="{plot_left}" y1="{y:.2f}" x2="{plot_left + plot_width}" y2="{y:.2f}" stroke="#263852"/>')
        parts.append(f'<text x="{plot_left - 8}" y="{y + 5:.2f}" text-anchor="end" class="small muted">{tick}</text>')
    for tick in (0.0, 0.25, 0.5, 0.75, 1.0):
        x = plot_left + tick * plot_width
        parts.append(f'<line x1="{x:.2f}" y1="{plot_top}" x2="{x:.2f}" y2="{plot_top + plot_height}" stroke="#1c2e44"/>')
        parts.append(f'<text x="{x:.2f}" y="{plot_top + plot_height + 22}" text-anchor="middle" class="small muted">{tick:g}</text>')
    series = (
        (chamber, "#7d8fa6", "5 5", "Chamber input", None),
        (quasi_temperature, "#48a6da", "", "Quasisteady", "circle"),
        (transient_temperature, "#edc76a", "9 3 2 3", "Lumped transient", "square"),
    )
    for values, color, dash, _label, marker in series:
        points = _line_points(
            values,
            phases,
            left=plot_left,
            top=plot_top,
            width=plot_width,
            height=plot_height,
            minimum=minimum_temperature,
            maximum=maximum_temperature,
        )
        dash_attribute = f' stroke-dasharray="{dash}"' if dash else ""
        parts.append(f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="2.5"{dash_attribute}/>')
        if marker:
            for point in points.split():
                x, y = point.split(",")
                if marker == "circle":
                    parts.append(f'<circle cx="{x}" cy="{y}" r="3" fill="#08111f" stroke="{color}" stroke-width="2"/>')
                else:
                    parts.append(f'<rect x="{float(x) - 3:.2f}" y="{float(y) - 3:.2f}" width="6" height="6" fill="#08111f" stroke="{color}" stroke-width="2"/>')
    legend_positions = ((48, 400), (210, 400), (48, 428))
    for (_values, color, dash, label, marker), (legend_x, legend_y) in zip(series, legend_positions):
        dash_attribute = f' stroke-dasharray="{dash}"' if dash else ""
        parts.append(f'<line x1="{legend_x}" y1="{legend_y}" x2="{legend_x + 22}" y2="{legend_y}" stroke="{color}" stroke-width="3"{dash_attribute}/>')
        if marker == "circle":
            parts.append(f'<circle cx="{legend_x + 11}" cy="{legend_y}" r="3" fill="#08111f" stroke="{color}" stroke-width="2"/>')
        elif marker == "square":
            parts.append(f'<rect x="{legend_x + 8}" y="{legend_y - 3}" width="6" height="6" fill="#08111f" stroke="{color}" stroke-width="2"/>')
        parts.append(f'<text x="{legend_x + 30}" y="{legend_y + 5}" class="small muted">{label}</text>')

    parts.extend(
        [
            '<line x1="22" y1="454" x2="378" y2="454" stroke="#33475f"/>',
            '<text x="22" y="486" font-size="18" font-weight="650">Peak-temperature mechanics states</text>',
            '<text x="22" y="510" class="small muted">Free DOFs solved · top displacement prescribed</text>',
        ]
    )
    parts.extend(_etv_snapshot(mesh, quasi, left=85.0, top=558.0, label="Quasisteady", color="#48a6da", size=230.0))
    parts.append('<line x1="22" y1="850" x2="378" y2="850" stroke="#263852"/>')
    parts.extend(_etv_snapshot(mesh, transient, left=85.0, top=884.0, label="Lumped transient", color="#edc76a", size=230.0))
    parts.extend(
        [
            '<text x="22" y="1172" class="small muted">Dashed: undeformed · deformation ×10</text>',
            '<text x="22" y="1194" class="small muted">Gold outline: top-layer aggregation region</text>',
            '<rect x="22" y="1222" width="356" height="200" rx="4" fill="#0e1c2d" stroke="#344961"/>',
            '<text x="40" y="1253" font-size="17" font-weight="650">Second-cycle inelastic energy density</text>',
        ]
    )
    sensitivity = float(fast["relative_energy_difference_percent"])
    sensitivity_label = f"-{abs(sensitivity):.2f}%" if sensitivity < 0.0 else f"+{sensitivity:.2f}%"
    slow_sensitivity = float(slow["relative_energy_difference_percent"])
    slow_sensitivity_label = f"-{abs(slow_sensitivity):.4f}%" if slow_sensitivity < 0.0 else f"+{slow_sensitivity:.4f}%"
    parts.extend(
        [
            '<text x="40" y="1288" class="small muted">Quasisteady · 1 s</text>',
            f'<text x="360" y="1288" text-anchor="end" class="value">{float(quasi["dW_last_MPa"]):.6f} MPa</text>',
            '<text x="40" y="1320" class="small muted">Lumped transient · 1 s</text>',
            f'<text x="360" y="1320" text-anchor="end" class="value">{float(transient["dW_last_MPa"]):.6f} MPa</text>',
            '<line x1="40" y1="1340" x2="360" y2="1340" stroke="#2e425a"/>',
            '<text x="40" y="1368" class="label">Energy-density change</text>',
            f'<text x="360" y="1368" text-anchor="end" font-size="22" font-weight="700" fill="#f0b35b">{sensitivity_label}</text>',
            '<text x="40" y="1392" class="mobile-note muted">lumped relative to quasisteady</text>',
            '<text x="22" y="1452" class="small muted">1,600 s control</text>',
            f'<text x="22" y="1476" class="small muted">{float(slow["quasisteady"]["dW_last_MPa"]):.6f} → {float(slow["lumped_transient"]["dW_last_MPa"]):.6f} MPa ({slow_sensitivity_label})</text>',
            '<line x1="22" y1="1504" x2="378" y2="1504" stroke="#33475f"/>',
            '<text x="22" y="1532" class="mobile-note muted">Uniform-temperature sensitivity—not a spatial thermal field,</text>',
            '<text x="22" y="1554" class="mobile-note muted">accuracy ranking, or monolithic φ–T–u solve.</text>',
            '<text x="22" y="1576" class="mobile-note muted">Not a measured-device result.</text>',
        ]
    )
    return _svg_document(
        "One-second partitioned solder-cycle response, portrait layout",
        "A portrait technical figure shows the retained second-cycle temperature path, two magnified deformed-mesh peak states, and the inelastic-energy comparison for the checked plane-strain SAC305 model.",
        "\n".join(f"  {part}" for part in parts),
        width=400,
        height=1604,
    )


def build(output_dir: Path, contract_path: Path) -> dict[str, Any]:
    core = _core_identity()
    solder, design_solder, etv = _verify_simulations()
    output_dir.mkdir(parents=True, exist_ok=True)
    expected = {
        "solder-3d-dissipation.svg": _solder_svg(solder),
        "design-linked-solder-screening.svg": _design_linked_solder_svg(design_solder),
        "etv-partitioned-comparison.svg": _etv_svg(etv),
        "etv-partitioned-comparison-mobile.svg": _etv_mobile_svg(etv),
        "etv-partitioned-record.json": json.dumps(
            etv, indent=2, sort_keys=True, allow_nan=False
        )
        + "\n",
    }
    for name, content in expected.items():
        _atomic_write(output_dir / name, content)

    sources = []
    for case_id, runner, oracle, dependencies in (
        (
            "solder_3d_cycle",
            "examples/solder_3d_cycle/run.py",
            "examples/solder_3d_cycle/expected_results.json",
            (
                "eda_multiphysics/anand_3d.py",
                "eda_multiphysics/_stateful_solve.py",
            ),
        ),
        (
            "design_linked_solder_screening",
            "examples/design_linked_solder_screening/run.py",
            "examples/design_linked_solder_screening/expected_results.json",
            (
                "eda_multiphysics/reliability_3d.py",
                "eda_multiphysics/anand_3d.py",
                "eda_multiphysics/_stateful_solve.py",
                "eda_multiphysics/cases/synthetic_pdn/joints.csv",
            ),
        ),
        (
            "etv_partitioned_cycle",
            "examples/etv_partitioned_cycle/run.py",
            "examples/etv_partitioned_cycle/expected_results.json",
            (
                "eda_multiphysics/etv_fe.py",
                "eda_multiphysics/etv_solder.py",
                "eda_multiphysics/solder_joint.py",
                "eda_multiphysics/_stateful_solve.py",
            ),
        ),
    ):
        sources.append(
            {
                "caseId": case_id,
                "runner": runner,
                "runnerSha256": _sha256(ROOT / runner),
                "oracle": oracle,
                "oracleSha256": _sha256(ROOT / oracle),
                "oraclePassed": True,
                "dependencies": [
                    {"path": path, "sha256": _sha256(ROOT / path)}
                    for path in dependencies
                ],
            }
        )
    contract = {
        "schemaVersion": 3,
        "generatedBy": "web/scripts/render-simulation-media.py",
        "generatorSha256": _sha256(
            ROOT / "web/scripts/render-simulation-media.py"
        ),
        "edaBaseRevision": _git_revision(ROOT),
        "core": core,
        "sources": sources,
        "artifacts": [
            {
                "name": name,
                "uri": f"generated/simulation-media/{name}",
                "mediaType": (
                    "image/svg+xml" if name.endswith(".svg") else "application/json"
                ),
                "sha256": _sha256(output_dir / name),
            }
            for name in expected
        ],
    }
    _atomic_write(contract_path, json.dumps(contract, indent=2, sort_keys=True) + "\n")
    return contract


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    args = parser.parse_args(argv)
    try:
        contract = build(args.output_dir.resolve(), args.contract.resolve())
    except (MediaBuildError, SourceIdentityError, OSError, subprocess.CalledProcessError) as error:
        print(f"simulation-media build failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"artifacts": len(contract["artifacts"]), "status": "valid"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
