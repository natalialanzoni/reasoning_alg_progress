"""Fingerprint what a given reasoning_effort setting actually buys, per model.

An unsupported effort value is NOT an error you will see -- vendors silently remap
it. This sends the same prompt/pins/cap as benchmark_math_open_source.py across
every effort setting a model exposes and records reasoning_tokens + generation id,
so you can tell which level a past run really received.

Usage: python code/effort_probe.py problems.json out.json
  where problems.json is {task_id: problem_text}

Run 2026-09-14 against GLM 5.2 (phala/fp8) and GLM 5.3 (z-ai/fp8), 40 requests,
0 errors. Medians (reasoning tokens, 2 problems x 2 samples per cell):

    setting    GLM 5.2   GLM 5.3   ratio
    low          9,007       652   13.8x
    high        12,643     1,123   11.3x
    max         24,546    14,268    1.7x
    enabled     10,756     7,271    1.5x

Conclusions: (1) `enabled: true` resolves to the model's own default near `max`,
NOT to medium as OpenRouter's docs state; (2) GLM 5.3's ladder is stretched --
low/high are shallow, max jumps ~10x. n=2 per cell, so only order-of-magnitude
gaps are trustworthy. Raw output of that run was not retained; see
data/hard_but_doable_10q_k32/GLM_ANALYSIS_NOTES.md for how it was used.
"""
import json, os, sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from openai import OpenAI

INSTRUCTIONS = (
    "Solve the problem step by step. End your response with your final answer "
    "inside \\boxed{}. The answer may be an integer, a fraction (e.g. "
    "\\frac{1}{2}), a closed-form expression with radicals, or a tuple/set.")

MODELS = [dict(label="GLM 5.2", or_model="z-ai/glm-5.2", provider="phala", quant="fp8"),
          dict(label="GLM 5.3", or_model="z-ai/glm-5.3", provider="z-ai",  quant="fp8")]
CONDS = [("medium", {"effort": "medium"}),   # invalid on both -- what the old run sent
         ("low",    {"effort": "low"}),
         ("high",   {"effort": "high"}),
         ("max",    {"effort": "max"}),
         ("enabled", {"enabled": True})]
N_SAMPLES = 2
MAX_TOKENS = 40_000

client = OpenAI(base_url="https://openrouter.ai/api/v1",
                api_key=os.environ["OPENROUTER_API_KEY"])


def run(m, cond_label, reasoning, pid, ptext, s):
    pref = {"only": [m["provider"]], "allow_fallbacks": False, "quantizations": [m["quant"]]}
    try:
        r = client.chat.completions.create(
            model=m["or_model"],
            messages=[{"role": "system", "content": INSTRUCTIONS},
                      {"role": "user", "content": ptext}],
            max_tokens=MAX_TOKENS,
            extra_body={"provider": pref, "reasoning": reasoning})
        u = r.usage
        det = getattr(u, "completion_tokens_details", None)
        rt = (getattr(det, "reasoning_tokens", 0) or 0) if det else 0
        return dict(model=m["label"], cond=cond_label, task=pid, sample=s,
                    reasoning_tokens=rt, output_tokens=u.completion_tokens,
                    provider=getattr(r, "provider", None), gen_id=getattr(r, "id", None),
                    error=None)
    except Exception as e:
        return dict(model=m["label"], cond=cond_label, task=pid, sample=s,
                    reasoning_tokens=None, output_tokens=None, provider=None,
                    gen_id=None, error=f"{type(e).__name__}: {e}")


def main():
    problems = json.load(open(sys.argv[1]))
    jobs = [(m, cl, rz, pid, ptext, s)
            for m in MODELS for cl, rz in CONDS
            for pid, ptext in problems.items() for s in range(N_SAMPLES)]
    print(f"dispatching {len(jobs)} requests", flush=True)
    out, done = [], 0
    with ThreadPoolExecutor(max_workers=10) as ex:
        for f in as_completed([ex.submit(run, *j) for j in jobs]):
            out.append(f.result()); done += 1
            if done % 10 == 0 or done == len(jobs):
                print(f"  {done}/{len(jobs)}", flush=True)
    json.dump(out, open(sys.argv[2], "w"), indent=2)
    print("wrote", sys.argv[2])


if __name__ == "__main__":
    main()
