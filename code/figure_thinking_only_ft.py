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
from futuretech_palette import PRIMARY, CATEGORICAL

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
OAI_C = CATEGORICAL[0]     # blue    — OpenAI, as in Figure 4 panel B
ANT_C = CATEGORICAL[1]     # MIT red — Anthropic, as in Figure 4 panel B


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
# ONE axes with BOTH families overlaid, matching panel B of Figure 4: log y, direct
# endpoint dot labels, no per-panel rate boxes competing with the lines. Equal decay
# rates read as parallel lines. No forecast and no milestone date -- without a floor
# there is nothing to forecast TO (see the module docstring).
fig, ax = plt.subplots(1, 1, figsize=(11.2, 6.4))
print("thinking-only figure — spec: log(thinking) = alpha_j + beta*Month, problem FE")
handles, rate_lines = [], []
for yi, ((fam, mfiles), col) in enumerate(zip(td.FAMILIES, (OAI_C, ANT_C))):
    ft = td.fit(td.rows_for(mfiles, dv="logthink"))
    fl = td.fit(td.rows_for(mfiles, dv="logL"))
    pt_t, pt_l = observed(mfiles, True), observed(mfiles, False)
    d0, d1 = pt_t[0][1], pt_t[-1][1]
    grid = [d0 + timedelta(days=k) for k in range(0, (d1 - d0).days + 1, 7)]

    lo = fitted_curve(None, pt_t, ft["lo"], grid)
    hi = fitted_curve(None, pt_t, ft["hi"], grid)
    ax.fill_between(grid, np.minimum(lo, hi), np.maximum(lo, hi),
                    color=col, alpha=0.15, lw=0, zorder=2)
    ax.plot(grid, fitted_curve(None, pt_t, ft["b"], grid), color=col, lw=2.6, zorder=4)
    # the same family's L fit, dotted, so "thinking falls faster" is visible and not
    # merely asserted in the annotation
    ax.plot(grid, fitted_curve(None, pt_l, fl["b"], grid), color=col, lw=1.8,
            ls=":", alpha=0.75, zorder=3)
    ax.plot([d for _, d, _ in pt_t], [v for _, _, v in pt_t], "o", color=col,
            ms=9, mec="white", mew=1.4, zorder=6)

    # Endpoint dot labels. Push the FIRST label left of its dot and the LAST one
    # right, so neither sits on the fit line running between them (the Anthropic
    # start label landed on its own curve when both were offset the same way).
    dy = -13 if yi == 0 else 13
    for (_, d, v), dx, ha in ((pt_t[0], -10, "right"), (pt_t[-1], 10, "left")):
        ax.annotate(f"{v:,.0f}", (d, v), textcoords="offset points", xytext=(dx, dy),
                    ha=ha, fontsize=9.5, fontweight="bold", color=col, zorder=8)
    rate_lines.append((fam.split(" (")[0], ft, fl, col))
    handles.append(mlines.Line2D([], [], color=col, lw=2.6, marker="o", ms=9, label=fam))
    print(f"  {fam:<26s} thinking {ft['q']:5.1f}%/qtr (p={ft['p']:.3f}, N={ft['n']}) "
          f"| L {fl['q']:5.1f}%/qtr | geo {pt_t[0][2]:.0f} -> {pt_t[-1][2]:.0f} = "
          f"{pt_t[0][2]/pt_t[-1][2]:.1f}x   [Figure 1 quotes the ARITHMETIC ratio]")

# both rates per family: the thinking rate and, for contrast, the same fit on L
for i, (nm, ft, fl, col) in enumerate(rate_lines):
    ax.annotate(f"{nm}   thinking {ft['q']:.0f}%/qtr{ft['star']}   ·   $L$ {fl['q']:.0f}%/qtr",
                xy=(0.97, 0.95 - 0.075 * i), xycoords="axes fraction",
                ha="right", va="top", fontsize=12.5, fontweight="bold", color=col)

ax.set_yscale("log")
# margin so the first/last endpoint labels are not clipped by the axes edge
ax.margins(x=0.06)
ax.set_xlabel("Date")
ax.set_ylabel("Thinking tokens per correct trace\n(geometric mean, log scale)")
ax.yaxis.set_major_formatter(unit_formatter(1e3, "k"))
ax.xaxis.set_major_locator(mdates.YearLocator())
ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
handles += [mlines.Line2D([], [], color="#888888", lw=2.6, label="Thinking tokens (fit)"),
            mlines.Line2D([], [], color="#888888", lw=1.8, ls=":",
                          label="Total output $L$ = thinking + answer (fit)"),
            mpatches.Patch(color="#888888", alpha=0.15, label="95% CI (wild bootstrap)")]
fig.legend(handles=handles, loc="upper center", ncol=3, fontsize=10.5,
           frameon=True, framealpha=0.95, bbox_to_anchor=(0.5, -0.01))
plt.tight_layout(pad=0.5)
print("wrote", *save_figure(fig, "fig4_thinking_only", outdir=OUT), sep="\n  ")
