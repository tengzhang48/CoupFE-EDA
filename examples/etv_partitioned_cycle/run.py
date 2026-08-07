"""Run the public partitioned SAC305 thermo-viscoplastic example."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

sys.dont_write_bytecode = True

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from eda_multiphysics.etv_fe import thermoviscoplastic_comparison
from eda_multiphysics.etv_solder import (
    RHOC_SOLDER,
    RHO0_SOLDER,
    dandu_bump,
    joule_density,
)
from eda_multiphysics.solder_joint import SAC305_PLANE


def _field_summary(result):
    field = result["last_cycle"]["dW_element_MPa"]
    top_indices = result["mesh"]["top_element_indices"]
    top_field = [field[index] for index in top_indices]
    return {
        "minimum": min(field),
        "maximum": max(field),
        "mean": sum(field) / len(field),
        "top_row_mean": sum(top_field) / len(top_field),
    }


def _canonical_sha256(value):
    """Hash nested JSON data with a documented, platform-stable float format."""

    def canonical(item):
        if isinstance(item, dict):
            return {key: canonical(item[key]) for key in sorted(item)}
        if isinstance(item, list):
            return [canonical(entry) for entry in item]
        if isinstance(item, float):
            if not math.isfinite(item):
                raise ValueError("integrity records cannot contain non-finite floats")
            return format(item, ".12e")
        if item is None or isinstance(item, (bool, int, str)):
            return item
        raise TypeError(f"unsupported integrity value type: {type(item).__name__}")

    payload = json.dumps(
        canonical(value),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def _integrity_record(record):
    """Bind the retained meshes and state arrays used by the public figures."""
    mesh = record["inputs"]["mesh"]
    results = record["results"]

    def retained(cycle, model):
        return results[cycle][model]["last_cycle"]

    fast_quasisteady = retained("fast_cycle", "quasisteady")
    fast_transient = retained("fast_cycle", "lumped_transient")
    return {
        "algorithm": "sha256",
        "canonicalization": (
            "sorted compact JSON; finite floats formatted with .12e"
        ),
        "mesh_coordinates_sha256": _canonical_sha256(mesh["coordinates_m"]),
        "mesh_connectivity_sha256": _canonical_sha256(mesh["connectivity"]),
        "slow_quasisteady_last_cycle_sha256": _canonical_sha256(
            retained("slow_cycle", "quasisteady")
        ),
        "slow_lumped_transient_last_cycle_sha256": _canonical_sha256(
            retained("slow_cycle", "lumped_transient")
        ),
        "fast_quasisteady_last_cycle_sha256": _canonical_sha256(
            fast_quasisteady
        ),
        "fast_lumped_transient_last_cycle_sha256": _canonical_sha256(
            fast_transient
        ),
        "fast_quasisteady_dW_field_sha256": _canonical_sha256(
            fast_quasisteady["dW_element_MPa"]
        ),
        "fast_lumped_transient_dW_field_sha256": _canonical_sha256(
            fast_transient["dW_element_MPa"]
        ),
        "fast_quasisteady_end_displacement_sha256": _canonical_sha256(
            fast_quasisteady["displacement_m"][-1]
        ),
        "fast_lumped_transient_end_displacement_sha256": _canonical_sha256(
            fast_transient["displacement_m"][-1]
        ),
    }


def _case_record(comparison, period_s):
    def model_record(result):
        return {
            "cycle_dW_MPa": result["dW_cyc"],
            "dW_last_MPa": result["dW_last"],
            "temperature_C_min": result["temperature_C_min"],
            "temperature_C_max": result["temperature_C_max"],
            "max_iterations": result["max_iterations"],
            "max_relative_residual": result["max_relative_residual"],
            "max_residual_fraction_of_acceptance_limit": result[
                "max_residual_fraction_of_limit"
            ],
            "dW_field_summary_MPa": _field_summary(result),
            "last_cycle": result["last_cycle"],
        }

    return {
        "period_s": period_s,
        "quasisteady": model_record(comparison["quasisteady"]),
        "lumped_transient": model_record(comparison["lumped_transient"]),
        "relative_energy_difference_percent": 100.0
        * comparison["relative_energy_difference"],
    }


def run(*, mesh_size=2):
    """Return slow- and fast-cycle records on a selected square mesh.

    The two-element mesh remains the fast default; the public website retains
    the separately checked 20-element-per-side case.
    """
    if (
        isinstance(mesh_size, bool)
        or not isinstance(mesh_size, int)
        or mesh_size < 1
    ):
        raise ValueError("mesh_size must be a positive integer")
    dandu = dandu_bump()
    q_joule = joule_density(dandu["j_avg"])
    common = {"q_joule": q_joule, "ncyc": 2, "nx": mesh_size, "ny": mesh_size}
    slow = thermoviscoplastic_comparison(period=1600.0, **common)
    fast = thermoviscoplastic_comparison(period=1.0, **common)
    mesh = slow["quasisteady"]["mesh"]
    node_count = len(mesh["coordinates_m"])
    element_count = len(mesh["connectivity"])
    record = {
        "schema_version": 3,
        "example": "etv_partitioned_cycle",
        "inputs": {
            "material": "SAC305_non_aged_Anand_fit",
            "representative_elastic_modulus_MPa": SAC305_PLANE["E"],
            "representative_poisson_ratio": SAC305_PLANE["nu"],
            "elastic_parameter_role": (
                "project model inputs; separate from the cited non-aged Anand fit"
            ),
            "geometry_mm": {"width": 0.1, "height": 0.1},
            "mesh": {
                "element": "Quad4_plane_strain",
                "nx": mesh_size,
                "ny": mesh_size,
                "nodes": node_count,
                "elements": element_count,
                "mechanical_displacement_dofs": 2 * node_count,
                "element_width_um": 100.0 / mesh_size,
                "element_height_um": 100.0 / mesh_size,
                "top_row_depth_um": 100.0 / mesh_size,
                "top_row_element_count": len(mesh["top_element_indices"]),
                "coordinates_m": mesh["coordinates_m"],
                "connectivity": mesh["connectivity"],
                "top_element_indices": mesh["top_element_indices"],
            },
            "temperature_cycle_C": {"low": -40.0, "high": 125.0},
            "cycles": 2,
            "increments_per_cycle": 8,
            "cte_mismatch_per_K": 20.0e-6,
            "distance_to_neutral_point_over_height": 6.0,
            "thermal_conductance_density_W_per_m3K": 8.0e6,
            "volumetric_heat_capacity_J_per_m3K": RHOC_SOLDER,
            "inelastic_heat_fraction": 1.0,
            "dandu_context": {
                "chain_current_A": 1.7,
                "representative_bump_diameter_um": dandu["D_um"],
                "derived_average_current_density_A_per_cm2": dandu["j_avg"],
                "solder_resistivity_ohm_m": RHO0_SOLDER,
                "derived_joule_density_W_per_m3": q_joule,
            },
        },
        "results": {
            "dW_units_equivalence": "1 MPa = 1 MJ/m^3",
            "dW_aggregation": (
                "increment sum of equal-volume top-layer Gauss-point mean"
            ),
            "slow_cycle": _case_record(slow, 1600.0),
            "fast_cycle": _case_record(fast, 1.0),
        },
        "solver": {
            "all_mechanical_increments_accepted": True,
            "state_commits_per_accepted_increment": 1,
            "acceptance_rule": "Core residual rule checked before state commit",
        },
        "scope": {
            "evidence": (
                "Sensitivity of spatial SAC305 mechanics to quasisteady versus "
                "backward-Euler lumped-temperature assumptions."
            ),
            "current_limits": (
                f"The selected {mesh_size}x{mesh_size} mesh reports a "
                f"{len(mesh['top_element_indices'])}-element, "
                f"{100.0 / mesh_size:g} um-deep top-row mean. Partitioned reduced "
                "model with uniform lagged heat feedback; not a monolithic phi-T-u "
                "element, mesh/load-step convergence study, measured-device "
                "comparison, crack prediction, or life result."
            ),
        },
    }
    record["integrity"] = _integrity_record(record)
    return record


def _value_at(record, path):
    value = record
    for key in path.split("."):
        value = value[key]
    return value


def _compare_metric(actual, expected, *, path, rel_tol, abs_tol):
    if isinstance(expected, (str, bool)):
        if actual != expected:
            return [f"{path}: expected {expected!r}, observed {actual!r}"]
        return []
    if isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) != len(expected):
            return [
                f"{path}: expected an array of length {len(expected)}, "
                f"observed {type(actual).__name__} of length "
                f"{len(actual) if isinstance(actual, list) else 'n/a'}"
            ]
        failures = []
        for index, (actual_item, expected_item) in enumerate(zip(actual, expected)):
            failures.extend(
                _compare_metric(
                    actual_item,
                    expected_item,
                    path=f"{path}[{index}]",
                    rel_tol=rel_tol,
                    abs_tol=abs_tol,
                )
            )
        return failures
    if not math.isclose(
        float(actual),
        float(expected),
        rel_tol=rel_tol,
        abs_tol=abs_tol,
    ):
        return [f"{path}: expected {expected!r}, observed {actual!r}"]
    return []


def _oracle_path_for_mesh(mesh_size):
    oracle_names = {
        2: "expected_results.json",
        20: "expected_results_20x20.json",
    }
    try:
        oracle_name = oracle_names[mesh_size]
    except KeyError as error:
        supported = ", ".join(str(size) for size in sorted(oracle_names))
        raise ValueError(
            f"no retained oracle for mesh_size={mesh_size}; supported: {supported}"
        ) from error
    return Path(__file__).with_name(oracle_name)


def _check(record, oracle_path=None):
    if oracle_path is None:
        mesh = record["inputs"]["mesh"]
        if mesh["nx"] != mesh["ny"]:
            raise ValueError("retained ETV oracles require a square nx-by-nx mesh")
        oracle_path = _oracle_path_for_mesh(mesh["nx"])
    else:
        oracle_path = Path(oracle_path)
    with oracle_path.open() as stream:
        oracle = json.load(stream)
    failures = []
    if oracle.get("schema_version") != record.get("schema_version"):
        failures.append(
            "oracle schema_version: expected to match retained record "
            f"{record.get('schema_version')!r}, observed "
            f"{oracle.get('schema_version')!r}"
        )
    computed_integrity = _integrity_record(record)
    if record.get("integrity") != computed_integrity:
        failures.append(
            "integrity: retained mesh/state digests do not match their arrays"
        )
    for metric in oracle["metrics"]:
        actual = _value_at(record, metric["path"])
        expected = metric["value"]
        failures.extend(
            _compare_metric(
                actual,
                expected,
                path=metric["path"],
                rel_tol=metric.get("relative_tolerance", 0.0),
                abs_tol=metric.get("absolute_tolerance", 0.0),
            )
        )
    for bound in oracle["bounds"]:
        actual = float(_value_at(record, bound["path"]))
        if "maximum_exclusive" in bound and not actual < bound["maximum_exclusive"]:
            failures.append(
                f"{bound['path']}: expected < {bound['maximum_exclusive']!r}, "
                f"observed {actual!r}"
            )
    return {"oracle": oracle_path.name, "passed": not failures, "failures": failures}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mesh-size",
        type=int,
        choices=(2, 20),
        default=2,
        help=(
            "square Quad4 mesh count; 2 is the fast CI smoke case and 20 is the "
            "retained public evidence case"
        ),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="compare selected metrics with the retained oracle for --mesh-size",
    )
    args = parser.parse_args(argv)
    record = run(mesh_size=args.mesh_size)
    oracle_path = _oracle_path_for_mesh(args.mesh_size)
    record["verification"] = (
        _check(record, oracle_path)
        if args.check
        else {"oracle": oracle_path.name, "passed": None, "failures": []}
    )
    print(json.dumps(record, indent=2, sort_keys=True, allow_nan=False))
    return 0 if record["verification"]["passed"] is not False else 1


if __name__ == "__main__":
    raise SystemExit(main())
