"""
Time-series plot of mean and SD of trace length per model on the full
thinking-benchmark, using a consistent problem set across models.

X-axis: model release date.
Y-axis (left panel):  mean total_completion_tokens per trial.
Y-axis (right panel): SD of total_completion_tokens per trial.

The "consistent sample" filter:
- Drop any task with `removed_from_dataset == True` (problems no longer in
  the current dataset version).
- Intersect task_ids across all included models — only tasks present in
  EVERY model's results contribute. With current data that yields 86 tasks.

Output:
    new_graphs/time_series/trace_length_mean_sd.png
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
    # (label, release_date_approx, path_to_main_k8_file, family)
    ("o3",      datetime(2025, 4, 1),
        RESULTS / "o3_shallow_pass" / "o3_medium_thinking_bench.json",
        "openai"),
    ("gpt-5",   datetime(2025, 8, 1),
        RESULTS / "thinking_20260612_100207" / "gpt-5_medium_thinking_bench.json",
        "openai"),
    ("gpt-5.2", datetime(2025, 12, 1),
        RESULTS / "thinking_20260612_100649" / "gpt-5.2_medium_thinking_bench.json",
        "openai"),
    ("gpt-5.4", datetime(2026, 3, 1),
        RESULTS / "gpt5.4_shallow_pass" / "gpt-5.4_medium_thinking_bench.json",
        "openai"),
    ("gpt-5.5", datetime(2026, 6, 1),
        RESULTS / "gpt5.5_shallow_pass" / "gpt-5.5_medium_thinking_bench.json",
        "openai"),
    ("R1",      datetime(2025, 1, 20),
        RESULTS / "thinking_dsr1_20260612_170446" / "deepseek_deepseek-r1_thinking_benchmark.json",
        "deepseek"),
    # V3.2 excluded from length analyses: DeepInfra imposes a 16,384-token
    # output cap that pins 55.7% of trials at exactly 16,384, biasing mean/SD/CV
    # downward. Restore once we re-run V3.2 on a provider without this cap.
    # ("V3.2",    datetime(2025, 9, 29),
    #     RESULTS / "thinking_v32_20260617" / "deepseek-ai_DeepSeek-V3.2_thinking_benchmark.json",
    #     "deepseek"),
    ("V4-pro",  datetime(2026, 4, 1),
        RESULTS / "thinking_v4pro_20260616" / "deepseek-v4-pro_thinking_benchmark.json",
        "deepseek"),
]
TOKEN_KEY = "total_completion_tokens"

FAMILY_STYLE = {
    "openai":   {"color": "#1B5E20", "marker": "o",  "label": "OpenAI"},
    "deepseek": {"color": "#D84315", "marker": "s",  "label": "DeepSeek"},
}


def load_model_rows(path: Path):
    if not path.exists():
        return None
    rows = json.load(open(path))
    return [r for r in rows if not r.get("removed_from_dataset", False)]


def main():
    # Load all models, filter out removed-from-dataset tasks. For DeepSeek R1
    # also drop any trial with thinking_tokens == 0 (damaged sample slot) so
    # the stats only reflect actually-thought trials.
    loaded = []
    for label, date, path, family in MODELS:
        rows = load_model_rows(path)
        if rows is None:
            print(f"SKIP {label}: {path} not found")
            continue
        loaded.append((label, date, rows, family))

    if len(loaded) < 2:
        print("Not enough models loaded.")
        return

    # Intersect task_ids across all models
    common_ids = set(r["task_id"] for r in loaded[0][2])
    for _, _, rows, _ in loaded[1:]:
        common_ids &= set(r["task_id"] for r in rows)
    print(f"Consistent problem set: {len(common_ids)} tasks (intersection across "
          f"{len(loaded)} models)")

    # Per-model: compute per-task mean/SD/CV + overall accuracy, plus pooled p90/p95
    per_model = []
    for label, date, rows, family in loaded:
        keep = [r for r in rows if r["task_id"] in common_ids]
        per_task_means, per_task_sds, per_task_cvs = [], [], []
        all_tokens = []
        n_correct, n_total = 0, 0
        for r in keep:
            toks = np.asarray(r[TOKEN_KEY], dtype=float)
            # Drop damaged slots (thinking_tokens == 0) for any model where
            # they exist; ensures we're not biasing means down with empty trials.
            tt = r.get("thinking_tokens")
            corr = r["correct"]
            if tt is not None and len(tt) == len(toks):
                mask = np.asarray(tt) > 0
                toks = toks[mask]
                corr_kept = [c for c, m in zip(corr, mask) if m]
            else:
                corr_kept = corr
            if len(toks) == 0:
                continue
            all_tokens.extend(toks.tolist())
            if len(toks) >= 2:
                m = float(toks.mean()); s = float(toks.std(ddof=1))
                per_task_means.append(m)
                per_task_sds.append(s)
                if m > 0:
                    per_task_cvs.append(s / m)
            n_correct += sum(corr_kept)
            n_total += len(corr_kept)
        all_tokens = np.asarray(all_tokens, dtype=float)
        per_model.append({
            "label": label, "date": date, "family": family,
            "mean": float(np.mean(per_task_means)),
            "sd":   float(np.mean(per_task_sds)),
            "cv":   float(np.mean(per_task_cvs)),
            "p90":  float(np.percentile(all_tokens, 90)),
            "p95":  float(np.percentile(all_tokens, 95)),
            "acc":  n_correct / max(1, n_total),
            "n_tasks": len(per_task_cvs),
            "per_task_means": per_task_means,  # for scatter overlay
            "all_trials": all_tokens.tolist(),  # every individual trial
        })
        print(f"  {label:<10} ({family:<8}) {len(keep)} tasks; "
              f"mean={np.mean(per_task_means):,.0f}  "
              f"SD={np.mean(per_task_sds):,.0f}  "
              f"CV={np.mean(per_task_cvs):.3f}")

    # Sort by release date for line connection; group by family for plotting
    per_model.sort(key=lambda d: d["date"])
    by_family = {}
    for d in per_model:
        by_family.setdefault(d["family"], []).append(d)
    for fam in by_family:
        by_family[fam].sort(key=lambda d: d["date"])

    # Flat lists for axis label placement (across all models, in date order)
    all_dates = [d["date"] for d in per_model]
    all_labels = [d["label"] for d in per_model]
    all_accs = [d["acc"] for d in per_model]

    # ----- Plot 1: mean with SD error bars (mean ± SD), per family.
    fig, ax = plt.subplots(figsize=(12.5, 6.4))
    for fam, entries in by_family.items():
        st = FAMILY_STYLE[fam]
        # Error bar + line
        d_ = [e["date"] for e in entries]
        m_ = [e["mean"] for e in entries]
        s_ = [e["sd"]   for e in entries]
        ax.errorbar(d_, m_, yerr=s_, fmt=f"{st['marker']}-",
                    color=st["color"], ecolor=st["color"], linewidth=2.5,
                    markersize=11, elinewidth=2, capsize=8, capthick=2,
                    alpha=0.95, label=st["label"], zorder=3)
        # Annotation side per family — OpenAI to the right of each marker,
        # DeepSeek to the left. Keeps gpt-5.4/V4-pro labels from overlapping
        # since their release dates are only ~1 month apart.
        dx = -14 if fam == "deepseek" else 14
        ha = "right" if fam == "deepseek" else "left"
        for d, m, s in zip(d_, m_, s_):
            ax.annotate(f"{m:,.0f}", (d, m),
                        textcoords="offset points", xytext=(dx, 8),
                        ha=ha, va="bottom",
                        fontsize=10, fontweight="bold", color=st["color"])
            ax.annotate(f"±{s:,.0f}", (d, m - s),
                        textcoords="offset points", xytext=(0, -14),
                        ha="center", fontsize=9, color=st["color"], alpha=0.85,
                        style="italic")
    # Y-axis: never extend below 0 — token counts can't be negative.
    ymax = ax.get_ylim()[1]
    ax.set_ylim(0, ymax)
    # Replace the manual below-axis annotations with proper x-tick labels.
    # All labels on the same row (compact format) so V4-pro doesn't drop down.
    tick_dates = sorted(all_dates)
    tick_labels = []
    for d in tick_dates:
        i = all_dates.index(d)
        tick_labels.append(
            f"{d.strftime('%Y-%m')}\n{all_labels[i]}\nacc {all_accs[i]:.0%}"
        )
    ax.set_xticks(tick_dates)
    ax.set_xticklabels(tick_labels, fontsize=8.5, fontweight="bold")
    ax.set_xlabel("Release Date", fontsize=11)

    ax.set_ylabel("Total Completion Tokens   (mean across tasks  ±  avg within-task SD)",
                  fontsize=10)
    ax.set_title(f"Within-task mean ± SD of trace length over time  "
                 f"({len(common_ids)} shared tasks, k=8 each)", fontsize=11)
    ax.legend(loc="lower left", framealpha=0.92, fontsize=10, title="Family")
    plt.tight_layout()
    out1 = OUT_DIR / "trace_length_mean_with_sd_bars.png"
    fig.savefig(out1, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"\nWrote {out1}")

    # ----- Plot 2: CV over time, per family -----
    fig, ax = plt.subplots(figsize=(11.5, 5.4))
    for fam, entries in by_family.items():
        st = FAMILY_STYLE[fam]
        d_ = [e["date"] for e in entries]
        c_ = [e["cv"]   for e in entries]
        ax.plot(d_, c_, f"{st['marker']}-", color=st["color"],
                linewidth=2.5, markersize=10, label=st["label"])
        for d, c in zip(d_, c_):
            ax.annotate(f"  {c:.2f}", (d, c), fontsize=10,
                        color=st["color"], va="center", ha="left")
    ymin, ymax = ax.get_ylim()
    pad = (ymax - ymin) * 0.14
    ax.set_ylim(ymin - pad, ymax)
    for d, lbl in zip(all_dates, all_labels):
        ax.annotate(lbl, (d, ymin - pad * 0.5),
                    ha="center", va="center", fontsize=9, fontweight="bold")
    ax.set_ylabel("Average Coefficient of Variation")
    ax.set_title(f"Within-Task Variation ({len(common_ids)} tasks of 8 attempts)")
    ax.legend(loc="upper left", framealpha=0.92, fontsize=10, title="Family")
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    fig.autofmt_xdate(rotation=0)
    plt.tight_layout()
    out2 = OUT_DIR / "trace_length_cv.png"
    fig.savefig(out2, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {out2}")

    # ----- Plot 3: p90 and p95 of pooled trial distribution over time, per family -----
    fig, ax = plt.subplots(figsize=(12.5, 6.2))
    # Two colors per family is messy; instead use marker/linestyle to distinguish p90 vs p95.
    for fam, entries in by_family.items():
        st = FAMILY_STYLE[fam]
        d_ = [e["date"] for e in entries]
        p95_ = [e["p95"] for e in entries]
        p90_ = [e["p90"] for e in entries]
        ax.plot(d_, p95_, marker=st["marker"], linestyle="-",
                color=st["color"], linewidth=2.5, markersize=10,
                label=f"{st['label']} p95")
        ax.plot(d_, p90_, marker=st["marker"], linestyle="--",
                color=st["color"], linewidth=2.0, markersize=9,
                alpha=0.75, label=f"{st['label']} p90")
        for d, v in zip(d_, p95_):
            ax.annotate(f"{v:,.0f}", (d, v),
                        textcoords="offset points", xytext=(10, 6),
                        ha="left", va="bottom", fontsize=9, fontweight="bold",
                        color=st["color"])
        for d, v in zip(d_, p90_):
            ax.annotate(f"{v:,.0f}", (d, v),
                        textcoords="offset points", xytext=(10, -10),
                        ha="left", va="top", fontsize=9,
                        color=st["color"], alpha=0.80)
    ymin, ymax = ax.get_ylim()
    pad = (ymax - ymin) * 0.14
    ax.set_ylim(ymin - pad, ymax)
    for d, lbl, acc in zip(all_dates, all_labels, all_accs):
        ax.annotate(f"{lbl}\nacc = {acc:.1%}", (d, ymin - pad * 0.5),
                    ha="center", va="center", fontsize=9, fontweight="bold")
    ax.set_ylabel("Total Completion Tokens")
    ax.set_title(f"Upper-tail of trial-token distribution over time  "
                 f"({len(common_ids)} shared tasks; pooled trials per model)")
    ax.legend(loc="upper left", framealpha=0.92, fontsize=9, ncol=2)
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    fig.autofmt_xdate(rotation=0)
    plt.tight_layout()
    out3 = OUT_DIR / "trace_length_tail_p90_p95.png"
    fig.savefig(out3, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {out3}")


if __name__ == "__main__":
    main()
