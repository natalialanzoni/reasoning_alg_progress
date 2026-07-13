"""
Time-series of mean ± SD of trace length, stratified by per-task success
rate. For each model, tasks are bucketed by THAT model's per-task success
rate into three bins:
    >= 80%      "easy for this model"
    60% - 80%   "medium"
    <  60%      "hard for this model"

Within each (model, bin), we pool all trials and compute mean + SD of
total_completion_tokens. Three lines, one per bin, plotted across model
release dates.

Output:
    new_graphs/time_series/length_by_difficulty_bin.png   mean ± SD per bin
    new_graphs/time_series/length_by_difficulty_bin_cv.png   CV per bin
"""
import json
from pathlib import Path
from datetime import datetime

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import seaborn as sns

sns.set_theme(style="whitegrid")
plt.rcParams["figure.dpi"] = 120

ROOT = Path(__file__).parent
RESULTS = ROOT / "results"
OUT_DIR = ROOT / "new_graphs" / "time_series"
OUT_DIR.mkdir(parents=True, exist_ok=True)

MODELS = [
    ("o3",      datetime(2025, 4, 1),
        RESULTS / "o3_shallow_pass" / "o3_medium_thinking_bench.json"),
    ("gpt-5",   datetime(2025, 8, 1),
        RESULTS / "thinking_20260612_100207" / "gpt-5_medium_thinking_bench.json"),
    ("gpt-5.2", datetime(2025, 12, 1),
        RESULTS / "thinking_20260612_100649" / "gpt-5.2_medium_thinking_bench.json"),
    ("gpt-5.4", datetime(2026, 3, 1),
        RESULTS / "gpt5.4_shallow_pass" / "gpt-5.4_medium_thinking_bench.json"),
]
TOKEN_KEY = "total_completion_tokens"

# Bin labels, lower/upper bounds, colors
BINS = [
    ("≥ 80%  (easy for model)",   0.80, 1.001, "#2E7D32"),
    ("60–80% (medium)",            0.60, 0.80,  "#EF6C00"),
    ("< 60%  (hard for model)",    0.00, 0.60,  "#C62828"),
]


def load_rows(path):
    if not path.exists():
        return None
    return [r for r in json.load(open(path)) if not r.get("removed_from_dataset", False)]


def main():
    # Build per (model, bin) statistics on the common task set
    loaded = []
    for label, date, path in MODELS:
        rows = load_rows(path)
        if rows is None:
            print(f"SKIP {label}: {path} missing"); continue
        loaded.append((label, date, rows))
    # Common task IDs
    common = set(r["task_id"] for r in loaded[0][2])
    for _, _, rows in loaded[1:]:
        common &= set(r["task_id"] for r in rows)
    print(f"Consistent task set: {len(common)} tasks across {len(loaded)} models\n")

    # Compute per-model per-bin stats
    series = []  # list of dicts: model, date, bin_label, mean, sd, cv, n_tasks, n_trials
    for label, date, rows in loaded:
        rows = [r for r in rows if r["task_id"] in common]
        # per-task success rate
        bin_buckets = {b[0]: [] for b in BINS}
        bin_task_count = {b[0]: 0 for b in BINS}
        for r in rows:
            corr = r["correct"]
            n = len(corr)
            sr = sum(corr) / n if n else 0
            for bin_label, lo, hi, _ in BINS:
                if lo <= sr < hi:
                    bin_buckets[bin_label].extend(r[TOKEN_KEY])
                    bin_task_count[bin_label] += 1
                    break
        for bin_label, lo, hi, color in BINS:
            tokens = np.asarray(bin_buckets[bin_label], dtype=float)
            if len(tokens) == 0:
                continue
            series.append({
                "model": label, "date": date,
                "bin": bin_label, "color": color,
                "mean": float(tokens.mean()),
                "sd": float(tokens.std(ddof=1)) if len(tokens) >= 2 else 0.0,
                "cv": float(tokens.std(ddof=1) / tokens.mean()) if tokens.mean() > 0 else 0.0,
                "n_tasks": bin_task_count[bin_label],
                "n_trials": len(tokens),
            })

    # Sort series by (bin, date) for plotting
    by_bin = {b[0]: [] for b in BINS}
    for s in series:
        by_bin[s["bin"]].append(s)
    for k in by_bin:
        by_bin[k].sort(key=lambda d: d["date"])

    print(f"{'model':<10} {'bin':<28} {'n_tasks':>9} {'n_trials':>10} {'mean':>8} {'SD':>8} {'CV':>6}")
    for label, _, _ in loaded:
        for bin_label, _, _, _ in BINS:
            entries = [s for s in series if s["model"] == label and s["bin"] == bin_label]
            if not entries: continue
            s = entries[0]
            print(f"{s['model']:<10} {s['bin']:<28} {s['n_tasks']:>9} {s['n_trials']:>10} "
                  f"{s['mean']:>8,.0f} {s['sd']:>8,.0f} {s['cv']:>6.2f}")

    # ----- Plot 1: mean ± SD per bin, over time -----
    fig, ax = plt.subplots(figsize=(11, 6.2))
    for bin_label, lo, hi, color in BINS:
        entries = by_bin[bin_label]
        if not entries: continue
        dates = [e["date"] for e in entries]
        means = [e["mean"] for e in entries]
        sds   = [e["sd"]   for e in entries]
        ax.errorbar(dates, means, yerr=sds, fmt="o-",
                    color=color, ecolor=color, linewidth=2.5,
                    markersize=10, elinewidth=1.6, capsize=6, capthick=1.6,
                    alpha=0.9, label=bin_label)
        for e in entries:
            ax.annotate(f"{e['mean']:,.0f}", (e["date"], e["mean"]),
                        textcoords="offset points", xytext=(12, 6),
                        ha="left", va="bottom", fontsize=9, fontweight="bold",
                        color=color)
    ymin, ymax = ax.get_ylim()
    pad = (ymax - ymin) * 0.10
    ax.set_ylim(ymin - pad, ymax)
    for label, date, _ in loaded:
        ax.annotate(label, (date, ymin - pad * 0.5),
                    ha="center", va="center", fontsize=11, fontweight="bold")

    ax.set_ylabel("Total Completion Tokens (mean ± 1 SD pooled)")
    ax.set_title("Trace length over time, stratified by per-model success rate")
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax.legend(loc="upper right", framealpha=0.92, fontsize=9, title="task success-rate bin")
    fig.autofmt_xdate(rotation=0)
    plt.tight_layout()
    out1 = OUT_DIR / "length_by_difficulty_bin.png"
    fig.savefig(out1, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"\nWrote {out1}")

    # ----- Plot 2: CV per bin over time -----
    fig, ax = plt.subplots(figsize=(10, 5.2))
    for bin_label, lo, hi, color in BINS:
        entries = by_bin[bin_label]
        if not entries: continue
        dates = [e["date"] for e in entries]
        cvs   = [e["cv"]   for e in entries]
        ax.plot(dates, cvs, "o-", color=color, linewidth=2.5, markersize=9,
                label=bin_label)
        for d, v in zip(dates, cvs):
            ax.annotate(f"{v:.2f}", (d, v),
                        textcoords="offset points", xytext=(8, 6),
                        fontsize=9, color=color)
    ymin, ymax = ax.get_ylim()
    pad = (ymax - ymin) * 0.10
    ax.set_ylim(ymin - pad, ymax)
    for label, date, _ in loaded:
        ax.annotate(label, (date, ymin - pad * 0.5),
                    ha="center", va="center", fontsize=11, fontweight="bold")
    ax.set_ylabel("CV (SD / mean) of pooled trials in bin")
    ax.set_title("Trace-length CV over time, stratified by per-model success rate")
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax.legend(loc="best", framealpha=0.92, fontsize=9, title="task success-rate bin")
    fig.autofmt_xdate(rotation=0)
    plt.tight_layout()
    out2 = OUT_DIR / "length_by_difficulty_bin_cv.png"
    fig.savefig(out2, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {out2}")


if __name__ == "__main__":
    main()
