"""
FIGURE 1 (headline): GPT reasoning length falling toward the irreducible floor.

Across GPT generations (o3 -> gpt-5 -> 5.2 -> 5.4 -> 5.5), mean trace length on
the reference problems falls steadily toward the canonical-solution floor (the
irreducible reasoning needed to solve the problem). Restricted to the 45
problems that have canonical solution keys, so the model lengths and the floor
are measured on the SAME problems. Canonical solutions tokenized with tiktoken
o200k_base (GPT family), matching how the model traces are counted.

Two versions:
    figure1/fig1_correct_only.png   trace length over CORRECT trials only
    figure1/fig1_all_traces.png     trace length over ALL trials

Each: bold line = mean per-task trace length (macro-avg across the 45 tasks),
shaded band = IQR (25-75th pct) of per-task means, plus the canonical floor
(avg + shortest) as horizontal reference lines.
"""
import json
import math
from pathlib import Path
from datetime import datetime

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import seaborn as sns
from datasets import load_dataset
import tiktoken

sns.set_theme(style="whitegrid")
plt.rcParams["figure.dpi"] = 120

ROOT = Path(__file__).parent
RESULTS = ROOT / "results"
OUT_DIR = ROOT / "figure1"
OUT_DIR.mkdir(parents=True, exist_ok=True)

MODELS = [
    ("o3",      datetime(2025, 4, 1), RESULTS / "o3_shallow_pass" / "o3_medium_thinking_bench.json"),
    ("gpt-5",   datetime(2025, 8, 1), RESULTS / "thinking_20260612_100207" / "gpt-5_medium_thinking_bench.json"),
    ("gpt-5.2", datetime(2025, 12, 1), RESULTS / "thinking_20260612_100649" / "gpt-5.2_medium_thinking_bench.json"),
    ("gpt-5.4", datetime(2026, 3, 1), RESULTS / "gpt5.4_shallow_pass" / "gpt-5.4_medium_thinking_bench.json"),
    ("gpt-5.5", datetime(2026, 6, 1), RESULTS / "gpt5.5_shallow_pass" / "gpt-5.5_medium_thinking_bench.json"),
]
LINE_COLOR = "#1B5E20"

# ---- Canonical floor, tokenized with tiktoken o200k_base ----
ds = load_dataset("tyrtleli/thinking-benchmark-90", split="test")
enc = tiktoken.get_encoding("o200k_base")
canon = {}
for r in ds:
    sc = r.get("solution_count")
    if sc is None or (isinstance(sc, float) and math.isnan(sc)) or sc == 0:
        continue
    toks = [len(enc.encode(s)) for s in json.loads(r["solutions"])]
    canon[str(r["id"])] = {"min": min(toks), "mean": float(np.mean(toks))}
CANON_KEYS = set(canon)
SOURCE_OF = {str(r["id"]): r.get("source") for r in ds}
canon_avg = float(np.mean([canon[t]["mean"] for t in CANON_KEYS]))
canon_short = float(np.mean([canon[t]["min"] for t in CANON_KEYS]))
print(f"Solution-key tasks: {len(CANON_KEYS)}; "
      f"canonical avg={canon_avg:.0f}, shortest-avg={canon_short:.0f} tok")


def per_task_mean_lengths(path, correct_only, restrict_to_keys=True):
    """task_id -> mean trace length. If restrict_to_keys, only solution-key tasks."""
    rows = [r for r in json.load(open(path)) if not r.get("removed_from_dataset")]
    out = {}
    for r in rows:
        tid = str(r["task_id"])
        if restrict_to_keys and tid not in CANON_KEYS:
            continue
        tt = r.get("thinking_tokens", [1] * len(r["correct"]))
        vals = []
        for tok, c, th in zip(r["total_completion_tokens"], r["correct"], tt):
            if th == 0:
                continue
            if correct_only and not c:
                continue
            vals.append(tok)
        if vals:
            out[tid] = float(np.mean(vals))
    return out


def accuracy_on_set(path, restrict_to_keys=True):
    """Pooled accuracy over non-damaged trials on the relevant problem set."""
    rows = [r for r in json.load(open(path)) if not r.get("removed_from_dataset")]
    n_correct = n_total = 0
    for r in rows:
        tid = str(r["task_id"])
        if restrict_to_keys and tid not in CANON_KEYS:
            continue
        tt = r.get("thinking_tokens", [1] * len(r["correct"]))
        for c, th in zip(r["correct"], tt):
            if th == 0:
                continue
            n_total += 1
            n_correct += int(c)
    return n_correct / max(1, n_total)


def make_figure(correct_only, fname, title_suffix, restrict_to_keys=True):
    dates, means, q1s, q3s, labels, ns, accs = [], [], [], [], [], [], []
    for label, date, path in MODELS:
        if not path.exists():
            print(f"SKIP {label}: missing"); continue
        ptm = per_task_mean_lengths(path, correct_only, restrict_to_keys)
        arr = np.array(list(ptm.values()))
        if len(arr) == 0:
            continue
        dates.append(date); labels.append(label); ns.append(len(arr))
        means.append(arr.mean())
        q1s.append(np.percentile(arr, 25))
        q3s.append(np.percentile(arr, 75))
        accs.append(accuracy_on_set(path, restrict_to_keys))

    fig, ax = plt.subplots(figsize=(11, 6.6))
    # IQR band
    ax.fill_between(dates, q1s, q3s, color=LINE_COLOR, alpha=0.13,
                    label="IQR across problems (p25–p75)", zorder=1)
    # Mean trend line
    ax.plot(dates, means, "o-", color=LINE_COLOR, linewidth=3, markersize=11,
            label="Mean trace length", zorder=4)
    for d, m in zip(dates, means):
        ax.annotate(f"{m:,.0f}", (d, m), textcoords="offset points",
                    xytext=(0, 14), ha="center", fontsize=10.5,
                    fontweight="bold", color=LINE_COLOR)

    # Canonical floor lines
    ax.axhline(canon_avg, color="#FFB300", linewidth=2.4, linestyle="-",
               zorder=3, label=f"Canonical solution (avg, {canon_avg:.0f} tok)")
    ax.axhline(canon_short, color="#000000", linewidth=1.8, linestyle="--",
               alpha=0.75, zorder=3,
               label=f"Shortest canonical (avg, {canon_short:.0f} tok)")
    # Shade the "irreducible floor" region
    ax.axhspan(0, canon_avg, color="#FFB300", alpha=0.06, zorder=0)

    # Secondary axis: accuracy on the same problem set
    ax2 = ax.twinx()
    ACC_COLOR = "#6A1B9A"
    ax2.plot(dates, [a * 100 for a in accs], "D--", color=ACC_COLOR,
             linewidth=2.2, markersize=9, alpha=0.9,
             label="Accuracy (same problems)", zorder=5)
    for d, a in zip(dates, accs):
        ax2.annotate(f"{a:.0%}", (d, a * 100), textcoords="offset points",
                     xytext=(0, 10), ha="center", fontsize=9.5,
                     fontweight="bold", color=ACC_COLOR)
    ax2.set_ylabel("Accuracy on the problem set", fontsize=11, color=ACC_COLOR)
    ax2.tick_params(axis="y", labelcolor=ACC_COLOR)
    ax2.set_ylim(0, 112)
    ax2.grid(False)

    # X-axis: model labels + dates
    ax.set_xticks(dates)
    ax.set_xticklabels([f"{l}\n{d.strftime('%Y-%m')}" for l, d in zip(labels, dates)],
                       fontsize=10, fontweight="bold")
    ax.set_xlabel("Model (release date)", fontsize=11)
    ax.set_ylabel("Trace length (output tokens, o200k)", fontsize=11, color=LINE_COLOR)
    ax.tick_params(axis="y", labelcolor=LINE_COLOR)
    ax.set_ylim(bottom=0)
    n_problems = max(ns) if ns else 0
    set_note = (f"{len(CANON_KEYS)} reference problems with canonical solutions"
                if restrict_to_keys else
                f"all {n_problems} problems (canonical floor from the {len(CANON_KEYS)} keyed)")
    ax.set_title(f"Figure 1.  GPT reasoning length falls toward the irreducible floor\n"
                 f"{title_suffix} — {set_note}", fontsize=12)
    # Combined legend from both axes, placed in the lower-left open area
    # (below the descending trace line, away from the accuracy line up top).
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="lower left", framealpha=0.96,
              fontsize=9.5, bbox_to_anchor=(0.02, 0.02))
    plt.tight_layout()
    out = OUT_DIR / fname
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {out}")
    # Print the overhead ratios + accuracy
    print(f"  {'model':<9} {'mean tok':>9} {'x canonical':>12} {'accuracy':>10}")
    for l, m, a in zip(labels, means, accs):
        print(f"  {l:<9} {m:>9,.0f} {m/canon_avg:>11.1f}x {a:>9.1%}")


# --- Restricted to the 45 solution-key problems (apples-to-apples vs floor) ---
make_figure(correct_only=True,  fname="fig1_correct_only.png",
            title_suffix="Correct traces only", restrict_to_keys=True)
print()
make_figure(correct_only=False, fname="fig1_all_traces.png",
            title_suffix="All traces", restrict_to_keys=True)

# --- Full problem set (all 86), same canonical floor reference ---
print()
make_figure(correct_only=True,  fname="fig1_correct_only_fullset.png",
            title_suffix="Correct traces only, full problem set", restrict_to_keys=False)
print()
make_figure(correct_only=False, fname="fig1_all_traces_fullset.png",
            title_suffix="All traces, full problem set", restrict_to_keys=False)


# ============================================================================
# Per-problem trajectories: one line per reference problem, mean trace length
# across GPT generations, with the canonical floor. Shows whether the fall is
# uniform across problems or driven by a few.
# ============================================================================
def make_per_problem(correct_only, fname, title_suffix, logy=True):
    SOURCE_COLOR = {"AIME": "#1565C0", "HMMT": "#2E7D32", "MATH-500": "#EF6C00"}
    # Collect per-problem mean length at each model
    dates = [d for _, d, _ in MODELS if (_ or True)]
    model_dates = [d for _, d, p in MODELS if p.exists()]
    per_problem = {}  # tid -> {date: mean_len}
    for label, date, path in MODELS:
        if not path.exists():
            continue
        ptm = per_task_mean_lengths(path, correct_only, restrict_to_keys=True)
        for tid, v in ptm.items():
            per_problem.setdefault(tid, {})[date] = v
    # Keep only problems present at every model
    full = {t: dd for t, dd in per_problem.items() if len(dd) == len(model_dates)}

    fig, ax = plt.subplots(figsize=(11, 7))
    # Per-problem faint lines, colored by source
    for tid, dd in full.items():
        xs = model_dates
        ys = [dd[d] for d in xs]
        color = SOURCE_COLOR.get(SOURCE_OF.get(tid), "#888888")
        ax.plot(xs, ys, "-", color=color, linewidth=0.8, alpha=0.30, zorder=2)
        # Mark each problem's own canonical floor as a faint dot at the last date
        ax.scatter([xs[-1]], [canon[tid]["mean"]], s=8, color=color,
                   alpha=0.5, zorder=3)

    # Bold aggregate canonical reference lines
    ax.axhline(canon_avg, color="#FFB300", linewidth=2.6, linestyle="-",
               zorder=5, label=f"Canonical solution (avg, {canon_avg:.0f} tok)")
    ax.axhline(canon_short, color="#000000", linewidth=1.8, linestyle="--",
               alpha=0.8, zorder=5, label=f"Shortest canonical (avg, {canon_short:.0f} tok)")

    # Bold median-of-problems trend on top
    med = [np.median([dd[d] for dd in full.values()]) for d in model_dates]
    ax.plot(model_dates, med, "o-", color="#000000", linewidth=2.6,
            markersize=9, zorder=6, label="Median across problems")

    if logy:
        ax.set_yscale("log")
    # Source legend handles
    import matplotlib.lines as mlines
    src_handles = [mlines.Line2D([], [], color=c, linewidth=2, label=s)
                   for s, c in SOURCE_COLOR.items()]
    h, l = ax.get_legend_handles_labels()
    ax.legend(handles=h + src_handles, loc="upper right", framealpha=0.95,
              fontsize=9)

    ax.set_xticks(model_dates)
    labels = [lab for lab, d, p in MODELS if p.exists()]
    ax.set_xticklabels([f"{lab}\n{d.strftime('%Y-%m')}"
                        for lab, d in zip(labels, model_dates)],
                       fontsize=10, fontweight="bold")
    ax.set_xlabel("Model (release date)", fontsize=11)
    ax.set_ylabel("Per-problem mean trace length (output tokens, o200k)"
                  + ("  [log]" if logy else ""), fontsize=11)
    ax.set_title(f"Per-problem reasoning length over GPT generations\n"
                 f"{title_suffix} — {len(full)} reference problems "
                 f"(faint line = one problem; dot = its canonical floor)",
                 fontsize=12)
    plt.tight_layout()
    out = OUT_DIR / fname
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {out}")


print()
make_per_problem(correct_only=False, fname="fig1_per_problem_trajectories.png",
                 title_suffix="All traces", logy=True)
make_per_problem(correct_only=True, fname="fig1_per_problem_trajectories_correct.png",
                 title_suffix="Correct traces only", logy=True)


# ============================================================================
# Faceted per-problem trajectories: one panel per source (AIME / HMMT /
# MATH-500). Much more readable than 45 overlapping colored lines — each panel
# has one muted line color, a bold median, and that source's canonical floor.
# ============================================================================
def make_per_problem_faceted(correct_only, fname, title_suffix, logy=False):
    SOURCES = ["AIME", "HMMT", "MATH-500"]
    SRC_COLOR = {"AIME": "#1565C0", "HMMT": "#2E7D32", "MATH-500": "#EF6C00"}

    model_dates = [d for _, d, p in MODELS if p.exists()]
    labels = [lab for lab, d, p in MODELS if p.exists()]
    # per-problem mean length at each model
    per_problem = {}
    for label, date, path in MODELS:
        if not path.exists():
            continue
        ptm = per_task_mean_lengths(path, correct_only, restrict_to_keys=True)
        for tid, v in ptm.items():
            per_problem.setdefault(tid, {})[date] = v
    full = {t: dd for t, dd in per_problem.items() if len(dd) == len(model_dates)}

    fig, axes = plt.subplots(1, len(SOURCES), figsize=(16, 5.8), sharey=True)
    ymax = max(max(dd.values()) for dd in full.values()) * 1.05
    for ax, src in zip(axes, SOURCES):
        tids = [t for t in full if SOURCE_OF.get(t) == src]
        color = SRC_COLOR[src]
        for tid in tids:
            ys = [full[tid][d] for d in model_dates]
            ax.plot(model_dates, ys, "-", color=color, linewidth=0.9,
                    alpha=0.30, zorder=2)
            ax.scatter([model_dates[-1]], [canon[tid]["mean"]], s=10,
                       color=color, alpha=0.6, zorder=3)
        # Median across this source's problems
        med = [np.median([full[t][d] for t in tids]) for d in model_dates]
        ax.plot(model_dates, med, "o-", color=color, linewidth=2.8,
                markersize=8, zorder=5, label="Median")
        # Source-specific canonical floor
        c_avg = np.mean([canon[t]["mean"] for t in tids])
        c_min = np.mean([canon[t]["min"] for t in tids])
        ax.axhline(c_avg, color="#FFB300", linewidth=2.2, zorder=4,
                   label=f"Canonical avg ({c_avg:.0f})")
        ax.axhline(c_min, color="#000000", linewidth=1.5, linestyle="--",
                   alpha=0.7, zorder=4, label=f"Shortest canon ({c_min:.0f})")
        if logy:
            ax.set_yscale("log")
        else:
            ax.set_ylim(0, ymax)
        ax.set_xticks(model_dates)
        ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=9)
        ax.set_title(f"{src}  ({len(tids)} problems)", fontsize=11, color=color,
                     fontweight="bold")
        ax.legend(loc="upper right", fontsize=8, framealpha=0.93)
    axes[0].set_ylabel("Per-problem mean trace length (o200k tokens)"
                       + ("  [log]" if logy else ""), fontsize=10)
    fig.suptitle(f"Per-problem reasoning length over GPT generations, by source — "
                 f"{title_suffix}\n(faint line = one problem; dot = its canonical floor)",
                 fontsize=12, y=1.02)
    plt.tight_layout()
    out = OUT_DIR / fname
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {out}")


print()
make_per_problem_faceted(correct_only=False,
                         fname="fig1_per_problem_faceted_linear.png",
                         title_suffix="All traces", logy=False)
make_per_problem_faceted(correct_only=False,
                         fname="fig1_per_problem_faceted_log.png",
                         title_suffix="All traces", logy=True)
