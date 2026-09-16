"""
Figure 1 — open source (gpt-oss), FutureTech house style, fig1-style shading.

The two graded open-weight models with hard-but-doable k=32 data: gpt-oss-20b and
gpt-oss-120b.  X axis is model PARAMETERS (not time) -> a size-scaling view.
Per-problem hard-but-doable IQR bands (one crest color per problem) shade the
background exactly like the time-series Figure 1; the navy line is the mean over
problems, amber dashed is accuracy.

Schema B (local GPU harness): top-level dict with `results`; each result is one
problem with `id` and a `completions` list of
{n_tokens, finish_reason, extracted_answer, is_correct}.

Tokens are CLIPPED at 40k for comparability with the 40k-capped GPT/Opus runs.
A trial counts toward token stats only if it produced an answer (not a
length-truncation); accuracy uses all trials (truncations count as wrong).

    MPLBACKEND=Agg ./venv/bin/python code/figure1_oss_ft.py
Output -> figures/figs_sept/fig1_oss.{png,pdf}
"""
import importlib.util
import json
import os
import sys

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.lines as mlines
import matplotlib.patches as mpatches
import seaborn as sns

sys.path.insert(0, os.path.expanduser("~/.claude/skills/futuretech-charts/python"))
from futuretech_helpers import use_style, unit_formatter, save_figure
from futuretech_palette import PRIMARY

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("fs", os.path.join(HERE, "figures_sept.py"))
fs = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(fs)
DATA = fs.pf.RESULTS_DIR
OUT = os.path.join(os.path.dirname(HERE), "figures", "figs_sept")

CAP = 40000
TOK = PRIMARY
ACC = "#E07A3F"
BANDS = sns.color_palette("crest", 10)
HARD = "hard_but_doable_10q_k32"

# (label, params in billions, hard-but-doable k=32 file) — Schema B
MODELS = [
    ("gpt-oss-20b",  20,  DATA / HARD / "gpt-oss-20b_hard-but-doable-10_re-medium_k=32.json"),
    ("gpt-oss-120b", 120, DATA / HARD / "gpt-oss-120b_hard-but-doable-10_re-medium_k=32.json"),
]


def load_oss(path):
    """Return {problem_id: clipped answered-token array} and all-trial correctness."""
    d = json.load(open(path))
    per, correct = {}, []
    for e in d["results"]:
        vals = []
        for c in e.get("completions", []):
            tok = c.get("n_tokens", 0)
            correct.append(1 if c.get("is_correct") else 0)
            answered = c.get("finish_reason") != "length" and \
                str(c.get("extracted_answer") or "").strip() != ""
            if answered and tok >= 50:
                vals.append(min(tok, CAP))
        if vals:
            per[str(e["id"])] = np.array(vals, float)
    return per, correct


xs, labels, pers, accs = [], [], [], []
for label, params, path in MODELS:
    per, correct = load_oss(path)
    xs.append(params); labels.append(label); pers.append(per)
    accs.append(100 * np.mean(correct))

common = sorted(set.intersection(*[set(p) for p in pers]))

use_style()
plt.rcParams.update({"axes.labelsize": 17, "xtick.labelsize": 16, "ytick.labelsize": 16})
fig, ax = plt.subplots(figsize=(8.5, 6.3))

# per-problem IQR bands + faint trajectory, one crest color per problem
for i, tid in enumerate(common):
    c = BANDS[i % len(BANDS)]
    lo = [float(np.percentile(p[tid], 25)) for p in pers]
    hi = [float(np.percentile(p[tid], 75)) for p in pers]
    mid = [float(p[tid].mean()) for p in pers]
    ax.fill_between(xs, lo, hi, color=c, alpha=0.30, lw=0, zorder=1)
    ax.plot(xs, mid, color=c, lw=1.4, alpha=0.9, zorder=2)

# mean over problems (macro), navy
means = [float(np.mean([p[t].mean() for t in common])) for p in pers]
ax.plot(xs, means, color=TOK, lw=3.5, marker="o", ms=11, zorder=6)
ax.annotate(f"{means[0] / means[-1]:.1f}× fewer\ntokens", xy=(0.96, 0.52),
            xycoords="axes fraction", ha="right", va="center",
            fontsize=18, fontweight="bold", color=TOK)

ax.set_xscale("log")
ax.set_xlim(14, 175)
ax.set_xticks(xs); ax.set_xticklabels([f"{p}B" for p in xs])
ax.xaxis.set_minor_locator(plt.NullLocator())
ax.set_xlabel("Model parameters")
ax.set_ylabel("Mean output tokens")
band_top = max(np.percentile(p[tid], 75) for tid in common for p in pers)
ax.set_ylim(0, band_top * 1.08)     # fit the data; no wasted space up to 40k
ax.yaxis.set_major_formatter(unit_formatter(1e3, "k"))

ax2 = ax.twinx()
ax2.plot(xs, accs, color=ACC, lw=2, ls="--", marker="D", ms=9, zorder=5)
# model names on the accuracy line (fig1 format)
for i, (x, acc, name) in enumerate(zip(xs, accs, labels)):
    ha = "left" if i == 0 else "right"
    ox = 6 if i == 0 else -6
    ax2.annotate(name, (x, acc), textcoords="offset points", xytext=(ox, 11),
                 ha=ha, va="bottom", fontsize=13, fontweight="bold", color=ACC,
                 bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.75))
ax2.set_ylim(0, 118)
ax2.set_ylabel("Accuracy")
ax2.yaxis.set_major_formatter(unit_formatter(1, "%", "{:.0f}"))
ax2.set_yticks([0, 20, 40, 60, 80, 100])
ax2.spines["right"].set_visible(True); ax2.spines["top"].set_visible(False); ax2.grid(False)

handles = [
    mlines.Line2D([], [], color=TOK, lw=3.5, marker="o", ms=9, label="Mean tokens per problem"),
    mlines.Line2D([], [], color=ACC, lw=2, ls="--", marker="D", ms=8, label="Accuracy"),
    mpatches.Patch(color=BANDS[0], alpha=0.5, label="Hard-but-doable problems (per-problem IQR)"),
]
fig.legend(handles=handles, loc="lower center", ncol=3, fontsize=14,
           frameon=True, framealpha=0.95, bbox_to_anchor=(0.5, -0.03))
plt.tight_layout(rect=[0, 0.06, 1, 0.99])
paths = save_figure(fig, "fig1_oss", outdir=OUT)
print("wrote", *paths, sep="\n  ")
