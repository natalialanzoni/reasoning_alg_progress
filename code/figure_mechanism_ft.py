"""Case-study figure (Figure 1 house style, 3 rows x 2 columns) — where do the
efficiency gains come from? Two open-source pairs, one lever changed in each:

  Column 1  SCALE      gpt-oss 20B -> 120B   (same family, ~6x the parameters)
  Column 2  ALGORITHM  GLM 5.2 -> 5.3        (same model size, newer training)

Rows match figure1_grid_ft.py exactly:
  1. accuracy
  2. mean output tokens over correct traces, with the minimal-human-derivation floor
     and the earliest->latest compression ratio
  3. within-problem distribution on the hard-but-doable-10 (k=32): per-problem median
     with IQR band, coloured by the same a-priori difficulty tier

Sample and conventions are inherited from figure1_grid_ft.py so the case study is
directly comparable to the frontier figure:
  - the 40 competition problems (AIME 2026 I/II + HMMT Feb 2026); MATH-500 excluded
  - floor recomputed over those same 40 problems (316 tok, not the all-45 303)
  - tiers: AIME 1-10 medium, AIME 11-15 hard, HMMT very hard
  - a trace needing more than the 40k output cap is re-scored WRONG (it would have
    been cut off before answering). This binds only on GLM, whose provider did not
    enforce the cap; it is a no-op for gpt-oss.

GLM 5.2/5.3 use the HIGH-effort runs. Their 'medium' runs were silently remapped by
the provider and are archived in data/archive/effort_medium_invalid/ — the _high
files are the only comparable pair, and the only ones left in data/.

    MPLBACKEND=Agg ./venv/bin/python code/figure_mechanism_ft.py
Output -> figures/figs_sept/fig_mechanism.{png,pdf}
"""
import importlib.util
import json
import os
import re
import sys

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.lines as mlines

# House style from the VENDORED copy in code/ft_style, not from the skill outside
# the repo -- a clone must reproduce the figures exactly. See its README.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "ft_style"))
try:                                    # house style from the skill, if present
    from futuretech_helpers import use_style, unit_formatter, save_figure
    from futuretech_palette import PRIMARY
    STYLE_SRC = "futuretech-charts skill"
except ModuleNotFoundError:             # only if code/ft_style is missing
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from _ft_style_local import use_style, unit_formatter, save_figure, PRIMARY
    STYLE_SRC = "LOCAL RECONSTRUCTION (_ft_style_local.py)"

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("fs", os.path.join(HERE, "figures_sept.py"))
fs = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(fs)
pf = fs.pf
OUT = os.path.join(os.path.dirname(HERE), "figures", "figs_sept")
D = pf.RESULTS_DIR

TOK = PRIMARY
ACC = "#0E8A8A"           # accuracy — teal, as in figure 1
FLOOR_COLOR = "#E07A3F"   # minimal human derivation — orange
CAP = 40000               # output cap; over-cap => truncated before answering => wrong

# Sample + floor, identical to figure1_grid_ft.py (MATH-500 excluded).
KEYS = {t for t in pf.CANON_KEYS if not str(t).startswith("math_500")}
FLOOR = float(np.mean([pf.CANON[t]["min"] for t in KEYS]))   # o200k, the default


def floor_of(labels):
    """This column's floor in its own token units. gpt-oss is o200k_harmony (verified
    identical to o200k on every canonical solution) and GLM is within 0.1%, so both
    columns land on ~316 -- but resolve it rather than assume it (README item 15)."""
    return pf.mean_floor(labels[-1], KEYS)

# Difficulty tiers — same a-priori rule as figure1_grid_ft.py: HMMT is a harder
# competition than AIME outright, so it ranks above every AIME problem.
TIER_COLOR = {"easy": "#4DAF4A", "medium": "#FDAE61", "hard": "#D7301F", "very hard": "#7F0000"}
TIER_ORDER = ["easy", "medium", "hard", "very hard"]


def human_tier(tid):
    t = str(tid); m = re.search(r"_(\d+)$", t)
    pos = int(m.group(1)) if m else 0
    if t.startswith("math_500"):
        return "easy"
    if t.startswith("aime"):
        return "medium" if pos <= 10 else "hard"
    if t.startswith("hmmt"):
        return "very hard"
    return None


# ---- schema A: GLM (pf.load_rows -> total_completion_tokens / correct) -------
def shallowA(path):
    toks, nc, nt = [], 0, 0
    for r in pf.load_rows(path):
        if str(r["task_id"]) not in KEYS:
            continue
        texts = r.get("response_texts", [None] * len(r["correct"]))
        for tok, c, txt in zip(r["total_completion_tokens"], r["correct"], texts):
            # central rules, not a local copy: duplicating them is what let the cap
            # bug survive in four scripts at once (README run-hygiene 6)
            if not fs._trial_ok(tok, txt, cap=CAP):
                continue
            ok = fs._trial_correct(tok, c, cap=CAP)
            nt += 1; nc += int(ok)
            if ok:
                toks.append(tok)
    return 100 * nc / max(1, nt), float(np.mean(toks))


def hardA(path):
    prob = {}
    for r in pf.load_rows(path):
        pid = str(r["task_id"])
        if pid not in KEYS:
            continue
        texts = r.get("response_texts", [None] * len(r["correct"]))
        toks = [tok for tok, c, txt in zip(r["total_completion_tokens"],
                                           r["correct"], texts)
                if fs._trial_ok(tok, txt, cap=CAP) and fs._trial_correct(tok, c, cap=CAP)]
        if toks:
            prob[pid] = toks
    return prob


# ---- schema B: gpt-oss (results / completions / n_tokens / is_correct) -------
def shallowB(path):
    d = json.load(open(path)); toks, nc, nt = [], 0, 0
    for e in d["results"]:
        if str(e["id"]) not in KEYS:
            continue
        for c in e.get("completions", []):
            tok = c.get("n_tokens", 0)
            if tok < 50:
                continue
            ok = bool(c.get("is_correct")) and tok < CAP   # AT the cap = truncated
            nt += 1; nc += int(ok)
            if ok:
                toks.append(tok)
    return 100 * nc / max(1, nt), float(np.mean(toks))


def hardB(path):
    d = json.load(open(path)); prob = {}
    for e in d["results"]:
        pid = str(e["id"])
        if pid not in KEYS:
            continue
        toks = [c["n_tokens"] for c in e.get("completions", [])
                if c.get("is_correct") and 50 <= c.get("n_tokens", 0) < CAP]
        if toks:
            prob[pid] = toks
    return prob


def col_glm(stems):
    accs, means, hards = [], [], []
    for s in stems:
        a, m = shallowA(D / f"{s}_shallow_pass" / f"{s}_thinking_benchmark_90_high.json")
        accs.append(a); means.append(m)
        hards.append(hardA(D / "hard_but_doable_10q_k32"
                           / f"{s}_thinking_benchmark_hard_but_doable_10_high.json"))
    return accs, means, hards


def col_oss(szs):
    accs, means, hards = [], [], []
    for sz in szs:
        a, m = shallowB(D / f"gpt_oss{sz.upper()}_shallow_pass" / f"gpt-oss-{sz}_re-medium.json")
        accs.append(a); means.append(m)
        hards.append(hardB(D / "hard_but_doable_10q_k32"
                           / f"gpt-oss-{sz}_hard-but-doable-10_re-medium_k=32.json"))
    return accs, means, hards


COLS = [
    ("Scale" + "\n" + r"gpt-oss 20B $\rightarrow$ 120B",
     ["20B", "120B"], col_oss(["20b", "120b"]), "Model size (fixed training recipe)"),
    ("Algorithm" + "\n" + r"GLM 5.2 $\rightarrow$ 5.3",
     ["GLM 5.2", "GLM 5.3"], col_glm(["glm_5_2", "glm_5_3"]), "Model version (fixed size)"),
]

print(f"fig_mechanism: {len(KEYS)} competition problems (MATH-500 excluded), "
      f"floor = {FLOOR:.0f} tok, cap = {CAP}")

use_style()
plt.rcParams.update({"axes.labelsize": 14, "xtick.labelsize": 14, "ytick.labelsize": 12,
                     "axes.titlesize": 16})
# TRANSPOSED 2x3, matching Figure 1: the two levers are ROWS, the three metrics are
# COLUMNS. 12 x 13.5 in becomes 18 x 8.4, a full-width slot instead of most of a page.
# No sharex: each row has its OWN categories (20B/120B vs GLM 5.2/5.3), so the x axis
# is set per panel rather than shared.
fig, axes = plt.subplots(2, 3, figsize=(18, 8.4),
                         gridspec_kw={"hspace": 0.26, "wspace": 0.22})
seen = set()
for row, (title, labels, (accs, means, hards), xlabel) in enumerate(COLS):
    x = list(range(len(labels)))

    a0 = axes[row][0]                                   # Col 1 — accuracy
    a0.plot(x, accs, "-o", color=ACC, lw=2.6, ms=12, zorder=5)
    # the lever names the ROW; the metrics are titled once on the top row
    a0.set_ylabel(title, fontweight="bold", fontsize=13, labelpad=10)
    # data spans 68-86%; 40-104 left half the row empty and flattened both
    # lines into near-horizontal segments, hiding the accuracy gain
    a0.set_ylim(60, 96)
    a0.yaxis.set_major_formatter(unit_formatter(1, "%", "{:.0f}"))
    for xi, yi in zip(x, accs):
        a0.annotate(f"{yi:.0f}%", (xi, yi), textcoords="offset points", xytext=(0, 13),
                    ha="center", fontsize=13, fontweight="bold", color=ACC)

    a1 = axes[row][1]                                   # Col 2 — mean + floor
    a1.plot(x, means, "-o", color=TOK, lw=3, ms=12, zorder=5)
    col_floor = floor_of(labels)
    a1.axhline(col_floor, color=FLOOR_COLOR, lw=2, zorder=3)
    a1.set_ylim(0, max(means) * 1.38)                   # headroom for the label
    a1.yaxis.set_major_formatter(unit_formatter(1e3, "k"))
    ratio = means[0] / means[-1] if means[-1] else float("nan")
    lbl = f"{ratio:.1f}× fewer tokens" if ratio >= 1.15 else f"≈flat ({ratio:.1f}×)"
    a1.annotate(lbl, xy=(0.96, 0.95), xycoords="axes fraction", ha="right", va="top",
                fontsize=14.5, fontweight="bold", color=TOK, zorder=7,
                bbox=dict(boxstyle="round,pad=0.3", fc="white", ec=TOK, alpha=0.9))
    a1.annotate(f"minimal human derivation ≈ {col_floor:.0f} tok", (x[-1], col_floor),
                textcoords="offset points", xytext=(0, 6), ha="right", va="bottom",
                fontsize=9.5, fontweight="bold", color=FLOOR_COLOR)
    print(f"  {labels[0]:>8s} -> {labels[-1]:<8s} acc {accs[0]:.1f}% -> {accs[-1]:.1f}%"
          f"   tokens {means[0]:.0f} -> {means[-1]:.0f} = {ratio:.1f}x")

    a2 = axes[row][2]                                   # Col 3 — per-problem by tier
    common = sorted(set.intersection(*[set(h) for h in hards])) if hards else []
    for pid in common:
        tier = human_tier(pid)
        if not tier:
            continue
        seen.add(tier)
        c = TIER_COLOR[tier]
        med = [float(np.median(h[pid])) for h in hards]
        lo = [float(np.percentile(h[pid], 25)) for h in hards]
        hi = [float(np.percentile(h[pid], 75)) for h in hards]
        a2.fill_between(x, lo, hi, color=c, alpha=0.14, lw=0, zorder=1)
        a2.plot(x, med, color=c, lw=2.2, alpha=0.95, zorder=2)
    a2.set_ylim(0, CAP)
    a2.yaxis.set_major_formatter(unit_formatter(1e3, "k"))
    # every panel in the row carries the row's own categories; the lever description
    # goes under the middle panel so it is not printed three times
    for _i, _a in enumerate((a0, a1, a2)):
        _a.set_xticks(x); _a.set_xticklabels(labels, fontweight="bold")
        _a.set_xlim(-0.3, len(labels) - 0.7)
        if _i == 1:
            _a.set_xlabel(xlabel)

axes[0][0].set_title("Accuracy", fontsize=13)
axes[0][1].set_title("Mean output tokens (correct traces)", fontsize=13)
axes[0][2].set_title("Output tokens by problem (hard-but-doable)", fontsize=13)
keys = [k for k in TIER_ORDER if k in seen]
handles = [mlines.Line2D([], [], color=TIER_COLOR[k], lw=3, label=k) for k in keys]
axes[-1][2].legend(handles=handles, loc="upper right", fontsize=10, frameon=True,
                   framealpha=0.95, title="difficulty")
paths = save_figure(fig, "fig_mechanism", outdir=OUT)
print("wrote", *paths, sep="\n  ")
