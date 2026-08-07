"""Electrothermal FE checks and a partitioned solder-cycle demonstration.

The material-point study (``etv_solder.py``) supplies a reduced comparison for
this spatially resolved finite element: one
residual carrying multiple fields, the cross-field tangent obtained by COMPLEX STEP (not hand-
coded), solved with `coupfe.newton_solve`. No separate FE library -- the same operator contract
as `fe.py`, extended to a coupled multi-DOF element.

Stage A (this module): the monolithic ELECTRO-THERMAL element -- phi and T in one Newton
system, with the two-way coupling captured automatically by the complex-step tangent:
    phi:  R_phi = integral( sigma(T) grad(phi) . grad(N) )                = 0
    T:    R_T   = integral( k grad(T).grad(N) - sigma(T)|grad phi|^2 N
                            + h_vol T N )                                  = 0
sigma(T) = sigma0/(1 + alpha (T)) makes the phi-block depend on T (thermal->electrical);
the Joule term sigma|grad phi|^2 makes the T-block depend on phi (electrical->thermal). A
staggered scheme splits these into two solves; here they are one block system.

The checked examples compare this implementation with the exact 1D self-heating
limit ``dT = sigma V0^2/8k`` and with the staggered Picard implementation in
``etv_solder.solve_et``. DOFs are interleaved per node: ``[phi, T]``.

The optional cycle demonstration combines a lumped backward-Euler temperature
model with the spatial plane-strain Anand mechanics in ``solder_joint``.  It is
partitioned (not a monolithic phi-T-u element), uses a fail-closed nonlinear
increment solve, and is not a device or fatigue-life validation.
"""

from __future__ import annotations

import numpy as np

from coupfe import newton_solve
from coupfe.operators.base import Residual, Tangent, complex_step_tangent

from .fe import StructuredQuadMesh, _GAUSS, _shape

NF = 2          # fields per node: 0 = phi (electric potential), 1 = T (temperature rise)


def _coupled_et_resid(ue, xy, sigma0, alpha_sig, k, h_vol):
    """Element residual of the coupled electro-thermal Q4 (ue = [phi0,T0,phi1,T1,...], 8).

    Complex-safe (the Joule term uses a holomorphic dot, no conjugate) so the cross-field
    tangent comes straight from `complex_step_tangent`.
    """
    R = np.zeros(2 * 4, dtype=ue.dtype)
    phi = ue[0::NF]
    T = ue[1::NF]
    for xi, eta, w in _GAUSS:
        N, dN = _shape(xi, eta)
        J = dN @ xy
        detJ = J[0, 0] * J[1, 1] - J[0, 1] * J[1, 0]
        invJ = np.array([[J[1, 1], -J[0, 1]], [-J[1, 0], J[0, 0]]]) / detJ
        B = invJ @ dN                                    # (2,4) physical grad(N)
        gphi = B @ phi
        gT = B @ T
        Tg = N @ T                                       # local temperature rise
        sig = sigma0 / (1.0 + alpha_sig * Tg)            # sigma(T): thermal->electrical
        Q = sig * (gphi @ gphi)                          # Joule: electrical->thermal (holo.)
        R[0::NF] += sig * (B.T @ gphi) * detJ * w
        R[1::NF] += (k * (B.T @ gT) - Q * N + h_vol * Tg * N) * detJ * w
    return R


class CoupledET:
    """CoupFE Operator: monolithic electro-thermal Q4 (2 DOF/node, phi & T)."""

    def __init__(self, mesh, *, sigma0, alpha_sig=0.0, k=1.0, h_vol=0.0):
        self.mesh = mesh
        self.sigma0, self.alpha_sig, self.k, self.h_vol = sigma0, alpha_sig, k, h_vol
        self.ndof = NF * mesh.nnode

    def _gd(self, conn):
        return np.array([NF * n + f for n in conn for f in range(NF)])

    def residual(self, U, state, t, dt):
        R = np.zeros(self.ndof, dtype=U.dtype)
        for conn in self.mesh.elems:
            gd = self._gd(conn)
            R[gd] += _coupled_et_resid(U[gd], self.mesh.coords[conn],
                                       self.sigma0, self.alpha_sig, self.k, self.h_vol)
        return Residual(gdofs=np.arange(self.ndof), values=R)

    def tangent(self, U, state, t, dt):
        rows, cols, vals = [], [], []
        for conn in self.mesh.elems:
            gd = self._gd(conn)
            xy = self.mesh.coords[conn]
            Ke = complex_step_tangent(
                lambda ue: _coupled_et_resid(ue, xy, self.sigma0, self.alpha_sig,
                                             self.k, self.h_vol), U[gd])
            for i in range(8):
                for j in range(8):
                    rows.append(gd[i]); cols.append(gd[j]); vals.append(Ke[i, j])
        return Tangent(rows=np.array(rows), cols=np.array(cols), values=np.array(vals))

    def commit(self, U, state, t, dt):
        return state


def solve_coupled_et(mesh, *, sigma0, alpha_sig=0.0, k=1.0, h_vol=0.0, dirichlet,
                     **newton_kw):
    """Solve the monolithic electro-thermal block system; returns (phi, Trise, n_iters)."""
    from coupfe import assemble_residual

    op = CoupledET(mesh, sigma0=sigma0, alpha_sig=alpha_sig, k=k, h_vol=h_vol)
    residual_rtol = float(newton_kw.pop("residual_rtol", 1e-8))
    residual_atol = float(newton_kw.pop("residual_atol", 1e-10))
    constrained = np.array(sorted(dirichlet), dtype=int)
    free = np.ones(op.ndof, dtype=bool)
    free[constrained] = False

    initial = np.zeros(op.ndof)
    for dof, value in dirichlet.items():
        initial[int(dof)] = float(value)
    initial_residual, _ = assemble_residual(
        [op], initial, None, 1.0, 1.0, op.ndof
    )
    initial_norm = (
        float(np.max(np.abs(initial_residual[free]))) if np.any(free) else 0.0
    )

    U, _, nit = newton_solve(
        [op], np.zeros(op.ndof), None, op.ndof, dirichlet, **newton_kw
    )
    final_residual, _ = assemble_residual([op], U, None, 1.0, 1.0, op.ndof)
    final_norm = float(np.max(np.abs(final_residual[free]))) if np.any(free) else 0.0
    residual_limit = max(residual_atol, residual_rtol * max(1.0, initial_norm))
    if not np.all(np.isfinite(U)) or not np.isfinite(final_norm) or final_norm > residual_limit:
        raise RuntimeError(
            "monolithic electrothermal solve did not satisfy the final residual check: "
            f"iterations={nit}, residual_norm={final_norm:.6e}, "
            f"residual_limit={residual_limit:.6e}"
        )
    return U[0::NF], U[1::NF], nit


def verify_selfheating_fe(sigma0=3.0, V0=2.0, k=1.5, L=1.0, n=48):
    """Monolithic FE element vs the exact self-heating limit dT = sigma V0^2/8k."""
    m = StructuredQuadMesh(n, 4, L, 0.2 * L)
    d = {}
    for i in m.left():
        d[NF * int(i)] = 0.0; d[NF * int(i) + 1] = 0.0      # phi=0, T=0 (cold face)
    for i in m.right():
        d[NF * int(i)] = V0; d[NF * int(i) + 1] = 0.0       # phi=V0, T=0 (cold face)
    _, T, nit = solve_coupled_et(m, sigma0=sigma0, k=k, dirichlet=d)
    peak = float(T.max())
    exact = sigma0 * V0 ** 2 / (8.0 * k)
    return peak, exact, abs(peak - exact) / exact, nit


def consistency_vs_staggered(sigma0=3.0, V0=2.0, alpha_sig=0.05, k=1.5, L=1.0, n=32):
    """Monolithic (one Newton block) == staggered Picard (two alternating solves), with the
    sigma(T) feedback on -> compares the two implementations at the selected case."""
    from .etv_solder import solve_et
    m = StructuredQuadMesh(n, 4, L, 0.2 * L)
    d = {}
    for i in m.left():
        d[NF * int(i)] = 0.0; d[NF * int(i) + 1] = 0.0
    for i in m.right():
        d[NF * int(i)] = V0; d[NF * int(i) + 1] = 0.0
    _, T_mono, nit = solve_coupled_et(m, sigma0=sigma0, alpha_sig=alpha_sig, k=k, dirichlet=d)
    Vbc = {**{int(i): 0.0 for i in m.left()}, **{int(i): V0 for i in m.right()}}
    Tbc = {**{int(i): 0.0 for i in m.left()}, **{int(i): 0.0 for i in m.right()}}
    r = solve_et(m, Vbc, sigma0=sigma0, alpha_sig=alpha_sig, k=k, T_bc=Tbc)
    T_stag = r["T"]
    rel = float(np.max(np.abs(T_mono - T_stag)) / max(1e-30, np.max(np.abs(T_stag))))
    return T_mono.max(), T_stag.max(), rel, nit


def thermoviscoplastic_cycle(
    *,
    temperature_model="lumped_transient",
    q_joule=0.0,
    g_th=8.0e6,
    Tlo_C=-40.0,
    Thi_C=125.0,
    dalpha=20.0e-6,
    ldnp_over_h=6.0,
    nx=2,
    ny=2,
    ncyc=1,
    steps_per_cyc=8,
    period=1600.0,
    maxit=30,
    p=None,
):
    """Run a partitioned SAC305 thermo-viscoplastic block demonstration.

    ``temperature_model='quasisteady'`` applies the chamber temperature plus
    the steady Joule offset.  ``'lumped_transient'`` advances one uniform local
    temperature with backward Euler and lagged inelastic-heating feedback, then
    solves the spatial mechanical equilibrium.  The latter is deliberately not
    described as a monolithic phi-T-u finite element.

    Each mechanical increment must satisfy Core's Newton residual rule before
    material state is committed.  Returned cycle ``dW`` is the sum over
    increments of the equal-volume mean of Gauss-point values over the top
    element layer.  The
    reduced feedback sets the Taylor–Quinney fraction to one: all of that
    top-layer inelastic work becomes a uniform lagged heat source.  Returned
    energy is a demonstration output, not a calibrated lifetime prediction.
    The returned ``last_cycle`` record retains the nine solved states used for
    reviewable temperature-path and deformed-mesh figures; displacements remain
    in metres and the element energy arrays remain in MPa.
    """
    from ._stateful_solve import solve_stateful_increment
    from .etv_solder import RHOC_SOLDER
    from .solder_joint import AnandPlaneStrain, SAC305_PLANE

    if temperature_model not in {"quasisteady", "lumped_transient"}:
        raise ValueError(
            "temperature_model must be 'quasisteady' or 'lumped_transient'"
        )
    if min(nx, ny, ncyc, maxit) < 1:
        raise ValueError("mesh counts, ncyc, and maxit must be positive")
    if steps_per_cyc < 2 or steps_per_cyc % 2:
        raise ValueError("steps_per_cyc must be a positive even integer")
    if g_th <= 0.0 or period <= 0.0 or q_joule < 0.0:
        raise ValueError("g_th and period must be positive; q_joule must be nonnegative")
    if Thi_C < Tlo_C:
        raise ValueError("Thi_C must be greater than or equal to Tlo_C")

    p = SAC305_PLANE if p is None else p
    H = 0.1e-3
    mesh = StructuredQuadMesh(nx, ny, H, H)
    op = AnandPlaneStrain(mesh, p)
    top = np.where(np.isclose(mesh.coords[:, 1], H))[0]
    bottom = np.where(np.isclose(mesh.coords[:, 1], 0.0))[0]
    top_elements = [
        e for e, conn in enumerate(mesh.elems)
        if np.isclose(mesh.coords[conn][:, 1].max(), H)
    ]
    TloK, ThiK = Tlo_C + 273.15, Thi_C + 273.15
    Tref = 0.5 * (TloK + ThiK)
    dt = period / steps_per_cyc
    steady_joule_offset = q_joule / g_th
    local_temperature = TloK + steady_joule_offset
    inelastic_power = 0.0
    U = np.zeros(op.ndof)
    cycle_energy = []
    cycle_element_energy = []
    temperature_history = []
    convergence = []
    last_cycle_states = []

    def boundary_conditions(gamma):
        bc = {}
        for node in bottom:
            bc[2 * int(node)] = 0.0
            bc[2 * int(node) + 1] = 0.0
        for node in top:
            bc[2 * int(node)] = gamma * H
            bc[2 * int(node) + 1] = 0.0
        return bc

    # Establish the cold-end mechanical state once. Its work initializes the
    # path and is not counted in the reported cold -> hot -> cold cycle.
    op.T = local_temperature
    op.dt = dt
    cold_gamma = dalpha * (local_temperature - Tref) * ldnp_over_h
    U, info = solve_stateful_increment(
        op, U, boundary_conditions(cold_gamma), dt=dt, maxit=maxit
    )
    convergence.append(info)
    temperature_history.append(local_temperature - 273.15)

    for cycle_index in range(ncyc):
        accumulated = 0.0
        accumulated_by_element = np.zeros(len(mesh.elems), dtype=float)
        cycle_states = [
            {
                "step": 0,
                "phase_fraction": 0.0,
                "chamber_temperature_C": float(Tlo_C),
                "local_temperature_C": float(local_temperature - 273.15),
                "displacement_m": np.asarray(U, dtype=float).tolist(),
                "increment_dW_element_MPa": np.zeros(
                    len(mesh.elems), dtype=float
                ).tolist(),
                "accumulated_dW_element_MPa": accumulated_by_element.tolist(),
            }
        ]
        for step in range(1, steps_per_cyc + 1):
            fraction = step / steps_per_cyc
            triangle = 1.0 - abs(2.0 * fraction - 1.0)
            chamber_temperature = TloK + (ThiK - TloK) * triangle
            if temperature_model == "lumped_transient":
                capacity_rate = RHOC_SOLDER / dt
                local_temperature = (
                    capacity_rate * local_temperature
                    + q_joule
                    + inelastic_power
                    + g_th * chamber_temperature
                ) / (capacity_rate + g_th)
            else:
                local_temperature = chamber_temperature + steady_joule_offset
            temperature_history.append(local_temperature - 273.15)

            gamma = dalpha * (local_temperature - Tref) * ldnp_over_h
            op.T = local_temperature
            op.dt = dt
            U, info = solve_stateful_increment(
                op, U, boundary_conditions(gamma), dt=dt, maxit=maxit
            )
            convergence.append(info)
            dW_step_by_element = np.asarray(op.dW, dtype=float).mean(axis=1)
            dW_step = float(dW_step_by_element[top_elements].mean())
            accumulated += dW_step
            accumulated_by_element += dW_step_by_element
            inelastic_power = dW_step * 1.0e6 / dt
            cycle_states.append(
                {
                    "step": step,
                    "phase_fraction": float(fraction),
                    "chamber_temperature_C": float(
                        chamber_temperature - 273.15
                    ),
                    "local_temperature_C": float(local_temperature - 273.15),
                    "displacement_m": np.asarray(U, dtype=float).tolist(),
                    "increment_dW_element_MPa": dW_step_by_element.tolist(),
                    "accumulated_dW_element_MPa": accumulated_by_element.tolist(),
                }
            )
        cycle_energy.append(accumulated)
        cycle_element_energy.append(accumulated_by_element.tolist())
        if cycle_index == ncyc - 1:
            last_cycle_states = cycle_states

    peak_state_index = max(
        range(len(last_cycle_states)),
        key=lambda index: last_cycle_states[index]["local_temperature_C"],
    )
    peak_displacement = np.asarray(
        last_cycle_states[peak_state_index]["displacement_m"], dtype=float
    )

    return {
        "temperature_model": temperature_model,
        "dW_cyc": cycle_energy,
        "dW_last": cycle_energy[-1],
        "dW_aggregation": "increment sum of equal-volume top-layer Gauss-point mean",
        "inelastic_heat_fraction": 1.0,
        "temperature_C_min": min(temperature_history),
        "temperature_C_max": max(temperature_history),
        "n_elem": int(len(mesh.elems)),
        "mesh": {
            "coordinates_m": np.asarray(mesh.coords, dtype=float).tolist(),
            "connectivity": np.asarray(mesh.elems, dtype=int).tolist(),
            "top_element_indices": [int(index) for index in top_elements],
        },
        "last_cycle": {
            "step": [int(state["step"]) for state in last_cycle_states],
            "phase_fraction": [
                float(state["phase_fraction"]) for state in last_cycle_states
            ],
            "chamber_temperature_C": [
                float(state["chamber_temperature_C"])
                for state in last_cycle_states
            ],
            "local_temperature_C": [
                float(state["local_temperature_C"])
                for state in last_cycle_states
            ],
            "displacement_m": [
                state["displacement_m"] for state in last_cycle_states
            ],
            "increment_dW_element_MPa": [
                state["increment_dW_element_MPa"]
                for state in last_cycle_states
            ],
            "accumulated_dW_element_MPa": [
                state["accumulated_dW_element_MPa"]
                for state in last_cycle_states
            ],
            "peak_temperature_state_index": int(peak_state_index),
            "peak_local_temperature_C": float(
                last_cycle_states[peak_state_index]["local_temperature_C"]
            ),
            "peak_displacement_m": peak_displacement.tolist(),
            "peak_top_edge_displacement_x_m": float(
                peak_displacement[2 * top].mean()
            ),
            "dW_element_MPa": cycle_element_energy[-1],
        },
        "max_iterations": max(i["iterations"] for i in convergence),
        "max_relative_residual": max(i["relative_residual"] for i in convergence),
        "max_residual_fraction_of_limit": max(
            i["residual_fraction_of_limit"] for i in convergence
        ),
    }


def thermoviscoplastic_comparison(**kwargs):
    """Compare the two documented temperature models at one demonstration case."""
    quasisteady = thermoviscoplastic_cycle(
        temperature_model="quasisteady", **kwargs
    )
    transient = thermoviscoplastic_cycle(
        temperature_model="lumped_transient", **kwargs
    )
    denominator = max(abs(quasisteady["dW_last"]), 1.0e-30)
    return {
        "quasisteady": quasisteady,
        "lumped_transient": transient,
        "relative_energy_difference": (
            transient["dW_last"] - quasisteady["dW_last"]
        ) / denominator,
    }


def main():
    peak, exact, err, nit = verify_selfheating_fe()
    print("Monolithic coupled electro-thermal FE element (CoupFE contract)")
    print(f"  self-heating: peak dT = {peak:.5f} vs sigma V0^2/8k = {exact:.5f}  "
          f"err {err:.1e}  ({nit} Newton iters)  {'PASS' if err < 2e-3 else 'CHECK'}")
    tm, ts, rel, nit2 = consistency_vs_staggered()
    print(f"  monolithic == staggered Picard (sigma(T) on): peak {tm:.4f} vs {ts:.4f}  "
          f"rel {rel:.1e}  (monolithic took {nit2} Newton iters)")
    print("  one block Newton system with cross-field terms supplied by the")
    print("  complex-step tangent.")
    from .etv_solder import dandu_bump, joule_density
    q_joule = joule_density(dandu_bump()["j_avg"])
    slow = thermoviscoplastic_comparison(q_joule=q_joule, ncyc=2)
    fast = thermoviscoplastic_comparison(
        q_joule=q_joule, period=1.0, ncyc=2
    )
    quasi = slow["quasisteady"]
    transient = slow["lumped_transient"]
    max_demo_iterations = max(
        case["max_iterations"]
        for result in (slow, fast)
        for case in (result["quasisteady"], result["lumped_transient"])
    )
    print("\nPartitioned SAC305 thermo-viscoplastic solder-cycle demonstration")
    print(
        f"  {quasi['n_elem']} Quad4 elements; quasisteady dW="
        f"{quasi['dW_last']:.5f} MPa, lumped-transient dW="
        f"{transient['dW_last']:.5f} MPa"
    )
    print(
        "  lumped-vs-quasisteady energy difference: "
        f"slow cycle {100.0 * slow['relative_energy_difference']:+.3f}%, "
        f"fast cycle {100.0 * fast['relative_energy_difference']:+.1f}%"
    )
    print(
        f"  all mechanical increments met Core's residual rule before commit; max Newton "
        f"iterations={max_demo_iterations}"
    )
    print("  scope: model-comparison demonstration, not monolithic phi-T-u or device validation")


if __name__ == "__main__":
    main()
