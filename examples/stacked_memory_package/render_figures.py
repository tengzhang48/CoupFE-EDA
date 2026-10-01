"""Render the README figures from a completed run (retained arrays only, no mock fields).

    python examples/stacked_memory_package/render_figures.py [--run runs/h0.45] [--out figures]

Needs pyvista (off-screen rendering) and matplotlib.
"""
from pathlib import Path
import argparse
import json

import numpy as np
import pyvista as pv
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
BG = "#ffffff"
INK = "#222222"
K1, K5 = "#c0392b", "#1f6fb2"
COLORS = dict(organic="#436b63", attach="#cf9868", silicon="#28556b", mold="#b8c2c6",
              copper="#ca854c", solder="#b6bdc9", top_tim="#96789f")
LOGIC = "#1f7a8c"
VIEW = np.array([30., -39., 27.])
pv.OFF_SCREEN = True
plt.rcParams.update({"text.color": INK, "axes.labelcolor": INK, "xtick.color": INK, "ytick.color": INK,
                     "axes.spines.top": False, "axes.spines.right": False, "font.size": 13,
                     "figure.facecolor": BG, "axes.facecolor": BG, "savefig.facecolor": BG})


def load(run):
    a = np.load(run / "mesh.npz")
    meta = json.loads((run / "geometry.json").read_text())
    c = a["tets"]
    grid = pv.UnstructuredGrid(np.c_[np.full(len(c), 4), c].ravel(), np.full(len(c), 10), a["points_m"] * 1e3)
    grid.cell_data["region_id"] = a["region_id"]
    return a, meta, grid


def plotter(size):
    p = pv.Plotter(off_screen=True, window_size=size)
    p.set_background(BG)
    p.enable_anti_aliasing("ssaa")
    return p


def fit_camera(p, points, size, margin=1.06):
    """Parallel projection sized so every point is inside the view."""
    points = np.asarray(points, float)
    center = (points.min(0) + points.max(0)) / 2
    f = -VIEW / np.linalg.norm(VIEW)
    r = np.cross(f, [0., 0., 1.]); r /= np.linalg.norm(r)
    u = np.cross(r, f)
    d = points - center
    scale = max(np.abs(d @ u).max(), np.abs(d @ r).max() / (size[0] / size[1])) * margin
    p.camera_position = [tuple(center + VIEW), tuple(center), (0, 0, 1)]
    p.enable_parallel_projection()
    p.camera.parallel_scale = scale


def shot(p, out, name):
    p.show(screenshot=str(out / name))
    p.close()
    print("rendered", out / name, flush=True)


def exploded(run, out):
    a, meta, g = load(run)
    size = (1500, 1100)
    p = plotter(size)
    pts = []
    for i, o in enumerate(meta["objects"]):
        name = o["id"]
        if name == "encapsulation":
            continue
        s = g.extract_cells(a["region_id"] == i).extract_surface()
        dz = 0.
        if name == "board":
            dz = -2.5
        elif name.startswith("bga."):
            dz = -1.7
        elif name == "interposer_attach":
            dz = .35
        elif name == "interposer":
            dz = .7
        elif name.startswith("memory."):
            dz = 1.4 + int(name.rsplit("_", 1)[1]) * .75
        elif name.startswith("logic."):
            dz = 1.4
        elif name == "top_tim":
            dz = 7.1
        elif name == "copper_lid":
            dz = 8.8
        s.translate((0, 0, dz), inplace=True)
        pts.append(s.points)
        p.add_mesh(s, color=LOGIC if name == "logic.die" else COLORS[o["material"]], smooth_shading=True, specular=.18)
    fit_camera(p, np.vstack(pts), size)
    p.add_text(f"90 bodies, 7 materials; {meta['elements']:,} conformal Tet4 (mold hidden, layers separated)",
               position=(30, size[1] - 50), font_size=15, color=INK)
    shot(p, out, "package_exploded.png")


def comparison(run, out):
    a, meta, g = load(run)
    objects = meta["objects"]
    rid = a["region_id"]
    visible = np.array([o["id"] not in ("encapsulation", "top_tim", "copper_lid") for o in objects])[rid]
    thermal = json.loads((run / "result.json").read_text())
    mechanics = json.loads((run / "mechanics_result.json").read_text())
    fdir = -VIEW / np.linalg.norm(VIEW)
    right = np.cross(fdir, [0, 0, 1.]); right /= np.linalg.norm(right)
    span = float(np.ptp(np.asarray(g.points) @ right)) * 1.14
    size = (2000, 950)

    def bar(fmt):
        return {"title": " ", "color": INK, "label_font_size": 16, "width": .44, "height": .05,
                "position_x": .28, "position_y": .06, "n_labels": 5, "fmt": fmt}

    p = plotter(size)
    pieces = []
    for j, case in enumerate(("baseline", "improved")):
        T = np.load(run / f"{case}_fields.npz")["temperature_C"]
        panel = g.copy()
        panel.point_data["Temperature (C)"] = T
        panel = panel.extract_cells(visible)
        panel.points = panel.points + j * span * right
        pieces.append(panel)
        p.add_mesh(panel, scalars="Temperature (C)", cmap="inferno", clim=(40, 80),
                   show_scalar_bar=(j == 0), scalar_bar_args=bar("%.0f"))
    fit_camera(p, np.vstack([q.points for q in pieces]), size, margin=1.10)
    p.add_text("Temperature (C), one scale for both; mold, TIM and lid hidden", position=(size[0] // 2 - 360, 12),
               font_size=15, color=INK)
    for j, case in enumerate(("baseline", "improved")):
        r = thermal["results"][case]
        p.add_text(f"top TIM k = {r['top_tim_k_W_mK']:.0f} W/(m K)\npeak die {r['peak_die_C']:.1f} C",
                   position=(80 + j * size[0] // 2, size[1] - 120), font_size=18, color=INK)
    shot(p, out, "thermal_comparison.png")

    amp = 300
    w, disp = [], []
    for case in ("baseline", "improved"):
        m = np.load(run / f"{case}_mechanics.npz")
        u, nodes = m["displacement_m"], m["substrate_top_nodes"]
        fit = np.linalg.lstsq(np.c_[np.ones(len(nodes)), g.points[nodes, :2]], u[nodes, 2], rcond=None)[0]
        w.append((u[:, 2] - np.c_[np.ones(len(u)), g.points[:, :2]] @ fit) * 1e6)
        disp.append(u)
    vmax = max(np.abs(v).max() for v in w)
    p = plotter(size)
    pieces = []
    for j, case in enumerate(("baseline", "improved")):
        d = g.copy()
        d.points = g.points + disp[j] * 1e3 * amp + j * span * right
        d.point_data["w (um)"] = w[j]
        panel = d.extract_cells(visible)
        pieces.append(panel)
        p.add_mesh(panel, scalars="w (um)", cmap="coolwarm", clim=(-vmax, vmax),
                   show_scalar_bar=(j == 0), scalar_bar_args=bar("%.1f"))
    fit_camera(p, np.vstack([q.points for q in pieces]), size, margin=1.10)
    p.add_text("Out-of-plane displacement after plane removal (um), one scale; deformation x300",
               position=(size[0] // 2 - 470, 12), font_size=15, color=INK)
    for j, case in enumerate(("baseline", "improved")):
        k = thermal["results"][case]["top_tim_k_W_mK"]
        v = mechanics["results"][case]["substrate_warpage_um"]
        p.add_text(f"top TIM k = {k:.0f} W/(m K)\nsubstrate warpage {v:.2f} um",
                   position=(80 + j * size[0] // 2, size[1] - 120), font_size=18, color=INK)
    shot(p, out, "warpage_comparison.png")

    fig, axs = plt.subplots(1, 3, figsize=(11, 3.6), layout="constrained")
    vals = [[thermal["results"][c]["peak_die_C"] for c in ("baseline", "improved")],
            [mechanics["results"][c]["substrate_warpage_um"] for c in ("baseline", "improved")],
            [mechanics["results"][c]["active_die_p95_vm_MPa"] for c in ("baseline", "improved")]]
    titles = ["Peak die temperature (°C)", "Substrate warpage (µm)", "Die von Mises stress, P95 (MPa)"]
    for ax, v, title in zip(axs, vals, titles):
        ax.bar([0, 1], v, color=[K1, K5], width=.55)
        ax.set_xticks([0, 1], ["TIM k = 1", "TIM k = 5"])
        ax.set_title(title, fontsize=13, pad=12)
        ax.set_ylim(0, max(v) * 1.25)
        ax.yaxis.grid(True, alpha=.15)
        ax.set_axisbelow(True)
        for i, x in enumerate(v):
            ax.text(i, x + max(v) * .035, f"{x:.2f}" if max(v) < 10 else f"{x:.1f}", ha="center", fontsize=14, weight="bold")
    fig.savefig(out / "metrics.png", dpi=150)
    plt.close(fig)
    print("rendered", out / "metrics.png", flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", type=Path, default=HERE / "runs" / "h0.45")
    ap.add_argument("--out", type=Path, default=HERE / "figures")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    exploded(a.run, a.out)
    comparison(a.run, a.out)


if __name__ == "__main__":
    main()
