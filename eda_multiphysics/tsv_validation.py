"""Fail-closed benchmark manifests and release scorecards for the TSV device workflow."""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path


SCHEMA_VERSION = 1
RELEASE_CATEGORIES = (
    "numerical_mechanics",
    "global_experiment",
    "local_experiment",
    "multilevel_accuracy",
    "conservation",
    "performance",
    "device_mapping",
    "eda_semantics",
    "design_action",
    "reproducibility",
)
_STATES = {"passed", "blocked", "failed", "not_started"}
_ROLES = {"calibration", "validation", "model_verification", "external_comparison"}
_DATA_STATUS = {"frozen", "definition_only", "blocked"}


def manifest_sha256(manifest):
    """SHA-256 over canonical JSON, excluding a top-level self-referential hash field."""
    data = deepcopy(dict(manifest))
    data.pop("manifest_sha256", None)
    payload = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _require(mapping, fields, context):
    missing = [field for field in fields if field not in mapping]
    if missing:
        raise ValueError(f"{context} missing required fields: {missing}")


def validate_benchmark_manifest(manifest):
    """Validate the repository's benchmark-manifest contract without an optional JSON-schema lib."""
    if not isinstance(manifest, dict):
        raise ValueError("benchmark manifest must be an object")
    _require(manifest, (
        "schema_version", "benchmark_id", "title", "source", "calibration_role",
        "data_status", "geometry", "thermal_history", "coordinate_convention",
        "quantities", "claim_boundary",
    ), "benchmark manifest")
    if manifest["schema_version"] != SCHEMA_VERSION:
        raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
    if manifest["calibration_role"] not in _ROLES:
        raise ValueError(f"calibration_role must be one of {sorted(_ROLES)}")
    if manifest["data_status"] not in _DATA_STATUS:
        raise ValueError(f"data_status must be one of {sorted(_DATA_STATUS)}")
    source = manifest["source"]
    _require(source, ("citation", "doi", "locator"), "source")
    if not str(source["doi"]).startswith("10."):
        raise ValueError("source.doi must be a DOI")
    if not isinstance(manifest["quantities"], list) or not manifest["quantities"]:
        raise ValueError("quantities must be a non-empty list")
    for index, quantity in enumerate(manifest["quantities"]):
        _require(quantity, ("name", "value", "unit", "uncertainty", "use"),
                 f"quantities[{index}]")
        if not str(quantity["unit"]).strip():
            raise ValueError(f"quantities[{index}].unit must be non-empty")
    expected = manifest.get("manifest_sha256")
    if expected is not None and expected != manifest_sha256(manifest):
        raise ValueError("manifest_sha256 does not match canonical manifest content")
    return manifest


def load_benchmark_manifest(path):
    """Load and validate a benchmark JSON file."""
    path = Path(path)
    with path.open(encoding="utf-8") as stream:
        return validate_benchmark_manifest(json.load(stream))


def stamp_evidence(manifest, *, results, code_revision, mesh_revision, material_revision):
    """Create a result evidence record carrying every release-required revision/hash."""
    validate_benchmark_manifest(manifest)
    revisions = {
        "code_revision": str(code_revision).strip(),
        "mesh_revision": str(mesh_revision).strip(),
        "material_revision": str(material_revision).strip(),
    }
    if any(not value for value in revisions.values()):
        raise ValueError("code, mesh, and material revisions must be non-empty")
    return {
        "schema_version": SCHEMA_VERSION,
        "benchmark_id": manifest["benchmark_id"],
        "benchmark_manifest_sha256": manifest_sha256(manifest),
        **revisions,
        "results": dict(results),
    }


def evaluate_release_scorecard(scorecard):
    """Return the only defensible release label from the ten mandatory categories."""
    if not isinstance(scorecard, dict) or scorecard.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"scorecard schema_version must be {SCHEMA_VERSION}")
    categories = scorecard.get("categories")
    if not isinstance(categories, dict) or set(categories) != set(RELEASE_CATEGORIES):
        raise ValueError(f"scorecard must contain exactly {list(RELEASE_CATEGORIES)}")
    states = {}
    for name in RELEASE_CATEGORIES:
        item = categories[name]
        _require(item, ("status", "evidence", "blocking_reason"), f"categories.{name}")
        if item["status"] not in _STATES:
            raise ValueError(f"categories.{name}.status must be one of {sorted(_STATES)}")
        states[name] = item["status"]
    if all(state == "passed" for state in states.values()):
        label = "v0.1_validated_research_workflow"
        allowed_claim = "validated multilevel TSV thermomechanics and device-impact screening"
    elif states["global_experiment"] == "failed" or states["local_experiment"] == "failed":
        label = "release_blocked"
        allowed_claim = "no validated TSV release claim"
    else:
        label = "alpha_numerical_prototype"
        allowed_claim = "TSV numerical/device-screening prototype; experimental validation pending"
    return {
        "release_label": label,
        "allowed_claim": allowed_claim,
        "passed": sum(state == "passed" for state in states.values()),
        "blocked": sum(state == "blocked" for state in states.values()),
        "failed": sum(state == "failed" for state in states.values()),
        "not_started": sum(state == "not_started" for state in states.values()),
        "release_ready": label == "v0.1_validated_research_workflow",
    }


def load_release_scorecard(path):
    path = Path(path)
    with path.open(encoding="utf-8") as stream:
        scorecard = json.load(stream)
    return scorecard, evaluate_release_scorecard(scorecard)
