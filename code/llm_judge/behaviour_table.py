"""The behaviour table: BOTH behaviours from an LLM judge, with markers alongside.

TWO JUDGE RUNS, one per behaviour, settled at different times:
  verification  out/judge_whole_gemini.jsonl     prompt v0, gemini-2.5-flash
  backtracking  out/judge_backtracking_v6.jsonl  prompt v6, gemini-3.1-pro-preview
                (written by run_backtracking_v6.py; v6 was validated against the
                hand-counted key in gold_soft/, see README)
Every record carries judge_model, prompt_version and prompt_sha, and the console
output prints them, so which run produced a number is on disk. Both are whole
trace, one count per trace. Whole-trace because the prompts ask the judge to
COUNT occurrences, which needs the whole chain -- a fragment cannot tell a
backtrack from a first attempt. Chunking or marker-anchored windows over-count
~5-6x against a hand count.

GUARDS (each of these once produced a wrong number silently):
  * every loaded trace must have exactly one usable record per behaviour; the
    last record for a trace wins (a resumed run appends retries), and --tex is
    refused while any trace has no record at all (e.g. a run still in progress)
  * the per-token denominator is CoT tokens joined from load_traces; a record
    that does not join is an error, never a silent fall-back to whole-completion
    tokens (the pre-2026-09-24 bug)
  * the backtracking file must exist -- there is no fall-back to the v0
    backtracking records inside judge_whole_gemini.jsonl
Unparsable records (no count) are dropped and reported per behaviour; the
"traces judged" rows give each behaviour's own n.

THE STRING-MARKER COLUMN IS A DIAGNOSTIC. It prints to the terminal but is NOT a
row in the paper table -- it measures a narrower construct (only abandonment the
writer states outright) and would invite readers to treat two different
definitions as one measurement. It is here to flag instrument disagreement to us,
not to the reader. It counts only
explicit abandonment language, so it is narrower by construction, and it has known
RECALL GAPS -- the set lacks "another approach" and "step wrong", both of which
appear in traces where the judge correctly found instances it missed.

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

# Two files, because the two behaviours were settled at different times (see the
# module note). judge_whole_gemini.jsonl also holds v0 BACKTRACKING records; they
# are superseded and never read -- only its verification records are used.
JUDGED = os.path.join(HERE, "out", "judge_whole_gemini.jsonl")
JUDGED_BT = os.path.join(HERE, "out", "judge_backtracking_v6.jsonl")
MODEL_ORDER = ["gpt-oss-20b", "gpt-oss-120b", "GLM 5.2", "GLM 5.3"]
NAN = float("nan")
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
# itself is per 10k REASONING TOKENS so backtracking and verification share a
# denominator, and the denominator matches where the behaviours are counted.
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


def load_judged(path, behaviour, keys):
    """Records for one behaviour, one per trace (the last record wins -- a resumed run
    appends its retries). Returns (usable records, unparsable count, traces with no
    record at all)."""
    if not os.path.exists(path):
        raise SystemExit(f"{behaviour}: {path} not found. There is no fall-back file.")
    last = {}
    for line in open(path):
        r = json.loads(line)
        if r["behaviour"] == behaviour:
            last[(r["model"], r["task_id"], r["sample"])] = r
    unknown = set(last) - keys
    if unknown:
        raise SystemExit(f"{behaviour}: {len(unknown)} records in {path} match no loaded trace, "
                         f"e.g. {sorted(unknown)[:3]}. The loader and the judged file disagree.")
    usable = [r for r in last.values() if r.get("count") is not None]
    return usable, len(last) - len(usable), keys - set(last)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--include-contradiction", action="store_true")
    ap.add_argument("--judged", default=JUDGED, help="verification records")
    ap.add_argument("--judged-backtracking", default=JUDGED_BT, help="backtracking records")
    ap.add_argument("--tex", default=None, help="also write the paper table to this .tex path")
    ap.add_argument("--correct-only", action="store_true",
                    help="restrict to traces that reached the right answer")
    ap.add_argument("--common-sample", action=argparse.BooleanOptionalAction, default=True,
                    help="use only traces with a count for BOTH behaviours (default), so the "
                         "two behaviours are measured on the same traces")
    ap.add_argument("--keep-recall", action="store_true",
                    help="do NOT drop marker hits in memory-recall context (shows the bias)")
    a = ap.parse_args()

    rx = re.compile("|".join(HIGH_PRECISION + (CONTRADICTION if a.include_contradiction else [])),
                    re.I)
    traces = load_all()
    # DENOMINATOR. Both behaviours are counted in the CoT, so a per-token rate has
    # to divide by CoT tokens. The judged records carry "tokens", which is the whole
    # completion (CoT + answer), so join back to the traces for cot_tokens. Exact
    # for GLM (thinking_tokens); estimated by character share for gpt-oss, which
    # logs no reasoning-token field.
    CT = {(t["model"], t["task_id"], t["sample"]): t["cot_tokens"] for t in traces}
    approx = sorted({t["model"] for t in traces if not t["cot_tokens_exact"]})

    def key(r):
        return (r["model"], r["task_id"], r["sample"])

    def ctok(r):
        return CT[(r["model"], r["task_id"], r["sample"])]   # load_judged checked the join

    J, drop, missing = {}, {}, {}
    for b, path in (("verification", a.judged), ("backtracking", a.judged_backtracking)):
        J[b], drop[b], missing[b] = load_judged(path, b, set(CT))
    about = {b: sorted({(r.get("judge_model"), r.get("prompt_version", "v0")) for r in v})
             for b, v in J.items()}
    if a.common_sample:
        # A reply with no count is dropped per behaviour, and the two runs drop different
        # traces (v0 verification runs away on some long traces). Keep the intersection, so
        # a difference between the behaviours cannot come from different samples.
        both = set.intersection(*({key(r) for r in v} for v in J.values()))
        for b in J:
            drop[b] += len(J[b]) - sum(key(r) in both for r in J[b])
            J[b] = [r for r in J[b] if key(r) in both]
    if a.correct_only:
        J = {b: [r for r in v if r["correct"]] for b, v in J.items()}
        traces = [t for t in traces if t["correct"]]
    print(f"  sample: {'CORRECT traces only' if a.correct_only else 'all traces'}"
          f"   rates per 10k REASONING tokens"
          f"   (estimated for {', '.join(approx)}; exact elsewhere)"
          f"   {'COMMON sample: traces with both counts' if a.common_sample else 'each behaviour on its own traces'}")
    for b in J:
        print(f"  {b:12} judge/prompt {about[b]}   {len(J[b])} traces used, "
              f"{drop[b]} unparsable dropped, {len(missing[b])} not yet judged")
    print(f"  marker cross-check: explicit abandonment language, contradiction "
          f"{'INCLUDED' if a.include_contradiction else 'excluded'}\n")

    res = {}
    print(f"  {'model':<15}{'n verif':>8}{'verif/trace':>12}{'verif/10k':>11}"
          f"{'n bt':>6}{'bt/trace':>10}{'bt/10k':>8}{'|  marker bt/10k':>18}")
    for m in MODEL_ORDER:
        g = [r for r in J["verification"] if r["model"] == m]
        jb = [r for r in J["backtracking"] if r["model"] == m]
        # the traces the rates use: with --common-sample the length and marker rows cover
        # exactly the judged traces, so per trace / per 10k x 1e4 = mean tokens
        t = [r for r in traces if r["model"] == m and (not a.common_sample or key(r) in both)]
        # pooled, not mean-of-ratios -- see the module note. nan only while a run is
        # incomplete (--tex refuses that case).
        rate = lambda rs: 1e4 * sum(r["count"] for r in rs) / sum(ctok(r) for r in rs) if rs else NAN
        mean = lambda rs: st.mean(r["count"] for r in rs) if rs else NAN
        # CROSS-CHECK: explicit abandonment markers over all loaded traces
        mk = [count_backtracking(r["cot"], rx, not a.keep_recall)[0] for r in t]
        res[m] = {"verif_n": len(g), "verif_trace": mean(g),
                  "verif_10k": rate(g),
                  "bt_n": len(jb), "bt_trace": mean(jb), "bt_10k": rate(jb),
                  # length rows are in reasoning tokens, the per-10k denominator, over the
                  # traces in the sample: per trace / per 10k x 1e4 gives this mean back
                  # (up to the few unparsable records dropped per behaviour). Characters
                  # would inflate GLM 5.2, which writes heavy LaTeX (see module note).
                  "mean_tokens": st.mean(r["cot_tokens"] for r in t),
                  "median_tokens": st.median(r["cot_tokens"] for r in t),
                  "marker_10k": 1e4 * sum(mk) / sum(r["cot_tokens"] for r in t)}
        x = res[m]
        print(f"  {m:<15}{x['verif_n']:>8}{x['verif_trace']:>12.2f}{x['verif_10k']:>11.2f}"
              f"{x['bt_n']:>6}{x['bt_trace']:>10.2f}{x['bt_10k']:>8.2f}{x['marker_10k']:>18.2f}")

    print("\n  the two levers")
    for lever, x, y in LEVERS:
        X, Y = res[x], res[y]
        r = lambda k: f"{X[k]:6.2f} -> {Y[k]:6.2f} ({Y[k] / X[k]:5.2f}x)"
        print(f"    {lever}")
        print(f"      verification  per trace {r('verif_trace')}   per 10k tok {r('verif_10k')}")
        print(f"      backtracking  per trace {r('bt_trace')}   per 10k tok {r('bt_10k')}"
              f"   [markers {r('marker_10k')}]")

    if a.tex:
        gaps = {b: len(v) for b, v in missing.items() if v}
        if gaps:
            raise SystemExit(f"\nNOT writing {a.tex}: traces with no record yet {gaps}. "
                             "Finish the judge run first.")
        latex(res, a.tex, a.common_sample)


def latex(res, path, common):
    """Emit the paper table. Mirrors table_decay.py's booktabs style."""
    t = [r"\begin{tabular}{lcccc}", r"\toprule",
         r" & \multicolumn{2}{c}{Scale} & \multicolumn{2}{c}{Algorithm} \\",
         # No (lr) trim: the parenthesised optional argument is booktabs-specific
         # syntax, and a document whose \cmidrule comes from somewhere else (or from
         # a class that stubs it) prints "(lr)2-3(lr)4-5" as literal text instead of
         # drawing the rules. Plain \cmidrule{a-b} is understood far more widely and
         # differs only by a hair of trim at the rule ends.
         r"\cmidrule{2-3}\cmidrule{4-5}",
         r" & gpt-oss-20B & gpt-oss-120B & GLM 5.2 & GLM 5.3 \\", r"\midrule"]
    names = ["gpt-oss-20b", "gpt-oss-120b", "GLM 5.2", "GLM 5.3"]
    cell = lambda k: " & ".join("$" + f"{res[m][k]:.2f}" + "$" for m in names) + r" \\"
    big = lambda k: " & ".join("$" + f"{res[m][k]:,.0f}".replace(",", "{,}") + "$" for m in names) + r" \\"
    t += ["Verification, per trace & " + cell("verif_trace"),
          "Verification, per 10k reasoning tokens & " + cell("verif_10k"),
          "Backtracking, per trace & " + cell("bt_trace"),
          "Backtracking, per 10k reasoning tokens & " + cell("bt_10k"),
          r"\addlinespace",
          "Mean reasoning tokens & " + big("mean_tokens"),
          "Median reasoning tokens & " + big("median_tokens"),
          # one n when both behaviours use the same traces; otherwise each its own
          *(["Traces judged & " + " & ".join(f"${res[m]['verif_n']}$" for m in names) + r" \\"] if common else
            ["Traces judged, verification & " + " & ".join(f"${res[m]['verif_n']}$" for m in names) + r" \\",
             "Traces judged, backtracking & " + " & ".join(f"${res[m]['bt_n']}$" for m in names) + r" \\"]),
          r"\bottomrule", r"\end{tabular}"]
    tex = "\n".join(t)
    Path(path).write_text(tex + "\n")
    print(f"\nwrote {path}")
    return tex


if __name__ == "__main__":
    main()
