"""Closed-loop electrothermal on a supplied design case: 1D PDN-graph <-> 2D die thermal.

The mixed-dimensional coupling the plan calls for (4.1): the PDN is a 1D resistor
graph (from PDNSim's `write_pg_spice`); the die is a 2D compact thermal model
(lateral spreading -div(k t grad T) + vertical sink g_v T = power-density). They
couple both ways:

  thermal -> electrical : metal resistance rises with temperature,
                          g_e(T) = g_e0 / (1 + alpha * dT_edge)
  electrical -> thermal : PDN Joule loss adds to the die heat source
                          (instance power dominates; Joule included for closure)

Staggered Picard loop with under-relaxation. The headline: coupled R(T) shifts the
IR-drop result versus an isothermal analysis. This is a compact research model,
not commercial signoff. Thermal calibration (k_si, t_si, g_v) and the metal
temperature coefficient alpha are documented assumptions (survey 6).

Run:  python -m eda_multiphysics.electrothermal_chip <case_dir> <pdn.sp> <P_total_W>
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from collections.abc import Mapping

import numpy as np

from .fe import StructuredQuadMesh, solve_field
from .pdn_graph import GraphConduction, parse_pg_spice
from coupfe import newton_solve


def _node_xy(name, dbu=2000.0):                 # VDD_x_y_layer -> (um, um)
    p = name.split("_")
    return float(p[1]) / dbu, float(p[2]) / dbu


def run(case_dir, spice, P_total, *, instance_power_W=None,
        power_mode="fixed_instance", alpha=0.004, k_si=148.0, t_si=100e-6,
        h_v=1.0e4, nx=80, relax=0.6, tol=1e-5, maxit=80, dbu=None,
        verbose=False):
    with open(f"{case_dir}/manifest.json") as f:
        man = json.load(f)
    with open(f"{case_dir}/instances.csv") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise ValueError(f"{case_dir}/instances.csv must contain at least one instance")
    P_total = float(P_total)
    if not np.isfinite(P_total) or P_total < 0.0:
        raise ValueError("P_total must be finite and nonnegative")
    if power_mode not in {"fixed_instance", "pdn_iv"}:
        raise ValueError("power_mode must be 'fixed_instance' or 'pdn_iv'")
    dbu = float(man["dbu_per_micron"] if dbu is None else dbu)
    if not np.isfinite(dbu) or dbu <= 0.0:
        raise ValueError(f"dbu must be positive and finite, got {dbu!r}")
    dx0, dy0, dx1, dy1 = man["die_um"]
    Lx, Ly = (dx1 - dx0) * 1e-6, (dy1 - dy0) * 1e-6

    # --- die thermal mesh + instance power source ---
    ny = nx
    mesh = StructuredQuadMesh(nx, ny, Lx, Ly)
    ne = len(mesh.elems)
    elem_area = (Lx / nx) * (Ly / ny)

    def elem_of(px, py):
        i = min(max(int(px / Lx * nx), 0), nx - 1)
        j = min(max(int(py / Ly * ny), 0), ny - 1)
        return j * nx + i

    area = np.array([float(r["area_um2"]) for r in rows])
    if not np.all(np.isfinite(area)) or np.any(area <= 0.0):
        raise ValueError("instance areas must be positive and finite")
    cx = np.array([(float(r["x_um"]) + float(r["w_um"]) / 2 - dx0) * 1e-6 for r in rows])
    cy = np.array([(float(r["y_um"]) + float(r["h_um"]) / 2 - dy0) * 1e-6 for r in rows])
    width = np.array([float(r["w_um"]) * 1e-6 for r in rows])
    height = np.array([float(r["h_um"]) * 1e-6 for r in rows])
    instance_ids = [str(r["eda_id"]) for r in rows]
    if len(set(instance_ids)) != len(instance_ids):
        raise ValueError("instances.csv requires unique eda_id values")
    if instance_power_W is None:
        p_inst_reference = P_total * area / area.sum()
    elif isinstance(instance_power_W, Mapping):
        supplied_ids = {str(key) for key in instance_power_W}
        if supplied_ids != set(instance_ids):
            missing = sorted(set(instance_ids) - supplied_ids)
            extra = sorted(supplied_ids - set(instance_ids))
            raise ValueError(
                f"instance_power_W does not match instances.csv: missing={missing}, extra={extra}"
            )
        p_inst_reference = np.array(
            [float(instance_power_W[instance_id]) for instance_id in instance_ids]
        )
    else:
        p_inst_reference = np.asarray(instance_power_W, dtype=float)
        if p_inst_reference.shape != (len(rows),):
            raise ValueError(
                f"instance_power_W must have shape ({len(rows)},), "
                f"got {p_inst_reference.shape}"
            )
    if (
        not np.all(np.isfinite(p_inst_reference))
        or np.any(p_inst_reference < 0.0)
    ):
        raise ValueError("instance_power_W values must be finite and nonnegative")
    if not np.isclose(
        float(p_inst_reference.sum()), P_total, rtol=1e-12, atol=1e-15
    ):
        raise ValueError(
            "P_total does not match the sum of the supplied per-instance power map"
        )
    inst_e = np.array([elem_of(x, y) for x, y in zip(cx, cy)])

    def instance_source(power):
        source = np.zeros(ne)
        np.add.at(source, inst_e, power)
        return source / elem_area                         # W/m^2

    s_inst_reference = instance_source(p_inst_reference)

    c_elem = np.full(ne, k_si * t_si)                     # lateral conductance
    rxn_elem = np.full(ne, h_v)                           # vertical sink to ambient

    # --- PDN graph + edge->die-element map ---
    idx, edges0, load, vsrc = parse_pg_spice(spice)
    n = len(idx)
    inv = {v: k for k, v in idx.items()}
    f = np.zeros(n)
    for nd, i in load.items():
        f[nd] = i
    dirich = dict(vsrc)
    if "0" in idx:
        dirich[idx["0"]] = 0.0
    Vsup = max(vsrc.values())
    edge_e = []
    for a, b, g in edges0:
        coordinate_nodes = [nd for nd in (a, b) if inv[nd] != "0"]
        if not coordinate_nodes:
            edge_e.append(-1)
            continue
        coordinates = [_node_xy(inv[nd], dbu) for nd in coordinate_nodes]
        mx = (sum(point[0] for point in coordinates) / len(coordinates) - dx0) * 1e-6
        my = (sum(point[1] for point in coordinates) / len(coordinates) - dy0) * 1e-6
        edge_e.append(elem_of(mx, my))
    edge_e = np.array(edge_e)
    grid = np.array([i for k, i in idx.items() if k != "0"])

    load_to_instance = {}
    if power_mode == "pdn_iv":
        for node_index in load:
            node_name = inv[node_index]
            if node_name == "0":
                raise ValueError("pdn_iv mode does not support a load attached to ground")
            load_x_um, load_y_um = _node_xy(node_name, dbu)
            load_x = (load_x_um - dx0) * 1e-6
            load_y = (load_y_um - dy0) * 1e-6
            distance = np.hypot(cx - load_x, cy - load_y)
            instance_index = int(np.argmin(distance))
            tolerance = 0.5 * np.hypot(
                width[instance_index], height[instance_index]
            ) + 1e-15
            if distance[instance_index] > tolerance:
                raise ValueError(
                    f"PDN load node {node_name!r} does not fall within a case instance"
                )
            load_to_instance[node_index] = instance_index

    def solve_pdn(scale):
        edges = [(a, b, g * s) for (a, b, g), s in zip(edges0, scale)]
        op = GraphConduction(n, edges, f)
        V, _, _ = newton_solve([op], np.full(n, Vsup), None, n, dirich)
        return V, edges

    def pdn_load_power(V):
        power = np.zeros(len(rows))
        for node_index, current in load.items():
            instance_index = load_to_instance[node_index]
            power[instance_index] += float(current) * float(V[node_index].real)
        return power

    def supply_power(V, edges):
        total = 0.0
        for source_node, source_voltage in vsrc.items():
            source_current = float(load.get(source_node, 0.0))
            for a, b, conductance in edges:
                if a == source_node:
                    source_current += conductance * float((V[a] - V[b]).real)
                elif b == source_node:
                    source_current += conductance * float((V[b] - V[a]).real)
            total += float(source_voltage) * source_current
        return total

    # --- isothermal baseline ---
    V_iso, edges_iso = solve_pdn(np.ones(len(edges0)))
    ir_iso = float(Vsup - V_iso[grid].min())
    if power_mode == "pdn_iv":
        p_inst_iso = pdn_load_power(V_iso)
        if not np.allclose(
            p_inst_iso, p_inst_reference, rtol=1e-10, atol=1e-15
        ):
            raise ValueError(
                "supplied instance_power_W does not match the isothermal PDN V*I map"
            )
    else:
        p_inst_iso = p_inst_reference.copy()

    # --- coupled staggered loop ---
    dT = np.zeros(mesh.nnode)
    ir_c = ir_iso
    p_inst_coupled = p_inst_iso.copy()
    pdn_joule_power = 0.0
    source_power = supply_power(V_iso, edges_iso)
    converged = False
    last_ir_change = float("inf")
    last_temperature_change = float("inf")
    for it in range(1, maxit + 1):
        T_edge = np.where(edge_e >= 0, dT[mesh.elems[np.clip(edge_e, 0, ne - 1)]].mean(axis=1), 0.0)
        scale = 1.0 / (1.0 + alpha * T_edge)              # g_e(T)
        V, edges = solve_pdn(scale)
        if power_mode == "pdn_iv":
            p_inst_coupled = pdn_load_power(V)
            s_inst = instance_source(p_inst_coupled)
        else:
            p_inst_coupled = p_inst_reference
            s_inst = s_inst_reference
        # PDN Joule per edge -> die source
        s_pdn = np.zeros(ne)
        pdn_joule_power = 0.0
        for (a, b, g), ee in zip(edges, edge_e):
            edge_power = g * float((V[a].real - V[b].real) ** 2)
            pdn_joule_power += edge_power
            if ee >= 0:
                s_pdn[ee] += edge_power
        s_pdn /= elem_area
        dT_new, _, _ = solve_field(mesh, c_elem, s_inst + s_pdn, {}, reaction_elem=rxn_elem)
        dT_relaxed = (1 - relax) * dT + relax * dT_new
        last_temperature_change = float(
            np.max(np.abs(dT_relaxed - dT)) / max(1.0, np.max(np.abs(dT_relaxed)))
        )
        ir_new = float(Vsup - V[grid].min())
        d = abs(ir_new - ir_c) / max(ir_c, 1e-300)
        last_ir_change = d
        if not (
            np.isfinite(d)
            and np.isfinite(last_temperature_change)
            and np.all(np.isfinite(V))
            and np.all(np.isfinite(dT_relaxed))
        ):
            raise RuntimeError("chip electrothermal iteration produced non-finite values")
        dT = dT_relaxed
        ir_c = ir_new
        if verbose:
            print(f"  it{it:3d} peakdT={dT.max():.3f}K  IR={ir_c:.4e}V  dIR={d:.2e}")
        if max(d, last_temperature_change) < tol and it > 1:
            converged = True
            break

    if not converged:
        raise RuntimeError(
            "chip electrothermal iteration did not converge: "
            f"iterations={maxit}, relative_ir_change={last_ir_change:.6e}, "
            f"relative_temperature_change={last_temperature_change:.6e}, "
            f"tolerance={tol:.6e}"
        )

    source_power = supply_power(V, edges)
    thermal_power = float(p_inst_coupled.sum() + pdn_joule_power)
    power_balance_error = (
        thermal_power - source_power if power_mode == "pdn_iv" else None
    )
    if power_balance_error is not None and not np.isclose(
        thermal_power, source_power, rtol=1e-10, atol=1e-12
    ):
        raise RuntimeError(
            "PDN V*I load heat plus resistor loss does not balance source power"
        )

    out = dict(ir_iso=ir_iso, ir_coupled=ir_c, peakdT=float(dT.max()),
               pct_ir=100.0 * (ir_c - ir_iso) / ir_iso, iters=it,
               n_inst=len(rows), die_um=(round(Lx * 1e6, 1), round(Ly * 1e6, 1)),
               P_total=P_total,
               power_mode=power_mode,
               instance_power_reference_W=p_inst_reference.copy(),
               instance_power_isothermal_W=p_inst_iso.copy(),
               instance_power_coupled_W=p_inst_coupled.copy(),
               load_power_coupled_W=float(p_inst_coupled.sum()),
               pdn_joule_power_coupled_W=float(pdn_joule_power),
               thermal_power_coupled_W=thermal_power,
               source_power_coupled_W=float(source_power),
               power_balance_error_W=power_balance_error,
               # expose the temperature field for downstream coupling (T -> u)
               mesh=mesh, dT=dT, Lx=Lx, Ly=Ly, dx0=dx0, dy0=dy0)
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run coupled electrothermal analysis on a case.")
    parser.add_argument("case_dir", help="OpenROAD case directory")
    parser.add_argument("spice", help="PDNSim write_pg_spice netlist")
    parser.add_argument("total_power_W", type=float, help="total chip power in W")
    args = parser.parse_args(argv)
    r = run(args.case_dir, args.spice, args.total_power_W, verbose=True)
    design = os.path.basename(os.path.normpath(args.case_dir))
    print(f"\nCoupled electrothermal on {design} "
          f"({r['n_inst']} insts, die {r['die_um'][0]}x{r['die_um'][1]} um, "
          f"P={args.total_power_W*1e3:.2f} mW):")
    print(f"  peak dT              = {r['peakdT']:.2f} K")
    print(f"  isothermal worst IR  = {r['ir_iso']:.4e} V")
    print(f"  coupled    worst IR  = {r['ir_coupled']:.4e} V")
    print(f"  --> R(T) shifts worst IR drop by {r['pct_ir']:+.2f}%  "
          f"(converged in {r['iters']} staggered iters)")


if __name__ == "__main__":
    main()
