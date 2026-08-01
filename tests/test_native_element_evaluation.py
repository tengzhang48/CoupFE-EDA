"""Focused checks for the opt-in native residual-only ETV path."""

from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import pytest


def test_distributed_cli_keeps_joint_default_and_rejects_auto():
    from eda_multiphysics.etv_distributed import _parse_args

    assert _parse_args([]).element_evaluation == "joint"
    assert (
        _parse_args(["24", "--element-evaluation", "split"]).element_evaluation
        == "split"
    )
    with pytest.raises(SystemExit):
        _parse_args(["--element-evaluation", "auto"])


def test_serial_split_rejects_the_abaqus_uel_backend():
    from eda_multiphysics.etv_distributed import serial_solve

    with pytest.raises(
        ValueError,
        match="evaluation_mode='split' requires kernel_backend='native'",
    ):
        serial_solve(1, evaluation_mode="split", kernel_backend="abaqus_uel")


def test_etv_codegen_keeps_uel_default_and_emits_native_residual_entry(tmp_path):
    from eda_multiphysics.etv_kernel import build_et_kernel

    uel_path = build_et_kernel(tmp_path, compile=False, verify=False)
    native_path = build_et_kernel(
        tmp_path, compile=False, verify=False, backend="native"
    )

    uel_source = Path(uel_path).read_text(encoding="utf-8").lower()
    native_source = Path(native_path).read_text(encoding="utf-8").lower()
    assert uel_path.endswith("et_quad4.for")
    assert "subroutine uel" in uel_source
    assert "subroutine coupfe_element_rk" not in uel_source
    assert native_path.endswith("et_quad4_native.for")
    assert "subroutine coupfe_element_rk" in native_source
    assert "subroutine coupfe_element_r(" in native_source


@pytest.mark.toolchain
def test_native_joint_split_and_uel_joint_have_element_parity(tmp_path):
    """Compile both EDA targets and compare R, K, and native residual-only R."""
    if not shutil.which("gfortran"):
        pytest.skip("gfortran not available")

    from coupfe.runtime.compiled_element import CompiledElement
    from eda_multiphysics.etv_kernel import build_et_kernel

    uel_dir = tmp_path / "uel"
    native_dir = tmp_path / "native"
    uel_dir.mkdir()
    native_dir.mkdir()
    uel_module = build_et_kernel(
        uel_dir, sigma0=3.0, alpha=0.05, k=1.5, verify=False
    )
    native_module = build_et_kernel(
        native_dir,
        sigma0=3.0,
        alpha=0.05,
        k=1.5,
        verify=False,
        backend="native",
    )
    props = (3.0, 0.05, 1.5)
    uel = CompiledElement(
        uel_module, props=props, dof_per_node=2, n_svars=0, mcrd=2, n_elem=1
    )
    native = CompiledElement(
        native_module, props=props, dof_per_node=2, n_svars=0, mcrd=2, n_elem=1
    )
    coords = np.array([[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]])
    displacement = np.array(
        [[0.0, 0.0, 0.4, 0.1, 0.5, 0.2, 0.1, 0.15]], dtype=float
    )
    increment = np.zeros_like(displacement)

    r_uel, k_uel = uel.element_rk_batch(coords, displacement, increment)
    r_native, k_native = native.element_rk_batch(coords, displacement, increment)
    r_only = native.element_r_batch(coords, displacement, increment)

    assert not uel.has_residual_only
    assert native.has_residual_only
    np.testing.assert_allclose(r_native, r_uel, rtol=2.0e-12, atol=2.0e-12)
    np.testing.assert_allclose(k_native, k_uel, rtol=2.0e-12, atol=2.0e-12)
    np.testing.assert_allclose(r_only, r_native, rtol=2.0e-12, atol=2.0e-12)
