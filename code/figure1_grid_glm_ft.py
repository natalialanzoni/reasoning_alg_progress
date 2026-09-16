"""
Figure 1 (3x3, FutureTech house style) — adds a GLM (open-source) column next to
OpenAI (GPT) and Anthropic (Opus + Fable), so the frontier efficiency trend can be
compared against open source.

GLM 5.2 / 5.3 are EXCLUDED: those runs used an effort parameter (they were re-run
on 'high' to get comparable settings) and are not comparable to the medium-thinking
frontier runs here. Included: GLM 4.5, 4.6, 4.7, 5, 5.1.

GLM ran WITHOUT an effective 40k cap on some providers (max seen ~79k). To match
the hard 40k cap OpenAI/Anthropic had, GLM is TRUNCATED at 40k: a trace that needed
>40k tokens to answer would have been cut off before answering under that cap, so
it is re-scored as WRONG (and its token count clipped to 40k). This is a no-op for
the frontier runs, which never exceed 40k.

Rows: (1) accuracy, (2) mean output tokens + human-derivation floor, (3) per-problem
IQR bands on the hard-but-doable-10 (k=32), colored by human-solve-rate difficulty.
Tokens are correct traces only (reasoning + answer).

    MPLBACKEND=Agg ./venv/bin/python code/figure1_grid_glm_ft.py
Output -> figures/figs_sept/fig1_grid_glm.{png,pdf}
"""
import importlib.util
import os
import re
import sys
from datetime import datetime

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.lines as mlines

sys.path.insert(0, os.path.expanduser("~/.claude/skills/futuretech-charts/python"))
from futuretech_helpers import use_style, unit_formatter, save_figure
from futuretech_palette import PRIMARY

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("fs", os.path.join(HERE, "figures_sept.py"))
fs = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(fs)
pf = fs.pf
OUT = os.path.join(os.path.dirname(HERE), "figures", "figs_sept")
_D = pf.RESULTS_DIR

TOK = PRIMARY
ACC = "#0E8A8A"            # accuracy line — teal
FLOOR_COLOR = "#E07A3F"    # minimal-human-derivation floor — orange
FLOOR = pf.canon_short     # ~303 tok over the 45 canonical problems
CLIP = 40000               # match the hard output cap (GLM providers ignored it)
TIER_COLOR = {"easy": "#4DAF4A", "medium": "#FDAE61", "hard": "#D7301F", "very hard": "#7F0000"}
TIER_ORDER = ["easy", "medium", "hard", "very hard"]


def _eff_pos(tid):
    t = str(tid); m = re.search(r"_(\d+)$", t); pos = int(m.group(1)) if m else 0
    if t.startswith("aime"):      return pos
    if t.startswith("hmmt"):      return pos + 5
    if t.startswith("math_500"):  return 2
    return 15


def human_tier(tid):
    e = _eff_pos(tid)
    return "easy" if e <= 5 else "medium" if e <= 9 else "hard" if e <= 12 else "very hard"


# ---- families (columns) ---------------------------------------------------
FAB_S = [("Fable 5.1", datetime(2026, 9, 1), _D / "fable5.1_shallow_pass" / "claude-fable-5-1_medium_thinking_benchmark.json")]
FAB_H = [("claude-fable-5-1", datetime(2026, 9, 1), _D / "hard_but_doable_10q_k32" / "claude-fable-5-1_medium_thinking_benchmark_hard_but_doable_10.json")]
ANTH_S = sorted(pf.OPUS_MODELS + FAB_S, key=lambda t: t[1])
ANTH_H = sorted(pf.OPUS_HARD10_K32 + FAB_H, key=lambda t: t[1])

_GLM_STEMS = [("GLM 4.5", "glm_4_5", datetime(2025, 7, 1)), ("GLM 4.6", "glm_4_6", datetime(2025, 9, 1)),
              ("GLM 4.7", "glm_4_7", datetime(2025, 12, 1)), ("GLM 5", "glm_5", datetime(2026, 2, 1)),
              ("GLM 5.1", "glm_5_1", datetime(2026, 4, 1))]   # official dates; 5.2/5.3 excluded (effort)
GLM_S = [(lab, d, _D / f"{s}_shallow_pass" / f"{s}_thinking_benchmark_90.json") for lab, s, d in _GLM_STEMS]
GLM_H = [(lab, d, _D / "hard_but_doable_10q_k32" / f"{s}_thinking_benchmark_hard_but_doable_10.json")
         for lab, s, d in _GLM_STEMS]

FAMILIES = [("OpenAI (GPT)", pf.MAIN_K8, fs.GPT_HARD),
            ("Anthropic (Opus + Fable)", ANTH_S, ANTH_H),
            ("GLM (open source)", GLM_S, GLM_H)]


def clean_label(name):
    if name.startswith("claude-opus-"):  return "Opus " + name[len("claude-opus-"):].replace("-", ".")
    if name.startswith("claude-fable-"): return "Fable " + name[len("claude-fable-"):].replace("-", ".")
    if name.startswith("gpt-"):          return "GPT-" + name[len("gpt-"):]
    return name


def shallow_dist(model_files):
    """Per model: date, mean correct-trace length (clip 40k), accuracy (45 canonical).

    A trial counts as a real ATTEMPT if it generated output (tok >= 50); an empty
    answer then counts as WRONG. We do NOT use fs._trial_ok here for the denominator,
    because it drops empty-text trials -- for GLM those are truncated-at-40k failures
    (17-26% of runs) and dropping them would inflate accuracy from ~73% to ~99%.
    """
    labels, dates, mean, acc = [], [], [], []
    for label, date, path in model_files:
        labels.append(clean_label(label))
        toks, nc, nt = [], 0, 0
        for r in pf.load_rows(path):
            if str(r["task_id"]) not in pf.CANON_KEYS:
                continue
            for tok, c in zip(r["total_completion_tokens"], r["correct"]):
                if tok < 50:                       # degenerate / API failure -> exclude
                    continue
                ok = bool(c) and tok <= CLIP        # over-cap => truncated before answering => wrong
                nt += 1; nc += int(ok)
                if ok:
                    toks.append(tok)
        dates.append(date); mean.append(np.mean(toks)); acc.append(100 * nc / max(1, nt))
    return mdates.date2num(dates), labels, mean, acc


def hard_perproblem(hard_files):
    """Per problem: (dates, median, p25, p75) over models (correct traces, clip 40k)."""
    dates = [d for _, d, _ in hard_files]
    prob = {}
    for i, (label, date, path) in enumerate(hard_files):
        for r in pf.load_rows(path):
            pid = str(r["task_id"])
            toks = [tok for tok, c in zip(r["total_completion_tokens"], r["correct"])
                    if bool(c) and 50 <= tok <= CLIP]   # correct AND within the 40k cap
            if toks:
                d = prob.setdefault(pid, {"i": [], "med": [], "lo": [], "hi": []})
                d["i"].append(i); d["med"].append(np.median(toks))
                d["lo"].append(np.percentile(toks, 25)); d["hi"].append(np.percentile(toks, 75))
    return mdates.date2num(dates), prob


use_style()
plt.rcParams.update({"axes.labelsize": 15, "xtick.labelsize": 12, "ytick.labelsize": 13,
                     "axes.titlesize": 17})
ncol = len(FAMILIES)
fig, axes = plt.subplots(3, ncol, figsize=(7.3 * ncol, 13.5), sharex="col",
                         gridspec_kw={"hspace": 0.18, "wspace": 0.24})
seen = set()
for col, (title, shallow, hard) in enumerate(FAMILIES):
    dx, labs, mean, acc = shallow_dist(shallow)

    a0 = axes[0][col]                                       # Row 1 — accuracy
    a0.plot(dx, acc, "-o", color=ACC, lw=2.6, ms=8, zorder=5)
    a0.set_ylim(58, 103); a0.set_title(title)
    a0.yaxis.set_major_formatter(unit_formatter(1, "%", "{:.0f}"))
    for i, (xi, yi, name) in enumerate(zip(dx, acc, labs)):
        dy, va = [(-16, "top"), (-32, "top"), (-48, "top")][i % 3]
        a0.annotate(name, (xi, yi), textcoords="offset points", xytext=(0, dy),
                    ha="center", va=va, fontsize=9, fontweight="bold", color=ACC, zorder=8,
                    bbox=dict(boxstyle="round,pad=0.12", fc="white", ec="none", alpha=0.8),
                    arrowprops=dict(arrowstyle="-", color=ACC, lw=0.6, alpha=0.6, shrinkA=1, shrinkB=3))

    a1 = axes[1][col]                                       # Row 2 — mean + floor
    a1.plot(dx, mean, "-o", color=TOK, lw=3, ms=8, zorder=5)
    a1.axhline(FLOOR, color=FLOOR_COLOR, lw=2, zorder=3)
    a1.set_ylim(bottom=0)
    a1.yaxis.set_major_formatter(unit_formatter(1e3, "k"))
    a1.annotate(f"minimal human derivation ≈ {FLOOR:.0f} tok", (dx[-1], FLOOR),
                textcoords="offset points", xytext=(0, 5), ha="right", va="bottom",
                fontsize=10, fontweight="bold", color=FLOOR_COLOR, zorder=6)

    a2 = axes[2][col]                                       # Row 3 — per-problem by tier
    hdx, prob = hard_perproblem(hard)
    for pid, d in prob.items():
        k = human_tier(pid); seen.add(k)
        c = TIER_COLOR.get(k, "#888888")
        xs = hdx[d["i"]]
        a2.fill_between(xs, d["lo"], d["hi"], color=c, alpha=0.13, lw=0, zorder=1)
        a2.plot(xs, d["med"], color=c, lw=2.1, alpha=0.95, zorder=2)
    a2.set_ylim(0, 40000)
    a2.yaxis.set_major_formatter(unit_formatter(1e3, "k"))
    a2.xaxis.set_major_locator(mdates.MonthLocator(interval=4))
    a2.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    a2.set_xlabel("Release date")

axes[0][0].set_ylabel("Accuracy")
axes[1][0].set_ylabel("Mean output tokens")
axes[2][0].set_ylabel("Output tokens\n(hard-but-doable, per problem)")
keys = [k for k in TIER_ORDER if k in seen]
handles = [mlines.Line2D([], [], color=TIER_COLOR[k], lw=3, label=k) for k in keys]
axes[2][ncol - 1].legend(handles=handles, loc="upper right", fontsize=11, ncol=1,
                         frameon=True, framealpha=0.95, title="difficulty")

paths = save_figure(fig, "fig1_grid_glm", outdir=OUT)
print("wrote", *paths, sep="\n  ")
