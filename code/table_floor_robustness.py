"""Appendix robustness table: is the MHD definition load-bearing?

Re-estimates the excess-trend slope under four definitions of the floor MHD_j:

    shortest      MHD_j = min of the human solutions   <- the paper's headline (MHD)
    median        MHD_j = median of the human solutions
    mean          MHD_j = mean of the human solutions
    none          no floor at all: log L with problem fixed effects

Everything else is held fixed: the 40 competition problems (MATH-500 excluded),
correct traces, problem fixed effects, per family, and the same wild-cluster
bootstrap over models used in the main decay table.

The DV is exactly pf._fit_headroom_forecast's, log(headroom - 1) = log((L-MHD)/MHD),
with MHD swapped per row, so the "shortest" row reproduces the headline numbers. The
no-floor row uses log(L/C_min); with problem FE that is the same slope as plain
log L, and it keeps the forecast target on a comparable scale.

NOTE on the date column: "within 10% of floor" is defined relative to EACH row's own
floor, so the absolute token target differs by row (10% above a 316-token floor is
348 tokens; above a 466-token floor it is 513). Later rows therefore reach their
target partly because the target is laxer, not only because the slope is steeper.

    ./venv/bin/python code/table_floor_robustness.py
Prints the table and a LaTeX version for the appendix.
"""
import importlib.util
import json
import math
import os
import sys
from datetime import datetime, timedelta

import numpy as np
import tiktoken
from datasets import load_dataset

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("pf", os.path.join(HERE, "paper_figures_71226.py"))
pf = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(pf)

# ---- per-problem min / median / mean of the human solution lengths ----------
_enc = tiktoken.get_encoding("o200k_base")
FLOORS = {}
for r in load_dataset(pf.HF_DATASET, split="test"):
    sc = r.get("solution_count")
    if sc is None or (isinstance(sc, float) and math.isnan(sc)) or sc == 0:
        continue
    n = [len(_enc.encode(s)) for s in json.loads(r["solutions"])]
    FLOORS[str(r["id"])] = {"min": float(min(n)), "median": float(np.median(n)),
                            "mean": float(np.mean(n))}
KEYS = {t for t in FLOORS if not str(t).startswith("math_500")}

ANTH = list(pf.OPUS_MODELS) + [
    ("Fable 5.1", datetime(2026, 9, 1),
     pf.RESULTS_DIR / "fable5.1_shallow_pass" / "claude-fable-5-1_medium_thinking_benchmark.json")]
FAMILIES = [("OpenAI (GPT)", list(pf.MAIN_K8)), ("Anthropic (Opus + Fable)", ANTH)]
SPECS = [("shortest", "min"), ("median", "median"), ("mean", "mean"), ("none (log $L$)", None)]


def build(mfiles, floor):
    rows = []
    for label, date, path in mfiles:
        month = (date - pf.ORIGIN).days / 30.44
        for r in pf.load_rows(path):
            tid = str(r["task_id"])
            if tid not in KEYS:
                continue
            tt = r.get("thinking_tokens", [1] * len(r["correct"]))
            for tok, c, th in zip(r["total_completion_tokens"], r["correct"], tt):
                # zero-thinking traces are valid; cap-hit traces are FAILED
                # attempts and cannot count as successes (fs._trial_correct)
                if tok < 50 or not c or tok >= 40000:
                    continue
                if floor is None:
                    rows.append((tid, month, label, math.log(tok / FLOORS[tid]["min"])))
                else:
                    h = tok / FLOORS[tid][floor]
                    if h > 1:
                        rows.append((tid, month, label, math.log(h - 1)))
    return rows


def fit(rows, B=9999, seed=0):
    probs = sorted({r[0] for r in rows}); pidx = {p: i for i, p in enumerate(probs)}
    models = sorted({r[2] for r in rows}); midx = {m: i for i, m in enumerate(models)}
    J, G, n = len(probs), len(models), len(rows)
    P = np.zeros((n, J + 1)); P[:, 0] = 1.0
    y = np.empty(n); cl = np.empty(n, dtype=int)
    for i, (tid, month, label, yy) in enumerate(rows):
        P[i, 1] = month
        k = pidx[tid]
        if k >= 1:
            P[i, 1 + k] = 1.0
        y[i] = yy; cl[i] = midx[label]
    Pinv = np.linalg.pinv(P); bh = Pinv @ y; e = y - P @ bh
    rng = np.random.default_rng(seed)
    wm = rng.choice([-1.0, 1.0], size=(B, G))
    bs = (((P @ bh)[None, :] + wm[:, cl] * e[None, :]) @ Pinv.T)[:, 1]
    return (float(bh[1]), float(bs.std(ddof=1)), float(np.percentile(bs, 2.5)),
            float(np.percentile(bs, 97.5)), float(bh[0] + bh[2:].sum() / J), n, G)


res = {}
for fam, mf in FAMILIES:
    n_correct = len(build(mf, None))          # every correct trace: the no-floor N
    for name, fl in SPECS:
        b, se, lo, hi, a, n, G = fit(build(mf, fl))
        # No floor is subtracted in the "none" row, so it has no MHD_j to report.
        # log(L/C_min) is used there only so the scale matches: with problem FE a
        # per-problem constant is fully absorbed, so beta equals that of plain log L.
        cbar = np.mean([FLOORS[t][fl] for t in KEYS]) if fl else None
        target = math.log(0.10) if fl else math.log(1.10)
        res[(fam, name)] = dict(
            b=b, se=se, lo=lo, hi=hi, n=n, G=G, drop=n_correct - n, cbar=cbar,
            q=(1 - math.exp(3 * b)) * 100, hl=-math.log(2) / b,
            date=pf.ORIGIN + timedelta(days=((target - a) / b) * 30.44))

print(f"\n{'family':<24s} {'floor':<14s} {'C (tok)':>8s} {'beta':>9s} {'SE':>7s} "
      f"{'%/qtr':>7s} {'half-life':>10s} {'N':>6s} {'drop':>5s} {'within-10%':>11s}")
for fam, _ in FAMILIES:
    for name, _fl in SPECS:
        r = res[(fam, name)]
        cb = f"{r['cbar']:.0f}" if r["cbar"] else "--"
        print(f"  {fam:<22s} {name:<14s} {cb:>8s} {r['b']:>+9.4f} {r['se']:>7.4f} "
              f"{r['q']:>6.1f}% {r['hl']:>9.1f}m {r['n']:>6d} {r['drop']:>5d} "
              f"{r['date']:%Y-%m}".rjust(0))
    qs = [res[(fam, n)]["q"] for n, _ in SPECS]
    ds = [res[(fam, n)]["date"] for n, _ in SPECS]
    print(f"  {'':<22s} {'-> spread':<14s} {min(qs):.1f}-{max(qs):.1f}%/qtr "
          f"({max(qs)-min(qs):.1f} pts);  dates {min(ds):%Y-%m} to {max(ds):%Y-%m}\n")

# ---- LaTeX ------------------------------------------------------------------
_tex = []
_emit = lambda ln: (_tex.append(ln), print(ln))[1]
print("% ---------------- appendix table ----------------")
_emit(r"\begin{tabular}{llccccc}")
_emit(r"\toprule")
_emit(r"Family & Floor $\mathrm{MHD}_j$ & $\overline{\mathrm{MHD}}_j$ & $\hat\beta$ & Quarterly & Half-life & "
      r"Within 10\% \\")
_emit(r" & & (tok) & (SE) & reduction & (months) & of floor \\")
_emit(r"\midrule")
for fi, (fam, _) in enumerate(FAMILIES):
    for si, (name, _fl) in enumerate(SPECS):
        r = res[(fam, name)]
        lead = fam if si == 0 else ""
        cb = f"{r['cbar']:.0f}" if r["cbar"] else r"---"
        _emit(f"{lead} & {name} & {cb} & ${r['b']:.3f}$ ({r['se']:.3f}) & "
              f"{r['q']:.1f}\\% & {r['hl']:.1f} & {r['date']:%Y-%m} \\\\")
    if fi == 0:
        _emit(r"\addlinespace")
_emit(r"\bottomrule")
_emit(r"\end{tabular}")

if len(sys.argv) > 1:          # optional path: also write the LaTeX to a file
    body = "\n".join(_tex)
    with open(sys.argv[1], "w") as fh:
        fh.write(body + "\n")
    print(f"\nwrote {sys.argv[1]}")
