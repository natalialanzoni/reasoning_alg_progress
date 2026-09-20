"""
figures_sept.py  —  Figure 1, three panels: OpenAI | Anthropic | Open source.

Each panel:
  * GREEN line (left y) = mean tokens to solve the benchmark (shallow-pass runs),
    averaged over the problem set shared by that panel's models.
  * PURPLE dashed line (right y) = benchmark accuracy / score.
  * Background = per-problem IQR (p25-p75) from the hard-but-doable-10 k=32 runs,
    each problem a distinct color so you can trace how individual-problem token
    distributions shift across generations.

Open-source panel: GLM and Kimi as two lines (tokens solid, accuracy dashed, in
each family's color). No hard-but-doable k=32 runs exist for open-source yet, so
its shading is a placeholder. RELEASE DATES for GLM/Kimi are PLACEHOLDERS — edit.

Reuses CANON / load_rows / per_problem_trajectories / model configs from
paper_figures_71226.py.   Output -> figs_sept/fig1_three_panel.png
"""
import importlib.util
import os
from datetime import datetime

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.lines as mlines
import seaborn as sns

sns.set_theme(style="whitegrid")

_s = importlib.util.spec_from_file_location(
    "pf", os.path.join(os.path.dirname(__file__), "paper_figures_71226.py"))
pf = importlib.util.module_from_spec(_s); _s.loader.exec_module(pf)
load_rows = pf.load_rows
per_problem_trajectories = pf.per_problem_trajectories
DATA = pf.RESULTS_DIR              # ../data
OUT = pf.ROOT.parent / "figures" / "figs_sept"
OUT.mkdir(parents=True, exist_ok=True)

# soft, non-garish qualitative palette for the per-problem shading
PROBLEM_PALETTE = sns.color_palette("muted", 10)

GREEN = "#1B5E20"          # benchmark-mean line
ACC = "#6A1B9A"            # accuracy (right axis)
GLM_C = "#1B5E20"
KIMI_C = "#00838F"

# GPT hard-but-doable = the k=32 set (o3..5.5) + gpt-5.6-sol (added later).
GPT_HARD = list(pf.HARD10_K32) + [
    ("gpt-5.6-sol", datetime(2026, 7, 9),
     DATA / "hard_but_doable_10q_k32" / "gpt-5.6-sol_medium_thinking_benchmark_hard_but_doable_10.json"),
    ("gpt-6-astra", datetime(2026, 9, 1),
     DATA / "hard_but_doable_10q_k32" / "gpt-6-astra_medium_thinking_benchmark_hard_but_doable_10.json"),
]

# --- Open-source shallow-pass runs.  GLM dates are official; KIMI dates are PLACEHOLDERS — edit. ---
def _sp(slug):
    return DATA / f"{slug}_shallow_pass" / f"{slug}_thinking_benchmark_90.json"

GLM_SHALLOW = [
    ("GLM 4.5", datetime(2025, 7, 1), _sp("glm_4_5")),
    ("GLM 4.6", datetime(2025, 9, 1), _sp("glm_4_6")),
    ("GLM 4.7", datetime(2025, 12, 1), _sp("glm_4_7")),
    ("GLM 5",   datetime(2026, 2, 1), _sp("glm_5")),
    ("GLM 5.1", datetime(2026, 4, 1), _sp("glm_5_1")),
    ("GLM 5.2", datetime(2026, 6, 1), _sp("glm_5_2")),
    ("GLM 5.3", datetime(2026, 8, 1), _sp("glm_5_3")),
]
KIMI_SHALLOW = [
    ("Kimi K2.5", datetime(2025, 8, 1), _sp("kimi_k2_5")),
    ("Kimi K2.6", datetime(2025, 10, 1), _sp("kimi_k2_6")),
    ("Kimi K2.7", datetime(2025, 12, 1), _sp("kimi_k2_7_code")),
    ("Kimi K2-Think", datetime(2026, 3, 1), _sp("kimi_k2_thinking")),
    ("Kimi K3", datetime(2026, 7, 1), _sp("kimi_k3")),
]


def shallow_stats(model_files):
    """Per-model (mean trace length, accuracy) over the shared problem set."""
    dates, labels, per_mean, per_corr = [], [], [], []
    for label, date, path in model_files:
        if not path.exists():
            print(f"  MISSING {path}")
            continue
        mb, cb = {}, {}
        for r in load_rows(path):
            tid = str(r["task_id"])
            tt = r.get("thinking_tokens", [1] * len(r["correct"]))
            toks = [t for t in r["total_completion_tokens"] if t >= 50]
            corr = [c for c, t in zip(r["correct"], r["total_completion_tokens"])
                    if t >= 50]
            if toks:
                mb[tid] = float(np.mean(toks)); cb[tid] = corr
        dates.append(date); labels.append(label); per_mean.append(mb); per_corr.append(cb)
    common = sorted(set.intersection(*[set(p) for p in per_mean])) if per_mean else []
    means = [float(np.mean([p[t] for t in common])) for p in per_mean]
    accs = [sum(c for t in common for c in cb[t]) / max(1, sum(len(cb[t]) for t in common))
            for cb in per_corr]
    return dates, labels, means, accs


CAP = 40000        # the output cap every published run was issued at


def _trial_ok(tok, txt, cap=CAP):
    """Did this trial actually happen? (It may still be WRONG -- that is `correct`.)

    A trial counts if it produced >= 50 tokens AND either has non-empty response
    text, or hit the output cap.

    The cap clause matters and was missing. A trace that spends its whole budget
    thinking and never writes an answer has empty text and `answer_tokens == 0`, so
    the empty-text test discarded it -- removing a genuine failure from the
    DENOMINATOR and inflating accuracy for exactly the models that hit the cap.
    Measured before the fix: Opus 4.6 read 98.0% against a true 90.3% (25 dropped
    truncations), gpt-5 91.6% against 88.4% (11). Models from gpt-5.2 and Opus 5
    onward never hit the cap and are unaffected. The README already specified the
    right behaviour -- "truncated-but-real attempts (tokens == cap) also score 0%"
    -- so this was an implementation gap, not a judgement call.

    Still excluded: empty/degenerate glitches below the cap, and sub-50-token runs.
    Token means are unaffected either way, since these traces contribute no usable
    length; only the accuracy denominator changes.
    """
    if tok < 50:
        return False
    if tok >= cap:                 # truncated before answering: a real, failed attempt
        return True
    return not (txt is not None and not str(txt).strip())


def _trial_correct(tok, c, cap=CAP):
    """Did this trial deliver a correct answer? A cap-hit trial scores WRONG.

    _trial_ok only fixed the DENOMINATOR -- it made truncated attempts count. This
    fixes the NUMERATOR, which is a separate thing and was still wrong: a truncated
    response is not a delivered answer, so it cannot be right, whatever the grader
    extracted from the fragment.

    It bites because the grader falls back to "text after the last `=`" when there is
    no \\boxed{}. On a truncated trace that fallback is fishing in incomplete work. One
    real case, gpt-5 on aime_2026_ii_15: 38,720 thinking + 1,280 answer, cut off
    mid-sentence at "...the number of ordered 7", but an earlier working line read
    "= 393." -- the gold answer -- so it was scored CORRECT. The model never delivered
    it. Exactly 1 of the 56 cap-hit traces in the corpus is affected today (all 56 sit
    at exactly 40,000, none overshoot), so this moves gpt-5 by 0.3pp and nothing else,
    but the rule belongs in one place rather than in each figure script.

    Use with _trial_ok: `if not _trial_ok(...): continue` then `_trial_correct(...)`.
    """
    return bool(c) and tok < cap


def valid_stats(model_files, correct_only=False, restrict_canon=False):
    """Per-model (mean tokens, accuracy) over the shared problem set, using the
    corrected valid-trial filter. If correct_only, token means use correct
    trials only ('tokens to correctly solve'); accuracy always uses all valid
    trials. If restrict_canon, keep only the 45 problems with a canonical
    solution (drops the 2 frontiermath problems). Accepts str or Path entries."""
    import os
    dates, labels, per_mean, per_corr = [], [], [], []
    for label, date, path in model_files:
        if not os.path.exists(path):
            print(f"  MISSING {path}")
            continue
        mb, cb = {}, {}
        for r in load_rows(path):
            tid = str(r["task_id"]); n = len(r["correct"])
            if restrict_canon and tid not in pf.CANON_KEYS:
                continue
            texts = r.get("response_texts", [None] * n)
            toks, corr = [], []
            for tok, c, txt in zip(r["total_completion_tokens"], r["correct"], texts):
                if not _trial_ok(tok, txt):
                    continue
                ok = _trial_correct(tok, c)
                corr.append(int(ok))
                if (not correct_only) or ok:
                    toks.append(tok)
            if toks:
                mb[tid] = float(np.mean(toks))
            if corr:
                cb[tid] = corr
        dates.append(date); labels.append(label); per_mean.append(mb); per_corr.append(cb)
    common = sorted(set.intersection(*[set(p) for p in per_mean])) if per_mean else []
    means = [float(np.mean([p[t] for t in common])) for p in per_mean]
    accs = [sum(c for t in common for c in cb[t]) / max(1, sum(len(cb[t]) for t in common))
            for cb in per_corr]
    return dates, labels, means, accs


def valid_bands(hard_files, correct_only=False, spread="iqr"):
    """Per-problem trajectories/bands from hard files, corrected valid-trial
    filter, optional correct-only. Returns (dates, labels, traj, band, None)
    matching per_problem_trajectories' shape."""
    import os
    dates, labels, per = [], [], []
    for label, date, path in hard_files:
        if not os.path.exists(path):
            print(f"  MISSING {path}")
            continue
        d = {}
        for r in load_rows(path):
            tid = str(r["task_id"]); n = len(r["correct"])
            texts = r.get("response_texts", [None] * n)
            vals = [tok for tok, c, txt in zip(r["total_completion_tokens"], r["correct"], texts)
                    if _trial_ok(tok, txt) and ((not correct_only) or c)]
            if vals:
                d[tid] = np.array(vals, float)
        dates.append(date); labels.append(label); per.append(d)
    common = sorted(set.intersection(*[set(p) for p in per])) if per else []
    traj, band = {}, {}
    for tid in common:
        traj[tid] = [float(p[tid].mean()) for p in per]
        if spread == "iqr":
            band[tid] = ([float(np.percentile(p[tid], 25)) for p in per],
                         [float(np.percentile(p[tid], 75)) for p in per])
        else:
            band[tid] = ([float(p[tid].min()) for p in per],
                         [float(p[tid].max()) for p in per])
    return dates, labels, traj, band, None


def draw_shading(ax, hard_files):
    """Per-problem IQR ribbons (each problem its own color) + faint mean line."""
    hd, _, traj, band, _ = per_problem_trajectories(hard_files, spread="iqr")
    for i, tid in enumerate(sorted(band)):
        c = PROBLEM_PALETTE[i % len(PROBLEM_PALETTE)]
        lows, highs = band[tid]
        ax.fill_between(hd, lows, highs, color=c, alpha=0.18, zorder=1, edgecolor="none")
        ax.plot(hd, traj[tid], "-", color=c, linewidth=0.9, alpha=0.6, zorder=2)


def tokens_and_acc(ax, ax2, model_files, tok_color, tok_label, acc_color, annotate=False):
    d, l, m, a = shallow_stats(model_files)
    ax.plot(d, m, "o-", color=tok_color, linewidth=3, markersize=9, zorder=6, label=tok_label)
    ax2.plot(d, [x * 100 for x in a], "D--", color=acc_color, linewidth=2, markersize=7,
             zorder=7, alpha=0.9)
    if annotate:
        for dd, mm in zip(d, m):
            ax.annotate(f"{mm:,.0f}", (dd, mm), textcoords="offset points", xytext=(0, 11),
                        ha="center", fontsize=8, fontweight="bold", color=tok_color)
    return d, l, m, a


def set_x(ax, dates, labels):
    ax.set_xticks(dates)
    ax.set_xticklabels([f"{lab}\n{d:%Y-%m}" for lab, d in zip(labels, dates)],
                       fontsize=8, rotation=45, ha="right", fontweight="bold")


def panel_openai(ax, ax2):
    draw_shading(ax, GPT_HARD)
    d, l, _, _ = tokens_and_acc(ax, ax2, pf.MAIN_K8, GREEN, "Mean tokens", ACC, annotate=True)
    set_x(ax, d, l)
    ax.set_title("OpenAI (GPT)", fontsize=13, fontweight="bold")


def panel_anthropic(ax, ax2):
    draw_shading(ax, pf.OPUS_HARD10_K32)
    d, l, _, _ = tokens_and_acc(ax, ax2, pf.OPUS_MODELS, GREEN, "Mean tokens", ACC, annotate=True)
    set_x(ax, d, l)
    ax.set_title("Anthropic (Opus)", fontsize=13, fontweight="bold")


def panel_oss(ax, ax2):
    dg, _, _, _ = tokens_and_acc(ax, ax2, GLM_SHALLOW, GLM_C, "GLM", GLM_C)
    dk, _, _, _ = tokens_and_acc(ax, ax2, KIMI_SHALLOW, KIMI_C, "Kimi", KIMI_C)
    ax.text(0.5, 0.05, "hard-but-doable shading:\nopen-source k=32 runs pending",
            transform=ax.transAxes, ha="center", va="bottom", fontsize=8.5,
            style="italic", color="#8a8a8a",
            bbox=dict(boxstyle="round,pad=0.4", fc="white", ec="#ccc", alpha=0.85))
    alld = sorted(set(dg) | set(dk))
    ax.set_xticks(alld)
    ax.set_xticklabels([f"{d:%Y-%m}" for d in alld], fontsize=8, rotation=45, ha="right")
    ax.set_title("Open source (GLM / Kimi)", fontsize=13, fontweight="bold")


def build(panels, fname, handles):
    n = len(panels)
    # independent panels (not sharey) so every panel shows its OWN accuracy axis;
    # a common token y-limit is set below to keep the panels comparable.
    fig, axes = plt.subplots(1, n, figsize=(7.5 * n, 7))
    axes = list(np.atleast_1d(axes))
    twins = [ax.twinx() for ax in axes]
    for t in twins:
        t.set_ylim(0, 105); t.grid(False); t.tick_params(axis="y", labelcolor=ACC)
        t.set_ylabel("Accuracy / score (%)", fontsize=10, color=ACC)
    for ax, t, draw in zip(axes, twins, panels):
        draw(ax, t)
    ymax = max(ax.get_ylim()[1] for ax in axes)          # shared token scale
    for i, ax in enumerate(axes):
        ax.set_ylim(0, ymax)
        ax.set_xlabel("Model (release date)", fontsize=11)
        ax.set_ylabel("Trace length (output tokens, o200k)" if i == 0 else "",
                      fontsize=11, color=GREEN)
    fig.suptitle("Figure 1.  Reasoning length over generations\n"
                 "green = mean tokens (left axis);  purple/dashed = accuracy (right axis);  "
                 "shading = hard-but-doable-10 per-problem IQR (one color per problem)",
                 fontsize=13.5, y=1.05)
    fig.legend(handles=handles, loc="lower center", ncol=len(handles), fontsize=10,
               framealpha=0.95, bbox_to_anchor=(0.5, -0.02))
    plt.tight_layout(rect=[0, 0.04, 1, 1])
    fig.savefig(OUT / fname, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {OUT / fname}")


def main():
    tok = mlines.Line2D([], [], color=GREEN, marker="o", lw=3, label="Mean tokens (left)")
    acc = mlines.Line2D([], [], color=ACC, marker="D", ls="--", lw=2, label="Accuracy (right)")
    glm = mlines.Line2D([], [], color=GLM_C, marker="o", lw=3, label="GLM tokens")
    kim = mlines.Line2D([], [], color=KIMI_C, marker="o", lw=3, label="Kimi tokens")
    ossacc = mlines.Line2D([], [], color="#555", ls="--", marker="D", lw=2, label="accuracy (right)")
    build([panel_openai, panel_anthropic], "fig1_openai_anthropic.png", [tok, acc])
    build([panel_openai, panel_anthropic, panel_oss], "fig1_three_panel.png",
          [tok, acc, glm, kim, ossacc])


if __name__ == "__main__":
    main()
