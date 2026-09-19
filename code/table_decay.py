"""Main decay table (tab:decay) -- the per-family excess-trend regression.

    log(L_ijt - MHD_j) = alpha_j + beta * Month_i + eps

estimated separately per family on correct attempts over the 40 competition
problems, with problem fixed effects. Standard errors are a wild cluster bootstrap
over MODELS, because Month is constant within a model: only 6-8 time points identify
beta, so clustering by problem would treat thousands of traces as independent
evidence about the trend and is badly anti-conservative.

Reports confidence intervals rather than significance stars. With G model clusters a
Rademacher wild bootstrap draws from at most 2^G sign patterns, so the smallest
attainable two-sided p-value is 2^(1-G): 0.008 for OpenAI (G=8) but 0.031 for
Anthropic (G=6), where p<0.01 is unreachable regardless of effect size. Starring one
column and not the other would wrongly suggest Anthropic's result is weaker when its
coefficient is in fact larger.

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


def rows_for(mfiles):
    out = []
    for label, date, path in mfiles:
        month = (date - pf.ORIGIN).days / 30.44
        for r in pf.load_rows(path):
            tid = str(r["task_id"])
            if tid not in KEYS:
                continue
            for tok, c in zip(r["total_completion_tokens"], r["correct"]):
                # validity is "did it produce an answer" (tok >= 50). A zero-length
                # thinking block is NOT invalid -- Fable 5.1 answers correctly with
                # no thinking block on a quarter of problems, and those are its
                # shortest traces. See figures_sept._trial_ok.
                if tok < 50 or not c:
                    continue
                h = tok / pf.CANON[tid]["min"]
                if h > 1:                      # log requires excess > 0
                    out.append((tid, month, label, math.log(h - 1)))
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
    return dict(b=b, se=float(bs.std(ddof=1)),
                lo=float(np.percentile(bs, 2.5)), hi=float(np.percentile(bs, 97.5)),
                n=n, G=G, J=J, q=(1 - math.exp(3 * b)) * 100, hl=-math.log(2) / b,
                pmin=2.0 ** (1 - G))


res = {fam: fit(rows_for(mf)) for fam, mf in FAMILIES}
print(f"{'family':<26s} {'beta':>9s} {'SE':>7s} {'95% CI':>18s} {'%/qtr':>7s} "
      f"{'half-life':>10s} {'N':>6s} {'G':>3s} {'min p':>7s}")
for fam, _ in FAMILIES:
    r = res[fam]
    print(f"  {fam:<24s} {r['b']:>+9.4f} {r['se']:>7.4f} "
          f"[{r['lo']:+.3f}, {r['hi']:+.3f}] {r['q']:>6.1f}% {r['hl']:>9.1f}m "
          f"{r['n']:>6d} {r['G']:>3d} {r['pmin']:>7.3f}")

tex = [r"\begin{tabular}{lcc}", r"\toprule",
       " & " + " & ".join(f for f, _ in FAMILIES) + r" \\", r"\midrule"]
cells = lambda f: [res[fam][f] for fam, _ in FAMILIES]
tex += ["Release month & " + " & ".join(f"${v:.3f}$" for v in cells("b")) + r" \\",
        " & " + " & ".join(f"$({v:.3f})$" for v in cells("se")) + r" \\",
        " & " + " & ".join(f"$[{res[f]['lo']:.3f}, {res[f]['hi']:.3f}]$"
                           for f, _ in FAMILIES) + r" \\",
        r"\addlinespace",
        "Problem fixed effects & " + " & ".join(f"Yes ({res[f]['J']})"
                                                for f, _ in FAMILIES) + r" \\",
        "Observations & " + " & ".join(f"${v:,}$".replace(",", "{,}")
                                       for v in cells("n")) + r" \\",
        "Model clusters & " + " & ".join(f"${v}$" for v in cells("G")) + r" \\",
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
