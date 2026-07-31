"""Fast constitutive and extraction gates for the anisotropic local-TSV foundation."""
from __future__ import annotations

import numpy as np
import pytest


def _three_region_tets():
    # Three disconnected unit tets are acceptable here because every DOF is prescribed. The test
    # exercises assembly and material-specific stress recovery without introducing a mesh solver.
    base = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0],
                     [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
    coords = np.vstack([base + [3.0 * i, 0.0, 0.0] for i in range(3)])
    return {
        "coords": coords,
        "regions": {
            "copper": np.array([[0, 1, 2, 3]]),
            "oxide": np.array([[4, 5, 6, 7]]),
            "silicon": np.array([[8, 9, 10, 11]]),
        },
        "bottom": np.array([0, 1, 2]),
        "outer": np.array([3, 7, 11]),
    }


def test_anisotropic_voigt_has_published_cubic_entries_and_fourfold_symmetry():
    from eda_multiphysics.tsv_local_3d import DEFAULT_MATERIALS, material_voigt

    material = {
        "kind": "cubic", "C11_GPa": 166.2, "C12_GPa": 64.4, "C44_GPa": 79.8,
        "alpha_per_K": 2.3e-6,
    }
    D0, alpha = material_voigt(material)
    assert D0[0, 0] == pytest.approx(166.2e9)
    assert D0[0, 1] == pytest.approx(64.4e9)
    assert D0[3, 3] == pytest.approx(79.8e9)
    assert alpha == pytest.approx(2.3e-6)
    R90 = np.array([[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
    D90, _ = material_voigt(material, crystal_to_global=R90)
    assert np.allclose(D90, D0, rtol=1e-14, atol=1e-3)
    _Doxide, alpha_oxide = material_voigt(DEFAULT_MATERIALS["oxide"])
    assert DEFAULT_MATERIALS["oxide"]["nu"] == pytest.approx(0.16)
    assert alpha_oxide == pytest.approx(0.55e-6)


def test_tet4_affine_strain_and_material_stress_recovery():
    from eda_multiphysics.tsv_local_3d import (
        DEFAULT_MATERIALS,
        material_voigt,
        solve_local_tsv,
        tet4_B_volume,
    )

    xyz_m = np.array([[0.0, 0.0, 0.0], [1.0e-6, 0.0, 0.0],
                      [0.0, 1.0e-6, 0.0], [0.0, 0.0, 1.0e-6]])
    B, volume = tet4_B_volume(xyz_m)
    gradient = np.array([[0.01, 0.02, -0.01], [0.03, -0.02, 0.04], [0.0, 0.05, 0.01]])
    u = np.array([gradient @ point for point in xyz_m]).ravel()
    expected = np.array([0.01, -0.02, 0.01, 0.05, 0.09, -0.01])
    assert np.allclose(B @ u, expected, atol=1e-14)
    assert volume == pytest.approx(1.0e-18 / 6.0)

    mesh = _three_region_tets()
    all_fixed = {dof: 0.0 for dof in range(3 * len(mesh["coords"]))}
    result = solve_local_tsv(mesh, -100.0, dirichlet=all_fixed)
    Dsi, alpha = material_voigt(DEFAULT_MATERIALS["silicon"])
    expected_si = -Dsi @ (alpha * -100.0 * np.array([1, 1, 1, 0, 0, 0])) / 1e6
    stress = result.element_stress_mpa["silicon"][0]
    assert [stress[0, 0], stress[1, 1], stress[2, 2]] == pytest.approx(expected_si[:3])
    assert result.free_residual_relative == 0.0
    assert result.release_validation is False
    assert result.boundary_condition == "user_dirichlet"
    assert np.array_equal(result.crystal_to_global, np.eye(3))
    assert len(result.material_sha256) == len(result.mesh_sha256) == 64


def test_raman_scan_depth_and_tet_field_sampling_are_exact():
    from eda_multiphysics.tsv_local_3d import (
        element_to_nodal_field,
        gaussian_spot_quadrature,
        project_element_field_l2,
        raman_scan_points,
        sample_element_field,
        sample_nodal_field,
    )

    points = raman_scan_points([0.0, 1.0], diameter_um=10.0, oxide_um=0.4,
                               depth_um=0.2, direction=(1.0, 1.0))
    assert np.all(points[:, 2] == -0.2)
    assert np.hypot(points[0, 0], points[0, 1]) == pytest.approx(5.4)
    assert np.hypot(points[1, 0], points[1, 1]) == pytest.approx(6.4)

    coords = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0],
                       [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
    values = np.array([np.diag([10.0, 20.0, 30.0])])
    sampled, indices = sample_element_field([[0.1, 0.1, 0.1]], coords, [[0, 1, 2, 3]], values)
    assert indices.tolist() == [0]
    assert np.allclose(sampled[0], values[0])
    nodal, weights = element_to_nodal_field(coords, [[0, 1, 2, 3]], values)
    interpolated, indices = sample_nodal_field(
        [[0.1, 0.1, 0.1]], coords, [[0, 1, 2, 3]], nodal
    )
    assert np.all(weights > 0.0)
    assert indices.tolist() == [0]
    assert np.allclose(interpolated[0], values[0])
    projected, active = project_element_field_l2(coords, [[0, 1, 2, 3]], values)
    assert active.tolist() == [0, 1, 2, 3]
    assert np.allclose(projected[active], values[0])
    spot_points, spot_weights = gaussian_spot_quadrature(points, 0.1, order=3)
    assert spot_points.shape == (2, 9, 3)
    assert spot_weights.sum() == pytest.approx(1.0)
    assert np.allclose(np.einsum("q,nqk->nk", spot_weights, spot_points), points)
    assert np.all(spot_points[:, :, 2] == -0.2)


def test_local_tsv_foundation_fails_closed_on_invalid_geometry_and_extraction():
    from eda_multiphysics.tsv_local_3d import (
        raman_scan_points,
        sample_element_field,
        silicon_far_field_constraints,
    )

    with pytest.raises(ValueError, match="non-negative"):
        raman_scan_points([-0.1])
    with pytest.raises(ValueError, match="outside Tet4 field"):
        sample_element_field(
            [[2.0, 2.0, 2.0]],
            [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
            [[0, 1, 2, 3]], [1.0],
        )
    with pytest.raises(ValueError, match="positive and explicit"):
        from eda_multiphysics.tsv_local_3d import gaussian_spot_quadrature
        gaussian_spot_quadrature([[0.0, 0.0, -0.2]], 0.0)
    mesh = _three_region_tets()
    far = silicon_far_field_constraints(mesh, -100.0, alpha_per_K=2.3e-6)
    node = int(mesh["outer"][0])
    assert far[3 * node + 2] == pytest.approx(-2.3e-10)
    from eda_multiphysics.tsv_local_3d import solve_local_tsv
    with pytest.raises(ValueError, match="proper orthonormal"):
        solve_local_tsv(
            mesh, -10.0, dirichlet={dof: 0.0 for dof in range(3 * len(mesh["coords"]))},
            crystal_to_global=np.diag([1.0, 1.0, -1.0]),
        )
    with pytest.raises(ValueError, match="requires an explicit macro_gradient"):
        solve_local_tsv(mesh, -10.0, boundary_condition="periodic_macro_gradient")
