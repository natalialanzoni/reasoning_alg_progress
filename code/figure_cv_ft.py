"""
Within-problem consistency over generations (FutureTech house style).

For each model we compute the coefficient of variation (CV = sd/mean) of the
correct-trace token counts within each hard-but-doable problem, then average the
CV over the 10 problems. Falling CV = the model solves the same problem with
increasingly consistent length. One line per family.

    MPLBACKEND=Agg ./venv/bin/python code/figure_cv_ft.py
Output -> figures/figs_sept/fig_cv.{png,pdf}
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
_spec = importlib.util.spec_from_file_location("pf", os.path.join(HERE, "paper_figures_71226.py"))
pf = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(pf)
HD = pf.RESULTS_DIR / "hard_but_doable_10q_k32"
OUT = os.path.join(os.path.dirname(HERE), "figures", "figs_sept")
OAI_C, ANT_C = CATEGORICAL[0], CATEGORICAL[1]


def clean(name):
    if name.startswith("claude-opus-"):
        return "Opus " + name[len("claude-opus-"):].replace("-", ".")
    if name.startswith("claude-fable-"):
        return "Fable " + name[len("claude-fable-"):].replace("-", ".")
    return "GPT-" + name[len("gpt-"):] if name.startswith("gpt-") else name


GPT = [("o3", datetime(2025, 4, 16)), ("gpt-5", datetime(2025, 8, 7)),
       ("gpt-5.2", datetime(2025, 12, 11)), ("gpt-5.4", datetime(2026, 3, 5)),
       ("gpt-5.5", datetime(2026, 4, 23)), ("gpt-5.6-sol", datetime(2026, 7, 9)),
       ("gpt-6-astra", datetime(2026, 9, 1))]
ANT = [("claude-opus-4-5", datetime(2025, 11, 24)), ("claude-opus-4-6", datetime(2026, 2, 5)),
       ("claude-opus-4-7", datetime(2026, 4, 16)), ("claude-opus-4-8", datetime(2026, 5, 28)),
       ("claude-opus-5", datetime(2026, 7, 24)), ("claude-fable-5-1", datetime(2026, 9, 1))]


def mean_cv(m):
    p = HD / f"{m}_medium_thinking_benchmark_hard_but_doable_10.json"
    if not os.path.exists(p):
        return None
    cvs = []
    for r in pf.load_rows(p):
        rt = r.get("response_texts", [None] * len(r["correct"]))
        toks = [t for t, c, txt in zip(r["total_completion_tokens"], r["correct"], rt)
                if c and t >= 50 and not (txt is not None and not str(txt).strip())]
        if len(toks) >= 3:
            cvs.append(np.std(toks) / np.mean(toks))
    return float(np.mean(cvs)) if cvs else None


use_style()
plt.rcParams.update({"axes.labelsize": 17, "xtick.labelsize": 15, "ytick.labelsize": 15})
fig, ax = plt.subplots(figsize=(11, 6.5))

handles = []
for fam, models, color in [("OpenAI (GPT)", GPT, OAI_C), ("Anthropic (Opus + Fable)", ANT, ANT_C)]:
    pts = [(d, mean_cv(m)) for m, d in models]
    pts = [(d, c) for d, c in pts if c is not None]
    dx = mdates.date2num([d for d, _ in pts])
    ax.plot(dx, [c for _, c in pts], "-o", color=color, lw=3, ms=9, zorder=5)
    handles.append(mlines.Line2D([], [], color=color, lw=3, marker="o", ms=8, label=fam))

ax.set_ylim(bottom=0)
ax.set_ylabel("Within-problem CV of trace length")
ax.set_xlabel("Release date")
ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
ax.legend(handles=handles, loc="upper right", frameon=True, framealpha=0.95, fontsize=14)
plt.tight_layout()
paths = save_figure(fig, "fig_cv", outdir=OUT)
print("wrote", *paths, sep="\n  ")
