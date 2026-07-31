"""Regression gates for the EDA-multiphysics suite (run: pytest eda_multiphysics).

The suite includes published/analytic oracles, independent-path comparisons,
invariants, interface/structural checks, and broken controls. Self-contained
(numpy+scipy+coupfe, no OpenROAD).
"""

import pytest

from eda_multiphysics.gates import GATES


@pytest.mark.parametrize("gate", GATES, ids=lambda g: g.__name__)
def test_gate(gate):
    r = gate()
    assert r["ok"], f"{r['name']} FAILED: {r['detail']}"
