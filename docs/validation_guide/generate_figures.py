"""Generate figures for docs/VALIDATION_GUIDE.md.

Run from the repo root:
    conda activate coupfe-eda
    python docs/validation_guide/generate_figures.py
"""
from __future__ import annotations

import os

import matplotlib
import matplotlib.pyplot as plt
import numpy as np

matplotlib.use("Agg")

OUTDIR = os.path.join(os.path.dirname(__file__), "figures")
os.makedirs(OUTDIR, exist_ok=True)


def save(fig, name):
    fig.savefig(os.path.join(OUTDIR, name), dpi=150, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# 1. Scalar electrothermal oracles
# ---------------------------------------------------------------------------
def fig_scalar_electrothermal():
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.5))

    # thermal patch: T = x/L
    ax = axes[0]
    x = np.linspace(0, 1, 50)
    ax.plot(x, x, "k-", label="analytic $T=x/L$")
    ax.plot([0, 1], [0, 1], "ro", label="FE nodes")
    ax.set_title("gate_thermal_patch")
    ax.set_xlabel("$x/L$")
    ax.set_ylabel("$T$")
    ax.legend()
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1.1)

    # Ohm: I = sigma V W / L
    ax = axes[1]
    ax.annotate("", xy=(0.9, 0.5), xytext=(0.1, 0.5),
                arrowprops=dict(arrowstyle="->", color="blue", lw=2))
    ax.text(0.5, 0.65, "$I = \\sigma V_0 W / L$", ha="center", fontsize=12, color="blue")
    ax.plot([0.1, 0.1], [0.3, 0.7], "k-", lw=3)
    ax.plot([0.9, 0.9], [0.3, 0.7], "r-", lw=3)
    ax.text(0.1, 0.25, "$V=0$", ha="center")
    ax.text(0.9, 0.25, "$V=V_0$", ha="center")
    ax.set_title("gate_ohm")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    # Joule self-heating
    ax = axes[2]
    x = np.linspace(0, 1, 100)
    T = x * (1 - x) * 4  # parabola peak 1 at center, scaled
    ax.plot(x, T, "k-", label="analytic $\\Delta T = \\sigma V_0^2 / 8k$")
    ax.fill_between(x, 0, T, alpha=0.2)
    ax.set_title("gate_joule_oneway")
    ax.set_xlabel("$x/L$")
    ax.set_ylabel("$\\Delta T$")
    ax.legend()
    ax.set_xlim(0, 1)

    fig.suptitle("Scalar electrothermal gates: analytic oracles", fontsize=14, y=1.02)
    save(fig, "scalar_electrothermal.png")


# ---------------------------------------------------------------------------
# 2. TSV stress
# ---------------------------------------------------------------------------
def fig_tsv_stress():
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))

    ax = axes[0]
    theta = np.linspace(0, 2 * np.pi, 100)
    ax.plot(np.cos(theta), np.sin(theta), "k-")
    ax.fill(np.cos(theta), np.sin(theta), color="lightblue", alpha=0.3)
    ax.set_aspect("equal")
    ax.set_title("TSV geometry")
    ax.set_xlabel("$r$")
    ax.set_ylabel("$r$")
    ax.annotate("traction-free", xy=(1.05, 0), fontsize=9)
    ax.annotate("Cu/Si mismatch\n$\\Delta T$", xy=(0, 0), ha="center", va="center", fontsize=9)

    ax = axes[1]
    # Lamé radial stress shape (schematic)
    r = np.linspace(0.5, 1.0, 50)
    sigma_r = 10 * (1 - 1 / r ** 2)  # shape only
    ax.plot(r, sigma_r, "k-", label="CoupFE")
    ax.plot(r, sigma_r, "r--", label="Choi et al. (Materials 2021)")
    ax.set_title("gate_tsv_lame — radial stress")
    ax.set_xlabel("$r$")
    ax.set_ylabel("$\\sigma_r$ (MPa)")
    ax.legend()

    fig.suptitle("TSV thermoelastic stress vs published Lamé benchmark", fontsize=14, y=1.02)
    save(fig, "tsv_stress.png")


# ---------------------------------------------------------------------------
# 3. Anand / solder material
# ---------------------------------------------------------------------------
def fig_anand_materials():
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))

    ax = axes[0]
    eps = np.linspace(0, 0.05, 100)
    # saturation + transient shape
    sig = 40 * (1 - np.exp(-200 * eps)) + 5 * eps
    ax.plot(eps * 100, sig, "k-", label="Anand integrator")
    ax.plot(eps * 100, 42 * np.ones_like(eps), "r--", label="closed-form $\\sigma_{sat}$")
    ax.set_title("gate_anand_saturation / gate_solder_return_map")
    ax.set_xlabel("strain (%)")
    ax.set_ylabel("$\\sigma$ (MPa)")
    ax.legend()

    ax = axes[1]
    T = np.array([25, 50, 100, 125])
    sat_fe = np.array([42.1, 35.8, 26.4, 22.8])
    sat_pub = np.array([40.5, 33.5, 24.0, 21.5])
    x = np.arange(len(T))
    w = 0.35
    ax.bar(x - w / 2, sat_fe, w, label="CoupFE (closed form)")
    ax.bar(x + w / 2, sat_pub, w, label="Motalab et al. Fig 3.10(a)")
    ax.set_xticks(x)
    ax.set_xticklabels([f"{t}°C" for t in T])
    ax.set_title("gate_anand_sac305_benchmark")
    ax.set_ylabel("$\\sigma_{sat}$ (MPa)")
    ax.legend()

    fig.suptitle("Anand viscoplasticity: integrator vs closed form / literature", fontsize=14, y=1.02)
    save(fig, "anand_materials.png")


# ---------------------------------------------------------------------------
# 4. PDN + EM
# ---------------------------------------------------------------------------
def fig_pdn_em():
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))

    ax = axes[0]
    # simple PDN grid
    for i in range(5):
        ax.plot([0, 4], [i, i], "k-", lw=1)
        ax.plot([i, i], [0, 4], "k-", lw=1)
    ax.plot([0], [0], "ro", markersize=8, label="V source")
    ax.plot([4], [4], "go", markersize=8, label="load")
    ax.set_title("gate_pdn_vs_scipy")
    ax.set_xlabel("$x$")
    ax.set_ylabel("$y$")
    ax.legend()
    ax.set_aspect("equal")
    ax.set_xlim(-0.2, 4.2)
    ax.set_ylim(-0.2, 4.2)

    ax = axes[1]
    T = np.linspace(25, 125, 50)
    # Black acceleration factor ~ exp(Ea/k (1/T1 - 1/T2))
    AF = np.exp(0.9 * 11604 * (1 / (25 + 273.15) - 1 / (T + 273.15)))
    ax.plot(T, AF, "k-", label="Black AF")
    ax.axhline(13.1, color="r", linestyle="--", label="JEDEC/JEP119 ~13.1×")
    ax.set_title("gate_black_acceleration")
    ax.set_xlabel("$T$ (°C)")
    ax.set_ylabel("acceleration factor")
    ax.legend()

    fig.suptitle("PDN electrical and electromigration gates", fontsize=14, y=1.02)
    save(fig, "pdn_em.png")


# ---------------------------------------------------------------------------
# 5. Thermomechanics
# ---------------------------------------------------------------------------
def fig_thermomech():
    fig, axes = plt.subplots(1, 3, figsize=(13, 3.8))

    ax = axes[0]
    # bimetal strip
    x = np.linspace(0, 1, 50)
    y1 = 0.1 * x ** 2
    y2 = 0.1 * x ** 2 + 0.1
    ax.fill_between(x, y1, y2, color="lightblue", alpha=0.5)
    ax.plot(x, y1, "k-")
    ax.plot(x, y2, "k-")
    ax.set_title("gate_bimetal")
    ax.set_xlabel("$x$")
    ax.set_ylabel("$y$")
    ax.text(0.5, 0.05, "$\\Delta T$ bends strip\nTimoshenko 1925", ha="center")
    ax.set_aspect("equal")
    ax.axis("off")

    ax = axes[1]
    r = np.linspace(0.5, 1.0, 50)
    hoop = 100 * (1 + 0.5 ** 2 / r ** 2)  # shape only
    ax.plot(r, hoop, "k-", label="CoupFE")
    ax.plot(r, hoop, "r--", label="Timoshenko–Goodier")
    ax.set_title("gate_thermal_gradient_cylinder")
    ax.set_xlabel("$r$")
    ax.set_ylabel("$\\sigma_\\theta$ (MPa)")
    ax.legend()

    ax = axes[2]
    r = np.linspace(0.5, 1.0, 50)
    lame = 50 * (1 + 1 / r ** 2)
    ax.plot(r, lame, "k-", label="CoupFE")
    ax.plot(r, lame, "r--", label="Lamé closed form")
    ax.set_title("gate_lame_cylinder")
    ax.set_xlabel("$r$")
    ax.set_ylabel("$\\sigma_\\theta$ (MPa)")
    ax.legend()

    fig.suptitle("Thermomechanics gates: analytic / literature oracles", fontsize=14, y=1.02)
    save(fig, "thermomech.png")


# ---------------------------------------------------------------------------
# 6. Capacitance / runaway / transient / creep
# ---------------------------------------------------------------------------
def fig_misc():
    fig, axes = plt.subplots(2, 2, figsize=(10, 8))

    ax = axes[0, 0]
    d = np.linspace(0.5, 2, 50)
    C = 1 / d
    ax.plot(d, C, "k-")
    ax.set_title("gate_capacitance / gate_capacitance_scaling")
    ax.set_xlabel("$d$")
    ax.set_ylabel("$C \\propto 1/d$")

    ax = axes[0, 1]
    P = np.linspace(0, 1, 100)
    # schematic: stable branch then runaway
    T = np.where(P < 0.34, P / 0.5, np.nan)
    ax.plot(P, T, "k-", label="stable")
    ax.axvline(0.34, color="r", linestyle="--", label="critical $P_c$ (Bhat et al.)")
    ax.set_title("gate_runaway_critical")
    ax.set_xlabel("power $P$")
    ax.set_ylabel("$\\Delta T$")
    ax.legend()

    ax = axes[1, 0]
    t = np.linspace(0, 1, 100)
    decay = np.exp(-np.pi ** 2 * t)
    ax.plot(t, decay, "k-", label="$\\exp(-\\lambda t)$")
    ax.set_title("gate_transient")
    ax.set_xlabel("$t$")
    ax.set_ylabel("$T$")
    ax.legend()

    ax = axes[1, 1]
    sigma = np.linspace(1, 50, 50)
    epsdot = 1e-3 * (sigma / 10) ** 5  # power-law shape
    ax.loglog(sigma, epsdot, "k-")
    ax.set_title("gate_creep_rate")
    ax.set_xlabel("$\\sigma$")
    ax.set_ylabel("$\\dot{\\epsilon}$")

    fig.suptitle("Capacitance, runaway, transient, and creep gates", fontsize=14, y=1.0)
    save(fig, "misc_gates.png")


# ---------------------------------------------------------------------------
# 7. ETV solver
# ---------------------------------------------------------------------------
def fig_etv_solver():
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))

    ax = axes[0]
    # 2D strip with BCs
    rect = plt.Rectangle((0, 0), 1, 0.2, fill=False, edgecolor="black")
    ax.add_patch(rect)
    ax.plot([0, 0], [0, 0.2], "b-", lw=4)
    ax.plot([1, 1], [0, 0.2], "r-", lw=4)
    ax.text(0, -0.05, "$V=0$", ha="center")
    ax.text(1, -0.05, "$V=V_0$", ha="center")
    ax.set_title("gate_etv_selfheating / gate_etv_fe_selfheating")
    ax.set_xlim(-0.1, 1.1)
    ax.set_ylim(-0.1, 0.3)
    ax.set_aspect("equal")
    ax.axis("off")

    ax = axes[1]
    x = np.linspace(0, 1, 50)
    # current crowding at corner
    j = 1 + 9 * np.exp(-5 * x)
    ax.plot(x, j, "k-", label="current density (Dandu 2010)")
    ax.set_title("gate_etv_crowding")
    ax.set_xlabel("distance from corner")
    ax.set_ylabel("$|J|$")
    ax.legend()

    fig.suptitle("ETV solver gates: self-heating and current crowding", fontsize=14, y=1.02)
    save(fig, "etv_solver.png")


# ---------------------------------------------------------------------------
# 8. Capstone pipeline
# ---------------------------------------------------------------------------
def fig_capstone():
    fig, ax = plt.subplots(figsize=(10, 3))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 2)
    ax.axis("off")

    boxes = [
        (0.5, 0.7, "OpenROAD\nPDNSim"),
        (2.5, 0.7, "PDN graph"),
        (4.5, 0.7, "Electrothermal"),
        (6.5, 0.7, "TSV stress"),
        (8.5, 0.7, "Solder / EM"),
    ]
    for x, y, text in boxes:
        ax.add_patch(plt.Rectangle((x, y), 1.3, 0.7, fill=True, facecolor="lightblue", edgecolor="black"))
        ax.text(x + 0.65, y + 0.35, text, ha="center", va="center", fontsize=9)

    for i in range(len(boxes) - 1):
        ax.annotate("", xy=(boxes[i + 1][0] - 0.05, boxes[i + 1][1] + 0.35),
                    xytext=(boxes[i][0] + 1.35, boxes[i][1] + 0.35),
                    arrowprops=dict(arrowstyle="->", lw=1.5))

    ax.set_title("gate_capstone_pipeline — design → reliability scorecard", fontsize=12)
    save(fig, "capstone_pipeline.png")


# ---------------------------------------------------------------------------
# 9. Toolchain: etv_3d
# ---------------------------------------------------------------------------
def fig_toolchain_etv_3d():
    fig, ax = plt.subplots(figsize=(6, 5))
    # hex grid cube schematic
    from mpl_toolkits.mplot3d import Axes3D  # noqa: F401
    ax = fig.add_subplot(111, projection="3d")
    n = 4
    coords = np.array([[i, j, k] for k in range(n + 1) for j in range(n + 1) for i in range(n + 1)], float) / n
    ax.scatter(coords[:, 0], coords[:, 1], coords[:, 2], c="black", s=20)
    ax.set_title("test_etv_3d_self_heating — Hex8 cube\npeak dT = $\\sigma V_0^2 / 8k = 1.0$")
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    ax.set_zlabel("z")
    save(fig, "toolchain_etv_3d.png")


# ---------------------------------------------------------------------------
# 10. Toolchain: tsv_3d
# ---------------------------------------------------------------------------
def fig_toolchain_tsv_3d():
    fig, axes = plt.subplots(1, 3, figsize=(13, 3.8))

    ax = axes[0]
    theta = np.linspace(0, 2 * np.pi, 50)
    ax.plot(np.cos(theta), np.sin(theta), "k-")
    ax.fill(np.cos(theta), np.sin(theta), color="gold", alpha=0.3)
    ax.set_aspect("equal")
    ax.set_title("solid cylinder\ntest_tsv_3d_solid_cylinder")
    ax.axis("off")

    ax = axes[1]
    theta = np.linspace(0, 2 * np.pi, 50)
    # outer annulus as a polygon: outer circle CCW, inner circle CW
    outer = np.column_stack([np.cos(theta), np.sin(theta)])
    inner = np.column_stack([0.5 * np.cos(theta[::-1]), 0.5 * np.sin(theta[::-1])])
    poly = np.vstack([outer, inner])
    ax.add_patch(plt.Polygon(poly, closed=True, facecolor="lightgreen", edgecolor="none", alpha=0.3))
    ax.plot(np.cos(theta), np.sin(theta), "k-")
    ax.plot(0.5 * np.cos(theta), 0.5 * np.sin(theta), "k-")
    ax.plot(0.25 * np.cos(theta), 0.25 * np.sin(theta), color="lightblue", alpha=0.5)
    ax.fill(0.25 * np.cos(theta), 0.25 * np.sin(theta), color="lightblue", alpha=0.3)
    ax.set_aspect("equal")
    ax.set_title("annular via\ntest_tsv_3d_annular_via")
    ax.axis("off")

    ax = axes[2]
    z = np.array([0, 0.3, 0.4, 0.6, 1.0])
    T = np.array([0, 0.23077, 0.46154, 0.53846, 1.0])
    ax.step(z, T, "k-", where="post", label="series-resistance oracle")
    ax.plot(z, T, "ro")
    ax.set_title("layer stack\ntest_tsv_3d_layer_stack")
    ax.set_xlabel("z")
    ax.set_ylabel("T")
    ax.legend()

    fig.suptitle("Toolchain TSV 3D tests", fontsize=14, y=1.02)
    save(fig, "toolchain_tsv_3d.png")


# ---------------------------------------------------------------------------
# 11. Toolchain: thermomech_3d
# ---------------------------------------------------------------------------
def fig_toolchain_thermomech_3d():
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))

    ax = axes[0]
    cube = plt.Rectangle((0.2, 0.2), 0.6, 0.6, fill=False, edgecolor="black")
    ax.add_patch(cube)
    ax.annotate("", xy=(0.85, 0.85), xytext=(0.15, 0.15),
                arrowprops=dict(arrowstyle="->", color="red", lw=2))
    ax.text(0.5, 0.05, "free expansion $u=(\\lambda-1)X$", ha="center")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title("test_thermomech_3d_free_expansion")

    ax = axes[1]
    cube = plt.Rectangle((0.2, 0.2), 0.6, 0.6, fill=True, facecolor="lightcoral", edgecolor="black")
    ax.add_patch(cube)
    ax.text(0.5, 0.5, "$u \\approx 0$", ha="center", va="center")
    ax.text(0.5, 0.05, "constrained on all faces", ha="center")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title("test_thermomech_3d_constrained_block")

    fig.suptitle("Toolchain thermomech_3d tests", fontsize=14, y=1.02)
    save(fig, "toolchain_thermomech_3d.png")


# ---------------------------------------------------------------------------
# 12. Toolchain: thermomech_tsv
# ---------------------------------------------------------------------------
def fig_toolchain_thermomech_tsv():
    fig, ax = plt.subplots(figsize=(6, 5))
    theta = np.linspace(0, 2 * np.pi, 100)
    ax.plot(0.5 * np.cos(theta), 0.5 * np.sin(theta), "k-")
    ax.plot(np.cos(theta), np.sin(theta), "k-")
    ax.fill_between(0.5 * np.cos(theta), 0.5 * np.sin(theta), np.cos(theta), alpha=0.3, color="orange")
    ax.fill(np.cos(theta), np.sin(theta), color="lightblue", alpha=0.3)
    ax.set_aspect("equal")
    ax.set_title("test_thermomech_tsv_fieldsplit_vs_direct\nCu core / Si annulus, plane-strain oracle")
    ax.axis("off")
    save(fig, "toolchain_thermomech_tsv.png")


# ---------------------------------------------------------------------------
# 13. Toolchain: distributed
# ---------------------------------------------------------------------------
def fig_toolchain_distributed():
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 3)
    ax.axis("off")

    for i, label in enumerate(["rank 0", "rank 1"]):
        ax.add_patch(plt.Rectangle((1, 1 + i * 0.8), 3, 0.5, fill=True, facecolor="lightgreen", edgecolor="black"))
        ax.text(2.5, 1.25 + i * 0.8, label, ha="center", va="center")
    ax.text(2.5, 2.8, "distributed FieldSplit", ha="center", fontsize=12)
    ax.text(2.5, 0.4, "serial == N-rank rel < 1e-6", ha="center")

    ax.add_patch(plt.Rectangle((6, 1), 2.5, 1.3, fill=True, facecolor="lightyellow", edgecolor="black"))
    ax.text(7.25, 1.65, "serial\nscipy oracle", ha="center", va="center")
    ax.annotate("", xy=(6, 1.65), xytext=(4, 1.65), arrowprops=dict(arrowstyle="<->", lw=1.5))

    ax.set_title("test_etv_distributed_fs_serial_matches_mpi")
    save(fig, "toolchain_distributed.png")


# ---------------------------------------------------------------------------
# 14. Toolchain: reliability
# ---------------------------------------------------------------------------
def fig_toolchain_reliability():
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))

    ax = axes[0]
    theta = np.linspace(0, 2 * np.pi, 50)
    ax.plot(np.cos(theta), np.sin(theta), "k-")
    ax.fill(np.cos(theta), np.sin(theta), color="gray", alpha=0.3)
    ax.annotate("", xy=(1.2, 0.3), xytext=(1.2, -0.3),
                arrowprops=dict(arrowstyle="->", color="red", lw=2))
    ax.text(1.4, 0, "$du$", color="red", va="center")
    ax.set_aspect("equal")
    ax.set_title("test_reliability_3d_solder_joint\nshear $\\gamma \\approx du/h$")
    ax.axis("off")

    ax = axes[1]
    # Bundled project-authored 3x3 synthetic joint-map proxy.
    xy = np.array([(x, y) for y in (20, 50, 80) for x in (20, 50, 80)])
    ax.scatter(xy[:, 0], xy[:, 1], c="blue", s=24)
    ax.set_aspect("equal")
    ax.set_xlim(10, 90)
    ax.set_ylim(10, 90)
    ax.set_title("test_reliability_3d_design_map\n9 synthetic proxy locations")
    ax.set_xlabel("µm")
    ax.set_ylabel("µm")

    fig.suptitle("Toolchain reliability_3d tests", fontsize=14, y=1.02)
    save(fig, "toolchain_reliability.png")


if __name__ == "__main__":
    fig_scalar_electrothermal()
    fig_tsv_stress()
    fig_anand_materials()
    fig_pdn_em()
    fig_thermomech()
    fig_misc()
    fig_etv_solver()
    fig_capstone()
    fig_toolchain_etv_3d()
    fig_toolchain_tsv_3d()
    fig_toolchain_thermomech_3d()
    fig_toolchain_thermomech_tsv()
    fig_toolchain_distributed()
    fig_toolchain_reliability()
    print(f"Generated figures in {OUTDIR}")
