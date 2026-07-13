"""
Distribution of response token counts per task per model, x-axis sorted by
AoPS difficulty (the dataset's `difficulty` field), within-difficulty
sub-sorted by per-task mean tokens.

Uses the original k=8 main thinking-benchmark runs for all 4 models on the
consistent 86-task set.

Output:
    new_graphs/time_series/dist_by_aops_difficulty.png
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

sns.set_theme(style="whitegrid")
plt.rcParams["figure.dpi"] = 120

ROOT = Path(__file__).parent
RESULTS = ROOT / "results"
OUT_DIR = ROOT / "new_graphs" / "time_series"
OUT_DIR.mkdir(parents=True, exist_ok=True)

MODEL_ORDER = ["o3", "gpt-5", "gpt-5.2", "gpt-5.4"]
MODEL_PALETTE = {
    "o3":      "#C2185B",
    "gpt-5":   "#1565C0",
    "gpt-5.2": "#00897B",
    "gpt-5.4": "#1B5E20",
}

FILES = {
    "o3":      RESULTS / "o3_shallow_pass" / "o3_medium_thinking_bench.json",
    "gpt-5":   RESULTS / "thinking_20260612_100207" / "gpt-5_medium_thinking_bench.json",
    "gpt-5.2": RESULTS / "thinking_20260612_100649" / "gpt-5.2_medium_thinking_bench.json",
    "gpt-5.4": RESULTS / "gpt5.4_shallow_pass" / "gpt-5.4_medium_thinking_bench.json",
}

# Background color per difficulty level (light tints)
DIFF_BG = {
    2: "#E8F5E9",  # very light green - easy
    3: "#E3F2FD",  # very light blue - medium
    4: "#FFF3E0",  # very light orange - hard
    5: "#FCE4EC",  # very light pink - olympiad
    6: "#F3E5F5",  # very light purple - frontier
}
DIFF_LABEL = {2: "easy", 3: "medium", 4: "hard", 5: "olympiad", 6: "frontier"}


def main():
    # 1. Load all models, filter removed-from-dataset, build long-format
    long = []
    task_difficulty = {}
    for model, path in FILES.items():
        rows = [r for r in json.load(open(path)) if not r.get("removed_from_dataset", False)]
        for r in rows:
            tid = r["task_id"]
            diff = r.get("difficulty")
            if diff is not None:
                task_difficulty[tid] = diff
            for tok, c in zip(r["total_completion_tokens"], r["correct"]):
                long.append({"task_id": tid, "model": model, "tokens": int(tok),
                             "correct": bool(c), "difficulty": diff})
    df = pd.DataFrame(long)

    # 2. Intersect task_ids across all 4 models
    common = set(df[df["model"] == MODEL_ORDER[0]]["task_id"])
    for m in MODEL_ORDER[1:]:
        common &= set(df[df["model"] == m]["task_id"])
    df = df[df["task_id"].isin(common)]
    print(f"Consistent task set: {len(common)} tasks across {len(MODEL_ORDER)} models")

    # 3. Per-task mean (across models) for within-difficulty sub-sort
    per_task_mean = df.groupby("task_id")["tokens"].mean()
    task_order = sorted(
        common,
        key=lambda t: (task_difficulty.get(t, 99), per_task_mean.get(t, 0)),
    )
    df["task_id"] = pd.Categorical(df["task_id"], categories=task_order, ordered=True)

    # 4. Plot
    fig, ax = plt.subplots(figsize=(max(20, 0.34 * len(task_order)), 7))

    # Background shading per difficulty contiguous group
    current_diff = None
    start = 0
    diff_groups = []  # (diff, start_idx, end_idx)
    for i, tid in enumerate(task_order):
        d = task_difficulty.get(tid)
        if d != current_diff:
            if current_diff is not None:
                diff_groups.append((current_diff, start, i - 1))
            current_diff = d
            start = i
    if current_diff is not None:
        diff_groups.append((current_diff, start, len(task_order) - 1))

    for d, s, e in diff_groups:
        ax.axvspan(s - 0.5, e + 0.5, color=DIFF_BG.get(d, "#FFFFFF"), alpha=0.6, zorder=0)
        # Label the difficulty band at the top
        mid = (s + e) / 2
        label = f"diff={d}\n({DIFF_LABEL.get(d, '?')})"
        ax.text(mid, ax.get_ylim()[1] if ax.get_ylim()[1] > 0 else 1, label,
                ha="center", va="bottom", fontsize=9, fontweight="bold",
                transform=ax.transData)

    sns.boxplot(
        data=df, x="task_id", y="tokens", hue="model",
        order=task_order, hue_order=MODEL_ORDER,
        palette=MODEL_PALETTE, showfliers=False,
        width=0.8, linewidth=0.6,
        ax=ax,
    )

    ax.set_xlabel("Tasks sorted by AoPS difficulty, then by mean tokens (within difficulty)")
    ax.set_ylabel("Total Completion Tokens")
    ax.set_title(f"Response-token distribution per task and model "
                 f"({len(common)} shared tasks, k=8 per task)")
    ax.tick_params(axis="x", rotation=70, labelsize=7)
    ax.legend(loc="upper left", framealpha=0.92, title="model")
    plt.tight_layout()
    out = OUT_DIR / "dist_by_aops_difficulty.png"
    fig.savefig(out, dpi=130, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {out}")

    # Difficulty-bin summary table
    print("\nTasks per difficulty bin:")
    for d, s, e in diff_groups:
        print(f"  diff={d} ({DIFF_LABEL.get(d, '?')}): {e - s + 1} tasks")


if __name__ == "__main__":
    main()
