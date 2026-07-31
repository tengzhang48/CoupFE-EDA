"""Regenerate the project-authored synthetic PDN integration fixture.

The fixture is deliberately small and uses no third-party design, platform, or
generated output.  A symmetric 3x3 resistor grid makes the reference voltages
available in closed form while retaining the same versioned files consumed
by the OpenROAD/PDNSim adapters.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
GRID_UM = (20.0, 50.0, 80.0)
DBU_PER_MICRON = 1000
CELL_SIZE_UM = 10.0
EDGE_RESISTANCE_OHM = 0.1
CELL_CURRENT_A = 1.0e-3
VDD_V = 1.0


def _node(x_um: float, y_um: float) -> str:
    return (
        f"VDD_{round(x_um * DBU_PER_MICRON)}_"
        f"{round(y_um * DBU_PER_MICRON)}_1"
    )


def _write_csv(name: str, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    with (HERE / name).open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _write_json(name: str, payload: dict[str, object]) -> None:
    (HERE / name).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _sha256(name: str) -> str:
    return hashlib.sha256((HERE / name).read_bytes()).hexdigest()


def generate() -> None:
    instances = []
    powers = []
    joints = []
    reference = []
    for row_index, y_um in enumerate(GRID_UM):
        for column_index, x_um in enumerate(GRID_UM):
            instance_id = f"SYNTH_U{row_index}{column_index}"
            node = _node(x_um, y_um)
            instances.append(
                {
                    "eda_id": instance_id,
                    "master": "SYNTH_CELL",
                    "x_um": f"{x_um - CELL_SIZE_UM / 2:g}",
                    "y_um": f"{y_um - CELL_SIZE_UM / 2:g}",
                    "w_um": f"{CELL_SIZE_UM:g}",
                    "h_um": f"{CELL_SIZE_UM:g}",
                    "area_um2": f"{CELL_SIZE_UM**2:g}",
                }
            )
            joints.append(
                {
                    "joint_id": f"SYNTH_J{row_index}{column_index}",
                    "x": f"{x_um:g}",
                    "y": f"{y_um:g}",
                    "z": "0",
                    "diameter": "",
                    "height": "",
                    "net": "VDD",
                    "source_object_id": node,
                }
            )
            distance_from_center = (
                int(x_um != GRID_UM[1]) + int(y_um != GRID_UM[1])
            )
            voltage = {
                0: VDD_V,
                1: VDD_V - 2.0 * CELL_CURRENT_A * EDGE_RESISTANCE_OHM,
                2: VDD_V - 2.5 * CELL_CURRENT_A * EDGE_RESISTANCE_OHM,
            }[distance_from_center]
            reference.append(
                {
                    "node": node,
                    "x_um": f"{x_um:g}",
                    "y_um": f"{y_um:g}",
                    "voltage_V": f"{voltage:.9g}",
                }
            )
            powers.append(
                {
                    "eda_id": instance_id,
                    "power_W": f"{voltage * CELL_CURRENT_A:.9g}",
                }
            )

    _write_csv(
        "instances.csv",
        ["eda_id", "master", "x_um", "y_um", "w_um", "h_um", "area_um2"],
        instances,
    )
    _write_csv("instance_power.csv", ["eda_id", "power_W"], powers)
    _write_json(
        "instance_power.meta.json",
        {
            "schema_version": 1,
            "total_power_W": sum(float(row["power_W"]) for row in powers),
            "total_power_provenance": "project_authored_synthetic_scenario",
            "instance_power_model": "closed_form_dc_load_power",
            "description": (
                "Per-instance P=V*I from the fixture's closed-form node voltages "
                "and nine 1 mA loads; not an EDA-tool power report."
            ),
        },
    )
    _write_csv(
        "joints.csv",
        [
            "joint_id",
            "x",
            "y",
            "z",
            "diameter",
            "height",
            "net",
            "source_object_id",
        ],
        joints,
    )
    _write_json(
        "joints.meta.json",
        {
            "schema_version": 1,
            "coordinate_unit": "micron",
            "dimension_unit": "micron",
            "coordinate_frame": "synthetic_die",
            "source": "project_authored_synthetic_joint_map",
            "geometry_fidelity": "proxy",
            "source_description": (
                "Synthetic 3x3 coordinates for exercising the joint-map API; "
                "not package or bump data."
            ),
            "transform_to_die_um": {
                "matrix": [
                    [1.0, 0.0, 0.0],
                    [0.0, 1.0, 0.0],
                    [0.0, 0.0, 1.0],
                ],
                "offset_um": [0.0, 0.0, 0.0],
            },
            "neutral_point_um": [50.0, 50.0, 0.0],
        },
    )

    spice_lines = [
        "* Project-authored synthetic 3x3 PDN; Apache-2.0.",
        "* R=0.1 ohm per edge, 1 mA load per node, center supply=1 V.",
    ]
    resistor_index = 0
    for y_um in GRID_UM:
        for x0_um, x1_um in zip(GRID_UM[:-1], GRID_UM[1:]):
            spice_lines.append(
                f"R{resistor_index} {_node(x0_um, y_um)} "
                f"{_node(x1_um, y_um)} {EDGE_RESISTANCE_OHM:g}"
            )
            resistor_index += 1
    for x_um in GRID_UM:
        for y0_um, y1_um in zip(GRID_UM[:-1], GRID_UM[1:]):
            spice_lines.append(
                f"R{resistor_index} {_node(x_um, y0_um)} "
                f"{_node(x_um, y1_um)} {EDGE_RESISTANCE_OHM:g}"
            )
            resistor_index += 1
    for load_index, y_um in enumerate(GRID_UM):
        for column_index, x_um in enumerate(GRID_UM):
            index = load_index * len(GRID_UM) + column_index
            spice_lines.append(
                f"I{index} {_node(x_um, y_um)} 0 {CELL_CURRENT_A:g}"
            )
    spice_lines.extend(
        [
            f"V0 {_node(GRID_UM[1], GRID_UM[1])} 0 {VDD_V:g}",
            ".OPTION NUMDGT=9",
            ".OP",
            ".END",
        ]
    )
    (HERE / "pdn_vdd.sp").write_text("\n".join(spice_lines) + "\n", encoding="utf-8")

    _write_csv(
        "reference_vdd_nodes.csv",
        ["node", "x_um", "y_um", "voltage_V"],
        reference,
    )
    source_power = round(VDD_V * len(reference) * CELL_CURRENT_A, 12)
    load_power = round(sum(float(row["power_W"]) for row in powers), 12)
    _write_json(
        "reference_vdd_nodes.meta.json",
        {
            "schema_version": 1,
            "reference_source": "closed_form_symmetric_resistor_grid",
            "pdn_spice_sha256": _sha256("pdn_vdd.sp"),
            "supply_voltage_V": VDD_V,
            "worst_ir_drop_V": 2.5 * CELL_CURRENT_A * EDGE_RESISTANCE_OHM,
            "total_source_power_W": source_power,
            "total_load_power_W": load_power,
            "total_grid_loss_W": round(source_power - load_power, 12),
            "derivation": (
                "By symmetry, edge nodes are Vdd-2IR and corner nodes are "
                "Vdd-(5/2)IR for this 3x3 grid."
            ),
        },
    )

    artifacts = [
        "instance_power.csv",
        "instance_power.meta.json",
        "instances.csv",
        "joints.csv",
        "joints.meta.json",
        "pdn_vdd.sp",
        "reference_vdd_nodes.csv",
        "reference_vdd_nodes.meta.json",
    ]
    _write_json(
        "manifest.json",
        {
            "schema_version": 2,
            "design": "synthetic_pdn",
            "dbu_per_micron": DBU_PER_MICRON,
            "units": "micron",
            "n_instances": len(instances),
            "die_um": [0.0, 0.0, 100.0, 100.0],
            "core_um": [10.0, 10.0, 90.0, 90.0],
            "provenance": {
                "source_kind": "project_authored_synthetic_data",
                "origin": "project_authored_synthetic_fixture",
                "copyright": "2026 Teng Zhang and CoupMech Lab",
                "license": "Apache-2.0",
                "generator": "generate_case.py",
                "randomness": "none",
                "third_party_design_data": False,
                "purpose": (
                    "Deterministic integration and regression example; "
                    "not real-design validation."
                ),
            },
            "artifact_sha256": {name: _sha256(name) for name in artifacts},
        },
    )


if __name__ == "__main__":
    generate()
