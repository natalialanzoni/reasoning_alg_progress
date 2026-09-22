"""
Figure 2 (FutureTech house style): the per-problem token distributions of the
hard-but-doable set collapsing toward the canonical floor over model generations.

Two rows (OpenAI | Anthropic).  Within each row, one violin per model (columns)
of the hard-but-doable trial token counts, in a cohesive crest palette that
darkens with each generation.  Faint threads trace each individual problem's
mean falling; a dashed line marks the canonical solution floor for that set.

    MPLBACKEND=Agg ./venv/bin/python code/figure2_ft.py
Output -> figures/figs_sept/fig2_hard_distributions.{png,pdf}
"""
import importlib.util
import os
import sys
from datetime import datetime

import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

sys.path.insert(0, os.path.expanduser("~/.claude/skills/futuretech-charts/python"))
try:                                    # house style from the skill, if present
    from futuretech_helpers import use_style, unit_formatter, save_figure
    from futuretech_palette import PRIMARY
    STYLE_SRC = "futuretech-charts skill"
except ModuleNotFoundError:             # replication machines: local stand-in
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from _ft_style_local import use_style, unit_formatter, save_figure, PRIMARY
    STYLE_SRC = "LOCAL RECONSTRUCTION (_ft_style_local.py)"

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("fs", os.path.join(HERE, "figures_sept.py"))
fs = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(fs)
pf = fs.pf
OUT = os.path.join(os.path.dirname(HERE), "figures", "figs_sept")
_D = pf.RESULTS_DIR

FLOOR_C = "#C1352B"     # canonical-floor line
YCLIP = 25000           # shared token axis; clip the long early-generation tails

# Anthropic hard-but-doable = Opus + Fable, date-ordered (matches Figure 1).
FABLE_HARD = [
    ("claude-fable-5-1", datetime(2026, 9, 1), _D / "hard_but_doable_10q_k32" / "claude-fable-5-1_medium_thinking_benchmark_hard_but_doable_10.json"),
]
GPT_HARD = fs.GPT_HARD
ANTH_HARD = sorted(pf.OPUS_HARD10_K32 + FABLE_HARD, key=lambda t: t[1])


def clean_label(name):
    if name.startswith("claude-opus-"):
        return "Opus " + name[len("claude-opus-"):].replace("-", ".")
    if name.startswith("claude-fable-"):
        return "Fable " + name[len("claude-fable-"):].replace("-", ".")
    if name.startswith("gpt-"):
        return "GPT-" + name[len("gpt-"):]
    return name


def model_samples(path):
    """Pooled trial token counts and per-problem means for *valid* trials.

    A trial is valid if it produced a real answer: non-empty response text and
    >= MIN_TOK tokens.  This (a) keeps legit zero-thinking short answers that the
    old `thinking_tokens>0` filter wrongly dropped, and (b) removes empty/0-token
    glitches and sub-100-token degenerate runs.
    """
    # Use the central rule rather than re-implementing it: fs._trial_ok decides
    # whether the trial happened, fs._trial_correct whether it succeeded (a cap-hit
    # trace is a real attempt that FAILED, so it can never be a "success" length).
    pooled, pmean = [], {}
    for r in pf.load_rows(path):
        n = len(r["correct"])
        texts = r.get("response_texts", [None] * n)
        toks = [tok for tok, c, txt in zip(r["total_completion_tokens"], r["correct"], texts)
                if fs._trial_ok(tok, txt)
                and ((not CORRECT_ONLY) or fs._trial_correct(tok, c))]
        if toks:
            pooled.extend(toks)
            pmean[str(r["task_id"])] = float(np.mean(toks))
    return pooled, pmean


def canonical_floor(keys, label=None):
    ks = [k for k in keys if k in pf.CANON_KEYS]
    # in the panel family's own token units (README item 15); `label` is the
    # newest model on that panel
    return float(np.mean([pf.floor_for(label, k) for k in ks])) if ks else None


def plot_row(ax, hard_files, title):
    labels, pooled_all, pmeans, keys = [], [], [], set()
    for lbl, _dt, p in hard_files:
        pooled, pm = model_samples(p)
        labels.append(clean_label(lbl)); pooled_all.append(pooled); pmeans.append(pm)
        keys |= set(pm)
    n = len(pooled_all)
    pos = list(range(n))
    colors = sns.color_palette("crest", n)     # cohesive family, darkens each generation

    parts = ax.violinplot(pooled_all, positions=pos, widths=0.82,
                          showmedians=False, showextrema=False)
    for body, c in zip(parts["bodies"], colors):
        body.set_facecolor(c); body.set_alpha(0.6)
        body.set_edgecolor(c); body.set_linewidth(1.0)

    # faint per-problem threads (problems shared by every model in the row)
    common = sorted(set.intersection(*[set(pm) for pm in pmeans])) if pmeans else []
    for pid in common:
        ax.plot(pos, [pm[pid] for pm in pmeans], color="#555555",
                lw=0.7, alpha=0.25, zorder=3)

    # median trajectory across generations
    meds = [float(np.median(p)) for p in pooled_all]
    ax.plot(pos, meds, color=PRIMARY, lw=2.5, marker="o", ms=6, zorder=6)

    floor = canonical_floor(keys, hard_files[-1][0])   # newest model on this panel
    if floor:
        ax.axhline(floor, ls="--", lw=1.6, color=FLOOR_C, zorder=4)
        ax.text(0.015, 0.955, f"Minimal human derivation ≈ {floor:,.0f} tokens",
                transform=ax.transAxes, ha="left", va="top", fontsize=15,
                fontweight="bold", color=FLOOR_C, zorder=8,
                bbox=dict(boxstyle="round,pad=0.3", fc="white", ec=FLOOR_C, alpha=0.9))

    ax.set_xticks(pos); ax.set_xticklabels(labels, fontsize=14)
    ax.set_xlim(-0.6, n - 0.4)
    ax.set_ylim(0, YCLIP)
    ax.set_title(title, fontsize=16, fontweight="bold", loc="left")
    ax.set_ylabel("Output tokens")
    ax.yaxis.set_major_formatter(unit_formatter(1e3, "k"))


use_style()
plt.rcParams.update({"axes.labelsize": 17, "xtick.labelsize": 16, "ytick.labelsize": 16,
                     "axes.titlesize": 18})


def build(fname):
    fig, axes = plt.subplots(2, 1, figsize=(13, 10), gridspec_kw={"hspace": 0.32})
    plot_row(axes[0], GPT_HARD, "OpenAI (GPT)")
    plot_row(axes[1], ANTH_HARD, "Anthropic (Opus + Fable)")
    # never include titles — captions live in the paper
    plt.tight_layout(rect=[0, 0, 1, 1.0])
    return save_figure(fig, fname, outdir=OUT)


CORRECT_ONLY = False
p1 = build("fig2_hard_distributions")
CORRECT_ONLY = True   # success-only replicate (correct trials only)
p2 = build("fig2_hard_distributions_success")
print("wrote", *p1, *p2, sep="\n  ")
