"""
Forecast figure (FutureTech house style) — reasoning-token excess over the
irreducible reasoning floor: SOLID line through the real observed models, a clear
separator at the last model, then a DASHED extrapolation with a 95% CI band.
Observed points carry clustered (between-problem) 95% error bars.

Regression (paper eq. excess-trend), per family, unchanged from
paper_figures_71226._fit_headroom_forecast:

    log(L_ijt - C_j) = alpha_j + beta * Month_i + eps_ijt,     beta = -1/tau

  L = total output tokens (reasoning + answer), C_j = irreducible floor for problem j, alpha_j = problem FE,
  Month = months since 2025-04-01, SEs clustered by problem, fit on L > C_j.
  Code DV log(headroom-1) = log(L-C_j) - log(C_j); the -log(C_j) is absorbed by
  alpha_j so beta is identical. The C_j SUBTRACTION (decay toward the floor) and
  the problem FE (per-problem level) are separate and both present.

Versions written (PRIMARY includes the full GPT series incl. o1, the earliest anchor):
  fig4_forecast              per-family; successful traces
  fig4_forecast_2panel       tokens + log multiple-of-floor
  fig4_forecast_all_traces   ALL traces
  fig4_forecast_combined     both families on one axis
  fig4_forecast_*_no_o1      SENSITIVITY: drop the earliest point (o1)
  fig4_forecast_arith_mean_appendix   arithmetic-mean token space
  fig4_forecast_precutoff_appendix    CONTAMINATION CHECK: same fit on only the
                             models released on/before 2026-02-05, which cannot
                             have trained on the AIME/HMMT 2026 problems

Only ONE milestone is drawn (within 10% of the floor, see MILE_P).

    MPLBACKEND=Agg ./venv/bin/python code/figure_forecast_ft.py
Output -> figures/figs_sept/fig4_forecast*.{png,pdf}
"""
import importlib.util
import math
import os
import sys
from datetime import datetime, timedelta

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.lines as mlines
import matplotlib.patches as mpatches

sys.path.insert(0, os.path.expanduser("~/.claude/skills/futuretech-charts/python"))
from futuretech_helpers import use_style, unit_formatter, save_figure
from futuretech_palette import PRIMARY, CATEGORICAL

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("pf", os.path.join(HERE, "paper_figures_71226.py"))
pf = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(pf)
OUT = os.path.join(os.path.dirname(HERE), "figures", "figs_sept")

TOK = PRIMARY            # navy — data + fit (single-family panels)
FLOOR_C = "#E07A3F"      # amber — irreducible reasoning floor
SEP_C = "#8A8A8A"        # grey — observed/forecast separator
OAI_C = CATEGORICAL[0]   # blue  — OpenAI (combined plot)
ANT_C = CATEGORICAL[1]   # MIT red — Anthropic (combined plot)
FULL_C = "#6E6E6E"       # grey — full-sample trend overlaid on the appendix check
CUT_C = "#B2182B"        # red  — benchmark publication cutoff
REF = pf.canon_short   # minimal human derivation (shortest canonical), tokens

MILE_P = 0.10            # the ONLY milestone drawn: within 10% of the floor

# ---- benchmark contamination cutoff ---------------------------------------
# 40 of the 45 canonical problems are AIME 2026 I/II + HMMT February 2026:
#   AIME 2026 I   administered 2026-02-05
#   AIME 2026 II  administered 2026-02-11
#   HMMT February 2026  held   2026-02-14
# (the other 5 are MATH-500, which long predates every model here). The earliest
# public release of any benchmark problem is therefore 2026-02-05, so a model
# released on or before that date cannot have been trained on them. Refitting on
# only those models gives a contamination-free beta to compare with the full fit.
CUTOFF = datetime(2026, 2, 5)

ANTH = list(pf.OPUS_MODELS) + [
    ("Fable 5.1", datetime(2026, 9, 1),
     pf.RESULTS_DIR / "fable5.1_shallow_pass" / "claude-fable-5-1_medium_thinking_benchmark.json"),
]


def model_points(mfiles, successes_only):
    """Per model: (label, date, center, lo, hi) in tokens; point = between-problem
    geomean excess, error bar = 95% CI from the spread ACROSS problems (clustered)."""
    out = []
    for label, date, path in mfiles:
        prob = {}
        for r in pf.load_rows(path):
            tid = str(r["task_id"])
            if tid not in pf.CANON_KEYS:
                continue
            tt = r.get("thinking_tokens", [1] * len(r["correct"]))
            for tok, c, th in zip(r["total_completion_tokens"], r["correct"], tt):
                if th == 0 or tok <= 0 or (successes_only and not c):
                    continue
                h = tok / pf.CANON[tid]["min"]
                if h > 1:
                    prob.setdefault(tid, []).append(math.log(h - 1))
        pm = [float(np.mean(v)) for v in prob.values() if v]
        if not pm:
            continue
        mu = float(np.mean(pm))
        se = float(np.std(pm, ddof=1) / math.sqrt(len(pm))) if len(pm) > 1 else 0.0
        out.append((label, date, (1 + math.exp(mu)) * REF,
                    (1 + math.exp(mu - 1.96 * se)) * REF, (1 + math.exp(mu + 1.96 * se)) * REF))
    return out


def _band(fit, fdates, extra_var=0.0):
    """Band + center for the fitted average-problem decay. extra_var=0 -> 95% CI of
    the mean trend (cluster-robust cov); extra_var=sigma^2 -> 95% PREDICTION interval
    (adds model-level residual scatter, so it envelops individual model points)."""
    res = fit["res"]; names = list(res.params.index)
    pvec = res.params.values; cov = res.cov_params().values; J = fit["n_problems"]
    lo, hi, ctr = [], [], []
    for d in fdates:
        m = (d - pf.ORIGIN).days / 30.44
        x = np.array([1.0 if nm == "Intercept" else
                      (m if nm == "month" else
                       (1.0 / J if nm.startswith("C(problem)") else 0.0)) for nm in names])
        mu = float(x @ pvec); se = float((x @ cov @ x + extra_var) ** 0.5)
        lo.append((1 + math.exp(mu - 1.96 * se)) * REF)
        hi.append((1 + math.exp(mu + 1.96 * se)) * REF)
        ctr.append((1 + math.exp(mu)) * REF)
    return lo, hi, ctr


def wcb_band(mfiles, excl, successes_only, dates, B=1999, seed=0):
    """Wild cluster bootstrap OVER MODELS (Rademacher weights) for the fitted
    average-problem trend. Returns (center, lo, hi) token curves at `dates`, the
    point beta, its 95% CI, and the number of model clusters. Model is the resample
    unit because Month is constant within a model (only ~6 time points identify beta)."""
    base = mfiles[0][0]
    rows = []
    for label, date, path in mfiles:
        if excl and label == base:
            continue
        month = (date - pf.ORIGIN).days / 30.44
        for r in pf.load_rows(path):
            tid = str(r["task_id"])
            if tid not in pf.CANON_KEYS:
                continue
            tt = r.get("thinking_tokens", [1] * len(r["correct"]))
            for tok, c, th in zip(r["total_completion_tokens"], r["correct"], tt):
                if th == 0 or tok <= 0 or (successes_only and not c):
                    continue
                h = tok / pf.CANON[tid]["min"]
                if h > 1:
                    rows.append((tid, month, label, math.log(h - 1)))
    probs = sorted({r[0] for r in rows}); pidx = {p: i for i, p in enumerate(probs)}
    models = sorted({r[2] for r in rows}); midx = {m: i for i, m in enumerate(models)}
    J = len(probs); G = len(models); n = len(rows); k = J + 1
    P = np.zeros((n, k)); P[:, 0] = 1.0
    y = np.empty(n); cl = np.empty(n, dtype=int)
    for i, (tid, month, label, yy) in enumerate(rows):
        P[i, 1] = month
        kk = pidx[tid]
        if kk >= 1:
            P[i, 1 + kk] = 1.0
        y[i] = yy; cl[i] = midx[label]
    Xd = np.array([[1.0, (d - pf.ORIGIN).days / 30.44] + [1.0 / J] * (J - 1) for d in dates])
    Pinv = np.linalg.pinv(P)
    bhat = Pinv @ y
    yhat = P @ bhat; e = y - yhat
    center = (1 + np.exp(Xd @ bhat)) * REF
    rng = np.random.default_rng(seed)
    wm = rng.choice([-1.0, 1.0], size=(B, G))     # one Rademacher sign per model per rep
    Ystar = yhat[None, :] + wm[:, cl] * e[None, :]
    Bstar = Ystar @ Pinv.T                         # (B, k)
    Cmu = Bstar @ Xd.T                             # (B, n_dates)
    lo = (1 + np.exp(np.percentile(Cmu, 2.5, axis=0))) * REF
    hi = (1 + np.exp(np.percentile(Cmu, 97.5, axis=0))) * REF
    bci = np.percentile(Bstar[:, 1], [2.5, 97.5])
    return center, lo, hi, float(bhat[1]), bci, G


def print_spec(title, fit):
    print(f"\n=== REGRESSION — {title} ===")
    print("  Estimator : OLS with cluster-robust (by problem) standard errors")
    print("  Equation  : log(L - C_j) = alpha_j + beta*Month + eps   (beta = -1/tau)")
    print("  Sample    : " + ("correct" if fit["successes_only"] else "all") +
          " traces with L > C_j" +
          (f", excluding baseline {fit['baseline_label']}" if fit["exclude_baseline"] else ""))
    print(f"  C(problem): {fit['n_problems']} FE   (N = {fit['n_obs']} traces)")
    b = fit["beta"]
    print(f"  beta_month = {b:.4f}  (SE {fit['beta_se']:.4f})   tau = {-1.0/b:.2f} months")
    print(f"  => {fit['quarterly_pct']:.1f}% less excess reasoning per quarter")
    for p in (0.25, 0.10, 0.05):
        print(f"  within {int(p*100):>2d}% of floor: {fit['mile'][p]:%Y-%m}")


def draw_family(ax, mfiles, excl, successes_only, color, milestones=True,
                q_xy=(0.96, 0.82), q_label=None, ratio=False, show_q=True,
                max_end=None):
    """Real (solid) observed line, then forecast + CI band. ratio=False plots absolute
    tokens; ratio=True plots the MULTIPLE OF THE FLOOR (L/floor) — divide by REF so the
    floor sits at 1x — with a DOTTED forecast (used on the log panel underneath)."""
    norm = REF if ratio else 1.0
    fc_ls = ":" if ratio else "--"
    fit = pf._fit_headroom_forecast(mfiles, exclude_baseline=excl, successes_only=successes_only)
    pts = [p for p in model_points(mfiles, successes_only)
           if not (excl and p[0] == fit["baseline_label"])]
    odates = [p[1] for p in pts]
    octr = [p[2] / norm for p in pts]

    # fitted trend across observed + forecast, with a continuous shaded 95% CI
    # ribbon; SOLID over the observed window, DASHED/DOTTED for the extrapolation.
    t_first, t_last = odates[0], odates[-1]
    end_mo = int((fit["mile"][MILE_P] - t_first).days / 30.44) + 3  # stop 3mo past within-10%
    full = [t_first + timedelta(days=30.44 * mo) for mo in range(0, end_mo + 1)]
    if max_end is not None:                      # cap a slow fit's runaway horizon
        full = [d for d in full if d <= max_end] or full[:2]
    # wild cluster bootstrap over models -> honest 95% CI band for the trend
    ctr, lo, hi, bhat, bci, G = wcb_band(mfiles, excl, successes_only, full)
    ctr = [c / norm for c in ctr]; lo = [x / norm for x in lo]; hi = [x / norm for x in hi]
    q = lambda bb: (1 - math.exp(3 * bb)) * 100
    print(f"  wild-cluster-bootstrap ({G} models): beta 95% CI [{bci[0]:.3f}, {bci[1]:.3f}]"
          f"  -> {q(bci[1]):.0f}-{q(bci[0]):.0f}% / quarter")
    ax.fill_between(full, lo, hi, color=color, alpha=0.20, lw=0, zorder=3)
    sd = [(d, c) for d, c in zip(full, ctr) if d <= t_last]
    dd = [(d, c) for d, c in zip(full, ctr) if d >= t_last]
    ax.plot([d for d, _ in sd], [c for _, c in sd], "-", color=color, lw=2.6, zorder=4)
    ax.plot([d for d, _ in dd], [c for _, c in dd], fc_ls, color=color, lw=2.6, zorder=4)
    ax.plot(odates, octr, "o", color=color, ms=10, zorder=6)

    if show_q and q_label:
        ax.annotate(f"{q_label}: {fit['quarterly_pct']:.0f}% / quarter", xy=q_xy,
                    xycoords="axes fraction", ha="right", va="center",
                    fontsize=14, fontweight="bold", color=color)
    elif show_q:
        ax.annotate(f"{fit['quarterly_pct']:.0f}% less reasoning\nrequired / quarter",
                    xy=q_xy, xycoords="axes fraction", ha="right", va="center",
                    fontsize=15, fontweight="bold", color=color)

    ymax = max(max(octr), max(hi)) * 1.06
    if milestones:
        # ONE milestone only — within 10% of the floor — so the date reads cleanly.
        d = fit["mile"][MILE_P]
        ax.axvline(d, color=color, lw=1.8, ls=":", alpha=0.85, zorder=2)
        # anchored LEFT of the line: the milestone sits at the far right of the
        # forecast, so a right-side label would spill out of the axes.
        ax.annotate(f"within {int(MILE_P * 100)}% of floor: {d:%Y-%m}", (d, ymax * 0.52),
                    textcoords="offset points", xytext=(-10, 0), ha="right", va="center",
                    fontsize=12.5, color=color, fontweight="bold", zorder=8,
                    annotation_clip=True,
                    bbox=dict(boxstyle="round,pad=0.22", fc="white", ec=color,
                              lw=0.8, alpha=0.95))
    return fit, t_last, full[-1], ymax


def _floor(ax, xend=None):
    """Floor line + label. The floor is ~303 tok against a 10-20k y-axis, so the
    label is anchored to the LEFT edge (where the decay curve is still high and the
    space is empty) in x-axes-fraction / y-data coords, with an opaque box — at the
    right edge it collided with the curve as it lands on the floor."""
    ax.axhspan(0, REF, color=FLOOR_C, alpha=0.10, zorder=0)
    ax.axhline(REF, color=FLOOR_C, lw=2.4, zorder=3)
    ax.annotate(f"minimal human derivation ≈ {REF:,.0f} tok",
                xy=(0.015, REF), xycoords=("axes fraction", "data"),
                textcoords="offset points", xytext=(0, 10), ha="left", va="bottom",
                fontsize=13.5, fontweight="bold", color=FLOOR_C, zorder=9,
                bbox=dict(boxstyle="round,pad=0.28", fc="white", ec=FLOOR_C,
                          lw=0.9, alpha=0.96))


def _sep(ax, t_last, ytop, color=SEP_C, labels=True):
    ax.axvline(t_last, color=color, lw=1.6, ls="--", zorder=2)
    if labels:
        ax.annotate("observed", (t_last, ytop), textcoords="offset points",
                    xytext=(-6, 0), ha="right", va="top", fontsize=11, style="italic", color=color)
        ax.annotate("forecast", (t_last, ytop), textcoords="offset points",
                    xytext=(6, 0), ha="left", va="top", fontsize=11, style="italic", color=color)


def _floor_ratio(ax, xend):
    """Floor at 1x for the multiplier (log) panel — label left-anchored, boxed."""
    ax.axhline(1.0, color=FLOOR_C, lw=2.4, zorder=3)
    ax.annotate("minimal human derivation (1×)",
                xy=(0.015, 1.0), xycoords=("axes fraction", "data"),
                textcoords="offset points", xytext=(0, 10), ha="left", va="bottom",
                fontsize=13.5, fontweight="bold", color=FLOOR_C, zorder=9,
                bbox=dict(boxstyle="round,pad=0.28", fc="white", ec=FLOOR_C,
                          lw=0.9, alpha=0.96))


def model_amean(mfiles, successes_only):
    """Per model: (label, date, arithmetic-mean L in tokens), problem-weighted
    (mean over problems of each problem's mean trace length)."""
    out = []
    for label, date, path in mfiles:
        prob = {}
        for r in pf.load_rows(path):
            tid = str(r["task_id"])
            if tid not in pf.CANON_KEYS:
                continue
            tt = r.get("thinking_tokens", [1] * len(r["correct"]))
            for tok, c, th in zip(r["total_completion_tokens"], r["correct"], tt):
                if th == 0 or tok <= 0 or (successes_only and not c):
                    continue
                prob.setdefault(tid, []).append(tok)
        pm = [float(np.mean(v)) for v in prob.values() if v]
        if pm:
            out.append((label, date, float(np.mean(pm))))
    return out


use_style()
plt.rcParams.update({"axes.labelsize": 17, "xtick.labelsize": 15, "ytick.labelsize": 15,
                     "axes.titlesize": 18})


def build(fname, exclude_earliest, successes_only):
    panels = [("OpenAI (GPT)", pf.MAIN_K8, exclude_earliest),
              ("Anthropic (Opus + Fable)", ANTH, False)]
    print(f"\n########## {fname} ##########")
    fig, axes = plt.subplots(1, 2, figsize=(16, 6.5), gridspec_kw={"wspace": 0.22})
    for ax, (title, mfiles, excl) in zip(axes, panels):
        fit, t_last, xend, ymax = draw_family(ax, mfiles, excl, successes_only, TOK)
        print_spec(title, fit)
        _floor(ax, xend)
        _sep(ax, t_last, ymax)
        start = (mfiles[1] if excl else mfiles[0])[1]
        ax.set_ylim(0, ymax)
        ax.set_xlim(start - timedelta(days=40), xend + timedelta(days=20))
        ax.set_title(title); ax.set_xlabel("Date")
        ax.yaxis.set_major_formatter(unit_formatter(1e3, "k"))
        ax.xaxis.set_major_locator(mdates.YearLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    axes[0].set_ylabel(f"Output tokens: reasoning + answer ({'correct' if successes_only else 'all'} traces)")
    handles = [
        mlines.Line2D([], [], color=TOK, lw=2.6, marker="o", ms=9, label="Fitted trend + data points"),
        mlines.Line2D([], [], color=TOK, lw=2.6, ls="--", label="Forecast (extrapolated)"),
        mpatches.Patch(color=TOK, alpha=0.2, label="95% CI (wild bootstrap)"),
        mlines.Line2D([], [], color=SEP_C, lw=1.6, ls="--", label="Forecast start"),
        mlines.Line2D([], [], color=FLOOR_C, lw=2.4, label="Minimal human derivation"),
    ]
    fig.legend(handles=handles, loc="lower center", ncol=5, fontsize=13,
               frameon=True, framealpha=0.95, bbox_to_anchor=(0.5, -0.13))
    plt.tight_layout(rect=[0, 0.02, 1, 1.0])
    paths = save_figure(fig, fname, outdir=OUT)
    print("wrote", *paths, sep="\n  ")


def build_combined(fname, successes_only=True, exclude_earliest=True):
    fams = [("OpenAI (GPT)", pf.MAIN_K8, exclude_earliest, OAI_C),
            ("Anthropic (Opus + Fable)", ANTH, False, ANT_C)]
    print(f"\n########## {fname}  (both families) ##########")
    fig, ax = plt.subplots(figsize=(12.5, 7))
    ymax, xlo, xhi, tlast_all, handles = 0, None, None, None, []
    for yi, (name, mfiles, excl, col) in enumerate(fams):
        fit, t_last, xend, ym = draw_family(ax, mfiles, excl, successes_only, col,
                                            milestones=False, q_xy=(0.97, 0.92 - 0.07 * yi),
                                            q_label=name.split(" (")[0])
        print_spec(name, fit)
        ymax = max(ymax, ym)
        start = (mfiles[1] if excl else mfiles[0])[1]
        s = start - timedelta(days=40); e = xend + timedelta(days=20)
        xlo = s if xlo is None else min(xlo, s); xhi = e if xhi is None else max(xhi, e)
        tlast_all = t_last if tlast_all is None else max(tlast_all, t_last)
        handles.append(mlines.Line2D([], [], color=col, lw=2.6, marker="o", ms=8, label=name))
    _floor(ax, xhi)
    _sep(ax, tlast_all, ymax)
    ax.set_ylim(0, ymax); ax.set_xlim(xlo, xhi)
    ax.set_ylabel(f"Output tokens: reasoning + answer ({'correct' if successes_only else 'all'} traces)")
    ax.set_xlabel("Date")
    ax.yaxis.set_major_formatter(unit_formatter(1e3, "k"))
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    handles += [mpatches.Patch(color="#888888", alpha=0.2, label="95% CI (wild bootstrap)"),
                mlines.Line2D([], [], color=SEP_C, lw=1.6, ls="--", label="Forecast start"),
                mlines.Line2D([], [], color=FLOOR_C, lw=2.4, label="Minimal human derivation")]
    fig.legend(handles=handles, loc="lower center", ncol=5, fontsize=13,
               frameon=True, framealpha=0.95, bbox_to_anchor=(0.5, -0.11))
    plt.tight_layout(rect=[0, 0.02, 1, 1.0])
    paths = save_figure(fig, fname, outdir=OUT)
    print("wrote", *paths, sep="\n  ")


def build_decay_2panel(fname, exclude_earliest=True, successes_only=True):
    """2 rows x 2 cols. Top: absolute tokens (decay + forecast). Bottom: multiple of
    the floor (L/MHD) on a LOG axis, floor at 1x, DOTTED projection."""
    panels = [("OpenAI (GPT)", pf.MAIN_K8, exclude_earliest),
              ("Anthropic (Opus + Fable)", ANTH, False)]
    print(f"\n########## {fname} ##########")
    fig, axes = plt.subplots(2, 2, figsize=(16, 12), sharex="col",
                             gridspec_kw={"wspace": 0.22, "hspace": 0.13})
    for col, (title, mfiles, excl) in enumerate(panels):
        start = (mfiles[1] if excl else mfiles[0])[1]
        at = axes[0][col]                                   # top — absolute tokens
        fit, t_last, xend, ymax = draw_family(at, mfiles, excl, successes_only, TOK)
        _floor(at, xend); _sep(at, t_last, ymax * 0.98)
        at.set_ylim(0, ymax); at.set_xlim(start - timedelta(days=40), xend + timedelta(days=20))
        at.set_title(title); at.yaxis.set_major_formatter(unit_formatter(1e3, "k"))

        ab = axes[1][col]                                   # bottom — multiple of floor (log)
        _, t_last2, xend2, ymax2 = draw_family(ab, mfiles, excl, successes_only, TOK,
                                               milestones=False, ratio=True, show_q=False)
        ab.set_yscale("log"); _floor_ratio(ab, xend2)
        ab.set_ylim(0.9, ymax2 * 1.4)
        _sep(ab, t_last2, ymax2 * 1.3, labels=False)
        ab.set_xlabel("Date")
        ab.xaxis.set_major_locator(mdates.YearLocator())
        ab.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    axes[0][0].set_ylabel(f"Output tokens: reasoning + answer\n({'correct' if successes_only else 'all'} traces)")
    axes[1][0].set_ylabel("Multiple of the floor  (L / MHD)")
    handles = [
        mlines.Line2D([], [], color=TOK, lw=2.6, marker="o", ms=9, label="Fitted trend + data points"),
        mlines.Line2D([], [], color=TOK, lw=2.6, ls="--", label="Forecast (tokens)"),
        mlines.Line2D([], [], color=TOK, lw=2.6, ls=":", label="Forecast (multiple of floor)"),
        mpatches.Patch(color=TOK, alpha=0.2, label="95% CI (wild bootstrap)"),
        mlines.Line2D([], [], color=FLOOR_C, lw=2.4, label="Minimal human derivation"),
    ]
    fig.legend(handles=handles, loc="lower center", ncol=5, fontsize=13,
               frameon=True, framealpha=0.95, bbox_to_anchor=(0.5, -0.06))
    plt.tight_layout(rect=[0, 0.02, 1, 1.0])
    paths = save_figure(fig, fname, outdir=OUT)
    print("wrote", *paths, sep="\n  ")


def build_arith_mean(fname, exclude_earliest=True, successes_only=True):
    """Appendix: same decay but plotted as the ARITHMETIC MEAN token count per model
    (problem-weighted), so the trend is readable in absolute token space. Forecast is a
    simple OLS of log(mean_L - floor) on month across the model means."""
    panels = [("OpenAI (GPT)", pf.MAIN_K8, exclude_earliest),
              ("Anthropic (Opus + Fable)", ANTH, False)]
    print(f"\n########## {fname}  (arithmetic mean) ##########")
    fig, axes = plt.subplots(1, 2, figsize=(16, 6.5), gridspec_kw={"wspace": 0.22})
    for ax, (title, mfiles, excl) in zip(axes, panels):
        base = mfiles[0][0]
        pts = [p for p in model_amean(mfiles, successes_only) if not (excl and p[0] == base)]
        odates = [p[1] for p in pts]; oy = [p[2] for p in pts]
        m = np.array([(d - pf.ORIGIN).days / 30.44 for d in odates])
        yv = np.log(np.array(oy) - REF)                     # excess over floor
        b1, b0 = np.polyfit(m, yv, 1)                       # slope, intercept
        t_last = odates[-1]
        end = t_last + timedelta(days=30.44 * 14)
        full = [odates[0] + timedelta(days=30.44 * k) for k in
                range(0, int((end - odates[0]).days / 30.44) + 1)]
        fm = np.array([(d - pf.ORIGIN).days / 30.44 for d in full])
        fc = np.exp(b0 + b1 * fm) + REF
        sd = [(d, c) for d, c in zip(full, fc) if d <= t_last]
        dd = [(d, c) for d, c in zip(full, fc) if d >= t_last]
        ax.plot([d for d, _ in sd], [c for _, c in sd], "-", color=TOK, lw=2.6, zorder=4)
        ax.plot([d for d, _ in dd], [c for _, c in dd], "--", color=TOK, lw=2.6, zorder=4)
        ax.plot(odates, oy, "o", color=TOK, ms=10, zorder=6)
        ymax = max(max(oy), max(fc)) * 1.06
        _floor(ax, full[-1]); _sep(ax, t_last, ymax * 0.98)
        ax.set_ylim(0, ymax)
        ax.set_xlim(odates[0] - timedelta(days=40), full[-1] + timedelta(days=20))
        ax.set_title(title); ax.set_xlabel("Date")
        ax.yaxis.set_major_formatter(unit_formatter(1e3, "k"))
        ax.xaxis.set_major_locator(mdates.YearLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
        q = (1 - math.exp(3 * b1)) * 100
        ax.annotate(f"{q:.0f}% fewer tokens\n/ quarter (mean)", xy=(0.96, 0.82),
                    xycoords="axes fraction", ha="right", va="center",
                    fontsize=15, fontweight="bold", color=TOK)
    axes[0].set_ylabel(f"Mean output tokens: reasoning + answer ({'correct' if successes_only else 'all'} traces)")
    handles = [
        mlines.Line2D([], [], color=TOK, lw=2.6, marker="o", ms=9, label="Arithmetic mean + fit"),
        mlines.Line2D([], [], color=TOK, lw=2.6, ls="--", label="Forecast (extrapolated)"),
        mlines.Line2D([], [], color=SEP_C, lw=1.6, ls="--", label="Forecast start"),
        mlines.Line2D([], [], color=FLOOR_C, lw=2.4, label="Minimal human derivation"),
    ]
    fig.legend(handles=handles, loc="lower center", ncol=4, fontsize=13,
               frameon=True, framealpha=0.95, bbox_to_anchor=(0.5, -0.13))
    plt.tight_layout(rect=[0, 0.02, 1, 1.0])
    paths = save_figure(fig, fname, outdir=OUT)
    print("wrote", *paths, sep="\n  ")


def _pre_cutoff(mfiles):
    """Models released on or before the first benchmark problem went public."""
    return [m for m in mfiles if m[1] <= CUTOFF]


def _is_new(tid):
    """True for the Feb-2026 competition problems (only post-cutoff models could
    possibly have memorised them); False for MATH-500, which every model here has
    had in its training corpus for years."""
    return not str(tid).startswith("math_500")


def _vintage_rows(mfiles, successes_only=True):
    """Trace-level frame with a `new` flag, for the problem-vintage DiD."""
    import pandas as pd
    rows = []
    for label, date, path in mfiles:
        month = (date - pf.ORIGIN).days / 30.44
        for r in pf.load_rows(path):
            tid = str(r["task_id"])
            if tid not in pf.CANON_KEYS:
                continue
            tt = r.get("thinking_tokens", [1] * len(r["correct"]))
            for tok, c, th in zip(r["total_completion_tokens"], r["correct"], tt):
                if th == 0 or tok <= 0 or (successes_only and not c):
                    continue
                h = tok / pf.CANON[tid]["min"]
                if h > 1:
                    rows.append({"problem": tid, "month": month, "date": date,
                                 "new": int(_is_new(tid)), "y": math.log(h - 1)})
    return pd.DataFrame(rows)


def _vintage_analysis(mfiles, successes_only=True):
    """Problem-vintage DiD. Fits, on the FULL time window (so it is NOT confounded by
    the window truncation the pre-cutoff refit suffers):

        log(L - C_j) = alpha_j + beta*Month + gamma*(Month x New_j) + eps

    gamma < 0 => the problems only the newest models could have memorised compress
    FASTER than the ones every model already memorised, i.e. a contamination signal.
    gamma ~ 0 => compression is vintage-independent => contamination is not driving it.
    Also returns a separate same-spec fit per vintage for plotting.
    """
    import statsmodels.formula.api as smf
    df = _vintage_rows(mfiles, successes_only)
    res = smf.ols("y ~ month + month:new + C(problem)", data=df).fit(
        cov_type="cluster", cov_kwds={"groups": df["problem"]})
    ci = res.conf_int().loc["month:new"]
    out = {"gamma": res.params["month:new"], "gamma_se": res.bse["month:new"],
           "gamma_p": res.pvalues["month:new"], "gamma_ci": (ci[0], ci[1]), "per": {}}
    for nv in (0, 1):
        d = df[df["new"] == nv]
        r2 = smf.ols("y ~ month + C(problem)", data=d).fit(
            cov_type="cluster", cov_kwds={"groups": d["problem"]})
        b = r2.params["month"]
        fe = [v for k, v in r2.params.items() if k.startswith("C(problem)")]
        a = r2.params["Intercept"] + sum(fe) / d["problem"].nunique()
        out["per"][nv] = {"beta": b, "a": a, "se": r2.bse["month"],
                          "pct": (1 - math.exp(3 * b)) * 100,
                          "n_obs": int(r2.nobs), "n_prob": int(d["problem"].nunique())}
    # per-model observed points within each vintage (geomean excess -> tokens)
    for nv in (0, 1):
        pts = []
        for date, g in df[df["new"] == nv].groupby("date"):
            pm = g.groupby("problem")["y"].mean()
            pts.append((date, (1 + math.exp(float(pm.mean()))) * REF))
        out["per"][nv]["pts"] = sorted(pts)
    return out


def _cutoff_band(ax, ytop):
    """Shade AIME-I -> HMMT-Feb publication window and mark the cutoff."""
    ax.axvspan(datetime(2026, 2, 5), datetime(2026, 2, 14), color=CUT_C, alpha=0.16,
               lw=0, zorder=1)
    ax.axvline(CUTOFF, color=CUT_C, lw=1.8, zorder=2)
    ax.annotate("benchmark problems\npublished (Feb 2026)", (CUTOFF, ytop),
                textcoords="offset points", xytext=(9, 0), ha="left", va="top",
                fontsize=11.5, fontweight="bold", color=CUT_C, zorder=9,
                bbox=dict(boxstyle="round,pad=0.22", fc="white", ec=CUT_C,
                          lw=0.8, alpha=0.95))


def build_contamination(fname, successes_only=True):
    """APPENDIX — contamination check. Refits the IDENTICAL excess-trend spec using
    only models released on or before 2026-02-05, which therefore cannot have been
    trained on the AIME 2026 I/II + HMMT Feb 2026 problems that make up 40 of the 45
    canonical items. If beta matches the full-sample beta, the measured decline in
    reasoning length is not an artifact of newer models having memorised the
    benchmark. The full-sample fitted trend is overlaid in grey for comparison.

    Panel 1 is single-lab (GPT), so no cross-lab pooling is involved. Panel 2 pools
    GPT with the pre-cutoff Opus models to widen the sample (one common slope, no lab
    FE — appendix-grade). Caveats: the pre-cutoff window is shorter than the full
    window, and the wild bootstrap has few model clusters, so its CI is coarse.
    """
    gpt_pre = _pre_cutoff(pf.MAIN_K8)
    pooled_full = sorted(list(pf.MAIN_K8) + list(ANTH), key=lambda t: t[1])
    pooled_pre = _pre_cutoff(pooled_full)
    panels = [("OpenAI (GPT) — pre-cutoff models only", gpt_pre, list(pf.MAIN_K8)),
              ("GPT + Opus pooled — pre-cutoff models only", pooled_pre, pooled_full)]

    print(f"\n########## {fname}  (CONTAMINATION CHECK) ##########")
    print(f"  cutoff = {CUTOFF:%Y-%m-%d}  (AIME 2026 I administered; AIME II 02-11, HMMT 02-14)")
    summary = []
    fig, axes = plt.subplots(1, 3, figsize=(22, 6.6), gridspec_kw={"wspace": 0.2})
    for ax, (title, pre, full_set) in zip(axes, panels):
        print(f"\n  --- {title} ---")
        print(f"      kept  ({len(pre)}): " + ", ".join(f"{l} {d:%Y-%m}" for l, d, _ in pre))
        print(f"      dropped ({len(full_set) - len(pre)}): " +
              ", ".join(f"{l} {d:%Y-%m}" for l, d, _ in full_set if d > CUTOFF))

        # The pre-cutoff fit is slower, so its within-10% date is 2031-2033; letting
        # that set the x-range would squeeze the observed points into the left tenth.
        # Cap the horizon and report the milestone dates as text instead.
        span_end = datetime(2029, 1, 1)
        fit, t_last, xend, ymax = draw_family(
            ax, pre, False, successes_only, TOK, milestones=False, max_end=span_end,
            q_xy=(0.97, 0.64), q_label="Pre-cutoff models")
        print_spec(title, fit)

        # overlay the FULL-sample fitted trend (grey dash-dot) on the same span
        fit_full = pf._fit_headroom_forecast(full_set, exclude_baseline=False,
                                             successes_only=successes_only)
        n_mo = int((span_end - pre[0][1]).days / 30.44) + 1
        gd = [pre[0][1] + timedelta(days=30.44 * k) for k in range(n_mo + 1)]
        gy = [fit_full["hhat"](d) * REF for d in gd]
        ax.plot(gd, gy, ls="-.", color=FULL_C, lw=2.2, alpha=0.9, zorder=5)
        ax.annotate(f"Full sample: {fit_full['quarterly_pct']:.0f}% / quarter",
                    xy=(0.97, 0.54), xycoords="axes fraction", ha="right", va="center",
                    fontsize=14, fontweight="bold", color=FULL_C)
        ax.annotate(f"within {int(MILE_P * 100)}% of floor —  pre-cutoff "
                    f"{fit['mile'][MILE_P]:%Y-%m}  ·  full {fit_full['mile'][MILE_P]:%Y-%m}",
                    xy=(0.97, 0.43), xycoords="axes fraction", ha="right", va="center",
                    fontsize=11, color="#333333", zorder=8,
                    bbox=dict(boxstyle="round,pad=0.22", fc="white", ec="#BBBBBB",
                              lw=0.8, alpha=0.95))

        ymax = max(ymax, max(gy) * 1.06)
        _floor(ax)
        _cutoff_band(ax, ymax * 0.98)
        ax.set_ylim(0, ymax)
        ax.set_xlim(pre[0][1] - timedelta(days=40), span_end + timedelta(days=20))
        ax.set_title(title, fontsize=15)
        ax.set_xlabel("Date")
        ax.yaxis.set_major_formatter(unit_formatter(1e3, "k"))
        ax.xaxis.set_major_locator(mdates.YearLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
        summary.append((title, fit, fit_full, len(pre), len(full_set)))

    # ---- Panel 3: problem-vintage DiD on the FULL window ------------------
    # The pre-cutoff refit above necessarily also SHORTENS the window, so a flatter
    # beta there is ambiguous (contamination vs. genuine recent acceleration). This
    # panel breaks the tie: it keeps every model and splits the PROBLEMS instead.
    # LOG y-axis: the outcome is log excess, so equal decay rates render as PARALLEL
    # lines — which is exactly the thing the reader has to judge here.
    ax = axes[2]
    va = _vintage_analysis(pooled_full, successes_only)
    VCOL = {0: ANT_C, 1: OAI_C}
    VLAB = {0: "MATH-500 — old, in every model's training data",
            1: "AIME/HMMT 2026 — new, only post-cutoff models could have seen"}
    handles3, ymax3 = [], 0
    for nv in (1, 0):
        p = va["per"][nv]
        pts = p["pts"]
        d0, d1 = pts[0][0], pts[-1][0]
        n_mo = int((d1 - d0).days / 30.44) + 1
        cd = [d0 + timedelta(days=30.44 * k) for k in range(n_mo + 1)]
        cy = [(1 + math.exp(p["a"] + p["beta"] * ((d - pf.ORIGIN).days / 30.44))) * REF
              for d in cd]
        ax.plot(cd, cy, "-", color=VCOL[nv], lw=2.8, zorder=4)
        ax.plot([d for d, _ in pts], [v for _, v in pts], "o", color=VCOL[nv],
                ms=9, zorder=6)
        ymax3 = max(ymax3, max(cy), max(v for _, v in pts))
        # direct-label each line at its right end; series identity is in the figure legend
        ax.annotate(f"{p['pct']:.0f}% / quarter", (cd[-1], cy[-1]),
                    textcoords="offset points", xytext=(9, -2), ha="left", va="center",
                    fontsize=12.5, fontweight="bold", color=VCOL[nv], zorder=8)
        handles3.append(mlines.Line2D(
            [], [], color=VCOL[nv], lw=2.8, marker="o", ms=8,
            label=f"{VLAB[nv]} ({p['n_prob']} problems)"))
    g, gp, gci = va["gamma"], va["gamma_p"], va["gamma_ci"]
    verdict = "no contamination signal" if gp > 0.05 else "CONTAMINATION SIGNAL"
    ax.annotate(f"interaction γ = {g:+.3f}  (p = {gp:.2f})\n→ {verdict}",
                xy=(0.97, 0.90), xycoords="axes fraction", ha="right", va="top",
                fontsize=12.5, fontweight="bold", color="#333333", zorder=9,
                bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="#333333",
                          lw=0.9, alpha=0.96))
    _floor(ax)
    ax.set_yscale("log")
    ax.set_ylim(REF * 0.62, ymax3 * 3.4)
    _cutoff_band(ax, ymax3 * 3.1)
    ax.set_xlim(min(va["per"][1]["pts"])[0] - timedelta(days=40),
                max(va["per"][1]["pts"])[0] + timedelta(days=210))
    ax.set_title("Same models, problems split by vintage\n(full window — breaks the tie)",
                 fontsize=15)
    ax.set_xlabel("Date")
    ax.yaxis.set_major_formatter(unit_formatter(1e3, "k"))
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

    axes[0].set_ylabel(f"Output tokens: reasoning + answer "
                       f"({'correct' if successes_only else 'all'} traces)")
    handles = [
        mlines.Line2D([], [], color=TOK, lw=2.6, marker="o", ms=9,
                      label="Panels 1-2: pre-cutoff fit + models (cannot be contaminated)"),
        mlines.Line2D([], [], color=TOK, lw=2.6, ls="--", label="Pre-cutoff forecast"),
        mpatches.Patch(color=TOK, alpha=0.2, label="95% CI (wild bootstrap)"),
        mlines.Line2D([], [], color=FULL_C, lw=2.2, ls="-.", label="Full-sample fitted trend"),
    ] + handles3 + [
        mpatches.Patch(color=CUT_C, alpha=0.16, label="Benchmark published (Feb 2026)"),
        mlines.Line2D([], [], color=FLOOR_C, lw=2.4, label="Minimal human derivation"),
    ]
    fig.legend(handles=handles, loc="lower center", ncol=4, fontsize=11.5,
               frameon=True, framealpha=0.95, bbox_to_anchor=(0.5, -0.15))
    plt.tight_layout(rect=[0, 0.02, 1, 1.0])
    paths = save_figure(fig, fname, outdir=OUT)

    print("\n  ===== CONTAMINATION CHECK SUMMARY =====")
    print(f"  {'sample':<44s} {'n':>3s} {'beta':>9s} {'SE':>7s} {'%/qtr':>7s} {'within-10%':>11s}")
    for title, fit, fit_full, npre, nfull in summary:
        for tag, f, n in ((f"{title.split(' — ')[0]}: PRE-CUTOFF", fit, npre),
                          (f"{title.split(' — ')[0]}: full sample", fit_full, nfull)):
            mile = f"{f['mile'][MILE_P]:%Y-%m}"
            print(f"  {tag:<44s} {n:>3d} {f['beta']:>9.4f} {f['beta_se']:>7.4f} "
                  f"{f['quarterly_pct']:>6.1f}% {mile:>11s}")
    print("  NOTE: the pre-cutoff refit also SHORTENS the window, so a flatter beta")
    print("        there is ambiguous (contamination vs. genuine recent acceleration).")
    print("\n  ===== PROBLEM-VINTAGE DiD (full window — breaks the tie) =====")
    for nv, tag in ((0, "OLD  MATH-500 (all models memorised)"),
                    (1, "NEW  AIME/HMMT 2026 (post-cutoff only)")):
        p = va["per"][nv]
        print(f"  {tag:<42s} {p['n_prob']:>2d} problems  beta={p['beta']:+.4f} "
              f"(SE {p['se']:.4f})  {p['pct']:5.1f}% / quarter  N={p['n_obs']}")
    print(f"  interaction gamma = {va['gamma']:+.4f} (SE {va['gamma_se']:.4f}), "
          f"p = {va['gamma_p']:.3f}, 95% CI [{gci[0]:+.4f}, {gci[1]:+.4f}]")
    print("  gamma < 0 would mean the possibly-memorised problems compress FASTER.")
    print(f"  -> {verdict}")
    print("wrote", *paths, sep="\n  ")


# PRIMARY: include the full GPT series incl. o1 (earliest anchor, 2024-12).
build_decay_2panel("fig4_forecast_2panel", exclude_earliest=False, successes_only=True)
build_arith_mean("fig4_forecast_arith_mean_appendix", exclude_earliest=False, successes_only=True)
build("fig4_forecast", exclude_earliest=False, successes_only=True)
build("fig4_forecast_all_traces", exclude_earliest=False, successes_only=False)
build_combined("fig4_forecast_combined", successes_only=True, exclude_earliest=False)
# SENSITIVITY: drop the earliest point (o1) from the GPT fit.
build("fig4_forecast_no_o1", exclude_earliest=True, successes_only=True)
build_decay_2panel("fig4_forecast_2panel_no_o1", exclude_earliest=True, successes_only=True)
# APPENDIX: contamination check — same fit, only pre-benchmark-cutoff models.
build_contamination("fig4_forecast_precutoff_appendix", successes_only=True)
