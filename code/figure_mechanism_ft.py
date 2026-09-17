"""
Mechanism figure — where do reasoning-token savings come from?
Two levers on two axes:
  x = SEARCH EFFICIENCY: how much shorter the *successful* reasoning path gets
      (ratio of median correct-trace length, before / after; >1 = shorter).
  y = RELIABILITY / fatal errors: change in accuracy (pp; >0 = fewer fatal errors).

Algorithmic progress (GLM version steps, fixed size) should move RIGHT (shorter
search) with little accuracy gain; scale (gpt-oss 20B->120B) should move UP
(fewer fatal errors). Hard-but-doable-10, k=32, 40k-truncation re-scored.

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
from futuretech_helpers import use_style, save_figure
from futuretech_palette import PRIMARY, CATEGORICAL

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


def metrics(trials):
    corr, nc, nt = [], 0, 0
    for tok, c in trials:
        if tok < 50:
            continue
        ok = bool(c) and tok <= CAP
        nt += 1; nc += int(ok)
        if ok:
            corr.append(min(tok, CAP))
    return 100 * nc / max(1, nt), float(np.median(corr)) if corr else np.nan


def glm(stem, high=False):
    suf = "_high" if high else ""
    tr = []
    for r in pf.load_rows(D / HARD / f"{stem}_thinking_benchmark_hard_but_doable_10{suf}.json"):
        tr += list(zip(r["total_completion_tokens"], r["correct"]))
    return metrics(tr)


def oss(sz):
    d = json.load(open(D / HARD / f"gpt-oss-{sz}_hard-but-doable-10_re-medium_k=32.json"))
    tr = [(c.get("n_tokens", 0), c.get("is_correct")) for e in d["results"] for c in e["completions"]]
    return metrics(tr)


def pair(before, after):
    a0, m0 = before; a1, m1 = after
    return m0 / m1, a1 - a0        # search efficiency (x shorter), Δaccuracy (pp)


# Two matched, controlled comparisons. ALGORITHM = GLM 5.2->5.3 (same size, both at
# HIGH effort). SCALE = gpt-oss 20B->120B. (Consecutive GLM default-run steps are NOT
# effort-controlled and swing wildly, so they are not comparable and omitted.)
gv = {"5_2": glm("glm_5_2", high=True), "5_3": glm("glm_5_3", high=True)}
ALGO = [(r"GLM 5.2 $\rightarrow$ 5.3", pair(gv["5_2"], gv["5_3"]))]
SCALE = [(r"gpt-oss 20B $\rightarrow$ 120B", pair(oss("20b"), oss("120b")))]

use_style()
plt.rcParams.update({"axes.labelsize": 15, "xtick.labelsize": 13, "ytick.labelsize": 13})
fig, ax = plt.subplots(figsize=(9.5, 7.5))
ax.axhline(0, color="#B0B0B0", lw=1.2, zorder=1)
ax.axvline(1, color="#B0B0B0", lw=1.2, zorder=1)

for lbl, (sx, dy) in ALGO:
    ax.scatter([sx], [dy], s=300, color=ALGO_C, zorder=5, edgecolor="white", lw=1.6, marker="o")
    ax.annotate(f"{lbl}\n{sx:.1f}× shorter · {dy:+.1f} pp", (sx, dy), textcoords="offset points",
                xytext=(-12, 10), ha="right", fontsize=12, fontweight="bold", color=ALGO_C)
for lbl, (sx, dy) in SCALE:
    ax.scatter([sx], [dy], s=300, color=SCALE_C, zorder=5, edgecolor="white", lw=1.6, marker="D")
    ax.annotate(f"{lbl}\n{sx:.1f}× shorter · {dy:+.1f} pp", (sx, dy), textcoords="offset points",
                xytext=(12, 8), ha="left", fontsize=12, fontweight="bold", color=SCALE_C)

ax.set_xlabel(r"Search efficiency  $\rightarrow$  (× shorter successful reasoning)")
ax.set_ylabel(r"Reliability  $\rightarrow$  (Δ accuracy, points)")
ax.set_title("Where the token savings come from: algorithm vs scale",
             fontsize=15, fontweight="bold", loc="left")
# quadrant hints in the empty corners
ax.annotate("more efficient search", (0.5, 0.02), xycoords="axes fraction",
            ha="center", va="bottom", fontsize=12, color=ALGO_C, style="italic")
ax.annotate("fewer\nfatal errors", (0.015, 0.5), xycoords="axes fraction", rotation=90,
            ha="left", va="center", fontsize=12, color=SCALE_C, style="italic")
xr = [p[1][0] for p in ALGO + SCALE]
dyr = [p[1][1] for p in ALGO + SCALE]
ax.set_xlim(0.9, max(xr) * 1.18)
ax.set_ylim(min(dyr) - 0.9, max(dyr) + 0.9)
handles = [mlines.Line2D([], [], color=ALGO_C, marker="o", ms=11, lw=0, label="Algorithm (fixed size, matched effort)"),
           mlines.Line2D([], [], color=SCALE_C, marker="D", ms=11, lw=0, label="Scale (model size)")]
ax.legend(handles=handles, loc="upper right", fontsize=12, frameon=True, framealpha=0.95)

paths = save_figure(fig, "fig_mechanism", outdir=OUT)
print("wrote", *paths, sep="\n  ")
for lbl, (sx, dy) in ALGO + SCALE:
    print(f"  {lbl:10s} search={sx:.2f}x  Δacc={dy:+.1f}pp")
