"""EDA-owned periodic-mesh adapters for affine multi-point constraints.

The lattice metadata, translated-node matching, and periodic graph construction
belong to the mesh-aware EDA layer.  The solver core supplies only the generic
``ConstraintRelation`` primitive consumed by ``periodic_relations``.

The matching and graph algorithms are adapted from ``coupfe/mesh/periodic.py`` and
``coupfe/constraints/periodic.py`` at CoupFE commit
``70ea06355ecf55cecb5ae01c55a377c03879470b`` (Apache-2.0).  Keeping that
source revision here makes the ownership move and numerical provenance
explicit; public input validation is hardened in this EDA-owned adapter.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import itertools
import json
import operator

import numpy as np
from scipy.spatial import cKDTree

from coupfe.constraints.affine import ConstraintRelation


def _index(value, *, name):
    """Return an actual integer control without lossy coercion."""

    if isinstance(value, (bool, np.bool_)):
        raise TypeError(f"{name} must be an integer, not a boolean")
    try:
        return int(operator.index(value))
    except TypeError as exc:
        raise TypeError(f"{name} must be an integer") from exc


def _index_array(values, *, name):
    """Validate a one-dimensional node-ID array before converting its dtype."""

    values = np.asarray(values, dtype=object)
    if values.ndim != 1:
        raise ValueError(f"{name} must be one-dimensional")
    return np.asarray(
        [_index(value, name=f"{name} entry") for value in values],
        dtype=int,
    )


@dataclass(frozen=True)
class PeriodicNodePairs:
    """One translated master/slave face correspondence."""

    master_nodes: np.ndarray
    slave_nodes: np.ndarray
    translation: np.ndarray
    max_mismatch: float
    rms_mismatch: float
    tolerance: float
    sha256: str

    def __post_init__(self):
        for name in ("master_nodes", "slave_nodes"):
            value = _index_array(getattr(self, name), name=name)
            value.setflags(write=False)
            object.__setattr__(self, name, value)
        value = np.asarray(self.translation, dtype=float).copy()
        value.setflags(write=False)
        object.__setattr__(self, "translation", value)
        if (
            self.master_nodes.ndim != 1
            or self.slave_nodes.ndim != 1
            or len(self.master_nodes) == 0
            or len(self.master_nodes) != len(self.slave_nodes)
        ):
            raise ValueError(
                "periodic node-pair arrays must be nonempty, one-dimensional, and equal"
            )
        if (
            np.any(self.master_nodes < 0)
            or np.any(self.slave_nodes < 0)
            or len(np.unique(self.master_nodes)) != len(self.master_nodes)
            or len(np.unique(self.slave_nodes)) != len(self.slave_nodes)
            or np.intersect1d(self.master_nodes, self.slave_nodes).size
        ):
            raise ValueError(
                "periodic node pairs require unique, non-negative, disjoint faces"
            )
        if self.translation.ndim != 1 or not np.all(np.isfinite(self.translation)):
            raise ValueError("periodic translation must be a finite vector")
        if np.linalg.norm(self.translation) == 0.0:
            raise ValueError("periodic translation must be nonzero")
        metrics = np.asarray(
            [self.max_mismatch, self.rms_mismatch, self.tolerance], dtype=float
        )
        if not np.all(np.isfinite(metrics)) or np.any(metrics < 0.0):
            raise ValueError(
                "periodic mismatch metrics and tolerance must be finite and non-negative"
            )
        if not str(self.sha256):
            raise ValueError("periodic node pairs require a provenance hash")


def match_periodic_nodes(
    coords,
    master_nodes,
    slave_nodes,
    translation,
    *,
    atol,
    rtol=0.0,
) -> PeriodicNodePairs:
    """Match ``master + translation`` to slave nodes with a strict bijection.

    The result is sorted geometrically and is independent of input face ordering.
    Nonmatching meshes, duplicate nodes, and nearest-neighbour guesses outside the
    declared tolerance are rejected.
    """

    coords = np.asarray(coords, dtype=float)
    masters = _index_array(master_nodes, name="master_nodes")
    slaves = _index_array(slave_nodes, name="slave_nodes")
    translation = np.asarray(translation, dtype=float).reshape(-1)
    atol, rtol = float(atol), float(rtol)
    if coords.ndim != 2 or not np.all(np.isfinite(coords)):
        raise ValueError("coords must be a finite (N,dim) array")
    if translation.shape != (coords.shape[1],) or not np.all(
        np.isfinite(translation)
    ):
        raise ValueError(
            "translation must be finite with one entry per coordinate dimension"
        )
    if np.linalg.norm(translation) == 0.0:
        raise ValueError("periodic face translation must be nonzero")
    if (
        not np.isfinite(atol)
        or atol < 0.0
        or not np.isfinite(rtol)
        or rtol < 0.0
    ):
        raise ValueError(
            "periodic matching tolerances must be finite and non-negative"
        )
    if len(masters) == 0 or len(masters) != len(slaves):
        raise ValueError("periodic faces must be nonempty and have equal node counts")
    if (
        np.any(masters < 0)
        or np.any(masters >= len(coords))
        or np.any(slaves < 0)
        or np.any(slaves >= len(coords))
    ):
        raise ValueError("periodic face contains an out-of-range node")
    if len(np.unique(masters)) != len(masters) or len(np.unique(slaves)) != len(
        slaves
    ):
        raise ValueError("periodic faces cannot contain duplicate node IDs")
    if np.intersect1d(masters, slaves).size:
        raise ValueError("master and slave faces must be disjoint")

    tolerance = atol + rtol * max(float(np.linalg.norm(translation)), 1.0)
    tree = cKDTree(coords[slaves])
    distances, local = tree.query(coords[masters] + translation, k=1)
    if np.any(~np.isfinite(distances)) or np.any(distances > tolerance):
        worst = float(np.max(distances))
        raise ValueError(
            f"periodic faces do not match within tolerance {tolerance:.3e}; "
            f"maximum nearest mismatch is {worst:.3e}"
        )
    paired_slaves = slaves[np.asarray(local, dtype=int)]
    if len(np.unique(paired_slaves)) != len(slaves):
        raise ValueError("periodic nearest-neighbour map is not one-to-one")

    # Canonical geometric ordering, with node ID only as an exact-coordinate tie-break.
    keys = [masters]
    keys.extend(coords[masters, axis] for axis in reversed(range(coords.shape[1])))
    order = np.lexsort(tuple(keys))
    masters = masters[order]
    paired_slaves = paired_slaves[order]
    distances = np.asarray(distances)[order]
    payload = json.dumps(
        {
            "master_nodes": masters.tolist(),
            "slave_nodes": paired_slaves.tolist(),
            "translation": translation.tolist(),
            "tolerance": tolerance,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return PeriodicNodePairs(
        masters,
        paired_slaves,
        translation,
        float(np.max(distances)),
        float(np.sqrt(np.mean(distances * distances))),
        float(tolerance),
        hashlib.sha256(payload.encode("utf-8")).hexdigest(),
    )


@dataclass(frozen=True)
class PeriodicBox:
    """Reference lattice and per-axis periodicity for an EDA mesh."""

    origin: np.ndarray
    lattice: np.ndarray
    periodic: tuple[bool, ...]
    coordinate_frame: object = None

    def __post_init__(self):
        origin = np.asarray(self.origin, dtype=float).reshape(-1).copy()
        lattice = np.asarray(self.lattice, dtype=float).copy()
        periodic_values = np.asarray(self.periodic, dtype=object)
        if periodic_values.ndim != 1:
            raise ValueError("periodic flags must be one-dimensional")
        if not all(
            isinstance(value, (bool, np.bool_)) for value in periodic_values
        ):
            raise TypeError("periodic flags must be booleans")
        periodic = tuple(bool(value) for value in periodic_values)
        if (
            lattice.shape != (len(origin), len(origin))
            or len(periodic) != len(origin)
            or not np.all(np.isfinite(origin))
            or not np.all(np.isfinite(lattice))
        ):
            raise ValueError(
                "origin, square lattice, and periodic flags must have one dimension"
            )
        if not any(periodic):
            raise ValueError("PeriodicBox requires at least one periodic axis")
        determinant = float(np.linalg.det(lattice))
        scale = float(np.linalg.norm(lattice, ord=2))
        if scale == 0.0:
            raise ValueError(
                "periodic lattice must be finite, nonsingular, and right-handed"
            )
        if determinant <= 100.0 * np.finfo(float).eps * scale ** len(origin):
            raise ValueError(
                "periodic lattice must be finite, nonsingular, and right-handed"
            )
        origin.setflags(write=False)
        lattice.setflags(write=False)
        object.__setattr__(self, "origin", origin)
        object.__setattr__(self, "lattice", lattice)
        object.__setattr__(self, "periodic", periodic)

    @property
    def ndim(self):
        return len(self.origin)

    @property
    def sha256(self):
        payload = json.dumps(
            {
                "origin": self.origin.tolist(),
                "lattice": self.lattice.tolist(),
                "periodic": self.periodic,
                "coordinate_frame": self.coordinate_frame,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def fractional_coordinates(self, points):
        points = np.asarray(points, dtype=float)
        if points.shape[-1:] != (self.ndim,) or not np.all(np.isfinite(points)):
            raise ValueError("points must be finite with the box coordinate dimension")
        return np.linalg.solve(
            self.lattice, (points - self.origin).reshape(-1, self.ndim).T
        ).T.reshape(points.shape)

    def wrap(self, points):
        """Return wrapped query coordinates without modifying the authoritative mesh."""

        fractional = self.fractional_coordinates(points)
        wrapped = fractional.copy()
        for axis, is_periodic in enumerate(self.periodic):
            if is_periodic:
                wrapped[..., axis] -= np.floor(wrapped[..., axis])
        return self.origin + wrapped @ self.lattice.T

    def translation(self, axis, direction=1):
        axis = _index(axis, name="axis")
        direction = _index(direction, name="direction")
        if axis < 0 or axis >= self.ndim or not self.periodic[axis]:
            raise ValueError("axis must identify a periodic box direction")
        if direction not in (-1, 1):
            raise ValueError("periodic translation direction must be -1 or +1")
        return direction * self.lattice[:, axis]

    def image_shifts(self, layers=1):
        """Lattice shifts for visualization/search only; never assemble image volumes."""

        layers = _index(layers, name="layers")
        if layers < 0:
            raise ValueError("image layers must be non-negative")
        ranges = [
            range(-layers, layers + 1) if flag else (0,) for flag in self.periodic
        ]
        coefficients = np.asarray(list(itertools.product(*ranges)), dtype=float)
        return coefficients @ self.lattice.T

    def deformed_lattice(self, macro_gradient):
        macro_gradient = np.asarray(macro_gradient, dtype=float)
        if macro_gradient.shape != self.lattice.shape or not np.all(
            np.isfinite(macro_gradient)
        ):
            raise ValueError("macro_gradient must be finite with the lattice shape")
        return (np.eye(self.ndim) + macro_gradient) @ self.lattice

    def pair_faces(self, coords, minus_nodes, plus_nodes, axis, *, atol, rtol=0.0):
        return match_periodic_nodes(
            coords,
            minus_nodes,
            plus_nodes,
            self.translation(axis),
            atol=atol,
            rtol=rtol,
        )


def periodic_relations(
    pair_sets,
    *,
    dof_per_node,
    components,
    coords=None,
    macro_gradient=None,
    scalar_gradient=None,
    label="periodic",
):
    """Canonicalize translated pairs into acyclic exact MPC relations.

    Edge and corner nodes may occur in more than one pair set.  A graph potential
    composes their lattice translations, chooses one representative per equivalence
    class, and rejects inconsistent cycles.
    """

    if isinstance(pair_sets, PeriodicNodePairs):
        pair_sets = (pair_sets,)
    else:
        pair_sets = tuple(pair_sets)
    if not pair_sets or not all(
        isinstance(item, PeriodicNodePairs) for item in pair_sets
    ):
        raise TypeError("pair_sets must contain PeriodicNodePairs")
    dpn = _index(dof_per_node, name="dof_per_node")
    components = tuple(
        _index(component, name="component") for component in components
    )
    if dpn <= 0 or not components or len(set(components)) != len(components):
        raise ValueError("dof_per_node and unique selected components are required")
    if any(component < 0 or component >= dpn for component in components):
        raise ValueError("periodic component is outside the node DOF layout")
    ndim = len(pair_sets[0].translation)
    if any(len(item.translation) != ndim for item in pair_sets):
        raise ValueError("all periodic translations must use the same dimension")
    if macro_gradient is not None and scalar_gradient is not None:
        raise ValueError("choose macro_gradient or scalar_gradient, not both")
    if scalar_gradient is not None:
        if len(components) != 1:
            raise ValueError(
                "scalar_gradient requires exactly one selected component"
            )
        jump_matrix = np.asarray(scalar_gradient, dtype=float).reshape(1, -1)
    elif macro_gradient is not None:
        jump_matrix = np.asarray(macro_gradient, dtype=float)
    else:
        jump_matrix = np.zeros((len(components), ndim))
    if jump_matrix.shape != (len(components), ndim) or not np.all(
        np.isfinite(jump_matrix)
    ):
        raise ValueError(
            "periodic gradient has incompatible shape or non-finite values"
        )

    coords_array = None if coords is None else np.asarray(coords, dtype=float)
    if coords_array is not None and (
        coords_array.ndim != 2
        or coords_array.shape[1] != ndim
        or not np.all(np.isfinite(coords_array))
    ):
        raise ValueError(
            "coords must be finite and dimensionally compatible with the pairs"
        )

    graph = {}
    scale = 1.0
    for pairs in pair_sets:
        scale = max(scale, float(np.linalg.norm(pairs.translation)))
        for master, slave in zip(pairs.master_nodes, pairs.slave_nodes):
            master = _index(master, name="master node")
            slave = _index(slave, name="slave node")
            graph.setdefault(master, []).append((slave, pairs.translation))
            graph.setdefault(slave, []).append((master, -pairs.translation))
    if coords_array is not None and graph and max(graph) >= len(coords_array):
        raise ValueError("coords does not contain every paired node")

    def root_key(node):
        if coords_array is None:
            return (node,)
        return tuple(coords_array[node]) + (node,)

    unseen = set(graph)
    relations = []
    cycle_atol = 1.0e-10 * scale
    while unseen:
        root = min(unseen, key=root_key)
        potential = {root: np.zeros(ndim)}
        stack = [root]
        while stack:
            node = stack.pop()
            for neighbour, shift in graph[node]:
                candidate = potential[node] + shift
                if neighbour in potential:
                    if not np.allclose(
                        potential[neighbour],
                        candidate,
                        atol=cycle_atol,
                        rtol=1.0e-12,
                    ):
                        raise ValueError(
                            "periodic edge/corner relations contain an inconsistent cycle"
                        )
                else:
                    potential[neighbour] = candidate
                    stack.append(neighbour)
        unseen.difference_update(potential)
        for node in sorted(
            (value for value in potential if value != root), key=root_key
        ):
            jump = jump_matrix @ potential[node]
            for local, component in enumerate(components):
                relations.append(
                    ConstraintRelation(
                        slave=node * dpn + component,
                        masters=(root * dpn + component,),
                        coefficients=(1.0,),
                        offset=float(jump[local]),
                        label=f"{label}:node{node}->node{root}:c{component}",
                    )
                )
    return tuple(relations)


__all__ = [
    "PeriodicBox",
    "PeriodicNodePairs",
    "match_periodic_nodes",
    "periodic_relations",
]
