"""Pull a judged trace next to the judge's own justification, for manual audit.

The judge answers in markdown: a "## Thoughts" block naming what it found, then
the <count>. So its claims are checkable -- you read the Thoughts, then look for
each claimed instance in the trace. This prints them side by side.

Use it to spot-check before trusting a run, and to sanity-check a new judge.

    python code/llm_judge/audit.py --model "GLM 5.2" --behaviour backtracking --n 3
    python code/llm_judge/audit.py --task aime_2026_i_10 --behaviour verification
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from load_traces import load_all                       # noqa: E402

DEFAULT = os.path.join(HERE, "out", "judge_whole_gemini.jsonl")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--records", default=DEFAULT)
    ap.add_argument("--model")
    ap.add_argument("--task")
    ap.add_argument("--behaviour", default="backtracking")
    ap.add_argument("--n", type=int, default=2)
    ap.add_argument("--count-at", type=int, default=None,
                    help="only records whose count equals this")
    ap.add_argument("--trace-chars", type=int, default=0,
                    help="also print the first N chars of the trace itself")
    a = ap.parse_args()

    rows = [json.loads(l) for l in open(a.records)]
    sel = [r for r in rows if r["behaviour"] == a.behaviour
           and (not a.model or r["model"] == a.model)
           and (not a.task or r["task_id"] == a.task)
           and (a.count_at is None or r.get("count") == a.count_at)]
    if not sel:
        raise SystemExit("no matching records")
    cots = {(t["model"], t["task_id"], t["sample"]): t["cot"] for t in load_all()}

    for r in sel[:a.n]:
        cot = cots.get((r["model"], r["task_id"], r["sample"]), "")
        print("=" * 78)
        print(f"{r['model']}  {r['task_id']}  sample={r['sample']}  {r['behaviour']}")
        print(f"COUNT = {r.get('count')}   trace {len(cot):,} chars / {r['tokens']:,} tokens"
              f"   judge {r.get('judge_model')}")
        print("=" * 78)
        print(r.get("raw", "")[:3000])
        if a.trace_chars:
            print("\n--- TRACE (first %d chars) ---" % a.trace_chars)
            print(cot[:a.trace_chars])
        print()


if __name__ == "__main__":
    main()
