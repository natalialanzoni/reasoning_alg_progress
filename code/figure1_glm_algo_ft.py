"""
Figure 1 — open source, GLM 5.2 -> 5.3 (algorithmic progress at fixed model size).

Same house style as figure1_oss_ft, but the x axis is the two GLM versions: same
model family / size, so the token drop is pure algorithmic progress rather than a
scale effect.  Per-problem hard-but-doable IQR bands (crest), navy mean line,
amber accuracy.

GLM files are Schema A (list of per-problem dicts with parallel per-trial lists:
correct, answer_in_boxed, total_completion_tokens, response_texts, ...).

Tokens CLIPPED at 40k (some OpenRouter providers ignored the cap).  A trial counts
toward token stats only if it produced a boxed answer; accuracy uses all trials
(cap-truncated no-answers count as wrong).

    MPLBACKEND=Agg ./venv/bin/python code/figure1_glm_algo_ft.py
Output -> figures/figs_sept/fig1_glm_algo.{png,pdf}
"""
import importlib.util
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
pf = fs.pf
DATA = pf.RESULTS_DIR
OUT = os.path.join(os.path.dirname(HERE), "figures", "figs_sept")

CAP = 40000
TOK = PRIMARY
ACC = "#E07A3F"
BANDS = sns.color_palette("crest", 10)
HARD = "hard_but_doable_10q_k32"

# (label, hard-but-doable k=32 file) — same model, later algorithm
MODELS = [
    ("GLM 5.2", DATA / HARD / "glm_5_2_thinking_benchmark_hard_but_doable_10.json"),
    ("GLM 5.3", DATA / HARD / "glm_5_3_thinking_benchmark_hard_but_doable_10.json"),
]


def load_glm(path):
    """Return {problem_id: clipped answered-token array} and all-trial correctness."""
    per, correct = {}, []
    for r in pf.load_rows(path):
        tid = str(r["task_id"]); n = len(r["correct"])
        box = r.get("answer_in_boxed", [None] * n)
        texts = r.get("response_texts", [None] * n)
        vals = []
        for i, (tok, c) in enumerate(zip(r["total_completion_tokens"], r["correct"])):
            correct.append(1 if c else 0)
            answered = box[i] if box[i] is not None else \
                (tok < CAP and not (texts[i] is not None and not str(texts[i]).strip()))
            if answered and tok >= 50:
                vals.append(min(tok, CAP))
        if vals:
            per[tid] = np.array(vals, float)
    return per, correct


labels, pers, accs = [], [], []
for label, path in MODELS:
    per, correct = load_glm(path)
    labels.append(label); pers.append(per); accs.append(100 * np.mean(correct))
xs = list(range(len(MODELS)))
common = sorted(set.intersection(*[set(p) for p in pers]))

use_style()
plt.rcParams.update({"axes.labelsize": 17, "xtick.labelsize": 16, "ytick.labelsize": 16})
fig, ax = plt.subplots(figsize=(8, 6.3))

for i, tid in enumerate(common):
    c = BANDS[i % len(BANDS)]
    lo = [float(np.percentile(p[tid], 25)) for p in pers]
    hi = [float(np.percentile(p[tid], 75)) for p in pers]
    mid = [float(p[tid].mean()) for p in pers]
    ax.fill_between(xs, lo, hi, color=c, alpha=0.30, lw=0, zorder=1)
    ax.plot(xs, mid, color=c, lw=1.4, alpha=0.9, zorder=2)

means = [float(np.mean([p[t].mean() for t in common])) for p in pers]
ax.plot(xs, means, color=TOK, lw=3.5, marker="o", ms=11, zorder=6)
ax.annotate(f"{means[0] / means[-1]:.1f}× fewer\ntokens", xy=(0.5, 0.4),
            xycoords="axes fraction", ha="center", va="center",
            fontsize=18, fontweight="bold", color=TOK)

ax.set_xlim(-0.3, len(MODELS) - 0.7)
ax.set_xticks(xs); ax.set_xticklabels(labels, fontsize=16, fontweight="bold")
ax.set_xlabel("Algorithmic progress (same model size)")
ax.set_ylabel("Mean output tokens")
ax.set_ylim(0, CAP)
ax.yaxis.set_major_formatter(unit_formatter(1e3, "k"))

ax2 = ax.twinx()
ax2.plot(xs, accs, color=ACC, lw=2, ls="--", marker="D", ms=9, zorder=5)
for x, acc in zip(xs, accs):
    ax2.annotate(f"{acc:.0f}%", (x, acc), textcoords="offset points", xytext=(0, 13),
                 ha="center", va="bottom", fontsize=13, fontweight="bold", color=ACC)
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
paths = save_figure(fig, "fig1_glm_algo", outdir=OUT)
print("wrote", *paths, sep="\n  ")
