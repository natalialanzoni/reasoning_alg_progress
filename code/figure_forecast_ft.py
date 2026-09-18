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
  fig4_forecast_2panel       PRIMARY: ONE ROW, two panels, BOTH families overlaid --
                             absolute tokens | multiple of the floor (log). Endpoint
                             dots carry their geometric-mean multiple of the floor.
  fig4_forecast_all_traces   ALL traces
  fig4_forecast_combined     both families on one axis
  fig4_forecast_*_no_o1      SENSITIVITY: drop the earliest point (o1)
  fig4_forecast_arith_mean_appendix   arithmetic-mean token space
  fig4_forecast_precutoff_appendix    CONTAMINATION CHECK: same fit on only the
                             models released on/before 2026-02-05, which cannot
                             have trained on the AIME/HMMT 2026 problems.

SAMPLE: the 40 competition problems. MATH-500 is dropped and the floor is recomputed
over the same 40 (316 tok, vs 303 over all 45) -- matching figure1_grid_ft.py.
fig4_forecast (single panel) is RETIRED to archive/stale_figures/.

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

# ---- MATCH FIGURE 1: drop MATH-500, keep the 40 competition problems --------
# Those 5 easy problems have the newest models sitting at or below the floor, where
# log(L - C_j) is undefined and 20-67% of their traces get dropped by the L > C_j
# filter; on the 40 competition problems that falls to 0.3%. We restrict THIS
# module's private copy of pf (importlib gives each script its own module object,
# so nothing else is affected) and recompute the floor over the same 40, so every
# helper below -- including pf._fit_headroom_forecast, which reads pf.CANON_KEYS
# internally -- is driven off one sample definition rather than two.
for _t in [t for t in pf.CANON if str(t).startswith("math_500")]:
    del pf.CANON[_t]
pf.CANON_KEYS = set(pf.CANON)
pf.canon_avg = float(np.mean([v["mean"] for v in pf.CANON.values()]))
pf.canon_short = float(np.mean([v["min"] for v in pf.CANON.values()]))
print(f"forecast: {len(pf.CANON_KEYS)} competition problems (MATH-500 excluded), "
      f"floor = {pf.canon_short:.0f} tok")

TOK = PRIMARY            # navy — data + fit (single-family panels)
FLOOR_C = "#E07A3F"      # amber — irreducible reasoning floor
SEP_C = "#8A8A8A"        # grey — observed/forecast separator
OAI_C = CATEGORICAL[0]   # blue  — OpenAI (combined plot)
ANT_C = CATEGORICAL[1]   # MIT red — Anthropic (combined plot)
FULL_C = "#6E6E6E"       # grey — full-sample trend overlaid on the appendix check
CUT_C = "#B2182B"        # red  — benchmark publication cutoff
REF = pf.canon_short   # minimal human derivation, over the 40 competition problems

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
                max_end=None, label_dots=False, dot_dy=13, dot_dx=0):
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
    if label_dots:
        # Each dot is the geometric mean of the excess over the floor, so the
        # natural label is that value as a MULTIPLE of the minimal human
        # derivation (pts carries it in tokens; divide by REF).
        # Only the ENDPOINTS: labelling every model made the overlap region
        # unreadable, and first-vs-last is the comparison the panel is making.
        _ends = {0, len(pts) - 1}
        for _i, ((_nm, _dt, _tok, _lo, _hi), _x, _y) in enumerate(zip(pts, odates, octr)):
            if _i not in _ends:
                continue
            ax.annotate(f"{_tok / REF:.0f}x" if _tok / REF >= 10 else
                        f"{_tok / REF:.1f}x", (_x, _y),
                        textcoords="offset points", xytext=(dot_dx, dot_dy),
                        ha="center" if not dot_dx else ("right" if dot_dx < 0 else "left"),
                        va="bottom" if dot_dy > 0 else "top",
                        fontsize=10.5, fontweight="bold", color=color,
                        zorder=9, bbox=dict(boxstyle="round,pad=0.14", fc="white",
                                           ec="none", alpha=0.85))

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
    # Right-anchored, well above the line. The observed dots (and now their
    # multiple-of-floor labels) occupy the bottom-LEFT, while by the right-hand end
    # the curve has flattened onto the floor and everything above it is empty.
    ax.annotate(f"minimal human derivation ≈ {REF:,.0f} tok",
                xy=(0.985, REF), xycoords=("axes fraction", "data"),
                textcoords="offset points", xytext=(0, 34), ha="right", va="bottom",
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


def _floor_ratio(ax, xend=None):
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
        fit, t_last, xend, ymax = draw_family(ax, mfiles, excl, successes_only, TOK,
                                              label_dots=True)
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
    fig.legend(handles=handles, loc="upper center", ncol=5, fontsize=13,
               frameon=True, framealpha=0.95, bbox_to_anchor=(0.5, -0.01))
    plt.tight_layout(pad=0.5)
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
    fig.legend(handles=handles, loc="upper center", ncol=5, fontsize=13,
               frameon=True, framealpha=0.95, bbox_to_anchor=(0.5, -0.01))
    plt.tight_layout(pad=0.5)
    paths = save_figure(fig, fname, outdir=OUT)
    print("wrote", *paths, sep="\n  ")


def build_decay_2panel(fname, exclude_earliest=True, successes_only=True):
    """ONE ROW, two panels, BOTH families overlaid on each so the labs are directly
    comparable rather than sitting in separate columns on separate axes:
      left  — absolute output tokens, solid over observed then DASHED forecast
      right — the same fit as a MULTIPLE OF THE FLOOR (L/MHD) on a log axis, floor
              at 1x, DOTTED forecast. Equal decay rates read as parallel lines here.
    Both families end 2026-09, so a single observed/forecast separator serves both.
    """
    fams = [("OpenAI (GPT)", pf.MAIN_K8, exclude_earliest, OAI_C),
            ("Anthropic (Opus + Fable)", ANTH, False, ANT_C)]
    print(f"\n########## {fname}  (one row, both families) ##########")
    fig, axes = plt.subplots(1, 2, figsize=(16, 6.8), gridspec_kw={"wspace": 0.2})
    al, ar = axes
    ymax = ymax2 = 0; xlo = xhi = None; tlast = None
    handles, miles = [], []
    for yi, (name, mfiles, excl, col) in enumerate(fams):
        fit, t_last, xend, ym = draw_family(
            al, mfiles, excl, successes_only, col, milestones=False,
            q_xy=(0.97, 0.93 - 0.08 * yi), q_label=name.split(" (")[0])
        print_spec(name, fit)
        # Label the dots on the RIGHT panel only. On the token axis both families
        # collapse into the same bottom-right corner and the labels overlap; the
        # log multiple-of-floor axis spreads the same points over a decade, and
        # there the label is simply a readout of that panel's own y value.
        _, _, xend2, ym2 = draw_family(ar, mfiles, excl, successes_only, col,
                                       milestones=False, ratio=True, show_q=False,
                                       label_dots=True,
                                       # Anthropic sits ABOVE OpenAI through the
                                       # overlap, so its labels go up-right and
                                       # OpenAI's down-left, pushing them apart
                                       # rather than into each other.
                                       dot_dy=-13 if yi == 0 else 13,
                                       dot_dx=-7 if yi == 0 else 7)
        ymax = max(ymax, ym); ymax2 = max(ymax2, ym2)
        start = (mfiles[1] if excl else mfiles[0])[1]
        s, e = start - timedelta(days=40), xend + timedelta(days=20)
        xlo = s if xlo is None else min(xlo, s); xhi = e if xhi is None else max(xhi, e)
        tlast = t_last if tlast is None else max(tlast, t_last)
        miles.append(f"{name.split(' (')[0]} {fit['mile'][MILE_P]:%Y-%m}")
        handles.append(mlines.Line2D([], [], color=col, lw=2.6, marker="o", ms=9, label=name))

    _floor(al); _sep(al, tlast, ymax * 0.98)
    al.set_ylim(0, ymax); al.set_xlim(xlo, xhi)
    al.set_ylabel(f"Output tokens: reasoning + answer\n"
                  f"({'correct' if successes_only else 'all'} traces)")
    al.yaxis.set_major_formatter(unit_formatter(1e3, "k"))
    # one milestone box covering both families, rather than two overlapping vlines
    al.annotate(f"within {int(MILE_P * 100)}% of floor — " + "  ·  ".join(miles),
                xy=(0.97, 0.60), xycoords="axes fraction", ha="right", va="center",
                fontsize=11.5, color="#333333", zorder=9,
                bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="#BBBBBB",
                          lw=0.8, alpha=0.95))

    ar.set_yscale("log"); _floor_ratio(ar)
    ar.set_ylim(0.9, ymax2 * 1.5); ar.set_xlim(xlo, xhi)
    _sep(ar, tlast, ymax2 * 1.4, labels=False)
    ar.set_ylabel("Multiple of the floor  (L / MHD)")

    for ax in axes:
        ax.set_xlabel("Date")
        ax.xaxis.set_major_locator(mdates.YearLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    handles += [
        mlines.Line2D([], [], color="#888888", lw=2.6, ls="--", label="Forecast (tokens)"),
        mlines.Line2D([], [], color="#888888", lw=2.6, ls=":", label="Forecast (multiple of floor)"),
        mpatches.Patch(color="#888888", alpha=0.2, label="95% CI (wild bootstrap)"),
        mlines.Line2D([], [], color=FLOOR_C, lw=2.4, label="Minimal human derivation"),
    ]
    fig.legend(handles=handles, loc="upper center", ncol=3, fontsize=12.5,
               frameon=True, framealpha=0.95, bbox_to_anchor=(0.5, -0.01))
    plt.tight_layout(pad=0.5)
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
    fig.legend(handles=handles, loc="upper center", ncol=4, fontsize=13,
               frameon=True, framealpha=0.95, bbox_to_anchor=(0.5, -0.01))
    plt.tight_layout(pad=0.5)
    paths = save_figure(fig, fname, outdir=OUT)
    print("wrote", *paths, sep="\n  ")


def _pre_cutoff(mfiles):
    """Models released on or before the first benchmark problem went public."""
    return [m for m in mfiles if m[1] <= CUTOFF]


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
    """APPENDIX — contamination check, three independent angles on the same worry:
    that newer models only look efficient because they memorised the benchmark.

    Panel 1  restrict the MODELS: refit the identical excess-trend spec on only the
             models released on/before 2026-02-05, which cannot have trained on the
             AIME 2026 / HMMT Feb 2026 problems (40 of the 45 canonical items).
             Single-lab (GPT) so no cross-lab pooling. Ambiguous on its own, because
             it also shortens the window.
    Panel 2  restrict the PROBLEMS: fit on MATH-500 only — old problems that sit in
             EVERY model's training data, so no model can gain a memorisation edge
             over another. The decline here is a contamination-free lower bound.
             GPT and Anthropic are fitted separately, never pooled.
    The problem-vintage difference-in-differences (gamma) is still computed and
    printed for the caption, but is no longer a panel -- panel 2 shows it more directly.
    """
    gpt_pre = _pre_cutoff(pf.MAIN_K8)
    pooled_full = sorted(list(pf.MAIN_K8) + list(ANTH), key=lambda t: t[1])
    panels = [("OpenAI (GPT) — pre-cutoff models only", gpt_pre, list(pf.MAIN_K8))]

    print(f"\n########## {fname}  (CONTAMINATION CHECK) ##########")
    print(f"  cutoff = {CUTOFF:%Y-%m-%d}  (AIME 2026 I administered; AIME II 02-11, HMMT 02-14)")
    summary = []
    fig, _ax0 = plt.subplots(1, 1, figsize=(9.2, 6.6))
    axes = [_ax0]
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
            label_dots=True,
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

    axes[0].set_ylabel(f"Output tokens: reasoning + answer "
                       f"({'correct' if successes_only else 'all'} traces)")
    axes[0].set_title("Contamination check — models released before the benchmark\n"
                      "OpenAI (GPT), pre-cutoff models only", fontsize=15)
    handles = [
        mlines.Line2D([], [], color=TOK, lw=2.6, marker="o", ms=9,
                      label="Pre-cutoff fit + models (cannot be contaminated)"),
        mlines.Line2D([], [], color=TOK, lw=2.6, ls="--", label="Pre-cutoff forecast"),
        mpatches.Patch(color=TOK, alpha=0.2, label="95% CI (wild bootstrap)"),
        mlines.Line2D([], [], color=FULL_C, lw=2.2, ls="-.", label="Full-sample fitted trend"),
        mpatches.Patch(color=CUT_C, alpha=0.16, label="Benchmark published (Feb 2026)"),
        mlines.Line2D([], [], color=FLOOR_C, lw=2.4, label="Minimal human derivation"),
    ]
    fig.legend(handles=handles, loc="upper center", ncol=2, fontsize=11,
               frameon=True, framealpha=0.95, bbox_to_anchor=(0.5, -0.01))
    plt.tight_layout(pad=0.5)
    paths = save_figure(fig, fname, outdir=OUT)

    print("\n  ===== CONTAMINATION CHECK SUMMARY =====")
    print(f"  {'sample':<44s} {'n':>3s} {'beta':>9s} {'SE':>7s} {'%/qtr':>7s} {'within-10%':>11s}")
    for title, fit, fit_full, npre, nfull in summary:
        pairs = [(f"{title.split(' — ')[0]}: PRE-CUTOFF", fit, npre)]
        if fit_full is not None:
            pairs.append((f"{title.split(' — ')[0]}: full sample", fit_full, nfull))
        for tag, f, n in pairs:
            # MATH-500 subset fits carry no forecast milestone; key names differ too
            beta = f["beta"]; se = f.get("beta_se", f.get("se"))
            pct = f.get("quarterly_pct", f.get("pct"))
            mile = f"{f['mile'][MILE_P]:%Y-%m}" if "mile" in f else "-"
            print(f"  {tag:<44s} {n:>3d} {beta:>9.4f} {se:>7.4f} {pct:>6.1f}% {mile:>11s}")
    print("  NOTE: the pre-cutoff refit also SHORTENS the window, so a flatter beta")
    print("        there is ambiguous (contamination vs. genuine recent acceleration).")
    print("wrote", *paths, sep="\n  ")


# PRIMARY: include the full GPT series incl. o1 (earliest anchor, 2024-12).
build_decay_2panel("fig4_forecast_2panel", exclude_earliest=False, successes_only=True)
build_arith_mean("fig4_forecast_arith_mean_appendix", exclude_earliest=False, successes_only=True)
# fig4_forecast (single-panel, absolute tokens only) is RETIRED -- fig4_forecast_2panel
# is the primary forecast figure. Archived to archive/stale_figures/. build() is kept
# because the all-traces and no-o1 variants below still use it.
build("fig4_forecast_all_traces", exclude_earliest=False, successes_only=False)
build_combined("fig4_forecast_combined", successes_only=True, exclude_earliest=False)
# SENSITIVITY: drop the earliest point (o1) from the GPT fit.
build("fig4_forecast_no_o1", exclude_earliest=True, successes_only=True)
build_decay_2panel("fig4_forecast_2panel_no_o1", exclude_earliest=True, successes_only=True)
# APPENDIX: contamination check — same fit, only pre-benchmark-cutoff models.
build_contamination("fig4_forecast_precutoff_appendix", successes_only=True)
