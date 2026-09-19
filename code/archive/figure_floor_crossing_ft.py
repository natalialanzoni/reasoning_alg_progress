"""Does any model ever go below the human floor? (FutureTech house style)

One panel, both samples POOLED: the whole benchmark (40 competition problems, k=8)
and the hard-but-doable subset (10 problems, k=32), giving ~630 correct traces per
model. For each model we plot two things against its release date, on a log axis
with the floor at 1x:

    solid line + dots   the MEDIAN trace length / minimal human derivation
    open markers        the MINIMUM over all its correct traces -- its closest
                        approach to the floor, i.e. the single shortest solution
                        it ever produced relative to the shortest human one

A model has "crossed the floor" exactly when its open marker sits below 1x. Those
models are annotated with how many traces and how many distinct problems.

Caveat, stated because pooling is not innocent: the 10 hard-but-doable problems are
a SUBSET of the 40, so after pooling they carry 8+32 = 40 attempts each while the
other 30 carry 8. The pooled rate is therefore weighted toward the hard subset. That
is fine for the question being asked here ("does it ever happen"), where more
attempts per problem simply means more chances to observe a crossing, but the
percentages are not a clean per-problem rate.

    MPLBACKEND=Agg ./venv/bin/python code/figure_floor_crossing_ft.py
Output -> figures/figs_sept/fig5b_floor_crossing.{png,pdf}
"""
import importlib.util
import os
import sys
from datetime import datetime

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.lines as mlines

sys.path.insert(0, os.path.expanduser("~/.claude/skills/futuretech-charts/python"))
from futuretech_helpers import use_style, save_figure
from futuretech_palette import CATEGORICAL

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("fs", os.path.join(HERE, "figures_sept.py"))
fs = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(fs)
pf = fs.pf
OUT = os.path.join(os.path.dirname(HERE), "figures", "figs_sept")
HD = pf.RESULTS_DIR / "hard_but_doable_10q_k32"

MIN_C = "#E07A3F"        # the floor
OAI_C = CATEGORICAL[0]
ANT_C = CATEGORICAL[1]
KEYS = {t for t in pf.CANON_KEYS if not str(t).startswith("math_500")}

FAB_S = [("claude-fable-5-1", datetime(2026, 9, 1),
          pf.RESULTS_DIR / "fable5.1_shallow_pass"
          / "claude-fable-5-1_medium_thinking_benchmark.json")]
FAB_H = [("claude-fable-5-1", datetime(2026, 9, 1),
          HD / "claude-fable-5-1_medium_thinking_benchmark_hard_but_doable_10.json")]
FAMILIES = [
    ("OpenAI (GPT)", list(pf.MAIN_K8), list(fs.GPT_HARD), OAI_C),
    ("Anthropic (Opus + Fable)",
     sorted(list(pf.OPUS_MODELS) + FAB_S, key=lambda t: t[1]),
     sorted(list(pf.OPUS_HARD10_K32) + FAB_H, key=lambda t: t[1]), ANT_C),
]


def clean(n):
    if n.startswith("claude-opus-"):  return "Opus " + n[len("claude-opus-"):].replace("-", ".")
    if n.startswith("claude-fable-"): return "Fable " + n[len("claude-fable-"):].replace("-", ".")
    if n.startswith("gpt-"):          return "GPT-" + n[len("gpt-"):]
    return n


def pool(shallow, hard):
    """Merge both samples per model -> ratios, crossings, distinct problems crossed."""
    out = {}
    for group in (shallow, hard):
        for label, date, path in group:
            d = out.setdefault(label, {"date": date, "r": [], "below": 0, "probs": set()})
            for r in pf.load_rows(path):
                tid = str(r["task_id"])
                if tid not in KEYS:
                    continue
                mn = pf.CANON[tid]["min"]
                for tok, c in zip(r["total_completion_tokens"], r["correct"]):
                    if tok < 50 or not c:      # zero-thinking traces ARE valid
                        continue
                    d["r"].append(tok / mn)
                    if tok <= mn:
                        d["below"] += 1; d["probs"].add(tid)
    for d in out.values():
        d["r"] = np.array(d["r"])
    return out


use_style()
plt.rcParams.update({"axes.labelsize": 15, "xtick.labelsize": 13, "ytick.labelsize": 14})
fig, ax = plt.subplots(figsize=(13, 7))
ax.axhspan(1e-3, 1.0, color=MIN_C, alpha=0.10, zorder=0)
ax.axhline(1.0, color=MIN_C, lw=2.6, zorder=4)

tot_n = tot_b = 0
handles = []
crossers = []   # annotated after both families, so boxes can be stacked
print("POOLED: whole benchmark (k=8) + hard-but-doable (k=32), correct traces\n")
print(f"  {'model':<16s} {'date':>8s} {'traces':>7s} {'median':>8s} {'closest':>8s} "
      f"{'below':>6s} {'problems':>9s}")
for fam, shallow, hard, col in FAMILIES:
    P = pool(shallow, hard)
    order = sorted(P, key=lambda l: P[l]["date"])
    xs = mdates.date2num([P[l]["date"] for l in order])
    med = [float(np.median(P[l]["r"])) for l in order]
    lo = [float(P[l]["r"].min()) for l in order]
    ax.plot(xs, med, "-o", color=col, lw=2.6, ms=9, zorder=5)
    ax.plot(xs, lo, "o", mfc="white", mec=col, mew=2.2, ms=11, zorder=6)
    ax.vlines(xs, lo, med, color=col, lw=1.2, alpha=0.45, zorder=3)
    handles.append(mlines.Line2D([], [], color=col, lw=2.6, marker="o", ms=9, label=fam))
    for l, x, y in zip(order, xs, lo):
        d = P[l]; tot_n += len(d["r"]); tot_b += d["below"]
        if d["below"]:
            crossers.append((x, y, clean(l), d["below"], len(d["probs"]), col))
        print(f"  {clean(l):<16s} {d['date']:%Y-%m} {len(d['r']):>7d} "
              f"{np.median(d['r']):>7.2f}x {d['r'].min():>7.2f}x {d['below']:>6d} "
              f"{len(d['probs']):>9d}")

# Annotate the floor-crossers last, stacking boxes for models that share a release
# date (Astra and Fable 5.1 are both 2026-09, so a single offset would overlap them).
crossers.sort(key=lambda t: t[0])
row, prev_x = 0, None
for x, y, name, nb, npr, col in crossers:
    row = row + 1 if (prev_x is not None and abs(x - prev_x) < 120) else 0
    prev_x = x
    ax.annotate(f"{name}: {nb} traces, {npr} problem{'s' if npr > 1 else ''}",
                (x, y), textcoords="offset points", xytext=(10, -26 - 30 * row),
                ha="left", va="top", fontsize=10.5, fontweight="bold",
                color=col, zorder=9,
                arrowprops=dict(arrowstyle="-", color=col, lw=0.9, alpha=0.7,
                                shrinkA=0, shrinkB=4),
                bbox=dict(boxstyle="round,pad=0.25", fc="white", ec=col,
                          lw=0.9, alpha=0.96))

ax.annotate("minimal human derivation (1×)", xy=(0.015, 1.0),
            xycoords=("axes fraction", "data"), textcoords="offset points",
            xytext=(0, 7), ha="left", va="bottom", fontsize=12, fontweight="bold",
            color=MIN_C, zorder=9,
            bbox=dict(boxstyle="round,pad=0.22", fc="white", ec="none", alpha=0.9))
ax.set_yscale("log"); ax.set_ylim(0.34, 60)
ax.set_ylabel("Trace length / minimal human derivation")
ax.set_xlabel("Release date")
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:g}×"))
ax.xaxis.set_major_locator(mdates.MonthLocator(interval=4))
ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
handles += [mlines.Line2D([], [], color="#666666", lw=2.6, marker="o", ms=9,
                          label="Median trace"),
            mlines.Line2D([], [], color="#666666", lw=0, marker="o", mfc="white",
                          mec="#666666", mew=2.2, ms=11, label="Shortest trace produced"),
            mlines.Line2D([], [], color=MIN_C, lw=2.6, label="Minimum human solution")]
ax.legend(handles=handles, loc="upper right", fontsize=11.5, frameon=True, framealpha=0.95)
plt.tight_layout(pad=0.5)
paths = save_figure(fig, "fig5b_floor_crossing", outdir=OUT)
print(f"\n  TOTAL {tot_b} of {tot_n} correct traces below the floor "
      f"({100 * tot_b / tot_n:.2f}%)")
print("wrote", *paths, sep="\n  ")
