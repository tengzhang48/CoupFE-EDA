"""Run the public plane-strain SnPbAg solder-cycle example."""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

sys.dont_write_bytecode = True

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from eda_multiphysics.solder_joint import SNPB, solder_joint_cycle


def run():
    """Return a deterministic record for the documented six-Quad4 case."""
    result = solder_joint_cycle(
        nx=3,
        ny=2,
        Tlo=-40.0,
        Thi=125.0,
        dalpha=20.0e-6,
        ldnp_over_h=6.0,
        ncyc=1,
        steps_per_cyc=12,
        maxit=30,
    )
    return {
        "schema_version": 1,
        "example": "solder_plane_cycle",
        "inputs": {
            "material": "62Sn36Pb2Ag_SnPbAg",
            "representative_elastic_modulus_MPa": SNPB["E"],
            "representative_poisson_ratio": SNPB["nu"],
            "elastic_parameter_role": (
                "project model inputs; separate from the cited Anand constants"
            ),
            "geometry_mm": {"width": 0.1, "height": 0.1},
            "mesh": {"element": "Quad4_plane_strain", "nx": 3, "ny": 2},
            "temperature_cycle_C": {"low": -40.0, "high": 125.0},
            "cycle_period_s": 1600.0,
            "cycles": 1,
            "increments_per_cycle": 12,
            "cte_mismatch_per_K": 20.0e-6,
            "distance_to_neutral_point_over_height": 6.0,
        },
        "result": {
            "cycle_dW_MPa": result["dW_cyc"],
            "dW_last_MPa": result["dW_last"],
            "dW_units_equivalence": "1 MPa = 1 MJ/m^3",
            "dW_aggregation": result["dW_aggregation"],
            "imposed_shear_range": result["gamma_range"],
            "element_count": result["n_elem"],
        },
        "solver": {
            "all_increments_accepted": True,
            "state_commits_per_accepted_increment": 1,
            "max_iterations": result["max_iterations"],
            "max_relative_residual": result["max_relative_residual"],
            "max_residual_fraction_of_acceptance_limit": result[
                "max_residual_fraction_of_limit"
            ],
        },
        "scope": {
            "evidence": (
                "Fail-closed stateful solve on a generated mesh; every accepted "
                "increment meets Core's residual rule before one state commit."
            ),
            "current_limits": (
                "Idealized block and loading; not a stabilized-cycle, package-life, "
                "or real-package validation result."
            ),
        },
    }


def _value_at(record, path):
    value = record
    for key in path.split("."):
        value = value[key]
    return value


def _check(record):
    oracle_path = Path(__file__).with_name("expected_results.json")
    with oracle_path.open() as stream:
        oracle = json.load(stream)
    failures = []
    for metric in oracle["metrics"]:
        actual = _value_at(record, metric["path"])
        expected = metric["value"]
        if not math.isclose(
            float(actual),
            float(expected),
            rel_tol=metric.get("relative_tolerance", 0.0),
            abs_tol=metric.get("absolute_tolerance", 0.0),
        ):
            failures.append(
                f"{metric['path']}: expected {expected!r}, observed {actual!r}"
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
