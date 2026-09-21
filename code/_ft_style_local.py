"""Local stand-in for the `futuretech-charts` skill helpers.

That skill (~/.claude/skills/futuretech-charts/python) is NOT present on this
machine, so every code/*_ft.py figure script fails at import. This module supplies
the three helpers they use, so figures can still be built.

PRIMARY was recovered by sampling the committed paper_figs/fig1_grid.png -- it is
the most common saturated colour in that figure (73,924 px). The two accents are
read straight out of the existing scripts. So the palette matches the published
figures exactly; the rcParams below are a RECONSTRUCTION and may differ in small
ways (font stack, exact grid alpha) from the real house style.

If the real skill is restored, delete this file and revert the import.
"""
import os
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

PRIMARY = "#002896"     # sampled from paper_figs/fig1_grid.png
# Copied verbatim from the skill's futuretech_palette.CATEGORICAL on 2026-09-21, so
# a machine without the skill produces byte-identical colours.
CATEGORICAL = ["#1966FF", "#750014", "#00AD00", "#9933FF", "#ED7700", "#FF14F0"]
ACCENT_ACC = "#0E8A8A"  # accuracy, from figure1_glm_algo_ft.py
ACCENT_FLOOR = "#E07A3F"


def use_style():
    plt.rcParams.update({
        "figure.dpi": 120, "savefig.dpi": 300,
        "savefig.bbox": "tight", "figure.facecolor": "white",
        "axes.facecolor": "white", "axes.edgecolor": "#333333",
        "axes.linewidth": 0.8, "axes.labelcolor": "#333333",
        "axes.titlesize": 11, "axes.titleweight": "bold", "axes.labelsize": 9.5,
        "axes.spines.top": False, "axes.spines.right": False,
        "xtick.color": "#333333", "ytick.color": "#333333",
        "xtick.labelsize": 8.5, "ytick.labelsize": 8.5,
        "grid.color": "#BBBBBB", "grid.alpha": 0.35, "grid.linewidth": 0.6,
        "axes.grid": True, "axes.axisbelow": True,
        "legend.frameon": False, "legend.fontsize": 8.5,
        "font.size": 9.5,
    })


def unit_formatter(scale=1.0, suffix="", fmt="{:.0f}"):
    return FuncFormatter(lambda v, _pos: fmt.format(v / scale) + suffix)


def save_figure(fig, fname, outdir="."):
    os.makedirs(outdir, exist_ok=True)
    out = []
    for ext in ("png", "pdf"):
        p = os.path.join(outdir, f"{fname}.{ext}")
        fig.savefig(p); out.append(p)
    plt.close(fig)
    print("wrote " + " + ".join(out))
    return out
