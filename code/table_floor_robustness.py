"""Appendix robustness table: is the MHD definition load-bearing?

Re-estimates the excess-trend slope under four definitions of the floor MHD_j:

    shortest      MHD_j = min of the human solutions   <- the paper's headline (MHD)
    median        MHD_j = median of the human solutions
    mean          MHD_j = mean of the human solutions
    none          no floor at all: log L with problem fixed effects

plus one row that changes the DEPENDENT VARIABLE:

    thinking only log(thinking), no floor. Answers "is the decline just shorter
                  ANSWERS?" -- it is not. Two things happen in the answer that are not
                  reasoning: gpt-5.1 writes 3.1x longer answers than gpt-5 at FLAT
                  thinking, and the series switches output format at gpt-5.1 (LaTeX
                  goes from ~0.3-2% of answer characters to ~20-25% for every later
                  model), which inflates L for the RECENT models. Neither touches the
                  thinking block. Compare this row against "none (log $L$)", which
                  holds functional form fixed and varies only the DV.
                  NO FLOOR, for two reasons: the MHD is a human's WRITTEN derivation,
                  the analogue of the model's answer rather than its scratch work; and
                  log(thinking - MHD_j) would censor 38.4% of gpt-6-astra's traces and
                  26.2% of Fable 5.1's. The milestone column is blank for that reason.
                  Caveat running the safe way: log(thinking) is undefined at zero, so
                  81 traces drop, all Fable 5.1 -- the newest model's shortest -- which
                  UNDERSTATES the decline.

plus one row that varies the SAMPLE rather than the floor:

    pre-cutoff    the headline floor, but only models whose published TRAINING-DATA
                  cutoff precedes the February 2026 benchmark, so they cannot have
                  memorised it. This replaced a standalone appendix figure -- it is
                  one number per family and reads more simply as a row. It is
                  excluded from the "spread" summary, which is about the FLOOR.

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
def _pre_cutoff(mfiles):
    """Models whose published TRAINING-DATA cutoff month precedes the benchmark.

    The contamination check used to be its own appendix figure. It is one number per
    family, so it is a row here instead. NOTE this row varies the SAMPLE, not the
    floor: it keeps the headline "shortest" floor and drops the models that could have
    trained on the AIME/HMMT 2026 problems. A model with no published cutoff is
    dropped rather than assumed clean. See pf.TRAIN_CUTOFF and the README.
    """
    return [m for m in mfiles
            if m[0] in pf.TRAIN_CUTOFF and pf.TRAIN_CUTOFF[m[0]] < pf.CUTOFF_MONTH]


THINK = "__thinking__"     # sentinel: DV is log(thinking), no floor

# (label, floor key, model subset). floor None = no floor (log L);
# floor THINK = no floor and thinking tokens instead of L.
SPECS = [("shortest", "min", None), ("median", "median", None),
         ("mean", "mean", None), ("none (log $L$)", None, None),
         ("thinking only", THINK, None),
         ("pre-cutoff models", "min", _pre_cutoff)]


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
                if floor is THINK:
                    # log(thinking) is undefined at zero, so zero-thinking traces
                    # drop out here -- all of them Fable 5.1, the newest model's
                    # SHORTEST traces, so their loss understates the decline.
                    if th and th > 0:
                        rows.append((tid, month, label, math.log(th)))
                elif floor is None:
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
    for name, fl, sub in SPECS:
        b, se, lo, hi, a, n, G = fit(build(sub(mf) if sub else mf, fl))
        # No floor is subtracted in the "none" row, so it has no MHD_j to report.
        # log(L/C_min) is used there only so the scale matches: with problem FE a
        # per-problem constant is fully absorbed, so beta equals that of plain log L.
        has_floor = fl is not None and fl is not THINK
        cbar = np.mean([FLOORS[t][fl] for t in KEYS]) if has_floor else None
        target = math.log(0.10) if has_floor else math.log(1.10)
        res[(fam, name)] = dict(
            b=b, se=se, lo=lo, hi=hi, n=n, G=G, drop=n_correct - n, cbar=cbar,
            q=(1 - math.exp(3 * b)) * 100, hl=-math.log(2) / b,
            # thinking tokens have no floor, so there is no target to converge TO
            # and the milestone column is left blank rather than filled with a
            # number that looks like a forecast.
            date=None if fl is THINK
                 else pf.ORIGIN + timedelta(days=((target - a) / b) * 30.44))

print(f"\n{'family':<24s} {'floor':<14s} {'C (tok)':>8s} {'beta':>9s} {'SE':>7s} "
      f"{'%/qtr':>7s} {'half-life':>10s} {'N':>6s} {'drop':>5s} {'within-10%':>11s}")
for fam, _ in FAMILIES:
    for name, _fl, _sub in SPECS:
        r = res[(fam, name)]
        cb = f"{r['cbar']:.0f}" if r["cbar"] else "--"
        print(f"  {fam:<22s} {name:<14s} {cb:>8s} {r['b']:>+9.4f} {r['se']:>7.4f} "
              f"{r['q']:>6.1f}% {r['hl']:>9.1f}m {r['n']:>6d} {r['drop']:>5d} "
              f"{r['date']:%Y-%m}" if r["date"] else
              f"  {fam:<22s} {name:<14s} {cb:>8s} {r['b']:>+9.4f} {r['se']:>7.4f} "
              f"{r['q']:>6.1f}% {r['hl']:>9.1f}m {r['n']:>6d} {r['drop']:>5d} "
              f"{'--':>7s}")
    qs = [res[(fam, n)]["q"] for n, fl, sub in SPECS
          if sub is None and fl is not THINK]
    ds = [res[(fam, n)]["date"] for n, fl, sub in SPECS
          if sub is None and fl is not THINK]
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
    for si, (name, _fl, _sub) in enumerate(SPECS):
        r = res[(fam, name)]
        lead = fam if si == 0 else ""
        cb = f"{r['cbar']:.0f}" if r["cbar"] else r"---"
        # set the sample-restriction row apart: it varies the SAMPLE, not the floor
        if (_sub is not None or _fl is THINK) and si:
            _emit(r"\addlinespace[2pt]")
        _emit(f"{lead} & {name} & {cb} & ${r['b']:.3f}$ ({r['se']:.3f}) & "
              f"{r['q']:.1f}\\% & {r['hl']:.1f} & "
              + (f"{r['date']:%Y-%m}" if r["date"] else "---") + r" \\")
    if fi == 0:
        _emit(r"\addlinespace")
_emit(r"\bottomrule")
_emit(r"\end{tabular}")

if len(sys.argv) > 1:          # optional path: also write the LaTeX to a file
    body = "\n".join(_tex)
    with open(sys.argv[1], "w") as fh:
        fh.write(body + "\n")
    print(f"\nwrote {sys.argv[1]}")
