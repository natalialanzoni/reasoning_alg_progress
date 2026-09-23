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
  fig4_forecast_excess_appendix       excess tokens above the floor, arithmetic mean
                             (this REPLACED the old fig4_forecast_arith_mean_appendix,
                             whose builder no longer exists -- do not expect that file)
  fig4_forecast_precutoff_appendix    CONTAMINATION CHECK: two panels, one per family,
                             refit on only the models whose published TRAINING-DATA
                             cutoff month predates Feb 2026 and which therefore cannot
                             have trained on the AIME/HMMT 2026 problems. Keyed on the
                             training cutoff, NOT the release date -- see TRAIN_CUTOFF.

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
import matplotlib.ticker as mticker

sys.path.insert(0, os.path.expanduser("~/.claude/skills/futuretech-charts/python"))
try:                                    # house style from the skill, if present
    from futuretech_helpers import use_style, unit_formatter, save_figure
    from futuretech_palette import PRIMARY, CATEGORICAL
    STYLE_SRC = "futuretech-charts skill"
except ModuleNotFoundError:             # replication machines: local stand-in
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from _ft_style_local import use_style, unit_formatter, save_figure, PRIMARY, CATEGORICAL
    STYLE_SRC = "LOCAL RECONSTRUCTION (_ft_style_local.py)"

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
REF = pf.canon_short   # o200k floor; the DEFAULT and the one OpenAI is measured in


def ref_of(mfiles):
    """The floor for this family, in the token units its models actually report.

    A family can span two tokenizers (Anthropic changed at Opus 4.7), so this uses
    the LATEST model's units -- the curve is about where the family is heading, and
    that is the unit its newest member is measured in. See README item 15.
    """
    return pf.mean_floor(mfiles[-1][0], pf.CANON_KEYS)

MILE_P = 0.10            # the ONLY milestone drawn: within 10% of the floor

# ---- benchmark contamination cutoff ---------------------------------------
# 40 of the 45 canonical problems are AIME 2026 I/II + HMMT February 2026, all three
# held in FEBRUARY 2026 (the other 5 are MATH-500, which long predates every model).
#
# MONTH GRANULARITY, DELIBERATELY. The competitions have exact dates (2026-02-05,
# -02-11, -02-14) but the training cutoffs we compare them against do not: Anthropic
# publishes months ("Jan 2026", "Aug 2025"), and a cutoff stated as a month could mean
# any day in it. Testing a month-precise cutoff against a day-precise competition date
# is false precision, and it would be actively wrong for any model whose cutoff fell in
# the same month. So the rule is stated at the granularity the inputs actually have:
#
#     a model is clean iff its training cutoff month is STRICTLY BEFORE 2026-02.
#
# No model sits in the ambiguous same-month case under this rule -- the nearest is
# gpt-5.6-sol at Feb 2026, which is excluded either way -- so nothing turns on it. But
# the rule holds up if a future model lands there, whereas a day comparison would not.
# TRAIN_CUTOFF / CUTOFF_MONTH live in paper_figures_71226 so that
# table_floor_robustness.py can use the same table. One copy only.
CUTOFF_MONTH = pf.CUTOFF_MONTH
TRAIN_CUTOFF = pf.TRAIN_CUTOFF
RELEASE_CUTOFF = pf.RELEASE_CUTOFF

ANTH = list(pf.OPUS_MODELS) + [
    ("Fable 5.1", datetime(2026, 9, 1),
     pf.RESULTS_DIR / "fable5.1_shallow_pass" / "claude-fable-5-1_medium_thinking_benchmark.json"),
]


def model_points(mfiles, successes_only):
    """Per model: (label, date, center, lo, hi) in tokens; point = between-problem
    geomean excess, error bar = 95% CI from the spread ACROSS problems (clustered)."""
    REF = ref_of(mfiles)      # this family's floor, not the global default
    out = []
    for label, date, path in mfiles:
        prob = {}
        for r in pf.load_rows(path):
            tid = str(r["task_id"])
            if tid not in pf.CANON_KEYS:
                continue
            tt = r.get("thinking_tokens", [1] * len(r["correct"]))
            for tok, c, th in zip(r["total_completion_tokens"], r["correct"], tt):
                if tok < 50 or (successes_only and not c):   # see _trial_ok
                    continue
                h = tok / pf.floor_for(label, tid)
                if h > 1:
                    prob.setdefault(tid, []).append(math.log(h - 1))
        pm = [float(np.mean(v)) for v in prob.values() if v]
        if not pm:
            continue
        mu = float(np.mean(pm))
        se = float(np.std(pm, ddof=1) / math.sqrt(len(pm))) if len(pm) > 1 else 0.0
        # Convert back to tokens with THIS MODEL's floor, not the family's. The ratio
        # above is already per-model; multiplying by a single family floor put Opus
        # 4.5 and 4.6 24% too high on the token panel, because they are measured
        # against 355 while the family reference is Fable 5.1's 441.
        own = pf.mean_floor(label, prob.keys())
        out.append((label, date, (1 + math.exp(mu)) * own,
                    (1 + math.exp(mu - 1.96 * se)) * own,
                    (1 + math.exp(mu + 1.96 * se)) * own, own))
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
    REF = ref_of(mfiles)      # this family's floor, not the global default
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
                if tok < 50:                                 # see figures_sept._trial_ok
                    continue
                # ... and a cap-hit trace never delivered an answer, so it is not a
                # success. Same rule as _fit_headroom_forecast: the band must be fitted
                # on the SAME rows as the estimate it wraps, or the two drift apart.
                if successes_only and not (c and tok < 40000):
                    continue
                # The PAPER'S DV, log(L - MHD_j), in absolute tokens -- the same one
                # pf._fit_headroom_forecast uses. This band and the curve it wraps are
                # what the figure DRAWS, while the rate annotation comes from that fit,
                # so the two must fit the same thing. They did not: this was still on
                # log(headroom - 1), whose -log(C_j) term stopped being absorbed by the
                # problem FE once the floor became per-model, putting the drawn
                # Anthropic curve at ~48.6%/quarter under a label reading 44.1%.
                cj = pf.floor_for(label, tid)
                if tok > cj:
                    rows.append((tid, month, label, math.log(tok - cj)))
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
    center = np.exp(Xd @ bhat) + REF          # excess tokens + the floor
    rng = np.random.default_rng(seed)
    wm = rng.choice([-1.0, 1.0], size=(B, G))     # one Rademacher sign per model per rep
    Ystar = yhat[None, :] + wm[:, cl] * e[None, :]
    Bstar = Ystar @ Pinv.T                         # (B, k)
    Cmu = Bstar @ Xd.T                             # (B, n_dates)
    lo = np.exp(np.percentile(Cmu, 2.5, axis=0)) + REF
    hi = np.exp(np.percentile(Cmu, 97.5, axis=0)) + REF
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
    REF = ref_of(mfiles)      # this family's floor, not the global default
    norm = REF if ratio else 1.0     # used for the fitted CURVE (one per family)
    fc_ls = ":" if ratio else "--"
    fit = pf._fit_headroom_forecast(mfiles, exclude_baseline=excl, successes_only=successes_only)
    pts = [p for p in model_points(mfiles, successes_only)
           if not (excl and p[0] == fit["baseline_label"])]
    odates = [p[1] for p in pts]
    # Each DOT divides by its own model's floor, so panel B reads "this model's
    # geometric mean as a multiple of the derivation IT is measured against".
    octr = [p[2] / (p[5] if ratio else 1.0) for p in pts]

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
        for _i, ((_nm, _dt, _tok, _lo, _hi, _own), _x, _y) in enumerate(zip(pts, odates, octr)):
            if _i not in _ends:
                continue
            _m = _tok / _own                      # that model's own multiple
            ax.annotate(f"{_m:.0f}x" if _m >= 10 else f"{_m:.1f}x", (_x, _y),
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


def _floor(ax, xend=None, ref=None, label=True):
    """Floor line + label. The floor is ~303 tok against a 10-20k y-axis, so the
    label is anchored to the LEFT edge (where the decay curve is still high and the
    space is empty) in x-axes-fraction / y-data coords, with an opaque box — at the
    right edge it collided with the curve as it lands on the floor."""
    REF = ref if ref is not None else globals()["REF"]
    ax.axhspan(0, REF, color=FLOOR_C, alpha=0.10, zorder=0)
    ax.axhline(REF, color=FLOOR_C, lw=2.4, zorder=3)
    if not label:
        return
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
                if tok < 50 or (successes_only and not c):   # see _trial_ok
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

    # Plain numbers on a log axis, and enough of them to read between 1 and 10.
    # Matplotlib's default gives 10^0 / 10^1 / 10^2 and nothing in between, which on
    # a panel whose whole story happens between 1x and 40x is close to unreadable.
    ticks = [1, 2, 3, 4, 5, 7, 10, 15, 20, 30, 50, 70, 100]
    lo_, hi_ = ar.get_ylim()
    ticks = [t for t in ticks if lo_ <= t <= hi_]
    ar.yaxis.set_major_locator(mticker.FixedLocator(ticks))
    ar.yaxis.set_major_formatter(mticker.FixedFormatter([f"{t:g}x" for t in ticks]))
    ar.yaxis.set_minor_locator(mticker.NullLocator())   # the majors are already dense

    # NO twin token axis here any more. It converted multiples to tokens with a single
    # floor, which was fine while every model shared one. Now that each family is
    # measured against its own tokenizer's floor (316 for OpenAI, 441 for Anthropic
    # 4.7+), one token scale cannot serve both curves -- it mislabelled every
    # Anthropic point by ~40%. Panel A already shows tokens, correctly, for both.
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


def build_excess_appendix(fname, successes_only=True):
    """APPENDIX — the same fit as Figure 4, read in absolute tokens.

    Panel B of Figure 4 with the units swapped: dots are the plain ARITHMETIC MEAN
    of the excess over the floor (L - MHD_j) per model, and the y axis is tokens on
    a log scale, so a constant decay rate is a straight line.

    NO SECOND REGRESSION. The curve is the same per-family fit the main figure and
    the decay table use, multiplied by Duan's smearing factor mean(exp(residual)) --
    1.12 for OpenAI, 1.14 for Anthropic. That factor is needed because the DV is log
    excess, so exp(fitted) is a GEOMETRIC mean; the smearing constant converts it to
    an arithmetic one to match the dots. It is a rescale of the fitted line, not a
    re-estimate: beta, the quarterly rate and the CI are untouched.

    The line still will not pass exactly through the dots, and does not in Figure 4
    either: the curve is the fitted value for the AVERAGE problem, while each dot
    averages over the problems that model actually solved. o1 solved 36 of 40, and
    the easier ones, so its dot sits below the curve.
    """
    fams = [("OpenAI (GPT)", pf.MAIN_K8, OAI_C), ("Anthropic (Opus + Fable)", ANTH, ANT_C)]
    print(f"\n########## {fname}  (excess tokens, same fit) ##########")
    fig, ax = plt.subplots(figsize=(11, 6.8))
    lo_y = 1e9
    handles = []
    for yi, (name, mfiles, col) in enumerate(fams):
        fit = pf._fit_headroom_forecast(mfiles, exclude_baseline=False,
                                        successes_only=successes_only)
        res = fit["res"]
        smear = float(np.mean(np.exp(res.resid)))     # Duan (1983)
        # arithmetic mean excess per model, over the problems that model solved
        pts = []
        for label, date, path in mfiles:
            ex = []
            for r in pf.load_rows(path):
                tid = str(r["task_id"])
                if tid not in pf.CANON_KEYS:
                    continue
                mn = pf.floor_for(label, tid)
                for tok, c in zip(r["total_completion_tokens"], r["correct"]):
                    # a cap-hit trace never delivered an answer, so it is not a
                    # success (same rule as figures_sept._trial_correct)
                    if tok < 50 or (successes_only and not (c and tok < 40000)):
                        continue
                    if tok > mn:
                        ex.append(tok - mn)
            if ex:
                pts.append((date, float(np.mean(ex))))
        pts.sort()
        dx = mdates.date2num([d for d, _ in pts]); ys = [v for _, v in pts]
        # fitted curve, smeared to an arithmetic mean, in excess tokens
        t0, t1 = pts[0][0], fit["mile"][MILE_P]
        n_mo = int((t1 - t0).days / 30.44) + 1
        cd = [t0 + timedelta(days=30.44 * k) for k in range(n_mo + 1)]
        cy = [(fit["hhat"](d) - 1.0) * REF * smear for d in cd]
        t_last = mfiles[-1][1]
        sd = [(d, v) for d, v in zip(cd, cy) if d <= t_last]
        dd = [(d, v) for d, v in zip(cd, cy) if d >= t_last]
        ax.plot([d for d, _ in sd], [v for _, v in sd], "-", color=col, lw=2.6, zorder=4)
        ax.plot([d for d, _ in dd], [v for _, v in dd], ":", color=col, lw=2.6, zorder=4)
        ax.plot(dx, ys, "o", color=col, ms=10, zorder=6)
        # Label every dot with its mean excess in TOKENS -- the arithmetic-mean
        # counterpart of the multiple-of-floor labels on panel B of Figure 4.
        # Stagger by family: Anthropic sits above OpenAI through the overlap, so its
        # labels go up-right and OpenAI's down-left, pushing them apart.
        # centred, one family below its dots and the other above. Offsetting
        # sideways instead let a label drift onto a neighbouring dot.
        ddy = -17 if yi == 0 else 15
        va = "top" if yi == 0 else "bottom"
        for xi, vi in zip(dx, ys):
            ax.annotate(f"{vi:,.0f}", (xi, vi), textcoords="offset points",
                        xytext=(0, ddy), ha="center", va=va, fontsize=8.6,
                        fontweight="bold", color=col, zorder=8,
                        # halo: the fitted line descends through the label band
                        bbox=dict(boxstyle="round,pad=0.12", fc="white",
                                  ec="none", alpha=0.75))
        lo_y = min(lo_y, min(ys), min(cy))
        handles.append(mlines.Line2D([], [], color=col, lw=2.6, marker="o", ms=9,
                                     # en dash: Helvetica Neue has no U+2192
                                     label=f"{name} — {ys[0]:,.0f} to {ys[-1]:,.0f} tok "
                                           f"({ys[0]/ys[-1]:.1f}×)"))
        print(f"  {name:<26s} smearing {smear:.2f}   "
              f"{ys[0]:.0f} -> {ys[-1]:.0f} excess tok = {ys[0]/ys[-1]:.1f}x")

    _sep(ax, max(f[1][-1][1] for f in fams), max(ys) * 4, labels=True)
    ax.set_yscale("log"); ax.set_ylim(lo_y * 0.45, 40000)
    ax.set_ylabel("Mean excess over the floor  (output tokens)")
    ax.set_xlabel("Date")
    ax.yaxis.set_major_formatter(unit_formatter(1e3, "k"))
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    handles += [mlines.Line2D([], [], color="#888888", lw=2.6, ls=":", label="Forecast"),
                mlines.Line2D([], [], color=SEP_C, lw=1.6, ls="--", label="Forecast start")]
    ax.legend(handles=handles, loc="upper right", fontsize=11.5, frameon=True,
              framealpha=0.95)
    plt.tight_layout(pad=0.5)
    paths = save_figure(fig, fname, outdir=OUT)
    print("wrote", *paths, sep="\n  ")


def _pre_cutoff(mfiles):
    """Models whose TRAINING DATA ends before the first benchmark problem went public.

    A model missing from TRAIN_CUTOFF is dropped rather than assumed clean -- if a new
    model is added to the series without its published cutoff, this check must get
    smaller, never silently larger.
    """
    return [m for m in mfiles
            if m[0] in TRAIN_CUTOFF and TRAIN_CUTOFF[m[0]] < CUTOFF_MONTH]


def _pre_cutoff_release(mfiles):
    """Stricter variant: models RELEASED before the problems existed. Airtight (it
    needs no vendor claim at all), but small. Reported alongside as a lower bound."""
    return [m for m in mfiles if m[1] <= RELEASE_CUTOFF]


# NO PUBLICATION-DATE MARKER ON THIS FIGURE. It used to draw a red line at
# Feb 2026, which made sense when models were selected by RELEASE date -- everything
# plotted then sat to its left. Under the training-cutoff rule four of the models shown
# (gpt-5.4, gpt-5.5, Opus 4.7, Opus 4.8) were released to the RIGHT of that date and are
# still clean, so the line contradicted the panel it was drawn on. The selection rule is
# stated in the title and caption instead.


def build_contamination(fname, successes_only=True):
    """APPENDIX — contamination check, three independent angles on the same worry:
    that newer models only look efficient because they memorised the benchmark.

    Panel 1  restrict the MODELS: refit the identical excess-trend spec on only the
             models whose training cutoff month is strictly before Feb 2026 and which
             cannot have trained on the AIME 2026 / HMMT Feb 2026 problems (40 of the
             45 canonical items).
             Single-lab (GPT) so no cross-lab pooling. Ambiguous on its own, because
             it also shortens the window.
    Panel 2  restrict the PROBLEMS: fit on MATH-500 only — old problems that sit in
             EVERY model's training data, so no model can gain a memorisation edge
             over another. The decline here is a contamination-free lower bound.
             GPT and Anthropic are fitted separately, never pooled.
    The problem-vintage difference-in-differences (gamma) is still computed and
    printed for the caption, but is no longer a panel -- panel 2 shows it more directly.
    """
    panels = [("OpenAI (GPT)", _pre_cutoff(pf.MAIN_K8), list(pf.MAIN_K8)),
              ("Anthropic (Opus + Fable)", _pre_cutoff(ANTH), list(ANTH))]

    print(f"\n########## {fname}  (CONTAMINATION CHECK) ##########")
    print("  benchmark problems published Feb 2026 (AIME I/II, HMMT Feb)")
    print(f"  clean iff training cutoff month < {CUTOFF_MONTH:%Y-%m}")
    print("  selection = published TRAINING-DATA cutoff < benchmark publication")
    summary, ymaxes, xlims = [], [], []
    fig, axes = plt.subplots(1, 2, figsize=(16.4, 6.8), sharey=True)
    axes = list(axes)
    for ax, (title, pre, full_set) in zip(axes, panels):
        kept = {l for l, _, _ in pre}
        print(f"\n  --- {title} ---")
        for l, d, _ in full_set:
            tc = TRAIN_CUTOFF.get(l)
            mark = "keep" if l in kept else "DROP"
            print(f"      {mark}  {l:<16s} released {d:%Y-%m}  train-cutoff "
                  f"{tc:%Y-%m}" if tc else f"      DROP  {l:<16s} (no published cutoff)")
        # the stricter release-date rule, for the lower-bound row in the summary
        rel = _pre_cutoff_release(full_set)
        print(f"      [release-date rule would keep {len(rel)}: "
              + ", ".join(l for l, _, _ in rel) + "]")

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

        ymax = max(ymax, max(gy) * 1.06)
        _floor(ax)
        xlims.append((pre[0][1] - timedelta(days=40), span_end + timedelta(days=20)))
        ax.set_title(title, fontsize=15)
        ax.set_xlabel("Date")
        ax.yaxis.set_major_formatter(unit_formatter(1e3, "k"))
        ax.xaxis.set_major_locator(mdates.YearLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
        ymaxes.append(ymax)
        summary.append((title, fit, fit_full, len(pre), len(full_set)))

    # The axes share y, so the LAST set_ylim would otherwise win and silently clip the
    # other panel's tallest model (o1, off the top of the OpenAI panel). Set one common
    # limit after both panels are drawn, then place the cutoff label against it.
    ytop = max(ymaxes)
    # ONE x range for both panels. The families start 11 months apart, so per-panel
    # limits silently plot them at different date scales and the two decay curves stop
    # being visually comparable -- which is the point of putting them side by side.
    xlo = min(a for a, _ in xlims); xhi = max(b for _, b in xlims)
    for ax in axes:
        ax.set_ylim(0, ytop)
        ax.set_xlim(xlo, xhi)

    axes[0].set_ylabel(f"Output tokens: reasoning + answer "
                       f"({'correct' if successes_only else 'all'} traces)")
    # no figure title -- captions live in the paper (same convention as figure2_ft.py).
    # The panel headings stay: they identify which family each axes is, which a caption
    # cannot do as directly.
    handles = [
        mlines.Line2D([], [], color=TOK, lw=2.6, marker="o", ms=9,
                      label="Pre-cutoff fit + models (cannot be contaminated)"),
        mlines.Line2D([], [], color=TOK, lw=2.6, ls="--", label="Pre-cutoff forecast"),
        mpatches.Patch(color=TOK, alpha=0.2, label="95% CI (wild bootstrap)"),
        mlines.Line2D([], [], color=FULL_C, lw=2.2, ls="-.", label="Full-sample fitted trend"),
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

    # The stricter release-date rule, refitted, as a lower bound for the appendix text.
    print("\n  ----- stricter variant: RELEASE date before the benchmark -----")
    for title, full_set in (("OpenAI (GPT)", list(pf.MAIN_K8)),
                            ("Anthropic (Opus + Fable)", list(ANTH))):
        rel = _pre_cutoff_release(full_set)
        if len(rel) < 3:
            print(f"  {title:<44s} {len(rel):>3d}   too few models to fit")
            continue
        f = pf._fit_headroom_forecast(rel, exclude_baseline=False,
                                      successes_only=successes_only)
        print(f"  {title + ': release-rule':<44s} {len(rel):>3d} {f['beta']:>9.4f} "
              f"{f.get('beta_se', float('nan')):>7.4f} {f['quarterly_pct']:>6.1f}% "
              f"{f['mile'][MILE_P]:%Y-%m}")
    print("\n  NOTE: keying on the TRAINING cutoff rather than the release date is what")
    print("        makes this informative -- it keeps the window long enough that a")
    print("        flatter beta would mean contamination rather than just less data.")
    print("wrote", *paths, sep="\n  ")


# PRIMARY: include the full GPT series incl. o1 (earliest anchor, 2024-12).
build_decay_2panel("fig4_forecast_2panel", exclude_earliest=False, successes_only=True)
build_excess_appendix("fig4_forecast_excess_appendix", successes_only=True)
# fig4_forecast (single-panel, absolute tokens only) is RETIRED -- fig4_forecast_2panel
# is the primary forecast figure. Archived to archive/stale_figures/. build() is kept
# because the all-traces and no-o1 variants below still use it.
build("fig4_forecast_all_traces", exclude_earliest=False, successes_only=False)
# APPENDIX: the primary two-panel figure on ALL attempts, right or wrong.
build_decay_2panel("fig4_forecast_2panel_alltraces", exclude_earliest=False,
                   successes_only=False)
build_combined("fig4_forecast_combined", successes_only=True, exclude_earliest=False)
# SENSITIVITY: drop the earliest point (o1) from the GPT fit.
build("fig4_forecast_no_o1", exclude_earliest=True, successes_only=True)
build_decay_2panel("fig4_forecast_2panel_no_o1", exclude_earliest=True, successes_only=True)
# APPENDIX: contamination check — same fit, only pre-benchmark-cutoff models.
build_contamination("fig4_forecast_precutoff_appendix", successes_only=True)
