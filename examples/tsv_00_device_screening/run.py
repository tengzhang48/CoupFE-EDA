"""Synthetic TSV-to-device screening and provenance demonstration."""
from __future__ import annotations

import argparse
import csv
import html
import json
import sys
from dataclasses import asdict
from pathlib import Path

import numpy as np

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from eda_multiphysics.tsv_device import (
    best_channel_orientation,
    lame_far_field_stress,
    screen_devices,
)


def run():
    """Return baseline/rotated device rows and a deterministic preview scorecard."""
    input_path = Path(__file__).with_name("device_sites.csv")
    with input_path.open(newline="") as stream:
        input_rows = list(csv.DictReader(stream))
    ids = [row["device_id"] for row in input_rows]
    xy = np.array([[float(row["x_um"]), float(row["y_um"])] for row in input_rows])
    carriers = np.array([row["carrier"] for row in input_rows])
    source_ids = np.array([row["source_object_id"] for row in input_rows])
    baseline_angles = np.array([float(row["channel_degrees"]) for row in input_rows])
    stress = lame_far_field_stress(xy, diameter_um=10.0, dT=-250.0)
    baseline = screen_devices(
        ids, xy, stress, carrier=carriers, channel_degrees=baseline_angles,
        threshold=0.05, tsv_id="TSV_0001", source_object_ids=source_ids
    )
    optimized_angles = np.array([
        best_channel_orientation(stress[index], carrier=carriers[index])
        for index in range(len(xy))
    ])
    optimized = screen_devices(
        ids, xy, stress, carrier=carriers, channel_degrees=optimized_angles,
        threshold=0.05, tsv_id="TSV_0001", source_object_ids=source_ids
    )
    peak0 = max(abs(row.mobility_change) for row in baseline)
    peak1 = max(abs(row.mobility_change) for row in optimized)
    violations0 = sum(row.koz_violation for row in baseline)
    violations1 = sum(row.koz_violation for row in optimized)
    scorecard = {
        "example_scope": "synthetic_identity_preserving_integration",
        "model_scope": "classical_lame_far_field_device_screening_proxy",
        "release_validation": False,
        "device_site_provenance": "synthetic_radial_angular_sampling",
        "runtime_inputs": ["device_sites.csv"],
        "fixed_in_code": ["tsv_id", "diameter_um", "thermal_load_C", "wafer", "threshold"],
        "tsv_id": "TSV_0001",
        "diameter_um": 10.0,
        "thermal_load_C": -250.0,
        "wafer": "(001) Si",
        "n_devices": len(ids),
        "threshold": 0.05,
        "baseline_violations": violations0,
        "optimized_violations": violations1,
        "baseline_peak_abs_mobility_change": peak0,
        "optimized_peak_abs_mobility_change": peak1,
        "violation_reduction": 1.0 - violations1 / max(violations0, 1),
        "peak_proxy_reduction": 1.0 - peak1 / max(peak0, 1.0e-30),
        "claim_boundary": (
            "Demonstrates identity-preserving stress-to-device mapping and a deterministic "
            "orientation action. It does not validate near-surface TSV stress, transistor delay, "
            "or a signoff keep-out zone."
        ),
    }
    return baseline, optimized, scorecard


def _write_outputs(output_dir, baseline, optimized, scorecard):
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "device_screening.csv").open("w", newline="") as stream:
        fields = [
            "case", "device_id", "source_object_id", "tsv_id", "x_um", "y_um", "carrier",
            "channel_degrees", "mobility_change", "koz_violation", "distance_um",
            "direction_degrees",
        ]
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for case, rows in (("baseline", baseline), ("orientation_action", optimized)):
            for row in rows:
                data = asdict(row)
                data.pop("stress_mpa")
                writer.writerow({"case": case, **data})
    (output_dir / "evidence.json").write_text(json.dumps(scorecard, indent=2) + "\n")
    _write_svg(output_dir / "device_screening.svg", baseline, optimized, scorecard)


def _write_svg(path, baseline, optimized, scorecard):
    """Write a dependency-free physical device map suitable for reports and reviews."""
    width, height = 960, 460
    centers = ((240, 235), (720, 235))
    scale = 7.4
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" '
        'aria-labelledby="figure-title figure-description">',
        '<title id="figure-title">Synthetic TSV-to-device screening map</title>',
        '<desc id="figure-description">Computed comparison of 32 project-authored synthetic '
        'device sites before and after a deterministic channel-orientation screening action. '
        'The Lamé far-field mobility proxy is an integration demonstration, not experimental '
        'validation or a signoff keep-out zone.</desc>',
        '<rect width="100%" height="100%" fill="#091628"/>',
        '<style>text{font-family:Arial,sans-serif;fill:#dce7f5}.muted{fill:#92a4bb}'
        '.axis{stroke:#334965;stroke-width:1}.channel{stroke:#eef4fb;stroke-width:1.5}</style>',
        '<text x="24" y="30" font-size="18" font-weight="bold">Synthetic TSV-to-device back-annotation</text>',
        '<text x="24" y="50" font-size="12" class="muted">10 µm TSV · synthetic device sites · 5% mobility-proxy threshold · demonstration</text>',
    ]
    for (cx, cy), title, rows in zip(centers, ("Baseline [100] channels", "Orientation-screening action"),
                                     (baseline, optimized)):
        parts.extend([
            f'<text x="{cx}" y="82" text-anchor="middle" font-size="16">{title}</text>',
            f'<line x1="{cx-180}" y1="{cy}" x2="{cx+180}" y2="{cy}" class="axis"/>',
            f'<line x1="{cx}" y1="{cy-170}" x2="{cx}" y2="{cy+170}" class="axis"/>',
            f'<circle cx="{cx}" cy="{cy}" r="{0.5 * scorecard["diameter_um"] * scale}" '
            'fill="#b87333" stroke="#f2b37f" stroke-width="2"/>',
            f'<text x="{cx}" y="{cy+4}" text-anchor="middle" font-size="10">TSV</text>',
        ])
        for row in rows:
            x, y = cx + row.x_um * scale, cy - row.y_um * scale
            color = "#ff6577" if row.koz_violation else "#35d0ba"
            shape = (f'<circle cx="{x:.2f}" cy="{y:.2f}" r="5"' if row.carrier == "n"
                     else f'<rect x="{x-5:.2f}" y="{y-5:.2f}" width="10" height="10"')
            tooltip = html.escape(
                f"{row.device_id} / {row.source_object_id}; {row.carrier}MOS; "
                f"channel={row.channel_degrees:g} deg; Δμ/μ={row.mobility_change:+.4f}"
            )
            parts.append(f'<g><title>{tooltip}</title>{shape} fill="{color}" '
                         'stroke="#091628"/></g>')
            angle = np.deg2rad(row.channel_degrees)
            dx, dy = 8 * np.cos(angle), -8 * np.sin(angle)
            parts.append(f'<line x1="{x-dx:.2f}" y1="{y-dy:.2f}" x2="{x+dx:.2f}" '
                         f'y2="{y+dy:.2f}" class="channel"/>')
    parts.extend([
        '<circle cx="335" cy="430" r="5" fill="#35d0ba"/><text x="347" y="434" font-size="12">within threshold</text>',
        '<circle cx="480" cy="430" r="5" fill="#ff6577"/><text x="492" y="434" font-size="12">KOZ violation</text>',
        '<circle cx="620" cy="430" r="5" fill="#35d0ba"/><text x="632" y="434" font-size="12">nMOS</text>',
        '<rect x="690" y="425" width="10" height="10" fill="#35d0ba"/><text x="706" y="434" font-size="12">pMOS</text>',
        '</svg>',
    ])
    path.write_text("\n".join(parts) + "\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, help="optional CSV/evidence output directory")
    args = parser.parse_args(argv)
    baseline, optimized, scorecard = run()
    if args.output_dir is not None:
        _write_outputs(args.output_dir, baseline, optimized, scorecard)
    print("TSV screening demonstration (synthetic sites, fixed geometry, cited coefficients, proxy stress)")
    print(json.dumps(scorecard, indent=2))


if __name__ == "__main__":
    main()
