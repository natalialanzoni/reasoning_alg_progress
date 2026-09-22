"""Aggregate LLM-judge records into per-model behaviour counts.

One record per trace per behaviour (whole-trace judging, no chunking), so a
"count" here is the judge's count for a complete reasoning trace.

TWO NUMBERS, because they answer different questions:
  per trace     how much of this behaviour in a whole solution
  per 10k tok   how DENSE the behaviour is in the reasoning

GLM 5.2's traces are ~3.4x longer than GLM 5.3's, so a per-trace difference
partly restates a length difference. Quote the rate when comparing models of
different verbosity; quote the count when the claim is about a whole solution.

    python code/llm_judge/aggregate.py code/llm_judge/out/judge_whole_gemini.jsonl
"""
import collections
import json
import statistics as st
import sys

MODEL_ORDER = ["gpt-oss-20b", "gpt-oss-120b", "GLM 5.2", "GLM 5.3"]
LEVERS = [("SCALE      gpt-oss 20B -> 120B", "gpt-oss-20b", "gpt-oss-120b"),
          ("ALGORITHM  GLM 5.2 -> 5.3", "GLM 5.2", "GLM 5.3")]


def main(path):
    rows = [json.loads(l) for l in open(path)]
    ok = [r for r in rows if r.get("count") is not None and not r.get("error")]
    bad = len(rows) - len(ok)
    judges = {r.get("judge_model") for r in ok}
    print(f"{len(rows):,} records   usable {len(ok):,}   dropped {bad} "
          f"({100*bad/max(1,len(rows)):.1f}%)   judge {judges}")
    if bad:
        print("  NOTE dropped = unparsable <count> or API error; they are NOT zeros.")

    behaviours = sorted({r["behaviour"] for r in ok})
    for b in behaviours:
        print(f"\n=== {b} ===")
        print(f"  {'model':<15}{'traces':>7}{'per trace':>11}{'median':>8}{'per 10k tok':>13}"
              f"{'% traces >0':>13}")
        for m in MODEL_ORDER:
            g = [r for r in ok if r["model"] == m and r["behaviour"] == b]
            if not g:
                continue
            c = [r["count"] for r in g]
            rate = [1e4 * r["count"] / r["tokens"] for r in g if r["tokens"]]
            print(f"  {m:<15}{len(g):>7}{st.mean(c):>11.2f}{st.median(c):>8.1f}"
                  f"{st.mean(rate):>13.2f}{100*sum(1 for x in c if x > 0)/len(c):>12.0f}%")

    print("\n=== the two levers (fig_mechanism) ===")
    for lever, a, z in LEVERS:
        print(f"  {lever}")
        for b in behaviours:
            def agg(m):
                g = [r for r in ok if r["model"] == m and r["behaviour"] == b]
                return (st.mean([r["count"] for r in g]),
                        st.mean([1e4 * r["count"] / r["tokens"] for r in g if r["tokens"]]))
            ca, ra = agg(a); cz, rz = agg(z)
            f = lambda x, y: f"{y/x:.2f}x" if x else "n/a"
            print(f"    {b:<16} per trace {ca:6.2f} -> {cz:6.2f} ({f(ca,cz):>6})"
                  f"   per 10k tok {ra:5.2f} -> {rz:5.2f} ({f(ra,rz):>6})")
        print()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "code/llm_judge/out/judge_whole_gemini.jsonl")
