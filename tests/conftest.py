"""Shared fixtures for the toolchain regression tier.

The toolchain tests compile Fortran kernels via f2py. These fixtures build each kernel once
per test module and share the resulting compiled module / workdir across the toolchain tier.
"""
from __future__ import annotations

import os
import shutil
import tempfile

import pytest


def _require_toolchain_deps():
    """Skip the current test if any hard toolchain dependency is missing."""
    pytest.importorskip("gmsh")
    pytest.importorskip("petsc4py")
    if not shutil.which("gfortran"):
        pytest.skip("gfortran not available")


@pytest.fixture(scope="module")
def etv_workdir():
    """Shared workdir with a compiled electro-thermal Hex8 kernel."""
    _require_toolchain_deps()
    from eda_multiphysics.etv_kernel import build_et_kernel

    wd = tempfile.mkdtemp(prefix="etv_kernel_")
    build_et_kernel(wd, sigma0=3.0, alpha=0.0, k=1.5, element="Hex8")
    yield wd
    shutil.rmtree(wd, ignore_errors=True)


@pytest.fixture(scope="module")
def tm_kernel_module():
    """Shared compiled thermo-mechanical Hex8 kernel module + its workdir."""
    _require_toolchain_deps()
    from eda_multiphysics.thermomech_kernel import build_thermomech_kernel

    wd = tempfile.mkdtemp(prefix="tm_kernel_")
    mod = build_thermomech_kernel(wd, element="Hex8")
    yield mod, wd
    shutil.rmtree(wd, ignore_errors=True)


@pytest.fixture(scope="module")
def tm_tet_kernel_module():
    """Shared compiled thermo-mechanical Tet4 kernel for conformal package tests."""
    _require_toolchain_deps()
    from eda_multiphysics.thermomech_kernel import build_thermomech_kernel

    wd = tempfile.mkdtemp(prefix="tm_tet_kernel_")
    mod = build_thermomech_kernel(wd, element="Tet4")
    yield mod, wd
    shutil.rmtree(wd, ignore_errors=True)
