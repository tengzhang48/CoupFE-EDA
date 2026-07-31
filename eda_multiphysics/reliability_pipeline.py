"""Capstone: an end-to-end design -> reliability pipeline on a solver-neutral case.

Composes separately checked components into one automated flow that takes an
EDA-style case and emits a reliability scorecard. The bundled default is a
project-authored synthetic fixture; the same interface accepts caller-supplied
OpenROAD/OpenDB placement and PDNSim network exports. The bundled PDN field has
a direct closed-form oracle; later handoffs have structural checks and reuse
component-level evidence. The composed output has no real-device oracle.

  stage              metric                       evidence
  1 PDN electrical   worst IR drop                direct case reference + scipy
  2 electrothermal   peak dT, R(T) IR shift       separate component gates
  3 thermomechanics  peak TSV stress              separate Lame component gate
  4 solder fatigue   dW/cycle, SAC305 life N_f    separate Anand/Syed evidence
  5 electromigration worst J, Blech screen        separate Black/Blech evidence

Each stage REUSES a module that ships its own gate(s) in `gates.py`; this driver only
wires them and propagates the physical hand-offs (hotter die -> larger solder excursion
and worse EM). Data provenance is explicit. The bundled voltage oracle is closed-form and
the power map is synthetic; caller-supplied cases may carry their own labeled tool reference.

Run:  python -m eda_multiphysics.reliability_pipeline [case_dir] [pdn.sp]
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import sys

import numpy as np

from coupfe import newton_solve

from .anand import SAC305, thermal_cycle
from .electromigration import CU_EM, acceleration_factor, blech_product_crit
from .electrothermal_chip import run as run_et, _node_xy
from .pdn_graph import GraphConduction, parse_pg_spice
from .tsv_stress import lame_sigma_r

# Small, deterministic, project-authored integration fixture.
DEFAULT_CASE = os.path.join(os.path.dirname(__file__), "cases", "synthetic_pdn")

# Syed (ECTC 2004) energy-based SAC fatigue life: N_f = 1/(W' * dW_acc), dW in MPa(=MJ/m^3).
# W'=0.0019 /MPa (hyperbolic-sine creep SAC; cross-checked range 0.0014-0.0019). The
# energy density dW is the rigorous mesh-objective output; N_f is calibration-specific.
SYED_W = 0.0019


def _case_total_power(case_dir):
    """Load total power and explicit provenance from a case artifact.

    New cases use ``instance_power.csv``. The legacy ``instance_temperature.csv``
    shape remains accepted for caller-owned cases, but file existence alone is
    never treated as evidence that values came from an EDA tool.
    """
    power_name = "instance_power.csv"
    path = os.path.join(case_dir, power_name)
    if not os.path.exists(path):
        power_name = "instance_temperature.csv"
        path = os.path.join(case_dir, power_name)
        if not os.path.exists(path):
            return None
    with open(path) as f:
        rows = list(csv.DictReader(f))
    power_by_id = {}
    for row in rows:
        instance_id = str(row.get("eda_id", "")).strip()
        if not instance_id or instance_id in power_by_id:
            raise ValueError(f"{path}: eda_id values must be unique and non-empty")
        value = float(row["power_W"])
        if not np.isfinite(value) or value < 0.0:
            raise ValueError(
                f"{path}: power for {instance_id!r} must be finite and nonnegative"
            )
        power_by_id[instance_id] = value
    csv_total = sum(power_by_id.values())
    meta_path = os.path.join(case_dir, os.path.splitext(power_name)[0] + ".meta.json")
    if not os.path.exists(meta_path):
        return dict(total_power_W=csv_total, provenance="unlabeled_instance_csv",
                    instance_power_model="unknown", power_by_id=power_by_id)
    with open(meta_path) as f:
        meta = json.load(f)
    total = float(meta.get("total_power_W", csv_total))
    if not np.isclose(total, csv_total, rtol=1e-3, atol=1e-12):
        raise ValueError(
            f"power metadata total {total:.9g} W does not match {path} sum {csv_total:.9g} W"
        )
    return dict(total_power_W=total,
                provenance=str(meta.get("total_power_provenance", "unlabeled_instance_csv")),
                instance_power_model=str(meta.get("instance_power_model", "unknown")),
                power_by_id=power_by_id)


def _case_voltage_reference(case_dir, Vdd, spice):
    """Load a labeled worst-IR reference from the case, when one is supplied.

    The bundled case uses ``reference_vdd_nodes.csv`` with a closed-form
    reference. Caller-owned legacy cases may instead provide a PDNSim voltage
    dump. The source label is propagated so the scorecard never calls a
    synthetic reference a PDNSim result.
    """

    candidates = (
        ("reference_vdd_nodes.csv", "reference_vdd_nodes.meta.json", "case_reference"),
        ("pdnsim_vdd_nodes.csv", None, "PDNSim"),
    )
    analyzed_spice = os.path.realpath(os.fspath(spice))
    default_spice = os.path.realpath(os.path.join(case_dir, "pdn_vdd.sp"))
    with open(analyzed_spice, "rb") as stream:
        analyzed_hash = hashlib.sha256(stream.read()).hexdigest()
    for csv_name, meta_name, default_source in candidates:
        path = os.path.join(case_dir, csv_name)
        if not os.path.exists(path):
            continue
        with open(path) as stream:
            rows = list(csv.DictReader(stream))
        voltages = []
        for row in rows:
            normalized = {str(key).strip(): value for key, value in row.items()}
            value = normalized.get("voltage_V", normalized.get("Voltage"))
            if value is None:
                raise ValueError(f"{path}: expected voltage_V or Voltage column")
            voltages.append(float(value))
        if not voltages:
            raise ValueError(f"{path}: voltage reference must contain at least one row")
        source = default_source
        metadata = {}
        if meta_name is not None:
            meta_path = os.path.join(case_dir, meta_name)
            if os.path.exists(meta_path):
                with open(meta_path) as stream:
                    metadata = json.load(stream)
                source = str(metadata.get("reference_source", default_source))
        bound_hash = metadata.get("pdn_spice_sha256")
        if bound_hash is not None:
            if (
                not isinstance(bound_hash, str)
                or len(bound_hash) != 64
                or any(character not in "0123456789abcdef" for character in bound_hash)
            ):
                raise ValueError(f"{meta_path}: pdn_spice_sha256 must be 64 lowercase hex")
            if analyzed_hash != bound_hash:
                continue
        elif analyzed_spice != default_spice:
            # Never attach a case-local reference to an arbitrary override netlist.
            continue
        return {
            "worst_ir": float(Vdd - min(voltages)),
            "source": source,
            "path": path,
            "pdn_spice_sha256": analyzed_hash,
        }
    return None


def _em_screen_pdn(
    spice,
    T_op,
    *,
    T_ref=25.0 + 273.15,
    rho=CU_EM["rho"],
    p=CU_EM,
    dbu_per_um=None,
):
    """Per-lateral-segment EM screen from the supplied PDN solve.

    For a metal segment R = rho*L/A, so J = I/A = (g*dV)/(rho*L*g) = |dV|/(rho*L); the
    Blech product is j*L = |dV|/rho. We solve the supplied netlist for V, then screen every
    *lateral* segment (vias have ~0 in-plane length and are skipped). ``T_op`` comes from the
    upstream electrothermal stage and drives Black's temperature acceleration relative to
    ``T_ref``.  The Blech classification itself is temperature-independent in this compact model.
    """
    if T_op <= 0.0 or T_ref <= 0.0:
        raise ValueError("Black-model temperatures must be in kelvin and greater than zero")
    if dbu_per_um is None:
        manifest_path = os.path.join(os.path.dirname(os.path.abspath(spice)), "manifest.json")
        if not os.path.exists(manifest_path):
            raise ValueError(
                f"cannot determine DBU scale for {spice!r}: pass dbu_per_um explicitly"
            )
        with open(manifest_path) as stream:
            dbu_per_um = float(json.load(stream)["dbu_per_micron"])
    dbu_per_um = float(dbu_per_um)
    if not np.isfinite(dbu_per_um) or dbu_per_um <= 0.0:
        raise ValueError("dbu_per_um must be positive and finite")
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
    op = GraphConduction(n, edges0, f)
    V, _, _ = newton_solve([op], np.full(n, Vsup), None, n, dirich)
    V = V.real

    jL_crit = blech_product_crit(p)
    worst_J = 0.0
    nseg = nimm = 0
    for a, b, g in edges0:
        if inv[a] == "0" or inv[b] == "0":
            continue
        (ax, ay), (bx, by) = (
            _node_xy(inv[a], dbu_per_um),
            _node_xy(inv[b], dbu_per_um),
        )
        L = np.hypot(ax - bx, ay - by) * 1e-6                 # um -> m
        if L < 1e-9:                                          # vertical via: skip
            continue
        dV = abs(V[a] - V[b])
        J = dV / (rho * L)                                    # A/m^2
        nseg += 1
        if dV / rho < jL_crit:
            nimm += 1
        worst_J = max(worst_J, J)
    temp_af = acceleration_factor(1.0, T_ref, 1.0, T_op, n=p["n"], Ea=p["Ea"])
    return dict(worst_J=worst_J, jL_crit=jL_crit, n_seg=nseg, n_immortal=nimm, Vdd=Vsup,
                T_op=T_op, T_ref=T_ref, temp_acceleration=float(temp_af),
                relative_lifetime=float(1.0 / temp_af))


def run(case_dir=DEFAULT_CASE, spice=None, *, T_amb=25.0, Tcold=-40.0,
        D_tsv=10.0, r_ko=20.0, ngrid=7, k_si=148.0, t_si=20e-6, h_v=1.0e5,
        nx=40, ncyc=4, P_override=None, solder_profile="mission",
        qualification_Thi=125.0, verbose=True):
    spice = spice or os.path.join(case_dir, "pdn_vdd.sp")
    with open(os.path.join(case_dir, "manifest.json")) as stream:
        manifest = json.load(stream)
    design = str(manifest.get("design", os.path.basename(case_dir.rstrip("/"))))
    case_power = _case_total_power(case_dir)
    instance_power_W = None
    if P_override is not None:
        P_total = float(P_override)
        power_provenance = "user_override"
        instance_power_model = "area_distributed_proxy"
    elif case_power is not None:
        P_total = case_power["total_power_W"]
        power_provenance = case_power["provenance"]
        instance_power_model = case_power["instance_power_model"]
        instance_power_W = case_power["power_by_id"]
    else:
        P_total = 5e-3
        power_provenance = "default_5mW_scenario"
        instance_power_model = "area_distributed_proxy"

    Vdd = max(parse_pg_spice(spice)[3].values())
    voltage_reference = _case_voltage_reference(case_dir, Vdd, spice)
    power_mode = (
        "pdn_iv"
        if (
            P_override is None
            and instance_power_model == "closed_form_dc_load_power"
            and voltage_reference is not None
        )
        else "fixed_instance"
    )

    # --- stages 1-2: PDN electrical + coupled electrothermal (V -> T) ---
    et = run_et(
        case_dir,
        spice,
        P_total,
        instance_power_W=instance_power_W,
        power_mode=power_mode,
        k_si=k_si,
        t_si=t_si,
        h_v=h_v,
        nx=nx,
    )
    ir_ours = et["ir_iso"]
    ir_reference = None if voltage_reference is None else voltage_reference["worst_ir"]
    ir_reference_source = (
        None if voltage_reference is None else voltage_reference["source"]
    )
    peak_dT = et["peakdT"]

    # --- stage 3: thermomechanics (T -> u), TSV array over the die (Lame) ---
    Lx, Ly = et["Lx"], et["Ly"]
    xs = np.linspace(0.08, 0.92, ngrid) * Lx
    ys = np.linspace(0.08, 0.92, ngrid) * Ly
    swing = np.zeros((ngrid, ngrid))
    for j, py in enumerate(ys):
        for i, px in enumerate(xs):
            mesh, dT = et["mesh"], et["dT"]
            ii = min(max(int(px / Lx * mesh.nx), 0), mesh.nx - 1)
            jj = min(max(int(py / Ly * mesh.ny), 0), mesh.ny - 1)
            Top = float(dT[mesh.elems[jj * mesh.nx + ii]].mean())
            swing[j, i] = abs(lame_sigma_r(r_ko, D_tsv, Top)) / 1e6        # MPa
    peak_stress = float(swing.max())

    # --- stage 4: solder fatigue (SAC305) ---
    # The default mission profile is an active handoff: the electrothermal operating temperature
    # is the upper cycle temperature.  A fixed qualification cycle remains available explicitly,
    # but is intentionally not presented as power-sensitive.
    if solder_profile == "mission":
        Thi = T_amb + peak_dT
    elif solder_profile == "qualification":
        Thi = float(qualification_Thi)
    else:
        raise ValueError("solder_profile must be 'mission' or 'qualification'")
    if Thi <= Tcold:
        raise ValueError(f"solder cycle upper temperature {Thi:g} C must exceed Tcold {Tcold:g} C")
    cyc = thermal_cycle(SAC305, Tlo=Tcold, Thi=Thi, ncyc=ncyc)
    dW = cyc["dW_stab"]                                # MJ/m^3 == MPa, mesh-objective
    Nf_solder = 1.0 / (SYED_W * dW) if dW > 0 else np.inf

    # --- stage 5: electromigration on the analyzed PDN (hotter die -> worse EM) ---
    T_em = T_amb + peak_dT + 273.15
    em = _em_screen_pdn(
        spice,
        T_em,
        T_ref=T_amb + 273.15,
        dbu_per_um=float(manifest["dbu_per_micron"]),
    )

    out = dict(design=design, n_inst=et["n_inst"], die_um=et["die_um"], Vdd=Vdd,
               P_total=P_total,
               release_validation=False,
               analysis_role=(
                   "synthetic_integration_demonstration"
                   if manifest.get("provenance", {}).get("source_kind")
                   == "project_authored_synthetic_data"
                   else "caller_case_research_analysis"
               ),
               claim_boundary=(
                   "Direct composed-case oracle covers the bundled PDN field only; "
                   "downstream values use parametric assumptions and separate component evidence."
                   if voltage_reference is not None
                   else "No direct composed-case oracle is attached to this analyzed netlist; "
                   "outputs are caller-case research results with separate component evidence."
               ),
               P_real=(power_provenance == "openroad_report_power"),
               power_provenance=power_provenance,
               instance_power_model=instance_power_model,
               electrothermal_power_mode=et["power_mode"],
               load_power_coupled_W=et["load_power_coupled_W"],
               pdn_joule_power_coupled_W=et["pdn_joule_power_coupled_W"],
               thermal_power_coupled_W=et["thermal_power_coupled_W"],
               source_power_coupled_W=et["source_power_coupled_W"],
               power_balance_error_W=(
                   None
                   if et["power_balance_error_W"] is None
                   else float(et["power_balance_error_W"])
               ),
               ir_ours=ir_ours, ir_reference=ir_reference,
               ir_reference_source=ir_reference_source,
               ir_pct=100.0 * ir_ours / Vdd,
               rt_shift=et["pct_ir"], peak_dT=peak_dT,
               peak_stress=peak_stress, dW=dW, Thi=Thi, solder_profile=solder_profile,
               Nf_solder=Nf_solder,
               em_worst_J=em["worst_J"], em_jL_crit=em["jL_crit"],
               em_nseg=em["n_seg"], em_immortal=em["n_immortal"],
               em_T_K=em["T_op"], em_temp_acceleration=em["temp_acceleration"],
               em_relative_lifetime=em["relative_lifetime"])
    if verbose:
        _scorecard(out)
    return out


def _scorecard(o):
    line_width = 132
    stage_width = 27
    metric_width = 84
    irv = f"{o['ir_ours']*1e3:.3f} mV ({o['ir_pct']:.3f}% Vdd)"
    if o["ir_reference"] is not None:
        irv += (
            f"; reference {o['ir_reference']*1e3:.3f} mV "
            f"[{o['ir_reference_source']}; "
            f"Δ{abs(o['ir_ours']-o['ir_reference'])*1e3:.3f} mV]"
        )
    pdn_evidence = (
        "direct case reference + scipy"
        if o["ir_reference"] is not None
        else "independent scipy graph solve; no case reference"
    )
    rows = [
        ("1 PDN electrical", irv, pdn_evidence),
        ("2 electrothermal", f"peak ΔT={o['peak_dT']:.2f} K; R(T) IR {o['rt_shift']:+.1f}%",
         "separate component gates"),
        ("3 thermomechanics", f"peak TSV stress={o['peak_stress']:.2f} MPa", "Lamé component evidence"),
        ("4 solder fatigue (SAC305)",
         f"ΔW={o['dW']:.4f} MJ/m³ → N_f≈{o['Nf_solder']:,.0f} cyc (cycle to {o['Thi']:.0f}°C)",
         "Anand/Syed component evidence"),
        ("5 electromigration",
         f"worst J={o['em_worst_J']/1e4:.3g} A/cm²; Black AF={o['em_temp_acceleration']:.2f}x; "
         f"{o['em_immortal']}/{o['em_nseg']} Blech-immortal",
         "Black/Blech component evidence"),
    ]
    pr = f"[{o['power_provenance']}; {o['instance_power_model']}]"
    print(f"\n{'='*line_width}\nRELIABILITY SCORECARD — {o['design']} "
          f"({o['n_inst']} cells, die {o['die_um'][0]}×{o['die_um'][1]} µm, "
          f"Vdd={o['Vdd']:.2f} V, P={o['P_total']*1e3:.2f} mW {pr})\n{'='*line_width}")
    print(f"  {'stage':<{stage_width}}{'metric':<{metric_width}}  evidence")
    print(f"  {'-'*stage_width}{'-'*metric_width}{'-'*14}")
    for s, m, orc in rows:
        print(f"  {s:<{stage_width}}{m:<{metric_width}}  {orc}")
    print(f"{'='*line_width}")
    if o["power_balance_error_W"] is not None:
        print(
            "  Coupled PDN power closes: "
            f"load {o['load_power_coupled_W']*1e3:.6f} mW + "
            f"grid {o['pdn_joule_power_coupled_W']*1e6:.6f} µW = "
            f"source {o['source_power_coupled_W']*1e3:.6f} mW."
        )
    print("  Only a hash-bound case reference is a direct composed-case oracle; downstream")
    print("  models have separate component evidence. This workflow is a research")
    print("  integration demonstration, not real-device validation or signoff.")


def main():
    case = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_CASE
    spice = sys.argv[2] if len(sys.argv) > 2 else None
    run(case, spice)


if __name__ == "__main__":
    main()
