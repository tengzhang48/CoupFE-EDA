"""Focused tests for the solver-visualization provenance contract."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from eda_multiphysics.visual_evidence import (
    VisualEvidenceValidationError,
    validate_manifest,
)


ROOT = Path(__file__).resolve().parents[1]


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _bundle(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    payloads = {
        "field/radial_field.csv": b"radius_um,stress_mpa,displacement_nm\n15,400,0\n",
        "summary.json": b'{"peak_stress_mpa":400.0}\n',
        "stress.png": b"\x89PNG\r\n\x1a\nsolver-derived-test-image",
        "cooling.webm": b"\x1aE\xdf\xa3solver-derived-test-video",
    }
    roles = {
        "field/radial_field.csv": "raw-field",
        "summary.json": "summary",
        "stress.png": "image",
        "cooling.webm": "video",
    }
    artifacts = []
    for relative, payload in payloads.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        artifacts.append(
            {
                "path": relative,
                "role": roles[relative],
                "size_bytes": len(payload),
                "sha256": _sha256(payload),
            }
        )

    manifest: dict[str, object] = {
        "schema_version": 1,
        "case": {
            "id": "tsv-prescribed-cooling",
            "description": "Axisymmetric TSV cooling-sweep field evidence",
        },
        "claim_boundary": (
            "Solver-derived component verification; not experimental device validation."
        ),
        "revisions": {"eda": "a" * 40, "core": "b" * 40},
        "command": [
            "python",
            "run_tsv_field.py",
            "--mesh-points",
            "2400",
            "--output-dir",
            "evidence",
        ],
        "field": {
            "topology": "axisymmetric-line2",
            "mesh": {
                "name": "radial-tsv-2400",
                "spatial_dimension": 1,
                "node_count": 2400,
                "element_count": 2399,
            },
            "degree_of_freedom_count": 2400,
            "components": [
                {"name": "radial_stress", "unit": "MPa", "location": "node"},
                {
                    "name": "radial_displacement",
                    "unit": "nm",
                    "location": "node",
                },
            ],
            "load_steps": [
                {
                    "index": index,
                    "name": f"cooling-{index}",
                    "value": -50.0 * index,
                    "unit": "K",
                }
                for index in range(9)
            ],
        },
        "renderer": {
            "name": "coupfe-eda-axisymmetric-renderer",
            "version": "1",
            "configuration": {
                "reconstruction": "axisymmetric-revolution",
                "frame_mapping": {"radial": "x", "axis": "z"},
                "color": {"palette": "turbo", "range_mpa": [0.0, 400.0]},
                "video": {
                    "width": 1280,
                    "height": 720,
                    "fps": 12,
                    "codec": "vp9",
                },
            },
            "interpretation": (
                "Frames show a prescribed cooling sweep, not a transient simulation."
            ),
        },
        "artifacts": artifacts,
    }
    manifest_path = tmp_path / "visual-evidence.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest_path, manifest


def _rewrite(path: Path, manifest: dict[str, object]) -> None:
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def test_valid_bundle_and_cli(tmp_path):
    manifest_path, manifest = _bundle(tmp_path)
    assert validate_manifest(manifest_path) == manifest

    completed = subprocess.run(
        [sys.executable, "-m", "eda_multiphysics.visual_evidence", str(manifest_path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        "artifact_count": 4,
        "case_id": "tsv-prescribed-cooling",
        "schema_version": 1,
        "status": "valid",
    }


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda data: data.pop("claim_boundary"), "missing=\\['claim_boundary'\\]"),
        (lambda data: data.update({"unreviewed": True}), "extra=\\['unreviewed'\\]"),
        (
            lambda data: data["revisions"].update({"core": "abc123"}),
            "40-hex revision",
        ),
        (lambda data: data.update({"command": "python solve.py"}), "command must be a list"),
        (
            lambda data: data["field"].update({"components": []}),
            "field.components must not be empty",
        ),
        (
            lambda data: data["field"]["load_steps"].reverse(),
            "strictly increasing",
        ),
        (
            lambda data: data["renderer"].update(
                {"interpretation": "Frames are physical time integration."}
            ),
            "not transient",
        ),
    ],
)
def test_manifest_metadata_fails_closed(tmp_path, mutation, message):
    manifest_path, manifest = _bundle(tmp_path)
    mutation(manifest)
    _rewrite(manifest_path, manifest)
    with pytest.raises(VisualEvidenceValidationError, match=message):
        validate_manifest(manifest_path)


@pytest.mark.parametrize(
    "unsafe",
    [
        "/tmp/raw.csv",
        "C:/tmp/raw.csv",
        "../raw.csv",
        "field/../../raw.csv",
        "field\\raw.csv",
        "raw.csv\n",
    ],
)
def test_artifact_paths_must_be_safe_relative_posix_paths(tmp_path, unsafe):
    manifest_path, manifest = _bundle(tmp_path)
    manifest["artifacts"][0]["path"] = unsafe
    _rewrite(manifest_path, manifest)
    with pytest.raises(VisualEvidenceValidationError, match="relative POSIX path|traversal"):
        validate_manifest(manifest_path)


def test_artifact_roles_are_exact(tmp_path):
    manifest_path, manifest = _bundle(tmp_path)
    manifest["artifacts"][0]["role"] = "summary"
    _rewrite(manifest_path, manifest)
    with pytest.raises(VisualEvidenceValidationError, match="exactly one"):
        validate_manifest(manifest_path)


@pytest.mark.parametrize("change", ["missing", "extra"])
def test_artifact_inventory_is_exact(tmp_path, change):
    manifest_path, _manifest = _bundle(tmp_path)
    if change == "missing":
        (tmp_path / "stress.png").unlink()
    else:
        (tmp_path / "unreviewed.txt").write_text("not declared", encoding="utf-8")
    with pytest.raises(VisualEvidenceValidationError, match="artifact inventory mismatch"):
        validate_manifest(manifest_path)


@pytest.mark.parametrize(
    ("field", "message"),
    [("size_bytes", "size mismatch"), ("sha256", "SHA-256 mismatch")],
)
def test_artifact_size_and_digest_are_verified(tmp_path, field, message):
    manifest_path, manifest = _bundle(tmp_path)
    if field == "size_bytes":
        manifest["artifacts"][0][field] += 1
    else:
        manifest["artifacts"][0][field] = "0" * 64
    _rewrite(manifest_path, manifest)
    with pytest.raises(VisualEvidenceValidationError, match=message):
        validate_manifest(manifest_path)


def test_duplicate_json_keys_are_rejected(tmp_path):
    manifest_path, _manifest = _bundle(tmp_path)
    manifest_path.write_text(
        '{"schema_version":1,"schema_version":1}\n', encoding="utf-8"
    )
    with pytest.raises(VisualEvidenceValidationError, match="repeats JSON key"):
        validate_manifest(manifest_path)


def test_cli_returns_nonzero_for_invalid_bundle(tmp_path):
    manifest_path, _manifest = _bundle(tmp_path)
    (tmp_path / "summary.json").write_text("tampered", encoding="utf-8")
    completed = subprocess.run(
        [sys.executable, "-m", "eda_multiphysics.visual_evidence", str(manifest_path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 1
    assert "visual evidence validation failed" in completed.stderr
