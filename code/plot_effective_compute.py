"""
plot_effective_compute.py
==========================
Effective compute in inference: how many fewer tokens each frontier GPT
generation needs to solve the SAME problems, expressed as a multiplier over
gpt-5 (M_i = tokens(gpt-5) / tokens(model_i)), with a fitted rate in
OOMs/year.

Problem set: the intersection of task_ids present across all five models
(o3, gpt-5, gpt-5.2, gpt-5.4, gpt-5.5), excluding removed_from_dataset tasks,
further restricted to tasks every model solves at least once (the
"jointly-solved" subset) so the comparison holds capability fixed. Damaged
trials (thinking_tokens == 0) are dropped, matching the rest of this repo's
analyses.

o3 is plotted (in grey) but EXCLUDED from the OLS fit: it predates the
gpt-5-series efficiency push this analysis is about.

Canonical-solution floor (optional annotation): mean canonical-solution
length, tokenized with tiktoken o200k_base, over the same jointly-solved
tasks, from the tyrtleli/thinking-benchmark-90 HF dataset. Skipped gracefully
if the dataset can't be loaded (no network, not cached).

USAGE:  python code/plot_effective_compute.py
"""
import json
import math
import os
from pathlib import Path
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

sns.set_theme(style="whitegrid")
plt.rcParams["figure.dpi"] = 120

ROOT = Path(__file__).parent
DATA_DIR = ROOT.parent / "data"
OUT_DIR = ROOT.parent / "figures" / "effective_compute"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# (label, release date, run JSON). Dates match code/paper_figures_71226.py.
MODELS = [
    ("o3",      datetime(2025, 4, 16), DATA_DIR / "o3_shallow_pass" / "o3_medium_thinking_bench.json"),
    ("gpt-5",   datetime(2025, 8, 7),  DATA_DIR / "gpt5_shallow_pass" / "gpt-5_medium_thinking_bench.json"),
    ("gpt-5.2", datetime(2025, 12, 11), DATA_DIR / "gpt5.2_shallow_pass" / "gpt-5.2_medium_thinking_bench.json"),
    ("gpt-5.4", datetime(2026, 3, 5),  DATA_DIR / "gpt5.4_shallow_pass" / "gpt-5.4_medium_thinking_bench.json"),
    ("gpt-5.5", datetime(2026, 6, 1),  DATA_DIR / "gpt5.5_shallow_pass" / "gpt-5.5_medium_thinking_bench.json"),
]
BASELINE = "gpt-5"
FIT_LABELS = ["gpt-5", "gpt-5.2", "gpt-5.4", "gpt-5.5"]   # o3 excluded from fit
HF_DATASET = "tyrtleli/thinking-benchmark-90"

MAIN_COLOR = "#1B5E20"      # gpt-5-series points + fit line (matches repo convention)
O3_COLOR = "#9E9E9E"        # o3: grey, excluded from fit
FLOOR_COLOR = "#FFB300"     # canonical floor (matches repo convention)
ORIGIN = MODELS[1][1]       # gpt-5 release date; regression origin (slope is origin-invariant)


def years_since(d, origin=ORIGIN):
    return (d - origin).days / 365.25


# ----------------------------------------------------------------------------
# Load data, build the shared + jointly-solved problem sets
# ----------------------------------------------------------------------------
def load_rows(path):
    data = json.load(open(path))
    return [r for r in data if not r.get("removed_from_dataset", False)]


RAW = {label: load_rows(path) for label, _, path in MODELS}

task_sets = [set(str(r["task_id"]) for r in rows) for rows in RAW.values()]
SHARED = set.intersection(*task_sets)


def solved_map(rows):
    """tid -> True if any non-damaged attempt on this task was correct."""
    out = {}
    for r in rows:
        tid = str(r["task_id"])
        tt = r.get("thinking_tokens", [1] * len(r["correct"]))
        out[tid] = any(c for c, th in zip(r["correct"], tt) if th != 0)
    return out


SOLVED = {label: solved_map(rows) for label, rows in RAW.items()}
JOINT = {t for t in SHARED if all(SOLVED[label].get(t, False) for label in RAW)}

print(f"Shared task set (all 5 models, not removed): {len(SHARED)} tasks")
print(f"Jointly-solved subset (every model solves >=1x): {len(JOINT)} tasks\n")


def mean_tokens_per_task(rows, task_set, successes_only=True):
    """tid -> mean total_completion_tokens over qualifying attempts."""
    out = {}
    for r in rows:
        tid = str(r["task_id"])
        if tid not in task_set:
            continue
        tt = r.get("thinking_tokens", [1] * len(r["correct"]))
        vals = [tok for tok, c, th in zip(r["total_completion_tokens"], r["correct"], tt)
                if th != 0 and (c or not successes_only)]
        if vals:
            out[tid] = float(np.mean(vals))
    return out


def macro_mean_tokens(task_set, successes_only=True):
    """label -> (macro-mean tokens across task_set, n_tasks contributing)."""
    out = {}
    for label, rows in RAW.items():
        ptm = mean_tokens_per_task(rows, task_set, successes_only)
        vals = [ptm[t] for t in task_set if t in ptm]
        out[label] = (float(np.mean(vals)) if vals else float("nan"), len(vals))
    return out


def fit_ooms_per_year(tokens_by_label):
    """OLS of log10(M) on release-year, gpt-5 -> gpt-5.5 (M_i = tok[gpt-5]/tok[i])."""
    base = tokens_by_label[BASELINE][0]
    dates = {label: date for label, date, _ in MODELS}
    xs = np.array([years_since(dates[l]) for l in FIT_LABELS])
    ys = np.array([math.log10(base / tokens_by_label[l][0]) for l in FIT_LABELS])
    slope, intercept = np.polyfit(xs, ys, 1)
    return slope, intercept, xs, ys


# ----------------------------------------------------------------------------
# Main analysis: successes only, jointly-solved subset
# ----------------------------------------------------------------------------
main_tokens = macro_mean_tokens(JOINT, successes_only=True)
print(f"{'model':<9} {'n_tasks':>8} {'mean tok (succ.)':>18} {'multiplier M':>13}")
base_tok = main_tokens[BASELINE][0]
multiplier = {}
for label, _, _ in MODELS:
    tok, n = main_tokens[label]
    m = base_tok / tok
    multiplier[label] = m
    print(f"{label:<9} {n:>8} {tok:>18,.0f} {m:>12.2f}x")

slope, intercept, fit_xs, fit_ys = fit_ooms_per_year(main_tokens)
annual_mult = 10 ** slope
quarter_mult = 10 ** (slope / 4)
print(f"\nFitted rate (successes only, jointly-solved, gpt-5->gpt-5.5, o3 excluded):")
print(f"  {slope:.3f} OOMs/year  (=> {annual_mult:.2f}x per year, {quarter_mult:.2f}x per quarter)")

# ----------------------------------------------------------------------------
# Robustness: same fit under (a) all attempts instead of successes-only, and
# (b) the full shared task set instead of the jointly-solved subset.
# ----------------------------------------------------------------------------
tokens_all_attempts = macro_mean_tokens(JOINT, successes_only=False)
slope_all_attempts, *_ = fit_ooms_per_year(tokens_all_attempts)

tokens_full_set = macro_mean_tokens(SHARED, successes_only=True)
slope_full_set, *_ = fit_ooms_per_year(tokens_full_set)

print("\nRobustness (fitted OOMs/year under alternate choices):")
print(f"  {'main (successes, jointly-solved)':<38} {slope:>7.3f} OOMs/yr")
print(f"  {'all attempts, jointly-solved':<38} {slope_all_attempts:>7.3f} OOMs/yr")
print(f"  {'successes only, full shared set':<38} {slope_full_set:>7.3f} OOMs/yr")

# ----------------------------------------------------------------------------
# Canonical-solution floor (optional): mean canonical tokens over JOINT tasks,
# tokenized with tiktoken o200k_base, from the HF dataset. Skip gracefully if
# it can't be loaded (no network, and no local cache).
# ----------------------------------------------------------------------------
floor_multiplier = None
canon_mean_tok = None
n_canon = 0
try:
    from datasets import load_dataset
    import tiktoken

    try:
        ds = load_dataset(HF_DATASET, split="test")
    except Exception:
        os.environ["HF_HUB_OFFLINE"] = "1"
        ds = load_dataset(HF_DATASET, split="test")

    enc = tiktoken.get_encoding("o200k_base")
    canon = {}
    for r in ds:
        sc = r.get("solution_count")
        if sc is None or (isinstance(sc, float) and math.isnan(sc)) or sc == 0:
            continue
        toks = [len(enc.encode(s)) for s in json.loads(r["solutions"])]
        canon[str(r["id"])] = float(np.mean(toks))

    canon_on_joint = [canon[t] for t in JOINT if t in canon]
    n_canon = len(canon_on_joint)
    if canon_on_joint:
        canon_mean_tok = float(np.mean(canon_on_joint))
        floor_multiplier = base_tok / canon_mean_tok
        print(f"\nCanonical floor: {canon_mean_tok:.0f} tok (n={n_canon} of {len(JOINT)} "
              f"jointly-solved tasks have canonical solutions) -> floor multiplier "
              f"{floor_multiplier:.2f}x")
    else:
        print("\nCanonical floor: no jointly-solved tasks have canonical solutions; skipping.")
except Exception as e:
    print(f"\nCanonical floor: could not load {HF_DATASET} (no network / not cached) — "
          f"skipping floor annotation. ({e})")

# ----------------------------------------------------------------------------
# Figure
# ----------------------------------------------------------------------------
dates = [d for _, d, _ in MODELS]
labels = [l for l, _, _ in MODELS]

fig, ax = plt.subplots(figsize=(11, 6.8))

# o3: grey, excluded from fit
o3_label, o3_date = labels[0], dates[0]
ax.plot(o3_date, multiplier[o3_label], "o", color=O3_COLOR, markersize=12,
        zorder=4, markeredgecolor="#616161", markeredgewidth=1.2)
ax.annotate(f"{o3_label}\n(excluded from fit)", (o3_date, multiplier[o3_label]),
            textcoords="offset points", xytext=(0, -30), ha="center", fontsize=9.5,
            fontweight="bold", color="#616161")

# gpt-5 series: green, used in fit
fit_dates = [d for l, d in zip(labels, dates) if l in FIT_LABELS]
fit_m = [multiplier[l] for l in FIT_LABELS]
ax.plot(fit_dates, fit_m, "o", color=MAIN_COLOR, markersize=12, zorder=5)
for l, d in zip(FIT_LABELS, fit_dates):
    ax.annotate(f"{l}\n{multiplier[l]:.2f}x", (d, multiplier[l]),
                textcoords="offset points", xytext=(0, 14), ha="center", fontsize=10,
                fontweight="bold", color=MAIN_COLOR)

# Dashed fitted line through the four gpt-5-series points
xs_line = np.linspace(min(fit_xs), max(fit_xs), 100)
line_dates = [ORIGIN + timedelta(days=x * 365.25) for x in xs_line]
line_vals = 10 ** (slope * xs_line + intercept)
ax.plot(line_dates, line_vals, "--", color=MAIN_COLOR, linewidth=2.4, zorder=3,
        label="OLS fit (gpt-5 → gpt-5.5)")

ax.set_yscale("log")
ax.set_xlabel("Release date", fontsize=11)
ax.set_ylabel("Effective compute multiplier vs. gpt-5 (tokens(gpt-5) / tokens(model), log scale)",
              fontsize=10.5)
ax.set_title("Effective compute in inference: fewer tokens for the same problems\n"
             f"jointly-solved subset (n={len(JOINT)} tasks), successful trials only",
             fontsize=12)

# Canonical floor reference
if floor_multiplier is not None:
    ax.axhline(floor_multiplier, color=FLOOR_COLOR, linewidth=2.2, linestyle="-",
               zorder=2, label=f"Canonical-solution floor ({floor_multiplier:.1f}x, "
                                f"{canon_mean_tok:.0f} tok)")
    ax.set_ylim(top=floor_multiplier * 1.3)

# Rate annotation
rate_text = (f"inference efficiency: ~{slope:.2f} OOMs/year\n"
             f"(≈ {annual_mult:.1f}× per year)")
ax.annotate(rate_text, xy=(fit_dates[1], fit_m[1]), xycoords="data",
            xytext=(0.62, 0.14), textcoords="axes fraction",
            fontsize=11, fontweight="bold", color=MAIN_COLOR, ha="left",
            bbox=dict(boxstyle="round,pad=0.4", facecolor="white",
                      edgecolor=MAIN_COLOR, alpha=0.92))

h, l = ax.get_legend_handles_labels()
if h:
    ax.legend(h, l, loc="upper left", fontsize=9.5, framealpha=0.95)

plt.tight_layout()
out_png = OUT_DIR / "effective_compute.png"
fig.savefig(out_png, dpi=300, bbox_inches="tight")
plt.close(fig)
print(f"\nwrote {out_png}")

# ----------------------------------------------------------------------------
# CSV table
# ----------------------------------------------------------------------------
rows = []
for label, date, _ in MODELS:
    tok, n = main_tokens[label]
    rows.append({
        "model": label,
        "release_date": date.strftime("%Y-%m-%d"),
        "mean_tokens_successes_jointly_solved": tok,
        "n_tasks": n,
        "multiplier_vs_gpt5": multiplier[label],
        "excluded_from_fit": label not in FIT_LABELS,
    })
df = pd.DataFrame(rows)
out_csv = OUT_DIR / "effective_compute.csv"
df.to_csv(out_csv, index=False)
print(f"wrote {out_csv}")
