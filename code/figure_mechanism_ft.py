"""
Mechanism figure — two mini before->after slope charts contrasting the two levers:
  (1) length of SUCCESSFUL reasoning (median correct-trace tokens) = search efficiency
  (2) accuracy = reliability / fewer fatal errors

Algorithm (GLM 5.2->5.3, fixed size, matched HIGH effort) shortens the search a lot
with no accuracy gain. Scale (gpt-oss 20B->120B) shortens search modestly but raises
accuracy. Hard-but-doable-10, k=32, 40k-truncation re-scored.

    MPLBACKEND=Agg ./venv/bin/python code/figure_mechanism_ft.py
Output -> figures/figs_sept/fig_mechanism.{png,pdf}
"""
import importlib.util
import json
import os
import sys

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.lines as mlines

sys.path.insert(0, os.path.expanduser("~/.claude/skills/futuretech-charts/python"))
from futuretech_helpers import use_style, unit_formatter, save_figure
from futuretech_palette import CATEGORICAL

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("fs", os.path.join(HERE, "figures_sept.py"))
fs = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(fs)
pf = fs.pf
OUT = os.path.join(os.path.dirname(HERE), "figures", "figs_sept")
D = pf.RESULTS_DIR
HARD = "hard_but_doable_10q_k32"
CAP = 40000
ALGO_C = CATEGORICAL[1]     # MIT red — algorithm
SCALE_C = CATEGORICAL[0]    # blue — scale


def split(trials):
    c, w = [], []
    for tok, ok in trials:
        if tok < 50:
            continue
        (c if (bool(ok) and tok <= CAP) else w).append(min(tok, CAP))
    return np.array(c, float), np.array(w, float)


def glm(stem, high=True):
    suf = "_high" if high else ""
    tr = []
    for r in pf.load_rows(D / HARD / f"{stem}_thinking_benchmark_hard_but_doable_10{suf}.json"):
        tr += list(zip(r["total_completion_tokens"], r["correct"]))
    return split(tr)


def oss(sz):
    d = json.load(open(D / HARD / f"gpt-oss-{sz}_hard-but-doable-10_re-medium_k=32.json"))
    tr = [(c.get("n_tokens", 0), c.get("is_correct")) for e in d["results"] for c in e["completions"]]
    return split(tr)


def acc(c, w):
    n = len(c) + len(w)
    return 100 * len(c) / n if n else 0


g52c, g52w = glm("glm_5_2"); g53c, g53w = glm("glm_5_3")
o20c, o20w = oss("20b"); o120c, o120w = oss("120b")

# (before, after) for each mechanism
LEN = {"algo": [np.median(g52c), np.median(g53c)], "scale": [np.median(o20c), np.median(o120c)]}
ACC = {"algo": [acc(g52c, g52w), acc(g53c, g53w)], "scale": [acc(o20c, o20w), acc(o120c, o120w)]}
ALGO_LABEL = r"Algorithm  (GLM 5.2 $\rightarrow$ 5.3, fixed size)"
SCALE_LABEL = r"Scale  (gpt-oss 20B $\rightarrow$ 120B)"

use_style()
plt.rcParams.update({"axes.labelsize": 15, "xtick.labelsize": 14, "ytick.labelsize": 13,
                     "axes.titlesize": 15})
fig, (axL, axR) = plt.subplots(1, 2, figsize=(13.5, 6.2), gridspec_kw={"wspace": 0.28})
x = [0, 1]


def slope(ax, series, fmt, dy_units=1.0):
    for key, color in [("algo", ALGO_C), ("scale", SCALE_C)]:
        y = series[key]
        ax.plot(x, y, "-o", color=color, lw=3, ms=13, zorder=5)
        for xi, yi, ha, off in [(0, y[0], "right", -14), (1, y[1], "left", 14)]:
            ax.annotate(fmt(yi), (xi, yi), textcoords="offset points", xytext=(off, 0),
                        ha=ha, va="center", fontsize=13, fontweight="bold", color=color)
    ax.set_xticks(x); ax.set_xticklabels(["before", "after"])
    ax.set_xlim(-0.55, 1.55)


slope(axL, LEN, lambda v: f"{v/1e3:.1f}k")
axL.set_title("Length of successful reasoning\n(search efficiency)", fontweight="bold")
axL.set_ylabel("Median correct-trace tokens")
axL.yaxis.set_major_formatter(unit_formatter(1e3, "k"))
axL.set_ylim(0, max(max(LEN["algo"]), max(LEN["scale"])) * 1.15)

slope(axR, ACC, lambda v: f"{v:.0f}%")
axR.set_title("Accuracy\n(reliability — fewer fatal errors)", fontweight="bold")
axR.set_ylabel("Accuracy")
axR.yaxis.set_major_formatter(unit_formatter(1, "%", "{:.0f}"))
axR.set_ylim(min(min(ACC["algo"]), min(ACC["scale"])) - 3, max(max(ACC["algo"]), max(ACC["scale"])) + 3)

handles = [mlines.Line2D([], [], color=ALGO_C, lw=3, marker="o", ms=10, label=ALGO_LABEL),
           mlines.Line2D([], [], color=SCALE_C, lw=3, marker="o", ms=10, label=SCALE_LABEL)]
fig.legend(handles=handles, loc="lower center", ncol=2, fontsize=13, frameon=True,
           framealpha=0.95, bbox_to_anchor=(0.5, -0.02))
plt.tight_layout(rect=[0, 0.08, 1, 0.99])
paths = save_figure(fig, "fig_mechanism", outdir=OUT)
print("wrote", *paths, sep="\n  ")
print(f"  search len: algo {LEN['algo'][0]:.0f}->{LEN['algo'][1]:.0f}  scale {LEN['scale'][0]:.0f}->{LEN['scale'][1]:.0f}")
print(f"  accuracy:   algo {ACC['algo'][0]:.1f}->{ACC['algo'][1]:.1f}  scale {ACC['scale'][0]:.1f}->{ACC['scale'][1]:.1f}")
