"""Steady closed-loop electrothermal coupling (plan Phase 5), staggered Picard.

    sigma(T) = sigma0 / (1 + alpha (T - Tref))     temperature-dependent conductance
    solve electrical:  -div(sigma(T) grad V) = 0   -> V, grad V, current
    Joule source:      Q = sigma(T) |grad V|^2
    solve thermal:     -div(k grad T) = Q          -> new T
    under-relax, repeat to convergence

Each sub-solve is a single-field linear diffusion solve on the CoupFE operator
contract (`fe.ScalarDiffusion`), so the staggered scheme is exactly the path that
would distribute over PETSc/MPI single-field today (cf. the plan/survey notes).
"""

from __future__ import annotations

import numpy as np

from .fe import (
    ScalarDiffusion,
    electrode_current,
    elem_gradients,
    solve_field,
)


def sigma_of_T(T_elem, sigma0, alpha, Tref):
    """Per-element conductivity from per-element temperature."""
    return sigma0 / (1.0 + alpha * (T_elem - Tref))


def solve_electrothermal(
    mesh,
    *,
    sigma0,
    alpha,
    k,
    Tsink,
    V0=None,
    Tref=0.0,
    relax=0.7,
    tol=1e-9,
    maxit=200,
    sigma_scale=None,
    I_inject=None,
    verbose=False,
):
    """Closed-loop steady electrothermal solve on a structured slab.

    Electrical BCs: V = V0 on the left electrode, V = 0 on the right.
    Thermal BCs:    T = Tsink on both left and right electrodes (heat sinks).
    Top/bottom are insulated (natural BC) for both fields.

    Returns a dict of fields and scalars (peak temperature, total current, history).
    """
    left, right = mesh.left(), mesh.right()
    # Voltage drive: V0 across the slab. Current drive: inject I_inject at the
    # left electrode, ground the right (the physical PDN load scenario).
    node_src = None
    if I_inject is None:
        V_bc = {**{int(n): V0 for n in left}, **{int(n): 0.0 for n in right}}
    else:
        V_bc = {int(n): 0.0 for n in right}
        node_src = np.zeros(mesh.nnode)
        node_src[left] = I_inject / len(left)
    T_bc = {**{int(n): Tsink for n in left}, **{int(n): Tsink for n in right}}
    k_elem = np.full(len(mesh.elems), float(k))
    scale = np.ones(len(mesh.elems)) if sigma_scale is None else np.asarray(sigma_scale, float)

    node_T = np.full(mesh.nnode, float(Tsink))
    history = []
    V = Q = grads = None
    for it in range(1, maxit + 1):
        T_elem = node_T[mesh.elems].mean(axis=1)
        sig = scale * sigma_of_T(T_elem, sigma0, alpha, Tref)

        V, eop, _ = solve_field(mesh, sig, None, V_bc, node_source=node_src)
        grads = elem_gradients(mesh, V)
        Q = sig * np.einsum("ij,ij->i", grads, grads)     # sigma |gradV|^2

        T_new, _, _ = solve_field(mesh, k_elem, Q, T_bc)
        T_relaxed = (1.0 - relax) * node_T + relax * T_new

        dT = float(np.max(np.abs(T_relaxed - node_T)))
        history.append(dT)
        node_T = T_relaxed
        if verbose:
            print(f"  it {it:3d}  max|dT| = {dT:.3e}  peakT = {node_T.max():.6f}")
        if dT < tol:
            break

    if I_inject is None:
        eop_final = ScalarDiffusion(
            mesh, scale * sigma_of_T(node_T[mesh.elems].mean(axis=1), sigma0, alpha, Tref), None)
        current = electrode_current(eop_final, V, left)
    else:
        current = float(I_inject)
    Vdrop = float(V[left].max() - V[right].min())   # IR drop across the slab
    return dict(
        T=node_T,
        V=V,
        Q=Q,
        gradV=grads,
        peakT=float(node_T.max()),
        current=float(current),
        Vdrop=Vdrop,
        iters=it,
        history=history,
    )
