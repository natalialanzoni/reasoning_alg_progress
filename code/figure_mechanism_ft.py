"""
Mechanism figure — where do reasoning-token savings come from? Two case studies,
trace-length distributions split by outcome (correct vs failed), before -> after:

  ALGORITHM  GLM 5.2 -> 5.3 (fixed size, matched HIGH effort): the whole distribution
             collapses -- correct AND failed traces get short -> more efficient SEARCH.
  SCALE      gpt-oss 20B -> 120B: the long, meandering FAILURE tail is chopped off
             (failures >20k: 43% -> 4%) while correct traces shorten only modestly
             -> fewer FATAL errors.

Split violins: left half = correct (teal), right half = failed (red). Log y (tokens),
hard-but-doable-10 k=32, 40k-truncation re-scored.

    MPLBACKEND=Agg ./venv/bin/python code/figure_mechanism_ft.py
Output -> figures/figs_sept/fig_mechanism.{png,pdf}
"""
import importlib.util
import json
import os
import sys

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.lines as mlines
import seaborn as sns

sys.path.insert(0, os.path.expanduser("~/.claude/skills/futuretech-charts/python"))
from futuretech_helpers import use_style, unit_formatter, save_figure

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("fs", os.path.join(HERE, "figures_sept.py"))
fs = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(fs)
pf = fs.pf
OUT = os.path.join(os.path.dirname(HERE), "figures", "figs_sept")
D = pf.RESULTS_DIR
HARD = "hard_but_doable_10q_k32"
CAP = 40000
C_OK = "#0E8A8A"     # correct — teal
C_BAD = "#C0392B"    # failed — red
FLOOR_C = "#E07A3F"
FLOOR = pf.canon_short


def split(trials):
    c, w = [], []
    for tok, ok in trials:
        if tok < 50:
            continue
        t = min(tok, CAP)
        (c if (bool(ok) and tok <= CAP) else w).append(t)
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


def frame(steps):
    recs = []
    for lab, (c, w) in steps:
        recs += [(lab, "correct", t) for t in c]
        recs += [(lab, "failed", t) for t in w]
    return pd.DataFrame(recs, columns=["step", "outcome", "tok"])


_g52, _g53 = glm("glm_5_2"), glm("glm_5_3")
_o20, _o120 = oss("20b"), oss("120b")
_note_algo = (f"correct search collapses\n{np.median(_g52[0])/1e3:.1f}k $\\rightarrow$ "
              f"{np.median(_g53[0])/1e3:.1f}k tok  ({np.median(_g52[0])/np.median(_g53[0]):.1f}× shorter)")
_note_scale = (f"meandering failures (>20k)\n{100*np.mean(_o20[1]>20000):.0f}% $\\rightarrow$ "
               f"{100*np.mean(_o120[1]>20000):.0f}% of failures")
PANELS = [
    (r"Algorithm  ·  GLM 5.2 $\rightarrow$ 5.3" + "\n(fixed size — more efficient search)",
     frame([("GLM 5.2", _g52), ("GLM 5.3", _g53)]), _note_algo),
    (r"Scale  ·  gpt-oss 20B $\rightarrow$ 120B" + "\n(fewer long, meandering failures)",
     frame([("20B", _o20), ("120B", _o120)]), _note_scale),
]

use_style()
plt.rcParams.update({"axes.labelsize": 15, "xtick.labelsize": 15, "ytick.labelsize": 13,
                     "axes.titlesize": 15})
fig, axes = plt.subplots(1, 2, figsize=(15, 7.6), sharey=True, gridspec_kw={"wspace": 0.08})
for ax, (title, df, note) in zip(axes, PANELS):
    sns.violinplot(data=df, x="step", y="tok", hue="outcome", split=True, gap=0.08,
                   density_norm="width", inner="quartile", cut=0, log_scale=True,
                   palette={"correct": C_OK, "failed": C_BAD}, ax=ax, legend=False)
    ax.axhline(FLOOR, color=FLOOR_C, lw=2.2, zorder=5)
    ax.set_title(title, fontweight="bold", loc="left")
    ax.set_xlabel(""); ax.set_ylabel("")
    ax.set_ylim(FLOOR * 0.82, 48000)
    ax.annotate(note, (0.5, 0.11), xycoords="axes fraction", ha="center", va="bottom",
                fontsize=12, fontweight="bold", color="#333333",
                bbox=dict(boxstyle="round,pad=0.4", fc="white", ec="#BBBBBB", alpha=0.92))
axes[0].set_ylabel("Output tokens per trace  (log)")
axes[0].yaxis.set_major_formatter(unit_formatter(1e3, "k"))
axes[0].annotate(f"minimal human derivation ≈ {FLOOR:.0f} tok", (0.03, FLOOR),
                 xycoords=("axes fraction", "data"), textcoords="offset points", xytext=(0, 4),
                 ha="left", va="bottom", fontsize=10.5, fontweight="bold", color=FLOOR_C)
handles = [mlines.Line2D([], [], color=C_OK, lw=8, label="correct trace"),
           mlines.Line2D([], [], color=C_BAD, lw=8, label="failed trace"),
           mlines.Line2D([], [], color=FLOOR_C, lw=2.2, label="minimal human derivation")]
fig.legend(handles=handles, loc="lower center", ncol=3, fontsize=13, frameon=True,
           framealpha=0.95, bbox_to_anchor=(0.5, -0.01))
plt.tight_layout(rect=[0, 0.06, 1, 1.0])
paths = save_figure(fig, "fig_mechanism", outdir=OUT)
print("wrote", *paths, sep="\n  ")
