"""Distance to the human floor, by family (FutureTech house style).

Two panels on the hard-but-doable k=32 set, OpenAI left and Anthropic right, on a
shared log axis so the families are directly comparable. Each violin is the
distribution of trace length divided by that problem's MINIMAL human derivation
(L / C_j) over correct traces, so 1x means "as short as the shortest human solution
to this problem". Two human reference lines are drawn:

    solid  1x       the MINIMUM human solution   (the floor, C_j)
    dashed ~M x     the AVERAGE human solution   (median over problems of mean/min)

and the region below the floor is shaded. The newest models dip into it.

The old left panel (share of traces emitting zero thinking tokens) has been dropped.
Those statistics are still computed and printed to stdout so they can be quoted in
the text -- nothing else in the figure set reports them.

    MPLBACKEND=Agg ./venv/bin/python code/figure_latent_floor_ft.py
Output -> figures/figs_sept/fig5_latent_floor.{png,pdf}
"""
import importlib.util
import os
import sys
from datetime import datetime

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.lines as mlines
import seaborn as sns

sys.path.insert(0, os.path.expanduser("~/.claude/skills/futuretech-charts/python"))
from futuretech_helpers import use_style, save_figure
from futuretech_palette import PRIMARY, CATEGORICAL

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("fs", os.path.join(HERE, "figures_sept.py"))
fs = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(fs)
pf = fs.pf
OUT = os.path.join(os.path.dirname(HERE), "figures", "figs_sept")
D = pf.RESULTS_DIR / "hard_but_doable_10q_k32"

MIN_C = "#E07A3F"        # minimal human derivation — orange, as in figures 1 and 4
AVG_C = "#5A5A5A"        # average human solution — grey
OAI_C = CATEGORICAL[0]   # blue
ANT_C = CATEGORICAL[1]   # MIT red

# MATH-500 is excluded everywhere else, and the hard-but-doable set contains none,
# but keep the guard so the sample definition is stated rather than assumed.
KEYS = {t for t in pf.CANON_KEYS if not str(t).startswith("math_500")}


def clean(name):
    if name.startswith("claude-opus-"):  return "Opus " + name[len("claude-opus-"):].replace("-", ".")
    if name.startswith("claude-fable-"): return "Fable " + name[len("claude-fable-"):].replace("-", ".")
    if name.startswith("gpt-"):          return "GPT-" + name[len("gpt-"):]
    return name


FAB = [("claude-fable-5-1", datetime(2026, 9, 1),
        D / "claude-fable-5-1_medium_thinking_benchmark_hard_but_doable_10.json")]
FAMILIES = [
    ("OpenAI (GPT)", list(fs.GPT_HARD), OAI_C),
    ("Anthropic (Opus + Fable)", sorted(list(pf.OPUS_HARD10_K32) + FAB, key=lambda t: t[1]), ANT_C),
]


def load(path):
    """Per model: L/C_j over correct traces, plus floor-crossing and latent shares."""
    ratios, latent, latent_ok, below_min, below_avg, n = [], 0, 0, 0, 0, 0
    for r in pf.load_rows(path):
        tid = str(r["task_id"])
        if tid not in KEYS:
            continue
        cj = pf.CANON.get(tid, {}); mn, me = cj.get("min"), cj.get("mean")
        tt = r.get("thinking_tokens", [None] * len(r["correct"]))
        for tok, c, th in zip(r["total_completion_tokens"], r["correct"], tt):
            n += 1
            if th == 0:
                latent += 1; latent_ok += int(c)
            if mn and c:
                ratios.append(tok / mn)
                below_min += int(tok < mn)
                below_avg += int(bool(me) and tok < me)
    nc = max(1, len(ratios))
    return dict(ratios=np.array(ratios), n=n, n_correct=len(ratios),
                latent_pct=100 * latent / max(1, n),
                latent_ok=(100 * latent_ok / latent if latent else 0.0),
                below_min=100 * below_min / nc, below_avg=100 * below_avg / nc)


# The average human solution as a multiple of the minimum, over the problems in this
# sample (median across problems of mean/min). This is the second reference line.
_pids = [str(r["task_id"]) for r in pf.load_rows(FAMILIES[0][1][0][2])
         if str(r["task_id"]) in KEYS]
AVG_REF = float(np.median([pf.CANON[k]["mean"] / pf.CANON[k]["min"] for k in _pids]))
print(f"fig5: {len(_pids)} hard-but-doable problems; average human solution = "
      f"{AVG_REF:.2f}x the minimum")

use_style()
plt.rcParams.update({"axes.labelsize": 15, "xtick.labelsize": 13, "ytick.labelsize": 14,
                     "axes.titlesize": 16})
fig, axes = plt.subplots(1, 2, figsize=(16, 6.8), sharey=True,
                         gridspec_kw={"wspace": 0.06})

for ax, (title, models, fam_c) in zip(axes, FAMILIES):
    stats = [load(p) for _, _, p in models]
    labels = [clean(l) for l, _, _ in models]
    x = np.arange(len(models))
    # light -> dark within the family, so "newer" reads as "darker"
    ramp = sns.light_palette(fam_c, n_colors=len(models) + 2)[2:]

    ax.axhspan(1e-2, 1.0, color=MIN_C, alpha=0.10, zorder=0)      # below the floor
    ax.axhline(AVG_REF, color=AVG_C, lw=1.8, ls="--", zorder=3)   # average human
    ax.axhline(1.0, color=MIN_C, lw=2.4, zorder=4)                # minimum human

    parts = ax.violinplot([s["ratios"] for s in stats], positions=x, widths=0.82,
                          showmedians=True, showextrema=False)
    for b, c in zip(parts["bodies"], ramp):
        b.set_facecolor(c); b.set_alpha(0.75); b.set_edgecolor(fam_c); b.set_linewidth(0.8)
    parts["cmedians"].set_color(PRIMARY); parts["cmedians"].set_linewidth(2)

    for xi, s in zip(x, stats):
        if s["below_min"] >= 1:        # how much of the distribution beats the floor
            ax.annotate(f"{s['below_min']:.0f}% below", (xi, 0.62), ha="center", va="center",
                        fontsize=10, fontweight="bold", color=MIN_C, zorder=9,
                        bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.85))
        print(f"  {title.split(' (')[0]:<10s} {clean(models[xi][0]):<14s} "
              f"median {np.median(s['ratios']):6.2f}x   below-min {s['below_min']:5.1f}%   "
              f"below-avg {s['below_avg']:5.1f}%   zero-thinking {s['latent_pct']:5.1f}%")

    ax.set_yscale("log"); ax.set_ylim(0.3, 70)
    ax.set_title(title, fontweight="bold")
    ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=12, rotation=20, ha="right")
    ax.set_xlim(-0.65, len(models) - 0.35)

axes[0].set_ylabel("Trace length / minimal human derivation")
# label the two reference lines once, on the right panel where the tail is lowest
axes[1].annotate(f"average human solution (≈{AVG_REF:.1f}×)", xy=(0.015, AVG_REF),
                 xycoords=("axes fraction", "data"), textcoords="offset points",
                 xytext=(0, 5), ha="left", va="bottom", fontsize=11, fontweight="bold",
                 color=AVG_C, zorder=9,
                 bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.9))
axes[1].annotate("minimal human derivation (1×)", xy=(0.015, 1.0),
                 xycoords=("axes fraction", "data"), textcoords="offset points",
                 xytext=(0, 5), ha="left", va="bottom", fontsize=11, fontweight="bold",
                 color=MIN_C, zorder=9,
                 bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.9))
handles = [mlines.Line2D([], [], color=MIN_C, lw=2.4, label="Minimum human solution (floor)"),
           mlines.Line2D([], [], color=AVG_C, lw=1.8, ls="--", label="Average human solution")]
fig.legend(handles=handles, loc="upper center", ncol=2, fontsize=12.5,
           frameon=True, framealpha=0.95, bbox_to_anchor=(0.5, -0.01))
plt.tight_layout(pad=0.5)
paths = save_figure(fig, "fig5_latent_floor", outdir=OUT)
print("wrote", *paths, sep="\n  ")
