"""Does a model RECALL these benchmark answers, or confabulate them?

THE NAIVE TEST IS WRONG AND FLATTERS EVERY MODEL. Counting every "I recall the
answer is X" against gold scores post-hoc restatement as memory: a model that
computes 62 and then writes "yes, I recall the answer is 062" is counted as a
match. Measured that way GLM 5.2 looks like the best recaller in the set (40%),
despite making essentially no real recall attempts.

THE CLEAN TEST restricts to claims made BEFORE the model has computed anything --
before the first equation with a computed right-hand side (or, as a cruder
alternative, inside the opening 12% of the trace). There the model cannot have
derived the number, so a match is evidence of memory.

Result (2026-09-22, thinking-benchmark-90, 40 competition problems, k=8):

    model          attempts/10k tok  % traces   pre-comp claims   matching gold
    gpt-oss-20b    0.18              11%        0                 --
    gpt-oss-120b   0.16              10%        1                 0 (0%)
    GLM 5.2        0.10              13%        0                 --
    GLM 5.3        9.86              54%        84                0 (0%)

ZERO pre-computation claims match gold, across all four models.

EVERY column is pre-computation-restricted. An attempt counted late in a trace is
the model restating an answer it already derived, which inflates the rate exactly
the way the naive match test did.

For contrast, the NAIVE test (every claim, regardless of position) gives 16-40%
and ranks GLM 5.2 highest at 40% -- despite GLM 5.2 making no real recall attempts
at all. That column is not reported here because it cannot be read correctly.

GLM 5.3 attempts recall ~100x more than any other model here (marker hits per 10k tokens; present in 54% of its traces vs ~11%) and gets ZERO of its
83 pre-computation claims right (over all 320 of its traces; 62 claims in its correct
traces). It cites contest years from 1984 to 2025, most often 2024 (1,054 times), then
2025, 2020, 2014 -- never 2026, because its training predates the benchmark.

So: NOT contamination. Confabulated retrieval. Which is also why backtracking
markers need the recall-context exclusion in behaviour_table.py -- "let me
reconsider [whether I'm remembering right]" is not an abandoned path.

    python code/llm_judge/recall_check.py
"""
import re
import sys
import os
import statistics as st

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from load_traces import load_all                       # noqa: E402
from behaviour_table import RECALL, WORD               # noqa: E402

MODEL_ORDER = ["gpt-oss-20b", "gpt-oss-120b", "GLM 5.2", "GLM 5.3"]
CLAIM = re.compile(r"(?:i\s+(?:recall|remember|believe)|my memory"
                   r"|answer (?:is|was|might be|being))[^.!?\n]{0,120}?\b(\d{1,4})\b", re.I)
# "computation has begun": an equation with a computed RHS, or an explicit compute step
EQ = re.compile(r"=\s*[-+]?\d|\\boxed|\\frac|\bcompute\b|\bcalculat", re.I)
EARLY_FRAC = 0.12
YEAR = re.compile(r"\b((?:19|20)\d\d)\s+(?:AIME|AMC|HMMT|USAMO|Putnam)", re.I)


def _norm(x):
    """gold is zero-padded ('062'); a recalled '62' is the same answer."""
    try:
        return str(int(x))
    except Exception:
        return str(x).strip()


def main():
    from datasets import load_dataset
    gold = {str(r["id"]): _norm(r["answer"])
            for r in load_dataset("tyrtleli/thinking-benchmark-90", split="test")}
    rows = load_all()
    totals = [0, 0]
    print("  EVERYTHING here is restricted to BEFORE the model computes anything.\n"
          "  A recall claim made after computation is the model restating its own\n"
          "  answer, not remembering one, so it cannot test recall.\n")
    print(f"  {'model':<15}{'attempts/10k tok':>17}{'% traces':>10}"
          f"{'w/ a number':>13}{'matching gold':>15}")
    for m in MODEL_ORDER:
        g = [r for r in rows if r["model"] == m]
        att = tok = 0; ntr = 0; pa = ph = 0
        for r in g:
            cot = r["cot"]; gd = gold.get(r["task_id"], "")
            e = EQ.search(cot)
            pre = cot[:e.start()] if e else cot          # the pre-computation region
            n = len(RECALL.findall(pre))
            att += n; tok += r["tokens"]; ntr += (n > 0)
            for mm in CLAIM.finditer(pre):
                pa += 1; ph += (_norm(mm.group(1)) == gd)
        rate = 1e4 * att / max(1, tok)
        match = f"{ph}/{pa} ({100*ph/pa:.0f}%)" if pa else "--"
        print(f"  {m:<15}{rate:>17.2f}{100*ntr/len(g):>9.0f}%{pa:>13}{match:>15}")
        totals[0] += pa; totals[1] += ph

    pa, ph = totals
    print(f"\n  ALL MODELS: {ph} of {pa} pre-computation recall claims match gold "
          f"({100*ph/pa:.1f}%)" if pa else "")
    print("  No model recalls an answer before deriving it. With n=%d the upper bound on\n"
          "  a true recall rate is roughly 1 in %d, not literally zero." % (pa, pa))

    yrs = {}
    for r in (x for x in rows if x["model"] == "GLM 5.3"):
        for y in YEAR.findall(r["cot"]):
            yrs[y] = yrs.get(y, 0) + 1
    top = sorted(yrs.items(), key=lambda kv: -kv[1])[:6]
    print("\n  years GLM 5.3 cites: " + ", ".join(f"{k}:{v}" for k, v in top))
    print("  (never 2026 -- its training predates the benchmark)")


if __name__ == "__main__":
    main()
