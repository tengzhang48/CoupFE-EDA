"""Run the public partitioned SAC305 thermo-viscoplastic example."""
from __future__ import annotations

import argparse
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
            "last_cycle": result["last_cycle"],
        }

    return {
        "period_s": period_s,
        "quasisteady": model_record(comparison["quasisteady"]),
        "lumped_transient": model_record(comparison["lumped_transient"]),
        "relative_energy_difference_percent": 100.0
        * comparison["relative_energy_difference"],
    }


def run():
    """Return deterministic slow- and fast-cycle model-comparison records."""
    dandu = dandu_bump()
    q_joule = joule_density(dandu["j_avg"])
    common = {"q_joule": q_joule, "ncyc": 2}
    slow = thermoviscoplastic_comparison(period=1600.0, **common)
    fast = thermoviscoplastic_comparison(period=1.0, **common)
    mesh = slow["quasisteady"]["mesh"]
    return {
        "schema_version": 2,
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
                "nx": 2,
                "ny": 2,
                "nodes": len(mesh["coordinates_m"]),
                "elements": len(mesh["connectivity"]),
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
                "Partitioned reduced model with uniform lagged heat feedback; not a "
                "monolithic phi-T-u element, measured-device comparison, or life result."
            ),
        },
    }


def _value_at(record, path):
    value = record
    for key in path.split("."):
        value = value[key]
    return value


def _compare_metric(actual, expected, *, path, rel_tol, abs_tol):
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


def _check(record):
    oracle_path = Path(__file__).with_name("expected_results.json")
    with oracle_path.open() as stream:
        oracle = json.load(stream)
    failures = []
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
        "--check",
        action="store_true",
        help="compare selected metrics with expected_results.json",
    )
    args = parser.parse_args(argv)
    record = run()
    record["verification"] = (
        _check(record)
        if args.check
        else {"oracle": "expected_results.json", "passed": None, "failures": []}
    )
    print(json.dumps(record, indent=2, sort_keys=True, allow_nan=False))
    return 0 if record["verification"]["passed"] is not False else 1


if __name__ == "__main__":
    raise SystemExit(main())
