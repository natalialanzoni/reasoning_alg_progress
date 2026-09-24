"""Count backtracking / verification steps in reasoning traces with an LLM judge.

WHAT THIS DOES
  For each trace: send the WHOLE chain-of-thought plus one Gandhi et al. prompt
  to the judge, read the <count> it returns, write one JSONL record. One call per
  trace per behaviour. Nothing is chunked, truncated, or summed.

WHICH TRACES
  The four models behind fig_mechanism (see load_traces.py):
    Scale      gpt-oss-20b -> gpt-oss-120b     Algorithm  GLM 5.2 -> GLM 5.3
  CoT only on both sides, 40 competition problems, k=8 -> 1,280 traces.

WHY WHOLE-TRACE, NOT CHUNKED
  The prompts ask the judge to COUNT occurrences, which requires seeing the whole
  chain -- you cannot tell a backtrack from a first attempt by looking at a
  fragment. Splitting the trace and summing over-counts ~5x: on a hand-counted
  trace with 2-3 genuine instances it returned 13, and the inflation scales with
  the number of pieces, i.e. with trace length. Since trace length is what this
  project measures, that would have produced a trend out of an artifact. Same
  failure for marker-anchored windows (14-18 on the same trace). See
  data/archive/llm_judge_abandoned/WHY_ARCHIVED.md.

WHY THIS JUDGE
  Twelve judges were run on the same full trace. gpt-4o-mini returns a constant 12
  regardless of input; gpt-4.1-mini, gemini-3.1-flash-lite and haiku-4.5 collapse
  toward 0; gpt-5-mini/nano emit unparsable replies; claude-opus-5 and
  claude-fable-5.1 REFUSE the task (Anthropic ToS on "reverse engineering or
  duplicating model outputs"). Only sonnet-4.5 and gemini-2.5-flash matched a hand
  count, and gemini-2.5-flash is ~10x cheaper.

USAGE
  python code/llm_judge/judge_traces.py --estimate     # volume + cost, no calls
  python code/llm_judge/judge_traces.py --show-one     # print a real payload
  python code/llm_judge/judge_traces.py --limit 6 --send   # pilot (spread over problems)
  python code/llm_judge/judge_traces.py --send            # full run (~$7, ~40 min)
  python code/llm_judge/behaviour_table.py --tex paper_figs/table_behaviours.tex

  Needs ERA_OPENROUTER_V2 (or OPENROUTER_API_KEY) in the environment.
  NOTHING IS SENT without --send.
"""
import argparse
import hashlib
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from load_traces import load_all, MODEL_ORDER          # noqa: E402

JUDGE_MODEL = "google/gemini-2.5-flash"   # $0.30/M in, $2.50/M out (2026-09-21)
TEMPERATURE = 0
MAX_OUT = 24000          # The template puts "## Thoughts" FIRST and <count> LAST, so a
                        # verbose judge is cut off before it emits the count -- an
                        # unparsable record, not a zero. Measured: 600 lost 7/96 replies
                        # (all the longest-trace model), 2000 lost 81/766 on Gemini,
                        # which enumerates at length; 4000 still lost 80/2560 and those
                        # drops were the LONGEST traces (median 33,620 tokens vs 6,561
                        # kept) -- a bias in exactly the variable under study. 12000
                        # clears it. Costs nothing for replies that finish early.
OPENROUTER = "https://openrouter.ai/api/v1"
OUT_DIR = os.path.join(HERE, "out")
# Gandhi et al. define four behaviours; we run only these two. The other two
# templates are not in this folder because we never used them -- fetch them from
# kanishkg/cognitive-behaviors if you want them.
BEHAVIOURS = ("backtracking", "verification")

# Whitespace-tolerant on purpose: the templates write "<count> [1/2/...] </count>"
# with spaces, so upstream's own r"<count>(\d+)</count>" would miss a spaced count
# and record a silent zero.
COUNT_RE = re.compile(r"<count>\s*(\d+)\s*</count>", re.I)

# The one documented edit to the upstream templates: line 2 was
#   "You will be provided with text from the internet."
# now reads
#   "You will be provided with the reasoning trace of a language model solving a
#    competition mathematics problem."
# Everything else is verbatim. State this in the appendix. Each record carries the
# template's sha256 so the claim is checkable.
EDIT_NOTE = ("line 2 reframed from 'text from the internet' to 'the reasoning trace of a "
             "language model solving a competition mathematics problem'; rest verbatim")


# MAX_OUT was raised 12000 -> 24000 for v3. The v3 format section originally let
# the judge walk long traces sentence by sentence, emitting thousands of entries
# reading "this is a verification"; 28/1280 never reached <count>, and the loss was
# concentrated in the longest traces (14.4% of GLM 5.3's tokens against 2.6% of GLM
# 5.2's -- i.e. biased along the algorithm lever). The format section now forbids
# listing non-instances, which cut typical output to 200-4,600 tokens.
#
# Prompt version is PER BEHAVIOUR, because they were settled separately.
#   verification v0 -- Gandhi et al.'s template + the one-line domain edit. Manual
#                      review found it sound, so it was never re-run.
#   backtracking v2 -- rewritten after review. v0 counted self-interruption as
#                      abandonment; a v1 attempt then undercounted. v2 tests
#                      whether the line of attack is CARRIED FORWARD, which is
#                      visible on the page. See README.
#   backtracking v3 -- IN USE. v2 undercounted:
#                      it refused brief ideas as "too undeveloped". v3 counts a
#                      candidate however briefly raised, separates required case
#                      eliminations from guessed ones, and counts recomputed wrong
#                      values. Pilot and rationale in
#                      for_RA_review/v3_backtracking/.
PROMPT_VERSION = {"backtracking": "v3", "verification": "v0"}


def _template(behaviour, version=None):
    p = os.path.join(HERE, f"{behaviour}_{version or PROMPT_VERSION[behaviour]}.txt")
    if not os.path.exists(p):
        raise SystemExit(f"no prompt template for {behaviour!r} at {p}")
    return open(p).read()


def template_sha(behaviour, version=None):
    return hashlib.sha256(_template(behaviour, version).encode()).hexdigest()[:16]


def build_messages(behaviour, trace, version=None):
    """One user turn, NO system message -- upstream's relabel_pretrain.py sends the
    formatted template as the only message, and adding a system turn would be a
    second undocumented change to the instrument."""
    t = _template(behaviour, version)
    if "{response}" not in t:
        raise SystemExit(f"{behaviour}_v0.txt lost its {{response}} placeholder")
    # .replace not .format: a trace containing { or } would break .format
    return [{"role": "user", "content": t.replace("{response}", trace)}]


def judge_one(client, behaviour, trace, model, version=None):
    r = client.chat.completions.create(
        model=model, messages=build_messages(behaviour, trace, version),
        max_tokens=MAX_OUT, temperature=TEMPERATURE)
    txt = r.choices[0].message.content or ""
    m = COUNT_RE.search(txt)
    return {"count": int(m.group(1)) if m else None, "raw": txt,
            "in_tok": r.usage.prompt_tokens, "out_tok": r.usage.completion_tokens}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--judge-model", default=JUDGE_MODEL)
    ap.add_argument("--prompt-version", default=None, choices=("v0", "v2", "v3"),
                    help="override the per-behaviour default in PROMPT_VERSION")
    ap.add_argument("--models", nargs="*", default=MODEL_ORDER)
    ap.add_argument("--behaviours", nargs="*", default=["backtracking", "verification"],
                    choices=list(BEHAVIOURS))
    ap.add_argument("--limit", type=int, default=None,
                    help="N traces per model for piloting, SPREAD ACROSS PROBLEMS. Taking "
                         "the first N would take N samples of ONE problem.")
    ap.add_argument("--limit-samples", type=int, default=1)
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--estimate", action="store_true")
    ap.add_argument("--show-one", action="store_true")
    ap.add_argument("--send", action="store_true", help="REQUIRED to contact OpenRouter")
    ap.add_argument("--out", default=os.path.join(OUT_DIR, "judge_whole_gemini.jsonl"))
    a = ap.parse_args()

    rows = load_all(a.models)
    if a.limit:
        keep = []
        for m in a.models:
            by_task = {}
            for r in (x for x in rows if x["model"] == m):
                by_task.setdefault(r["task_id"], []).append(r)
            for tid in sorted(by_task)[:a.limit]:
                keep += sorted(by_task[tid], key=lambda r: r["sample"])[:a.limit_samples]
        rows = keep
        print(f"--limit {a.limit}: {len(rows)} traces over "
              f"{len({r['task_id'] for r in rows})} distinct problems")

    jobs = [{**{k: r[k] for k in ("model", "task_id", "sample", "tokens", "correct")},
             "behaviour": b, "cot": r["cot"]}
            for r in rows for b in a.behaviours]
    print(f"traces {len(rows)}   behaviours {a.behaviours}   judge calls {len(jobs)}")

    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        n = sum(len(enc.encode(build_messages(j["behaviour"], j["cot"],
                                              a.prompt_version)[0]["content"]))
                for j in jobs[:150]) / min(150, len(jobs))
        tot = n * len(jobs)
        print(f"  mean prompt ~{n:,.0f} tok  ->  ~{tot/1e6:.1f}M input tokens")
        print(f"  cost at gemini-2.5-flash ($0.30/M in, $2.50/M out, ~300 out each): "
              f"${tot/1e6*0.30 + len(jobs)*300/1e6*2.50:,.2f}")
    except Exception as e:
        print(f"  (cost estimate unavailable: {type(e).__name__})")

    if a.show_one:
        j = jobs[0]
        c = build_messages(j["behaviour"], j["cot"], a.prompt_version)[0]["content"]
        print("\n" + "=" * 70)
        print(f"ONE REAL PAYLOAD  {j['model']} {j['task_id']} sample={j['sample']} "
              f"behaviour={j['behaviour']}")
        print("=" * 70)
        print(c if len(c) < 4000 else c[:2000] + f"\n[... {len(c)-4000:,} chars ...]\n" + c[-2000:])

    if not a.send:
        print("\nDRY RUN -- nothing sent. Re-run with --send.")
        return

    key = os.environ.get("ERA_OPENROUTER_V2") or os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise SystemExit("no OpenRouter key (ERA_OPENROUTER_V2 / OPENROUTER_API_KEY)")
    from openai import OpenAI
    client = OpenAI(base_url=OPENROUTER, api_key=key, timeout=600.0, max_retries=5)

    os.makedirs(OUT_DIR, exist_ok=True)
    done = set()
    if os.path.exists(a.out):
        for line in open(a.out):
            try:
                d = json.loads(line)
                done.add((d["model"], d["task_id"], d["sample"], d["behaviour"]))
            except Exception:
                pass
        print(f"resuming: {len(done)} already judged")
    todo = [j for j in jobs
            if (j["model"], j["task_id"], j["sample"], j["behaviour"]) not in done]
    print(f"sending {len(todo)} calls to {a.judge_model} ...")

    n = 0
    with open(a.out, "a") as fh, ThreadPoolExecutor(max_workers=a.workers) as ex:
        fut = {ex.submit(judge_one, client, j["behaviour"], j["cot"], a.judge_model,
                         a.prompt_version): j for j in todo}
        for f in as_completed(fut):
            j = fut[f]
            rec = {k: j[k] for k in ("model", "task_id", "sample", "behaviour",
                                     "tokens", "correct")}
            rec.update({"judge_model": a.judge_model, "temperature": TEMPERATURE,
                        "prompt_version": a.prompt_version or PROMPT_VERSION[j["behaviour"]],
                        "prompt_sha": template_sha(j["behaviour"], a.prompt_version),
                        "prompt_edit": EDIT_NOTE})
            try:
                rec.update(f.result())
            except Exception as e:
                rec["error"] = f"{type(e).__name__}: {e}"[:200]
            fh.write(json.dumps(rec) + "\n"); fh.flush()
            n += 1
            if n % 100 == 0:
                print(f"  {n}/{len(todo)}", flush=True)
    print(f"done -> {a.out}")


if __name__ == "__main__":
    main()
