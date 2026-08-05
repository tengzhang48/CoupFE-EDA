"""Fail-closed validation for retained solver-visualization evidence bundles.

The manifest is intentionally small and strict.  It binds one case and its
claim boundary to exact source revisions, an argv-style command, field and mesh
semantics, renderer choices, and an exact four-file artifact inventory.  This
module validates provenance and integrity; it does not assert that the
underlying physical model is experimentally validated.

Run ``python -m eda_multiphysics.visual_evidence MANIFEST.json`` to validate a
bundle whose manifest and artifacts share one directory.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import sys
from typing import Any, Sequence


SCHEMA_VERSION = 1
REQUIRED_ARTIFACT_ROLES = frozenset({"raw-field", "summary", "image", "video"})
_REVISION_PATTERN = re.compile(r"[0-9a-f]{40}")
_NOT_TRANSIENT_PATTERN = re.compile(
    r"\b(?:not\s+(?:a\s+)?transient|non[-\s]?transient)\b",
    flags=re.IGNORECASE,
)


class VisualEvidenceValidationError(ValueError):
    """Raised when a visual-evidence bundle is incomplete or inconsistent."""


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise VisualEvidenceValidationError(f"manifest repeats JSON key {key!r}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise VisualEvidenceValidationError(
        f"manifest contains non-finite JSON constant {value!r}"
    )


def _load_manifest(path: Path) -> dict[str, Any]:
    try:
        payload = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise VisualEvidenceValidationError(
            f"could not read manifest as UTF-8: {path}: {exc}"
        ) from exc
    try:
        value = json.loads(
            payload,
            object_pairs_hook=_strict_object,
            parse_constant=_reject_json_constant,
        )
    except json.JSONDecodeError as exc:
        raise VisualEvidenceValidationError(
            f"manifest is not strict JSON: {exc}"
        ) from exc
    if not isinstance(value, dict):
        raise VisualEvidenceValidationError("manifest root must be a JSON object")
    return value


def _object(
    value: Any,
    location: str,
    keys: set[str],
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise VisualEvidenceValidationError(f"{location} must be an object")
    actual = set(value)
    missing = sorted(keys - actual)
    extra = sorted(actual - keys)
    if missing or extra:
        raise VisualEvidenceValidationError(
            f"{location} key mismatch: missing={missing}, extra={extra}"
        )
    return value


def _list(value: Any, location: str, *, nonempty: bool = True) -> list[Any]:
    if not isinstance(value, list):
        raise VisualEvidenceValidationError(f"{location} must be a list")
    if nonempty and not value:
        raise VisualEvidenceValidationError(f"{location} must not be empty")
    return value


def _string(value: Any, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise VisualEvidenceValidationError(f"{location} must be a non-empty string")
    if "\x00" in value:
        raise VisualEvidenceValidationError(f"{location} must not contain NUL")
    return value


def _integer(value: Any, location: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise VisualEvidenceValidationError(
            f"{location} must be an integer >= {minimum}"
        )
    return value


def _finite_number(value: Any, location: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise VisualEvidenceValidationError(f"{location} must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise VisualEvidenceValidationError(f"{location} must be a finite number")
    return number


def _safe_relative_path(value: Any, location: str) -> PurePosixPath:
    raw = _string(value, location)
    if (
        "\\" in raw
        or raw != raw.strip()
        or any(ord(character) < 32 or ord(character) == 127 for character in raw)
        or re.match(r"^[A-Za-z]:", raw)
    ):
        raise VisualEvidenceValidationError(
            f"{location} must use a canonical relative POSIX path"
        )
    path = PurePosixPath(raw)
    if (
        path.is_absolute()
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
        or path.as_posix() != raw
    ):
        raise VisualEvidenceValidationError(
            f"{location} must be a canonical relative POSIX path without traversal"
        )
    return path


def _validate_configuration(value: Any, location: str = "renderer.configuration") -> None:
    """Require a non-empty, finite JSON object while leaving renderer keys open."""

    if not isinstance(value, dict) or not value:
        raise VisualEvidenceValidationError(f"{location} must be a non-empty object")

    def walk(item: Any, child_location: str) -> None:
        if item is None or isinstance(item, (str, bool)):
            return
        if isinstance(item, int):
            return
        if isinstance(item, float):
            if math.isfinite(item):
                return
            raise VisualEvidenceValidationError(
                f"{child_location} must not contain non-finite numbers"
            )
        if isinstance(item, list):
            for index, child in enumerate(item):
                walk(child, f"{child_location}[{index}]")
            return
        if isinstance(item, dict):
            for key, child in item.items():
                if not isinstance(key, str) or not key:
                    raise VisualEvidenceValidationError(
                        f"{child_location} keys must be non-empty strings"
                    )
                walk(child, f"{child_location}.{key}")
            return
        raise VisualEvidenceValidationError(
            f"{child_location} contains a non-JSON value"
        )

    walk(value, location)


def _validate_schema(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    root = _object(
        manifest,
        "manifest",
        {
            "schema_version",
            "case",
            "claim_boundary",
            "revisions",
            "command",
            "field",
            "renderer",
            "artifacts",
        },
    )
    if root["schema_version"] != SCHEMA_VERSION or isinstance(
        root["schema_version"], bool
    ):
        raise VisualEvidenceValidationError(
            f"schema_version must equal {SCHEMA_VERSION}"
        )

    case = _object(root["case"], "case", {"id", "description"})
    _string(case["id"], "case.id")
    _string(case["description"], "case.description")
    _string(root["claim_boundary"], "claim_boundary")

    revisions = _object(root["revisions"], "revisions", {"eda", "core"})
    for name in ("eda", "core"):
        revision = _string(revisions[name], f"revisions.{name}")
        if _REVISION_PATTERN.fullmatch(revision) is None:
            raise VisualEvidenceValidationError(
                f"revisions.{name} must be one lowercase full 40-hex revision"
            )

    command = _list(root["command"], "command")
    for index, argument in enumerate(command):
        _string(argument, f"command[{index}]")

    field = _object(
        root["field"],
        "field",
        {
            "topology",
            "mesh",
            "degree_of_freedom_count",
            "components",
            "load_steps",
        },
    )
    _string(field["topology"], "field.topology")
    mesh = _object(
        field["mesh"],
        "field.mesh",
        {"name", "spatial_dimension", "node_count", "element_count"},
    )
    _string(mesh["name"], "field.mesh.name")
    dimension = _integer(
        mesh["spatial_dimension"], "field.mesh.spatial_dimension", minimum=1
    )
    if dimension > 3:
        raise VisualEvidenceValidationError(
            "field.mesh.spatial_dimension must be 1, 2, or 3"
        )
    _integer(mesh["node_count"], "field.mesh.node_count", minimum=1)
    _integer(mesh["element_count"], "field.mesh.element_count", minimum=1)
    _integer(
        field["degree_of_freedom_count"],
        "field.degree_of_freedom_count",
        minimum=1,
    )

    components = _list(field["components"], "field.components")
    component_names: list[str] = []
    for index, value in enumerate(components):
        location = f"field.components[{index}]"
        component = _object(value, location, {"name", "unit", "location"})
        component_names.append(_string(component["name"], f"{location}.name"))
        _string(component["unit"], f"{location}.unit")
        _string(component["location"], f"{location}.location")
    duplicate_components = sorted(
        name for name, count in Counter(component_names).items() if count > 1
    )
    if duplicate_components:
        raise VisualEvidenceValidationError(
            f"field.components repeats names: {duplicate_components}"
        )

    load_steps = _list(field["load_steps"], "field.load_steps")
    previous_index: int | None = None
    for position, value in enumerate(load_steps):
        location = f"field.load_steps[{position}]"
        load_step = _object(value, location, {"index", "name", "value", "unit"})
        index = _integer(load_step["index"], f"{location}.index", minimum=0)
        if previous_index is not None and index <= previous_index:
            raise VisualEvidenceValidationError(
                "field.load_steps indices must be strictly increasing in list order"
            )
        previous_index = index
        _string(load_step["name"], f"{location}.name")
        _finite_number(load_step["value"], f"{location}.value")
        _string(load_step["unit"], f"{location}.unit")

    renderer = _object(
        root["renderer"],
        "renderer",
        {"name", "version", "configuration", "interpretation"},
    )
    _string(renderer["name"], "renderer.name")
    _string(renderer["version"], "renderer.version")
    _validate_configuration(renderer["configuration"])
    interpretation = _string(renderer["interpretation"], "renderer.interpretation")
    if _NOT_TRANSIENT_PATTERN.search(interpretation) is None:
        raise VisualEvidenceValidationError(
            "renderer.interpretation must explicitly state that the prescribed "
            "load sweep is not transient"
        )

    artifacts = _list(root["artifacts"], "artifacts")
    records: list[dict[str, Any]] = []
    paths: list[str] = []
    roles: list[str] = []
    for index, value in enumerate(artifacts):
        location = f"artifacts[{index}]"
        record = _object(
            value,
            location,
            {"path", "role", "size_bytes", "sha256"},
        )
        path = _safe_relative_path(record["path"], f"{location}.path")
        role = _string(record["role"], f"{location}.role")
        if role not in REQUIRED_ARTIFACT_ROLES:
            raise VisualEvidenceValidationError(
                f"{location}.role must be one of {sorted(REQUIRED_ARTIFACT_ROLES)}"
            )
        _integer(record["size_bytes"], f"{location}.size_bytes", minimum=0)
        digest = _string(record["sha256"], f"{location}.sha256")
        if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise VisualEvidenceValidationError(
                f"{location}.sha256 must be one lowercase 64-hex SHA-256"
            )
        paths.append(path.as_posix())
        roles.append(role)
        records.append(record)

    duplicate_paths = sorted(
        path for path, count in Counter(paths).items() if count > 1
    )
    if duplicate_paths:
        raise VisualEvidenceValidationError(
            f"artifacts repeats paths: {duplicate_paths}"
        )
    role_counts = Counter(roles)
    missing_roles = sorted(REQUIRED_ARTIFACT_ROLES - set(role_counts))
    duplicate_roles = sorted(role for role, count in role_counts.items() if count > 1)
    if missing_roles or duplicate_roles:
        raise VisualEvidenceValidationError(
            "artifacts must contain exactly one of each required role: "
            f"missing={missing_roles}, duplicate={duplicate_roles}"
        )
    return records


def _resolve_regular_manifest(manifest_path: str | Path) -> Path:
    path = Path(manifest_path).expanduser()
    if path.is_symlink():
        raise VisualEvidenceValidationError("manifest path must not be a symbolic link")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise VisualEvidenceValidationError(f"manifest does not exist: {path}") from exc
    if not resolved.is_file():
        raise VisualEvidenceValidationError(f"manifest is not a regular file: {path}")
    return resolved


def _resolve_artifact_root(artifact_root: str | Path) -> Path:
    path = Path(artifact_root).expanduser()
    if path.is_symlink():
        raise VisualEvidenceValidationError(
            "artifact root must not be a symbolic link"
        )
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise VisualEvidenceValidationError(
            f"artifact root does not exist: {path}"
        ) from exc
    if not resolved.is_dir():
        raise VisualEvidenceValidationError(
            f"artifact root is not a directory: {path}"
        )
    return resolved


def _inventory(root: Path, manifest_path: Path) -> set[str]:
    files: set[str] = set()
    try:
        entries = sorted(root.rglob("*"))
    except OSError as exc:
        raise VisualEvidenceValidationError(
            f"could not enumerate artifact root {root}: {exc}"
        ) from exc
    for entry in entries:
        relative = entry.relative_to(root).as_posix()
        if entry.is_symlink():
            raise VisualEvidenceValidationError(
                f"artifact root contains symbolic link: {relative}"
            )
        if entry.is_dir():
            continue
        if not entry.is_file():
            raise VisualEvidenceValidationError(
                f"artifact root contains non-regular entry: {relative}"
            )
        if entry.resolve() == manifest_path:
            continue
        files.add(relative)
    return files


def _assert_no_symlink_components(root: Path, path: PurePosixPath) -> Path:
    candidate = root
    for part in path.parts:
        candidate = candidate / part
        if candidate.is_symlink():
            raise VisualEvidenceValidationError(
                f"artifact path traverses a symbolic link: {path.as_posix()}"
            )
    return candidate


def _sha256_and_size(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    try:
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
                size += len(block)
    except OSError as exc:
        raise VisualEvidenceValidationError(
            f"could not read declared artifact {path}: {exc}"
        ) from exc
    return digest.hexdigest(), size


def validate_manifest(
    manifest_path: str | Path,
    *,
    artifact_root: str | Path | None = None,
) -> dict[str, Any]:
    """Validate one manifest and the exact artifact inventory it declares.

    ``artifact_root`` defaults to the manifest's directory.  Every regular file
    under that root, except the manifest itself, must be declared.  Every
    declared artifact must exist there as a regular non-symlink file and match
    its recorded byte size and SHA-256 digest.  The validated manifest is
    returned unchanged.
    """

    manifest = _resolve_regular_manifest(manifest_path)
    root = _resolve_artifact_root(
        artifact_root if artifact_root is not None else manifest.parent
    )
    data = _load_manifest(manifest)
    records = _validate_schema(data)

    declared = {str(record["path"]) for record in records}
    if manifest.is_relative_to(root):
        manifest_relative = manifest.relative_to(root).as_posix()
        if manifest_relative in declared:
            raise VisualEvidenceValidationError(
                "the manifest must not declare itself as an artifact"
            )

    observed = _inventory(root, manifest)
    missing = sorted(declared - observed)
    extra = sorted(observed - declared)
    if missing or extra:
        raise VisualEvidenceValidationError(
            f"artifact inventory mismatch: missing={missing}, extra={extra}"
        )

    for record in records:
        relative = PurePosixPath(str(record["path"]))
        path = _assert_no_symlink_components(root, relative)
        actual_digest, actual_size = _sha256_and_size(path)
        if actual_size != record["size_bytes"]:
            raise VisualEvidenceValidationError(
                f"artifact size mismatch for {relative.as_posix()}: "
                f"declared={record['size_bytes']}, actual={actual_size}"
            )
        if actual_digest != record["sha256"]:
            raise VisualEvidenceValidationError(
                f"artifact SHA-256 mismatch for {relative.as_posix()}: "
                f"declared={record['sha256']}, actual={actual_digest}"
            )
    return data


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate a CoupFE-EDA solver-visualization evidence bundle."
    )
    parser.add_argument("manifest", type=Path)
    parser.add_argument(
        "--artifact-root",
        type=Path,
        help="exact artifact inventory root (default: manifest directory)",
    )
    args = parser.parse_args(argv)
    try:
        manifest = validate_manifest(
            args.manifest,
            artifact_root=args.artifact_root,
        )
    except VisualEvidenceValidationError as exc:
        print(f"visual evidence validation failed: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "artifact_count": len(manifest["artifacts"]),
                "case_id": manifest["case"]["id"],
                "schema_version": manifest["schema_version"],
                "status": "valid",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
