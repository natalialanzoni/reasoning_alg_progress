"""
Figure 1 + DeepSeek — 2 rows x 3 columns, one shared time axis.

  Columns: OpenAI (GPT) | Anthropic (Opus + Fable) | DeepSeek
  Row 1: accuracy over generations
  Row 2: mean output tokens over generations, with the minimal-human-derivation
         floor drawn for reference

WHY ONLY TWO ROWS. The published fig1_grid has a third row (within-problem IQR
bands on hard-but-doable-10, k=32). **No hard-but-doable-10 k=32 data exists for
DeepSeek**, so that row cannot be drawn for the new column. Rather than show an
empty panel, this figure drops the row for every family, which keeps the three
columns strictly parallel.

COMPARABILITY — the point of this version. DeepSeek was served through OpenRouter
by SiliconFlow, which truncates intermittently at 32,768 and ignores max_tokens
entirely for models with no effort knob (R1 ran to 66,106; V3.2 to 82,918). So
every family here is right-censored at a COMMON 32,768: a trace needing more is
scored WRONG and its token count clamped, exactly as a 32,768-capped backend would
have produced. That costs the incumbent families almost nothing -- 23/2,543 OpenAI
trials (0.90%) and 25/1,565 Anthropic (1.60%) -- so the columns are directly
comparable rather than DeepSeek being a caveat-laden outlier.

Sample = the same 40 competition problems as fig1_grid (AIME 2026 I/II + HMMT Feb
2026; MATH-500 excluded), floor recomputed over those 40. DeepSeek covers 40/40.

DeepSeek column = the SiliconFlow/fp8 timeline only (R1-0528 -> V3.2 -> V4 Pro
April build). The DeepSeek-direct GA runs are a different provider AND a different
build and are deliberately NOT mixed in — see OPEN_SOURCE_README.md section 7d.

    MPLBACKEND=Agg ./venv/bin/python code/figure1_deepseek_ft.py
Output -> figures/figs_sept/fig1_grid_deepseek.{png,pdf}
"""
import importlib.util
import os
import sys
from datetime import datetime

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.lines as mlines

HERE = os.path.dirname(os.path.abspath(__file__))
# The futuretech-charts skill is absent on this machine; see _ft_style_local.py.
sys.path.insert(0, os.path.expanduser("~/.claude/skills/futuretech-charts/python"))
try:
    from futuretech_helpers import use_style, unit_formatter, save_figure
    from futuretech_palette import PRIMARY
    STYLE_SRC = "futuretech-charts skill"
except ModuleNotFoundError:
    sys.path.insert(0, HERE)
    from _ft_style_local import use_style, unit_formatter, save_figure, PRIMARY
    STYLE_SRC = "LOCAL RECONSTRUCTION (_ft_style_local.py)"

_spec = importlib.util.spec_from_file_location("fs", os.path.join(HERE, "figures_sept.py"))
fs = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(fs)
pf = fs.pf

OUT = os.path.join(os.path.dirname(HERE), "figures", "figs_sept")
_D = pf.RESULTS_DIR
# see figure_deepseek_branch_ft.py: data/ is tracked, code/results/ is not
_R = str(pf.RESULTS_DIR)
if not os.path.exists(os.path.join(_R, "deepseek_r1_0528_shallow_pass")):
    _R = os.path.join(os.path.dirname(HERE), "code", "results")

TOK = PRIMARY
ACC = "#0E8A8A"
FLOOR_COLOR = "#E07A3F"
CLIP = 32768          # common ceiling; see module docstring

KEYS = {t for t in pf.CANON_KEYS if not str(t).startswith("math_500")}
FLOOR = float(np.mean([pf.CANON[t]["min"] for t in KEYS]))

FAB_S = [("Fable 5.1", datetime(2026, 9, 1),
          _D / "fable5.1_shallow_pass" / "claude-fable-5-1_medium_thinking_benchmark.json")]
ANTH_S = sorted(pf.OPUS_MODELS + FAB_S, key=lambda t: t[1])
DEEPSEEK = [
    ("R1-0528", datetime(2025, 5, 28),
     os.path.join(_R, "deepseek_r1_0528_shallow_pass", "deepseek_r1_0528_thinking_benchmark_90.json")),
    ("V3.2", datetime(2025, 12, 1),
     os.path.join(_R, "deepseek_v3_2_shallow_pass", "deepseek_v3_2_thinking_benchmark_90.json")),
    ("V4 Pro", datetime(2026, 4, 24),
     os.path.join(_R, "deepseek_v4_pro_shallow_pass", "deepseek_v4_pro_thinking_benchmark_90_high.json")),
]
FAMILIES = [("OpenAI (GPT)", pf.MAIN_K8),
            ("Anthropic (Opus + Fable)", ANTH_S),
            ("DeepSeek", DEEPSEEK)]


def clean_label(name):
    if name.startswith("claude-opus-"):
        return "Opus " + name[len("claude-opus-"):].replace("-", ".")
    if name.startswith("claude-fable-"):
        return "Fable " + name[len("claude-fable-"):].replace("-", ".")
    if name.startswith("gpt-"):
        return "GPT-" + name[len("gpt-"):]
    return name


def series(model_files, successes_only=True):
    """Per model: date, mean trace length, accuracy — censored at CLIP.

    A trial at or above CLIP is what a CLIP-capped backend would have truncated:
    scored WRONG, tokens clamped. Such a trial still counts in the denominator even
    though its text is empty (it is a real attempt that failed), which _trial_ok
    would otherwise silently drop and thereby inflate accuracy.
    """
    labels, dates, mean, acc, censored = [], [], [], [], 0
    for label, date, path in model_files:
        labels.append(clean_label(label))
        toks, nc, nt = [], 0, 0
        for r in pf.load_rows(path):
            if str(r["task_id"]) not in KEYS:
                continue
            texts = r.get("response_texts", [None] * len(r["correct"]))
            for tok, c, txt in zip(r["total_completion_tokens"], r["correct"], texts):
                if tok >= CLIP:
                    censored += 1
                    nt += 1                      # counted, scored wrong
                    continue
                if not fs._trial_ok(tok, txt):
                    continue
                nt += 1; nc += int(c)
                if c or not successes_only:
                    toks.append(tok)
        dates.append(date); mean.append(float(np.mean(toks)) if toks else np.nan)
        acc.append(100 * nc / max(1, nt))
    return mdates.date2num(dates), labels, mean, acc, censored


def build(fname, successes_only=True):
    use_style()
    fig, axes = plt.subplots(2, 3, figsize=(15.0, 7.4), sharex="col")
    data = [series(f, successes_only) for _, f in FAMILIES]

    all_tok = [v for _, _, m, _, _ in data for v in m if np.isfinite(v)]
    tok_hi = max(all_tok) * 1.30
    xmin = min(x.min() for x, _, _, _, _ in data)
    xmax = max(x.max() for x, _, _, _, _ in data)
    pad = (xmax - xmin) * 0.06

    for col, ((fam, _), (x, labels, mean, acc, ncens)) in enumerate(zip(FAMILIES, data)):
        a0, a1 = axes[0][col], axes[1][col]

        # --- row 1: accuracy -------------------------------------------------
        a0.plot(x, acc, "-o", color=ACC, lw=2, ms=6, zorder=3,
                mec="white", mew=1.2)
        a0.set_ylim(55, 103)
        a0.yaxis.set_major_formatter(unit_formatter(1, "%", "{:.0f}"))
        a0.set_title(fam, pad=9)
        if col == 0:
            a0.set_ylabel("Accuracy")
        # The censoring RULE is identical across columns, but the families absorb
        # very different amounts of it (DeepSeek ~24% of trials vs OpenAI ~1%).
        # That asymmetry biases accuracy DOWNWARD for the verbose family, so it is
        # stated on the figure rather than left to the caption.
        ntot = len(labels) * 8 * len(KEYS)
        a0.text(0.03, 0.05, f"{100*ncens/max(1,ntot):.0f}% of trials censored",
                transform=a0.transAxes, fontsize=7.6, color="#888888", va="bottom")

        # --- row 2: mean tokens + floor --------------------------------------
        a1.plot(x, mean, "-o", color=TOK, lw=2, ms=6, zorder=3,
                mec="white", mew=1.2)
        a1.axhline(FLOOR, color=FLOOR_COLOR, ls="--", lw=1.4, zorder=2)
        a1.set_ylim(0, tok_hi)
        a1.yaxis.set_major_formatter(unit_formatter(1e3, "k"))
        if col == 0:
            a1.set_ylabel("Mean output tokens")
            a1.text(xmin, FLOOR * 2.4, f"minimal human derivation ({FLOOR:.0f} tok)",
                    color=FLOOR_COLOR, fontsize=8, va="bottom")
        # earliest -> latest compression, the row's headline
        if np.isfinite(mean[0]) and np.isfinite(mean[-1]) and mean[-1] > 0:
            a1.text(0.97, 0.93, f"{mean[0]/mean[-1]:.1f}x fewer", transform=a1.transAxes,
                    ha="right", va="top", fontsize=9.5, color=TOK, fontweight="bold")

        for a in (a0, a1):
            a.set_xlim(xmin - pad, xmax + pad)
            a.xaxis.set_major_locator(mdates.YearLocator())
            a.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
            a.xaxis.set_minor_locator(mdates.MonthLocator(bymonth=(1, 7)))

        # direct labels beat a legend for <= 8 points that each name a model
        for i, (xi, li, mi) in enumerate(zip(x, labels, mean)):
            if not np.isfinite(mi):
                continue
            # alternate above/below: 8 GPT points collide on a single side
            up = (i % 2 == 0)
            a1.annotate(li, (xi, mi), textcoords="offset points",
                        xytext=(0, 11 if up else -15), ha="center",
                        va="bottom" if up else "top",
                        fontsize=7.2, color="#333333")
        print(f"  {fam:<26} {len(labels)} models, {ncens} trials censored at {CLIP:,}")

    fig.suptitle("Accuracy and reasoning length across model generations "
                 f"(40 competition problems, right-censored at {CLIP:,} tokens)",
                 y=0.985, fontsize=12, fontweight="bold")
    fig.text(0.5, 0.005,
             "All families censored at a common 32,768-token ceiling, so the rule is identical across "
             "columns -- but DeepSeek absorbs 23.6% of it against OpenAI's 1.4%, which biases its accuracy "
             "downward.\nDeepSeek = SiliconFlow/fp8 timeline (R1-0528 -> V3.2 -> V4 Pro April build).",
             ha="center", fontsize=8, color="#555555")
    fig.tight_layout(rect=(0, 0.045, 1, 0.965))
    return save_figure(fig, fname, outdir=OUT)


if __name__ == "__main__":
    print(f"style: {STYLE_SRC}")
    print(f"sample: {len(KEYS)} competition problems, floor {FLOOR:.0f} tok, clip {CLIP:,}")
    build("fig1_grid_deepseek", successes_only=True)
    build("fig1_grid_deepseek_alltraces", successes_only=False)
