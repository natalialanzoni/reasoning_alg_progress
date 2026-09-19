"""Distance to the human floor (FutureTech house style).

OpenAI left, Anthropic right, on a shared log axis. Each violin POOLS both runs of
that model -- the whole benchmark (40 competition problems, k=8) and the
hard-but-doable subset (10 problems, k=32) -- giving ~630 correct traces per model
instead of ~315. The extra sample matters only in the tails, which is where the
interesting behaviour is: crossing the floor is a sub-1% event for every model
except Astra and is barely resolvable on either run alone.

The 10 hard problems are a SUBSET of the 40, so after pooling they carry 8+32=40
attempts each against 8 for the other 30, tilting the distribution toward the harder
problems. `avg_ref_pooled` weights the average-human reference line the same way, so
the line and the violins describe the same sample. Each violin is the
distribution of trace length divided by that problem's MINIMAL human derivation
(L / C_j) over correct traces, so 1x means "as short as the shortest human solution
to this problem". Two human reference lines are drawn:

    solid  1x       the MINIMUM human solution   (the floor, C_j)
    dashed ~M x     the AVERAGE human solution   (median over problems of mean/min)

and the region below the floor is shaded. The newest models dip into it.

The old left panel (share of traces emitting zero thinking tokens) has been dropped.
Those statistics are still computed and printed to stdout so they can be quoted in
the text -- nothing else in the figure set reports them.

    MPLBACKEND=Agg ./venv/bin/python code/figure_latent_floor_ft.py
Output -> figures/figs_sept/fig5_latent_floor.{png,pdf}
"""
import importlib.util
import os
import sys
from datetime import datetime

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.lines as mlines
import seaborn as sns

sys.path.insert(0, os.path.expanduser("~/.claude/skills/futuretech-charts/python"))
from futuretech_helpers import use_style, save_figure
from futuretech_palette import PRIMARY, CATEGORICAL

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("fs", os.path.join(HERE, "figures_sept.py"))
fs = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(fs)
pf = fs.pf
OUT = os.path.join(os.path.dirname(HERE), "figures", "figs_sept")
D = pf.RESULTS_DIR / "hard_but_doable_10q_k32"

MIN_C = "#E07A3F"        # minimal human derivation — orange, as in figures 1 and 4
AVG_C = "#5A5A5A"        # average human solution — grey
OAI_C = CATEGORICAL[0]   # blue
ANT_C = CATEGORICAL[1]   # MIT red

# MATH-500 is excluded everywhere else, and the hard-but-doable set contains none,
# but keep the guard so the sample definition is stated rather than assumed.
KEYS = {t for t in pf.CANON_KEYS if not str(t).startswith("math_500")}


def clean(name):
    if name.startswith("claude-opus-"):  return "Opus " + name[len("claude-opus-"):].replace("-", ".")
    if name.startswith("claude-fable-"): return "Fable " + name[len("claude-fable-"):].replace("-", ".")
    if name.startswith("gpt-"):          return "GPT-" + name[len("gpt-"):]
    return name


FAB_H = [("claude-fable-5-1", datetime(2026, 9, 1),
          D / "claude-fable-5-1_medium_thinking_benchmark_hard_but_doable_10.json")]
FAB_S = [("claude-fable-5-1", datetime(2026, 9, 1),
          pf.RESULTS_DIR / "fable5.1_shallow_pass"
          / "claude-fable-5-1_medium_thinking_benchmark.json")]

# Two samples. They disagree, which is the point of showing both: the
# hard-but-doable problems have longer human write-ups, so the AVERAGE-solution
# line sits further above the minimum there and is crossed far more often.
SAMPLES = [
    ("Whole benchmark  (40 competition problems, $k=8$)",
     list(pf.MAIN_K8), sorted(list(pf.OPUS_MODELS) + FAB_S, key=lambda t: t[1])),
    ("Hard-but-doable  (10 problems, $k=32$)",
     list(fs.GPT_HARD), sorted(list(pf.OPUS_HARD10_K32) + FAB_H, key=lambda t: t[1])),
]
FAM_COLORS = [("OpenAI (GPT)", OAI_C), ("Anthropic (Opus + Fable)", ANT_C)]


def load(path):
    """Per model, ONE run: L/C_j over correct traces, plus crossing/latent shares."""
    ratios, latent, latent_ok, below_min, below_avg, n = [], 0, 0, 0, 0, 0
    for r in pf.load_rows(path):
        tid = str(r["task_id"])
        if tid not in KEYS:
            continue
        cj = pf.CANON.get(tid, {}); mn, me = cj.get("min"), cj.get("mean")
        tt = r.get("thinking_tokens", [None] * len(r["correct"]))
        for tok, c, th in zip(r["total_completion_tokens"], r["correct"], tt):
            n += 1
            if th == 0:
                latent += 1; latent_ok += int(c)
            if mn and c:
                ratios.append(tok / mn)
                below_min += int(tok < mn)
                below_avg += int(bool(me) and tok < me)
    nc = max(1, len(ratios))
    return dict(ratios=np.array(ratios), n=n, n_correct=len(ratios),
                latent_pct=100 * latent / max(1, n),
                latent_ok=(100 * latent_ok / latent if latent else 0.0),
                below_min=100 * below_min / nc, below_avg=100 * below_avg / nc)


# The average human solution as a multiple of the minimum, over the problems in this
# sample (median across problems of mean/min). This is the second reference line.
def avg_ref(path):
    """Average human solution as a multiple of the minimum, over the problems in
    THIS sample. It is sample-specific: harder problems have longer write-ups."""
    pids = [str(r["task_id"]) for r in pf.load_rows(path) if str(r["task_id"]) in KEYS]
    return float(np.median([pf.CANON[k]["mean"] / pf.CANON[k]["min"] for k in pids])), len(pids)

def load_pooled(paths):
    """Same as load() but over SEVERAL runs of the same model, concatenated.

    Pooling the whole benchmark (40 problems, k=8) with the hard-but-doable subset
    (10 problems, k=32) roughly doubles the sample to ~630 correct traces per model,
    which matters for the tails: crossing the floor is a <1% event for every model
    except Astra, so it is barely resolvable on either run alone.

    Note the 10 hard problems are a SUBSET of the 40, so after pooling they carry
    8+32=40 attempts each against 8 for the other 30. The pooled distribution is
    therefore tilted toward the harder problems; `avg_ref_pooled` is computed with the
    same weighting so the reference line and the violins describe the same sample.
    """
    parts = [load(p) for p in paths]
    ratios = np.concatenate([q["ratios"] for q in parts])
    n = sum(q["n"] for q in parts)
    latent = sum(q["latent_pct"] * q["n"] for q in parts) / max(1, n)
    nc = max(1, len(ratios))
    bmin = sum(q["below_min"] * q["n_correct"] for q in parts) / 100
    bavg = sum(q["below_avg"] * q["n_correct"] for q in parts) / 100
    return dict(ratios=ratios, n=n, n_correct=len(ratios), latent_pct=latent,
                below_min=100 * bmin / nc, below_avg=100 * bavg / nc)


def avg_ref_pooled(paths):
    """Average human solution as a multiple of the minimum, weighted by how many
    traces each problem actually contributes to the pooled violin."""
    per_trace = []
    for path in paths:
        for r in pf.load_rows(path):
            tid = str(r["task_id"])
            if tid not in KEYS:
                continue
            ratio = pf.CANON[tid]["mean"] / pf.CANON[tid]["min"]
            per_trace += [ratio] * sum(1 for c in r["correct"] if c)
    return float(np.median(per_trace))


use_style()
plt.rcParams.update({"axes.labelsize": 15, "xtick.labelsize": 13, "ytick.labelsize": 14,
                     "axes.titlesize": 16})
fig, axes = plt.subplots(1, 2, figsize=(16, 6.8), sharey=True,
                         gridspec_kw={"wspace": 0.06})

# pair each model's two runs by label
PAIRED = []
for (fam, fam_c), (_, shallow, hard) in zip(FAM_COLORS,
                                            [(None, SAMPLES[0][1], SAMPLES[1][1]),
                                             (None, SAMPLES[0][2], SAMPLES[1][2])]):
    hmap = {l: p for l, _, p in hard}
    PAIRED.append((fam, fam_c, [(l, d, [p, hmap[l]]) for l, d, p in shallow if l in hmap]))

AVG_REF = avg_ref_pooled([p for _, _, models in PAIRED for _, _, ps in models for p in ps])
print(f"fig5 (POOLED whole benchmark k=8 + hard-but-doable k=32); "
      f"average human solution = {AVG_REF:.2f}x the minimum\n")

for ax, (fam, fam_c, models) in zip(axes, PAIRED):
    stats = [load_pooled(ps) for _, _, ps in models]
    labels = [clean(l) for l, _, _ in models]
    x = np.arange(len(models))
    ramp = sns.light_palette(fam_c, n_colors=len(models) + 2)[2:]

    ax.axhspan(1e-2, 1.0, color=MIN_C, alpha=0.10, zorder=0)
    ax.axhline(AVG_REF, color=AVG_C, lw=1.8, ls="--", zorder=3)
    ax.axhline(1.0, color=MIN_C, lw=2.4, zorder=4)

    parts = ax.violinplot([st["ratios"] for st in stats], positions=x, widths=0.82,
                          showmedians=True, showextrema=False)
    for b, c in zip(parts["bodies"], ramp):
        b.set_facecolor(c); b.set_alpha(0.75); b.set_edgecolor(fam_c); b.set_linewidth(0.8)
    parts["cmedians"].set_color(PRIMARY); parts["cmedians"].set_linewidth(2)

    for xi, st in zip(x, stats):
        if st["below_min"] >= 0.2:
            ax.annotate(f"{st['below_min']:.1f}% below", (xi, 0.60), ha="center",
                        va="center", fontsize=9.5, fontweight="bold", color=MIN_C,
                        zorder=9, bbox=dict(boxstyle="round,pad=0.15", fc="white",
                                            ec="none", alpha=0.88))
        print(f"  {fam.split(' (')[0]:<10s} {clean(models[xi][0]):<14s} "
              f"n={st['n_correct']:>4d}  median {np.median(st['ratios']):6.2f}x  "
              f"below-min {st['below_min']:5.2f}%  below-avg {st['below_avg']:5.1f}%  "
              f"zero-think {st['latent_pct']:5.1f}%")

    ax.set_yscale("log"); ax.set_ylim(0.3, 90)
    ax.set_title(fam, fontweight="bold")
    ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=12, rotation=20, ha="right")
    ax.set_xlim(-0.65, len(models) - 0.35)

axes[0].set_ylabel("Trace length / minimal human derivation")
for yv, txt, c in ((AVG_REF, f"average human solution (≈{AVG_REF:.1f}×)", AVG_C),
                   (1.0, "minimal human derivation (1×)", MIN_C)):
    axes[1].annotate(txt, xy=(0.015, yv), xycoords=("axes fraction", "data"),
                     textcoords="offset points", xytext=(0, 5), ha="left", va="bottom",
                     fontsize=11, fontweight="bold", color=c, zorder=9,
                     bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.9))
handles = [mlines.Line2D([], [], color=MIN_C, lw=2.4, label="Minimum human solution (floor)"),
           mlines.Line2D([], [], color=AVG_C, lw=1.8, ls="--", label="Average human solution")]
fig.legend(handles=handles, loc="upper center", ncol=2, fontsize=12.5,
           frameon=True, framealpha=0.95, bbox_to_anchor=(0.5, -0.01))
plt.tight_layout(pad=0.5)
paths = save_figure(fig, "fig5_latent_floor", outdir=OUT)
print("\nwrote", *paths, sep="\n  ")
