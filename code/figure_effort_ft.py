"""
Appendix figure (FutureTech house style): reasoning length over generations by
reasoning-effort level (low / medium / high), on the hard-but-doable-10 set.
One line per effort (macro-mean per-problem trace length over the shared 10
problems), faint per-problem lines behind, the minimal human derivation floor,
and the per-effort decay rate (same excess-over-floor FE spec as the forecast,
MHD = shortest canonical, o3 included) shown in the legend.

COVERAGE IS NOW COMPLETE: all 8 GPT models have all three arms (gpt-5.1's low/high
runs landed 2026-09-20). gather() still skips a model with no run file SILENTLY, so if
a line ever loses a point, look for a missing file before reading it as a finding.

  low / high : o3, gpt-5, 5.1, 5.2, 5.4, 5.5, 5.6-sol, 6-astra   (k=8)
  medium     : the same 8                                        (k=32, hard-but-doable dir)

k IS MATCHED AT K_CAP=8 BY TRUNCATION, and it has to be. The raw runs are:

    o3 .. gpt-5.6-sol    low k=8    medium k=32   high k=8
    gpt-6-astra          low k=32   medium k=32   high k=32

so gpt-6-astra -- the newest and SHORTEST model -- carried four times the weight of
every other model in the low and high regressions, but not in medium. That is a
weighting artifact masquerading as an effort effect, and it inflated the low and high
rates. Truncating every problem to its first 8 attempts removes it:

                   uncapped        k=8
    low             37.7%         33.5%
    medium          36.3%         35.6%
    high            40.1%         36.3%

Capped, the three rates are close and ordered in effort; uncapped, low appeared to
beat medium. Attempts are independent samples, so the leading 8 is an unbiased
subsample, and taking the FIRST 8 is deterministic where a random draw would not be.

To add a model's low/high arms:  bash code/run_openai_effort.sh <model> low|high
That script pins k=8 -- note the medium arm comes from the k=32 runs, so the efforts
are NOT matched on k. DATES already lists gpt-5.1, and files are discovered by path,
so nothing here needs editing once the runs are in data/<effort>_reasoning_effort/.

    MPLBACKEND=Agg ./venv/bin/python code/figure_effort_ft.py
Output -> figures/figs_sept/fig_effort.{png,pdf}
"""
import importlib.util
import math
import os
import sys
from datetime import datetime

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.lines as mlines
import seaborn as sns
import statsmodels.formula.api as smf

sys.path.insert(0, os.path.expanduser("~/.claude/skills/futuretech-charts/python"))
from futuretech_helpers import use_style, unit_formatter, save_figure

HERE = os.path.dirname(os.path.abspath(__file__))
_fsspec = importlib.util.spec_from_file_location(
    "fs", os.path.join(HERE, "figures_sept.py"))
fs = importlib.util.module_from_spec(_fsspec); _fsspec.loader.exec_module(fs)
_spec = importlib.util.spec_from_file_location("pf", os.path.join(HERE, "paper_figures_71226.py"))
pf = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(pf)
CANON, load_rows, ORIGIN = pf.CANON, pf.load_rows, pf.ORIGIN
DATA = pf.RESULTS_DIR
OUT = os.path.join(os.path.dirname(HERE), "figures", "figs_sept")
FLOOR_C = "#E07A3F"

# MATH-500 excluded, matching figure1_grid_ft.py / figure_forecast_ft.py /
# figure_mechanism_ft.py. The hard-but-doable-10 set contains no MATH-500 problems,
# so this changes no data here -- but the FLOOR does change: pf.canon_short averages
# over all 45 canonical problems including MATH-500's short solutions (303 tok),
# whereas every other figure now draws the floor over the 40 competition problems
# (316 tok). Drawing the 303 line here would put a different floor on this figure
# than on the ones it is meant to be read against.
CANON_KEYS = {t for t in pf.CANON_KEYS if not str(t).startswith("math_500")}
REF = float(np.mean([CANON[t]["min"] for t in CANON_KEYS]))
print(f"fig_effort: floor = {REF:.0f} tok over {len(CANON_KEYS)} competition problems "
      f"(all-45 floor was {pf.canon_short:.0f})")

DATES = {"o3": datetime(2025, 4, 16), "gpt-5": datetime(2025, 8, 7),
         "gpt-5.1": datetime(2025, 11, 13),
         "gpt-5.2": datetime(2025, 12, 11), "gpt-5.4": datetime(2026, 3, 5),
         "gpt-5.5": datetime(2026, 4, 23), "gpt-5.6-sol": datetime(2026, 7, 9),
         "gpt-6-astra": datetime(2026, 9, 1)}
ALL = list(DATES)
# low -> high uses a light->dark crest ramp (more effort = darker)
_c = sns.color_palette("crest", 3)
K_CAP = 8          # attempts per problem per model, matched across efforts
EFFORTS = {"low": ("low_reasoning_effort", _c[0]),
           "medium": ("hard_but_doable_10q_k32", _c[1]),
           "high": ("high_reasoning_effort", _c[2])}


def jpath(eff, m):
    return DATA / EFFORTS[eff][0] / f"{m}_{eff}_thinking_benchmark_hard_but_doable_10.json"


def gather(eff):
    dates, per_model, reg = [], [], []
    for m in ALL:
        p = jpath(eff, m)
        if not os.path.exists(p):
            continue
        month = (DATES[m] - ORIGIN).days / 30.44
        by_id = {}
        for r in load_rows(p):
            tid = str(r["task_id"])
            if tid not in CANON_KEYS:      # competition problems only (no MATH-500)
                continue
            # MATCH k ACROSS EFFORTS. low/high were run at k=8, medium reuses the
            # k=32 hard-but-doable runs, so medium rested on 4x the attempts and its
            # points were steadier for a reason that has nothing to do with effort.
            # Truncating to the first K_CAP attempts puts every line on the same
            # sample size. Attempts are independent samples, so the leading 8 is an
            # unbiased subsample; taking the first is deterministic, which a random
            # draw would not be.
            n_keep = min(K_CAP, len(r["correct"]))
            r = dict(r)
            r["correct"] = r["correct"][:n_keep]
            r["total_completion_tokens"] = r["total_completion_tokens"][:n_keep]
            if r.get("response_texts") is not None:
                r["response_texts"] = r["response_texts"][:n_keep]
            texts = r.get("response_texts", [None] * len(r["correct"]))
            # central rules (figures_sept): zero-thinking traces are valid, and a
            # cap-hit trace is a real attempt that FAILED -- it must not supply a
            # "successful" length to the regression.
            toks = [t for t, x in zip(r["total_completion_tokens"], texts)
                    if fs._trial_ok(t, x)]
            if toks:
                by_id[tid] = float(np.mean(toks))
            for tok, c, txt in zip(r["total_completion_tokens"], r["correct"], texts):
                if not fs._trial_ok(tok, txt) or not fs._trial_correct(tok, c):
                    continue
                if tok > CANON[tid]["min"]:
                    reg.append({"problem": tid, "month": month,
                                "y": math.log(tok - CANON[tid]["min"]), "model": m})
        dates.append(DATES[m]); per_model.append(by_id)
    common = sorted(set.intersection(*[set(d) for d in per_model])) if per_model else []
    traj = {tid: [d[tid] for d in per_model] for tid in common}
    return dates, traj, pd.DataFrame(reg)


def rate(df):
    if df.empty or df["month"].nunique() < 2:
        return None
    b = smf.ols("y ~ month + C(problem)", data=df).fit().params["month"]
    return (1 - math.exp(3 * b)) * 100


use_style()
plt.rcParams.update({"axes.labelsize": 17, "xtick.labelsize": 15, "ytick.labelsize": 15})
fig, ax = plt.subplots(figsize=(12, 6.8))

handles = []
for eff, (d, color) in EFFORTS.items():
    dates, traj, reg = gather(eff)
    if not traj:
        continue
    dx = mdates.date2num(dates)
    macro = [float(np.mean([traj[t][i] for t in traj])) for i in range(len(dates))]
    ax.plot(dx, macro, "-o", color=color, lw=3, ms=9, zorder=5)
    q = rate(reg)
    lab = f"{eff} effort" + (f"  ({q:.0f} %/qtr)" if q is not None else "")
    handles.append(mlines.Line2D([], [], color=color, lw=3, marker="o", ms=8, label=lab))

ax.axhspan(0, REF, color=FLOOR_C, alpha=0.08, zorder=0)
ax.axhline(REF, color=FLOOR_C, lw=2.2, zorder=4)
ax.annotate(f"minimal human derivation ≈ {REF:,.0f} tok",
            (ax.get_xlim()[0], REF), textcoords="offset points", xytext=(8, 8),
            ha="left", va="bottom", fontsize=12, fontweight="bold", color=FLOOR_C)
handles.append(mlines.Line2D([], [], color=FLOOR_C, lw=2.2, label="Minimal human derivation"))

ax.set_ylim(bottom=0)
ax.set_ylabel("Mean output tokens")
ax.set_xlabel("Release date")
ax.yaxis.set_major_formatter(unit_formatter(1e3, "k"))
ax.xaxis.set_major_locator(mdates.MonthLocator(interval=4))
ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
ax.legend(handles=handles, loc="upper right", frameon=True, framealpha=0.95, fontsize=13)
plt.tight_layout()
paths = save_figure(fig, "fig_effort", outdir=OUT)
print("wrote", *paths, sep="\n  ")
