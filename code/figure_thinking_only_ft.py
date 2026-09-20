"""Thinking-only robustness figure (Figure 4 counterpart).

    MPLBACKEND=Agg ./venv/bin/python code/figure_thinking_only_ft.py
Output -> figures/figs_sept/fig4_thinking_only.{png,pdf}

WHY THIS EXISTS. The headline DV is L = thinking + answer, and two things happen in
the ANSWER that have nothing to do with reasoning:
  * gpt-5.1 writes 3.1x longer answers than gpt-5 while its thinking is flat, so it
    reads as an efficiency regression on L when its reasoning did not change;
  * the series switches output format at gpt-5.1, plain-text math -> LaTeX display
    blocks, taking LaTeX from ~0.3-2% of answer characters to ~20-25% for every later
    model -- inflating L for the RECENT models, against the paper's own claim.
Refitting on thinking alone retires both at once.

WHY IT IS A TREND FIGURE, NOT A FORECAST. Figure 4 forecasts the date reasoning comes
within 10% of the minimal human derivation. That floor is a human's WRITTEN
derivation -- exposition, the analogue of the model's answer, not of its hidden
scratch work -- so it does not apply to thinking tokens, and there is no principled
target to forecast to. Subtracting it anyway is also empirically unusable: it would
censor 38.4% of gpt-6-astra's traces and 26.2% of Fable 5.1's. So this figure shows
the fitted decay and stops there; no floor line, no milestone.

Spec, per family, on correct non-truncated traces over the 40 competition problems:

    log(thinking_ijt) = alpha_j + beta * Month_i + eps     (problem FE)

with the same wild cluster bootstrap over MODELS as table_decay (Webb weights,
bootstrap-t under H0). The grey dash-dot line is the same fit on log(L), plotted so
the gap between the two is visible: thinking falls FASTER than total output.
"""
import importlib.util
import math
import os
import sys
from datetime import datetime, timedelta

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.lines as mlines
import matplotlib.patches as mpatches

sys.path.insert(0, os.path.expanduser("~/.claude/skills/futuretech-charts/python"))
from futuretech_helpers import use_style, unit_formatter, save_figure
from futuretech_palette import PRIMARY

HERE = os.path.dirname(os.path.abspath(__file__))
_s = importlib.util.spec_from_file_location("td", os.path.join(HERE, "table_decay.py"))
_stdout = sys.stdout; sys.stdout = open(os.devnull, "w")
td = importlib.util.module_from_spec(_s); _s.loader.exec_module(td)
sys.stdout.close(); sys.stdout = _stdout
pf = td.pf
_s2 = importlib.util.spec_from_file_location("fs", os.path.join(HERE, "figures_sept.py"))
fs = importlib.util.module_from_spec(_s2); _s2.loader.exec_module(fs)

OUT = os.path.join(os.path.dirname(HERE), "figures", "figs_sept")
KEYS = td.KEYS
THINK_C = PRIMARY          # navy — thinking tokens
L_C = "#6E6E6E"            # grey — total output, for contrast


def observed(mfiles, thinking):
    """Per model: (date, geometric mean over traces). Geometric, to match the log fit."""
    out = []
    for label, date, path in mfiles:
        vals = []
        for r in pf.load_rows(path):
            tid = str(r["task_id"])
            if tid not in KEYS:
                continue
            th = r.get("thinking_tokens")
            texts = r.get("response_texts", [None] * len(r["correct"]))
            for i, (tok, c, x) in enumerate(zip(r["total_completion_tokens"],
                                                r["correct"], texts)):
                if not fs._trial_ok(tok, x) or not fs._trial_correct(tok, c):
                    continue
                v = (th[i] if th is not None else None) if thinking else tok
                if v is not None and v > 0:
                    vals.append(math.log(v))
        if vals:
            out.append((label, date, math.exp(float(np.mean(vals)))))
    return out


def fitted_curve(rows, pts, beta, dates):
    """Project the problem-FE fit onto the AVERAGE problem.

    The regression carries a level per problem, so a single line in token space is
    only defined once a problem mix is fixed. Anchoring the slope through the
    geometric mean of the observed points at the mean month is exactly that fit
    evaluated at the average problem, which is what the plotted points also are.
    """
    m = np.array([(d - pf.ORIGIN).days / 30.44 for _, d, _ in pts])
    y = np.array([math.log(v) for _, _, v in pts])
    c = float(np.mean(y) - beta * np.mean(m))
    mm = np.array([(d - pf.ORIGIN).days / 30.44 for d in dates])
    return np.exp(c + beta * mm)


use_style()
fig, axes = plt.subplots(1, 2, figsize=(15.4, 6.4), sharey=True)
print("thinking-only figure — spec: log(thinking) = alpha_j + beta*Month, problem FE")
for ax, (fam, mfiles) in zip(axes, td.FAMILIES):
    ft = td.fit(td.rows_for(mfiles, dv="logthink"))
    fl = td.fit(td.rows_for(mfiles, dv="logL"))
    pt_t, pt_l = observed(mfiles, True), observed(mfiles, False)
    d0, d1 = pt_t[0][1], pt_t[-1][1]
    grid = [d0 + timedelta(days=k) for k in range(0, (d1 - d0).days + 1, 7)]

    # CI band from the bootstrap interval on beta, re-anchored the same way
    lo = fitted_curve(None, pt_t, ft["lo"], grid)
    hi = fitted_curve(None, pt_t, ft["hi"], grid)
    ax.fill_between(grid, np.minimum(lo, hi), np.maximum(lo, hi),
                    color=THINK_C, alpha=0.16, lw=0, zorder=2)
    ax.plot(grid, fitted_curve(None, pt_t, ft["b"], grid), color=THINK_C, lw=2.6, zorder=4)
    ax.plot(grid, fitted_curve(None, pt_l, fl["b"], grid), color=L_C, lw=2.0,
            ls="-.", zorder=3)
    ax.plot([d for _, d, _ in pt_t], [v for _, _, v in pt_t], "o", color=THINK_C,
            ms=9, mec="white", mew=1.4, zorder=6)
    ax.plot([d for _, d, _ in pt_l], [v for _, _, v in pt_l], "o", color=L_C,
            ms=6, alpha=0.55, zorder=5)

    ax.set_yscale("log")
    ax.set_title(fam, fontsize=14)
    ax.set_xlabel("Date")
    ax.yaxis.set_major_formatter(unit_formatter(1e3, "k"))
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.annotate(f"thinking: {ft['q']:.0f}% / quarter{ft['star']}",
                xy=(0.96, 0.95), xycoords="axes fraction", ha="right", va="top",
                fontsize=14, fontweight="bold", color=THINK_C)
    ax.annotate(f"total output L: {fl['q']:.0f}% / quarter",
                xy=(0.96, 0.87), xycoords="axes fraction", ha="right", va="top",
                fontsize=12.5, fontweight="bold", color=L_C)
    # GEOMETRIC ratio, to match the log fit and the plotted points. Figure 1 quotes
    # ARITHMETIC means, so the two ratios differ (Anthropic 3.4x here vs 6.7x there):
    # the distributions are right-skewed, and zero-thinking traces are absent here.
    # Label it, or a reader will read the mismatch as a contradiction.
    r = pt_t[0][2] / pt_t[-1][2]
    ax.annotate(f"{r:.1f}x less thinking (geo. mean)\n{d0:%Y-%m} – {d1:%Y-%m}",
                xy=(0.96, 0.76), xycoords="axes fraction", ha="right", va="top",
                fontsize=11, color="#333333",
                bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="#BBBBBB", lw=0.8))
    print(f"  {fam:<26s} thinking {ft['q']:5.1f}%/qtr (p={ft['p']:.3f}, N={ft['n']}) "
          f"| L {fl['q']:5.1f}%/qtr | geo {pt_t[0][2]:.0f} -> {pt_t[-1][2]:.0f} = {r:.1f}x"
          f"   [Figure 1 quotes the ARITHMETIC ratio, which is larger]")

axes[0].set_ylabel("Tokens per correct trace (geometric mean, log scale)")
fig.suptitle("Robustness: the decline is in REASONING, not in answer formatting",
             fontsize=15, fontweight="bold", y=1.0)
fig.legend(handles=[
    mlines.Line2D([], [], color=THINK_C, lw=2.6, marker="o", ms=9,
                  label="Thinking tokens (fit + models)"),
    mpatches.Patch(color=THINK_C, alpha=0.16, label="95% CI (wild cluster bootstrap)"),
    mlines.Line2D([], [], color=L_C, lw=2.0, ls="-.", marker="o", ms=6,
                  label="Total output $L$ = thinking + answer"),
], loc="upper center", ncol=3, fontsize=10.5, frameon=True, bbox_to_anchor=(0.5, 0.055))
fig.text(0.5, -0.10,
         "No floor is drawn: the minimal human derivation is a written derivation, the analogue of the "
         "model's ANSWER, so it does not bound thinking.\nSubtracting it would also censor 38% of "
         "gpt-6-astra's traces. Zero-thinking traces cannot enter log(thinking); all 81 are Fable 5.1, "
         "the newest model's shortest,\nso their loss makes the thinking-only rate conservative.",
         ha="center", fontsize=8.4, color="#555555")
fig.tight_layout(rect=(0, 0.14, 1, 0.97))   # room for legend + footnote
print("wrote", *save_figure(fig, "fig4_thinking_only", outdir=OUT), sep="\n  ")
