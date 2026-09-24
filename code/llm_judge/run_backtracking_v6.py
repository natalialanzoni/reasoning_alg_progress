"""Full run of backtracking v6 on the 1,280 fig_mechanism traces.

  python code/llm_judge/run_backtracking_v6.py            # dry run: volume, cost, nothing sent
  python code/llm_judge/run_backtracking_v6.py --send     # full run, resumable
  python code/llm_judge/behaviour_table.py --judged-backtracking out/judge_backtracking_v6.jsonl

Why a separate script: v6 differs from v0-v3 in its INPUT (the trace is line-numbered, so the
judge can cite lines) and its OUTPUT (quoted instances, not just a count). The request,
numbering and quote check are the pilot's (pilot.py / pilot_v4.py), so the full run sees
exactly what the pilot validated against gold_soft/.

`count` is the number of instances whose abandon quote is found in the trace (the measure the
pilot scored), set only when the reply reached <count>. A reply cut off before <count> stays
None, which behaviour_table.py drops. The judge's own <count> is kept as `judge_count`.

Output cap: the pilot's 24,000 cut off 1/20 replies (the judge's reasoning counts against it),
so this uses the model's full 65,536.
"""
import argparse
import hashlib
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from load_traces import load_all, MODEL_ORDER          # noqa: E402
import pilot as P                                       # noqa: E402
import pilot_v4 as p                                    # noqa: E402

JUDGE_MODEL = "google/gemini-3.1-pro-preview"   # $2/M in, $12/M out (OpenRouter, 2026-09-24)
PROMPT_VERSION = "v6"
TEMPERATURE = 0
MAX_OUT = 65536
OUT = os.path.join(HERE, "out", "judge_backtracking_v6.jsonl")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--send", action="store_true", help="REQUIRED to contact OpenRouter")
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()

    tmpl = open(os.path.join(HERE, f"backtracking_{PROMPT_VERSION}.txt")).read()
    sha = hashlib.sha256(tmpl.encode()).hexdigest()[:16]
    rows = load_all(MODEL_ORDER)
    done = set()
    if os.path.exists(a.out):
        for d in map(json.loads, open(a.out)):
            # an errored or empty reply is retried on the next run; the last record wins
            if (d.get("raw") or "").strip() and d.get("finish") != "error":
                done.add((d["model"], d["task_id"], d["sample"]))
    todo = [r for r in rows if (r["model"], r["task_id"], r["sample"]) not in done]
    chars = sum(len(r["cot"]) for r in todo)
    print(f"traces {len(rows)}, already judged {len(done)}, to send {len(todo)}")
    # pilot means on the same prompt and judge: 28.7k in, 13.3k out per trace
    print(f"  ~{len(todo) * 28.7e3 / 1e6:.1f}M in, ~{len(todo) * 13.3e3 / 1e6:.1f}M out "
          f"-> ~${len(todo) * (28.7e3 * 2 + 13.3e3 * 12) / 1e6:,.0f}  ({chars / 1e6:.1f}M chars of CoT)")
    if not a.send:
        print("DRY RUN -- nothing sent. Re-run with --send.")
        return
    key = os.environ.get("ERA_OPENROUTER_V2") or os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise SystemExit("no OpenRouter key (ERA_OPENROUTER_V2 / OPENROUTER_API_KEY)")

    def one(r):
        lines, numbered = p.number_lines(r["cot"])
        res = P.call(key, JUDGE_MODEL, tmpl.replace("{response}", numbered), MAX_OUT)
        rec = {k: r[k] for k in ("model", "task_id", "sample", "tokens", "correct")}
        rec.update({"behaviour": "backtracking", "judge_model": JUDGE_MODEL,
                    "temperature": TEMPERATURE, "max_tokens": MAX_OUT,
                    "prompt_version": PROMPT_VERSION, "prompt_sha": sha, **res})
        inst = p.parse(res.get("raw"), lines)
        c = p.COUNT_RE.search(res.get("raw") or "")
        rec.update({"judge_count": int(c.group(1)) if c else None,
                    "n_listed": len(inst), "n_verified": sum(d["verified"] for d in inst),
                    "count": sum(d["verified"] for d in inst) if c else None})
        return rec

    n = 0
    with open(a.out, "a") as fh, ThreadPoolExecutor(a.workers) as ex:
        for f in as_completed([ex.submit(one, r) for r in todo]):
            rec = f.result()
            fh.write(json.dumps(rec) + "\n"); fh.flush()
            n += 1
            if n % 25 == 0 or "error" in rec:
                print(f"  {n}/{len(todo)}" + (f"  ERROR {rec['error']}" if "error" in rec else ""),
                      flush=True)
    print(f"done -> {a.out}")


if __name__ == "__main__":
    main()
