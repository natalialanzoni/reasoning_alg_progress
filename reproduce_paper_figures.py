"""
reproduce_paper_figures.py
==========================
Self-contained script to regenerate the four figures used in the paper:

    1. figures/fig1_2panel.png
         GPT reasoning gets shorter/cheaper/more consistent over generations
         (mean length + accuracy | within-problem SD + range), vs canonical floor.
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
RESULTS_DIR = ROOT / "results"
OUT_DIR = ROOT / "figures"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# (label, release date, main k=8 run JSON)
MAIN_K8 = [
    ("o3",      datetime(2025, 4, 1), RESULTS_DIR / "o3_shallow_pass" / "o3_medium_thinking_bench.json"),
    ("gpt-5",   datetime(2025, 8, 1), RESULTS_DIR / "thinking_20260612_100207" / "gpt-5_medium_thinking_bench.json"),
    ("gpt-5.2", datetime(2025, 12, 1), RESULTS_DIR / "thinking_20260612_100649" / "gpt-5.2_medium_thinking_bench.json"),
    ("gpt-5.4", datetime(2026, 3, 1), RESULTS_DIR / "gpt5.4_shallow_pass" / "gpt-5.4_medium_thinking_bench.json"),
    ("gpt-5.5", datetime(2026, 6, 1), RESULTS_DIR / "gpt5.5_shallow_pass" / "gpt-5.5_medium_thinking_bench.json"),
]
# k=32 edge_of_capability runs (merged with main k=8 -> k=40 in-memory for fig 4)
EDGE_K32 = {
    "o3":      RESULTS_DIR / "edge_of_capability_k32" / "o3_medium_thinking_benchmark_o3.json",
    "gpt-5":   RESULTS_DIR / "edge_of_capability_k32" / "gpt-5_medium_thinking_benchmark_gpt5.json",
    "gpt-5.2": RESULTS_DIR / "edge_of_capability_k32" / "gpt-5.2_medium_thinking_benchmark_gpt5_2.json",
    "gpt-5.4": RESULTS_DIR / "edge_of_capability_k32" / "gpt-5.4_medium_thinking_benchmark_gpt5_4.json",
}
HF_DATASET = "tyrtleli/thinking-benchmark-90"

LINE_COLOR = "#1B5E20"
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


def load_rows(path):
    rows = json.load(open(path))
    return [r for r in rows if not r.get("removed_from_dataset", False)]


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


# ============================================================================
# FIGURE 1 (2-panel)
# ============================================================================
def figure1_2panel(fname="fig1_2panel.png", trend="linear"):
    dates, labels, lengths, accs, sds, ranges = [], [], [], [], [], []
    for label, date, path in MAIN_K8:
        if not path.exists():
            continue
        ptm = per_task_mean_lengths(path, correct_only=False)
        arr = np.array(list(ptm.values()))
        if len(arr) == 0:
            continue
        dates.append(date); labels.append(label); lengths.append(arr.mean())
        accs.append(accuracy_on_set(path))
        sd, rng = per_task_spread(path); sds.append(sd); ranges.append(rng)

    fig, (axA, axB) = plt.subplots(1, 2, figsize=(17, 6.5))

    # Panel A: mean length + trend + canonical floor + accuracy twin
    axA.plot(dates, lengths, "o-", color=LINE_COLOR, linewidth=3, markersize=11,
             zorder=4, label="Mean trace length")
    for d, m in zip(dates, lengths):
        axA.annotate(f"{m:,.0f}", (d, m), textcoords="offset points", xytext=(0, 13),
                     ha="center", fontsize=10, fontweight="bold", color=LINE_COLOR)
    fit_idx = [i for i, l in enumerate(labels) if l != "o3"]
    xf = mdates.date2num([dates[i] for i in fit_idx])
    yv = np.array([lengths[i] for i in fit_idx])
    total_ratio = yv[0] / yv[-1]
    per_day = total_ratio ** (1.0 / (xf.max() - xf.min()))
    dec_3mo, dec_yr = per_day ** 91.31, per_day ** 365.25
    xfit = np.linspace(xf.min(), xf.max(), 100)
    if trend == "linear":
        s, b = np.polyfit(xf, yv, 1)
        axA.plot(mdates.num2date(xfit), s * xfit + b, ":", color="#555", linewidth=2, zorder=3)
    else:
        sl, il = np.polyfit(xf, np.log(yv), 1)
        axA.plot(mdates.num2date(xfit), np.exp(sl * xfit + il), ":", color="#555", linewidth=2, zorder=3)
    axA.text(0.04, 0.56, f"↓ {total_ratio:.1f}× total (gpt-5→5.5)\n"
             f"≈ {dec_3mo:.1f}× / 3 months  ({dec_yr:.1f}× / yr)",
             transform=axA.transAxes, fontsize=10, color="#333", fontweight="bold",
             bbox=dict(boxstyle="round,pad=0.4", fc="white", ec="#999", alpha=0.92))
    axA.axhline(canon_avg, color="#FFB300", linewidth=2.4, zorder=3,
                label=f"Canonical solution (avg, {canon_avg:.0f} tok)")
    axA.axhline(canon_short, color="#000000", linewidth=1.8, linestyle="--", alpha=0.75,
                zorder=3, label=f"Shortest canonical (avg, {canon_short:.0f})")
    axA.axhspan(0, canon_avg, color="#FFB300", alpha=0.06, zorder=0)
    axA.set_ylim(bottom=0)
    axA.set_ylabel("Trace length (output tokens, o200k)", fontsize=11, color=LINE_COLOR)
    axA.tick_params(axis="y", labelcolor=LINE_COLOR)
    axA2 = axA.twinx(); ACC = "#6A1B9A"
    axA2.plot(dates, [a * 100 for a in accs], "D--", color=ACC, linewidth=2.2, markersize=9,
              zorder=5, label="Accuracy")
    for d, a in zip(dates, accs):
        axA2.annotate(f"{a:.0%}", (d, a * 100), textcoords="offset points", xytext=(0, 9),
                      ha="center", fontsize=9, fontweight="bold", color=ACC)
    axA2.set_ylim(0, 112); axA2.set_ylabel("Accuracy", fontsize=11, color=ACC)
    axA2.tick_params(axis="y", labelcolor=ACC); axA2.grid(False)
    h1, l1 = axA.get_legend_handles_labels(); h2, l2 = axA2.get_legend_handles_labels()
    axA.legend(h1 + h2, l1 + l2, loc="lower left", framealpha=0.95, fontsize=9)
    axA.set_title("(A)  Reasoning length falls toward the irreducible floor",
                  fontsize=11, loc="left", fontweight="bold")

    # Panel B: within-problem SD inside range band
    axB.fill_between(dates, 0, ranges, color=LINE_COLOR, alpha=0.13, zorder=1,
                     label="Avg within-problem range (max−min)")
    axB.plot(dates, sds, "o-", color=LINE_COLOR, linewidth=3, markersize=11, zorder=4,
             label="Avg within-problem SD")
    for d, sdv in zip(dates, sds):
        axB.annotate(f"{sdv:,.0f}", (d, sdv), textcoords="offset points", xytext=(0, 11),
                     ha="center", fontsize=10, fontweight="bold", color=LINE_COLOR)
    for d, rg in zip(dates, ranges):
        axB.annotate(f"{rg:,.0f}", (d, rg), textcoords="offset points", xytext=(0, 6),
                     ha="center", fontsize=8.5, color="#558B2F", style="italic")
    axB.set_ylim(bottom=0)
    axB.set_ylabel("Within-problem spread (tokens)", fontsize=11)
    axB.legend(loc="upper right", framealpha=0.95, fontsize=9)
    axB.set_title("(B)  Within-problem variability collapses (more consistent runs)",
                  fontsize=11, loc="left", fontweight="bold")

    for ax in (axA, axB):
        ax.set_xticks(dates)
        ax.set_xticklabels([f"{l}\n{d.strftime('%Y-%m')}" for l, d in zip(labels, dates)],
                           fontsize=9.5, fontweight="bold")
        ax.set_xlabel("Model (release date)", fontsize=11)
    fig.suptitle("Figure 1.  GPT reasoning gets shorter, cheaper, and more consistent  "
                 f"({len(CANON_KEYS)} reference problems with canonical solutions; all traces, k=8)",
                 fontsize=13, y=1.02)
    plt.tight_layout()
    fig.savefig(OUT_DIR / fname, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {OUT_DIR / fname}")


# ============================================================================
# FIGURE 1 (example problems)
# ============================================================================
def figure1_example_problems(fname="fig1_example_problems.png"):
    MODEL_ORDER = [m for m, _, _ in MAIN_K8]
    PALETTE = {"o3": "#9E9E9E", "gpt-5": "#A5D6A7", "gpt-5.2": "#66BB6A",
               "gpt-5.4": "#388E3C", "gpt-5.5": "#1B5E20"}
    EXAMPLES = [
        ("Easy",   ["aime_2026_i_01", "math_500_0148"]),
        ("Medium", ["aime_2026_i_06", "aime_2026_i_09"]),
        ("Hard",   ["hmmt_2026_feb_geo_10", "hmmt_2026_feb_comb_09"]),
    ]
    RAW = {m: {str(r["task_id"]): r for r in load_rows(p)} for m, _, p in MAIN_K8}

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
    fig.suptitle("Per-problem reasoning length across GPT generations "
                 "(2 easy / 2 medium / 2 hard; each falls toward its canonical floor)",
                 fontsize=14, fontweight="bold", y=1.01)
    plt.tight_layout()
    fig.savefig(OUT_DIR / fname, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {OUT_DIR / fname}")


# ============================================================================
# FIGURE 3 (headroom forecast, successes only, linear)
# ============================================================================
def figure3_forecast(fname="fig3_forecast_successes_linear.png"):
    rows, geomean = [], {}
    for label, date, path in MAIN_K8:
        month = (date - ORIGIN).days / 30.44
        hrs = []
        for r in load_rows(path):
            tid = str(r["task_id"])
            if tid not in CANON_KEYS:
                continue
            tt = r.get("thinking_tokens", [1] * len(r["correct"]))
            for tok, c, th in zip(r["total_completion_tokens"], r["correct"], tt):
                if th == 0 or tok <= 0 or not c:        # successes only
                    continue
                hr = tok / CANON[tid]["mean"]
                rows.append({"problem": tid, "month": month, "headroom": hr})
                hrs.append(hr)
        exc = np.array([h - 1 for h in hrs if h > 1])
        geomean[label] = 1.0 + math.exp(np.mean(np.log(exc)))   # model-consistent central tendency
    df = pd.DataFrame(rows)

    # log(headroom - 1) ~ month, excl o3 (pre-trend peak)
    o3_month = (MAIN_K8[0][1] - ORIGIN).days / 30.44
    fitdf = df[(df["headroom"] > 1) & (df["month"] > o3_month)].copy()
    fitdf["y"] = np.log(fitdf["headroom"] - 1.0)
    import statsmodels.formula.api as smf   # only needed here
    res = smf.ols("y ~ month", data=fitdf).fit(
        cov_type="cluster", cov_kwds={"groups": fitdf["problem"]})
    a, b = res.params["Intercept"], res.params["month"]
    q_factor = math.exp(3 * b)
    t0 = MAIN_K8[-1][1]; month_t0 = (t0 - ORIGIN).days / 30.44
    H_t0 = math.exp(a + b * month_t0)
    def hhat(dt):
        m = (dt - ORIGIN).days / 30.44
        return 1.0 + math.exp(a + b * m)
    def reach(frac):
        return ORIGIN + timedelta(days=((math.log(frac) - a) / b) * 30.44)
    mile = {p: reach(p) for p in (0.25, 0.10, 0.05)}

    labels = [m for m, _, _ in MAIN_K8]
    dates = [d for _, d, _ in MAIN_K8]
    gm = [geomean[m] for m in labels]
    fdates = [MAIN_K8[1][1] + timedelta(days=30.44 * mo) for mo in range(0, 58)]
    plot_md = [((d - ORIGIN).days / 30.44, d) for l, d, _ in MAIN_K8 if l != "o3"]
    rng = np.random.RandomState(0)

    fig, ax = plt.subplots(figsize=(11.5, 6.8))
    # light grey per-problem median trajectories (checks broad-based compression)
    for pid in df["problem"].unique():
        xs, ys = [], []
        for mo, d in plot_md:
            s = df[(df["problem"] == pid) & np.isclose(df["month"], mo)]["headroom"]
            if len(s) >= 1:
                xs.append(d); ys.append(s.median())
        if len(xs) >= 2:
            ax.plot(xs, ys, "-", color="#B0B0B0", lw=0.6, alpha=0.45, zorder=0)
    for l, d, _ in MAIN_K8:
        if l == "o3":
            continue
        sub = df[np.isclose(df["month"], (d - ORIGIN).days / 30.44)]
        xj = [d + timedelta(days=float(j)) for j in (rng.rand(len(sub)) - 0.5) * 22]
        ax.scatter(xj, sub["headroom"].values, s=6, color="#1B5E20", alpha=0.06,
                   edgecolors="none", zorder=1)
    for l, d, g in zip(labels, dates, gm):
        if l == "o3":
            continue
        ax.plot(d, g, "o", color="#1B5E20", markersize=11, zorder=5)
        ax.annotate(f"{l}: {g:.1f}× avg headroom", (d, g), textcoords="offset points",
                    xytext=(14, 0), ha="left", va="center", fontsize=9,
                    fontweight="bold", color="#1B5E20")
    ax.plot(fdates, [hhat(d) for d in fdates], "--", color="#1565C0", linewidth=2.6, zorder=4)
    ax.annotate(f"fit: {(1-q_factor)*100:.0f}% less reasoning required / quarter",
                (datetime(2027, 6, 1), hhat(datetime(2027, 6, 1))),
                textcoords="offset points", xytext=(30, 22), fontsize=11, fontweight="bold",
                color="#1565C0", arrowprops=dict(arrowstyle="->", color="#1565C0", lw=1.2))
    ax.axhline(1.0, color="#FFB300", linewidth=2.6, zorder=3)
    ax.annotate("canonical floor (headroom = 1)", (fdates[-1], 1.0),
                textcoords="offset points", xytext=(-6, 6), ha="right", va="bottom",
                fontsize=9, color="#C79100", fontweight="bold")
    for p, d in mile.items():
        ax.axvline(d, color="#1565C0", linewidth=1, linestyle=":", alpha=0.5)
        ax.annotate(f"within {int(p*100)}%\n{d:%Y-%m}", (d, 1 + p), textcoords="offset points",
                    xytext=(6, 20), fontsize=8, color="#1565C0", fontweight="bold")
    ax.set_ylim(0, max(gm) * 1.25)
    ax.axhspan(0, 1.0, color="#FFB300", alpha=0.07, zorder=0)
    ax.set_ylabel("Headroom = trace tokens / canonical floor", fontsize=11)
    ax.set_xlabel("Date", fontsize=11)
    ax.set_xlim(MAIN_K8[1][1] - timedelta(days=40), fdates[-1] + timedelta(days=20))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=4))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    fig.autofmt_xdate(rotation=30)
    plt.tight_layout()
    fig.savefig(OUT_DIR / fname, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {OUT_DIR / fname}  (excl o3: {(1-q_factor)*100:.0f}%/quarter; "
          f"within10%={mile[0.10]:%Y-%m})")


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


if __name__ == "__main__":
    figure1_2panel()
    figure1_example_problems()
    figure3_forecast()
    figure4_edge_violins()
    print(f"\nAll figures written to {OUT_DIR}/")
