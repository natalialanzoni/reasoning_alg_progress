"""
Time-series CV plot but computed ONLY over successful trials per model.

Rationale: an "all-trials" CV bundles together solutions that worked and
solutions that spiraled into garbage / hit the cap / gave up. The success-only
view shows variance among reasoning paths that actually produced the right
answer — closer to "how spread-out is the model's *productive* reasoning?"

Caveats baked into this metric:
- Per-task CV requires ≥ 2 successes on that task; tasks with < 2 are
  dropped from THAT model's CV (different per-model task sets).
- Models that fail more often will average over an easier subset of tasks
  (selection bias toward easier-for-them problems). We report the per-model
  task count so this is visible.
- Damaged trials (thinking_tokens == 0) are excluded as before.

Output:
    new_graphs/time_series/trace_length_cv_successes_only.png
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
    ("o3",      datetime(2025, 4, 1), "openai",
        RESULTS / "o3_shallow_pass" / "o3_medium_thinking_bench.json"),
    ("gpt-5",   datetime(2025, 8, 1), "openai",
        RESULTS / "thinking_20260612_100207" / "gpt-5_medium_thinking_bench.json"),
    ("gpt-5.2", datetime(2025, 12, 1), "openai",
        RESULTS / "thinking_20260612_100649" / "gpt-5.2_medium_thinking_bench.json"),
    ("gpt-5.4", datetime(2026, 3, 1), "openai",
        RESULTS / "gpt5.4_shallow_pass" / "gpt-5.4_medium_thinking_bench.json"),
    ("R1",      datetime(2025, 1, 20), "deepseek",
        RESULTS / "thinking_dsr1_20260612_170446" / "deepseek_deepseek-r1_thinking_benchmark.json"),
    # V3.2 excluded — 16,384-token DeepInfra cap pollutes its variance metrics.
    ("V4-pro",  datetime(2026, 4, 1), "deepseek",
        RESULTS / "thinking_v4pro_20260616" / "deepseek-v4-pro_thinking_benchmark.json"),
]

FAMILY_STYLE = {
    "openai":   {"color": "#1B5E20", "marker": "o", "label": "OpenAI"},
    "deepseek": {"color": "#D84315", "marker": "s", "label": "DeepSeek"},
}


def load(path):
    if not path.exists():
        return None
    return [r for r in json.load(open(path)) if not r.get("removed_from_dataset", False)]


def main():
    loaded = []
    for label, date, family, path in MODELS:
        rows = load(path)
        if rows is None:
            print(f"SKIP {label}: {path} not found"); continue
        loaded.append((label, date, family, rows))

    common = set(r["task_id"] for r in loaded[0][3])
    for _, _, _, rows in loaded[1:]:
        common &= set(r["task_id"] for r in rows)
    print(f"Common tasks: {len(common)} across {len(loaded)} models\n")

    per_model = []
    print(f"{'model':<10} {'family':<10} {'tasks_used':<11} {'n_succ_trials':<14} "
          f"{'CV_succ':<8} {'CV_all (ref)':<12}")
    for label, date, family, rows in loaded:
        keep = [r for r in rows if r["task_id"] in common]
        per_task_cv_succ = []
        per_task_cv_all = []
        n_succ_trials = 0
        for r in keep:
            toks = np.asarray(r["total_completion_tokens"], dtype=float)
            corr = np.asarray(r["correct"], dtype=bool)
            tt   = np.asarray(r.get("thinking_tokens", [1]*len(toks)))
            # Drop damaged
            mask_kept = tt > 0
            toks = toks[mask_kept]; corr = corr[mask_kept]
            # CV across all kept trials (for reference)
            if len(toks) >= 2 and toks.mean() > 0:
                per_task_cv_all.append(toks.std(ddof=1) / toks.mean())
            # CV over successful trials only
            t_succ = toks[corr]
            n_succ_trials += int(corr.sum())
            if len(t_succ) >= 2 and t_succ.mean() > 0:
                per_task_cv_succ.append(t_succ.std(ddof=1) / t_succ.mean())
        per_model.append({
            "label": label, "date": date, "family": family,
            "cv_succ": float(np.mean(per_task_cv_succ)) if per_task_cv_succ else float("nan"),
            "cv_all":  float(np.mean(per_task_cv_all))  if per_task_cv_all  else float("nan"),
            "tasks_used": len(per_task_cv_succ),
            "n_succ_trials": n_succ_trials,
        })
        print(f"{label:<10} {family:<10} {len(per_task_cv_succ):<11} {n_succ_trials:<14} "
              f"{per_model[-1]['cv_succ']:<8.3f} {per_model[-1]['cv_all']:<12.3f}")

    per_model.sort(key=lambda d: d["date"])
    by_family = {}
    for d in per_model:
        by_family.setdefault(d["family"], []).append(d)
    for fam in by_family:
        by_family[fam].sort(key=lambda d: d["date"])

    fig, ax = plt.subplots(figsize=(12, 5.6))
    for fam, entries in by_family.items():
        st = FAMILY_STYLE[fam]
        d_ = [e["date"] for e in entries]
        cv_ = [e["cv_succ"] for e in entries]
        ax.plot(d_, cv_, f"{st['marker']}-", color=st["color"],
                linewidth=2.5, markersize=11, label=st["label"])
        for e in entries:
            ax.annotate(f"  {e['cv_succ']:.3f}\n  (n={e['tasks_used']} tasks)",
                        (e["date"], e["cv_succ"]),
                        fontsize=9, color=st["color"], va="center", ha="left")
    ymin, ymax = ax.get_ylim()
    pad = (ymax - ymin) * 0.14
    ax.set_ylim(ymin - pad, ymax)
    for e in per_model:
        ax.annotate(e["label"], (e["date"], ymin - pad * 0.5),
                    ha="center", va="center", fontsize=9, fontweight="bold")
    ax.set_ylabel("Average Coefficient of Variation\n(over successful trials only)")
    ax.set_title("Within-task Variation Among Successful Trials Only "
                 "(no damaged, no V3.2; tasks with < 2 successes skipped per-model)")
    ax.legend(loc="upper right", framealpha=0.92, fontsize=10, title="Family")
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    fig.autofmt_xdate(rotation=0)
    plt.tight_layout()
    out = OUT_DIR / "trace_length_cv_successes_only.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
