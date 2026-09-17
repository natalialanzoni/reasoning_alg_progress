"""
Mechanism figure (Figure 1 house style, 3 rows x 2 columns) — two open-source case
studies of reasoning compression, side by side:
  Column 1  ALGORITHM  GLM 5.2 -> 5.3   (fixed model size, matched HIGH effort)
  Column 2  SCALE      gpt-oss 20B -> 120B

Rows: (1) accuracy, (2) mean output tokens + minimal-human-derivation floor (+ N×
label), (3) within-problem distribution (hard-but-doable-10, k=32) by human_tier.

Honest reading: BOTH levers mainly just make the reasoning more concise (row 2 drops);
algorithm compresses far more than scale; accuracy (row 1) is roughly flat for both —
so this is "compression, more vs less", not "two different mechanisms". Rows 1-2 use
the full benchmark-90; row 3 the hard-but-doable-10. Tokens clipped/re-scored at 40k.

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

sys.path.insert(0, os.path.expanduser("~/.claude/skills/futuretech-charts/python"))
from futuretech_helpers import use_style, unit_formatter, save_figure
from futuretech_palette import PRIMARY

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("fs", os.path.join(HERE, "figures_sept.py"))
fs = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(fs)
pf = fs.pf
OUT = os.path.join(os.path.dirname(HERE), "figures", "figs_sept")
D = pf.RESULTS_DIR
HARD = "hard_but_doable_10q_k32"
CAP = 40000
TOK = PRIMARY
ACC = "#0E8A8A"
FLOOR_COLOR = "#E07A3F"
FLOOR = pf.canon_short
TIER_COLOR = {"easy": "#4DAF4A", "medium": "#FDAE61", "hard": "#F16913", "very hard": "#B2182B"}
TIER_ORDER = ["easy", "medium", "hard", "very hard"]


def _eff_pos(tid):
    t = str(tid); m = re.search(r"_(\d+)$", t); pos = int(m.group(1)) if m else 0
    if t.startswith("aime"):     return pos
    if t.startswith("hmmt"):     return pos + 5
    if t.startswith("math_500"): return 2
    return 15


def human_tier(tid):
    e = _eff_pos(tid)
    return "easy" if e <= 5 else "medium" if e <= 9 else "hard" if e <= 12 else "very hard"


# ---- schema-A (GLM) loaders -------------------------------------------------
def shallowA(path):
    toks, nc, nt = [], 0, 0
    for r in pf.load_rows(path):
        if str(r["task_id"]) not in pf.CANON_KEYS:
            continue
        for tok, c in zip(r["total_completion_tokens"], r["correct"]):
            if tok < 50:
                continue
            ok = bool(c) and tok <= CAP
            nt += 1; nc += int(ok)
            if ok:
                toks.append(tok)
    return 100 * nc / max(1, nt), float(np.mean(toks))


def hardA(path):
    prob = {}
    for r in pf.load_rows(path):
        toks = [tok for tok, c in zip(r["total_completion_tokens"], r["correct"])
                if bool(c) and 50 <= tok <= CAP]
        if toks:
            prob[str(r["task_id"])] = toks
    return prob


# ---- schema-B (gpt-oss) loaders --------------------------------------------
def shallowB(path):
    d = json.load(open(path)); toks, nc, nt = [], 0, 0
    for e in d["results"]:
        if str(e["id"]) not in pf.CANON_KEYS:
            continue
        for c in e.get("completions", []):
            tok = c.get("n_tokens", 0)
            if tok < 50:
                continue
            ok = bool(c.get("is_correct")) and tok <= CAP
            nt += 1; nc += int(ok)
            if ok:
                toks.append(tok)
    return 100 * nc / max(1, nt), float(np.mean(toks))


def hardB(path):
    d = json.load(open(path)); prob = {}
    for e in d["results"]:
        toks = [c["n_tokens"] for c in e.get("completions", [])
                if c.get("is_correct") and 50 <= c.get("n_tokens", 0) <= CAP]
        if toks:
            prob[str(e["id"])] = toks
    return prob


def col_glm(stems):
    accs, means, hards = [], [], []
    for s in stems:
        a, m = shallowA(D / f"{s}_shallow_pass" / f"{s}_thinking_benchmark_90_high.json")
        accs.append(a); means.append(m)
        hards.append(hardA(D / HARD / f"{s}_thinking_benchmark_hard_but_doable_10_high.json"))
    return accs, means, hards


def col_oss(szs):
    accs, means, hards = [], [], []
    for sz in szs:
        sd = f"gpt_oss{sz.upper()}_shallow_pass"
        a, m = shallowB(D / sd / f"gpt-oss-{sz}_re-medium.json")
        accs.append(a); means.append(m)
        hards.append(hardB(D / HARD / f"gpt-oss-{sz}_hard-but-doable-10_re-medium_k=32.json"))
    return accs, means, hards


COLS = [
    (r"Algorithm  ·  GLM 5.2 $\rightarrow$ 5.3" + "\n(fixed model size)",
     ["GLM 5.2", "GLM 5.3"], col_glm(["glm_5_2", "glm_5_3"]), "Version (fixed size)"),
    (r"Scale  ·  gpt-oss 20B $\rightarrow$ 120B" + "\n(model size)",
     ["20B", "120B"], col_oss(["20b", "120b"]), "Model parameters"),
]

use_style()
plt.rcParams.update({"axes.labelsize": 14, "xtick.labelsize": 14, "ytick.labelsize": 12,
                     "axes.titlesize": 15})
fig, axes = plt.subplots(3, 2, figsize=(12, 13.5), sharex="col",
                         gridspec_kw={"hspace": 0.13, "wspace": 0.2})
seen = set()
for col, (title, labels, (accs, means, hards), xlabel) in enumerate(COLS):
    x = list(range(len(labels)))

    a0 = axes[0][col]
    a0.plot(x, accs, "-o", color=ACC, lw=2.6, ms=12, zorder=5)
    a0.set_title(title, fontweight="bold"); a0.set_ylim(60, 100)
    a0.yaxis.set_major_formatter(unit_formatter(1, "%", "{:.0f}"))
    for xi, yi in zip(x, accs):
        a0.annotate(f"{yi:.0f}%", (xi, yi), textcoords="offset points", xytext=(0, 12),
                    ha="center", fontsize=13, fontweight="bold", color=ACC)

    a1 = axes[1][col]
    a1.plot(x, means, "-o", color=TOK, lw=3, ms=12, zorder=5)
    a1.axhline(FLOOR, color=FLOOR_COLOR, lw=2, zorder=3)
    a1.set_ylim(bottom=0); a1.yaxis.set_major_formatter(unit_formatter(1e3, "k"))
    ratio = means[0] / means[-1] if means[-1] else float("nan")
    a1.annotate(f"{ratio:.1f}× fewer tokens", xy=(0.95, 0.9), xycoords="axes fraction",
                ha="right", va="top", fontsize=14, fontweight="bold", color=TOK,
                bbox=dict(boxstyle="round,pad=0.3", fc="white", ec=TOK, alpha=0.9))
    a1.annotate(f"minimal human derivation ≈ {FLOOR:.0f} tok", (x[-1], FLOOR),
                textcoords="offset points", xytext=(0, 5), ha="right", va="bottom",
                fontsize=9.5, fontweight="bold", color=FLOOR_COLOR)

    a2 = axes[2][col]
    common = sorted(set.intersection(*[set(h) for h in hards])) if hards else []
    for pid in common:
        tier = human_tier(pid); seen.add(tier)
        c = TIER_COLOR.get(tier, "#888888")
        med = [float(np.median(h[pid])) for h in hards]
        lo = [float(np.percentile(h[pid], 25)) for h in hards]
        hi = [float(np.percentile(h[pid], 75)) for h in hards]
        a2.fill_between(x, lo, hi, color=c, alpha=0.14, lw=0, zorder=1)
        a2.plot(x, med, color=c, lw=2.2, alpha=0.95, zorder=2)
    a2.set_ylim(0, 40000); a2.yaxis.set_major_formatter(unit_formatter(1e3, "k"))
    a2.set_xticks(x); a2.set_xticklabels(labels, fontweight="bold")
    a2.set_xlim(-0.3, len(labels) - 0.7); a2.set_xlabel(xlabel)

axes[0][0].set_ylabel("Accuracy")
axes[1][0].set_ylabel("Mean output tokens")
axes[2][0].set_ylabel("Output tokens\n(hard-but-doable, per problem)")
keys = [k for k in TIER_ORDER if k in seen]
handles = [mlines.Line2D([], [], color=TIER_COLOR[k], lw=3, label=k) for k in keys]
axes[2][1].legend(handles=handles, loc="upper right", fontsize=11, frameon=True,
                  framealpha=0.95, title="difficulty")
paths = save_figure(fig, "fig_mechanism", outdir=OUT)
print("wrote", *paths, sep="\n  ")
for (title, labels, (accs, means, hards), _) in COLS:
    print(f"  {labels}: acc {accs}  mean {[round(m) for m in means]}")
