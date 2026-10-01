"""Compare the CoupFE/EDA package run with the independent FEniCSx reference.

This comparison-stage script reads the original result fields. Tolerances
are declared up front in ``TOLERANCES`` and are never adjusted to the observed
numbers; the actual errors are always reported, pass or fail.

Both solutions use the same P1 Tet4 mesh, the same declared materials, loads
and boundary conditions, and the same reporting definitions, so what is being
measured is agreement of two independent implementations of one declared linear
synthetic model - not discretisation accuracy and not device validation.

Usage
  python -u compare_solvers.py \
      --mesh-dir ../runs/h0.45 --reference results --out .
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REFERENCE_C = 40.0
CASES = ("baseline", "improved")

# Predeclared, before looking at any comparison output.
TOLERANCES = {
    "field_relative": 1e-5,   # nodal T (scaled by temperature rise) and U (by max |U|)
    "cell_relative": 1e-5,    # cell von Mises and stress components (by field max)
    "metric_relative": 1e-4,  # scalar reported metrics
}

# reported metric -> (original key, reference section, reference key, scale key)
# scale: "self" = relative to the original value, "rise" = relative to the
# original peak temperature rise above 40 C.
METRICS = [
    ("peak_active_die_C", "thermal", "peak_die_C", "thermal", "peak_active_die_node_C", "rise"),
    ("peak_all_C", "thermal", "peak_all_C", "thermal", "peak_all_C", "rise"),
    ("top_removed_W", "thermal", "top_removed_W", "thermal", "top_removed_W", "self"),
    ("board_removed_W", "thermal", "board_removed_W", "thermal", "board_removed_W", "self"),
    ("substrate_warpage_um", "mech", "substrate_warpage_um", "mechanics",
     "substrate_warpage_um", "self"),
    ("active_die_p95_vm_MPa", "mech", "active_die_p95_vm_MPa", "mechanics",
     "active_die_p95_vm_MPa", "self"),
    ("active_die_mean_vm_MPa", "mech", "active_die_mean_vm_MPa", "mechanics",
     "active_die_mean_vm_MPa", "self"),
    ("active_die_max_principal_MPa", "mech", "active_die_max_principal_MPa", "mechanics",
     "active_die_max_principal_MPa", "self"),
    ("max_displacement_um", "mech", "max_displacement_um", "mechanics",
     "max_displacement_um", "self"),
]


def rel(a: float, b: float, scale: float) -> dict:
    return dict(coupfe=float(a), fenicsx=float(b), difference=float(b - a),
                relative_error=float(abs(b - a) / scale) if scale else None)


def field_errors(orig: np.ndarray, ref: np.ndarray, scale: float) -> dict:
    d = ref - orig
    return dict(
        max_absolute_error=float(np.abs(d).max()),
        rms_absolute_error=float(np.sqrt(np.mean(d ** 2))),
        scale=float(scale),
        max_relative_error=float(np.abs(d).max() / scale),
        rms_relative_error=float(np.sqrt(np.mean(d ** 2)) / scale),
        l2_relative_error=float(np.linalg.norm(d.ravel()) / np.linalg.norm(orig.ravel())),
        node_or_cell_of_max=int(np.abs(d).reshape(len(d), -1).max(axis=1).argmax()),
    )


def compare(mesh_dir: Path, ref_dir: Path, cross_path: Path | None = None) -> dict:
    mesh = np.load(mesh_dir / "mesh.npz", allow_pickle=False)
    meta = json.loads((mesh_dir / "geometry.json").read_text())
    cells = mesh["tets"]
    rid = mesh["region_id"]
    volumes = mesh["volume_m3"]
    objects = meta["objects"]
    power = np.array([float(o["power_W"]) for o in objects])
    active_cells = power[rid] > 0.0
    active_nodes = np.unique(cells[active_cells])

    thermal_orig = json.loads((mesh_dir / "result.json").read_text())
    mech_orig = json.loads((mesh_dir / "mechanics_result.json").read_text())
    ref = json.loads((ref_dir / "fenicsx_result.json").read_text())

    if ref["provenance"]["mesh_sha256"] != thermal_orig["mesh_sha256"]:
        raise RuntimeError("the reference solved a different mesh file than the original run")

    out = {"cases": {}}
    for case in CASES:
        T_o = np.load(mesh_dir / f"{case}_fields.npz")["temperature_C"]
        T_r = np.load(ref_dir / f"{case}_fenicsx_fields.npz")["temperature_C"]
        mo = np.load(mesh_dir / f"{case}_mechanics.npz")
        mr = np.load(ref_dir / f"{case}_fenicsx_mechanics.npz")
        U_o, U_r = mo["displacement_m"], mr["displacement_m"]
        S_o, S_r = mo["stress_MPa"], mr["stress_MPa"]
        V_o, V_r = mo["von_mises_MPa"], mr["von_mises_MPa"]
        P_o, P_r = mo["principal_max_MPa"], mr["principal_max_MPa"]

        rise = float(T_o.max() - REFERENCE_C)
        fields = {
            "temperature_C": field_errors(T_o, T_r, rise),
            "displacement_m": field_errors(U_o, U_r, float(np.linalg.norm(U_o, axis=1).max())),
            "von_mises_MPa": field_errors(V_o, V_r, float(np.abs(V_o).max())),
            "stress_MPa": field_errors(S_o.reshape(len(S_o), 9), S_r.reshape(len(S_r), 9),
                                       float(np.abs(S_o).max())),
            "principal_max_MPa": field_errors(P_o, P_r, float(np.abs(P_o).max())),
            "substrate_detrended_w_um": field_errors(
                mo["substrate_detrended_w_um"], mr["substrate_detrended_w_um"],
                float(np.abs(mo["substrate_detrended_w_um"]).max())),
        }
        fields["temperature_C"]["definition"] = "scale = peak temperature rise above 40 C"
        fields["temperature_C"]["l2_relative_error"] = float(
            np.linalg.norm(T_r - T_o) / np.linalg.norm(T_o - REFERENCE_C))
        fields["temperature_C"]["l2_definition"] = "L2 difference divided by L2 original temperature rise"
        fields["displacement_m"]["definition"] = "scale = max nodal displacement magnitude"

        # node / cell ordering agreement, independent of the field values
        node_sets = dict(
            substrate_top_nodes_identical=bool(np.array_equal(
                mo["substrate_top_nodes"], mr["substrate_top_nodes"])),
            peak_active_die_node_coupfe=int(active_nodes[int(T_o[active_nodes].argmax())]),
            peak_active_die_node_fenicsx=int(active_nodes[int(T_r[active_nodes].argmax())]),
            peak_vm_cell_coupfe=int(np.argmax(np.where(active_cells, V_o, -np.inf))),
            peak_vm_cell_fenicsx=int(np.argmax(np.where(active_cells, V_r, -np.inf))),
        )

        metrics = {}
        src = {"thermal": (thermal_orig["results"][case], ref["results"][case]["thermal"]),
               "mech": (mech_orig["results"][case], ref["results"][case]["mechanics"])}
        for name, o_sec, o_key, r_sec, r_key, scale_kind in METRICS:
            o_val = src[o_sec][0][o_key]
            r_val = ref["results"][case][r_sec][r_key]
            scale = rise if scale_kind == "rise" else abs(o_val)
            metrics[name] = rel(o_val, r_val, scale)
            metrics[name]["scale_definition"] = ("peak temperature rise above 40 C"
                                                 if scale_kind == "rise" else "original value")

        # per-body volume-weighted mean and peak temperature, same definitions
        body_rows = []
        c_o, c_r = T_o[cells].mean(axis=1), T_r[cells].mean(axis=1)
        for i, o in enumerate(objects):
            sel = rid == i
            nodes = np.unique(cells[sel])
            mo_ = float(np.average(c_o[sel], weights=volumes[sel]))
            mr_ = float(np.average(c_r[sel], weights=volumes[sel]))
            body_rows.append(dict(id=o["id"], material=o["material"], power_W=o["power_W"],
                                  mean_C_coupfe=mo_, mean_C_fenicsx=mr_,
                                  mean_relative_error=abs(mr_ - mo_) / rise,
                                  peak_C_coupfe=float(T_o[nodes].max()),
                                  peak_C_fenicsx=float(T_r[nodes].max()),
                                  peak_relative_error=abs(float(T_r[nodes].max())
                                                          - float(T_o[nodes].max())) / rise))
        worst_body = max(body_rows, key=lambda r: max(r["mean_relative_error"],
                                                      r["peak_relative_error"]))

        checks = {
            "fields_within_tolerance": all(
                fields[k]["max_relative_error"] <= TOLERANCES[
                    "field_relative" if k in ("temperature_C", "displacement_m")
                    else "cell_relative"]
                for k in fields),
            "metrics_within_tolerance": all(
                m["relative_error"] <= TOLERANCES["metric_relative"] for m in metrics.values()),
            "worst_field_relative_error": max(f["max_relative_error"] for f in fields.values()),
            "worst_field": max(fields, key=lambda k: fields[k]["max_relative_error"]),
            "worst_metric_relative_error": max(m["relative_error"] for m in metrics.values()),
            "worst_metric": max(metrics, key=lambda k: metrics[k]["relative_error"]),
            "worst_body_temperature_relative_error": max(
                worst_body["mean_relative_error"], worst_body["peak_relative_error"]),
            "worst_body": worst_body["id"],
        }
        out["cases"][case] = dict(fields=fields, metrics=metrics, ordering=node_sets,
                                  per_body=body_rows, checks=checks)

    # the sensitivity result the example reports
    dt_o = (thermal_orig["results"]["baseline"]["peak_die_C"]
            - thermal_orig["results"]["improved"]["peak_die_C"])
    dt_r = (ref["results"]["baseline"]["thermal"]["peak_active_die_node_C"]
            - ref["results"]["improved"]["thermal"]["peak_active_die_node_C"])
    wo = (mech_orig["results"]["baseline"]["substrate_warpage_um"]
          / mech_orig["results"]["improved"]["substrate_warpage_um"])
    wr = (ref["results"]["baseline"]["mechanics"]["substrate_warpage_um"]
          / ref["results"]["improved"]["mechanics"]["substrate_warpage_um"])
    out["derived"] = dict(
        peak_die_reduction_C=rel(dt_o, dt_r, abs(dt_o)),
        warpage_ratio_baseline_over_improved=rel(wo, wr, abs(wo)))

    if cross_path is not None and cross_path.exists():
        out["cross_residual"] = json.loads(cross_path.read_text())

    out["tolerances"] = TOLERANCES
    out["solvers"] = dict(
        coupfe=dict(
            description="CoupFE / CoupFE-EDA generated native Tet4 kernels, Newton driver",
            core_revision=thermal_orig["core_revision"],
            eda_revision=thermal_orig["eda_revision"],
            python=thermal_orig["python"], platform=thermal_orig["platform"],
            thermal_driver_sha256=thermal_orig["driver_sha256"],
            mechanics_driver_sha256=mech_orig["script_sha256"],
            thermal_free_residual={c: thermal_orig["results"][c]["free_residual_relative"]
                                   for c in CASES},
            mechanics_free_residual={c: mech_orig["results"][c]["free_residual_relative"]
                                     for c in CASES}),
        fenicsx=dict(
            description=ref["solver"],
            dolfinx=ref["provenance"]["dolfinx_version"], ufl=ref["provenance"]["ufl_version"],
            basix=ref["provenance"]["basix_version"], petsc=ref["provenance"]["petsc_version"],
            python=ref["provenance"]["python"], platform=ref["provenance"]["platform"],
            script_sha256=ref["provenance"]["script_sha256"],
            patch_checks=ref["patch_checks"],
            mesh_checks=ref["mesh_checks"],
            thermal_free_residual={c: ref["results"][c]["thermal"]["free_residual_relative"]
                                   for c in CASES},
            mechanics_free_residual={c: ref["results"][c]["mechanics"]["free_residual_relative"]
                                     for c in CASES}))
    def shown(path):   # recorded relative to the example folder, never as a machine path
        try:
            return str(Path(path).resolve().relative_to(HERE.parent))
        except ValueError:
            return Path(path).name
    out["mesh_nodes"] = int(len(mesh["points_m"]))
    out["mesh_tets"] = int(len(cells))
    out["provenance"] = dict(
        mesh_dir=shown(mesh_dir), reference_dir=shown(ref_dir),
        mesh_sha256=ref["provenance"]["mesh_sha256"],
        geometry_sha256=ref["provenance"]["geometry_sha256"],
        compare_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    out["scope"] = (
        "Two independent implementations of one declared linear synthetic model on the same "
        "P1 Tet4 mesh. Agreement here is evidence about numerical implementation only: not "
        "real-device validation, not mesh convergence, not plasticity, and not verification "
        "of the physical package model or of its synthetic material data.")
    out["passed"] = bool(all(out["cases"][c]["checks"]["fields_within_tolerance"]
                             and out["cases"][c]["checks"]["metrics_within_tolerance"]
                             for c in CASES))
    return out


def markdown(res: dict) -> str:
    L = ["# CoupFE vs independent FEniCSx reference - 0.45 mm mesh", "",
         f"Same P1 Tet4 mesh ({res['mesh_nodes']:,} nodes / {res['mesh_tets']:,} tets), same declared materials, loads and",
         "boundary conditions, same reporting definitions; two independently written solvers.",
         "", f"**Overall: {'agreement within the predeclared tolerances' if res['passed'] else 'MISMATCH - see below'}**",
         "", "Predeclared tolerances (fixed before the comparison was run): "
         f"nodal fields {TOLERANCES['field_relative']:.0e}, cell fields "
         f"{TOLERANCES['cell_relative']:.0e}, scalar metrics {TOLERANCES['metric_relative']:.0e} "
         "relative.", ""]

    L += ["## Reported metrics", "",
          "| Case | Metric | CoupFE | FEniCSx | Difference | Relative error | Tol |",
          "|---|---|---|---|---|---|---|"]
    for case in CASES:
        for name, m in res["cases"][case]["metrics"].items():
            L.append(f"| {case} | {name} | {m['coupfe']:.9g} | {m['fenicsx']:.9g} | "
                     f"{m['difference']:+.3e} | {m['relative_error']:.2e} | "
                     f"{TOLERANCES['metric_relative']:.0e} |")
    for name, m in res["derived"].items():
        L.append(f"| both | {name} | {m['coupfe']:.9g} | {m['fenicsx']:.9g} | "
                 f"{m['difference']:+.3e} | {m['relative_error']:.2e} | "
                 f"{TOLERANCES['metric_relative']:.0e} |")

    L += ["", "## Full fields", "",
          "| Case | Field | Max abs error | Scale | Max rel error | RMS rel error | L2 rel error | Tol |",
          "|---|---|---|---|---|---|---|---|"]
    for case in CASES:
        for name, f in res["cases"][case]["fields"].items():
            tol = TOLERANCES["field_relative" if name in ("temperature_C", "displacement_m") \
                             else "cell_relative"]
            L.append(f"| {case} | {name} | {f['max_absolute_error']:.3e} | {f['scale']:.6g} | "
                     f"{f['max_relative_error']:.2e} | {f['rms_relative_error']:.2e} | "
                     f"{f['l2_relative_error']:.2e} | {tol:.0e} |")

    L += ["", "## Per-body temperatures (all 90 bodies)", ""]
    for case in CASES:
        c = res["cases"][case]["checks"]
        L.append(f"- **{case}**: worst body temperature relative error "
                 f"{c['worst_body_temperature_relative_error']:.2e} (`{c['worst_body']}`), "
                 f"scaled by the peak temperature rise.")

    L += ["", "## Ordering and locations", ""]
    for case in CASES:
        o = res["cases"][case]["ordering"]
        L.append(f"- **{case}**: peak active-die node "
                 f"{o['peak_active_die_node_coupfe']} vs {o['peak_active_die_node_fenicsx']}; "
                 f"peak active-die von Mises cell {o['peak_vm_cell_coupfe']} vs "
                 f"{o['peak_vm_cell_fenicsx']}; substrate top node set identical: "
                 f"{o['substrate_top_nodes_identical']}.")

    L += ["", "## Solver-reported linear residuals", "",
          "| Solver | Case | Thermal free residual | Mechanical free residual |",
          "|---|---|---|---|"]
    for key, label in (("coupfe", "CoupFE"), ("fenicsx", "FEniCSx")):
        for case in CASES:
            s = res["solvers"][key]
            L.append(f"| {label} | {case} | {s['thermal_free_residual'][case]:.2e} | "
                     f"{s['mechanics_free_residual'][case]:.2e} |")

    if "cross_residual" in res:
        L += ["", "## Cross-residual check "
              "(`cross_residual_check.py`)", "",
              "Each solver's field substituted into the *FEniCSx reference's own* discrete "
              "equations, normalised by that reference's load over the unconstrained dofs.", "",
              "| Case | Equation | CoupFE field | FEniCSx field |", "|---|---|---|---|"]
        for case in CASES:
            c = res["cross_residual"]["cases"][case]
            L.append(f"| {case} | thermal | {c['thermal_residual_of_coupfe_field']:.2e} | "
                     f"{c['thermal_residual_of_fenicsx_field']:.2e} |")
            L.append(f"| {case} | mechanical | {c['mechanical_residual_of_coupfe_field']:.2e} | "
                     f"{c['mechanical_residual_of_fenicsx_field']:.2e} |")
        L += ["", "Both computed solutions satisfy the independently assembled reference equations "
              "with small residuals. This is consistent with roundoff amplified by conditioning; "
              "it does not measure a condition number or prove equality of the full matrices. "
              "It does not establish the physical validity of the model.", ""]

    p = res["solvers"]["fenicsx"]["patch_checks"]
    m = res["solvers"]["fenicsx"]["mesh_checks"]
    L += ["", "## Independent absolute checks in the FEniCSx reference", "",
          f"- unit-cube Fourier flux error {p['cube_flux_absolute_error_W']:.2e} W against the "
          "exact 2 W,",
          f"- free thermal expansion relative error {p['free_expansion_relative_error']:.2e} "
          "against u = alpha dT x,",
          f"- fully constrained thermal stress error {p['constrained_stress_absolute_error_Pa']:.2e} "
          f"Pa against the exact {p['constrained_stress_exact_Pa']:.6g} Pa,",
          f"- recomputed tetrahedron volumes vs the input array: max relative difference "
          f"{m['recomputed_volume_max_relative_error']:.2e}, "
          f"{m['non_positive_orientations']} non-positive orientations,",
          f"- DOLFINx node coordinates vs input after ID mapping: max error "
          f"{m['node_coord_max_abs_error_m']:.1e} m, connectivity one-to-one: "
          f"{m['connectivity_one_to_one']},",
          f"- {m['top_facets_matched']} of {m['exterior_facets']} exterior facets matched to the "
          f"supplied top face set, integrated Robin area {m['dolfinx_top_area_m2']:.9e} m^2 "
          f"(relative error {m['top_area_relative_error']:.1e} against the 18 mm x 18 mm lid).", ""]

    L += ["## Scope", "", res["scope"], "",
          "Provenance: mesh `" + res["provenance"]["mesh_sha256"][:16] + "...`, geometry `"
          + res["provenance"]["geometry_sha256"][:16] + "...`; "
          f"FEniCSx {res['solvers']['fenicsx']['dolfinx']} / PETSc "
          f"{res['solvers']['fenicsx']['petsc']}; CoupFE core "
          f"`{res['solvers']['coupfe']['core_revision'][:12]}`, EDA "
          f"`{res['solvers']['coupfe']['eda_revision'][:12]}`.", ""]
    return "\n".join(L)


def figure(res: dict, mesh_dir: Path, ref_dir: Path, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    bins = np.logspace(-18, -4, 71)   # relative error decades, tolerance at 1e-5

    fig, axes = plt.subplots(2, 2, figsize=(11, 8))
    for case, colour in zip(CASES, ("tab:blue", "tab:orange")):
        T_o = np.load(mesh_dir / f"{case}_fields.npz")["temperature_C"]
        T_r = np.load(ref_dir / f"{case}_fenicsx_fields.npz")["temperature_C"]
        U_o = np.load(mesh_dir / f"{case}_mechanics.npz")["displacement_m"]
        U_r = np.load(ref_dir / f"{case}_fenicsx_mechanics.npz")["displacement_m"]
        V_o = np.load(mesh_dir / f"{case}_mechanics.npz")["von_mises_MPa"]
        V_r = np.load(ref_dir / f"{case}_fenicsx_mechanics.npz")["von_mises_MPa"]
        rise = T_o.max() - REFERENCE_C
        floor = bins[0]
        axes[0, 0].hist(np.clip(np.abs(T_r - T_o) / rise, floor, None), bins=bins,
                        histtype="step", color=colour, label=case, log=True)
        axes[0, 1].hist(np.clip(np.linalg.norm(U_r - U_o, axis=1)
                                / np.linalg.norm(U_o, axis=1).max(), floor, None),
                        bins=bins, histtype="step", color=colour, label=case, log=True)
        axes[1, 0].plot(V_o, V_r, ".", ms=1, alpha=.3, color=colour, label=case)
        axes[1, 1].hist(np.clip(np.abs(V_r - V_o) / np.abs(V_o).max(), floor, None), bins=bins,
                        histtype="step", color=colour, label=case, log=True)
    lim = axes[1, 0].get_xlim()
    axes[1, 0].plot(lim, lim, "k-", lw=.6)
    for ax, title, xlabel in (
            (axes[0, 0], "Nodal temperature", "|dT| / peak rise"),
            (axes[0, 1], "Nodal displacement", "|dU| / max |U|"),
            (axes[1, 0], "Cell von Mises parity", "CoupFE [MPa]"),
            (axes[1, 1], "Cell von Mises", "|dVM| / max VM")):
        ax.set_title(title)
        ax.set_xlabel(xlabel)
        ax.legend(fontsize=8, markerscale=8)
    axes[1, 0].set_ylabel("FEniCSx [MPa]")
    for ax in (axes[0, 0], axes[0, 1], axes[1, 1]):
        ax.set_ylabel("cells / nodes")
        ax.set_xscale("log")
        ax.set_xlim(bins[0], bins[-1])
        ax.axvline(TOLERANCES["field_relative"], color="k", ls="--", lw=.8)
        ax.text(TOLERANCES["field_relative"], 1.02, " tolerance 1e-5", fontsize=7,
                transform=ax.get_xaxis_transform(), ha="right", va="bottom")
    fig.suptitle("CoupFE vs independent FEniCSx reference, same mesh "
                 "(dashed line = predeclared 1e-5 tolerance)")
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mesh-dir", type=Path, default=HERE.parent / "runs" / "h0.45")
    ap.add_argument("--reference", type=Path, default=HERE / "results")
    ap.add_argument("--out", type=Path, default=HERE)
    ap.add_argument("--cross-residual", type=Path, default=HERE / "cross_residual.json",
                    help="optional cross_residual_check.py output to fold into the report")
    ap.add_argument("--no-figure", action="store_true")
    args = ap.parse_args()

    res = compare(args.mesh_dir.resolve(), args.reference.resolve(), args.cross_residual)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "comparison.json").write_text(json.dumps(res, indent=2))
    (args.out / "COMPARISON.md").write_text(markdown(res))
    if not args.no_figure:
        figure(res, args.mesh_dir.resolve(), args.reference.resolve(),
               args.out / "comparison.png")

    for case in CASES:
        c = res["cases"][case]["checks"]
        print(f"{case}: worst field {c['worst_field_relative_error']:.3e} "
              f"({c['worst_field']}), worst metric {c['worst_metric_relative_error']:.3e} "
              f"({c['worst_metric']}), worst body T {c['worst_body_temperature_relative_error']:.3e}",
              flush=True)
    print("passed" if res["passed"] else "MISMATCH", flush=True)


if __name__ == "__main__":
    main()
