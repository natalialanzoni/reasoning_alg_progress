"""
DeepSeek timeline with the V4 effort branch — 2 rows, one panel.

  Spine:  R1-0528 -> V3.2, the two models with no effort knob.
  Branch: at V4 Pro the line splits into its two available effort levels, high and
          max, light->dark on the repo's `crest` ramp (more effort = darker). V4 is
          drawn ONLY as the branch -- there is no separate "default" V4 point,
          because the default IS high and it would plot on top of the high arm.
  Rows:   1 = accuracy, 2 = mean output tokens + minimal-human-derivation floor.

TWO BRANCH POINTS, AND THEY ARE NOT THE SAME MODEL.

  V4 Pro April (2026-04-24), OpenRouter/SiliconFlow fp8 — DOTTED, two levels only.
  The April build offered **high and max**; there was no `low`. We swept `low`
  anyway and it came back 0.5% from `high` (10,380 vs 10,434 tok; 76.3% vs 75.8%)
  — it was remapped to `high`, so it is NOT plotted. DeepSeek's 2026-08-13 release
  note confirms the three-level knob arrived with GA: the thinking modes "now
  support three thinking effort levels: low / high / max".

  The DeepSeek-direct GA runs are deliberately NOT drawn. They are a different
  build AND a different endpoint (native precision, not SiliconFlow fp8), and
  provider alone moves these numbers by 6-14 points after censoring — so putting
  them on this line would compare provider, not model. They live in
  deepseek_v4_pro_ga_shallow_pass/ and are reported separately.

Censoring: every point is right-censored at 32,768, matching fig1_grid_deepseek —
a trace needing more is scored wrong and clamped. DeepSeek absorbs far more of
this than the incumbent families (23.6% of trials), so accuracy is biased down.

Sample = the same 40 competition problems as fig1_grid (MATH-500 excluded).

    MPLBACKEND=Agg ./venv/bin/python code/figure_deepseek_branch_ft.py
Output -> figures/figs_sept/fig_deepseek_branch.{png,pdf}
"""
import importlib.util
import os
import sys
from datetime import datetime

import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.lines as mlines

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.expanduser("~/.claude/skills/futuretech-charts/python"))
try:
    from futuretech_helpers import use_style, unit_formatter, save_figure
    from futuretech_palette import PRIMARY
except ModuleNotFoundError:
    sys.path.insert(0, HERE)
    from _ft_style_local import use_style, unit_formatter, save_figure, PRIMARY

_spec = importlib.util.spec_from_file_location("fs", os.path.join(HERE, "figures_sept.py"))
fs = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(fs)
pf = fs.pf

OUT = os.path.join(os.path.dirname(HERE), "figures", "figs_sept")
R = os.path.join(HERE, "results")
CLIP = 32768
KEYS = {t for t in pf.CANON_KEYS if not str(t).startswith("math_500")}
FLOOR = float(np.mean([pf.CANON[t]["min"] for t in KEYS]))

_crest = sns.color_palette("crest", 3)
EFF_COLOR = {"low": _crest[0], "high": _crest[1], "max": _crest[2]}
SPINE = PRIMARY
FLOOR_COLOR = "#E07A3F"

SPINE_PTS = [
    ("R1-0528", datetime(2025, 5, 28),
     f"{R}/deepseek_r1_0528_shallow_pass/deepseek_r1_0528_thinking_benchmark_90.json"),
    ("V3.2", datetime(2025, 12, 1),
     f"{R}/deepseek_v3_2_shallow_pass/deepseek_v3_2_thinking_benchmark_90.json"),
]
APR = (datetime(2026, 4, 24),
       lambda e: f"{R}/deepseek_v4_pro_shallow_pass/deepseek_v4_pro_thinking_benchmark_90_{e}.json")


def stat(path):
    """Mean tokens over CORRECT traces, accuracy, and the truncation rate — censored at CLIP.

    The truncation rate matters as much as the accuracy here. Among traces that
    COMPLETE, V4 high and max are indistinguishable (98.8% vs 98.7%); the entire
    accuracy gap on this figure is max overrunning the ceiling more often (106 vs
    76 of 320 trials at 32,768). So the branch shows "max costs accuracy under a
    fixed budget", NOT "max reasons worse" -- label it accordingly.
    """
    toks, nc, nt, cen = [], 0, 0, 0
    comp = compc = 0            # traces that finished (non-empty text), and how many were right
    for r in pf.load_rows(path):
        if str(r["task_id"]) not in KEYS:
            continue
        texts = r.get("response_texts", [None] * len(r["correct"]))
        for tok, c, txt in zip(r["total_completion_tokens"], r["correct"], texts):
            blank = (txt is not None and not str(txt).strip())
            if not blank and tok >= 50:
                comp += 1; compc += int(c)
            if tok >= CLIP:          # what a 32,768-capped backend would truncate
                nt += 1; cen += 1
                continue
            if not fs._trial_ok(tok, txt):
                continue
            nt += 1; nc += int(c)
            if c:
                toks.append(tok)
    return (float(np.mean(toks)) if toks else np.nan), 100 * nc / max(1, nt), \
        100 * cen / max(1, nt), 100 * compc / max(1, comp)


def main():
    use_style()
    fig, (a0, a1) = plt.subplots(2, 1, figsize=(11.2, 8.8), sharex=True)

    sx = mdates.date2num([d for _, d, _ in SPINE_PTS])
    svals = [stat(p) for _, _, p in SPINE_PTS]
    stok = [v[0] for v in svals]; sacc = [v[1] for v in svals]
    scomp = [v[3] for v in svals]

    # spine
    a0.plot(sx, scomp, "--", color=SPINE, lw=1.6, alpha=0.55, zorder=2)
    a0.plot(sx, scomp, "s", color=SPINE, ms=5, alpha=0.55, zorder=2)
    a0.plot(sx, sacc, "-", color=SPINE, lw=2.4, zorder=3)
    a1.plot(sx, stok, "-", color=SPINE, lw=2.4, zorder=3)
    for ax, ys in ((a0, sacc), (a1, stok)):
        ax.plot(sx, ys, "o", color=SPINE, ms=7, mec="white", mew=1.3, zorder=4)
    for (lab, _, _), xi, ti in zip(SPINE_PTS, sx, stok):
        a1.annotate(lab, (xi, ti), textcoords="offset points", xytext=(0, 12),
                    ha="center", fontsize=8.4, color="#333333", fontweight="bold")

    # branches
    # April offered high and max only -- its `low` was remapped to `high`, so the
    # April branch has two arms, not three.
    for (bx_date, pathf), solid, effs in ((APR, True, ("high", "max")),):
        bx = mdates.date2num(bx_date)
        for eff in effs:
            tok, acc, trunc, compacc = stat(pathf(eff))
            col = EFF_COLOR[eff]
            if solid:
                # dotted arms off the April spine point
                a0.plot([sx[-1], bx], [scomp[-1], compacc], "--", color=col, lw=1.4,
                        alpha=0.55, zorder=1)
                a0.plot([bx], [compacc], "s", color=col, ms=5, alpha=0.55, zorder=2)
                a0.plot([sx[-1], bx], [sacc[-1], acc], ":", color=col, lw=2.2, zorder=2)
                a1.plot([sx[-1], bx], [stok[-1], tok], ":", color=col, lw=2.2, zorder=2)
                a0.plot([bx], [acc], "o", color=col, ms=8, mec="white", mew=1.3, zorder=5)
                a1.plot([bx], [tok], "o", color=col, ms=8, mec="white", mew=1.3, zorder=5)
            a1.annotate(f"V4 Pro\n{eff}", (bx, tok), textcoords="offset points",
                        xytext=(11, 0), va="center", fontsize=8.2, color=col,
                        fontweight="bold")
            a0.annotate(f"{eff}\n{trunc:.0f}% truncated", (bx, acc),
                        textcoords="offset points", xytext=(11, 0), va="center",
                        fontsize=8.2, color=col, fontweight="bold")

    a0.set_ylabel("Accuracy"); a0.set_ylim(55, 101)
    a0.yaxis.set_major_formatter(unit_formatter(1, "%", "{:.0f}"))
    a0.set_title("Capability keeps rising; accuracy under a fixed token budget does not",
                 fontsize=10, pad=8, color="#333333", fontweight="normal")
    a1.set_ylabel("Mean output tokens")
    a1.axhline(FLOOR, color=FLOOR_COLOR, ls="--", lw=1.4)
    a1.text(sx[0], FLOOR * 1.6, f"minimal human derivation ({FLOOR:.0f} tok)",
            color=FLOOR_COLOR, fontsize=8, va="bottom")
    a1.set_ylim(0, 20500)
    a1.yaxis.set_major_formatter(unit_formatter(1e3, "k"))
    a1.xaxis.set_major_locator(mdates.MonthLocator(bymonth=(1, 7)))
    a1.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))

    handles = [mlines.Line2D([], [], color=EFF_COLOR[e], lw=2.4, marker="o", ms=7,
                             mec="white", label=f"{e} effort") for e in ("high", "max")]
    handles += [mlines.Line2D([], [], color="#666666", lw=1.6, ls="--", marker="s", ms=5,
                              alpha=0.7, label="accuracy among traces that finish")]
    handles += [
        mlines.Line2D([], [], color=SPINE, lw=2.4, marker="o", ms=7, mec="white",
                      label="spine: default setting (SiliconFlow fp8)"),
        mlines.Line2D([], [], color="#666666", lw=2.2, ls=":",
                      label="April build branch (high / max only \u2014 no low)"),
    ]
    a0.legend(handles=handles, loc="lower right", fontsize=8, ncol=1,
              borderaxespad=0.6)

    fig.suptitle("DeepSeek: reasoning length and accuracy, with the V4 effort branch",
                 y=0.98, fontsize=12.5, fontweight="bold")
    fig.text(0.5, 0.005,
             "SOLID = accuracy under a 32,768-token budget (an overrun scores wrong).  DASHED = accuracy "
             "among traces that FINISH, i.e. capability unconstrained by the budget.\n"
             "They diverge because V4 overruns the budget far more often: R1 and V3.2 were never cut at "
             "32,768 by the provider (they ran to 66k and 83k), V4 was, on 41 of 320 trials.\n"
             "So V4 scoring below V3.2 on the solid line is a budget effect, not lower capability \u2014 on "
             "traces that finish V4 leads 98.8% to 92.7%. April build offered high and max only.",
             ha="center", fontsize=8, color="#555555")
    fig.tight_layout(rect=(0, 0.075, 1, 0.955))
    return save_figure(fig, "fig_deepseek_branch", outdir=OUT)


if __name__ == "__main__":
    main()
