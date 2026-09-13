"""
Figure 1 in the MIT FutureTech house style (futuretech-charts skill):
brand palette, sans-serif, despined axes, inline line labels (no legend),
natural-unit ticks, logo footer, PNG+PDF. Reuses the data helpers from
figures_sept.py.  Output -> figures/figs_sept/fig1_ft_*.{png,pdf}
"""
import importlib.util
import os
import sys
from datetime import datetime

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.lines as mlines
import matplotlib.patches as mpatches
import seaborn as sns
from matplotlib.ticker import LogLocator

sys.path.insert(0, os.path.expanduser("~/.claude/skills/futuretech-charts/python"))
from futuretech_helpers import use_style, unit_formatter, save_figure, sync_axes
from futuretech_palette import CATEGORICAL, PRIMARY

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("fs", os.path.join(HERE, "figures_sept.py"))
fs = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(fs)
pf = fs.pf
shallow_stats = fs.shallow_stats
ppt = pf.per_problem_trajectories
OUT = os.path.join(os.path.dirname(HERE), "figures", "figs_sept")
_D = pf.RESULTS_DIR

# Fable (Anthropic) — shallow-pass + hard-but-doable. RELEASE DATES PLACEHOLDER.
FABLE_SHALLOW = [
    ("Fable 5",   datetime(2026, 6, 9), _D / "fable5_shallow_pass" / "claude-fable-5_medium_thinking_benchmark.json"),
    ("Fable 5.1", datetime(2026, 9, 1), _D / "fable5.1_shallow_pass" / "claude-fable-5-1_medium_thinking_benchmark.json"),
]
FABLE_HARD = [
    ("claude-fable-5",   datetime(2026, 6, 9), _D / "hard_but_doable_10q_k32" / "claude-fable-5_medium_thinking_benchmark_hard_but_doable_10.json"),
    ("claude-fable-5-1", datetime(2026, 9, 1), _D / "hard_but_doable_10q_k32" / "claude-fable-5-1_medium_thinking_benchmark_hard_but_doable_10.json"),
]

use_style()
TOK = PRIMARY                       # deep navy — the emphasis (mean-tokens line)
ACC = "#E07A3F"                     # warm amber — accuracy (softer than MIT red)
BANDS = sns.color_palette("crest", 10)   # cohesive cool teal->navy family (not rainbow)
YCLIP = 25000                       # clip the tall outlier band so the collapse reads
# curated model labels for Figure 1 (start / peak / newest) — kept small for legibility
LABEL_MODELS = {"o3", "gpt-5", "gpt-6-astra",
                "claude-opus-4-5", "claude-opus-5", "Fable 5.1"}


def clean_label(name):
    """Human-friendly model name for the accuracy-line annotations."""
    if name.startswith("claude-opus-"):
        return "Opus " + name[len("claude-opus-"):].replace("-", ".")
    if name.startswith("claude-fable-"):
        return "Fable " + name[len("claude-fable-"):].replace("-", ".")
    if name.startswith("gpt-"):
        return "GPT-" + name[len("gpt-"):]
    return name


def panel(ax, shallow, hard, title, ymax=None, correct_only=False):
    if hard:
        hd, _, traj, band, _ = fs.valid_bands(hard, correct_only=correct_only, spread="iqr")
        hx = mdates.date2num(hd)
        for i, tid in enumerate(sorted(band)):
            c = BANDS[i % len(BANDS)]
            lo, hi = band[tid]
            ax.fill_between(hx, lo, hi, color=c, alpha=0.30, lw=0, zorder=1)
            ax.plot(hx, traj[tid], color=c, lw=1.4, alpha=0.9, zorder=2)
    d, labs, m, a = fs.valid_stats(shallow, correct_only=correct_only)
    dx = mdates.date2num(d)
    ax.plot(dx, m, color=TOK, lw=3.5, marker="o", ms=8, zorder=6)
    ax.yaxis.set_major_formatter(unit_formatter(1e3, "k"))
    ax.set_ylim(0, ymax) if ymax else ax.set_ylim(bottom=0)
    ax.annotate(f"{max(m) / m[-1]:.1f}× fewer\ntokens", xy=(0.96, 0.52),
                xycoords="axes fraction", ha="right", va="center",
                fontsize=14, fontweight="bold", color=TOK)
    ax2 = ax.twinx()
    apct = [x * 100 for x in a]
    ax2.plot(dx, apct, color=ACC, lw=1.8, ls="--", marker="D", ms=5, zorder=5, alpha=0.95)
    # label every model on the accuracy line; 3 staggered levels so dense
    # frontier clusters (3 releases bunched at the right) don't overlap
    levels = [(10, "bottom"), (-11, "top"), (24, "bottom")]
    # explicit placements for the crowded GPT frontier so it's clear what's what
    override = {"GPT-5.4": (24, "bottom"), "GPT-5.5": (10, "bottom"),
                "GPT-5.6-sol": (-12, "top"), "GPT-6-astra": (-26, "top")}
    for i, (xi, yi, name) in enumerate(zip(dx, apct, labs)):
        last, first = i == len(dx) - 1, i == 0
        ha = "right" if last else ("left" if first else "center")
        ox = -5 if last else (5 if first else 0)
        dy, va = override.get(clean_label(name), levels[i % 3])
        ax2.annotate(clean_label(name), (xi, yi), textcoords="offset points",
                     xytext=(ox, dy), ha=ha, va=va, fontsize=8,
                     fontweight="bold", color=ACC, zorder=8,
                     bbox=dict(boxstyle="round,pad=0.12", fc="white", ec="none", alpha=0.75),
                     arrowprops=dict(arrowstyle="-", color=ACC, lw=0.6, alpha=0.6,
                                     shrinkA=1, shrinkB=3))
    ax2.set_ylim(0, 118)
    ax2.yaxis.set_major_formatter(unit_formatter(1, "%", "{:.0f}"))
    ax2.set_yticks([0, 20, 40, 60, 80, 100])
    ax2.spines["right"].set_visible(True)
    ax2.spines["top"].set_visible(False)
    ax2.grid(False)
    ax.set_title(title)
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=4))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    return ax2


# Anthropic time series = Opus + Fable, combined and date-ordered (one line).
ANTH_SHALLOW = sorted(pf.OPUS_MODELS + FABLE_SHALLOW, key=lambda t: t[1])
ANTH_HARD = sorted(pf.OPUS_HARD10_K32 + FABLE_HARD, key=lambda t: t[1])
PANELS = [
    (pf.MAIN_K8, fs.GPT_HARD, "OpenAI (GPT)"),
    (ANTH_SHALLOW, ANTH_HARD, "Anthropic (Opus + Fable)"),
]
def make_figure(fname, ymax, correct_only=False):
    """ymax=None -> full data range; ymax set -> clip the tall outlier bands.
    correct_only -> token line/bands use only correct trials (accuracy unchanged)."""
    fig, axes = plt.subplots(1, 2, figsize=(15, 6.3), gridspec_kw={"wspace": 0.32})
    a2s = [panel(ax, sh, hd, t, ymax, correct_only) for ax, (sh, hd, t) in zip(axes, PANELS)]
    if ymax is None:                       # common auto scale across both panels
        ym = max(ax.get_ylim()[1] for ax in axes)
        for ax in axes:
            ax.set_ylim(0, ym)
    axes[0].set_ylabel("Mean output tokens")
    a2s[-1].set_ylabel("Accuracy")
    handles = [
        mlines.Line2D([], [], color=TOK, lw=3.5, marker="o", ms=7, label="Mean tokens per problem"),
        mlines.Line2D([], [], color=ACC, lw=1.8, ls="--", marker="D", ms=5, label="Accuracy"),
        mpatches.Patch(color=BANDS[0], alpha=0.5, label="Hard-but-doable problems (per-problem IQR)"),
    ]
    fig.legend(handles=handles, loc="lower center", ncol=3, fontsize=12,
               frameon=True, framealpha=0.95, bbox_to_anchor=(0.5, -0.03))
    title = ("Reasoning models solve the benchmark with fewer tokens each generation"
             if not correct_only else
             "Correct solves only: fewer tokens each generation (accuracy confound removed)")
    fig.suptitle(title, fontsize=16, fontweight="bold", y=1.04)
    plt.tight_layout(rect=[0, 0.05, 1, 0.97])
    return save_figure(fig, fname, outdir=OUT)   # no logo — anonymous (ICLR)


# Full data range (v1 style). Crest palette, contrast, accuracy-line labels.
p1 = make_figure("fig1_ft_frontier", ymax=None)
# success-only replicate (correct trials only) — same v1 full-range style.
p3 = make_figure("fig1_ft_frontier_success", ymax=None, correct_only=True)
print("wrote", *p1, *p3, sep="\n  ")
