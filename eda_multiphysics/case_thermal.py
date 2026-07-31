"""Versioned placement case -> CoupFE thermal map.

Consumes ``instances.csv`` and ``manifest.json`` from the bundled project-authored
synthetic case or a caller-supplied EDA export. The default case also provides
``instance_power.csv``; callers may instead pass a total-power scenario, which is
distributed by cell area. The result is a steady die-temperature map with optional
per-instance back-annotation.

Thermal model:
  2D die-plane conduction, ``-div(k*t grad dT) = p_area``, edge-cooled
  (``dT=0`` at the die boundary), with ``k_si=148 W/(m K)`` and a specified die
  thickness. Absolute temperature rise depends on these compact-model assumptions;
  this example demonstrates the data and coupling path rather than chip signoff.

Run: ``python -m eda_multiphysics.case_thermal [case_dir] [total_power_W]
      [-o instance_temperature.csv]``
"""

from __future__ import annotations

import argparse
import csv
import json
import os

import numpy as np

from .fe import StructuredQuadMesh, solve_field

K_SI = 148.0        # silicon thermal conductivity [W/(m K)]
T_SI = 100e-6       # assumed die thickness [m]
DEFAULT_CASE = os.path.join(os.path.dirname(__file__), "cases", "synthetic_pdn")
ANALYSIS_ROLE = "integration_demonstration"
CLAIM_BOUNDARY = (
    "Steady edge-cooled compact die thermal model for integration and regression; "
    "not real-device thermal validation or signoff."
)


def load_case(case_dir):
    with open(f"{case_dir}/manifest.json") as f:
        man = json.load(f)
    rows = []
    with open(f"{case_dir}/instances.csv") as f:
        for r in csv.DictReader(f):
            rows.append(r)
    return man, rows


def load_instance_power(case_dir, rows):
    """Return a labeled per-instance power vector, or ``None`` when none is supplied."""

    power_path = os.path.join(case_dir, "instance_power.csv")
    if not os.path.exists(power_path):
        return None
    with open(power_path) as stream:
        power_rows = list(csv.DictReader(stream))
    by_id = {}
    for row in power_rows:
        instance_id = str(row.get("eda_id", "")).strip()
        if not instance_id or instance_id in by_id:
            raise ValueError(f"{power_path} requires unique, non-empty eda_id values")
        value = float(row["power_W"])
        if not np.isfinite(value) or value < 0.0:
            raise ValueError(f"{power_path}: power for {instance_id!r} must be finite and nonnegative")
        by_id[instance_id] = value
    instance_ids = [str(row["eda_id"]) for row in rows]
    if set(by_id) != set(instance_ids):
        missing = sorted(set(instance_ids) - set(by_id))
        extra = sorted(set(by_id) - set(instance_ids))
        raise ValueError(f"{power_path} does not match instances.csv: missing={missing}, extra={extra}")

    meta_path = os.path.join(case_dir, "instance_power.meta.json")
    metadata = {}
    if os.path.exists(meta_path):
        with open(meta_path) as stream:
            metadata = json.load(stream)
    power = np.array([by_id[instance_id] for instance_id in instance_ids])
    total = float(power.sum())
    declared_total = float(metadata.get("total_power_W", total))
    if not np.isclose(total, declared_total, rtol=1e-12, atol=1e-15):
        raise ValueError(
            f"{meta_path}: total_power_W={declared_total:.9g} does not match "
            f"instance_power.csv sum {total:.9g}"
        )
    return {
        "power_W": power,
        "total_power_W": total,
        "provenance": str(
            metadata.get("total_power_provenance", "caller_supplied_instance_power")
        ),
        "model": str(metadata.get("instance_power_model", "specified_per_instance")),
    }


def run(case_dir, total_power_W=None, *, output_path=None, power_provenance=None):
    man, rows = load_case(case_dir)
    design = man.get("design", os.path.basename(os.path.normpath(case_dir)))
    dx0, dy0, dx1, dy1 = man["die_um"]
    Lx = (dx1 - dx0) * 1e-6                       # m
    Ly = (dy1 - dy0) * 1e-6
    # instance centroids (m, die-local) and areas
    cx = np.array([(float(r["x_um"]) + float(r["w_um"]) / 2 - dx0) * 1e-6 for r in rows])
    cy = np.array([(float(r["y_um"]) + float(r["h_um"]) / 2 - dy0) * 1e-6 for r in rows])
    area = np.array([float(r["area_um2"]) for r in rows])

    supplied_power = load_instance_power(case_dir, rows) if total_power_W is None else None
    if supplied_power is not None:
        P = supplied_power["total_power_W"]
        p_inst = supplied_power["power_W"]
        provenance = power_provenance or supplied_power["provenance"]
        power_model = supplied_power["model"]
    elif total_power_W is not None:
        P = float(total_power_W)
        if not np.isfinite(P) or P < 0.0:
            raise ValueError("total_power_W must be finite and nonnegative")
        provenance = power_provenance or "user_scenario"
        power_model = "area_distributed_proxy"
        p_inst = P * area / area.sum()
    else:
        raise ValueError(
            f"{case_dir} has no instance_power.csv; pass total_power_W explicitly"
        )

    # mesh the die; bin instance power into elements -> areal source density (W/m^2)
    nx = ny = 72
    mesh = StructuredQuadMesh(nx, ny, Lx, Ly)
    ne = len(mesh.elems)
    ex = np.clip((cx / Lx * nx).astype(int), 0, nx - 1)
    ey = np.clip((cy / Ly * ny).astype(int), 0, ny - 1)
    eidx = ey * nx + ex
    elem_area = (Lx / nx) * (Ly / ny)
    p_elem = np.zeros(ne)
    np.add.at(p_elem, eidx, p_inst)
    s_elem = p_elem / elem_area                   # W/m^2 (per-area density)

    c_elem = np.full(ne, K_SI * T_SI)             # effective 2D conductance

    # edge-cooled: dT = 0 on all four die-boundary nodes
    X, Y = mesh.coords[:, 0], mesh.coords[:, 1]
    bnd = np.where(np.isclose(X, 0) | np.isclose(X, Lx) |
                   np.isclose(Y, 0) | np.isclose(Y, Ly))[0]
    bc = {int(n): 0.0 for n in bnd}

    dT, _, _ = solve_field(mesh, c_elem, s_elem, bc)

    # back-annotate dT to each instance (containing-element node average)
    node_T = dT
    inst_T = node_T[mesh.elems[eidx]].mean(axis=1)
    pk = int(np.argmax(node_T))
    px, py = mesh.coords[pk] * 1e6 + np.array([dx0, dy0])  # back to um, die coords
    # nearest instance to the hotspot
    d = np.hypot(cx * 1e6 + dx0 - px, cy * 1e6 + dy0 - py)
    near = rows[int(np.argmin(d))]

    print(f"\nCoupFE thermal map on {design} ({len(rows)} instances, "
          f"die {Lx*1e6:.1f}x{Ly*1e6:.1f} um, P={P*1e6:.2f} uW):")
    print(f"  peak dT          = {node_T.max():.3e} K")
    print(f"  hotspot location = ({px:.2f}, {py:.2f}) um")
    print(f"  nearest instance = {near['eda_id']} ({near['master']})")
    print(f"  mean instance dT = {inst_T.mean():.3e} K   max = {inst_T.max():.3e} K")

    # Back-annotation is opt-in so inspecting a case never mutates the input fixture. The sibling
    # metadata preserves power provenance, model assumptions, and the public claim boundary.
    if output_path is not None:
        out = os.path.abspath(os.fspath(output_path))
        with open(out, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["eda_id", "x_um", "y_um", "power_W", "dT_K"])
            for i, r in enumerate(rows):
                w.writerow([r["eda_id"], r["x_um"], r["y_um"], f"{p_inst[i]:.8e}",
                            f"{inst_T[i]:.6e}"])
        meta_path = os.path.splitext(out)[0] + ".meta.json"
        with open(meta_path, "w") as f:
            json.dump(dict(schema_version=1, total_power_W=P,
                           total_power_provenance=provenance,
                           instance_power_model=power_model,
                           release_validation=False,
                           analysis_role=ANALYSIS_ROLE,
                           claim_boundary=CLAIM_BOUNDARY,
                           source_case=os.path.abspath(os.fspath(case_dir)),
                           thermal_boundary_condition={
                               "type": "dirichlet",
                               "field": "temperature_rise",
                               "boundary": "all_die_edges",
                               "value_K": 0.0,
                           },
                           mesh_size={
                               "element_type": "Quad4",
                               "nx": nx,
                               "ny": ny,
                               "n_elements": ne,
                               "n_nodes": len(mesh.coords),
                           },
                           k_si_W_per_m_K=K_SI,
                           thickness_m=T_SI), f, indent=2)
            f.write("\n")
        print(f"  wrote {out}")
        print(f"  wrote {meta_path}")
    return node_T.max(), (px, py)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Solve a placement case thermal map.")
    parser.add_argument("case_dir", nargs="?", default=DEFAULT_CASE,
                        help="versioned case directory (default: bundled synthetic case)")
    parser.add_argument("total_power_W", nargs="?", type=float,
                        help="optional scenario total power in W; otherwise use instance_power.csv")
    parser.add_argument("-o", "--output", help="optional back-annotation CSV output path")
    parser.add_argument("--power-provenance",
                        help="explicit total-power provenance stored beside --output")
    args = parser.parse_args(argv)
    run(args.case_dir, args.total_power_W, output_path=args.output,
        power_provenance=args.power_provenance)


if __name__ == "__main__":
    main()
