"""The behaviour table: BOTH behaviours from the LLM judge, with markers alongside.

PRIMARY INSTRUMENT: gemini-2.5-flash, whole trace, one count per trace per
behaviour. Whole-trace because the prompts ask the judge to COUNT occurrences,
which needs the whole chain -- a fragment cannot tell a backtrack from a first
attempt. Chunking or marker-anchored windows over-count ~5-6x against a hand
count.

THE STRING-MARKER COLUMN IS A CROSS-CHECK, not the headline. It counts only
explicit abandonment language, so it is narrower by construction, and it has known
RECALL GAPS -- the set lacks "another approach" and "step wrong", both of which
appear in traces where the judge correctly found instances it missed.

BOTH INSTRUMENTS HAVE A KNOWN PROBLEM AND THE REVIEW IS OPEN. The judge's count
correlates more with how often the model writes "wait" (r=+0.50) than with
explicit abandonment language (r=+0.35), and its justifications sometimes cite
mere uncertainty ("expresses uncertainty ('Hmm')") as backtracking -- i.e. it may
over-count self-interruption on long traces. Two judges (gemini-2.5-flash,
sonnet-4.5) also correlate only +0.52 with each other on backtracking, against a
preserved ranking on verification. 20 traces are laid out in for_RA_review/ to
settle which instrument is right. Until that lands, report backtracking with the
marker cross-check beside it and say the effect size is instrument-dependent.

MARKER PRECISION, checked by reading samples:
  reconsider / start over / try different / is wrong / made an error  -- mostly genuine
  contradiction -- EXCLUDED by default: in mathematics it is usually a proof
    technique ("...then M_125 > m, contradiction. So indeed...") and not an
    abandoned path. Including it does not change either lever's direction
    (scale 0.37x vs 0.41x, algorithm 3.51x vs 5.15x), only the magnitude.

Rates are POOLED per 10k tokens: sum(counts) / sum(tokens) x 1e4, not the mean of
per-trace ratios. That matters. The mean of ratios is NOT count/length -- for a
sparse behaviour concentrated in long traces, E[c/t] sits well below E[c]/E[t],
so "per trace" divided by "per 10k tokens" implies a trace length that matches
nothing (measured: 19,584 tokens implied for gpt-oss-20b against a true mean of
12,494). A reviewer dividing one row by the other would catch it. Pooled rates
divide exactly: per-trace / per-10k x 1e4 = mean tokens per trace. Raw
per-trace counts scale with trace length, and GLM 5.2's traces are ~3.4x longer
than 5.3's, so a per-trace difference partly just restates a length difference.

A character denominator would be wrong here: GLM 5.2 writes heavy LaTeX (413 "$"
per 10k chars) against 5.3's 7, so markup inflates one model's denominator only.
Tokens are far less sensitive to that, and the lever ratio is stable across
denominators anyway (per char / token / sentence / word all within ~10%).

    python code/llm_judge/behaviour_table.py
    python code/llm_judge/behaviour_table.py --include-contradiction
"""
import argparse
import json
import os
import re
import statistics as st
import sys
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from load_traces import load_all                       # noqa: E402

JUDGED = os.path.join(HERE, "out", "judge_whole_gemini.jsonl")
MODEL_ORDER = ["gpt-oss-20b", "gpt-oss-120b", "GLM 5.2", "GLM 5.3"]
LEVERS = [("SCALE      gpt-oss 20B -> 120B", "gpt-oss-20b", "gpt-oss-120b"),
          ("ALGORITHM  GLM 5.2 -> 5.3", "GLM 5.2", "GLM 5.3")]

HIGH_PRECISION = [
    r"\b(?:doesn'?t|does not|won'?t|will not|didn'?t)\s+work\b",
    r"\bis\s+(?:wrong|incorrect)\b", r"\b(?:that'?s|this is)\s+(?:wrong|incorrect)\b",
    r"\bi\s+made\s+an?\s+(?:error|mistake)\b", r"\bmiscalc\w*\b",
    r"\blet(?:'s| us| me)?\s+(?:try|use)\s+(?:a\s+)?(?:different|another)\b",
    r"\bdifferent\s+approach\b", r"\b(?:start over|start again|scrap that|never mind|forget that)\b",
    r"\blet(?:'s| us| me)?\s+recons\w+\b", r"\bon second thought\b",
    r"\bsomething\s+(?:is\s+)?wrong\b",
]
CONTRADICTION = [r"\bcontradiction\b"]

# WORD is kept only for the recall-rate diagnostic in recall_check.py; the table
# itself is per 10k TOKENS so backtracking and verification share a denominator.
WORD = re.compile(r"\b[a-zA-Z]{2,}\b")

# RECALL-CONTEXT EXCLUSION.
# GLM 5.3 spends much of its trace trying to REMEMBER whether it has seen the
# problem -- "let me reconsider the memory one final time... I believe the answer
# is 63". That fires the backtracking markers without any path being abandoned.
# It is 100x more common in 5.3 than anywhere else (42.07 vs 0.39-0.57 marker hits
# per 10k words; present in 54% of its traces vs ~11%), so it biases the
# 5.2 -> 5.3 comparison specifically. Hand-check of 20 hits each: GLM 5.2 ~14/14
# genuine, GLM 5.3 ~7/20.
# A marker hit is dropped when recall language appears within RECALL_WINDOW chars.
RECALL = re.compile(
    r"\bi\s+(?:recall|remember|believe)\b|\bmy\s+memory\b|\bmisremember\w*\b"
    r"|\brecall(?:ing)?\s+(?:the|that|this|it)\b|\bsearch\s+memory\b"
    r"|\bi'?m\s+thinking\s+of\b|\bknown\s+(?:problem|answer)\b"
    r"|\b(?:19|20)\d\d\s+(?:AIME|AMC|HMMT|USAMO|Putnam)\b", re.I)
RECALL_WINDOW = 400


def count_backtracking(cot, rx, exclude_recall=True, window=RECALL_WINDOW):
    """Marker hits, optionally dropping those in a memory-recall context."""
    hits = list(rx.finditer(cot))
    if not exclude_recall:
        return len(hits), 0
    spans = [(m.start(), m.end()) for m in RECALL.finditer(cot)]
    kept = dropped = 0
    for h in hits:
        near = any(not (h.start() > e + window or h.end() < s - window) for s, e in spans)
        if near:
            dropped += 1
        else:
            kept += 1
    return kept, dropped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--include-contradiction", action="store_true")
    ap.add_argument("--judged", default=JUDGED)
    ap.add_argument("--tex", default=None, help="also write the paper table to this .tex path")
    ap.add_argument("--keep-recall", action="store_true",
                    help="do NOT drop marker hits in memory-recall context (shows the bias)")
    a = ap.parse_args()

    rx = re.compile("|".join(HIGH_PRECISION + (CONTRADICTION if a.include_contradiction else [])),
                    re.I)
    traces = load_all()
    jr = [json.loads(l) for l in open(a.judged)]
    J = {b: [r for r in jr if r["behaviour"] == b and r.get("count") is not None]
         for b in ("verification", "backtracking")}
    drop = {b: sum(1 for r in jr if r["behaviour"] == b and r.get("count") is None)
            for b in J}
    judges = {r.get("judge_model") for v in J.values() for r in v}
    print(f"both behaviours: LLM judge {judges}")
    print(f"  verification {len(J['verification'])} traces ({drop['verification']} unparsable "
          f"dropped)   backtracking {len(J['backtracking'])} ({drop['backtracking']} dropped)")
    print(f"  marker cross-check: explicit abandonment language, contradiction "
          f"{'INCLUDED' if a.include_contradiction else 'excluded'}\n")
    ok = J["verification"]

    res = {}
    print(f"  {'model':<15}{'n':>5}{'verif/trace':>12}{'verif/10k':>11}"
          f"{'bt/trace':>10}{'bt/10k':>8}{'|  marker bt/10k':>18}")
    for m in MODEL_ORDER:
        g = [r for r in ok if r["model"] == m]
        t = [r for r in traces if r["model"] == m]
        v_tr = st.mean(r["count"] for r in g)
        # pooled, not mean-of-ratios -- see the module note
        v_rt = 1e4 * sum(r["count"] for r in g) / max(1, sum(r["tokens"] for r in g))
        # PRIMARY: the judge's backtracking counts
        jb = [r for r in J["backtracking"] if r["model"] == m]
        b_tr = st.mean(r["count"] for r in jb)
        b_rt = 1e4 * sum(r["count"] for r in jb) / max(1, sum(r["tokens"] for r in jb))
        # CROSS-CHECK: explicit abandonment markers over the same traces
        bcounts = [count_backtracking(r["cot"], rx, not a.keep_recall)[0] for r in t]
        mk_rt = 1e4 * sum(bcounts) / max(1, sum(r["tokens"] for r in t))
        dropped = sum(count_backtracking(r["cot"], rx, not a.keep_recall)[1] for r in t)
        raw = sum(len(rx.findall(r["cot"])) for r in t)
        res[m] = (v_tr, v_rt, b_rt, st.median(len(r["cot"]) for r in t), len(g), b_tr,
                  dropped, raw, mk_rt)
        print(f"  {m:<15}{len(g):>5}{v_tr:>12.2f}{v_rt:>11.2f}{b_tr:>10.2f}{b_rt:>8.2f}"
              f"{mk_rt:>18.2f}")

    print("\n  the two levers")
    for lever, x, y in LEVERS:
        av, ar, ab = res[x][:3]; zv, zr, zb = res[y][:3]
        print(f"    {lever}")
        print(f"      verification  per trace {av:6.2f} -> {zv:6.2f} ({zv/av:5.2f}x)"
              f"   per 10k tok {ar:5.2f} -> {zr:5.2f} ({zr/ar:5.2f}x)")
        print(f"      backtracking  per 10k tok {ab:5.2f} -> {zb:5.2f} ({zb/ab:5.2f}x)"
              f"   [markers {res[x][8]:.2f} -> {res[y][8]:.2f} ({res[y][8]/res[x][8]:.2f}x)]")

    if a.tex:
        latex(res, a.tex)


def latex(res, path):
    """Emit the paper table. Mirrors table_decay.py's booktabs style."""
    def col(m):
        v_tr, v_rt, b_wd = res[m]
        return f"${v_tr:.2f}$ & ${v_rt:.2f}$ & ${b_wd:.2f}$"
    t = [r"\begin{tabular}{lcccc}", r"\toprule",
         r" & \multicolumn{2}{c}{Scale} & \multicolumn{2}{c}{Algorithm} \\",
         r"\cmidrule(lr){2-3}\cmidrule(lr){4-5}",
         r" & gpt-oss-20B & gpt-oss-120B & GLM 5.2 & GLM 5.3 \\", r"\midrule"]
    names = ["gpt-oss-20b", "gpt-oss-120b", "GLM 5.2", "GLM 5.3"]
    rows_spec = [("Verification, per trace", 0, "{:.2f}"),
                 ("Verification, per 10k tokens", 1, "{:.2f}"),
                 ("Backtracking, per trace", 5, "{:.2f}"),
                 ("Backtracking, per 10k tokens", 2, "{:.2f}"),
                 (r"\quad \emph{marker cross-check, per 10k}", 8, "{:.2f}")]
    for lab, i, f in rows_spec:
        t.append(lab + " & " + " & ".join("$" + f.format(res[m][i]) + "$" for m in names) + r" \\")
    t += [r"\addlinespace",
          "Median CoT characters & " +
          " & ".join("$" + f"{res[m][3]:,.0f}".replace(",", "{,}") + "$" for m in names) + r" \\",
          "Traces judged & " +
          " & ".join(f"${res[m][4]}$" for m in names) + r" \\",
          r"\bottomrule", r"\end{tabular}"]
    tex = "\n".join(t)
    Path(path).write_text(tex + "\n")
    print(f"\nwrote {path}")
    return tex


if __name__ == "__main__":
    main()
