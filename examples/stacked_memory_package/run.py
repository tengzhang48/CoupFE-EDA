"""Synthetic stacked-memory package: steady heat conduction -> one-way thermoelastic warpage.

Builds the 90-body package CAD and a conformal Tet4 mesh (Gmsh), solves steady
Fourier conduction for two top-TIM conductivities with CoupFE-EDA's generated
native Tet4 kernel, then a one-way small-strain thermoelastic solve on the
same nodes with a CoupFE-generated kernel, and prints the comparison.

    python examples/stacked_memory_package/run.py                  # 0.65 mm mesh, ~2 min
    python examples/stacked_memory_package/run.py --check          # compare with the retained result
    python examples/stacked_memory_package/run.py --mesh-size 0.45 --check   # headline mesh, ~9 min

Meshing needs ``gmsh``; when the solver Python lacks it, pass ``--cad-python``
(or set ``CAD_PYTHON``) to a Python that has it. Outputs go to
``examples/stacked_memory_package/runs/h<size>/`` unless ``--output`` is given.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
if __package__ in {None, ""}:
    sys.path.insert(0, str(HERE.parents[1]))
    sys.path.insert(0, str(HERE))

ORACLES = {0.65: "expected_results.json", 0.45: "expected_results_h045.json"}
CASES = ("baseline", "improved")


def _cad_python(explicit):
    if explicit:
        return explicit
    if os.environ.get("CAD_PYTHON"):
        return os.environ["CAD_PYTHON"]
    if importlib.util.find_spec("gmsh") is not None:
        return sys.executable
    raise SystemExit("gmsh is not importable here; pass --cad-python /path/to/python-with-gmsh "
                     "or set CAD_PYTHON")


def build(out, h, cad_python):
    cmd = [cad_python, str(HERE / "build_package.py"), "--output", str(out), "--h", str(h)]
    print("building CAD and mesh:", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)


def summarize(out):
    geometry = json.loads((out / "geometry.json").read_text())
    thermal = json.loads((out / "result.json").read_text())
    mechanics = json.loads((out / "mechanics_result.json").read_text())
    t, m = thermal["results"], mechanics["results"]
    return {
        "mesh": {"mesh_size_mm": geometry["mesh_size_mm"], "nodes": geometry["nodes"],
                 "elements": geometry["elements"], "cad_bodies": geometry["cad_bodies"],
                 "materials": len(geometry["materials"]), "gmsh_version": geometry["gmsh_version"],
                 "min_gamma": geometry["quality"]["min_gamma"],
                 "body_adjacencies": len(geometry["adjacency"])},
        "power_W": t["baseline"]["power_W"],
        "thermal": {c: {"top_tim_k_W_mK": t[c]["top_tim_k_W_mK"], "peak_die_C": t[c]["peak_die_C"],
                        "balance_error_relative": t[c]["balance_error_relative"],
                        "free_residual_relative": t[c]["free_residual_relative"]} for c in CASES},
        "mechanics": {c: {"substrate_warpage_um": m[c]["substrate_warpage_um"],
                          "active_die_p95_vm_MPa": m[c]["active_die_p95_vm_MPa"],
                          "active_die_max_principal_MPa": m[c]["active_die_max_principal_MPa"],
                          "free_residual_relative": m[c]["free_residual_relative"]} for c in CASES},
        "comparison": {"peak_die_reduction_C": thermal["peak_reduction_C"],
                       "warpage_ratio_improved_to_baseline":
                           m["improved"]["substrate_warpage_um"] / m["baseline"]["substrate_warpage_um"]},
        "verification": {"cube_flux_absolute_error_W": thermal["verification"]["absolute_error_W"],
                         "zero_power_max_rise_K": thermal["verification"]["zero_power_max_rise_K"],
                         "free_expansion_relative_error": mechanics["verification"]["free_expansion_relative_error"],
                         "constrained_stress_error_Pa": mechanics["verification"]["constrained_stress_error_Pa"]},
        "revisions": {"coupfe": thermal["core_revision"], "coupfe_eda": thermal["eda_revision"]},
    }


def _lookup(record, path):
    for key in path.split("."):
        record = record[key]
    return record


def check(summary, oracle_path):
    oracle = json.loads(oracle_path.read_text())
    failures = []
    for metric in oracle["metrics"]:
        actual, expected = _lookup(summary, metric["path"]), metric["value"]
        if isinstance(expected, str):
            if actual != expected:
                failures.append(f"{metric['path']}: expected {expected!r}, observed {actual!r}")
            continue
        if not math.isclose(float(actual), float(expected), rel_tol=metric.get("relative_tolerance", 0.0),
                            abs_tol=metric.get("absolute_tolerance", 0.0)):
            failures.append(f"{metric['path']}: expected {expected!r}, observed {actual!r}")
    for bound in oracle.get("bounds", []):
        actual = _lookup(summary, bound["path"])
        if not abs(float(actual)) < bound["maximum_exclusive"]:
            failures.append(f"{bound['path']}: expected |value| < {bound['maximum_exclusive']!r}, observed {actual!r}")
    return failures


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mesh-size", type=float, default=0.65, help="maximum element size, mm (0.65 or 0.45 have retained results)")
    ap.add_argument("--output", type=Path, default=None)
    ap.add_argument("--cad-python", default=None)
    ap.add_argument("--reuse", action="store_true", help="reuse an existing mesh in --output and re-solve")
    ap.add_argument("--check", action="store_true", help="compare with the retained result for this mesh size")
    a = ap.parse_args(argv)
    out = a.output or HERE / "runs" / f"h{a.mesh_size:g}"
    if (out / "mesh.npz").exists():
        if not a.reuse:
            raise SystemExit(f"{out} already holds a mesh; pass --reuse to re-solve it or choose another --output")
    else:
        out.parent.mkdir(parents=True, exist_ok=True)
        build(out, a.mesh_size, _cad_python(a.cad_python))
    import solve_thermal
    import solve_mechanics
    solve_thermal.solve(out)
    solve_mechanics.solve(out)
    summary = summarize(out)
    (out / "summary.json").write_text(json.dumps(summary, indent=2))
    mesh = summary["mesh"]
    print(f"\nStacked-memory package, h = {mesh['mesh_size_mm']} mm: {mesh['nodes']:,} nodes, "
          f"{mesh['elements']:,} Tet4, {mesh['cad_bodies']} bodies, {summary['power_W']:.0f} W")
    print(f"{'top TIM k [W/(m K)]':<22}{'peak die [C]':>14}{'warpage [um]':>14}{'die P95 vM [MPa]':>18}")
    for c in CASES:
        print(f"{summary['thermal'][c]['top_tim_k_W_mK']:<22g}{summary['thermal'][c]['peak_die_C']:>14.3f}"
              f"{summary['mechanics'][c]['substrate_warpage_um']:>14.3f}{summary['mechanics'][c]['active_die_p95_vm_MPa']:>18.3f}")
    print(f"peak die reduction {summary['comparison']['peak_die_reduction_C']:.2f} C; warpage ratio "
          f"{summary['comparison']['warpage_ratio_improved_to_baseline']:.3f}; results in {out}")
    if a.check:
        name = ORACLES.get(round(a.mesh_size, 2))
        if name is None:
            raise SystemExit(f"no retained result for --mesh-size {a.mesh_size}; use 0.65 or 0.45")
        failures = check(summary, HERE / name)
        if failures:
            print("CHECK FAILED against", name)
            for f in failures:
                print("  ", f)
            return 1
        print("check passed against", name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
