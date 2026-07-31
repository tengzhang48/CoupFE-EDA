"""TSV thermal-mismatch stress: the 3D thermo-mechanical Hex8 element on a gmsh Cu/Si via.

Ties the two threads together -- generated gmsh canonical geometry (`mesh3d.via_annulus`) and the
coupled thermo-mechanical element (`thermomech_kernel`) -- into a *reliability* result: the
thermal stress from the Cu/Si CTE mismatch in a through-silicon via, validated against the exact
**plane-strain composite-cylinder** closed form (the same Lame-family oracle the project trusts
for TSV stress in 2D axisymmetric, here on a generated 3D mesh).

The neo-Hookean element at small strain reduces to linear thermo-elasticity with mu=G, lambda=K,
thermal-stress coefficient beta=K*alpha -- so the composite-cylinder oracle uses those constants:
    sigma_r = 2G eps_r + K(eps_r+eps_theta) - K*alpha*dT     (plane strain, eps_zz=0)
    u(r) = C r + D/r   (D=0 in the core),  constants from u- & sigma_r-continuity at r=a and
    sigma_r(b)=0 (traction-free wall).

    python -m eda_multiphysics.thermomech_tsv          # component checks + research-size sweep
"""
from __future__ import annotations

import os
import time

import numpy as np
import scipy.sparse.linalg as spla

from .mesh3d import min_signed_jacobian, via_annulus
from .thermomech_kernel import build_thermomech_kernel

# representative (normalized) elastic constants per material: (G=mu, K=lambda, alpha)
CU = (47.0, 137.0, 17.0e-6)     # copper-like: compliant, high thermal expansion
SI = (66.0, 98.0, 2.6e-6)       # silicon-like: stiffer, low expansion


def composite_constants(a, b, mc, ma, dT):
    Gc, Kc, ac = mc; Ga, Ka, aa = ma
    Pc, Qc, Thc = 2 * (Gc + Kc), 2 * Gc, Kc * ac * dT
    Pa, Qa, Tha = 2 * (Ga + Ka), 2 * Ga, Ka * aa * dT
    M = np.array([[1.0, -1.0, -1.0 / a ** 2],
                  [Pc, -Pa, Qa / a ** 2],
                  [0.0, Pa, -Qa / b ** 2]])
    rhs = np.array([0.0, Thc - Tha, Tha])
    Cc, Ca, Da = np.linalg.solve(M, rhs)
    return Cc, Ca, Da, (Pc, Qc, Thc, Pa, Qa, Tha)


def composite_ur(r, a, b, mc, ma, dT):
    """Exact plane-strain composite-cylinder radial displacement u_r(r)."""
    Cc, Ca, Da, _ = composite_constants(a, b, mc, ma, dT)
    return np.where(r <= a, Cc * r, Ca * r + Da / np.maximum(r, 1e-30))


def interface_radial_stress(a, b, mc, ma, dT):
    Cc, Ca, Da, (Pc, Qc, Thc, Pa, Qa, Tha) = composite_constants(a, b, mc, ma, dT)
    return Pc * Cc - Thc


def _fieldsplit_tm_solve(K, R, drows, coords, comm=None):
    """FieldSplit solve of the 4-field (u,T) Newton system. PCFIELDSPLIT splits displacement u from
    temperature T; the **u-block is GAMG seeded with the rigid-body near-null-space** (the 6 modes
    GAMG needs for elasticity, built from the node coordinates via PC.setCoordinates); the scalar
    T-block is plain GAMG. Built from the scipy CSR on COMM_SELF (SEQAIJ -> no setValuesCOO bug).
    Returns (dU, ksp_iterations)."""
    from petsc4py import PETSc
    comm = comm or PETSc.COMM_SELF
    it = PETSc.IntType
    A = PETSc.Mat().createAIJ(size=K.shape, comm=comm,
                              csr=(K.indptr.astype(it), K.indices.astype(it), K.data))
    A.assemble()
    b = PETSc.Vec().createWithArray(-np.asarray(R, float).copy(), comm=comm)
    xbc = b.duplicate(); xbc.set(0.0)
    A.zeroRowsColumns(np.asarray(drows, it), diag=1.0, x=xbc, b=b)    # symmetric Dirichlet (SPD)
    nn = len(coords); ar = np.arange(nn)
    u_idx = np.empty(3 * nn, it)
    u_idx[0::3] = 4 * ar; u_idx[1::3] = 4 * ar + 1; u_idx[2::3] = 4 * ar + 2   # node-grouped -> bs=3
    is_u = PETSc.IS().createGeneral(u_idx, comm=comm)
    is_T = PETSc.IS().createGeneral((4 * ar + 3).astype(it), comm=comm)
    ksp = PETSc.KSP().create(comm); ksp.setOperators(A)
    ksp.setType("gmres"); ksp.setTolerances(rtol=1e-9, max_it=2000)
    pc = ksp.getPC(); pc.setType("fieldsplit")
    pc.setFieldSplitIS(("u", is_u), ("T", is_T))
    pc.setFieldSplitType(PETSc.PC.CompositeType.ADDITIVE)
    ksp.setUp()
    ksp_u, ksp_T = pc.getFieldSplitSubKSP()
    ksp_u.setType("preonly"); ksp_u.getPC().setType("gamg")
    # seed the u-block GAMG with the 6 rigid-body modes (the elasticity near-null-space) -- WITHOUT
    # Historical runs showed a large iteration reduction; retain an ablation on
    # final revisions before making a mesh-independence claim.
    Au = ksp_u.getOperators()[0]
    cvec = PETSc.Vec().createWithArray(np.ascontiguousarray(coords.ravel(), float), comm=comm)
    cvec.setBlockSize(3)
    Au.setNearNullSpace(PETSc.NullSpace().createRigidBody(cvec))
    # T is fully prescribed here -> the T sub-block is the identity; GAMG can't coarsen it
    # ("max singular value zero"), so use a trivial PC. (A real conduction T-block would use gamg.)
    ksp_T.setType("preonly"); ksp_T.getPC().setType("jacobi")
    x = A.createVecLeft(); ksp.solve(b, x)
    dU = x.getArray().copy(); n = ksp.getIterationNumber()
    A.destroy(); ksp.destroy()
    return dU, n


def solve_tsv_thermal_stress(h, *, a=0.5, b=1.0, L=0.25, mc=CU, ma=SI, dT=100.0,
                             workdir=None, maxit=25, mod=None, solver="direct"):
    """Multi-material neo-Hookean (Cu core / Si annulus) thermal-mismatch solve, plane strain
    (u_z=0 on both z-faces), uniform dT, traction-free outer wall. Pass a prebuilt `mod` to skip
    recompiling. Returns (U, M, ndof, its, min_jac, t_assemble, t_solve)."""
    from coupfe import ElementGroup, assemble_residual, assemble_tangent
    from coupfe.runtime.compiled_element import CompiledElement

    M = via_annulus(a=a, b=b, L=L, h=h)
    coords = M["coords"]; ndof = len(coords) * 4
    mj = min(min_signed_jacobian(coords, M["core"]), min_signed_jacobian(coords, M["annulus"]))
    if mod is None:
        mod = build_thermomech_kernel(workdir or os.path.join(os.path.dirname(__file__), "_tm_hex"),
                                      element="Hex8")
    groups = []
    for elems, (G, K, al) in ((M["core"], mc), (M["annulus"], ma)):
        ce = CompiledElement(mod, props=(G, K, al, 1.0, 1.0), dof_per_node=4, n_svars=0, mcrd=3,
                             n_elem=len(elems))
        groups.append(ElementGroup(ce, coords, elems, dof_per_node=4, comps=(0, 1, 2, 3)))

    x, y = coords[:, 0], coords[:, 1]; r = np.hypot(x, y)
    d = {int(4 * n + 3): dT for n in range(len(coords))}            # T = dT (uniform)
    for n in np.concatenate([M["cap0"], M["capL"]]):
        d[4 * int(n) + 2] = 0.0                                     # u_z = 0 (plane strain)
    cen = int(np.argmin(r)); d[4 * cen + 0] = 0.0; d[4 * cen + 1] = 0.0   # pin centre (translation)
    cand = np.where(x > 0.9 * x.max())[0]
    rk = int(cand[np.argmin(np.abs(y[cand]))]); d[4 * rk + 1] = 0.0       # kill z-rotation
    from ._coupled_solve import coupled_newton, direct_linsolve
    if solver == "fieldsplit":
        def backend(Kc, Rr, dr):
            dU, n = _fieldsplit_tm_solve(Kc, Rr, dr, coords)
            return dU, {"ksp_its": n}
    else:
        backend = direct_linsolve
    U, n_newton, info = coupled_newton(groups, ndof, d, backend, maxit=maxit, tol=1e-12)
    return U, M, ndof, n_newton, info.get("ksp_its", 0), mj, info["t_asm"], info["t_solve"]


def _radial_disp(U, coords):
    u = U.reshape(-1, 4)[:, :3]
    r = np.hypot(coords[:, 0], coords[:, 1])
    ur = (coords[:, 0] * u[:, 0] + coords[:, 1] * u[:, 1]) / np.maximum(r, 1e-30)
    return r, ur, u[:, 2]


def profile_error(r, ur, ur_ref, *, lo=0.2, hi=0.97):
    """Robust accuracy metric: bin u_r(r) by radius over the bulk [lo,hi] and take the RMS of the
    binned-mean error / peak. (A plain max-over-nodes is dominated by a few tiny-r / edge nodes.)"""
    edges = np.linspace(lo, hi, 16)
    scale = np.max(np.abs(ur_ref))
    errs = []
    for i in range(len(edges) - 1):
        sel = (r >= edges[i]) & (r < edges[i + 1])
        if sel.sum():
            errs.append(ur[sel].mean() - ur_ref[sel].mean())
    return float(np.sqrt(np.mean(np.square(errs))) / scale)


def main():
    a, b, L, dT = 0.5, 1.0, 0.25, 100.0
    mod = build_thermomech_kernel(os.path.join(os.path.dirname(__file__), "_tm_hex"),
                                  element="Hex8")          # build ONCE; reuse across the sweep
    print("3D thermo-mechanical TSV thermal-mismatch stress (Cu core / Si annulus, gmsh all-hex)")
    print(f"  composite-cylinder oracle: interface sigma_r(a) = "
          f"{interface_radial_stress(a, b, CU, SI, dT):.5f}")
    # --- direct vs FieldSplit at one size ---
    Ud, Md, nd, _, _, _, _, td = solve_tsv_thermal_stress(0.16, a=a, b=b, L=L, dT=dT, mod=mod,
                                                          solver="direct")
    print(f"  DIRECT (SuperLU) at {nd} DOF: solve {td:.1f}s")
    # --- PCFIELDSPLIT diagnostic sweep (u: GAMG + rigid-body near-null-space; T: jacobi) ---
    print("  PCFIELDSPLIT (u-block GAMG + rigid-body modes / T-block jacobi) -- diagnostic sweep:")
    print(f"  {'h':>5} {'Hex8':>8} {'DOF':>9} {'Newton':>6} {'KSPit':>6} {'asm(s)':>7} {'solve(s)':>8} "
          f"{'u_r rel':>9} {'|u_z|':>8}", flush=True)
    for h in (0.22, 0.17, 0.13, 0.10, 0.085):
        U, M, ndof, nN, kspits, mj, t_asm, t_sol = solve_tsv_thermal_stress(
            h, a=a, b=b, L=L, dT=dT, mod=mod, solver="fieldsplit")
        r, ur, uz = _radial_disp(U, M["coords"]); ur_ref = composite_ur(r, a, b, CU, SI, dT)
        rel = profile_error(r, ur, ur_ref); ne = len(M["core"]) + len(M["annulus"])
        print(f"  {h:>5.3f} {ne:>8} {ndof:>9} {nN:>6} {kspits:>6} {t_asm:>7.1f} {t_sol:>8.1f} "
              f"{rel:>9.2e} {np.max(np.abs(uz)):>8.1e}", flush=True)
    print("  The table reports this run; archive final-revision raw output and an")
    print("  ablation before claiming mesh independence or scalability.")
    print("  u_r convergence is compared with the composite-cylinder oracle.")


if __name__ == "__main__":
    main()
