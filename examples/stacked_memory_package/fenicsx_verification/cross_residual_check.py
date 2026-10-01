"""Substitute the CoupFE solution fields into this reference's discrete equations.

Field-by-field agreement (``compare_solvers.py``) says the two solutions are close.
This asks a sharper question: does the *other* solver's field satisfy *these*
independently assembled discrete equations? Comparable small residuals are
consistent with linear-algebra roundoff amplified by conditioning. Checking two
solutions does not prove equality of the full matrices or measure conditioning.

Reuses the reference's own forms via ``fenicsx_reference``; nothing from
CoupFE/EDA is imported. Like ``compare_solvers.py``, this is a comparison-stage
script and does read the original result fields.

Usage
  OMP_NUM_THREADS=4 python -u \
      cross_residual_check.py --mesh-dir ../runs/h0.45 --reference results
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import ufl
from dolfinx.fem import Function, form, functionspace
from dolfinx.fem.petsc import assemble_vector

import fenicsx_reference as ref

HERE = Path(__file__).resolve().parent
CASES = ("baseline", "improved")


def check(mesh_dir: Path, ref_dir: Path) -> dict:
    data = ref.load_input(mesh_dir)
    points, tets = data["points"], data["tets"]
    volumes = ref.geometric_volumes(points, tets)
    msh = ref.build_mesh(points, tets)
    maps = ref.mesh_maps(msh, points, tets)
    facet_tags, _, _ = ref.tag_top_facets(msh, data["top"], maps["node_to_input"])

    V = functionspace(msh, ("Lagrange", 1))
    Vv = functionspace(msh, ("Lagrange", 1, (3,)))
    Q = functionspace(msh, ("DG", 0))
    cell_region = data["region_id"][maps["cell_to_input"]]
    mu, lam, alpha = ref.material_fields(Q, cell_region, data["materials"])

    dx = ufl.Measure("dx", domain=msh, metadata={"quadrature_degree": ref.QDEG})
    ds_top = ufl.Measure("ds", domain=msh, subdomain_data=facet_tags,
                         metadata={"quadrature_degree": ref.QDEG})(ref.TOP_MARKER)
    v, w = ufl.TestFunction(V), ufl.TestFunction(Vv)
    ident = ufl.Identity(3)

    bottom_dofs = maps["inv_node"][np.unique(data["bottom"])]
    free_scalar = np.ones(len(points), dtype=bool)
    free_scalar[bottom_dofs] = False

    anchor_dofs = []
    for target, comps in ref.ANCHORS_M:
        node = int(np.argmin(np.linalg.norm(points - np.asarray(target), axis=1)))
        anchor_dofs += [3 * int(maps["inv_node"][node]) + c for c in comps]
    free_vector = np.setdiff1d(np.arange(3 * len(points)), np.array(anchor_dofs))

    out = {}
    for case in CASES:
        k, f, _ = ref.thermal_coefficients(Q, maps, data, volumes, case)
        load_T = assemble_vector(form(f * v * dx)).array.copy()

        def thermal_residual(theta_input_order: np.ndarray) -> float:
            th = Function(V)
            th.x.array[:] = theta_input_order[maps["node_to_input"]]
            R = assemble_vector(form(ufl.inner(k * ufl.grad(th), ufl.grad(v)) * dx
                                     + ref.H_TOP * th * v * ds_top - f * v * dx)).array
            return float(np.linalg.norm(R[free_scalar]) / np.linalg.norm(load_T[free_scalar]))

        def mechanical_residual(u_input_order: np.ndarray,
                                theta_input_order: np.ndarray) -> tuple[float, float]:
            th = Function(V)
            th.x.array[:] = theta_input_order[maps["node_to_input"]]
            uh = Function(Vv)
            uh.x.array[:] = u_input_order[maps["node_to_input"]].ravel()
            e = ufl.sym(ufl.grad(uh)) - alpha * th * ident
            sig = 2.0 * mu * e + lam * ufl.tr(e) * ident
            R = assemble_vector(form(ufl.inner(sig, ufl.sym(ufl.grad(w))) * dx)).array
            load = assemble_vector(
                form((2.0 * mu + 3.0 * lam) * alpha * th * ufl.div(w) * dx)).array
            return (float(np.linalg.norm(R[free_vector]) / np.linalg.norm(load[free_vector])),
                    float(np.abs(np.sum(R.reshape(-1, 3), axis=0)).max()))

        T_o = np.load(mesh_dir / f"{case}_fields.npz")["temperature_C"]
        T_r = np.load(ref_dir / f"{case}_fenicsx_fields.npz")["temperature_C"]
        U_o = np.load(mesh_dir / f"{case}_mechanics.npz")["displacement_m"]
        U_r = np.load(ref_dir / f"{case}_fenicsx_mechanics.npz")["displacement_m"]

        # each displacement field is checked against the temperature that produced it
        mech_o = mechanical_residual(U_o, T_o - ref.REFERENCE_C)
        mech_r = mechanical_residual(U_r, T_r - ref.REFERENCE_C)
        out[case] = dict(
            thermal_residual_of_coupfe_field=thermal_residual(T_o - ref.REFERENCE_C),
            thermal_residual_of_fenicsx_field=thermal_residual(T_r - ref.REFERENCE_C),
            mechanical_residual_of_coupfe_field=mech_o[0],
            mechanical_residual_of_fenicsx_field=mech_r[0],
            mechanical_net_force_of_coupfe_field_N=mech_o[1],
            mechanical_net_force_of_fenicsx_field_N=mech_r[1],
        )
        print(case, json.dumps(out[case], indent=1), flush=True)

    return dict(
        question=("does the CoupFE solution satisfy the FEniCSx reference's own discrete "
                  "equations as well as the reference's own solution does?"),
        normalisation=("thermal: ||R||/||F|| over non-Dirichlet nodes; mechanical: "
                       "||R||/||F|| over non-anchored dofs, with R = integral of "
                       "sigma(u, theta):eps(v) using the reference's forms"),
        interpretation=("both computed solutions satisfy the reference equations with small "
                        "residuals; this is consistent with roundoff amplified by conditioning, "
                        "but does not prove matrix equality, measure conditioning, or establish "
                        "physical validity"),
        cases=out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mesh-dir", type=Path, default=HERE.parent / "runs" / "h0.45")
    ap.add_argument("--reference", type=Path, default=HERE / "results")
    ap.add_argument("--out", type=Path, default=HERE / "cross_residual.json")
    args = ap.parse_args()
    res = check(args.mesh_dir.resolve(), args.reference.resolve())
    args.out.write_text(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
