"""
Figure 3 (FutureTech house style): the token/accuracy Pareto.

Each model is a point at (accuracy, mean output tokens); generations are joined by
arrows in release order.  Down-and-right = strictly better (fewer tokens, more
accurate).  Reveals whether a generation bought efficiency for free (moves down,
holds/gains accuracy) or traded accuracy for it (moves down-LEFT).

    MPLBACKEND=Agg ./venv/bin/python code/figure3_pareto_ft.py
Output -> figures/figs_sept/fig3_pareto.{png,pdf}
"""
import importlib.util
import os
import sys
from datetime import datetime

import numpy as np
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.expanduser("~/.claude/skills/futuretech-charts/python"))
from futuretech_helpers import use_style, unit_formatter, save_figure
from futuretech_palette import CATEGORICAL

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("fs", os.path.join(HERE, "figures_sept.py"))
fs = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(fs)
pf = fs.pf
OUT = os.path.join(os.path.dirname(HERE), "figures", "figs_sept")
_D = pf.RESULTS_DIR

FABLE_SHALLOW = [
    ("Fable 5.1", datetime(2026, 9, 1), _D / "fable5.1_shallow_pass" / "claude-fable-5-1_medium_thinking_benchmark.json"),
]
ANTH_SHALLOW = sorted(pf.OPUS_MODELS + FABLE_SHALLOW, key=lambda t: t[1])

OAI_C = CATEGORICAL[0]     # blue
ANT_C = CATEGORICAL[1]     # MIT red


def clean_label(name):
    if name.startswith("claude-opus-"):
        return "Opus " + name[len("claude-opus-"):].replace("-", ".")
    if name.startswith("claude-fable-"):
        return "Fable " + name[len("claude-fable-"):].replace("-", ".")
    if name.startswith("gpt-"):
        return "GPT-" + name[len("gpt-"):]
    return name


def series(ax, model_files, color, family):
    d, labs, m, a = fs.valid_stats(model_files)
    x = [v * 100 for v in a]; y = m
    ax.plot(x, y, "-", color=color, lw=1.3, alpha=0.5, zorder=2)
    for i in range(len(x) - 1):                 # direction arrows between generations
        ax.annotate("", xy=(x[i + 1], y[i + 1]), xytext=(x[i], y[i]),
                    arrowprops=dict(arrowstyle="->", color=color, lw=1.3, alpha=0.6), zorder=3)
    ax.scatter(x, y, s=90, color=color, zorder=5, edgecolor="white", linewidth=1.2,
               label=family)
    for xi, yi, name in zip(x, y, labs):
        ax.annotate(clean_label(name), (xi, yi), textcoords="offset points",
                    xytext=(6, 6), fontsize=12, fontweight="bold", color=color, zorder=6)
    return x, y


use_style()
plt.rcParams.update({"axes.labelsize": 17, "xtick.labelsize": 16, "ytick.labelsize": 16})
fig, ax = plt.subplots(figsize=(11, 7.5))
series(ax, pf.MAIN_K8, OAI_C, "OpenAI (GPT)")
series(ax, ANTH_SHALLOW, ANT_C, "Anthropic (Opus + Fable)")

ax.set_xlabel("Accuracy")
ax.set_ylabel("Mean output tokens")
ax.xaxis.set_major_formatter(unit_formatter(1, "%", "{:.0f}"))
ax.yaxis.set_major_formatter(unit_formatter(1e3, "k"))
ax.set_ylim(bottom=0)
# "better" corner cue
ax.annotate("more efficient  +  more accurate", xy=(0.98, 0.03), xycoords="axes fraction",
            ha="right", va="bottom", fontsize=13, style="italic", color="#666666")
ax.legend(loc="upper left", frameon=True, framealpha=0.95, fontsize=14)
# never include titles — captions live in the paper
plt.tight_layout(rect=[0, 0, 1, 1.0])
paths = save_figure(fig, "fig3_pareto", outdir=OUT)
print("wrote", *paths, sep="\n  ")
