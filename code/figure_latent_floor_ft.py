"""
Latent reasoning & distance-to-floor (FutureTech house style).

Two panels on the hard-but-doable k=32 set:
  (A) Latent reasoning: share of traces that emit ZERO thinking tokens (the model
      reasons inline in the answer instead of in a separate thinking block).
  (B) Distance to the canonical floor: distribution of trace length / canonical-
      solution length (L / C_j) per model, log scale, with the floor at 1.0 and a
      shaded "below canonical" region.  Shows that the newest efficient models
      dip BELOW the canonical solution length.

    MPLBACKEND=Agg ./venv/bin/python code/figure_latent_floor_ft.py
Output -> figures/figs_sept/fig5_latent_floor.{png,pdf}
"""
import importlib.util
import os
import sys

import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

sys.path.insert(0, os.path.expanduser("~/.claude/skills/futuretech-charts/python"))
from futuretech_helpers import use_style, unit_formatter, save_figure
from futuretech_palette import PRIMARY

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("pf", os.path.join(HERE, "paper_figures_71226.py"))
pf = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(pf)
OUT = os.path.join(os.path.dirname(HERE), "figures", "figs_sept")
D = pf.RESULTS_DIR / "hard_but_doable_10q_k32"

TOK = PRIMARY
ACC = "#E07A3F"

# (display, file) — verbose baseline -> efficient frontier
MODELS = [
    ("o3", "o3_medium_thinking_benchmark_hard_but_doable_10.json"),
    ("GPT-5.6-sol", "gpt-5.6-sol_medium_thinking_benchmark_hard_but_doable_10.json"),
    ("GPT-6-astra", "gpt-6-astra_medium_thinking_benchmark_hard_but_doable_10.json"),
    ("Opus 5", "claude-opus-5_medium_thinking_benchmark_hard_but_doable_10.json"),
    ("Fable 5", "claude-fable-5_medium_thinking_benchmark_hard_but_doable_10.json"),
    ("Fable 5.1", "claude-fable-5-1_medium_thinking_benchmark_hard_but_doable_10.json"),
]


def load(fn):
    # ratios are relative to the MINIMAL human derivation (shortest canonical)
    ratios, latent, latent_ok, below, below_mean, n = [], 0, 0, 0, 0, 0
    for r in pf.load_rows(D / fn):
        tid = str(r["task_id"]); cj = pf.CANON.get(tid, {})
        mn, me = cj.get("min"), cj.get("mean")
        tt = r.get("thinking_tokens", [None] * len(r["correct"]))
        for tok, c, th in zip(r["total_completion_tokens"], r["correct"], tt):
            n += 1
            if th == 0:
                latent += 1; latent_ok += int(c)
            if mn and c:                     # distance-to-floor: correct traces only
                ratios.append(tok / mn)
                if tok < mn:
                    below += 1
                if me and tok < me:
                    below_mean += 1
    nc = max(1, len(ratios))     # correct traces (matches the violin population)
    return dict(n=n, latent_pct=100 * latent / n, latent_ok=(100 * latent_ok / latent if latent else 0),
                below_pct=100 * below / nc, below_mean_pct=100 * below_mean / nc, ratios=np.array(ratios))


# average human solution as a multiple of the MHD (shortest), over these problems
_k = [str(r["task_id"]) for r in pf.load_rows(D / MODELS[0][1]) if str(r["task_id"]) in pf.CANON_KEYS]
MEAN_REF = float(np.median([pf.CANON[k]["mean"] / pf.CANON[k]["min"] for k in _k]))


labels = [m for m, _ in MODELS]
stats = [load(fn) for _, fn in MODELS]
colors = sns.color_palette("crest", len(MODELS))
x = np.arange(len(MODELS))

use_style()
plt.rcParams.update({"axes.labelsize": 16, "xtick.labelsize": 14, "ytick.labelsize": 14})
fig, (axA, axB) = plt.subplots(1, 2, figsize=(16, 6.5), gridspec_kw={"wspace": 0.22})

# ---- Panel A: latent reasoning (% zero-thinking traces) ----
bars = axA.bar(x, [s["latent_pct"] for s in stats], color=colors, width=0.7, zorder=3)
for xi, s in zip(x, stats):
    if s["latent_pct"] > 0.5:
        axA.annotate(f"{s['latent_pct']:.0f}%\n({s['latent_ok']:.0f}% correct)",
                     (xi, s["latent_pct"]), textcoords="offset points", xytext=(0, 6),
                     ha="center", va="bottom", fontsize=11, fontweight="bold", color=TOK)
    else:
        axA.annotate(f"{s['latent_pct']:.0f}%", (xi, s["latent_pct"]), textcoords="offset points",
                     xytext=(0, 6), ha="center", va="bottom", fontsize=10, color="#888888")
axA.set_ylim(0, max(s["latent_pct"] for s in stats) * 1.25 + 1)
axA.set_ylabel("Traces with 0 thinking tokens")
axA.yaxis.set_major_formatter(unit_formatter(1, "%", "{:.0f}"))
axA.set_title("Latent reasoning (no explicit thinking)", fontsize=15, fontweight="bold", loc="left")
axA.set_xticks(x); axA.set_xticklabels(labels, fontsize=12, rotation=20, ha="right")

# ---- Panel B: distance to the minimal human derivation (L / MHD) ----
axB.axhspan(1e-2, 1.0, color=ACC, alpha=0.08, zorder=0)          # below the MHD floor
axB.axhline(1.0, color=ACC, lw=2.2, zorder=3)                    # minimal human derivation
axB.axhline(MEAN_REF, color="#8A8A8A", lw=1.8, ls="--", zorder=3)  # average human solution
parts = axB.violinplot([s["ratios"] for s in stats], positions=x, widths=0.8,
                       showmedians=True, showextrema=False)
for b, c in zip(parts["bodies"], colors):
    b.set_facecolor(c); b.set_alpha(0.6); b.set_edgecolor(c)
parts["cmedians"].set_color(TOK); parts["cmedians"].set_linewidth(2)
for xi, s in zip(x, stats):
    if s["below_mean_pct"] > 3:      # share beating the average human solution
        axB.annotate(f"{s['below_mean_pct']:.0f}%\n<avg", (xi, MEAN_REF * 0.78), ha="center",
                     va="center", fontsize=10, fontweight="bold", color="#5A5A5A")
axB.set_yscale("log")
axB.set_ylim(0.5, 60)
axB.set_ylabel("Trace length / minimal human derivation")
axB.set_title("Distance to the minimal human derivation", fontsize=15, fontweight="bold", loc="left")
axB.annotate("minimal human derivation (1×)", (len(MODELS) - 0.5, 1.0), textcoords="offset points",
             xytext=(0, 4), ha="right", va="bottom", fontsize=11, fontweight="bold", color=ACC)
axB.annotate(f"average human solution (≈{MEAN_REF:.1f}×)", (len(MODELS) - 0.5, MEAN_REF),
             textcoords="offset points", xytext=(0, 4), ha="right", va="bottom",
             fontsize=10.5, fontweight="bold", color="#5A5A5A")
axB.set_xticks(x); axB.set_xticklabels(labels, fontsize=12, rotation=20, ha="right")

plt.tight_layout()
paths = save_figure(fig, "fig5_latent_floor", outdir=OUT)
print("wrote", *paths, sep="\n  ")
