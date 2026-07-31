"""TSV near-device observables and literature-model mobility/KOZ screening.

This module is intentionally a device *proxy* layer, not TCAD. It converts a supplied silicon
stress tensor into the (001) Raman observable and the Ryu et al. piezoresistive mobility proxy,
then preserves stable device/TSV identities for EDA back-annotation. A Lamé far-field stress helper
supports a realistic-dimension preview; it is explicitly not the release-blocking near-surface 3-D
anisotropic FE field required by the TSV validation plan.

Primary model source: Ryu et al., IEEE TDMR 12 (2012), 255-262,
doi:10.1109/TDMR.2012.2194784. Raman conversion: Jiang et al., Microelectronics Reliability 53
(2013), 53-62, doi:10.1016/j.microrel.2012.05.008.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


SI_CUBIC_STIFFNESS_GPA = (166.2, 64.4, 79.8)  # C11, C12, C44; Ryu 2012 Eq. (1)
PIEZORESISTANCE_1E11_PA_INV = {
    "n": (-102.2, 53.7, -13.6),
    "p": (6.6, -1.1, 138.1),
}  # pi11, pi12, pi44; Ryu 2012 Table I
RAMAN_MPA_PER_CM_INV = -470.0


@dataclass(frozen=True)
class DeviceScreen:
    """One stable device-site back-annotation from a supplied stress tensor."""

    device_id: str
    tsv_id: str
    x_um: float
    y_um: float
    carrier: str
    channel_degrees: float
    stress_mpa: np.ndarray
    mobility_change: float
    koz_violation: bool
    distance_um: float
    direction_degrees: float
    source_object_id: str | None = None


def _proper_rotation(rotation):
    R = np.asarray(rotation, dtype=float)
    if R.shape != (3, 3) or not np.all(np.isfinite(R)):
        raise ValueError("rotation must be a finite 3x3 matrix")
    if not np.allclose(R @ R.T, np.eye(3), atol=1.0e-12):
        raise ValueError("rotation must be orthonormal")
    if not np.isclose(np.linalg.det(R), 1.0, atol=1.0e-12):
        raise ValueError("rotation must be proper (determinant +1)")
    return R


def cubic_stiffness_tensor(c11=166.2, c12=64.4, c44=79.8):
    """Return the cubic elastic tensor ``C_ijkl`` in GPa in crystal coordinates."""
    values = np.asarray([c11, c12, c44], dtype=float)
    if not np.all(np.isfinite(values)) or np.any(values <= 0.0) or c11 <= abs(c12):
        raise ValueError("cubic stiffnesses must be finite, positive, and mechanically admissible")
    C = np.zeros((3, 3, 3, 3), dtype=float)
    for i in range(3):
        C[i, i, i, i] = c11
        for j in range(3):
            if i != j:
                C[i, i, j, j] = c12
                C[i, j, i, j] = c44
                C[i, j, j, i] = c44
    return C


def rotate_fourth_order(tensor, crystal_to_global):
    """Rotate ``C_abcd`` when ``v_global = R @ v_crystal``."""
    C = np.asarray(tensor, dtype=float)
    if C.shape != (3, 3, 3, 3) or not np.all(np.isfinite(C)):
        raise ValueError("tensor must be finite with shape (3,3,3,3)")
    R = _proper_rotation(crystal_to_global)
    return np.einsum("ia,jb,kc,ld,abcd->ijkl", R, R, R, R, C)


def stress_from_strain(strain, *, stiffness=None, alpha=2.3e-6, dT=0.0):
    """Cubic-Si thermoelastic stress in GPa for dimensionless strain and ``dT`` in kelvin."""
    eps = np.asarray(strain, dtype=float)
    if eps.shape != (3, 3) or not np.all(np.isfinite(eps)) or not np.allclose(eps, eps.T):
        raise ValueError("strain must be a finite symmetric 3x3 tensor")
    C = cubic_stiffness_tensor() if stiffness is None else np.asarray(stiffness, dtype=float)
    if C.shape != (3, 3, 3, 3) or not np.all(np.isfinite(C)):
        raise ValueError("stiffness must be finite with shape (3,3,3,3)")
    mechanical = eps - float(alpha) * float(dT) * np.eye(3)
    return np.einsum("ijkl,kl->ij", C, mechanical)


def channel_basis(channel_degrees):
    """Rows of the [channel, in-plane transverse, wafer-normal] basis in global coordinates."""
    theta = np.deg2rad(float(channel_degrees))
    c, s = np.cos(theta), np.sin(theta)
    return np.array([[c, s, 0.0], [-s, c, 0.0], [0.0, 0.0, 1.0]])


def mobility_change(stress_mpa, *, carrier="n", channel_degrees=0.0, absolute=False):
    """Ryu literature-model relative mobility change ``Δμ/μ`` from a stress tensor in MPa.

    ``channel_degrees=0`` is [100], ``45`` is [110], and ``-45`` is [1-10] on a (001) wafer.
    The signed result follows ``Δμ/μ = -Δρ/ρ``. Set ``absolute=True`` only for KOZ magnitude.
    """
    sigma = np.asarray(stress_mpa, dtype=float)
    if sigma.shape[-2:] != (3, 3) or not np.all(np.isfinite(sigma)):
        raise ValueError("stress_mpa must be finite with trailing shape (3,3)")
    if not np.allclose(sigma, np.swapaxes(sigma, -1, -2), atol=1.0e-10):
        raise ValueError("stress_mpa must be symmetric")
    carrier = str(carrier).lower()
    if carrier not in PIEZORESISTANCE_1E11_PA_INV:
        raise ValueError("carrier must be 'n' or 'p'")
    pi11, pi12, pi44 = np.asarray(PIEZORESISTANCE_1E11_PA_INV[carrier]) * 1.0e-11
    theta = np.deg2rad(float(channel_degrees))
    c2s2 = np.cos(theta) ** 2 * np.sin(theta) ** 2
    delta = pi44 + pi12 - pi11
    pi11p = pi11 + 2.0 * delta * c2s2
    pi12p = pi12 - 2.0 * delta * c2s2
    B = channel_basis(channel_degrees)
    rotated = np.einsum("ij,...jk,lk->...il", B, sigma, B)
    resistivity_change = (pi11p * rotated[..., 0, 0]
                          + pi12p * (rotated[..., 1, 1] + rotated[..., 2, 2])) * 1.0e6
    result = -resistivity_change
    return np.abs(result) if absolute else result


def raman_stress_sum_mpa(stress_mpa):
    """The (001) backscattering observable ``σ_xx + σ_yy`` in MPa."""
    sigma = np.asarray(stress_mpa, dtype=float)
    if sigma.shape[-2:] != (3, 3) or not np.all(np.isfinite(sigma)):
        raise ValueError("stress_mpa must be finite with trailing shape (3,3)")
    return sigma[..., 0, 0] + sigma[..., 1, 1]


def raman_shift_cm_inv(stress_mpa):
    """Longitudinal Raman frequency shift from ``σ_xx+σ_yy = -470 Δω``."""
    return raman_stress_sum_mpa(stress_mpa) / RAMAN_MPA_PER_CM_INV


def koz_mask(stress_mpa, *, carrier="n", channel_degrees=0.0, threshold=0.05):
    """Boolean KOZ mask for a user-selected absolute mobility-change threshold."""
    threshold = float(threshold)
    if not np.isfinite(threshold) or threshold <= 0.0:
        raise ValueError("threshold must be positive and finite")
    return mobility_change(stress_mpa, carrier=carrier, channel_degrees=channel_degrees,
                           absolute=True) >= threshold


def lame_far_field_stress(xy_um, *, diameter_um=10.0, dT=-250.0):
    """Classical axisymmetric Lamé stress tensor preview outside a Cu TSV.

    This provides a deterministic device-scale-dimension synthetic screening demo. It is not the 0.2-µm-depth
    anisotropic free-surface field and must not be used for Raman validation or release claims.
    """
    from .tsv_stress import lame_sigma_r

    xy = np.asarray(xy_um, dtype=float)
    if xy.ndim != 2 or xy.shape[1] != 2 or not np.all(np.isfinite(xy)):
        raise ValueError("xy_um must be a finite (N,2) array")
    radius = np.hypot(xy[:, 0], xy[:, 1])
    via_radius = 0.5 * float(diameter_um)
    if np.any(radius <= via_radius):
        raise ValueError("device sites must lie outside the TSV radius")
    sr = lame_sigma_r(radius, diameter_um, dT) / 1.0e6
    st = -sr
    c, s = xy[:, 0] / radius, xy[:, 1] / radius
    sigma = np.zeros((len(xy), 3, 3), dtype=float)
    sigma[:, 0, 0] = sr * c * c + st * s * s
    sigma[:, 1, 1] = sr * s * s + st * c * c
    sigma[:, 0, 1] = sigma[:, 1, 0] = (sr - st) * s * c
    return sigma


def best_channel_orientation(stress_mpa, *, carrier, allowed_degrees=(0.0, 45.0, -45.0)):
    """Choose the allowed channel orientation with the smallest absolute mobility proxy."""
    allowed = np.asarray(tuple(allowed_degrees), dtype=float)
    if allowed.ndim != 1 or not len(allowed) or not np.all(np.isfinite(allowed)):
        raise ValueError("allowed_degrees must contain finite angles")
    values = np.stack([
        mobility_change(stress_mpa, carrier=carrier, channel_degrees=angle, absolute=True)
        for angle in allowed
    ], axis=-1)
    return allowed[np.argmin(values, axis=-1)]


def screen_devices(device_ids, xy_um, stress_mpa, *, carrier="n", channel_degrees=0.0,
                   threshold=0.05, tsv_id="TSV0", tsv_xy_um=(0.0, 0.0),
                   source_object_ids=None):
    """Back-annotate stable device sites with stress, mobility proxy, and KOZ violation.

    Carrier and channel orientation may be scalars or length-N arrays. The function deliberately
    consumes stress supplied by a solver/transfer layer; it does not imply that the stress field is
    experimentally validated.
    """
    ids = tuple(str(value) for value in device_ids)
    if not ids or len(set(ids)) != len(ids) or any(not value for value in ids):
        raise ValueError("device_ids must be non-empty and unique")
    xy = np.asarray(xy_um, dtype=float)
    sigma = np.asarray(stress_mpa, dtype=float)
    n = len(ids)
    if xy.shape != (n, 2) or sigma.shape != (n, 3, 3):
        raise ValueError("xy_um and stress_mpa must have shapes (N,2) and (N,3,3)")
    if not np.all(np.isfinite(xy)) or not np.all(np.isfinite(sigma)):
        raise ValueError("xy_um and stress_mpa must be finite")
    if not np.allclose(sigma, np.swapaxes(sigma, -1, -2), atol=1.0e-10):
        raise ValueError("stress_mpa must be symmetric")
    carriers = np.full(n, str(carrier), dtype=object) if np.ndim(carrier) == 0 else np.asarray(carrier)
    angles = (np.full(n, float(channel_degrees)) if np.ndim(channel_degrees) == 0
              else np.asarray(channel_degrees, dtype=float))
    if carriers.shape != (n,) or angles.shape != (n,):
        raise ValueError("carrier and channel_degrees must be scalars or length-N arrays")
    source_ids = (np.full(n, None, dtype=object) if source_object_ids is None
                  else np.asarray(source_object_ids, dtype=object))
    if source_ids.shape != (n,) or any(value is not None and not str(value) for value in source_ids):
        raise ValueError("source_object_ids must be omitted or contain N non-empty IDs")
    threshold = float(threshold)
    if not np.isfinite(threshold) or threshold <= 0.0:
        raise ValueError("threshold must be positive and finite")
    if not str(tsv_id):
        raise ValueError("tsv_id must be non-empty")
    origin = np.asarray(tsv_xy_um, dtype=float)
    if origin.shape != (2,) or not np.all(np.isfinite(origin)):
        raise ValueError("tsv_xy_um must be a finite length-2 coordinate")
    delta = xy - origin
    rows = []
    for index in range(n):
        change = float(mobility_change(sigma[index], carrier=carriers[index],
                                       channel_degrees=angles[index]))
        rows.append(DeviceScreen(
            device_id=ids[index], tsv_id=str(tsv_id), x_um=float(xy[index, 0]),
            y_um=float(xy[index, 1]), carrier=str(carriers[index]).lower(),
            channel_degrees=float(angles[index]), stress_mpa=sigma[index].copy(),
            mobility_change=change, koz_violation=abs(change) >= threshold,
            distance_um=float(np.hypot(*delta[index])),
            direction_degrees=float(np.rad2deg(np.arctan2(delta[index, 1], delta[index, 0]))),
            source_object_id=(None if source_ids[index] is None else str(source_ids[index])),
        ))
    return rows
