"""
Figure 1 (3x2, FutureTech house style). Columns = OpenAI (GPT) | Anthropic
(Opus + Fable).  Rows:
  1. Accuracy over generations (whole benchmark, 45 canonical problems).
  2. Mean output tokens over generations, with the minimal-human-derivation
     floor drawn for reference.
  3. Within-problem distribution on the hard-but-doable-10 sample: per-problem
     IQR bands over generations, shaded by problem difficulty (dataset rating 4-5:
     4 = "hard", 5 = "olympiad").

Sample = the 40 competition problems (AIME 2026 I/II + HMMT Feb 2026); MATH-500 is
excluded and the floor is recomputed over the same 40 (316 tok). Rows 1-2 use the
shallow-pass set (k=8); row 3 the hard-but-doable-10 set (k=32). Both columns share
one time axis so the two families can be compared on the same calendar.

Writes:
  fig1_grid            row 3 = hard-but-doable-10, CORRECT traces  (main text)
  fig1_grid_fulldiff   row 3 = full benchmark k=8, sampled per tier
  fig1_grid_alltraces  APPENDIX: identical to fig1_grid but tokens come from ALL
                       valid attempts, right or wrong -- no conditioning on
                       correctness, so the problem mix is the same for every model

    MPLBACKEND=Agg ./venv/bin/python code/figure1_grid_ft.py
Output -> figures/figs_sept/fig1_grid*.{png,pdf}
"""
import importlib.util
import os
import re
import sys
from datetime import datetime

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.lines as mlines
import matplotlib.patches as mpatches

sys.path.insert(0, os.path.expanduser("~/.claude/skills/futuretech-charts/python"))
from futuretech_helpers import use_style, unit_formatter, save_figure
from futuretech_palette import PRIMARY

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("fs", os.path.join(HERE, "figures_sept.py"))
fs = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(fs)
pf = fs.pf
OUT = os.path.join(os.path.dirname(HERE), "figures", "figs_sept")
_D = pf.RESULTS_DIR

TOK = PRIMARY
ACC = "#0E8A8A"           # accuracy line (row 1) — teal
FLOOR_COLOR = "#E07A3F"   # minimal-human-derivation floor (row 2) — orange
# full difficulty ramp (easy -> frontier); hard-but-doable only spans 4-5
DIFF_COLOR = {2: "#FEE08B", 3: "#FDAE61", 4: "#F46D43", 5: "#D73027", 6: "#A50026"}
DIFF_NAME = {2: "easy", 3: "medium", 4: "hard", 5: "olympiad", 6: "frontier"}
# hard-but-doable uses just two levels — give them clearly distinct hues
HARD_COLOR = {4: "#EC9006", 5: "#7B1E3B"}   # hard = amber, olympiad = deep maroon

# Difficulty tiers from competition position. AIME numbers its problems in
# increasing difficulty (the "sequential rule": #1-5 are solved by 40-70%+ of
# contestants, #6-10 by 15-40%, #11-15 by under 5%). HMMT is a harder competition
# than AIME outright -- invitational, elite field, olympiad-style -- so every HMMT
# problem ranks above every AIME problem rather than being interleaved by number:
#
#     AIME   1-10   -> medium       (early AIME)
#     AIME  11-15   -> hard         (late AIME)
#     HMMT  (any)   -> very hard    (harder competition than AIME throughout)
#     MATH-500      -> easy
#
# So the hard-but-doable-10 sample spans medium / hard / very hard exactly as
# intended. Problems with no competition position (olymmath, frontiermath) have no
# position to read and return None, so they are skipped rather than mislabelled.
TIER_COLOR = {"easy": "#4DAF4A", "medium": "#FDAE61", "hard": "#D7301F", "very hard": "#7F0000"}
TIER_ORDER = ["easy", "medium", "hard", "very hard"]


def human_tier(tid):
    t = str(tid); m = re.search(r"_(\d+)$", t)
    pos = int(m.group(1)) if m else 0
    if t.startswith("math_500"):
        return "easy"
    if t.startswith("aime"):
        return "medium" if pos <= 10 else "hard"
    if t.startswith("hmmt"):
        return "very hard"                             # harder competition than AIME
    return None                                        # olymmath / frontiermath
PER_BUCKET = 3     # full-benchmark row 3: problems sampled per difficulty level

# MATH-500 is EXCLUDED from this figure. It is 5 easy problems on which the recent
# models sit at (or below) the minimal human derivation, so they drag the row-2 mean
# down and are unusable for any floor-relative statement. The sample here is the 40
# competition problems: AIME 2026 I/II + HMMT February 2026.
KEYS = {t for t in pf.CANON_KEYS if not str(t).startswith("math_500")}
# The floor must be recomputed over the SAME sample — MATH-500's canonical solutions
# are short (~202 tok), so leaving them in canon_short would understate the floor.
FLOOR = float(np.mean([pf.CANON[t]["min"] for t in KEYS]))
print(f"figure1_grid: {len(KEYS)} competition problems (MATH-500 excluded), "
      f"floor = {FLOOR:.0f} tok  (all-45 floor was {pf.canon_short:.0f})")

FAB_S = [("Fable 5.1", datetime(2026, 9, 1), _D / "fable5.1_shallow_pass" / "claude-fable-5-1_medium_thinking_benchmark.json")]
FAB_H = [("claude-fable-5-1", datetime(2026, 9, 1), _D / "hard_but_doable_10q_k32" / "claude-fable-5-1_medium_thinking_benchmark_hard_but_doable_10.json")]
ANTH_S = sorted(pf.OPUS_MODELS + FAB_S, key=lambda t: t[1])
ANTH_H = sorted(pf.OPUS_HARD10_K32 + FAB_H, key=lambda t: t[1])
FAMILIES = [("OpenAI (GPT)", pf.MAIN_K8, fs.GPT_HARD),
            ("Anthropic (Opus + Fable)", ANTH_S, ANTH_H)]


def clean_label(name):
    if name.startswith("claude-opus-"):
        return "Opus " + name[len("claude-opus-"):].replace("-", ".")
    if name.startswith("claude-fable-"):
        return "Fable " + name[len("claude-fable-"):].replace("-", ".")
    if name.startswith("gpt-"):
        return "GPT-" + name[len("gpt-"):]
    return name


def shallow_dist(model_files, successes_only=True):
    """Per model: date, mean trace length, accuracy (40 competition problems).

    successes_only=True  -> tokens from CORRECT traces only ("tokens to solve"). This
    conditions on accuracy, so later models' means include harder problems that earlier
    models never solved -- a bias AGAINST measured efficiency gains.
    successes_only=False -> tokens from EVERY valid attempt, right or wrong. No
    conditioning, so the problem mix is identical across models. Accuracy (nc/nt) is
    computed over all valid attempts either way and is unaffected by this switch.
    """
    labels, dates, mean, acc = [], [], [], []
    for label, date, path in model_files:
        labels.append(clean_label(label))
        toks, nc, nt = [], 0, 0
        for r in pf.load_rows(path):
            if str(r["task_id"]) not in KEYS:
                continue
            texts = r.get("response_texts", [None] * len(r["correct"]))
            for tok, c, txt in zip(r["total_completion_tokens"], r["correct"], texts):
                if not fs._trial_ok(tok, txt):
                    continue
                # a cap-hit trace is a real attempt (denominator) that FAILED
                # (numerator) -- see fs._trial_correct
                ok = fs._trial_correct(tok, c)
                nt += 1; nc += int(ok)
                if ok or not successes_only:
                    toks.append(tok)
        dates.append(date); mean.append(np.mean(toks))
        acc.append(100 * nc / max(1, nt))
    return mdates.date2num(dates), labels, mean, acc


def hard_perproblem(hard_files, successes_only=True):
    """Per problem: (dates, median, p25, p75) over models + its difficulty rating."""
    dates = [d for _, d, _ in hard_files]
    prob, diff = {}, {}
    for i, (label, date, path) in enumerate(hard_files):
        for r in pf.load_rows(path):
            pid = str(r["task_id"])
            if pid not in KEYS:        # drop MATH-500 and anything with no floor
                continue               # (olymmath/frontiermath have no canonical soln)
            diff[pid] = r.get("difficulty")
            texts = r.get("response_texts", [None] * len(r["correct"]))
            toks = [tok for tok, c, txt in zip(r["total_completion_tokens"], r["correct"], texts)
                    if (c or not successes_only) and fs._trial_ok(tok, txt)]
            if toks:
                d = prob.setdefault(pid, {"i": [], "med": [], "lo": [], "hi": []})
                d["i"].append(i); d["med"].append(np.median(toks))
                d["lo"].append(np.percentile(toks, 25)); d["hi"].append(np.percentile(toks, 75))
    return mdates.date2num(dates), prob, diff


use_style()
plt.rcParams.update({"axes.labelsize": 15, "xtick.labelsize": 13, "ytick.labelsize": 13,
                     "axes.titlesize": 17})


def build(fname, full_row3, successes_only=True):
    """full_row3=False -> row 3 = hard-but-doable k=32 (difficulty 4-5);
    full_row3=True -> row 3 = full benchmark k=8 (all difficulty levels 2-6).
    successes_only=False -> appendix variant on ALL attempts (see shallow_dist)."""
    # ONE SHARED TIME AXIS across both columns. With a per-column axis the two
    # families were drawn the same physical width despite covering very different
    # spans (GPT 2024-12 -> 2026-09, Anthropic 2025-11 -> 2026-09), which made
    # Anthropic's flat-high accuracy look like a property of the models instead of
    # an artifact of entering the series 11 months later. On a common axis the late
    # start is visible, and each family sits against its contemporaries.
    all_dates = [d for _, sh, _ in FAMILIES for _, d, _ in sh]
    xlo, xhi = min(all_dates), max(all_dates)
    pad = (xhi - xlo).days * 0.04
    fig, axes = plt.subplots(3, 2, figsize=(15, 13.5), sharex=True,
                             gridspec_kw={"hspace": 0.18, "wspace": 0.22})
    seen = set()
    for col, (title, shallow, hard) in enumerate(FAMILIES):
        dx, labs, mean, acc = shallow_dist(shallow, successes_only)

        a0 = axes[0][col]                                   # Row 1 — accuracy
        a0.plot(dx, acc, "-o", color=ACC, lw=2.6, ms=8, zorder=5)
        a0.set_ylim(58, 103); a0.set_title(title)
        a0.yaxis.set_major_formatter(unit_formatter(1, "%", "{:.0f}"))
        levels = [(-16, "top"), (-32, "top"), (-48, "top")]
        for i, (xi, yi, name) in enumerate(zip(dx, acc, labs)):
            dy, va = levels[i % 3]
            a0.annotate(name, (xi, yi), textcoords="offset points", xytext=(0, dy),
                        ha="center", va=va, fontsize=9, fontweight="bold", color=ACC, zorder=8,
                        bbox=dict(boxstyle="round,pad=0.12", fc="white", ec="none", alpha=0.8),
                        arrowprops=dict(arrowstyle="-", color=ACC, lw=0.6, alpha=0.6,
                                        shrinkA=1, shrinkB=3))

        a1 = axes[1][col]                                   # Row 2 — mean falling to floor
        a1.plot(dx, mean, "-o", color=TOK, lw=3, ms=8, zorder=5)
        a1.axhline(FLOOR, color=FLOOR_COLOR, lw=2, zorder=3)   # minimal human derivation
        # headroom above the curve for the compression label. Anthropic's series is
        # squeezed into the right third of the shared axis with its peak at the top,
        # so without this the label lands on the data in that column.
        a1.set_ylim(0, max(mean) * 1.38)
        a1.yaxis.set_major_formatter(unit_formatter(1e3, "k"))
        a1.annotate(f"minimal human derivation ≈ {FLOOR:.0f} tok", (dx[-1], FLOOR),
                    textcoords="offset points", xytext=(0, 5), ha="right", va="bottom",
                    fontsize=10, fontweight="bold", color=FLOOR_COLOR, zorder=6)
        # earliest -> latest compression, anchored upper-RIGHT so it reads as a
        # statement about the newest models rather than the oldest
        # The window is part of the claim: 8.5x over 21 months is not the same
        # achievement as 4.8x over 10, so the span is printed under the ratio.
        ratio = mean[0] / mean[-1] if mean[-1] else float("nan")
        d0, d1 = mdates.num2date(dx[0]), mdates.num2date(dx[-1])
        months = round((d1 - d0).days / 30.44)
        lbl = (f"{ratio:.1f}× fewer tokens" if ratio >= 1.15 else f"≈flat ({ratio:.1f}×)")
        lbl += f"\n{d0:%Y-%m} – {d1:%Y-%m}  ({months} months)"   # en dash: Helvetica
        #                                                        # Neue has no U+2192
        a1.annotate(lbl, xy=(0.97, 0.97), xycoords="axes fraction", ha="right", va="top",
                    fontsize=13.5, fontweight="bold", color=TOK, zorder=7,
                    linespacing=1.5, multialignment="center",
                    bbox=dict(boxstyle="round,pad=0.3", fc="white", ec=TOK, alpha=0.9))
        print(f"  row2 {title:<26s} {mean[0]:.0f} -> {mean[-1]:.0f} tok = {ratio:.1f}x"
              f"  over {months} months ({d0:%Y-%m} -> {d1:%Y-%m})")

        a2 = axes[2][col]                                   # Row 3 — per-problem by difficulty
        hdx, prob, diff = hard_perproblem(shallow if full_row3 else hard, successes_only)
        cat = {p: human_tier(p) for p in prob}              # human-solve-rate tiers
        prob = {p: d for p, d in prob.items() if cat[p]}    # skip anything unlabelled
        palette = TIER_COLOR
        if full_row3:                                       # sample N problems per tier
            keep = set()
            for tier in set(cat.values()):
                pids = [p for p in prob if cat[p] == tier]
                pids.sort(key=lambda p: (-len(prob[p]["i"]), p))  # widest coverage first
                keep.update(pids[:PER_BUCKET])
            prob = {p: d for p, d in prob.items() if p in keep}
        alpha = 0.16 if full_row3 else 0.13       # lighter fill so overlaps don't muddy
        lw = 1.2 if full_row3 else 2.1            # crisper median lines
        for pid, d in prob.items():
            k = cat[pid]; seen.add(k)
            c = palette.get(k, "#888888")
            xs = hdx[d["i"]]
            a2.fill_between(xs, d["lo"], d["hi"], color=c, alpha=alpha, lw=0, zorder=1)
            a2.plot(xs, d["med"], color=c, lw=lw, alpha=0.95, zorder=2)
        a2.set_ylim(0, 30000 if full_row3 else 34000)
        a2.yaxis.set_major_formatter(unit_formatter(1e3, "k"))
        a2.xaxis.set_major_locator(mdates.MonthLocator(interval=4))
        a2.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
        a2.set_xlim(mdates.date2num(xlo) - pad, mdates.date2num(xhi) + pad)
        a2.set_xlabel("Release date")

    axes[0][0].set_ylabel("Accuracy")
    cond = "correct traces" if successes_only else "all attempts"
    axes[1][0].set_ylabel(f"Mean output tokens\n({cond})")
    src = "full benchmark" if full_row3 else "hard-but-doable"
    axes[2][0].set_ylabel(f"Output tokens\n({src}, {cond})")
    # MATCHED-WINDOW check: the raw per-family ratios are not comparable because the
    # families cover different spans. Recompute each family over the LATEST-COMMON
    # window (starts at the later of the two first-model dates) so the two numbers
    # describe the same stretch of calendar time.
    starts = [min(d for _, d, _ in sh) for _, sh, _ in FAMILIES]
    t0 = max(starts)
    print(f"  matched window from {t0:%Y-%m} (the later of the two family starts):")
    for title, shallow, _ in FAMILIES:
        sub = [m for m in shallow if m[1] >= t0]
        _, _, mn, _ = shallow_dist(sub, successes_only)
        r = mn[0] / mn[-1]
        print(f"    {title:<26s} {mn[0]:.0f} -> {mn[-1]:.0f} tok = {r:.1f}x"
              f"  ({len(sub)} models, {sub[0][0]} -> {sub[-1][0]})")

    keys = [k for k in TIER_ORDER if k in seen]             # human-solve-rate tiers
    handles = [mlines.Line2D([], [], color=TIER_COLOR[k], lw=3, label=k) for k in keys]
    axes[2][1].legend(handles=handles, loc="upper right", fontsize=11, ncol=1,
                      frameon=True, framealpha=0.95, title="difficulty")
    return save_figure(fig, fname, outdir=OUT)


p1 = build("fig1_grid", full_row3=False)
p2 = build("fig1_grid_fulldiff", full_row3=True)
# APPENDIX: identical figure on ALL attempts (no conditioning on correctness), so
# the "results are largely unchanged including failures" claim is backed by the
# same code path and the same 40-problem sample.
p3 = build("fig1_grid_alltraces", full_row3=False, successes_only=False)
print("wrote", *p1, *p2, *p3, sep="\n  ")
