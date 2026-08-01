"""Run the synthetic design-linked 3-D solder screening example."""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

sys.dont_write_bytecode = True

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from eda_multiphysics.anand_3d import SAC305_3D
from eda_multiphysics.reliability_3d import SYED_W, critical_joint_bvp_screening


def _rounded(value):
    """Return a stable, reviewable number without hiding useful precision."""
    return float(f"{float(value):.12g}")


def _optional_number(value):
    value = float(value)
    return _rounded(value) if math.isfinite(value) else None


def run():
    """Return the documented design-linked default as JSON-compatible data."""
    result = critical_joint_bvp_screening(
        h_solder=50.0,
        dalpha=14.4e-6,
        Tlo=-40.0,
        Thi=125.0,
        nx=3,
        ny=3,
        nz=2,
        ncyc=1,
        steps_per_cyc=8,
    )
    return {
        "example": "design_linked_solder_screening",
        "input_provenance": {
            "joint_map": "eda_multiphysics/cases/synthetic_pdn/joints.csv",
            "joint_source": result["joint_source"],
            "joint_map_explicit": result["joint_map_explicit"],
            "geometry_fidelity": result["joint_geometry_fidelity"],
            "coordinate_frame": result["coordinate_frame"],
            "representative_elastic_modulus_MPa": SAC305_3D["E"],
            "representative_poisson_ratio": SAC305_3D["nu"],
            "elastic_parameter_role": (
                "project model inputs; separate from the cited non-aged Anand fit"
            ),
        },
        "selected_design_object": {
            "joint_id": result["joint_id"],
            "source_object_id": result["source_object_id"],
            "net": result["net"],
            "L_D_um": _rounded(result["L_D"]),
            "joint_map_diameter_um": _optional_number(result["diameter_um"]),
            "joint_map_height_um": _optional_number(result["height_um"]),
            "selection_criterion": "maximum distance to neutral point",
            "maximum_dnp_tie_count": result["maximum_dnp_tie_count"],
            "maximum_dnp_tied_joint_ids": result[
                "maximum_dnp_tied_joint_ids"
            ],
            "tie_break_policy": result["critical_joint_selection_policy"],
        },
        "configuration": {
            "mesh_elements_xyz": [3, 3, 2],
            "block_dimensions_mm": [0.1, 0.1, 0.1],
            "n_elements": result["n_elem"],
            "temperature_C": [-40.0, 125.0],
            "cycle_period_s": 1600.0,
            "cycles": 1,
            "increments_per_cycle": 8,
            "delta_alpha_per_K": 14.4e-6,
            "screening_height_um": result["screening_height_um"],
            "L_D_over_h": _rounded(result["ldnp_over_h"]),
            "height_role": "caller study input; joint-map height does not size the block",
            "Syed_energy_coefficient_per_MPa": SYED_W,
            "Syed_coefficient_role": (
                "corrected hyperbolic-sine value used for a calibration-specific screen"
            ),
        },
        "results": {
            "dW_element_MPa": [_rounded(value) for value in result["dW_elem"]],
            "dW_peak_MPa": _rounded(result["dW_peak"]),
            "dW_mean_MPa": _rounded(result["dW_mean"]),
            "peak_to_mean": _rounded(result["peak_to_mean"]),
            "engineering_shear_range": _rounded(result["gamma_range"]),
            "Syed_calibration_screen_cycles": _rounded(result["Nf_screen_peak"]),
        },
        "solver_evidence": {
            "all_increments_accepted": True,
            "max_newton_iterations": result["max_iterations"],
            "max_final_residual_fraction_of_acceptance_limit": _rounded(
                result["max_residual_fraction_of_limit"]
            ),
        },
        "limitations": (
            "The bundled design map and regular block are synthetic. Only L_D and object "
            "identity come from the map; h is a study input. The energy-to-life value is a "
            "calibration-specific screen, not predictive package life."
        ),
    }


def _compare(actual, expected, *, rtol, atol, path="result"):
    errors = []
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return [f"{path}: expected an object"]
        for key, value in expected.items():
            if key not in actual:
                errors.append(f"{path}.{key}: missing")
            else:
                errors.extend(
                    _compare(actual[key], value, rtol=rtol, atol=atol, path=f"{path}.{key}")
                )
        return errors
    if isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) != len(expected):
            return [f"{path}: expected a list of length {len(expected)}"]
        for index, value in enumerate(expected):
            errors.extend(
                _compare(actual[index], value, rtol=rtol, atol=atol, path=f"{path}[{index}]")
            )
        return errors
    if isinstance(expected, float):
        if not isinstance(actual, (int, float)) or not math.isclose(
            float(actual), expected, rel_tol=rtol, abs_tol=atol
        ):
            errors.append(f"{path}: got {actual!r}, expected {expected!r}")
        return errors
    if actual != expected:
        errors.append(f"{path}: got {actual!r}, expected {expected!r}")
    return errors


def _value_at(record, path):
    value = record
    for key in path.split("."):
        value = value[key]
    return value


def _check_bounds(record, bounds):
    errors = []
    for bound in bounds:
        value = float(_value_at(record, bound["path"]))
        if "minimum_inclusive" in bound and value < bound["minimum_inclusive"]:
            errors.append(
                f"{bound['path']}: got {value!r}, expected >= {bound['minimum_inclusive']!r}"
            )
        if "maximum_inclusive" in bound and value > bound["maximum_inclusive"]:
            errors.append(
                f"{bound['path']}: got {value!r}, expected <= {bound['maximum_inclusive']!r}"
            )
        if "maximum_exclusive" in bound and value >= bound["maximum_exclusive"]:
            errors.append(
                f"{bound['path']}: got {value!r}, expected < {bound['maximum_exclusive']!r}"
            )
    return errors


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="compare selected outputs with expected_results.json",
    )
    args = parser.parse_args(argv)
    output = run()
    exit_code = 0
    if args.check:
        expected_path = Path(__file__).with_name("expected_results.json")
        reference = json.loads(expected_path.read_text())
        errors = _compare(
            output,
            reference["expected"],
            rtol=float(reference["relative_tolerance"]),
            atol=float(reference["absolute_tolerance"]),
        )
        errors.extend(_check_bounds(output, reference.get("bounds", [])))
        output["check"] = {
            "expected_results": expected_path.name,
            "passed": not errors,
            "errors": errors,
        }
        exit_code = int(bool(errors))
    print(json.dumps(output, indent=2, sort_keys=True, allow_nan=False))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
