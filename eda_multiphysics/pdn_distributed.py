"""Distributed PDN electrical solve on PETSc/MPI — scaling the EDA application.

The serial `pdn_graph` solver (scipy) is fine for one chip; a flagship PDN is millions
of nodes. This integrates the EDA-multiphysics electrical solve with CoupFE's
distributed PETSc/MPI approach (cf. `coupfe/assembly/distributed.py`): the resistor-graph
Laplacian is assembled into a distributed PETSc matrix (each rank stamps only the edges
it owns; PETSc routes the off-process contributions), and a KSP (CG + GAMG algebraic
multigrid) solves it across ranks.

The trust gate is the same 1-vs-N invariant CoupFE uses: the gathered N-rank solution
must equal the serial scipy solve (to the KSP tolerance — this minimal PETSc build has no
distributed-direct solver, so iterative + tight rtol, not machine-precision LU).

    mpirun -n 4 python -m eda_multiphysics.pdn_distributed [grid_n]
"""

from __future__ import annotations

import sys
import time

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla
from petsc4py import PETSc


def build_grid_pdn(n):
    """An n x n resistor-grid model PDN: node id = j*n+i, unit-conductance edges to
    right/down neighbours, a corner voltage source, uniform per-node current draw."""
    nodes = n * n
    edges = []
    for j in range(n):
        for i in range(n):
            k = j * n + i
            if i < n - 1:
                edges.append((k, k + 1, 1.0))
            if j < n - 1:
                edges.append((k, k + n, 1.0))
    load = np.full(nodes, 1.0 / nodes)      # current drawn at each node
    load[0] = 0.0
    return nodes, np.array(edges), load, {0: 1.0}   # corner source at 1.0 V


def build_from_spice(path):
    """Load a caller-supplied PDN from an OpenROAD ``write_pg_spice`` netlist."""
    from .pdn_graph import parse_pg_spice
    idx, edges, load_d, vsrc = parse_pg_spice(path)
    n = len(idx)
    load = np.zeros(n)
    for nd, i in load_d.items():
        load[nd] = i
    dirichlet = dict(vsrc)                  # supply node(s)
    if "0" in idx:
        dirichlet[idx["0"]] = 0.0           # ground
    return n, np.array([(a, b, g) for a, b, g in edges]), load, dirichlet


def serial_solve(nodes, edges, load, dirichlet):
    """Independent oracle: assemble + direct solve with scipy."""
    G = sp.lil_matrix((nodes, nodes))
    for a, b, g in edges:
        a, b = int(a), int(b)
        G[a, a] += g; G[b, b] += g; G[a, b] -= g; G[b, a] -= g
    rhs = -load.copy()
    for nd, v in dirichlet.items():
        G.rows[nd] = [nd]; G.data[nd] = [1.0]; rhs[nd] = v
    return spla.spsolve(G.tocsr(), rhs)


def dist_solve(nodes, edges, load, dirichlet, rtol=1e-11, direct=False):
    """Distributed PETSc/MPI solve. Each rank stamps edges whose first node it owns.
    `direct=True` uses a reproducible distributed LU (superlu_dist) for exact 1-vs-N."""
    comm = PETSc.COMM_WORLD
    A = PETSc.Mat().createAIJ((nodes, nodes), comm=comm)
    A.setUp()
    r0, r1 = A.getOwnershipRange()
    for a, b, g in edges:
        a, b = int(a), int(b)
        if r0 <= a < r1:                    # owner of 'a' stamps the whole edge once
            A.setValues([a, b], [a, b], [[g, -g], [-g, g]],
                        addv=PETSc.InsertMode.ADD_VALUES)
    A.assemble()
    b = A.createVecRight()
    xbc = A.createVecRight()
    lo, hi = b.getOwnershipRange()
    for i in range(lo, hi):
        b.setValue(i, -float(load[i]))      # RHS = -load (current sinks)
    drows = sorted(dirichlet)
    for nd, v in dirichlet.items():
        if lo <= nd < hi:
            xbc.setValue(nd, v)             # prescribed potentials
    b.assemble(); xbc.assemble()
    # SYMMETRIC Dirichlet elimination -> A stays SPD (CG-safe), b adjusted for the columns
    A.zeroRowsColumns(drows, diag=1.0, x=xbc, b=b)
    x = A.createVecLeft()
    ksp = PETSc.KSP().create(comm)
    ksp.setOperators(A)
    if direct:                              # exact, reproducible 1-vs-N
        ksp.setType("preonly")
        pc = ksp.getPC(); pc.setType("lu")
        pc.setFactorSolverType("superlu_dist")
    else:
        ksp.setType("cg")
        ksp.getPC().setType("gamg")
        ksp.setTolerances(rtol=rtol, max_it=2000)
    ksp.solve(b, x)
    its = ksp.getIterationNumber()
    # gather to rank 0
    scat, seq = PETSc.Scatter.toZero(x)
    scat.scatter(x, seq, mode=PETSc.ScatterMode.FORWARD)
    V = np.array(seq.getArray()).copy() if comm.rank == 0 else None
    return V, its


def main():
    comm = PETSc.COMM_WORLD
    direct = "--direct" in sys.argv
    pos = [a for a in sys.argv[1:] if not a.startswith("--")]
    spec = pos[0] if pos else "120"
    if spec.endswith(".sp"):
        nodes, edges, load, dirichlet = build_from_spice(spec)
        label = spec.split("/")[-1]
    else:
        n = int(spec)
        nodes, edges, load, dirichlet = build_grid_pdn(n)
        label = f"{n}x{n} grid"
    t0 = time.time()
    V, its = dist_solve(nodes, edges, load, dirichlet, direct=direct)
    comm.barrier()
    dt = time.time() - t0
    if comm.rank == 0:
        Vs = serial_solve(nodes, edges, load, dirichlet)
        err = float(np.max(np.abs(V - Vs)))
        nondir = np.setdiff1d(np.arange(nodes), list(dirichlet))
        worst_ir = max(dirichlet.values()) - float(V[nondir].min())
        tol = 1e-9 if direct else 1e-7
        solver = "superlu_dist (direct)" if direct else f"CG+GAMG iters={its}"
        print(f"PDN {label} = {nodes} nodes, {len(edges)} edges | {comm.size} rank(s)")
        print(f"  {solver}  wall={dt:.2f}s")
        print(f"  worst IR drop = {worst_ir:.4e} V")
        print(f"  serial==N-rank: max|V_dist - V_serial| = {err:.2e}  "
              f"{'PASS' if err < tol else 'CHECK'}")


if __name__ == "__main__":
    main()
