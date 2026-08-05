"""Render website figures from checked CoupFE-EDA simulation runners.

The script executes the named EDA examples, verifies their retained numerical
oracles, and writes three accessible SVG figures plus a checksum/source contract.
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
    return solder, design_solder, etv


def _mix(left: tuple[int, int, int], right: tuple[int, int, int], amount: float) -> str:
    amount = min(1.0, max(0.0, amount))
    channels = [round(a + (b - a) * amount) for a, b in zip(left, right)]
    return "#" + "".join(f"{channel:02x}" for channel in channels)


def _svg_document(title: str, description: str, body: str, *, height: int = 560) -> str:
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="960" height="{height}" viewBox="0 0 960 {height}" role="img" aria-labelledby="figure-title figure-description">
  <title id="figure-title">{escape(title)}</title>
  <desc id="figure-description">{escape(description)}</desc>
  <rect width="960" height="{height}" fill="#08111f"/>
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


def _bar(x: float, baseline: float, width: float, value: float, maximum: float, height: float, fill: str, pattern: bool) -> str:
    bar_height = value / maximum * height
    y = baseline - bar_height
    overlay = f'<rect x="{x}" y="{y}" width="{width}" height="{bar_height}" fill="url(#transient-hatch)" opacity=".45"/>' if pattern else ""
    return (
        f'<rect x="{x}" y="{y}" width="{width}" height="{bar_height}" rx="5" fill="{fill}"/>{overlay}'
        f'<text x="{x + width / 2}" y="{y - 9}" text-anchor="middle" class="value">{value:.3f}</text>'
    )


def _etv_svg(record: dict[str, Any]) -> str:
    slow = record["results"]["slow_cycle"]
    fast = record["results"]["fast_cycle"]
    cases = (("Slow · 1,600 s", slow), ("Fast · 1 s", fast))
    parts = [
        '<defs><pattern id="transient-hatch" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="8" stroke="#ffffff" stroke-width="2"/></pattern></defs>',
        '<text x="42" y="46" font-size="24" font-weight="700">Partitioned ETV model comparison</text>',
        '<text x="42" y="72" class="muted" font-size="13">Checked CoupFE mechanics · quasisteady versus backward-Euler lumped temperature · second-cycle values</text>',
    ]
    panel_specs = ((42, "Last-cycle inelastic energy", "MPa = MJ/m³", 0.8, 250), (510, "Peak temperature", "°C", 160.0, 250))
    for panel_index, (left, title, unit, maximum, chart_height) in enumerate(panel_specs):
        top, baseline = 132, 132 + chart_height
        parts.extend(
            [
                f'<text x="{left}" y="112" font-size="16" font-weight="650">{title}</text>',
                f'<text x="{left + 402}" y="112" text-anchor="end" class="small muted">{unit}</text>',
                f'<line x1="{left}" y1="{baseline}" x2="{left + 408}" y2="{baseline}" class="axis"/>',
            ]
        )
        for tick in range(5):
            fraction = tick / 4
            y = baseline - fraction * chart_height
            label = fraction * maximum
            parts.append(f'<line x1="{left}" y1="{y}" x2="{left + 408}" y2="{y}" stroke="#263852" stroke-width="1"/>')
            parts.append(f'<text x="{left - 8}" y="{y + 4}" text-anchor="end" class="small muted">{label:.1f}</text>')
        for case_index, (label, case) in enumerate(cases):
            center = left + 115 + case_index * 205
            if panel_index == 0:
                quasi = float(case["quasisteady"]["dW_last_MPa"])
                transient = float(case["lumped_transient"]["dW_last_MPa"])
            else:
                quasi = float(case["quasisteady"]["temperature_C_max"])
                transient = float(case["lumped_transient"]["temperature_C_max"])
            parts.append(_bar(center - 56, baseline, 48, quasi, maximum, chart_height, "#3b82b8", False))
            parts.append(_bar(center + 8, baseline, 48, transient, maximum, chart_height, "#d7a83e", True))
            parts.append(f'<text x="{center}" y="{baseline + 25}" text-anchor="middle" class="label">{label}</text>')
    parts.extend(
        [
            '<rect x="42" y="458" width="18" height="12" rx="2" fill="#3b82b8"/><text x="70" y="469" class="label">Quasisteady</text>',
            '<rect x="190" y="458" width="18" height="12" rx="2" fill="#d7a83e"/><rect x="190" y="458" width="18" height="12" fill="url(#transient-hatch)"/><text x="218" y="469" class="label">Lumped transient</text>',
            f'<text x="42" y="514" class="label">Fast-cycle energy difference: {fast["relative_energy_difference_percent"]:.2f}% · slow-cycle difference: {slow["relative_energy_difference_percent"]:.3f}%</text>',
            '<text x="42" y="538" class="small muted">Uniform lagged thermal feedback; this is not a monolithic φ–T–u formulation or measured-device validation.</text>',
        ]
    )
    return _svg_document(
        "Partitioned ETV model comparison",
        "Two grouped-bar panels compare quasisteady and backward-Euler lumped-temperature assumptions for the checked slow and fast CoupFE-EDA mechanics cases. The fast case shows a large energy difference and a lower lumped-transient peak temperature; the slow case nearly agrees.",
        "\n".join(f"  {part}" for part in parts),
    )


def build(output_dir: Path, contract_path: Path) -> dict[str, Any]:
    core = _core_identity()
    solder, design_solder, etv = _verify_simulations()
    output_dir.mkdir(parents=True, exist_ok=True)
    expected = {
        "solder-3d-dissipation.svg": _solder_svg(solder),
        "design-linked-solder-screening.svg": _design_linked_solder_svg(design_solder),
        "etv-partitioned-comparison.svg": _etv_svg(etv),
    }
    for name, content in expected.items():
        _atomic_write(output_dir / name, content)

    sources = []
    for case_id, runner, oracle in (
        ("solder_3d_cycle", "examples/solder_3d_cycle/run.py", "examples/solder_3d_cycle/expected_results.json"),
        (
            "design_linked_solder_screening",
            "examples/design_linked_solder_screening/run.py",
            "examples/design_linked_solder_screening/expected_results.json",
        ),
        ("etv_partitioned_cycle", "examples/etv_partitioned_cycle/run.py", "examples/etv_partitioned_cycle/expected_results.json"),
    ):
        sources.append(
            {
                "caseId": case_id,
                "runner": runner,
                "runnerSha256": _sha256(ROOT / runner),
                "oracle": oracle,
                "oracleSha256": _sha256(ROOT / oracle),
                "oraclePassed": True,
            }
        )
    contract = {
        "schemaVersion": 1,
        "generatedBy": "web/scripts/render-simulation-media.py",
        "edaBaseRevision": _git_revision(ROOT),
        "core": core,
        "sources": sources,
        "artifacts": [
            {
                "name": name,
                "uri": f"generated/simulation-media/{name}",
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
