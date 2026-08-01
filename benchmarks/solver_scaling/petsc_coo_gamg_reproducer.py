#!/usr/bin/env python
"""Historical PETSc ``MatSetValuesCOO``/GAMG repeated-solve reproducer.

During development, this standalone scalar-Laplacian case reproduced a pattern
under PETSc/petsc4py 3.24.2 and 3.25.2: three fresh GAMG solves assembled with
ordinary ``setValues`` converged, while a COO-assembled matrix converged on the
first solve and later solves in the same process failed. That observation led
the EDA distributed driver to use batched element evaluation plus owned-row CSR
construction rather than ``setValuesCOO``.

This script is preserved as technical history and a version-specific diagnostic.
It contains no CoupFE-EDA application code and is not part of the pass/fail test
suite. It exits 1 when the historical failure signature is reproduced and 0
otherwise; either outcome must be reported with the PETSc build and complete
process output.

Run from the repository root with a PETSc-enabled environment:

    python benchmarks/solver_scaling/petsc_coo_gamg_reproducer.py
"""
from __future__ import annotations

import sys

import numpy as np
import petsc4py
from petsc4py import PETSc


def laplacian_triplets(n):
    """Return COO triplets for an ``n`` by ``n`` five-point Laplacian."""
    indices = np.arange(n * n).reshape(n, n)
    diagonal = indices.ravel()
    rows = [diagonal]
    columns = [diagonal]
    values = [4.0 * np.ones(n * n)]
    for row_shift, column_shift in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        neighbor = np.roll(np.roll(indices, row_shift, axis=0), column_shift, axis=1)
        mask = np.ones((n, n), dtype=bool)
        if row_shift == -1:
            mask[0, :] = False
        if row_shift == 1:
            mask[-1, :] = False
        if column_shift == -1:
            mask[:, 0] = False
        if column_shift == 1:
            mask[:, -1] = False
        selected = mask.ravel()
        rows.append(diagonal[selected])
        columns.append(neighbor.ravel()[selected])
        values.append(-np.ones(selected.sum()))
    return (
        np.concatenate(rows).astype(PETSc.IntType),
        np.concatenate(columns).astype(PETSc.IntType),
        np.concatenate(values),
    )


def main():
    communicator = PETSc.COMM_WORLD
    n = 60
    ndof = n * n
    rows, columns, values = laplacian_triplets(n)
    right_hand_side = PETSc.Vec().createMPI(ndof, comm=communicator)
    right_hand_side.set(1.0)
    right_hand_side.assemble()

    def build(use_coo):
        matrix = PETSc.Mat().createAIJ([ndof, ndof], comm=communicator)
        if use_coo:
            matrix.setPreallocationCOO(rows, columns)
            matrix.setValuesCOO(values)
        else:
            matrix.setPreallocationNNZ(5)
            matrix.setOption(PETSc.Mat.Option.NEW_NONZERO_ALLOCATION_ERR, False)
            for row, column, value in zip(rows, columns, values):
                matrix.setValues(
                    [int(row)],
                    [int(column)],
                    [value],
                    addv=PETSc.InsertMode.ADD_VALUES,
                )
        matrix.assemble()
        return matrix

    def solve(matrix):
        solver = PETSc.KSP().create(communicator)
        solver.setOperators(matrix)
        solver.setType("gmres")
        solver.setTolerances(rtol=1.0e-10, max_it=500)
        solver.getPC().setType("gamg")
        solver.setUp()
        solution = matrix.createVecLeft()
        solver.solve(right_hand_side, solution)
        result = (solver.getIterationNumber(), int(solver.getConvergedReason()))
        solution.destroy()
        matrix.destroy()
        solver.destroy()
        return result

    print(f"petsc4py {petsc4py.__version__}; PETSc {PETSc.Sys.getVersion()}")
    set_values_results = [solve(build(False)) for _ in range(3)]
    print(f"setValues + GAMG x3:    {set_values_results}")
    coo_results = [solve(build(True)) for _ in range(3)]
    print(f"setValuesCOO + GAMG x3: {coo_results}")

    set_values_healthy = all(reason > 0 for _, reason in set_values_results)
    coo_first_healthy = coo_results[0][1] > 0
    coo_later_failed = all(reason < 0 for _, reason in coo_results[1:])
    reproduced = set_values_healthy and coo_first_healthy and coo_later_failed
    print(
        "historical signature reproduced: "
        f"{reproduced} (ordinary path healthy={set_values_healthy}, "
        f"COO first solve healthy={coo_first_healthy}, "
        f"COO later solves failed={coo_later_failed})"
    )
    right_hand_side.destroy()
    return 1 if reproduced else 0


if __name__ == "__main__":
    sys.exit(main())
