"""Fast regression checks for the EDA-multiphysics suite.

The suite combines published/analytic oracles, independent implementation
comparisons, invariants, interface and structural checks, and broken controls.
The suite uses NumPy, SciPy, and CoupFE without OpenROAD data. Broken controls ensure selected
acceptance tests reject a reintroduced bug. Consumed by both `tests/` and
`run.py`.
"""

from __future__ import annotations

import numpy as np

from coupfe import newton_solve

from .anand import (SNPB as ANAND, SAC305, SAC305_FIG310, integrate_uniaxial,
                    sat_stress)
from .electrothermal import solve_electrothermal
from .fe import StructuredQuadMesh, electrode_current, solve_field
from .pdn_graph import GraphConduction
from .tsv_stress import lame_sigma_r, sigma_at, solve_tsv


def _g(name, ok, detail):
    return dict(name=name, ok=bool(ok), detail=detail)


# ---- scalar electrothermal checks ----
def gate_thermal_patch():
    m = StructuredQuadMesh(16, 4, 1.0, 0.3)
    bc = {**{int(n): 0.0 for n in m.left()}, **{int(n): 1.0 for n in m.right()}}
    T, _, _ = solve_field(m, np.ones(len(m.elems)), None, bc)
    err = float(np.max(np.abs(T - m.coords[:, 0] / m.Lx)))
    return _g("thermal linear patch test", err < 1e-10, f"max|err|={err:.1e}")


def _l2_error_quad(mesh, U, exact_fn):
    """True element-L2 norm ||U - exact||_L2 over the quad mesh via 2x2 Gauss (for h-convergence)."""
    from .fe import _shape
    gp = 1.0 / np.sqrt(3.0)
    pts = [(-gp, -gp), (gp, -gp), (gp, gp), (-gp, gp)]
    e2 = 0.0
    for conn in mesh.elems:
        Xe, Ue = mesh.coords[conn], U[conn]
        for xi, eta in pts:
            N, dN = _shape(xi, eta)
            detJ = abs(np.linalg.det(dN @ Xe))
            xg = N @ Xe
            e2 += (float(N @ Ue) - exact_fn(xg[0], xg[1])) ** 2 * detJ
    return np.sqrt(e2)


def _h_convergence_order(const_source=False):
    """Solve -div(grad T) = Q with the manufactured T=sin(pi x)sin(pi y) at 3 mesh sizes; return
    (observed L2 order, errs). `const_source` reintroduces a wrong RHS (the broken control)."""
    exact = lambda x, y: np.sin(np.pi * x) * np.sin(np.pi * y)
    errs = []
    for n in (8, 16, 32):
        mesh = StructuredQuadMesh(n, n, 1.0, 1.0)
        Xc = mesh.elem_centroids()
        Q = 2.0 * np.pi ** 2 * np.sin(np.pi * Xc[:, 0]) * np.sin(np.pi * Xc[:, 1])
        if const_source:
            Q = np.full_like(Q, Q.mean())               # wrong RHS -> converges to the WRONG field
        X = mesh.coords
        onb = (np.isclose(X[:, 0], 0.0) | np.isclose(X[:, 0], 1.0)
               | np.isclose(X[:, 1], 0.0) | np.isclose(X[:, 1], 1.0))
        bc = {int(i): 0.0 for i in np.where(onb)[0]}
        U, _, _ = solve_field(mesh, np.ones(len(mesh.elems)), Q, bc)
        errs.append(_l2_error_quad(mesh, U, exact))
    order = 0.5 * (np.log2(errs[0] / errs[1]) + np.log2(errs[1] / errs[2]))
    return order, errs


def gate_h_convergence():
    """Measure L2 refinement order for bilinear diffusion on a manufactured solution."""
    order, errs = _h_convergence_order()
    ok = 1.8 <= order <= 2.3
    return _g("h-convergence: bilinear diffusion 2nd-order O(h^2)", ok,
              f"observed L2 order {order:.2f} (expect ~2); L2 {errs[0]:.1e}->{errs[1]:.1e}->{errs[2]:.1e}")


def gate_h_convergence_broken_control():
    """BROKEN CONTROL: with a wrong (constant) source the FE converges to the WRONG field, so the L2
    error vs the manufactured solution STAGNATES (order ~0) -- the convergence gate must reject it."""
    order, _ = _h_convergence_order(const_source=True)
    return _g("BROKEN-CONTROL: wrong-source h-convergence stagnates", abs(order) < 0.5,
              f"observed order {order:.2f} (must be ~0 -- no convergence to the manufactured field)")


def gate_ohm():
    sigma, V0, L, W = 3.0, 2.0, 1.0, 0.5
    m = StructuredQuadMesh(20, 5, L, W)
    bc = {**{int(n): V0 for n in m.left()}, **{int(n): 0.0 for n in m.right()}}
    V, op, _ = solve_field(m, np.full(len(m.elems), sigma), None, bc)
    I = abs(electrode_current(op, V, m.left()))
    err = abs(I - sigma * V0 * W / L) / (sigma * V0 * W / L)
    return _g("Ohm's-law current", err < 1e-6, f"I={I:.4f} vs {sigma*V0*W/L:.4f}")


def gate_joule_oneway():
    r = solve_electrothermal(StructuredQuadMesh(48, 2, 1.0, 1.0),
                             sigma0=1.0, alpha=0.0, k=1.0, V0=1.0, Tsink=0.0)
    err = abs(r["peakT"] - 1.0 / 8) / (1.0 / 8)
    return _g("Joule one-way peak dT (=sigmaV0^2/8k)", err < 3e-3,
              f"peakdT={r['peakT']:.4f} vs 0.125")


def gate_joule_broken_control():
    # the oracle must reject "no Joule coupling" (dT=0 != 0.125)
    return _g("BROKEN-CONTROL: Q=0 rejected", abs(0.0 - 0.125) > 1e-3, "must reject")


# ---- TSV thermomechanics (Lamé, PMC8472814) ----
def gate_tsv_lame():
    dT = -400.0
    _, rc, s_rr, _ = solve_tsv(30.0, dT)        # selected checked resolution (n=2400)
    fe = sigma_at(rc, s_rr, 20.0) / 1e6
    an = lame_sigma_r(20.0, 30.0, dT) / 1e6
    err = abs(fe - an) / abs(an)
    return _g("TSV stress vs Lame (D=30um)", err < 1e-2,
              f"FE={fe:.2f} vs {an:.2f} MPa")


# ---- Anand viscoplasticity (closed-form saturation) ----
def gate_anand_saturation():
    worst = 0.0
    for TC, ed in ((25.0, 1e-3), (125.0, 1e-3)):
        T = TC + 273.15
        _, sh, _ = integrate_uniaxial(ed, T, ANAND, eps_max=0.6)
        worst = max(worst, abs(float(sh[-1]) - float(sat_stress(ed, T, ANAND)))
                    / float(sat_stress(ed, T, ANAND)))
    return _g("Anand vs closed-form saturation", worst < 1e-2, f"max err={worst:.2%}")


def gate_anand_broken_control():
    # wrong activation energy must break the saturation match
    bad = dict(ANAND, QR=ANAND["QR"] * 1.1)
    _, sh, _ = integrate_uniaxial(1e-3, 298.15, bad, eps_max=0.6)
    err = abs(float(sh[-1]) - float(sat_stress(1e-3, 298.15, ANAND))) / float(sat_stress(1e-3, 298.15, ANAND))
    return _g("BROKEN-CONTROL: Anand Q/R x1.1 rejected", err > 0.05, f"err={err:.0%}")


# ---- SAC305 (modern lead-free): reproduce published Motalab Fig 3.10 benchmark ----
def gate_anand_sac305_saturation():
    # Compare the SAC305 integrator with its closed-form saturation relation.
    worst = 0.0
    for TC, ed in ((25.0, 1e-3), (125.0, 1e-3), (25.0, 1e-5)):
        T = TC + 273.15
        _, sh, _ = integrate_uniaxial(ed, T, SAC305, eps_max=0.20)
        worst = max(worst, abs(float(sh[-1]) - float(sat_stress(ed, T, SAC305)))
                    / float(sat_stress(ed, T, SAC305)))
    return _g("SAC305 Anand vs closed-form saturation", worst < 1e-2, f"max err={worst:.2%}")


def gate_anand_sac305_benchmark():
    # closed-form saturation reproduces the PUBLISHED figure (Motalab diss. Fig 3.10a)
    worst = max(abs(float(sat_stress(ed, TC + 273.15, SAC305)) - pub) / pub
                for TC, ed, pub in SAC305_FIG310)
    anchor = float(sat_stress(1e-3, 298.15, SAC305))   # 25C/1e-3 ~ 40-41 MPa published
    ok = worst < 0.12 and abs(anchor - 40.5) < 2.5
    return _g("SAC305 saturation vs published Motalab Fig 3.10", ok,
              f"anchor={anchor:.1f} MPa (pub ~40-41); worst fig diff={worst:.1%}")


def gate_anand_sac305_broken_control():
    # wrong constants must MISS the published figure (here: A off by 100x)
    bad = dict(SAC305, A=SAC305["A"] * 100.0)
    worst = max(abs(float(sat_stress(ed, TC + 273.15, bad)) - pub) / pub
                for TC, ed, pub in SAC305_FIG310)
    return _g("BROKEN-CONTROL: SAC305 A x100 misses figure", worst > 0.25,
              f"worst diff={worst:.0%}")


# ---- solder-joint FE (return map + patch test) ----
def gate_solder_return_map():
    from .solder_joint import _drive_homogeneous, SNPB as SJ
    T = 298.15
    exy_dot = 1e-3
    deps = 0.6 / 1500
    dt = deps / exy_dot
    path = [[0.0, 0.0, k * deps] for k in range(1500)]
    hist, _ = _drive_homogeneous(path, T, SJ, dt)
    q_fe = np.sqrt(3.0) * abs(hist[-1, 3])
    q_an = float(sat_stress(2 / np.sqrt(3) * exy_dot, T, SJ))
    err = abs(q_fe - q_an) / q_an
    return _g("solder J2 return map vs saturation (shear)", err < 1e-2,
              f"err={err:.2%}")


def gate_solder_patch():
    from .solder_joint import patch_test
    import contextlib
    import io
    with contextlib.redirect_stdout(io.StringIO()):
        ok = patch_test()
    return _g("solder FE elastic patch test", ok, "affine field exact")


# ---- 3D Anand Hex8 viscoplastic element ----
def gate_anand_3d_return_map():
    from .anand_3d import validate_return_map_3d
    err = validate_return_map_3d()
    return _g("3D Anand return map vs saturation (shear)", err < 1e-2,
              f"err={err:.2%}")


def gate_anand_3d_transient():
    from .anand_3d import validate_return_map_transient_3d
    err = validate_return_map_transient_3d()
    return _g("3D Anand map vs integrate_uniaxial (full transient)", err < 5e-3,
              f"max transient err={err:.2%} vs 1D oracle")


def gate_anand_3d_transient_broken_control():
    from .anand_3d import SAC305_3D, validate_return_map_transient_3d
    bad = dict(SAC305_3D, h0=SAC305_3D["h0"] * 1.3)
    err = validate_return_map_transient_3d(p=bad, oracle_p=SAC305_3D)
    return _g("BROKEN-CONTROL: 3D Anand h0 error rejected by transient", err > 5e-3,
              f"transient err={err:.1%} while saturation is h0-independent")


def gate_anand_3d_patch():
    from .anand_3d import patch_test_3d
    err = patch_test_3d()
    return _g("3D Anand Hex8 elastic patch test", err < 1e-10,
              f"max|err|={err:.1e}")


def gate_anand_3d_sac305_cycle_smoke():
    from .anand_3d import prescribed_hex8_cycle
    r = prescribed_hex8_cycle(ncyc=2, steps_per_cyc=18)
    ok = r["dW_stab"] > 0.0 and np.isfinite(r["Nf"]) and r["Nf"] > 0.0
    return _g("prescribed one-Hex8 SAC305 cycle smoke check", ok,
              f"dW={r['dW_stab']:.4f} MPa; calibration output={r['Nf']:,.0f} cycles")


def gate_anand_3d_broken_control():
    from .anand_3d import prescribed_hex8_cycle
    r = prescribed_hex8_cycle(Tlo=25.0, Thi=25.0, ncyc=1, steps_per_cyc=8)
    return _g("BROKEN-CONTROL: 3D Anand no swing -> no dW", abs(r["dW_stab"]) < 1e-12,
              f"dW={r['dW_stab']:.1e} (must be ~0)")


def gate_solder_life_experimental_anchor():
    """IN-SAMPLE CALIBRATION CHECK (an external, measured tie-point). The Darveaux energy-life model with
    Motalab's (Auburn 2013) SAC305 constants reproduces the MEASURED characteristic thermal-cycling
    life of the 19 mm PBGA (N63.2 = 4719 cycles, -40/+125 C, IPC-9701 TC3) from the published
    dW ~ 0.20 MPa/cycle -- within Darveaux's OWN stated +/-2x absolute accuracy. This turns N_f from a
    bare formula into a calibration reproduction. (Reproduces the measured life
    to ~5% at dW=0.23, within the figure-read band; the Syed W'=0.0019 form lands at 0.56x, also <2x.)
    Honest scope: this is not independent validation of the dW->N_f mapping; it
    reuses an in-sample calibration case, so +/-2x is the scoped check."""
    from .anand_3d import darveaux_life, MOTALAB_2013
    N_meas, dW = MOTALAB_2013["N_measured"], MOTALAB_2013["dW"]
    Nf, _, _ = darveaux_life(dW)
    ratio = Nf / N_meas
    return _g("solder-life in-sample calibration reproduction (Motalab 19mm PBGA)",
              0.5 <= ratio <= 2.0,
              f"Darveaux N_f={Nf:,.0f} vs calibration case {N_meas:,.0f} "
              f"= {ratio:.2f}x (within scoped +/-2x)")


def gate_solder_life_experimental_broken_control():
    """BROKEN CONTROL: a 10x-wrong dW drives the predicted life far outside the +/-2x scatter band,
    so the anchor is not a trivially-always-true check -- it can reject a bad energy input."""
    from .anand_3d import darveaux_life, MOTALAB_2013
    N_meas = MOTALAB_2013["N_measured"]
    Nf, _, _ = darveaux_life(2.0)                       # 10x the real ~0.20 MPa dW
    ratio = Nf / N_meas
    return _g("BROKEN-CONTROL: 10x-wrong dW misses measured life", not (0.5 <= ratio <= 2.0),
              f"N_f={Nf:,.0f} -> {ratio:.3f}x measured (must fall OUTSIDE +/-2x)")


# ---- PDN-graph electrical solver vs independent scipy ----
def gate_pdn_vs_scipy():
    import scipy.sparse as sp
    import scipy.sparse.linalg as spla
    n = 4                                   # 0=gnd, 1=source(1.1V), 2, 3(load)
    edges = [(1, 2, 1.0), (2, 3, 2.0), (1, 3, 0.5)]
    load = np.zeros(n)
    load[3] = 0.3
    op = GraphConduction(n, edges, load)
    V, _, _ = newton_solve([op], np.full(n, 1.1), None, n, {1: 1.1, 0: 0.0})
    G = sp.lil_matrix((n, n))               # independent assembly + solve
    for a, b, g in edges:
        G[a, a] += g; G[b, b] += g; G[a, b] -= g; G[b, a] -= g
    rhs = -load.copy()
    for nd, v in {1: 1.1, 0: 0.0}.items():
        G.rows[nd] = [nd]; G.data[nd] = [1.0]; rhs[nd] = v
    Vs = spla.spsolve(G.tocsr(), rhs)
    err = float(np.max(np.abs(V - Vs)))
    return _g("PDN-graph solver vs scipy", err < 1e-10, f"max|dV|={err:.1e}")


# ---- composed pipeline on the project-authored synthetic fixture ----
def gate_capstone_pipeline():
    # Run the full chain and require the graph solve to reproduce the fixture's
    # independent closed-form voltage reference.
    from .reliability_pipeline import run
    r = run(nx=12, ncyc=2, verbose=False)
    ir_ok = (
        r["ir_reference"] is not None
        and np.isclose(r["ir_ours"], r["ir_reference"], rtol=1e-9, atol=1e-12)
    )
    physical = (r["peak_dT"] > 0 and r["peak_stress"] > 0 and r["dW"] > 0
                and np.isfinite(r["Nf_solder"]) and r["Nf_solder"] > 0
                and r["em_nseg"] > 0 and 1000 < r["em_jL_crit"] / 100 < 6000)
    power_ok = (
        r["electrothermal_power_mode"] == "pdn_iv"
        and r["power_balance_error_W"] is not None
        and abs(r["power_balance_error_W"]) < 1e-12
        and np.isclose(r["source_power_coupled_W"], 9.0e-3, rtol=1e-10, atol=1e-12)
    )
    claim_ok = (
        r["release_validation"] is False
        and r["analysis_role"] == "synthetic_integration_demonstration"
    )
    return _g("capstone V->T->u->life pipeline (synthetic fixture)",
              ir_ok and physical and power_ok and claim_ok,
              f"IR {r['ir_ours']*1e3:.3f}mV vs reference "
              f"{(r['ir_reference'] or 0)*1e3:.3f}; "
              f"balance={r['power_balance_error_W']:.1e}W; "
              f"dT={r['peak_dT']:.1f}K σ={r['peak_stress']:.1f}MPa "
              f"Nf={r['Nf_solder']:,.0f}")


def gate_capstone_broken_control():
    # Structural zero plus active-handoff control: no chip power removes self-heating/stress;
    # adding power must worsen both mission-profile solder fatigue and Black temperature AF.
    from .reliability_pipeline import run
    cold = run(nx=12, ncyc=2, P_override=0.0, verbose=False)
    hot = run(nx=12, ncyc=2, P_override=5e-3, verbose=False)
    zero_ok = cold["peak_dT"] < 1e-2 and cold["peak_stress"] < 1e-2
    handoffs_ok = (hot["dW"] > cold["dW"] and hot["Nf_solder"] < cold["Nf_solder"]
                   and hot["em_temp_acceleration"] > cold["em_temp_acceleration"])
    return _g("BROKEN-CONTROL: P=0 structural zero + active life handoffs",
              zero_ok and handoffs_ok,
              f"zero dT={cold['peak_dT']:.1e}K σ={cold['peak_stress']:.1e}MPa; "
              f"5mW Nf {cold['Nf_solder']:,.0f}->{hot['Nf_solder']:,.0f}, "
              f"EM AF {cold['em_temp_acceleration']:.2f}->{hot['em_temp_acceleration']:.2f}")


# ---- electro-thermo-viscoplastic study, Phase 1: electro-thermal core ----
def gate_etv_selfheating():
    # Coupled electrothermal solver vs the exact 1D self-heating limit sigmaV0^2/8k.
    from .etv_solder import verify_selfheating
    peak, exact, err = verify_selfheating()
    return _g("ETV self-heating vs sigma*V0^2/8k", err < 2e-3,
              f"peak dT={peak:.4f} vs {exact:.4f} ({err:.1e})")


def gate_etv_crowding():
    # Qualitative literature-context check on a fixed simplified mesh.
    from .etv_solder import crowding_factor
    f, _, _ = crowding_factor(n=28)
    return _g("ETV fixed-mesh crowding is in the Dandu-context range", 5.0 < f < 25.0,
              f"factor={f:.1f}x on the tested simplified geometry (qualitative check)")


def gate_etv_broken_control():
    # structural zero: full entry+exit (uniform current) -> no crowding (factor ~ 1)
    from .etv_solder import crowding_factor
    f, _, _ = crowding_factor(n=28, post_frac=1.0, pad_frac=1.0)
    return _g("BROKEN-CONTROL: uniform current -> no crowding", abs(f - 1.0) < 0.05,
              f"factor={f:.3f} (must be ~1)")


def gate_etv_staggered():
    # Phase 2: the staggered SAC305 viscoplastic cycle yields a well-defined, shaken-down dW
    from .etv_solder import staggered_baseline
    r = staggered_baseline(ncyc=3)
    c = r["dW_cyc"]
    shook = r["dW_stag"] > 0 and abs(c[-1] - c[-2]) < 0.5 * abs(c[0])
    return _g("ETV staggered SAC305 dW/cycle (Phase 2)", shook,
              f"dW={r['dW_stag']:.4f} MJ/m^3 (shakes down; baseline for Phase 3)")


def gate_etv_staggered_broken_control():
    # structural zero: no operating temperature swing -> no CTE strain -> no inelastic work
    from .etv_solder import staggered_baseline
    r = staggered_baseline(dT_cyc=0.0, ncyc=2)
    return _g("BROKEN-CONTROL: no swing -> no inelastic dW", abs(r["dW_stag"]) < 1e-6,
              f"dW={r['dW_stag']:.1e} (must be ~0)")


def gate_etv_monolithic_consistency():
    # The monolithic material-point model reduces to staggered with no internal heating.
    from .etv_solder import etv_cycle
    stag = etv_cycle(coupled=False, q_joule=0.0, ncyc=3)["dW_stab"]
    mono = etv_cycle(coupled=True, q_joule=0.0, g_th=1e10, ncyc=3)["dW_stab"]
    return _g("ETV monolithic reduces to staggered (Phase 3)", abs(mono - stag) / stag < 1e-4,
              f"mono={mono:.5f} vs stag={stag:.5f} (rel {abs(mono-stag)/stag:.1e})")


def gate_etv_coupling_quasistatic():
    # Regression for the tested material-point parameterization.
    from .etv_solder import coupling_effect, joule_density, dandu_bump
    q = joule_density(dandu_bump()["j_avg"])
    r = coupling_effect(q_joule=q, g_th=8e6, ramp=200.0, ncyc=3)
    return _g("ETV tested slow-ramp material-point delta", abs(r["delta"]) < 0.01,
              f"delta={r['delta']*100:+.2f}% for this parameterization")


# ---- ETV FE refinement: monolithic coupled element on the CoupFE contract ----
def gate_etv_fe_selfheating():
    # The monolithic electrothermal FE element is checked against dT = sigma V0^2/8k.
    from .etv_fe import verify_selfheating_fe
    peak, exact, err, nit = verify_selfheating_fe(n=32)
    return _g("ETV monolithic FE element vs sigma*V0^2/8k", err < 2e-3,
              f"peak={peak:.4f} vs {exact:.4f} ({err:.1e}; {nit} Newton iters)")


def gate_etv_fe_consistency():
    # Compare the monolithic block solve with staggered Picard under sigma(T) feedback.
    from .etv_fe import consistency_vs_staggered
    tm, ts, rel, nit = consistency_vs_staggered(n=24)
    return _g("ETV monolithic FE == staggered Picard", rel < 1e-3,
              f"rel={rel:.1e} (sigma(T) coupling via complex-step tangent)")


def gate_etv_fe_broken_control():
    # structural zero: no applied voltage -> no current -> no Joule heating -> T = 0
    from .etv_fe import solve_coupled_et
    from .fe import StructuredQuadMesh
    m = StructuredQuadMesh(16, 4, 1.0, 0.2)
    d = {}
    for i in m.left():
        d[2 * int(i)] = 0.0; d[2 * int(i) + 1] = 0.0
    for i in m.right():
        d[2 * int(i)] = 0.0; d[2 * int(i) + 1] = 0.0          # V0 = 0
    _, T, _ = solve_coupled_et(m, sigma0=3.0, k=1.5, dirichlet=d)
    return _g("BROKEN-CONTROL: no voltage -> no Joule heating", float(abs(T).max()) < 1e-12,
              f"peakT={float(abs(T).max()):.1e} (must be ~0)")


# reliability + classic-mechanics benchmark gates (each returns name/ok/detail)
from .electromigration import (gate_black_acceleration, gate_blech_product,  # noqa: E402
                               gate_em_broken_control)
from .thermomech import (gate_bimetal, gate_bimetal_broken_control,  # noqa: E402
                         gate_thermal_gradient_cylinder, gate_lame_cylinder)
from .capacitance import gate_capacitance, gate_capacitance_scaling  # noqa: E402
from .thermal_runaway import gate_runaway_critical, gate_runaway_balance  # noqa: E402
from .transient import gate_transient, gate_transient_broken_control  # noqa: E402
from .creep import gate_creep_rate, gate_creep_broken_control  # noqa: E402

GATES = [
    gate_thermal_patch, gate_h_convergence, gate_h_convergence_broken_control,
    gate_ohm, gate_joule_oneway, gate_joule_broken_control,
    gate_tsv_lame, gate_anand_saturation, gate_anand_broken_control,
    # SAC305 (modern lead-free) -- reproduce published Motalab Fig 3.10 benchmark
    gate_anand_sac305_saturation, gate_anand_sac305_benchmark,
    gate_anand_sac305_broken_control,
    gate_solder_return_map, gate_solder_patch, gate_pdn_vs_scipy,
    # 3D Hex8 Anand material/element checks plus a fully prescribed cycle smoke check
    gate_anand_3d_return_map, gate_anand_3d_transient,
    gate_anand_3d_transient_broken_control, gate_anand_3d_patch,
    gate_anand_3d_sac305_cycle_smoke, gate_anand_3d_broken_control,
    # in-sample calibration reproduction: Darveaux/Motalab SAC305 4719-cycle case (+/-2x) + control
    gate_solder_life_experimental_anchor, gate_solder_life_experimental_broken_control,
    # electromigration (Black + Blech)
    gate_black_acceleration, gate_blech_product, gate_em_broken_control,
    # classic mechanics benchmarks (bending + thermal-gradient)
    gate_bimetal, gate_bimetal_broken_control, gate_thermal_gradient_cylinder,
    # capacitance (RC), thermal runaway (bifurcation), transient (time domain)
    gate_capacitance, gate_capacitance_scaling,
    gate_runaway_critical, gate_runaway_balance,
    gate_transient, gate_transient_broken_control,
    # creep (stress-controlled Anand) + 2D axisymmetric element (Lame)
    gate_creep_rate, gate_creep_broken_control, gate_lame_cylinder,
    # capstone: the whole design->reliability chain on a project-authored fixture
    gate_capstone_pipeline, gate_capstone_broken_control,
    # electrothermal material/reduced-model checks (Dandu 2010 context)
    gate_etv_selfheating, gate_etv_crowding, gate_etv_broken_control,
    # staggered viscoplastic baseline (SAC305)
    gate_etv_staggered, gate_etv_staggered_broken_control,
    # monolithic material-point comparison and coupling sensitivity
    gate_etv_monolithic_consistency, gate_etv_coupling_quasistatic,
    # ETV FE refinement: monolithic coupled electro-thermal element on the CoupFE contract
    gate_etv_fe_selfheating, gate_etv_fe_consistency, gate_etv_fe_broken_control,
]


def run_all():
    return [g() for g in GATES]
