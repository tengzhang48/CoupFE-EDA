"""Regression coverage for reviewed integration and CLI defects."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import numpy as np
import pytest


def _write_joint_map(tmp_path, rows, **metadata_overrides):
    csv_path = tmp_path / "joints.csv"
    csv_path.write_text(
        "joint_id,x,y,z,diameter,height,net,source_object_id\n" + "\n".join(rows) + "\n"
    )
    metadata = {
        "schema_version": 1,
        "coordinate_unit": "mm",
        "dimension_unit": "mm",
        "coordinate_frame": "package",
        "source": "test_export",
        "geometry_fidelity": "design_export",
        "transform_to_die_um": {
            "matrix": [[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]],
            "offset_um": [10.0, 20.0, 30.0],
        },
    }
    metadata.update(metadata_overrides)
    (tmp_path / "joints.meta.json").write_text(json.dumps(metadata))
    return csv_path


def test_joint_map_normalizes_units_and_applies_affine_transform(tmp_path):
    from eda_multiphysics.joint_map import load_joint_map

    path = _write_joint_map(
        tmp_path,
        ["J1,0.001,0.002,0.003,0.0005,0.0004,VDD,BUMP_A"],
        neutral_point_um=[8.0, 21.0, 33.0],
    )
    joints = load_joint_map(path)
    assert joints.ids == ("J1",)
    assert np.allclose(joints.xyz_um[0], [8.0, 21.0, 33.0])
    assert joints.diameter_um[0] == pytest.approx(0.5)
    assert joints.height_um[0] == pytest.approx(0.4)
    assert joints.nets == ("VDD",)
    assert joints.source_object_ids == ("BUMP_A",)
    assert joints.geometry_fidelity == "design_export"
    assert joints.dnp_um[0] == pytest.approx(0.0)


def test_joint_map_rejects_duplicate_stable_ids(tmp_path):
    from eda_multiphysics.joint_map import load_joint_map

    path = _write_joint_map(tmp_path, ["J1,0,0,0,,,,", "J1,1,1,0,,,,"])
    with pytest.raises(ValueError, match="duplicate joint_id"):
        load_joint_map(path)
    path = _write_joint_map(
        tmp_path,
        ["J1,0,0,0,,,,"],
        transform_to_die_um={
            "matrix": [[1.0, 0.0, 0.0], [0.0, 0.0, 0.0], [0.0, 0.0, 1.0]],
            "offset_um": [0.0, 0.0, 0.0],
        },
    )
    with pytest.raises(ValueError, match="must be nonsingular"):
        load_joint_map(path)
    path = _write_joint_map(
        tmp_path,
        ["J1,0,0,0,,,,"],
        geometry_fidelity="universal",
    )
    with pytest.raises(ValueError, match="geometry_fidelity must be one of"):
        load_joint_map(path)


def test_design_joints_prefers_explicit_map(tmp_path):
    from eda_multiphysics.reliability_3d import design_joints

    path = _write_joint_map(tmp_path, ["EXPLICIT_1,0,0,0,,,,BUMP_1"])
    joints = design_joints(tmp_path / "absent.sp", joint_map_path=path)
    assert joints["explicit"] is True
    assert joints["source"] == "test_export"
    assert joints["joint_ids"].tolist() == ["EXPLICIT_1"]


def test_design_joints_labels_pdn_fallback(tmp_path):
    from eda_multiphysics.reliability_3d import design_joints

    spice = tmp_path / "pdn.sp"
    spice.write_text("R1 VDD_0_0_1 VDD_2000_0_1 1.0\n")
    (tmp_path / "manifest.json").write_text(json.dumps({"dbu_per_micron": 2000}))
    joints = design_joints(spice)
    assert joints["explicit"] is False
    assert joints["source"] == "pdn_node_proxy_fallback"
    assert joints["joint_ids"].tolist() == ["PDN_PROXY_0000", "PDN_PROXY_0001"]


def test_bundled_synthetic_joint_map_is_an_explicit_labeled_proxy():
    from eda_multiphysics.reliability_3d import design_joints

    joints = design_joints()
    assert len(joints["xy"]) == 9
    assert len(set(joints["joint_ids"])) == 9
    assert joints["explicit"] is True
    assert joints["source"] == "project_authored_synthetic_joint_map"
    assert joints["geometry_fidelity"] == "proxy"
    assert np.allclose(np.ptp(joints["xy"], axis=0), [60.0, 60.0], atol=1e-12)
    assert np.isclose(joints["dnp"].max(), np.sqrt(1800.0), atol=1e-12)


def test_design_grid_reads_dbu_from_case_manifest():
    from eda_multiphysics.reliability_3d import design_grid

    xy, _center, dnp = design_grid()
    assert np.allclose(np.ptp(xy, axis=0), [60.0, 60.0], atol=1e-12)
    assert np.isclose(dnp.max(), np.sqrt(1800.0), atol=1e-12)


def test_design_grid_requires_units_for_standalone_netlist(tmp_path):
    from eda_multiphysics.reliability_3d import design_grid

    spice = tmp_path / "pdn.sp"
    spice.write_text("R1 VDD_0_0_1 VDD_2000_0_1 1.0\n")
    with pytest.raises(ValueError, match="pass dbu_per_um explicitly"):
        design_grid(spice)
    xy, _center, _dnp = design_grid(spice, dbu_per_um=2000)
    assert np.allclose(np.ptp(xy, axis=0), [1.0, 0.0])


def test_bundled_case_power_is_explicitly_synthetic_and_balanced(tmp_path):
    from eda_multiphysics.reliability_pipeline import (
        DEFAULT_CASE,
        _case_total_power,
        _case_voltage_reference,
        run as run_pipeline,
    )

    power = _case_total_power(DEFAULT_CASE)
    assert power["total_power_W"] == pytest.approx(8.9982e-3)
    assert power["provenance"] == "project_authored_synthetic_scenario"
    assert power["instance_power_model"] == "closed_form_dc_load_power"
    assert power["power_by_id"]["SYNTH_U11"] == pytest.approx(1.0e-3)
    assert power["power_by_id"]["SYNTH_U00"] == pytest.approx(0.99975e-3)

    result = run_pipeline(nx=4, ncyc=2, verbose=False)
    assert result["electrothermal_power_mode"] == "pdn_iv"
    assert result["release_validation"] is False
    assert result["analysis_role"] == "synthetic_integration_demonstration"
    assert result["source_power_coupled_W"] == pytest.approx(9.0e-3, abs=1e-12)
    assert result["thermal_power_coupled_W"] == pytest.approx(9.0e-3, abs=1e-12)
    assert abs(result["power_balance_error_W"]) < 1e-12

    default_spice = Path(DEFAULT_CASE) / "pdn_vdd.sp"
    reference = _case_voltage_reference(DEFAULT_CASE, 1.0, default_spice)
    assert reference["source"] == "closed_form_symmetric_resistor_grid"
    alternate_spice = tmp_path / "alternate.sp"
    alternate_spice.write_text(default_spice.read_text() + "* changed netlist identity\n")
    assert _case_voltage_reference(DEFAULT_CASE, 1.0, alternate_spice) is None
    alternate_result = run_pipeline(
        spice=alternate_spice, nx=4, ncyc=2, verbose=False
    )
    assert alternate_result["ir_reference"] is None
    assert alternate_result["electrothermal_power_mode"] == "fixed_instance"
    assert "No direct composed-case oracle" in alternate_result["claim_boundary"]


def test_em_screen_uses_upstream_temperature():
    from eda_multiphysics.reliability_3d import DEFAULT_SPICE
    from eda_multiphysics.reliability_pipeline import _em_screen_pdn

    ambient = _em_screen_pdn(DEFAULT_SPICE, 298.15, T_ref=298.15)
    hot = _em_screen_pdn(DEFAULT_SPICE, 348.15, T_ref=298.15)
    assert ambient["temp_acceleration"] == pytest.approx(1.0)
    assert hot["temp_acceleration"] > ambient["temp_acceleration"]
    assert hot["relative_lifetime"] < ambient["relative_lifetime"]


def test_tet_element_strain_reproduces_affine_field():
    from eda_multiphysics.reliability_3d import tet_element_strain

    coords = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0],
                       [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
    tets = np.array([[0, 1, 2, 3]])
    grad_u = np.array([[0.10, 0.02, -0.03],
                       [0.04, -0.05, 0.01],
                       [0.00, 0.06, 0.08]])
    U = np.zeros((4, 4))
    U[:, :3] = coords @ grad_u.T
    strain = tet_element_strain(coords, tets, U.ravel())[0]
    assert np.allclose(strain, 0.5 * (grad_u + grad_u.T), atol=1e-14)


def test_chip_vtu_has_one_entry_guard_and_two_intentional_regimes(monkeypatch):
    import eda_multiphysics.chip_vtu as chip_vtu

    tree = ast.parse(Path(chip_vtu.__file__).read_text())
    entry_guards = [
        node for node in tree.body
        if isinstance(node, ast.If) and "__name__" in ast.unparse(node.test)
        and "__main__" in ast.unparse(node.test)
    ]
    assert len(entry_guards) == 1

    calls = []
    monkeypatch.setattr(chip_vtu, "run", lambda *args, **kwargs: calls.append((args, kwargs)))
    chip_vtu.main(["case", "pdn.sp", "0.005"])
    assert len(calls) == 2
    assert {call[1]["t_si"] for call in calls} == {100e-6, 20e-6}


@pytest.mark.parametrize("module_name", [
    "eda_multiphysics.chip_vtu",
    "eda_multiphysics.electrothermal_chip",
    "eda_multiphysics.pdn_graph",
])
def test_required_argument_clis_report_usage(module_name, capsys):
    module = __import__(module_name, fromlist=["main"])
    with pytest.raises(SystemExit) as exc:
        module.main([])
    assert exc.value.code == 2
    assert "usage:" in capsys.readouterr().err


def test_case_thermal_defaults_to_synthetic_case_without_writing(monkeypatch):
    import eda_multiphysics.case_thermal as case_thermal

    calls = []
    monkeypatch.setattr(case_thermal, "run", lambda *args, **kwargs: calls.append((args, kwargs)))
    case_thermal.main([])
    assert calls == [((case_thermal.DEFAULT_CASE, None),
                      {"output_path": None, "power_provenance": None})]


def test_case_thermal_writes_power_metadata(tmp_path):
    from eda_multiphysics.case_thermal import DEFAULT_CASE, run

    output = tmp_path / "instance_temperature.csv"
    run(DEFAULT_CASE, 1e-5, output_path=output, power_provenance="test_scenario")
    metadata = json.loads((tmp_path / "instance_temperature.meta.json").read_text())
    assert metadata["total_power_W"] == pytest.approx(1e-5)
    assert metadata["total_power_provenance"] == "test_scenario"
    assert metadata["instance_power_model"] == "area_distributed_proxy"
    assert metadata["release_validation"] is False
    assert metadata["analysis_role"] == "integration_demonstration"
    assert "not real-device thermal validation or signoff" in metadata["claim_boundary"]
    assert metadata["source_case"] == str(Path(DEFAULT_CASE).resolve())
    assert metadata["thermal_boundary_condition"] == {
        "type": "dirichlet",
        "field": "temperature_rise",
        "boundary": "all_die_edges",
        "value_K": 0.0,
    }
    assert metadata["mesh_size"] == {
        "element_type": "Quad4",
        "nx": 72,
        "ny": 72,
        "n_elements": 72 * 72,
        "n_nodes": 73 * 73,
    }
    assert metadata["k_si_W_per_m_K"] == pytest.approx(148.0)
    assert metadata["thickness_m"] == pytest.approx(100e-6)
    assert output.exists()
