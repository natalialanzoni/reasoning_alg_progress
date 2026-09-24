"""Appendix table: the backtracking levers under each judge prompt, on the same traces.

  python code/llm_judge/prompt_robustness_table.py --tex paper_figs/table_backtracking_prompts.tex
  python code/llm_judge/prompt_robustness_table.py --all-traces      # the same, all traces

The main table uses v6. This one shows how much the answer depends on how backtracking is
defined: the same 1,280 traces judged under the four prompts we ran (v0 upstream, v2 carried
forward, v3 brief candidates, v6 wasted search; README has what each counts). Correct traces
only by default, matching the paper's per-correct-trace framing.

Cells are newer/bigger over older/smaller. Rates are pooled exactly as in behaviour_table.py,
using its loader, so the v6 column reproduces the main table's ratios. The last column is v6
with every problem weighted equally: each model's per-problem mean (per trace) or per-problem
pooled rate (per 10k), averaged over the problems both models have traces for, so a model
that solves more samples of a hard problem does not weight that problem more.
"""
import argparse
import os
import statistics as st
import sys
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from behaviour_table import LEVERS, load_judged        # noqa: E402
from load_traces import load_all                       # noqa: E402

RUNS = [("v0", "judge_whole_gemini.jsonl"), ("v2", "judge_backtracking_v2.jsonl"),
        ("v3", "judge_backtracking_v3.jsonl"), ("v6", "judge_backtracking_v6.jsonl")]


def per_trace(rs):
    return st.mean(r["count"] for r in rs)


def per_10k(rs, ct):
    return 1e4 * sum(r["count"] for r in rs) / sum(ct[k(r)] for r in rs)


def k(r):
    return (r["model"], r["task_id"], r["sample"])


def equal_weight(rs, old, new, f):
    """f averaged over problems (each problem once), for problems both models have."""
    by = {}
    for r in rs:
        by.setdefault((r["model"], r["task_id"]), []).append(r)
    probs = sorted({p for m, p in by if m == old} & {p for m, p in by if m == new})
    return st.mean(f(by[(new, p)]) for p in probs) / st.mean(f(by[(old, p)]) for p in probs), len(probs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all-traces", action="store_true", help="do not restrict to correct traces")
    ap.add_argument("--tex", default=None)
    a = ap.parse_args()

    traces = load_all()
    ct = {k(t): t["cot_tokens"] for t in traces}
    cols, n_eq = {}, {}
    for name, f in RUNS:
        rs, _, missing = load_judged(os.path.join(HERE, "out", f), "backtracking", set(ct))
        if missing:
            raise SystemExit(f"{name}: {len(missing)} traces have no record")
        if not a.all_traces:
            rs = [r for r in rs if r["correct"]]
        col, eq = {}, {}
        for lever, old, new in LEVERS:
            R = {m: [r for r in rs if r["model"] == m] for m in (old, new)}
            col[(lever, "trace")] = per_trace(R[new]) / per_trace(R[old])
            col[(lever, "10k")] = per_10k(R[new], ct) / per_10k(R[old], ct)
            if name == "v6":
                eq[(lever, "trace")], n_eq[lever] = equal_weight(rs, old, new, per_trace)
                eq[(lever, "10k")], _ = equal_weight(rs, old, new, lambda g: per_10k(g, ct))
        cols[name] = col
        if eq:
            cols["v6, problems equal"] = eq
    order = [n for n, _ in RUNS] + ["v6, problems equal"]

    rows = [((lever, unit), f"{lever.split()[0].capitalize()}, per {'trace' if unit == 'trace' else '10k tokens'}")
            for lever, _, _ in LEVERS for unit in ("trace", "10k")]
    print(f"backtracking, newer/older, {'all' if a.all_traces else 'correct'} traces")
    print(f"  {'':28}" + "".join(f"{c:>20}" for c in order))
    for key, lab in rows:
        print(f"  {lab:28}" + "".join(f"{cols[c][key]:>19.2f}x" for c in order))
    print(f"  problems in the equal-weight column: {n_eq}")
    if a.tex:
        t = [r"\begin{tabular}{lccccc}", r"\toprule",
             r" & \multicolumn{4}{c}{Judge prompt} & v6, each problem \\",
             r"\cmidrule{2-5}",
             r"Backtracking, newer / older & v0 & v2 & v3 & v6 & weighted equally \\", r"\midrule"]
        for key, lab in rows:
            t.append(lab.replace("10k tokens", "10k reasoning tokens") + " & "
                     + " & ".join(f"${cols[c][key]:.2f}\\times$" for c in order) + r" \\")
        t += [r"\bottomrule", r"\end{tabular}"]
        Path(a.tex).write_text("\n".join(t) + "\n")
        print(f"wrote {a.tex}")


if __name__ == "__main__":
    main()
