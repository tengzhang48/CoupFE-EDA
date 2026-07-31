"""1D PDN-graph electrical conduction on the CoupFE operator contract (plan 4.1).

Solves a power-delivery network as a resistor graph: nodes carry a potential,
edges are metal-segment/via conductances, current sources are instance loads, the
voltage source is the supply. This is the 1D model the plan calls for, and it lets
us validate against PDNSim *on the identical network* (parsed from `write_pg_spice`)
so any discrepancy is solver-only, not modeling.

The operator is a graph Laplacian: residual_n = sum_e g_e (V_n - V_m) + I_load_n,
Dirichlet at the supply node (and ground). Tangent is the (constant) conductance
matrix — identical to what complex-step would return for this linear operator.

Run:  python -m eda_multiphysics.pdn_graph <pdn.sp> [pdnsim_worst_ir] [pdnsim_avg_ir]
"""

from __future__ import annotations

import argparse

import numpy as np

from coupfe import newton_solve
from coupfe.operators.base import Residual, Tangent


def parse_pg_spice(path):
    """Parse an OpenROAD write_pg_spice netlist -> (node_index, edges, load, vsrc)."""
    idx = {}

    def nid(name):
        return idx.setdefault(name, len(idx))

    edges, load, vsrc = [], {}, {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line[0] in "*.":
                continue
            p = line.split()
            kind = p[0][0].upper()
            if kind == "R":
                a, b, R = nid(p[1]), nid(p[2]), float(p[3])
                if R > 0:
                    edges.append((a, b, 1.0 / R))
            elif kind == "I":                       # current source node -> ground (a load)
                load[nid(p[1])] = load.get(nid(p[1]), 0.0) + float(p[3])
                nid(p[2])
            elif kind == "V":                       # voltage source: fix node potential
                vsrc[nid(p[1])] = float(p[3])
                nid(p[2])
    return idx, edges, load, vsrc


class GraphConduction:
    """CoupFE Operator: steady conduction on a resistor graph."""

    def __init__(self, nnode, edges, load_vec):
        self.nnode = nnode
        self.edges = edges
        self.f = load_vec                            # (nnode,) positive load currents

    def residual(self, V, state, t, dt):
        R = self.f.astype(V.dtype).copy()
        for a, b, g in self.edges:
            d = g * (V[a] - V[b])
            R[a] += d
            R[b] -= d
        return Residual(gdofs=np.arange(self.nnode), values=R)

    def tangent(self, V, state, t, dt):
        rows, cols, vals = [], [], []
        for a, b, g in self.edges:
            rows += [a, b, a, b]
            cols += [a, b, b, a]
            vals += [g, g, -g, -g]
        return Tangent(rows=np.array(rows), cols=np.array(cols), values=np.array(vals))

    def commit(self, V, state, t, dt):
        return state


def solve_pdn(path, conductance_scale=None):
    """Solve a write_pg_spice PDN. `conductance_scale` (per-edge) enables R(T)."""
    idx, edges, load, vsrc = parse_pg_spice(path)
    n = len(idx)
    if conductance_scale is not None:
        edges = [(a, b, g * s) for (a, b, g), s in zip(edges, conductance_scale)]
    f = np.zeros(n)
    for node, i in load.items():
        f[node] = i
    op = GraphConduction(n, edges, f)
    dirichlet = dict(vsrc)
    if "0" in idx:
        dirichlet[idx["0"]] = 0.0
    Vsupply = max(vsrc.values())
    V, _, nit = newton_solve([op], np.full(n, Vsupply), None, n, dirichlet)
    return dict(idx=idx, V=V, edges=edges, load=f, vsrc=vsrc, Vsupply=Vsupply,
                nit=nit, n=n, n_edges=len(edges))


def _grid_mask(idx, vsrc):
    """All nodes except global ground '0'."""
    m = np.ones(len(idx), dtype=bool)
    if "0" in idx:
        m[idx["0"]] = False
    return m


def main(argv=None):
    parser = argparse.ArgumentParser(description="Solve a PDNSim write_pg_spice network.")
    parser.add_argument("path", help="PDNSim write_pg_spice netlist")
    parser.add_argument("pdnsim_worst", nargs="?", type=float,
                        help="optional PDNSim worst IR drop in V")
    parser.add_argument("pdnsim_avg", nargs="?", type=float,
                        help="optional PDNSim average IR drop in V")
    args = parser.parse_args(argv)

    r = solve_pdn(args.path)
    m = _grid_mask(r["idx"], r["vsrc"])
    drop = r["Vsupply"] - r["V"][m]
    worst, avg = float(drop.max()), float(drop.mean())

    print(f"\nCoupFE PDN-graph solve of {args.path}")
    print(f"  nodes={r['n']}  edges={r['n_edges']}  loads={int((r['load']>0).sum())}  "
          f"Vsupply={r['Vsupply']}  Newton iters={r['nit']}")
    print(f"  worst IR drop = {worst:.4e} V")
    print(f"  avg   IR drop = {avg:.4e} V")
    if args.pdnsim_worst is not None:
        e = abs(worst - args.pdnsim_worst) / args.pdnsim_worst
        print(f"\n  vs PDNSim worst {args.pdnsim_worst:.4e} V  ->  rel err {e:.2%}  "
              f"{'PASS' if e < 0.02 else 'CHECK'}")
    if args.pdnsim_avg is not None:
        e = abs(avg - args.pdnsim_avg) / args.pdnsim_avg
        print(f"  vs PDNSim avg   {args.pdnsim_avg:.4e} V  ->  rel err {e:.2%}  "
              f"{'PASS' if e < 0.05 else 'CHECK'}")


if __name__ == "__main__":
    main()
