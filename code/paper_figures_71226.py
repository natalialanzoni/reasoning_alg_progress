"""
reproduce_paper_figures.py
==========================
Self-contained script to regenerate the four figures used in the paper:

    1. figures/fig1.png
         GPT reasoning gets shorter and cheaper over generations. (A) per-problem
         trace length + IQR bands falling toward the canonical floor (hard-but-doable
         10q k=32); (B) whole-benchmark total tokens + dollar cost (prices in
         PRICE_PER_1M — PLACEHOLDERS, edit to real per-model pricing).
    2. figures/fig1_example_problems.png
         Per-problem token distributions for 6 example problems across GPT gens.
    3. figures/fig3_forecast_successes_linear.png
         Headroom (tokens / canonical) decay toward the floor, successes only,
         with per-problem trajectories and an extrapolated forecast.
    4. figures/k40_violin_edge_of_capability.png
         Edge-of-capability per-problem token distributions, split success/failure.

WHAT YOU NEED (raw data), under RESULTS_DIR below:
  Main k=8 benchmark runs (one JSON per model), each a list of per-task records
  with fields: task_id, correct[], total_completion_tokens[], thinking_tokens[],
  answer_in_boxed[], gold_answer, source, difficulty, removed_from_dataset(optional).
      o3, gpt-5, gpt-5.2, gpt-5.4, gpt-5.5   -> paths in MAIN_K8 below
  For figure 4 only, the k=32 edge_of_capability runs + main k=8 (merged to k=40
  here in-memory):
      edge_of_capability k=32 per model      -> paths in EDGE_K32 below

  Canonical solutions come from the HuggingFace dataset tyrtleli/thinking-benchmark-90
  (field `solutions`), tokenized with tiktoken o200k_base (GPT token units).

DEPENDENCIES:  pip install numpy pandas matplotlib seaborn datasets tiktoken statsmodels
  (No answer-grading needed — the `correct` field is read from the run JSONs.)

USAGE:  python reproduce_paper_figures.py
  Edit RESULTS_DIR / the path dicts if your layout differs. Figures land in figures/.
"""
import json
import math
from pathlib import Path
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import seaborn as sns
from datasets import load_dataset
import tiktoken

sns.set_theme(style="whitegrid")
plt.rcParams["figure.dpi"] = 120

# ----------------------------------------------------------------------------
# CONFIG — edit these paths to match where your raw run JSONs live.
# ----------------------------------------------------------------------------
ROOT = Path(__file__).parent
RESULTS_DIR = ROOT.parent / "data"          # raw run JSONs live in ../data/
OUT_DIR = ROOT.parent / "figures"            # figures land in ../figures/
OUT_DIR.mkdir(parents=True, exist_ok=True)

# (label, release date, main k=8 run JSON)
MAIN_K8 = [
    ("o3",      datetime(2025, 4, 1), RESULTS_DIR / "o3_shallow_pass" / "o3_medium_thinking_bench.json"),
    ("gpt-5",   datetime(2025, 8, 7), RESULTS_DIR / "gpt5_shallow_pass" / "gpt-5_medium_thinking_bench.json"),
    ("gpt-5.2", datetime(2025, 12, 1), RESULTS_DIR / "gpt5.2_shallow_pass" / "gpt-5.2_medium_thinking_bench.json"),
    ("gpt-5.4", datetime(2026, 3, 1), RESULTS_DIR / "gpt5.4_shallow_pass" / "gpt-5.4_medium_thinking_bench.json"),
    ("gpt-5.5", datetime(2026, 6, 1), RESULTS_DIR / "gpt5.5_shallow_pass" / "gpt-5.5_medium_thinking_bench.json"),
    ("gpt-5.6-sol", datetime(2026, 8, 1), RESULTS_DIR / "gpt5.6_sol_shallow_pass" / "gpt-5.6-sol_medium_thinking_bench.json"),
]
# k=32 "hard but doable" runs (10 problems, one JSON per model) — drives Panel A of
# Figure 1: per-problem trace-length trajectories over GPT generations.
HARD10_K32 = [
    ("o3",      datetime(2025, 4, 1), RESULTS_DIR / "hard_but_doable_10q_k32" / "o3_medium_thinking_benchmark_hard_but_doable_10.json"),
    ("gpt-5",   datetime(2025, 8, 1), RESULTS_DIR / "hard_but_doable_10q_k32" / "gpt-5_medium_thinking_benchmark_hard_but_doable_10.json"),
    ("gpt-5.2", datetime(2025, 12, 1), RESULTS_DIR / "hard_but_doable_10q_k32" / "gpt-5.2_medium_thinking_benchmark_hard_but_doable_10.json"),
    ("gpt-5.4", datetime(2026, 3, 1), RESULTS_DIR / "hard_but_doable_10q_k32" / "gpt-5.4_medium_thinking_benchmark_hard_but_doable_10.json"),
    ("gpt-5.5", datetime(2026, 6, 1), RESULTS_DIR / "hard_but_doable_10q_k32" / "gpt-5.5_medium_thinking_benchmark_hard_but_doable_10.json"),
]
# Claude Opus k=32 "hard but doable" runs (same 10 problems, same shared folder).
OPUS_HARD10_K32 = [
    ("claude-opus-4-5", datetime(2025, 11, 24), RESULTS_DIR / "hard_but_doable_10q_k32" / "claude-opus-4-5_medium_thinking_benchmark_hard_but_doable_10.json"),
    ("claude-opus-4-6", datetime(2026, 2, 5),   RESULTS_DIR / "hard_but_doable_10q_k32" / "claude-opus-4-6_medium_thinking_benchmark_hard_but_doable_10.json"),
    ("claude-opus-4-7", datetime(2026, 4, 16),  RESULTS_DIR / "hard_but_doable_10q_k32" / "claude-opus-4-7_medium_thinking_benchmark_hard_but_doable_10.json"),
    ("claude-opus-4-8", datetime(2026, 5, 28),  RESULTS_DIR / "hard_but_doable_10q_k32" / "claude-opus-4-8_medium_thinking_benchmark_hard_but_doable_10.json"),
    ("claude-opus-5",   datetime(2026, 7, 24),  RESULTS_DIR / "hard_but_doable_10q_k32" / "claude-opus-5_medium_thinking_benchmark_hard_but_doable_10.json"),
]
# k=32 edge_of_capability runs (merged with main k=8 -> k=40 in-memory for fig 4)
EDGE_K32 = {
    "o3":      RESULTS_DIR / "edge_of_capability_k32" / "o3_medium_thinking_benchmark_o3.json",
    "gpt-5":   RESULTS_DIR / "edge_of_capability_k32" / "gpt-5_medium_thinking_benchmark_gpt5.json",
    "gpt-5.2": RESULTS_DIR / "edge_of_capability_k32" / "gpt-5.2_medium_thinking_benchmark_gpt5_2.json",
    "gpt-5.4": RESULTS_DIR / "edge_of_capability_k32" / "gpt-5.4_medium_thinking_benchmark_gpt5_4.json",
}
OSS_MODELS = [
    ("gpt-oss-20b",  datetime(2025, 8, 5), RESULTS_DIR / "gpt_oss20B_shallow_pass"  / "gpt-oss-20b_re-medium.json"),
    ("gpt-oss-120b", datetime(2025, 8, 6), RESULTS_DIR / "gpt_oss120B_shallow_pass" / "gpt-oss-120b_re-medium.json"),
]
# Claude Opus generations, main k=8 shallow-pass runs (47-problem benchmark,
# medium effort/thinking). No hard-but-doable k=32 or edge_of_capability k=32
# runs exist yet for these models, so only the k=8-based figures are built.
OPUS_MODELS = [
    ("claude-opus-4-5", datetime(2025, 11, 24), RESULTS_DIR / "opus4.5_shallow_pass" / "claude-opus-4-5_medium_thinking_benchmark.json"),
    ("claude-opus-4-6", datetime(2026, 2, 5),   RESULTS_DIR / "opus4.6_shallow_pass" / "claude-opus-4-6_medium_thinking_benchmark.json"),
    ("claude-opus-4-7", datetime(2026, 4, 16),  RESULTS_DIR / "opus4.7_shallow_pass" / "claude-opus-4-7_medium_thinking_benchmark.json"),
    ("claude-opus-4-8", datetime(2026, 5, 28),  RESULTS_DIR / "opus4.8_shallow_pass" / "claude-opus-4-8_medium_thinking_benchmark.json"),
    ("claude-opus-5",   datetime(2026, 7, 24),  RESULTS_DIR / "opus5_shallow_pass"   / "claude-opus-5_medium_thinking_benchmark.json"),
]
OPUS_PALETTE = {"claude-opus-4-5": "#CE93D8", "claude-opus-4-6": "#AB47BC",
                "claude-opus-4-7": "#8E24AA", "claude-opus-4-8": "#6A1B9A",
                "claude-opus-5":   "#4A148C"}
HF_DATASET = "tyrtleli/thinking-benchmark-90"

# Blended price in USD per 1M tokens, per model, for the benchmark-cost axis
# (cost = total_tokens * PRICE_PER_1M / 1e6).
# Right now this is current price. We may want to change to be price at time of release. 
PRICE_PER_1M = {
    "o3":      40,
    "gpt-5":   10.00,
    "gpt-5.2":  14,
    "gpt-5.4":  15,
    "gpt-5.5":  30,
    "gpt-5.6-sol": 30,   # PLACEHOLDER price — update with real gpt-5.6-sol pricing
}

LINE_COLOR = "#1B5E20"
COST_COLOR = "#B71C1C"
ORIGIN = datetime(2025, 4, 1)   # month axis origin for the regression

# ----------------------------------------------------------------------------
# Canonical floor: tokenize each problem's solutions with tiktoken o200k_base
# ----------------------------------------------------------------------------
print(f"Loading canonical solutions from {HF_DATASET} ...")
_ds = load_dataset(HF_DATASET, split="test")
_enc = tiktoken.get_encoding("o200k_base")
CANON = {}          # task_id -> {"mean":, "min":}
for r in _ds:
    sc = r.get("solution_count")
    if sc is None or (isinstance(sc, float) and math.isnan(sc)) or sc == 0:
        continue
    toks = [len(_enc.encode(s)) for s in json.loads(r["solutions"])]
    CANON[str(r["id"])] = {"mean": float(np.mean(toks)), "min": float(min(toks))}
CANON_KEYS = set(CANON)
canon_avg = float(np.mean([CANON[t]["mean"] for t in CANON_KEYS]))
canon_short = float(np.mean([CANON[t]["min"] for t in CANON_KEYS]))
print(f"  {len(CANON_KEYS)} problems with canonical solutions; "
      f"avg={canon_avg:.0f}, shortest-avg={canon_short:.0f} tokens\n")


def _extract_last_boxed(text):
    marker = r'\boxed{'
    idx = text.rfind(marker)
    if idx == -1:
        return None
    start = idx + len(marker)
    depth, i = 1, start
    while i < len(text) and depth > 0:
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
        i += 1
    return text[start:i - 1] if depth == 0 else None


def _grade_answer(extracted, gold):
    if extracted is None:
        return False
    e, g = extracted.strip(), str(gold).strip()
    if e == g:
        return True
    try:
        return abs(float(e) - float(g)) < 1e-9
    except (ValueError, TypeError):
        return False


def load_rows(path):
    data = json.load(open(path))
    if isinstance(data, dict) and "results" in data:
        rows = []
        for r in data["results"]:
            gold = r["answer"]
            completions = r.get("completions", [])
            rows.append({
                "task_id": r["id"],
                "correct": [_grade_answer(_extract_last_boxed(c["text"]), gold)
                            for c in completions],
                "total_completion_tokens": [c["n_tokens"] for c in completions],
            })
        return rows
    return [r for r in data if not r.get("removed_from_dataset", False)]


def per_task_mean_lengths(path, correct_only, restrict_to_keys=True):
    rows = load_rows(path)
    out = {}
    for r in rows:
        tid = str(r["task_id"])
        if restrict_to_keys and tid not in CANON_KEYS:
            continue
        tt = r.get("thinking_tokens", [1] * len(r["correct"]))
        vals = [tok for tok, c, th in zip(r["total_completion_tokens"], r["correct"], tt)
                if th != 0 and not (correct_only and not c)]
        if vals:
            out[tid] = float(np.mean(vals))
    return out


def accuracy_on_set(path, restrict_to_keys=True):
    rows = load_rows(path)
    nc = nt = 0
    for r in rows:
        if restrict_to_keys and str(r["task_id"]) not in CANON_KEYS:
            continue
        tt = r.get("thinking_tokens", [1] * len(r["correct"]))
        for c, th in zip(r["correct"], tt):
            if th == 0:
                continue
            nt += 1; nc += int(c)
    return nc / max(1, nt)


def per_task_spread(path, restrict_to_keys=True):
    rows = load_rows(path)
    sds, ranges = [], []
    for r in rows:
        if restrict_to_keys and str(r["task_id"]) not in CANON_KEYS:
            continue
        tt = r.get("thinking_tokens", [1] * len(r["correct"]))
        toks = np.array([t for t, th in zip(r["total_completion_tokens"], tt) if th > 0], float)
        if len(toks) < 2:
            continue
        sds.append(toks.std(ddof=1)); ranges.append(toks.max() - toks.min())
    return float(np.mean(sds)), float(np.mean(ranges))


def per_problem_trajectories(model_files, spread="iqr"):
    """From a list of (label, date, path), return per-problem trace-length
    trajectories at each model, restricted to problems present in EVERY model.

    `spread` sets the per-problem band bounds: "iqr" -> p25/p75 across the
    model's trials on that problem, "range" -> min/max.

    Returns (dates, labels, traj, band, accs) where:
      dates  : list[datetime]                 release date per model
      labels : list[str]                       model label per model
      traj   : dict[tid -> list[float]]        per-problem mean tokens, per model
      band   : dict[tid -> (lows, highs)]      per-problem spread bounds, per model
      accs   : list[float]                     pooled accuracy per model, shared set
    """
    dates, labels, raw, common = [], [], [], None
    for label, date, path in model_files:
        if not path.exists():
            print(f"  SKIP {label}: {path} not found")
            continue
        by_id = {}
        for r in load_rows(path):
            tt = r.get("thinking_tokens", [1] * len(r["correct"]))
            toks = np.array([t for t, th in zip(r["total_completion_tokens"], tt) if th > 0], float)
            corr = [c for c, th in zip(r["correct"], tt) if th > 0]
            if len(toks):
                if spread == "range":
                    lo, hi = float(toks.min()), float(toks.max())
                else:
                    lo, hi = float(np.percentile(toks, 25)), float(np.percentile(toks, 75))
                by_id[str(r["task_id"])] = (float(toks.mean()), lo, hi, corr)
        ids = set(by_id)
        common = ids if common is None else (common & ids)
        dates.append(date); labels.append(label); raw.append(by_id)
    common = sorted(common or [])
    traj = {tid: [rw[tid][0] for rw in raw] for tid in common}
    band = {tid: ([rw[tid][1] for rw in raw], [rw[tid][2] for rw in raw]) for tid in common}
    accs = []
    for rw in raw:
        flat = [c for tid in common for c in rw[tid][3]]
        accs.append(sum(flat) / max(1, len(flat)))
    return dates, labels, traj, band, accs


def benchmark_token_totals(model_files):
    """Total tokens (prompt + completion, all trials) to run the whole benchmark,
    summed over the task set SHARED by every model so counts are comparable.

    Returns (dates, labels, totals, n_tasks) with totals in raw tokens.
    """
    dates, labels, by_model, common = [], [], [], None
    for label, date, path in model_files:
        if not path.exists():
            print(f"  SKIP {label}: {path} not found")
            continue
        by_id = {}
        for r in load_rows(path):
            ct = r["total_completion_tokens"]
            pl = r.get("prompt_length_tokens") or [0] * len(ct)
            by_id[str(r["task_id"])] = sum(pl) + sum(ct)
        ids = set(by_id)
        common = ids if common is None else (common & ids)
        dates.append(date); labels.append(label); by_model.append(by_id)
    common = sorted(common or [])
    totals = [sum(bi[t] for t in common) for bi in by_model]
    return dates, labels, totals, len(common)


# ============================================================================
# FIGURE 1 (2-panel).
#   (A) Per-problem trace length falling toward the floor: each problem = a
#       colored spread band (IQR or range) + mean line in its own color, bold
#       macro-average on top, single canonical length line.
#   (B) Whole-benchmark resource use: total tokens (left y) and dollar cost
#       (right y = total tokens x per-model price) over model generations.
# ============================================================================
def figure1(hard10_k32_files=None, main_k8_files=None, fname="fig1.png", spread="iqr",
            suptitle="Figure 1.  GPT reasoning gets shorter and cheaper over generations",
            show_cost=True):
    import matplotlib.lines as mlines
    hard10_k32_files = hard10_k32_files if hard10_k32_files is not None else HARD10_K32
    main_k8_files = main_k8_files if main_k8_files is not None else MAIN_K8
    dates, labels, traj, band, accs = per_problem_trajectories(hard10_k32_files, spread=spread)
    macro = [float(np.mean([traj[t][i] for t in traj])) for i in range(len(dates))]
    # Single canonical length line, restricted to THIS set's keyed problems
    # (hard problems have longer solutions; a global floor would understate it).
    panel_keys = [t for t in traj if t in CANON_KEYS]
    canon = float(np.mean([CANON[t]["mean"] for t in panel_keys])) if panel_keys else None

    fig, (axL, axR) = plt.subplots(1, 2, figsize=(18, 7))

    # ------------------------------------------------------------ (A) per-problem
    # A translucent spread band + mean line per problem, in the problem's own
    # gradient color. The fall is broad-based, not driven by a few outliers.
    order = sorted(traj, key=lambda t: -max(traj[t]))     # darkest = longest-reasoning
    cmap = plt.cm.viridis
    for rank, tid in enumerate(order):
        color = cmap(rank / max(1, len(order) - 1))
        lows, highs = band[tid]
        axL.fill_between(dates, lows, highs, color=color, alpha=0.13, zorder=2,
                         edgecolor="none")
        axL.plot(dates, traj[tid], "-", color=color, linewidth=1.4, alpha=0.85, zorder=3)

    axL.plot(dates, macro, "o-", color="#000000", linewidth=3, markersize=10,
             zorder=6, label="Mean across problems")
    for d, m in zip(dates, macro):
        axL.annotate(f"{m:,.0f}", (d, m), textcoords="offset points", xytext=(0, 13),
                     ha="center", fontsize=9.5, fontweight="bold", color="#000000")
    if canon is not None:
        axL.axhline(canon, color="#FFB300", linewidth=2.4, zorder=4,
                    label=f"Canonical solution ({canon:.0f} tok)")
        axL.axhspan(0, canon, color="#FFB300", alpha=0.06, zorder=0)
    axL.set_ylim(bottom=0)
    axL.set_ylabel("Per-problem trace length (output tokens, o200k)",
                   fontsize=11, color=LINE_COLOR)
    axL.tick_params(axis="y", labelcolor=LINE_COLOR)

    band_lbl = "IQR" if spread == "iqr" else "min–max"
    prob_proxy = mlines.Line2D([], [], color=cmap(0.5), linewidth=1.4,
                               label=f"Per problem: mean + {band_lbl} band (n={len(traj)})")
    h1, l1 = axL.get_legend_handles_labels()
    axL.legend([prob_proxy] + h1, [prob_proxy.get_label()] + l1,
               loc="upper right", framealpha=0.95, fontsize=9)
    axL.set_xticks(dates)
    axL.set_xticklabels([f"{l}\n{d.strftime('%Y-%m')}" for l, d in zip(labels, dates)],
                        fontsize=9.5, fontweight="bold")
    axL.set_xlabel("Model (release date)", fontsize=11)
    axL.set_title(f"(A)  Reasoning length falls toward the floor — every problem "
                  f"({len(traj)} hard-but-doable, k=32)",
                  fontsize=11, loc="left", fontweight="bold")

    # ------------------------------------------------- (B) whole-benchmark cost
    bdates, blabels, totals, n_tasks = benchmark_token_totals(main_k8_files)
    tok_M = [t / 1e6 for t in totals]

    axR.plot(bdates, tok_M, "o-", color=LINE_COLOR, linewidth=3, markersize=10,
             zorder=4, label="Tokens to run benchmark")
    for d, v in zip(bdates, tok_M):
        axR.annotate(f"{v:.1f}M", (d, v), textcoords="offset points", xytext=(0, 12),
                     ha="center", fontsize=9.5, fontweight="bold", color=LINE_COLOR)
    axR.set_ylim(bottom=0)
    axR.set_ylabel("Total tokens to run benchmark (millions, prompt + completion)",
                   fontsize=11, color=LINE_COLOR)
    axR.tick_params(axis="y", labelcolor=LINE_COLOR)

    if show_cost:
        costs = [t * PRICE_PER_1M.get(l, float("nan")) / 1e6 for l, t in zip(blabels, totals)]
        axRc = axR.twinx()
        axRc.plot(bdates, costs, "s--", color=COST_COLOR, linewidth=2.4, markersize=9,
                  zorder=5, label="Cost (tokens × price)")
        for d, c in zip(bdates, costs):
            axRc.annotate(f"${c:,.0f}", (d, c), textcoords="offset points", xytext=(0, -16),
                          ha="center", fontsize=9.5, fontweight="bold", color=COST_COLOR)
        axRc.set_ylim(bottom=0)
        axRc.set_ylabel("Benchmark cost (USD)", fontsize=11, color=COST_COLOR)
        axRc.tick_params(axis="y", labelcolor=COST_COLOR); axRc.grid(False)
        hb1, lb1 = axR.get_legend_handles_labels(); hb2, lb2 = axRc.get_legend_handles_labels()
        axR.legend(hb1 + hb2, lb1 + lb2, loc="upper right", framealpha=0.95, fontsize=9)
        b_title = f"(B)  Whole-benchmark tokens & cost  ({n_tasks} shared tasks, k=8)"
    else:
        axR.legend(loc="upper right", framealpha=0.95, fontsize=9)
        b_title = f"(B)  Whole-benchmark tokens  ({n_tasks} shared tasks, k=8)"
    axR.set_xticks(bdates)
    axR.set_xticklabels([f"{l}\n{d.strftime('%Y-%m')}" for l, d in zip(blabels, bdates)],
                        fontsize=9.5, fontweight="bold")
    axR.set_xlabel("Model (release date)", fontsize=11)
    axR.set_title(b_title, fontsize=11, loc="left", fontweight="bold")

    fig.suptitle(suptitle,
                 fontsize=13.5, y=1.01)
    plt.tight_layout()
    fig.savefig(OUT_DIR / fname, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {OUT_DIR / fname}")


# ============================================================================
# FIGURE 1 (example problems)
# ============================================================================
def figure1_example_problems(model_files=None, palette=None, examples=None,
                              suptitle=None, fname="fig1_example_problems.png"):
    model_files = model_files if model_files is not None else MAIN_K8
    MODEL_ORDER = [m for m, _, _ in model_files]
    PALETTE = palette or {"o3": "#9E9E9E", "gpt-5": "#A5D6A7", "gpt-5.2": "#66BB6A",
                           "gpt-5.4": "#388E3C", "gpt-5.5": "#1B5E20",
                           "gpt-5.6-sol": "#0D3D14"}
    EXAMPLES = examples or [
        ("Easy",   ["aime_2026_i_01", "math_500_0148"]),
        ("Medium", ["aime_2026_i_06", "aime_2026_i_09"]),
        ("Hard",   ["hmmt_2026_feb_geo_10", "hmmt_2026_feb_comb_09"]),
    ]
    RAW = {m: {str(r["task_id"]): r for r in load_rows(p)} for m, _, p in model_files}

    def trials(pid):
        rows = []
        for m in MODEL_ORDER:
            r = RAW[m].get(pid)
            if not r:
                continue
            tt = r.get("thinking_tokens", [1] * len(r["correct"]))
            for tok, th in zip(r["total_completion_tokens"], tt):
                if th != 0:
                    rows.append({"model": m, "tokens": int(tok)})
        return pd.DataFrame(rows)

    fig, axes = plt.subplots(2, 3, figsize=(16, 9))
    for col, (tier, pids) in enumerate(EXAMPLES):
        for row, pid in enumerate(pids):
            ax = axes[row, col]
            df = trials(pid)
            sns.violinplot(data=df, x="model", y="tokens", order=MODEL_ORDER,
                           hue="model", hue_order=MODEL_ORDER, palette=PALETTE, legend=False,
                           density_norm="width", cut=0, inner="quartile", linewidth=0.8, ax=ax)
            for xi, m in enumerate(MODEL_ORDER):
                v = df[df["model"] == m]["tokens"]
                if not v.empty:
                    ax.scatter([xi], [v.median()], marker="D", s=34, color="white",
                               edgecolors="black", linewidths=0.9, zorder=6)
            c = CANON.get(pid)
            if c:
                ax.axhline(c["mean"], color="#FFB300", linewidth=2.2, zorder=7,
                           label=f"Canonical avg ({c['mean']:.0f})")
                ax.axhline(c["min"], color="#000000", linewidth=1.5, linestyle="--",
                           alpha=0.8, zorder=7, label=f"Shortest ({c['min']:.0f})")
                ax.legend(loc="upper right", fontsize=8, framealpha=0.95)
            ax.set_ylim(bottom=0); ax.set_xlabel("")
            ax.set_xticks(range(len(MODEL_ORDER)))
            ax.set_xticklabels(MODEL_ORDER, rotation=40, ha="right", fontsize=9)
            ax.set_ylabel("Trace length (tokens)" if col == 0 else "", fontsize=10)
            ax.set_title(pid, fontsize=10.5, fontweight="bold")
            if row == 0:
                ax.annotate(tier, xy=(0.5, 1.18), xycoords="axes fraction", ha="center",
                            fontsize=13, fontweight="bold", color="#333")
    fig.suptitle(suptitle or "Per-problem reasoning length across GPT generations "
                 "(2 easy / 2 medium / 2 hard; each falls toward its canonical floor)",
                 fontsize=14, fontweight="bold", y=1.01)
    plt.tight_layout()
    fig.savefig(OUT_DIR / fname, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {OUT_DIR / fname}")


# ============================================================================
# FIGURE 3 (headroom forecast, successes only, linear)
# ============================================================================
def _fit_headroom_forecast(model_files, exclude_baseline=True, successes_only=True):
    """Fit log(headroom - 1) ~ month + problem fixed effects on a (label, date,
    path) list. Shared by figure3_forecast() and figure3_forecast_combined() so
    the econometrics live in exactly one place.

    `successes_only` restricts to correct traces (drop it to fit on all traces,
    right or wrong). `exclude_baseline` drops the first model in `model_files`
    from the regression (e.g. o3 as a pre-trend peak) -- set False to include it.

    This matches the paper's excess-trend spec: with problem FE alpha_j, the
    DV log(headroom - 1) = log(L - C_j) - log(C_j) yields the SAME month slope
    as log(L - C_j) (the -log(C_j) is absorbed by alpha_j). SEs clustered by
    problem.

    Returns a dict: labels, dates, gm (geomean headroom per model), hhat
    (fitted headroom at any datetime), reach (datetime a target headroom
    fraction is hit), mile ({0.25,0.10,0.05: datetime}), baseline_label,
    quarterly_pct (% less reasoning required per quarter), t0 (last real
    data point's date), exclude_baseline, successes_only (echoed back so
    callers building fdates/start_i don't have to thread them separately).
    """
    rows, geomean = [], {}
    for label, date, path in model_files:
        month = (date - ORIGIN).days / 30.44
        hrs = []
        for r in load_rows(path):
            tid = str(r["task_id"])
            if tid not in CANON_KEYS:
                continue
            tt = r.get("thinking_tokens", [1] * len(r["correct"]))
            for tok, c, th in zip(r["total_completion_tokens"], r["correct"], tt):
                if th == 0 or tok <= 0:
                    continue
                if successes_only and not c:            # drop incorrect traces
                    continue
                hr = tok / CANON[tid]["mean"]
                rows.append({"problem": tid, "month": month, "headroom": hr})
                hrs.append(hr)
        exc = np.array([h - 1 for h in hrs if h > 1])
        geomean[label] = 1.0 + math.exp(np.mean(np.log(exc)))   # model-consistent central tendency
    df = pd.DataFrame(rows)

    baseline_label = model_files[0][0]
    baseline_month = (model_files[0][1] - ORIGIN).days / 30.44
    mask = df["headroom"] > 1
    if exclude_baseline:
        mask &= df["month"] > baseline_month   # drop the first model (pre-trend peak, e.g. o3)
    fitdf = df[mask].copy()
    fitdf["y"] = np.log(fitdf["headroom"] - 1.0)
    import statsmodels.formula.api as smf   # only needed here
    res = smf.ols("y ~ month + C(problem)", data=fitdf).fit(
        cov_type="cluster", cov_kwds={"groups": fitdf["problem"]})
    b = res.params["month"]
    # Representative intercept for the forecast curve = mean problem fixed effect
    # (Intercept is the reference problem; add the average of the dummy offsets,
    # dividing by n_problems so the reference's implicit 0 is counted).
    _fe = [v for k, v in res.params.items() if k.startswith("C(problem)")]
    a = res.params["Intercept"] + sum(_fe) / fitdf["problem"].nunique()
    q_factor = math.exp(3 * b)

    def hhat(dt):
        m = (dt - ORIGIN).days / 30.44
        return 1.0 + math.exp(a + b * m)
    def reach(frac):
        return ORIGIN + timedelta(days=((math.log(frac) - a) / b) * 30.44)
    mile = {p: reach(p) for p in (0.25, 0.10, 0.05)}

    labels = [m for m, _, _ in model_files]
    dates = [d for _, d, _ in model_files]
    gm = [geomean[m] for m in labels]

    return {
        "labels": labels, "dates": dates, "gm": gm, "hhat": hhat, "reach": reach,
        "mile": mile, "baseline_label": baseline_label,
        "quarterly_pct": (1 - q_factor) * 100, "t0": model_files[-1][1],
        "exclude_baseline": exclude_baseline, "successes_only": successes_only,
    }


def figure3_forecast(model_files=None, fname="fig3_forecast_successes_linear.png",
                      fit_annotation_date=None, exclude_baseline=True, successes_only=True):
    model_files = model_files if model_files is not None else MAIN_K8
    fit = _fit_headroom_forecast(model_files, exclude_baseline=exclude_baseline,
                                  successes_only=successes_only)
    labels, dates, gm = fit["labels"], fit["dates"], fit["gm"]
    hhat, mile, baseline_label, t0 = fit["hhat"], fit["mile"], fit["baseline_label"], fit["t0"]

    start_i = 1 if exclude_baseline else 0
    fdates = [model_files[start_i][1] + timedelta(days=30.44 * mo) for mo in range(0, 58)]
    if fit_annotation_date is None:
        # Midpoint between the last real data point and the first (least
        # stringent) milestone, so the label sits clear of both the data
        # points and the milestone lines/annotations regardless of how fast
        # this series converges.
        fit_annotation_date = t0 + (mile[0.25] - t0) / 2

    # Display in TOKENS: headroom is trace tokens / per-problem canonical floor,
    # so multiplying by the average canonical floor (a constant) turns the whole
    # picture into interpretable token units without touching the econometrics.
    REF = canon_avg   # avg canonical-solution length over keyed problems (tokens)

    fig, ax = plt.subplots(figsize=(11.5, 6.8))
    for l, d, g in zip(labels, dates, gm):
        if exclude_baseline and l == baseline_label:
            continue
        ax.plot(d, g * REF, "o", color="#1B5E20", markersize=11, zorder=5)
        ax.annotate(f"{l}: {g:.1f}× over floor ({g * REF:,.0f} tok)", (d, g * REF),
                    textcoords="offset points", xytext=(14, 0), ha="left", va="center",
                    fontsize=9, fontweight="bold", color="#1B5E20")
    ax.plot(fdates, [hhat(d) * REF for d in fdates], "--", color="#1565C0",
            linewidth=2.6, zorder=4)
    ax.annotate(f"fit: {fit['quarterly_pct']:.0f}% less reasoning required / quarter",
                (fit_annotation_date, hhat(fit_annotation_date) * REF),
                textcoords="offset points", xytext=(30, 22), fontsize=11, fontweight="bold",
                color="#1565C0", arrowprops=dict(arrowstyle="->", color="#1565C0", lw=1.2))
    ax.axhline(REF, color="#FFB300", linewidth=2.6, zorder=3)
    ax.annotate(f"canonical floor ({REF:,.0f} tok)", (fdates[-1], REF),
                textcoords="offset points", xytext=(-6, 6), ha="right", va="bottom",
                fontsize=9, color="#C79100", fontweight="bold")
    for p, d in mile.items():
        ax.axvline(d, color="#1565C0", linewidth=1, linestyle=":", alpha=0.5)
        ax.annotate(f"within {int(p*100)}%\n{d:%Y-%m}", (d, (1 + p) * REF),
                    textcoords="offset points", xytext=(6, 20), fontsize=8,
                    color="#1565C0", fontweight="bold")
    ax.set_ylim(0, max(gm) * 1.25 * REF)
    ax.axhspan(0, REF, color="#FFB300", alpha=0.07, zorder=0)
    ax.set_ylabel(f"Reasoning tokens ({'successful' if successes_only else 'all'} traces, o200k)", fontsize=11)
    ax.set_xlabel("Date", fontsize=11)
    ax.set_xlim(model_files[start_i][1] - timedelta(days=40), fdates[-1] + timedelta(days=20))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=4))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    fig.autofmt_xdate(rotation=30)
    plt.tight_layout()
    fig.savefig(OUT_DIR / fname, dpi=200, bbox_inches="tight")
    plt.close(fig)
    scope = f"excl {baseline_label}" if exclude_baseline else "all models"
    print(f"wrote {OUT_DIR / fname}  ({scope}: {fit['quarterly_pct']:.0f}%/quarter; "
          f"within10%={mile[0.10]:%Y-%m})")


def figure3_forecast_combined(fname="fig3_forecast_combined.png",
                               families=(("OpenAI", MAIN_K8, "#1B5E20", "#66BB6A"),
                                         ("Anthropic", None, "#4A148C", "#AB47BC"))):
    """Both families' headroom-over-canonical-floor fits on one shared axis,
    for a direct pace-of-convergence comparison. `families` is a list of
    (display_name, model_files, dot_color, curve_color); `model_files=None`
    for the second entry defaults to OPUS_MODELS (deferred so this default
    argument doesn't need OPUS_MODELS defined above this function)."""
    families = [(name, mf if mf is not None else OPUS_MODELS, dot_c, line_c)
                for name, mf, dot_c, line_c in families]
    REF = canon_avg
    fig, ax = plt.subplots(figsize=(12.5, 7.2))

    # Labels go above the first family's points and below the second's --
    # the two series' points land close together in date/value, so a single
    # fixed offset direction would make same-vicinity labels overlap.
    label_side = [(14, "bottom"), (-14, "top")]

    fdate_ends = []
    for fam_idx, (fam_name, model_files, dot_color, line_color) in enumerate(families):
        fit = _fit_headroom_forecast(model_files)
        labels, dates, gm = fit["labels"], fit["dates"], fit["gm"]
        dy, va = label_side[fam_idx % len(label_side)]
        for l, d, g in zip(labels, dates, gm):
            if l == fit["baseline_label"]:
                continue
            ax.plot(d, g * REF, "o", color=dot_color, markersize=10, zorder=5)
            ax.annotate(f"{l}", (d, g * REF), textcoords="offset points",
                        xytext=(0, dy), ha="center", va=va, fontsize=8,
                        fontweight="bold", color=dot_color)
        fdates = [model_files[1][1] + timedelta(days=30.44 * mo) for mo in range(0, 58)]
        ax.plot(fdates, [fit["hhat"](d) * REF for d in fdates], "--",
                color=line_color, linewidth=2.6, zorder=4,
                label=f"{fam_name} fit: {fit['quarterly_pct']:.0f}% less reasoning / quarter")
        fdate_ends.append(fdates[-1])

    ax.axhline(REF, color="#FFB300", linewidth=2.4, zorder=3)
    ax.annotate(f"canonical floor ({REF:,.0f} tok)", (max(fdate_ends), REF),
                textcoords="offset points", xytext=(-6, 6), ha="right", va="bottom",
                fontsize=9, color="#C79100", fontweight="bold")
    ax.axhspan(0, REF, color="#FFB300", alpha=0.07, zorder=0)
    ax.set_ylim(bottom=0)
    ax.set_ylabel("Reasoning tokens (successful traces, o200k)", fontsize=11)
    ax.set_xlabel("Date", fontsize=11)
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=4))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    fig.autofmt_xdate(rotation=30)
    ax.legend(loc="upper right", framealpha=0.95, fontsize=10)
    ax.set_title("Reasoning-length forecast: OpenAI vs. Anthropic converge toward "
                 "the same canonical floor", fontsize=12.5, loc="left", fontweight="bold")
    plt.tight_layout()
    fig.savefig(OUT_DIR / fname, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {OUT_DIR / fname}")


# ============================================================================
# FIGURE 4 (edge_of_capability k=40 violins, split success/failure)
#   k=40 is built in-memory: main k=8 samples + k=32 edge samples per (model, task)
# ============================================================================
_LIST_FIELDS = ["correct", "total_completion_tokens", "thinking_tokens", "answer_in_boxed",
                "extracted_answers", "response_texts", "prompt_length_tokens",
                "trace_length_tokens", "answer_tokens", "response_chars", "total_latency_sec"]


def merge_k40(main_path, k32_path):
    """Concatenate k=8 main samples + k=32 edge samples per task -> k=40 rows."""
    main_by_id = {r["task_id"]: r for r in json.load(open(main_path))}
    merged = []
    for r in json.load(open(k32_path)):
        new = dict(r)
        m = main_by_id.get(r["task_id"])
        if m:
            for fld in _LIST_FIELDS:
                if fld in r:
                    new[fld] = list(m.get(fld, [])) + list(r[fld])
        merged.append(new)
    return merged


def figure4_edge_violins(fname="k40_violin_edge_of_capability.png"):
    MODEL_ORDER = ["o3", "gpt-5", "gpt-5.2", "gpt-5.4"]
    main_by_model = {m: p for m, _, p in MAIN_K8}
    rows = []
    for m in MODEL_ORDER:
        if m not in EDGE_K32 or not EDGE_K32[m].exists() or not main_by_model[m].exists():
            print(f"  SKIP {m}: edge k32 or main k8 file missing"); continue
        for r in merge_k40(main_by_model[m], EDGE_K32[m]):
            for tok, c in zip(r["total_completion_tokens"], r["correct"]):
                rows.append({"task_id": r["task_id"], "model": m, "tokens": int(tok),
                             "correct": bool(c)})
    df = pd.DataFrame(rows)
    df["outcome"] = df["correct"].map({True: "success", False: "failure"})
    OUTCOME = {"success": "#4C72B0", "failure": "#DD8452"}

    fig, axes = plt.subplots(1, len(MODEL_ORDER), figsize=(15, 5.8), sharey=True)
    ymax = df["tokens"].max() * 1.05
    for ax, model in zip(axes, MODEL_ORDER):
        sub = df[df["model"] == model]
        if sub.empty:
            ax.set_title(f"{model}\n(no data)"); continue
        sr = sub.groupby("task_id")["correct"].mean().sort_values()
        order = sr.index.tolist()
        sns.violinplot(data=sub, x="task_id", y="tokens", hue="outcome", order=order,
                       hue_order=["success", "failure"], palette=OUTCOME, split=True,
                       cut=0, inner="quartile", density_norm="width", linewidth=0.6, ax=ax)
        for ti, tid in enumerate(order):
            g = sub[sub["task_id"] == tid]
            for oc, dx in [("success", -0.2), ("failure", 0.2)]:
                v = g[g["outcome"] == oc]["tokens"]
                if v.empty:
                    continue
                ax.scatter([ti + dx], [v.mean()], marker="D", s=40, color="white",
                           edgecolors="black", linewidths=0.9, zorder=5)
                ax.text(ti + dx, 0, f"{len(v)}", ha="center", va="bottom", fontsize=6, color="gray")
        ax.set_title(f"{model}  (5 edge-of-capability problems)")
        ax.set_xlabel("Success probability (hard ← … → easy)")
        ax.set_xticks(range(len(order)))
        ax.set_xticklabels([f"{sr[t]:.2f}" for t in order], fontsize=9)
        ax.set_ylim(0, ymax)
        ax.legend(loc="upper left", framealpha=0.92, fontsize=8, title="outcome")
    axes[0].set_ylabel("total_completion_tokens")
    fig.suptitle("Token distribution at the limit, split by success/failure  "
                 "(white diamonds = means per half)", y=1.02, fontsize=12)
    plt.tight_layout()
    fig.savefig(OUT_DIR / fname, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {OUT_DIR / fname}")


# ============================================================================
# FIGURE 1 (OSS-only, 2-panel, mirrors figure1() exactly but uses OSS_MODELS)
#   Panel A uses k=8 data (no k=32 hard-but-doable for gpt-oss), 45 problems.
#   Panel B shows tokens only — no cost line (gpt-oss prices not in PRICE_PER_1M).
#   Both panels use integer x-positions because the two OSS models are 1 day apart.
# ============================================================================
def figure1_oss(model_files=None, fname="fig1_oss.png", spread="iqr",
                 suptitle="Figure 1 (OSS).  Open-weight reasoning token usage"):
    import matplotlib.lines as mlines
    model_files = model_files if model_files is not None else OSS_MODELS

    # ------------------------------------------------------------ (A) per-problem
    dates, labels, traj, band, accs = per_problem_trajectories(model_files, spread=spread)
    macro = [float(np.mean([traj[t][i] for t in traj])) for i in range(len(dates))]
    panel_keys = [t for t in traj if t in CANON_KEYS]
    canon = float(np.mean([CANON[t]["mean"] for t in panel_keys])) if panel_keys else None

    fig, axL = plt.subplots(1, 1, figsize=(10, 7))
    xs = list(range(len(labels)))

    order = sorted(traj, key=lambda t: -max(traj[t]))
    cmap = plt.cm.viridis
    for rank, tid in enumerate(order):
        color = cmap(rank / max(1, len(order) - 1))
        lows, highs = band[tid]
        axL.fill_between(xs, lows, highs, color=color, alpha=0.13, zorder=2, edgecolor="none")
        axL.plot(xs, traj[tid], "-", color=color, linewidth=1.4, alpha=0.85, zorder=3)

    axL.plot(xs, macro, "o-", color="#000000", linewidth=3, markersize=10,
             zorder=6, label="Mean across problems")
    for xi, m in zip(xs, macro):
        axL.annotate(f"{m:,.0f}", (xi, m), textcoords="offset points", xytext=(0, 13),
                     ha="center", fontsize=9.5, fontweight="bold", color="#000000")
    if canon is not None:
        axL.axhline(canon, color="#FFB300", linewidth=2.4, zorder=4,
                    label=f"Canonical solution ({canon:.0f} tok)")
        axL.axhspan(0, canon, color="#FFB300", alpha=0.06, zorder=0)
    axL.set_ylim(bottom=0)
    axL.set_xlim(-0.5, len(labels) - 0.5)
    axL.set_ylabel("Per-problem trace length (output tokens, o200k)",
                   fontsize=11, color=LINE_COLOR)
    axL.tick_params(axis="y", labelcolor=LINE_COLOR)

    band_lbl = "IQR" if spread == "iqr" else "min–max"
    prob_proxy = mlines.Line2D([], [], color=cmap(0.5), linewidth=1.4,
                               label=f"Per problem: mean + {band_lbl} band (n={len(traj)})")
    h1, l1 = axL.get_legend_handles_labels()
    axL.legend([prob_proxy] + h1, [prob_proxy.get_label()] + l1,
               loc="upper right", framealpha=0.95, fontsize=9)
    axL.set_xticks(xs)
    axL.set_xticklabels([f"{l}\n{d.strftime('%Y-%m')}\n({acc * 100:.0f}% acc)"
                         for l, d, acc in zip(labels, dates, accs)],
                        fontsize=9.5, fontweight="bold")
    axL.set_xlabel("Model (release date)", fontsize=11)
    axL.set_title(f"(A)  Reasoning length — every problem ({len(traj)} problems, k=8)",
                  fontsize=11, loc="left", fontweight="bold")

    fig.suptitle(suptitle, fontsize=13.5, y=1.01)
    plt.tight_layout()
    fig.savefig(OUT_DIR / fname, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {OUT_DIR / fname}")


# ============================================================================
# FIGURE 1 (open-weight variant)
#   Panel A style: per-problem trace lengths for all GPT gens + gpt-oss models,
#   plotted on an equal-spacing x-axis with accuracy annotated per model.
#   Uses k=8 main runs for all models (no k=32 hard-but-doable for gpt-oss).
# ============================================================================
def figure1_open_weight(fname="fig1_open_weight.png", spread="iqr"):
    import matplotlib.lines as mlines
    import matplotlib.patches as mpatches

    OSS_LABELS = {"gpt-oss-20b", "gpt-oss-120b"}
    all_models = sorted(list(MAIN_K8) + list(OSS_MODELS), key=lambda x: x[1])
    dates, labels, traj, band, accs = per_problem_trajectories(all_models, spread=spread)
    macro = [float(np.mean([traj[t][i] for t in traj])) for i in range(len(dates))]

    panel_keys = [t for t in traj if t in CANON_KEYS]
    canon = float(np.mean([CANON[t]["mean"] for t in panel_keys])) if panel_keys else None

    fig, ax = plt.subplots(figsize=(17, 7))
    xs = list(range(len(labels)))

    # Shade open-weight model columns
    for xi, lbl in enumerate(labels):
        if lbl in OSS_LABELS:
            ax.axvspan(xi - 0.45, xi + 0.45, facecolor="#FFF3E0", alpha=0.8, zorder=0,
                       edgecolor="#FF6D00", linewidth=0.5)

    # Per-problem spread bands and mean lines
    order = sorted(traj, key=lambda t: -max(traj[t]))
    cmap = plt.cm.viridis
    for rank, tid in enumerate(order):
        color = cmap(rank / max(1, len(order) - 1))
        lows, highs = band[tid]
        ax.fill_between(xs, lows, highs, color=color, alpha=0.13, zorder=2, edgecolor="none")
        ax.plot(xs, traj[tid], "-", color=color, linewidth=1.2, alpha=0.75, zorder=3)

    # Bold macro-average
    ax.plot(xs, macro, "o-", color="#000000", linewidth=3, markersize=9, zorder=6,
            label="Mean across problems")
    for xi, m in zip(xs, macro):
        ax.annotate(f"{m:,.0f}", (xi, m), textcoords="offset points", xytext=(0, 13),
                    ha="center", fontsize=9, fontweight="bold", color="#000000")

    # Canonical floor
    if canon is not None:
        ax.axhline(canon, color="#FFB300", linewidth=2.4, zorder=4,
                   label=f"Canonical solution ({canon:.0f} tok)")
        ax.axhspan(0, canon, color="#FFB300", alpha=0.06, zorder=0)

    ax.set_ylim(bottom=0)
    ax.set_xlim(-0.5, len(labels) - 0.5)

    tick_labels = [f"{l}\n{d.strftime('%Y-%m')}\n({acc * 100:.0f}% acc)"
                   for l, d, acc in zip(labels, dates, accs)]
    ax.set_xticks(xs)
    ax.set_xticklabels(tick_labels, fontsize=9.5, fontweight="bold")
    for tick, lbl in zip(ax.get_xticklabels(), labels):
        tick.set_color("#BF360C" if lbl in OSS_LABELS else "#000000")

    ax.set_ylabel("Per-problem trace length (output tokens, o200k)", fontsize=11, color=LINE_COLOR)
    ax.tick_params(axis="y", labelcolor=LINE_COLOR)
    ax.set_xlabel("Model (release date)  —  shaded columns: open-weight", fontsize=11)

    band_lbl = "IQR" if spread == "iqr" else "min–max"
    prob_proxy = mlines.Line2D([], [], color=cmap(0.5), linewidth=1.4,
                               label=f"Per problem: mean + {band_lbl} band (n={len(traj)})")
    oss_patch = mpatches.Patch(facecolor="#FFF3E0", label="Open-weight (gpt-oss)",
                               edgecolor="#FF6D00", linewidth=1.2)
    h1, l1 = ax.get_legend_handles_labels()
    ax.legend([prob_proxy, oss_patch] + h1,
              [prob_proxy.get_label(), oss_patch.get_label()] + l1,
              loc="upper right", framealpha=0.95, fontsize=9)

    ax.set_title(
        f"Reasoning length: GPT generations vs. open-weight models  "
        f"({len(traj)} shared problems, k=8)",
        fontsize=11, loc="left", fontweight="bold"
    )
    plt.tight_layout()
    fig.savefig(OUT_DIR / fname, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {OUT_DIR / fname}")


# ============================================================================
# HEADLINE (draft): two side-by-side panels, one per provider, each showing
# the per-problem hard-but-doable k=32 spread bands + bold mean line falling
# toward the canonical floor. Shared y-axis so magnitudes are honestly
# comparable at a glance.
# ============================================================================
def _draw_trace_length_panel(ax, model_files, spread="iqr"):
    """Draw the per-problem viridis spread-band + bold mean-line panel used by
    figure1()'s Panel A onto `ax`. Returns (dates, labels, macro, canon,
    max_high) so the caller can title the axis and unify y-limits across
    panels."""
    import matplotlib.lines as mlines
    dates, labels, traj, band, accs = per_problem_trajectories(model_files, spread=spread)
    macro = [float(np.mean([traj[t][i] for t in traj])) for i in range(len(dates))]
    panel_keys = [t for t in traj if t in CANON_KEYS]
    canon = float(np.mean([CANON[t]["mean"] for t in panel_keys])) if panel_keys else None

    order = sorted(traj, key=lambda t: -max(traj[t]))
    cmap = plt.cm.viridis
    max_high = 0.0
    for rank, tid in enumerate(order):
        color = cmap(rank / max(1, len(order) - 1))
        lows, highs = band[tid]
        max_high = max(max_high, max(highs))
        ax.fill_between(dates, lows, highs, color=color, alpha=0.13, zorder=2, edgecolor="none")
        ax.plot(dates, traj[tid], "-", color=color, linewidth=1.4, alpha=0.85, zorder=3)

    ax.plot(dates, macro, "o-", color="#000000", linewidth=3, markersize=10,
            zorder=6, label="Mean across problems")
    for d, m in zip(dates, macro):
        ax.annotate(f"{m:,.0f}", (d, m), textcoords="offset points", xytext=(0, 13),
                    ha="center", fontsize=9.5, fontweight="bold", color="#000000")
    if canon is not None:
        ax.axhline(canon, color="#FFB300", linewidth=2.4, zorder=4,
                   label=f"Canonical solution ({canon:.0f} tok)")
        ax.axhspan(0, canon, color="#FFB300", alpha=0.06, zorder=0)
        max_high = max(max_high, canon)

    band_lbl = "IQR" if spread == "iqr" else "min–max"
    prob_proxy = mlines.Line2D([], [], color=cmap(0.5), linewidth=1.4,
                               label=f"Per problem: mean + {band_lbl} band (n={len(traj)})")
    h1, l1 = ax.get_legend_handles_labels()
    ax.legend([prob_proxy] + h1, [prob_proxy.get_label()] + l1,
              loc="upper right", framealpha=0.95, fontsize=8.5)
    ax.set_xticks(dates)
    ax.set_xticklabels([f"{l}\n{d.strftime('%Y-%m')}" for l, d in zip(labels, dates)],
                       fontsize=9, fontweight="bold")
    ax.set_xlabel("Model (release date)", fontsize=11)
    return dates, labels, macro, canon, max_high


def figure_headline_openai_vs_anthropic(fname="headline_openai_vs_anthropic.png", spread="iqr"):
    fig, (axL, axR) = plt.subplots(1, 2, figsize=(20, 7.5), sharey=True)

    *_, maxL = _draw_trace_length_panel(axL, HARD10_K32, spread=spread)
    *_, maxR = _draw_trace_length_panel(axR, OPUS_HARD10_K32, spread=spread)

    axL.set_ylim(0, max(maxL, maxR) * 1.08)
    axL.set_ylabel("Per-problem trace length (output tokens, o200k)",
                   fontsize=11, color=LINE_COLOR)
    axL.tick_params(axis="y", labelcolor=LINE_COLOR)

    axL.set_title("(A)  OpenAI", fontsize=13, loc="left", fontweight="bold")
    axR.set_title("(B)  Anthropic", fontsize=13, loc="left", fontweight="bold")

    fig.suptitle("DRAFT — Reasoning length falls toward the canonical floor: "
                 "OpenAI vs. Anthropic  (10 hard-but-doable problems, k=32)",
                 fontsize=14.5, y=1.03)
    plt.tight_layout()
    fig.savefig(OUT_DIR / fname, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {OUT_DIR / fname}")


if __name__ == "__main__":
    figure1()
    figure1_example_problems()
    figure3_forecast()
    figure4_edge_violins()
    figure1_oss()
    figure1_open_weight()

    # Claude Opus family. Panel B has no cost line: PRICE_PER_1M isn't reliably
    # confirmed for all 5 Opus models, and fabricating a $-axis on a figure
    # like this isn't worth the risk of quietly presenting wrong numbers as
    # fact. No edge_of_capability k=32 runs exist yet, so no figure4_edge_violins()
    # equivalent is built here.
    figure1(hard10_k32_files=OPUS_HARD10_K32, main_k8_files=OPUS_MODELS,
            fname="fig1_opus.png", show_cost=False,
            suptitle="Figure 1 (Opus).  Claude Opus reasoning gets shorter over generations")
    figure1_example_problems(
        model_files=OPUS_MODELS, palette=OPUS_PALETTE,
        suptitle="Per-problem reasoning length across Claude Opus generations "
                 "(2 easy / 2 medium / 2 hard; each vs. its canonical floor)",
        fname="fig1_example_problems_opus.png")
    figure3_forecast(model_files=OPUS_MODELS, fname="fig3_forecast_opus.png")

    figure_headline_openai_vs_anthropic()
    figure3_forecast_combined()
    print(f"\nAll figures written to {OUT_DIR}/")
