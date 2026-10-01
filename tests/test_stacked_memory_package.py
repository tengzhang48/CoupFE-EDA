"""Stacked-memory package example: oracle logic (default tier) and the full run (toolchain tier)."""
from __future__ import annotations

import copy
import importlib.util
import json
import os
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "stacked_memory_package"


def _run_module():
    spec = importlib.util.spec_from_file_location("stacked_package_run", EXAMPLE / "run.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _summary_from_oracle(oracle):
    """A summary that satisfies every metric exactly and every bound with zero."""
    summary = {}

    def put(path, value):
        node = summary
        keys = path.split(".")
        for key in keys[:-1]:
            node = node.setdefault(key, {})
        node[keys[-1]] = value

    for metric in oracle["metrics"]:
        put(metric["path"], metric["value"])
    for bound in oracle["bounds"]:
        put(bound["path"], 0.0)
    return summary


@pytest.mark.parametrize("name", ["expected_results.json", "expected_results_h045.json"])
def test_oracle_is_self_consistent_and_check_detects_changes(name):
    run = _run_module()
    path = EXAMPLE / name
    oracle = json.loads(path.read_text())
    assert oracle["metrics"] and oracle["bounds"]
    summary = _summary_from_oracle(oracle)
    assert run.check(summary, path) == []

    changed = copy.deepcopy(summary)
    changed["mechanics"]["baseline"]["substrate_warpage_um"] *= 1.001
    assert any("substrate_warpage_um" in f for f in run.check(changed, path))

    broken = copy.deepcopy(summary)
    broken["thermal"]["improved"]["balance_error_relative"] = 1e-3
    assert any("balance_error_relative" in f for f in run.check(broken, path))


@pytest.mark.toolchain
def test_quick_package_run_matches_retained_result(tmp_path):
    if shutil.which("gfortran") is None:
        pytest.skip("gfortran is required to compile the native kernels")
    if importlib.util.find_spec("gmsh") is None and not os.environ.get("CAD_PYTHON"):
        pytest.skip("gmsh (or CAD_PYTHON pointing to a Python with gmsh) is required")
    sys.path.insert(0, str(EXAMPLE))
    run = _run_module()
    assert run.main(["--output", str(tmp_path / "h0.65"), "--check"]) == 0
