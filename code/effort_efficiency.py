"""
Low / medium / high reasoning-effort efficiency over model generations, on the
hard-but-doable-10 set. Per-problem mean trace length over release date, one
line per effort, plus the same excess-tokens FE regression as Figure 3
(log(headroom-1) ~ month + problem fixed effects, clustered, successes only)
computed PER effort.

Data coverage differs by effort (whatever runs exist on this 10-problem set):
  low  : gpt-5, gpt-5.4, gpt-5.6-sol            (k=8)
  medium: gpt-5, gpt-5.2, gpt-5.4, gpt-5.5      (k=32, from hard_but_doable_10q_k32)
  high : gpt-5, gpt-5.4, (gpt-5.6-sol pending)  (k=8)
Reuses CANON / load_rows from paper_figures_71226.py.
"""
import importlib.util
import math
import os
from datetime import datetime

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.lines as mlines
import seaborn as sns
import statsmodels.formula.api as smf

sns.set_theme(style="whitegrid")

_spec = importlib.util.spec_from_file_location("pf", os.path.join(os.path.dirname(__file__), "paper_figures_71226.py"))
pf = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(pf)
CANON, CANON_KEYS, load_rows = pf.CANON, pf.CANON_KEYS, pf.load_rows
ORIGIN = pf.ORIGIN
ROOT = pf.ROOT
DATA = ROOT.parent / "data"
OUT = ROOT.parent / "figures"

# release dates (gpt-5.6-sol has no official snapshot; assumed, edit me)
DATES = {"o3": datetime(2025, 4, 16), "gpt-5": datetime(2025, 8, 7),
         "gpt-5.2": datetime(2025, 12, 11), "gpt-5.4": datetime(2026, 3, 5),
         "gpt-5.5": datetime(2026, 6, 1), "gpt-5.6-sol": datetime(2026, 8, 1)}

# Candidate models per effort (any without a run json are skipped). o3 is
# plotted but EXCLUDED from the trend fit (pre-GPT-5 peak, as in Fig 3).
ALL = ["o3", "gpt-5", "gpt-5.2", "gpt-5.4", "gpt-5.5", "gpt-5.6-sol"]
FIT_EXCLUDE = {"o3"}
EFFORTS = {
    "low":    {"dir": "low_reasoning_effort",    "color": "#1565C0", "models": ALL},
    "medium": {"dir": "hard_but_doable_10q_k32", "color": "#2E7D32", "models": ALL},
    "high":   {"dir": "high_reasoning_effort",   "color": "#C62828", "models": ALL},
}


def jpath(eff, m):
    return DATA / EFFORTS[eff]["dir"] / f"{m}_{eff}_thinking_benchmark_hard_but_doable_10.json"


def gather(eff):
    dates, per_model, reg = [], [], []
    for m in EFFORTS[eff]["models"]:
        p = jpath(eff, m)
        if not p.exists():
            print(f"  SKIP {eff:6} {m}: not found")
            continue
        month = (DATES[m] - ORIGIN).days / 30.44
        by_id = {}
        for r in load_rows(p):
            tid = str(r["task_id"])
            tt = r.get("thinking_tokens", [1] * len(r["correct"]))
            toks = [t for t, th in zip(r["total_completion_tokens"], tt) if th > 0]
            if toks:
                by_id[tid] = float(np.mean(toks))
            if tid not in CANON_KEYS:
                continue
            for tok, c, th in zip(r["total_completion_tokens"], r["correct"], tt):
                if th == 0 or tok <= 0 or not c:
                    continue
                h = tok / CANON[tid]["mean"]
                if h > 1:
                    reg.append({"problem": tid, "month": month, "y": math.log(h - 1), "model": m})
        dates.append(DATES[m]); per_model.append(by_id)
    common = sorted(set.intersection(*[set(d) for d in per_model])) if per_model else []
    traj = {tid: [d[tid] for d in per_model] for tid in common}
    return dates, traj, pd.DataFrame(reg)


def fit(df, label):
    df = df[~df["model"].isin(FIT_EXCLUDE)]        # drop o3 from the trend (as in Fig 3)
    npts = df["month"].nunique()
    if npts < 2:
        print(f"  {label:6}: <2 time points after o3 exclusion — no slope"); return None
    res = smf.ols("y ~ month + C(problem)", data=df).fit(
        cov_type="cluster", cov_kwds={"groups": df["problem"]})
    b, se = res.params["month"], res.bse["month"]
    qtr, hl = (1 - math.exp(3 * b)) * 100, math.log(2) / abs(b)
    print(f"  {label:6} beta={b:+.4f}/mo (se {se:.4f})  N={int(res.nobs)}  "
          f"pts={npts}  {qtr:.1f}%/qtr  half-life={hl:.1f}mo")
    return dict(b=b, qtr=qtr, hl=hl, pts=npts)


def main():
    fig, ax = plt.subplots(figsize=(11.5, 7))
    fits, all_keys = {}, set()
    for eff, cfg in EFFORTS.items():
        dates, traj, reg = gather(eff)
        if not traj:
            continue
        all_keys |= set(traj)
        c = cfg["color"]
        for tid, ys in traj.items():
            ax.plot(dates, ys, "-", color=c, lw=1.0, alpha=0.22, zorder=2)
        macro = [float(np.mean([traj[t][i] for t in traj])) for i in range(len(dates))]
        ax.plot(dates, macro, "o-", color=c, lw=3, ms=10, zorder=5, label=f"{eff} effort (mean)")
        for d, mv in zip(dates, macro):
            ax.annotate(f"{mv:,.0f}", (d, mv), textcoords="offset points", xytext=(0, 11),
                        ha="center", fontsize=8.5, fontweight="bold", color=c)
        f = fit(reg, eff)
        if f:
            fits[eff] = f

    pk = [t for t in all_keys if t in CANON_KEYS]
    canon = float(np.mean([CANON[t]["mean"] for t in pk]))
    ax.axhline(canon, color="#FFB300", lw=2.4, zorder=4, label=f"Canonical solution ({canon:.0f} tok)")
    ax.axhspan(0, canon, color="#FFB300", alpha=0.06, zorder=0)

    lines = ["Excess-tokens FE regression (same method as Fig 3):"]
    for eff in EFFORTS:
        if eff in fits:
            f = fits[eff]
            lines.append(f"  {eff:6}: {f['qtr']:4.0f}%/qtr  (β={f['b']:+.3f}/mo, "
                         f"half-life {f['hl']:.1f}mo, {f['pts']} pts)")
    ax.text(0.03, 0.03, "\n".join(lines), transform=ax.transAxes, fontsize=8.5,
            va="bottom", family="monospace",
            bbox=dict(boxstyle="round,pad=0.5", fc="white", ec="#999", alpha=0.95))

    all_dates = sorted({d for eff in EFFORTS for d in gather(eff)[0]})
    lbl_of = {v: k for k, v in DATES.items()}
    ax.set_xticks(all_dates)
    ax.set_xticklabels([f"{lbl_of[d]}\n{d.strftime('%Y-%m')}" for d in all_dates],
                       fontsize=9, fontweight="bold")
    ax.set_ylim(bottom=0)
    ax.set_xlabel("Model (release date)", fontsize=11)
    ax.set_ylabel("Per-problem mean trace length (output tokens)", fontsize=11)
    ax.set_title("Reasoning length over generations by effort level\n"
                 "(hard-but-doable-10; faint = per problem, bold = mean)", fontsize=12.5)
    ax.legend(loc="upper right", framealpha=0.95, fontsize=9)
    plt.tight_layout()
    out = OUT / "fig_effort_efficiency.png"
    fig.savefig(out, dpi=200, bbox_inches="tight"); plt.close(fig)
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
