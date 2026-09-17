"""
Figure 1 (3-row, FutureTech house style) — open source gpt-oss, 20B -> 120B size
scaling. Mirrors the main figure1_grid layout:
  Row 1: accuracy
  Row 2: mean output tokens + minimal-human-derivation floor (+ N× fewer label)
  Row 3: within-problem distribution (hard-but-doable-10, k=32), per-problem IQR
         bands colored by human-solve-rate difficulty (human_tier).

Schema B (local GPU harness): top-level dict with `results`; each result is one
problem with `id` and a `completions` list of {n_tokens, finish_reason,
extracted_answer, is_correct}. Tokens clipped at 40k for comparability with the
40k-capped GPT/Opus runs; a trace needing >40k is re-scored WRONG.

    MPLBACKEND=Agg ./venv/bin/python code/figure1_oss_ft.py
Output -> figures/figs_sept/fig1_oss.{png,pdf}
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

TOK = PRIMARY
ACC = "#0E8A8A"
FLOOR_COLOR = "#E07A3F"
FLOOR = pf.canon_short
CLIP = 40000
TIER_COLOR = {"easy": "#4DAF4A", "medium": "#FDAE61", "hard": "#F16913", "very hard": "#B2182B"}
TIER_ORDER = ["easy", "medium", "hard", "very hard"]

HARD = "hard_but_doable_10q_k32"
MODELS = [("gpt-oss-20b", "20B", D / f"{HARD}/gpt-oss-20b_hard-but-doable-10_re-medium_k=32.json",
           D / "gpt_oss20B_shallow_pass/gpt-oss-20b_re-medium.json"),
          ("gpt-oss-120b", "120B", D / f"{HARD}/gpt-oss-120b_hard-but-doable-10_re-medium_k=32.json",
           D / "gpt_oss120B_shallow_pass/gpt-oss-120b_re-medium.json")]
XLABEL = "Model parameters"
TITLE = r"gpt-oss (open source): 20B $\rightarrow$ 120B"


def _eff_pos(tid):
    t = str(tid); m = re.search(r"_(\d+)$", t); pos = int(m.group(1)) if m else 0
    if t.startswith("aime"):     return pos
    if t.startswith("hmmt"):     return pos + 5
    if t.startswith("math_500"): return 2
    return 15


def human_tier(tid):
    e = _eff_pos(tid)
    return "easy" if e <= 5 else "medium" if e <= 9 else "hard" if e <= 12 else "very hard"


def oss_shallow(path):
    """Accuracy + mean correct-trace tokens over CANON (clip 40k, over-cap = wrong)."""
    d = json.load(open(path)); toks, nc, nt = [], 0, 0
    for e in d["results"]:
        if str(e["id"]) not in pf.CANON_KEYS:
            continue
        for c in e.get("completions", []):
            tok = c.get("n_tokens", 0)
            if tok < 50:
                continue
            ok = bool(c.get("is_correct")) and tok <= CLIP
            nt += 1; nc += int(ok)
            if ok:
                toks.append(tok)
    return 100 * nc / max(1, nt), float(np.mean(toks))


def oss_hard(path):
    d = json.load(open(path)); prob = {}
    for e in d["results"]:
        toks = [c["n_tokens"] for c in e.get("completions", [])
                if c.get("is_correct") and 50 <= c.get("n_tokens", 0) <= CLIP]
        if toks:
            prob[str(e["id"])] = toks
    return prob


def build():
    accs, means, hards, labels = [], [], [], []
    for label, sz, hard_path, sh_path in MODELS:
        a, m = oss_shallow(sh_path); accs.append(a); means.append(m)
        hards.append(oss_hard(hard_path)); labels.append(sz)
    x = list(range(len(MODELS)))

    use_style()
    plt.rcParams.update({"axes.labelsize": 15, "xtick.labelsize": 15, "ytick.labelsize": 13})
    fig, axes = plt.subplots(3, 1, figsize=(7.2, 13.5), sharex=True,
                             gridspec_kw={"hspace": 0.14})

    a0 = axes[0]
    a0.plot(x, accs, "-o", color=ACC, lw=2.6, ms=11, zorder=5)
    a0.set_ylabel("Accuracy"); a0.set_title(TITLE)
    a0.yaxis.set_major_formatter(unit_formatter(1, "%", "{:.0f}"))
    for xi, yi in zip(x, accs):
        a0.annotate(f"{yi:.0f}%", (xi, yi), textcoords="offset points", xytext=(0, 11),
                    ha="center", fontsize=13, fontweight="bold", color=ACC)
    a0.margins(y=0.25)

    a1 = axes[1]
    a1.plot(x, means, "-o", color=TOK, lw=3, ms=11, zorder=5)
    a1.axhline(FLOOR, color=FLOOR_COLOR, lw=2, zorder=3)
    a1.set_ylabel("Mean output tokens"); a1.set_ylim(bottom=0)
    a1.yaxis.set_major_formatter(unit_formatter(1e3, "k"))
    ratio = means[0] / means[-1] if means[-1] else float("nan")
    lbl = (f"{ratio:.1f}× fewer tokens" if ratio >= 1.15
           else f"{1/ratio:.1f}× more tokens" if ratio <= 0.87 else f"≈flat ({ratio:.1f}×)")
    a1.annotate(lbl, xy=(0.96, 0.9), xycoords="axes fraction", ha="right", va="top",
                fontsize=15, fontweight="bold", color=TOK,
                bbox=dict(boxstyle="round,pad=0.3", fc="white", ec=TOK, alpha=0.9))
    a1.annotate(f"minimal human derivation ≈ {FLOOR:.0f} tok", (x[-1], FLOOR),
                textcoords="offset points", xytext=(0, 6), ha="right", va="bottom",
                fontsize=10, fontweight="bold", color=FLOOR_COLOR)

    a2 = axes[2]
    seen = set()
    common = sorted(set.intersection(*[set(h) for h in hards])) if hards else []
    for pid in common:
        tier = human_tier(pid); seen.add(tier)
        c = TIER_COLOR.get(tier, "#888888")
        med = [float(np.median(h[pid])) for h in hards]
        lo = [float(np.percentile(h[pid], 25)) for h in hards]
        hi = [float(np.percentile(h[pid], 75)) for h in hards]
        a2.fill_between(x, lo, hi, color=c, alpha=0.14, lw=0, zorder=1)
        a2.plot(x, med, color=c, lw=2.2, alpha=0.95, zorder=2)
    a2.set_ylabel("Output tokens\n(hard-but-doable, per problem)")
    a2.set_ylim(0, 40000); a2.yaxis.set_major_formatter(unit_formatter(1e3, "k"))
    a2.set_xticks(x); a2.set_xticklabels(labels, fontweight="bold")
    a2.set_xlim(-0.25, len(MODELS) - 0.75); a2.set_xlabel(XLABEL)
    keys = [k for k in TIER_ORDER if k in seen]
    handles = [mlines.Line2D([], [], color=TIER_COLOR[k], lw=3, label=k) for k in keys]
    a2.legend(handles=handles, loc="upper right", fontsize=11, frameon=True,
              framealpha=0.95, title="difficulty")

    paths = save_figure(fig, "fig1_oss", outdir=OUT)
    print("wrote", *paths, sep="\n  ")


build()
