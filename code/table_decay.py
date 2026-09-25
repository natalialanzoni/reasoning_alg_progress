"""Main decay table (tab:decay) -- the per-family excess-trend regression.

    log(L_ijt - MHD_j) = alpha_j + beta * Month_i + eps

estimated separately per family on correct attempts over the 40 competition
problems, with problem fixed effects. Standard errors are a wild cluster bootstrap
over MODELS, because Month is constant within a model: only 6-8 time points identify
beta, so clustering by problem would treat thousands of traces as independent
evidence about the trend and is badly anti-conservative.

Inference is a WILD CLUSTER BOOTSTRAP-t (WCR), imposing H0: beta = 0 and studentizing
with a cluster-robust SE in every replication, using WEBB six-point weights. Two
choices matter and both are the standard recommendation for few clusters
(Cameron-Gelbach-Miller; Roodman et al. 2019):

  Webb over Rademacher  -- a Rademacher bootstrap has only 2^G sign patterns, so with
    G=6 the smallest attainable two-sided p is 2^(1-G) = 0.031 and p<0.01 is
    unreachable regardless of effect size. Webb gives 6^G patterns.
  bootstrap-t over percentile -- the percentile interval from an UNRESTRICTED
    bootstrap is anti-conservative here. It excludes zero for both families, but the
    bootstrap-t puts Anthropic at p = 0.066, i.e. NOT significant at 5% despite
    t = -5.8. Do not read significance off the reported interval.

The interval is printed to the console because it is what the Figure 4 band shows, but
the LaTeX table carries neither the interval nor significance stars -- only the
coefficient, its bootstrap SE, and the bootstrap-t p.

Four columns: each family on all its models, and on the PRE-CUTOFF models only (training
data ends before the Feb 2026 benchmark, the fig4_forecast_precutoff_appendix sample).
With few clusters (Anthropic pre-cutoff has G = 4) the bootstrap-t is the honest test and
it has little power; read those p-values accordingly.

    ./venv/bin/python code/table_decay.py            # print
    ./venv/bin/python code/table_decay.py OUT.tex    # and write LaTeX
"""
import importlib.util
import math
import os
import sys
from datetime import datetime

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("pf", os.path.join(HERE, "paper_figures_71226.py"))
pf = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(pf)

# Same sample as every current figure: the 40 competition problems, MATH-500 out.
KEYS = {t for t in pf.CANON_KEYS if not str(t).startswith("math_500")}
ANTH = list(pf.OPUS_MODELS) + [
    ("Fable 5.1", datetime(2026, 9, 1),
     pf.RESULTS_DIR / "fable5.1_shallow_pass" / "claude-fable-5-1_medium_thinking_benchmark.json")]
FAMILIES = [("OpenAI (GPT)", list(pf.MAIN_K8)), ("Anthropic (Opus + Fable)", ANTH)]


def pre_cutoff(mfiles):
    """The contamination-check sample (fig4_forecast_precutoff_appendix): models whose
    published TRAINING-DATA cutoff month is strictly before Feb 2026, when the benchmark
    problems went public, so none can have trained on them. A model with no recorded
    cutoff is dropped, never assumed clean. Same rule as figure_forecast_ft._pre_cutoff."""
    return [m for m in mfiles if m[0] in pf.TRAIN_CUTOFF and pf.TRAIN_CUTOFF[m[0]] < pf.CUTOFF_MONTH]


# One column per (family, sample). Families are never pooled: a single time trend across
# two labs would mix their levels with calendar time.
COLUMNS = [(fam, sample, ms) for fam, mf in FAMILIES
           for sample, ms in (("All models", mf), ("Pre-cutoff", pre_cutoff(mf)))]


def rows_for(mfiles, dv="excess"):
    """Build the regression rows. `dv` selects the dependent variable:

      "excess"    log(L/MHD_j - 1)  -- the headline spec; decay toward the floor
      "logL"      log(L)            -- same form, no floor, for comparability
      "logthink"  log(thinking)     -- ROBUSTNESS: is the decline just shorter answers?

    The thinking-only variant takes NO floor. The floor is the shortest human-written
    derivation, i.e. exposition, which is the analogue of the model's ANSWER rather
    than its hidden scratch work, so subtracting it from thinking is not meaningful.
    It is also unusable empirically: log(thinking - MHD_j) would censor 38.4% of
    gpt-6-astra's traces and 26.2% of Fable 5.1's, which is the same defect that
    disqualified MATH-500 as a contamination panel. "logL" is reported alongside so
    the thinking comparison holds functional form fixed and varies only the DV.
    """
    out = []
    for label, date, path in mfiles:
        month = (date - pf.ORIGIN).days / 30.44
        for r in pf.load_rows(path):
            tid = str(r["task_id"])
            if tid not in KEYS:
                continue
            th = r.get("thinking_tokens")
            for i, (tok, c) in enumerate(zip(r["total_completion_tokens"], r["correct"])):
                # validity is "did it produce an answer" (tok >= 50). A zero-length
                # thinking block is NOT invalid -- Fable 5.1 answers correctly with
                # no thinking block on a quarter of problems, and those are its
                # shortest traces. See figures_sept._trial_ok. A cap-hit trace never
                # delivered an answer, so it cannot count as a success here either.
                if tok < 50 or not c or tok >= 40000:
                    continue
                if dv == "excess":
                    # the PAPER'S DV, log(L - MHD_j), in absolute tokens. It used to
                    # be log(h - 1) = log(L - C_j) - log(C_j), justified by -log(C_j)
                    # being absorbed by the problem FE. That holds only while C_j
                    # depends on the problem alone; with per-model tokenizers it also
                    # varies by model and correlates with time, which put Anthropic at
                    # 48.6%/qtr against the correct 44.1%. See README item 15.
                    cj = pf.floor_for(label, tid)        # model's own tokenizer
                    if tok > cj:               # log requires excess > 0
                        out.append((tid, month, label, math.log(tok - cj)))
                elif dv == "logL":
                    out.append((tid, month, label, math.log(tok)))
                elif dv == "logthink":
                    if th is not None and th[i] > 0:
                        out.append((tid, month, label, math.log(th[i])))
                else:
                    raise ValueError(dv)
    return out


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
    b = float(bh[1])
    A = np.linalg.pinv(P.T @ P)

    def cr_se1(Xm, u):
        """cluster-robust SE of the month coefficient, with the G/(G-1) correction."""
        meat = np.zeros((Xm.shape[1], Xm.shape[1]))
        for g in range(G):
            m = cl == g; sc = Xm[m].T @ u[m]; meat += np.outer(sc, sc)
        return math.sqrt(max((A @ meat @ A * (G / (G - 1)))[1, 1], 1e-300))

    # WCR bootstrap-t under H0: beta = 0, Webb weights
    t_hat = b / cr_se1(P, e)
    Q = np.delete(P, 1, axis=1); br = np.linalg.pinv(Q) @ y
    er = y - Q @ br; fit0 = Q @ br
    webb = np.array([-math.sqrt(1.5), -1.0, -math.sqrt(0.5),
                     math.sqrt(0.5), 1.0, math.sqrt(1.5)])
    hits = 0
    for w in np.random.default_rng(seed + 1).choice(webb, size=(B, G)):
        ys = fit0 + w[cl] * er
        bstar = Pinv @ ys
        hits += int(abs(bstar[1] / cr_se1(P, ys - P @ bstar)) >= abs(t_hat))
    pval = (hits + 1) / (B + 1)
    return dict(b=b, se=float(bs.std(ddof=1)),
                lo=float(np.percentile(bs, 2.5)), hi=float(np.percentile(bs, 97.5)),
                n=n, G=G, J=J, q=(1 - math.exp(3 * b)) * 100, hl=-math.log(2) / b,
                t=t_hat, p=pval,
                star="***" if pval < 0.01 else "**" if pval < 0.05
                     else "*" if pval < 0.10 else "")


res = {(fam, sample): fit(rows_for(ms)) for fam, sample, ms in COLUMNS}
keys = [(fam, sample) for fam, sample, _ in COLUMNS]
print(f"{'family':<26s} {'sample':<11s} {'beta':>9s} {'SE':>7s} {'95% CI':>18s} {'t':>7s} "
      f"{'WCR p':>7s} {'%/qtr':>7s} {'N':>6s} {'G':>3s}")
for (fam, sample), (_, _, ms) in zip(keys, COLUMNS):
    r = res[(fam, sample)]
    print(f"  {fam:<24s} {sample:<11s} {r['b']:>+9.4f} {r['se']:>7.4f} "
          f"[{r['lo']:+.3f}, {r['hi']:+.3f}] {r['t']:>7.2f} {r['p']:>7.4f}{r['star']:<3s} "
          f"{r['q']:>6.1f}% {r['n']:>6d} {r['G']:>3d}   " + ", ".join(m[0] for m in ms))

tex = [r"\begin{tabular}{l" + "c" * len(keys) + "}", r"\toprule",
       " & " + " & ".join(rf"\multicolumn{{2}}{{c}}{{{f}}}" for f, _ in FAMILIES) + r" \\",
       # plain \cmidrule{a-b}, no (lr) trim: see behaviour_table.latex -- the trim is
       # booktabs-only syntax and printed as literal text in the paper's class
       "".join(rf"\cmidrule{{{2 + 2 * i}-{3 + 2 * i}}}" for i in range(len(FAMILIES))),
       " & " + " & ".join(sample for _, sample in keys) + r" \\", r"\midrule"]
cells = lambda f: [res[k][f] for k in keys]
# No significance stars and no interval row: the bootstrap-t p is reported in its own
# row, and the percentile interval is anti-conservative here (see the module note), so
# printing it would invite reading significance off it.
tex += ["Release month & " + " & ".join(f"${res[k]['b']:.3f}$" for k in keys) + r" \\",
        " & " + " & ".join(f"$({v:.3f})$" for v in cells("se")) + r" \\",
        r"\addlinespace",
        "Problem fixed effects & " + " & ".join(f"Yes ({res[k]['J']})"
                                                for k in keys) + r" \\",
        "Observations & " + " & ".join(f"${v:,}$".replace(",", "{,}")
                                       for v in cells("n")) + r" \\",
        "Model clusters & " + " & ".join(f"${v}$" for v in cells("G")) + r" \\",
        "Bootstrap-$t$ $p$ & " + " & ".join(f"${res[k]['p']:.3f}$"
                                            for k in keys) + r" \\",
        r"\midrule",
        "Quarterly reduction & " + " & ".join(f"${v:.1f}\\%$" for v in cells("q")) + r" \\",
        "Half-life (months) & " + " & ".join(f"${v:.1f}$" for v in cells("hl")) + r" \\",
        r"\bottomrule", r"\end{tabular}"]
tex = "\n".join(tex)
print("\n% ---------------- tab:decay ----------------\n" + tex)
if len(sys.argv) > 1:
    with open(sys.argv[1], "w") as fh:
        fh.write(tex + "\n")
    print(f"\nwrote {sys.argv[1]}")
