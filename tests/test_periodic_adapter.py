"""Ownership and behavior gates for the EDA periodic-mesh adapter."""

from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import pytest

from coupfe.constraints.affine import compile_affine_constraints
from eda_multiphysics.periodic import (
    PeriodicBox,
    PeriodicNodePairs,
    periodic_relations,
)


def _grid():
    xs = [0.0, 1.0, 2.0]
    ys = [0.0, 0.5, 1.0]
    return np.array([[x, y] for y in ys for x in xs])


def test_periodic_box_and_two_axis_corner_relations():
    coords = _grid()
    box = PeriodicBox([0.0, 0.0], [[2.0, 0.0], [0.0, 1.0]], (True, True))
    left, right = np.array([6, 0, 3]), np.array([5, 8, 2])
    bottom, top = np.array([2, 0, 1]), np.array([7, 6, 8])
    x_pairs = box.pair_faces(coords, left, right, 0, atol=1.0e-12)
    y_pairs = box.pair_faces(coords, bottom, top, 1, atol=1.0e-12)
    assert x_pairs.master_nodes.tolist() == [0, 3, 6]
    assert x_pairs.slave_nodes.tolist() == [2, 5, 8]
    assert y_pairs.master_nodes.tolist() == [0, 1, 2]
    assert y_pairs.slave_nodes.tolist() == [6, 7, 8]
    assert x_pairs.max_mismatch == y_pairs.max_mismatch == 0.0

    gradient = np.array([[0.10, 0.02], [-0.03, 0.05]])
    relations = periodic_relations(
        (x_pairs, y_pairs),
        dof_per_node=2,
        components=(0, 1),
        coords=coords,
        macro_gradient=gradient,
    )
    assert len(relations) == 10
    transform = compile_affine_constraints(
        2 * len(coords), relations, dirichlet={0: 0.0, 1: 0.0}
    )
    displacement = transform.lift(np.zeros(transform.reduced_ndof)).reshape(-1, 2)
    for pairs in (x_pairs, y_pairs):
        expected = gradient @ pairs.translation
        assert np.allclose(
            displacement[pairs.slave_nodes] - displacement[pairs.master_nodes],
            expected,
            atol=2.0e-14,
            rtol=0.0,
        )
    assert np.max(np.abs(transform.constraint_error(displacement.ravel()))) < 2.0e-14

    assert np.allclose(
        box.wrap([[2.2, -0.1], [-0.1, 1.2]]),
        [[0.2, 0.9], [1.9, 0.2]],
        atol=1.0e-14,
    )
    assert box.image_shifts(1).shape == (9, 2)
    assert np.allclose(
        box.deformed_lattice(gradient), (np.eye(2) + gradient) @ box.lattice
    )
    assert len(box.sha256) == 64

    tiny = PeriodicBox(
        [-3.0e-6, -4.0e-6, -3.0e-6],
        np.diag([6.0e-6, 8.0e-6, 3.0e-6]),
        (True, True, False),
    )
    assert np.linalg.det(tiny.lattice) > 0.0


def test_periodic_matching_and_cycle_fail_closed():
    coords = _grid()
    box = PeriodicBox([0.0, 0.0], [[2.0, 0.0], [0.0, 1.0]], (True, True))
    with pytest.raises(ValueError, match="equal node counts"):
        box.pair_faces(coords, [0, 3, 6], [2, 5], 0, atol=1.0e-12)

    bad = coords.copy()
    bad[5, 1] += 0.1
    with pytest.raises(ValueError, match="do not match"):
        box.pair_faces(bad, [0, 3, 6], [2, 5, 8], 0, atol=1.0e-12)

    good = box.pair_faces(coords, [0, 3, 6], [2, 5, 8], 0, atol=1.0e-12)
    contradictory = PeriodicNodePairs(
        np.array([0]),
        np.array([2]),
        np.array([2.1, 0.0]),
        0.0,
        0.0,
        1.0e-12,
        "contradictory",
    )
    with pytest.raises(ValueError, match="inconsistent cycle"):
        periodic_relations(
            (good, contradictory),
            dof_per_node=2,
            components=(0, 1),
            coords=coords,
        )

    with pytest.raises(ValueError, match="right-handed"):
        PeriodicBox([0.0, 0.0], [[-2.0, 0.0], [0.0, 1.0]], (True, True))


def test_tsv_setup_consumes_eda_pairs_and_core_affine_primitives():
    from eda_multiphysics.tsv_local_3d import periodic_mpc_setup

    coords = np.column_stack([_grid(), np.zeros(9)])
    box = PeriodicBox(
        [0.0, 0.0, 0.0],
        np.diag([2.0, 1.0, 1.0]),
        (True, True, False),
    )
    faces = {
        "x_minus": np.array([6, 0, 3]),
        "x_plus": np.array([5, 8, 2]),
        "y_minus": np.array([2, 0, 1]),
        "y_plus": np.array([7, 6, 8]),
    }
    pair_sets = {
        "x": box.pair_faces(
            coords, faces["x_minus"], faces["x_plus"], 0, atol=1.0e-12
        ),
        "y": box.pair_faces(
            coords, faces["y_minus"], faces["y_plus"], 1, atol=1.0e-12
        ),
    }

    def record(pairs):
        return {
            "master_nodes": pairs.master_nodes,
            "slave_nodes": pairs.slave_nodes,
            "tolerance_um": pairs.tolerance,
            "sha256": pairs.sha256,
        }

    mesh = {
        "coords": coords,
        "periodic_pairing_status": "matching_nodes_verified",
        "periodic_box": {
            "origin_um": box.origin,
            "lattice_um": box.lattice,
            "periodic": box.periodic,
        },
        "periodic_faces": faces,
        "periodic_node_pairs": {
            axis: record(pairs) for axis, pairs in pair_sets.items()
        },
    }
    gradient = np.array(
        [[0.01, 0.02, 0.0], [-0.03, 0.04, 0.0], [0.0, 0.0, 0.05]]
    )
    relations, anchor, recorded_gradient, mismatch = periodic_mpc_setup(
        mesh, gradient
    )
    assert len(relations) == 15
    assert set(anchor) == {0, 1, 2}
    assert np.array_equal(recorded_gradient, gradient)
    assert mismatch == 0.0

    transform = compile_affine_constraints(
        3 * len(coords), relations, dirichlet=anchor
    )
    displacement = transform.lift(np.zeros(transform.reduced_ndof)).reshape(-1, 3)
    for pairs in pair_sets.values():
        assert np.allclose(
            displacement[pairs.slave_nodes] - displacement[pairs.master_nodes],
            gradient @ (pairs.translation * 1.0e-6),
            atol=2.0e-20,
            rtol=0.0,
        )

    mesh["periodic_node_pairs"]["x"]["sha256"] = "stale"
    with pytest.raises(ValueError, match="provenance hash"):
        periodic_mpc_setup(mesh, gradient)


def test_consumers_do_not_import_mesh_specific_adapters_from_core():
    root = Path(__file__).resolve().parents[1]
    forbidden = {
        "PeriodicBox",
        "PeriodicNodePairs",
        "match_periodic_nodes",
        "periodic_relations",
    }
    for relative in (
        "eda_multiphysics/mesh3d.py",
        "eda_multiphysics/tsv_local_3d.py",
    ):
        tree = ast.parse((root / relative).read_text(encoding="utf-8"))
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            and node.module is not None
            and node.module.startswith("coupfe")
            for alias in node.names
        }
        assert not imported & forbidden


@pytest.mark.parametrize(
    "invalid_index",
    [True, np.bool_(False), "1", 1.0, 1.9, np.float64(2.0)],
)
def test_periodic_adapter_rejects_lossy_integer_controls(invalid_index):
    with pytest.raises(TypeError, match="must be an integer"):
        PeriodicNodePairs(
            np.array([invalid_index], dtype=object),
            np.array([2]),
            np.array([2.0, 0.0]),
            0.0,
            0.0,
            1.0e-12,
            "invalid-index",
        )

    box = PeriodicBox([0.0, 0.0], np.eye(2), (True, True))
    with pytest.raises(TypeError, match="master_nodes entry must be an integer"):
        box.pair_faces(
            np.array([[0.0, 0.0], [1.0, 0.0]]),
            np.array([invalid_index], dtype=object),
            np.array([1]),
            0,
            atol=1.0e-12,
        )
    with pytest.raises(TypeError, match="axis must be an integer"):
        box.translation(invalid_index)
    with pytest.raises(TypeError, match="layers must be an integer"):
        box.image_shifts(invalid_index)

    pairs = PeriodicNodePairs(
        np.array([0]),
        np.array([1]),
        np.array([1.0, 0.0]),
        0.0,
        0.0,
        1.0e-12,
        "valid",
    )
    with pytest.raises(TypeError, match="dof_per_node must be an integer"):
        periodic_relations(
            pairs,
            dof_per_node=invalid_index,
            components=(0,),
        )
    with pytest.raises(TypeError, match="component must be an integer"):
        periodic_relations(
            pairs,
            dof_per_node=2,
            components=(invalid_index,),
        )


def test_periodic_adapter_accepts_numpy_integer_controls():
    pairs = PeriodicNodePairs(
        np.array([np.int64(0)]),
        np.array([np.int32(1)]),
        np.array([1.0, 0.0]),
        0.0,
        0.0,
        1.0e-12,
        "numpy-integers",
    )
    box = PeriodicBox([0.0, 0.0], np.eye(2), (True, True))

    assert np.array_equal(box.translation(np.int64(0), np.int32(-1)), [-1.0, 0.0])
    assert box.image_shifts(np.int64(1)).shape == (9, 2)
    relations = periodic_relations(
        pairs,
        dof_per_node=np.int64(2),
        components=(np.int32(0),),
    )
    assert len(relations) == 1


def test_periodic_box_requires_boolean_periodic_flags():
    with pytest.raises(TypeError, match="flags must be booleans"):
        PeriodicBox([0.0, 0.0], np.eye(2), (1, 0))
