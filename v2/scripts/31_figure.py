r"""Figure 2: declared floor against the floor the code supports, both frames (v2/results/figure_data.json).

Each cell is a (declared floor, detected floor) pair; area is proportional to the number of projects.
Blue circles: the code is consistent with the declared floor (on or below the diagonal). Orange
squares with a count: confirmed contradictions (detected above declared). The shape carries the
distinction as well as the colour. Detected floors at or below 3.4 share one row, since 3.4 is the
oldest interpreter tested.

    py v2/scripts/31_figure.py
"""
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

V2 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
d = json.load(open(os.path.join(V2, "results", "figure_data.json"), encoding="utf-8"))
BLUE, ORANGE, INK, MUTED = "#2a78d6", "#eb6834", "#1f1f1e", "#8a897f"
plt.rcParams.update({"font.size": 8, "font.family": "serif", "axes.edgecolor": MUTED,
                     "axes.labelcolor": INK, "xtick.color": INK, "ytick.color": INK})

fig, axes = plt.subplots(1, 2, figsize=(7.0, 3.3), sharey=True)
for ax, F, title in ((axes[0], "U", "Uniform sample of the index"),
                     (axes[1], "P", "1,000 most-downloaded projects")):
    cells = {tuple(map(int, k.split(","))): v for k, v in d[F].items()}
    conf = {}
    for k in d[F + "_confirmed"]:
        t = tuple(map(int, k.split(",")))
        conf[t] = conf.get(t, 0) + 1
    xs = sorted({x for x, _ in cells})
    for (x, y), n in cells.items():
        y = max(y, 4)
        c = conf.get((x, y), 0)
        if n - c > 0:
            ax.scatter(x, y, s=6 + 9 * (n - c) ** 0.75, color=BLUE, alpha=0.75,
                       edgecolors="white", linewidths=1.0, zorder=2)
        if c:
            ax.scatter(x, y, s=34 + 9 * c ** 0.75, marker="s", color=ORANGE,
                       edgecolors="white", linewidths=1.0, zorder=3)
            ax.annotate(str(c), (x, y), xytext=(5, 4), textcoords="offset points",
                        fontsize=7, color=INK, zorder=4)
    lo, hi = 0, 15
    ax.plot([4, hi], [4, hi], color=MUTED, lw=0.8, ls="--", zorder=1)
    ax.set_xlim(lo - 0.5, hi + 0.5)
    ax.set_ylim(3.5, 14.5)
    ax.set_xticks(range(0, 16, 2))
    ax.set_xticklabels(["3.%d" % v for v in range(0, 16, 2)])
    ax.set_yticks(range(4, 15, 2))
    ax.set_yticklabels(["≤3.4"] + ["3.%d" % v for v in range(6, 15, 2)])
    ax.set_title(title, fontsize=8.5, color=INK)
    ax.set_xlabel("declared floor (Requires-Python)")
    ax.grid(color="#e6e5df", lw=0.5, zorder=0)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
axes[0].set_ylabel("floor the code supports (detected)")
h1 = axes[1].scatter([], [], s=40, color=BLUE, alpha=0.75, label="consistent with the declared floor")
h2 = axes[1].scatter([], [], s=40, marker="s", color=ORANGE, label="confirmed contradiction (count)")
fig.legend(handles=[h1, h2], loc="lower center", ncol=2, frameon=False, fontsize=7.5)
fig.tight_layout(rect=(0, 0.07, 1, 1))
out = os.path.join(V2, "draft", "fig_floors.pdf")
fig.savefig(out)
fig.savefig(out.replace(".pdf", ".png"), dpi=200)
print("written", out)
