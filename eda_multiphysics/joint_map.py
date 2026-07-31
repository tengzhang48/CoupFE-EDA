"""Versioned package-joint map input for layout-driven reliability analyses.

The CSV carries stable object identities and geometry.  Its sibling JSON file carries units,
coordinate-frame provenance, and the affine transform into the die frame used by CoupFE-EDA.
All public numeric fields are normalized to microns on load.
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np


SCHEMA_VERSION = 1
_TO_UM = {
    "micron": 1.0,
    "microns": 1.0,
    "um": 1.0,
    "millimeter": 1.0e3,
    "millimeters": 1.0e3,
    "mm": 1.0e3,
    "meter": 1.0e6,
    "meters": 1.0e6,
    "m": 1.0e6,
    "nanometer": 1.0e-3,
    "nanometers": 1.0e-3,
    "nm": 1.0e-3,
}
_GEOMETRY_FIDELITY = {"proxy", "design_export", "calibrated", "qualified"}


@dataclass(frozen=True)
class JointMap:
    """Joint locations and optional dimensions in the die frame, in microns."""

    ids: tuple[str, ...]
    xyz_um: np.ndarray
    diameter_um: np.ndarray
    height_um: np.ndarray
    nets: tuple[str, ...]
    source_object_ids: tuple[str, ...]
    source: str
    geometry_fidelity: str
    coordinate_frame: str
    neutral_point_um: np.ndarray
    path: Path
    schema_version: int = SCHEMA_VERSION

    @property
    def xy_um(self):
        return self.xyz_um[:, :2]

    @property
    def dnp_um(self):
        delta = self.xy_um - self.neutral_point_um[:2]
        return np.hypot(delta[:, 0], delta[:, 1])


def _unit_scale(value, field, metadata_path):
    unit = str(value).strip().lower()
    if unit not in _TO_UM:
        supported = ", ".join(sorted(_TO_UM))
        raise ValueError(f"{metadata_path}: unsupported {field} {value!r}; use one of {supported}")
    return _TO_UM[unit]


def _finite_vector(value, length, field, metadata_path):
    array = np.asarray(value, dtype=float)
    if array.shape != (length,) or not np.all(np.isfinite(array)):
        raise ValueError(f"{metadata_path}: {field} must be a finite length-{length} array")
    return array


def _optional_positive(row, field, row_number):
    text = (row.get(field) or "").strip()
    if not text:
        return np.nan
    try:
        value = float(text)
    except ValueError as exc:
        raise ValueError(f"row {row_number}: {field} must be numeric or blank") from exc
    if not np.isfinite(value) or value <= 0.0:
        raise ValueError(f"row {row_number}: {field} must be positive and finite")
    return value


def load_joint_map(csv_path, metadata_path=None):
    """Load schema-v1 ``joints.csv`` and normalize coordinates/dimensions to microns.

    Required CSV columns are ``joint_id,x,y``. Optional columns are ``z,diameter,height,net`` and
    ``source_object_id``. The metadata path defaults to sibling ``joints.meta.json`` and must state
    the schema version, coordinate and dimension units, source, geometry fidelity, coordinate frame, and an affine
    ``transform_to_die_um``. Duplicate IDs, ambiguous units, and invalid transforms fail closed.
    """
    csv_path = Path(csv_path)
    metadata_path = Path(metadata_path) if metadata_path is not None else csv_path.with_name(
        "joints.meta.json"
    )
    if not metadata_path.exists():
        raise ValueError(f"joint map {csv_path} requires metadata file {metadata_path}")
    with metadata_path.open(encoding="utf-8") as stream:
        metadata = json.load(stream)
    if metadata.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(
            f"{metadata_path}: schema_version must be {SCHEMA_VERSION}, "
            f"got {metadata.get('schema_version')!r}"
        )
    coordinate_scale = _unit_scale(metadata.get("coordinate_unit"), "coordinate_unit", metadata_path)
    dimension_scale = _unit_scale(metadata.get("dimension_unit"), "dimension_unit", metadata_path)
    source = str(metadata.get("source", "")).strip()
    geometry_fidelity = str(metadata.get("geometry_fidelity", "")).strip()
    coordinate_frame = str(metadata.get("coordinate_frame", "")).strip()
    if not source or not coordinate_frame:
        raise ValueError(f"{metadata_path}: source and coordinate_frame must be non-empty")
    if geometry_fidelity not in _GEOMETRY_FIDELITY:
        raise ValueError(
            f"{metadata_path}: geometry_fidelity must be one of "
            f"{sorted(_GEOMETRY_FIDELITY)}, got {geometry_fidelity!r}"
        )
    transform = metadata.get("transform_to_die_um")
    if not isinstance(transform, dict):
        raise ValueError(f"{metadata_path}: transform_to_die_um must be an object")
    matrix = np.asarray(transform.get("matrix"), dtype=float)
    if matrix.shape != (3, 3) or not np.all(np.isfinite(matrix)):
        raise ValueError(f"{metadata_path}: transform_to_die_um.matrix must be a finite 3x3 array")
    if abs(np.linalg.det(matrix)) < 1.0e-12:
        raise ValueError(f"{metadata_path}: transform_to_die_um.matrix must be nonsingular")
    offset = _finite_vector(
        transform.get("offset_um"), 3, "transform_to_die_um.offset_um", metadata_path
    )

    with csv_path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        required = {"joint_id", "x", "y"}
        missing = required - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"{csv_path}: missing required columns {sorted(missing)}")
        ids = []
        xyz = []
        diameters = []
        heights = []
        nets = []
        source_ids = []
        for row_number, row in enumerate(reader, start=2):
            joint_id = (row.get("joint_id") or "").strip()
            if not joint_id:
                raise ValueError(f"row {row_number}: joint_id must be non-empty")
            try:
                point = [float(row["x"]), float(row["y"]), float((row.get("z") or "0").strip())]
            except ValueError as exc:
                raise ValueError(f"row {row_number}: x, y, and z must be numeric") from exc
            if not np.all(np.isfinite(point)):
                raise ValueError(f"row {row_number}: x, y, and z must be finite")
            ids.append(joint_id)
            xyz.append(point)
            diameters.append(_optional_positive(row, "diameter", row_number))
            heights.append(_optional_positive(row, "height", row_number))
            nets.append((row.get("net") or "").strip())
            source_ids.append((row.get("source_object_id") or "").strip())
    if not ids:
        raise ValueError(f"{csv_path}: joint map must contain at least one row")
    if len(ids) != len(set(ids)):
        duplicates = sorted({joint_id for joint_id in ids if ids.count(joint_id) > 1})
        raise ValueError(f"{csv_path}: duplicate joint_id values: {duplicates}")

    xyz_um = np.asarray(xyz, dtype=float) * coordinate_scale
    xyz_um = xyz_um @ matrix.T + offset
    if not np.all(np.isfinite(xyz_um)):
        raise ValueError(f"{metadata_path}: coordinate transform produced non-finite values")
    if "neutral_point_um" in metadata:
        neutral_point_um = _finite_vector(
            metadata["neutral_point_um"], 3, "neutral_point_um", metadata_path
        )
    else:
        neutral_point_um = xyz_um.mean(axis=0)
    return JointMap(
        ids=tuple(ids),
        xyz_um=xyz_um,
        diameter_um=np.asarray(diameters, dtype=float) * dimension_scale,
        height_um=np.asarray(heights, dtype=float) * dimension_scale,
        nets=tuple(nets),
        source_object_ids=tuple(source_ids),
        source=source,
        geometry_fidelity=geometry_fidelity,
        coordinate_frame=coordinate_frame,
        neutral_point_um=neutral_point_um,
        path=csv_path,
    )
