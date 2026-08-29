"""
Benchmark open-source models on the tyrtleli/thinking-benchmark dataset via
OpenRouter, with each model PINNED to the provider you chose.

Notes:
  - OpenRouter otherwise sprays a model across providers with different caps /
    precision. We pin exactly what's in MODELS below (provider.only,
    allow_fallbacks=False, quantizations=[precision]) so nothing gets swapped.
  - No batch API for these, so requests are LIVE and concurrent (thread pool,
    full price).
  - One common --max-tokens cap for every model; a startup line flags any model
    whose provider cap is below it (so truncation bias is visible).

Grading / dataset handling / output schema match the other two scripts.

Usage:
    python benchmark_math_open_source.py --models all --n-samples 8 --max-tokens 40000
    python benchmark_math_open_source.py --models glm-5 kimi-k2

Requires OPENROUTER_API_KEY in the environment.
"""
import argparse
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from datasets import load_dataset
from openai import OpenAI

try:
    from sympy import simplify, sympify
    from sympy.parsing.latex import parse_latex
    _SYMPY_OK = True
except ImportError:
    _SYMPY_OK = False

ROOT = Path(__file__).parent
RESULTS_ROOT = ROOT / "results"
OPENROUTER_BASE = "https://openrouter.ai/api/v1"

DEFAULT_DATASET = "tyrtleli/thinking-benchmark"
DEFAULT_SPLIT = "test"
INSTRUCTIONS = (
    "Solve the problem step by step. End your response with your final answer "
    "inside \\boxed{}. The answer may be an integer, a fraction (e.g. "
    "\\frac{1}{2}), a closed-form expression with radicals, or a tuple/set."
)

# ----------------------------------------------------------------------------
# Your curated pins. `or_model` slugs are confirmed against openrouter.ai/models;
# `provider` slugs are OpenRouter routing ids. Edit freely.
# fields: label, series, or_model, provider, quant, provider_max, in$/M, out$/M
# ----------------------------------------------------------------------------
MODELS = [
    dict(label="DeepSeek V4 Pro 0813", series="deepseek-v4", or_model="deepseek/deepseek-v4-pro-0813",
         provider="novita", quant="fp8", provider_max=393_216, price_in=1.32, price_out=3.96),
    # DeepSeek V4 Flash removed: efficiency variant, not a frontier model.
    dict(label="DeepSeek V3.1 Terminus", series="deepseek-v3", or_model="deepseek/deepseek-v3.1-terminus",
         provider="atlas-cloud", quant="fp8", provider_max=65_536, price_in=0.30, price_out=0.95),
    dict(label="DeepSeek R1 0528", series="deepseek-r1", or_model="deepseek/deepseek-r1-0528",
         provider="siliconflow", quant="fp8", provider_max=163_800, price_in=0.70, price_out=2.50),
    # DeepSeek V3 (deepseek-chat) removed: non-reasoning model (no reasoning
    # params on OpenRouter) and hard-capped at ~16k everywhere.
    # Kimi K3 moved off DeepInfra (16k) to BaseTen fp8 (262k) so the cap doesn't truncate.
    dict(label="Kimi K3", series="kimi-k3", or_model="moonshotai/kimi-k3",
         provider="baseten", quant="fp8", provider_max=262_144, price_in=3.00, price_out=15.00),
    dict(label="Kimi K2.7 Code", series="kimi-k2", or_model="moonshotai/kimi-k2.7-code",
         provider="siliconflow", quant="fp8", provider_max=235_929, price_in=0.86, price_out=3.80),
    dict(label="Kimi K2.6", series="kimi-k2", or_model="moonshotai/kimi-k2.6",
         provider="crusoe", quant="bf16", provider_max=235_929, price_in=0.70, price_out=3.50),
    dict(label="Kimi K2.5", series="kimi-k2", or_model="moonshotai/kimi-k2.5",
         provider="streamlake", quant="fp8", provider_max=230_400, price_in=0.54, price_out=2.70),
    dict(label="Kimi K2 Thinking", series="kimi-k2", or_model="moonshotai/kimi-k2-thinking",
         provider="novita", quant="bf16", provider_max=100_352, price_in=0.60, price_out=2.50),
    dict(label="GLM 5.3", series="glm-5", or_model="z-ai/glm-5.3",
         provider="z-ai", quant="fp8", provider_max=131_072, price_in=1.40, price_out=4.40),
    dict(label="GLM 5.2", series="glm-5", or_model="z-ai/glm-5.2",
         provider="phala", quant="fp8", provider_max=131_072, price_in=1.26, price_out=3.00),
    dict(label="GLM 5.1", series="glm-5", or_model="z-ai/glm-5.1",
         provider="baidu", quant="fp8", provider_max=131_072, price_in=0.91, price_out=2.86),
    dict(label="GLM 5", series="glm-5", or_model="z-ai/glm-5",
         provider="streamlake", quant="fp8", provider_max=128_000, price_in=0.60, price_out=1.92),
    dict(label="GLM 4.7", series="glm-4", or_model="z-ai/glm-4.7",
         provider="novita", quant="fp8", provider_max=131_072, price_in=0.54, price_out=1.98),
    dict(label="GLM 4.6", series="glm-4", or_model="z-ai/glm-4.6",
         provider="novita", quant="bf16", provider_max=131_072, price_in=0.55, price_out=2.20),
    dict(label="GLM 4.5", series="glm-4", or_model="z-ai/glm-4.5",
         provider="z-ai", quant="fp8", provider_max=98_304, price_in=0.60, price_out=2.20),
]

# reasoning_effort is only exposed by these on OpenRouter; every other model is
# reasoning-on with NO effort knob (a comparability caveat vs the GPT/Opus runs,
# where all models take medium). We set medium where supported, else just force
# reasoning on. Edit the set / per-model "effort" as OpenRouter adds support.
_EFFORT_CAPABLE = {"DeepSeek V4 Pro 0813", "Kimi K3", "GLM 5.3", "GLM 5.2"}
for _m in MODELS:
    _m["effort"] = "medium" if _m["label"] in _EFFORT_CAPABLE else None


def provider_pref(m):
    pref = {"only": [m["provider"]], "allow_fallbacks": False}
    if m.get("quant"):
        pref["quantizations"] = [m["quant"]]
    return pref


# ======================= answer extraction + grading =======================
def _find_boxed(text):
    if not text:
        return None
    target, results, i = "\\boxed{", [], 0
    while True:
        idx = text.find(target, i)
        if idx == -1:
            break
        start, depth, j = idx + len(target), 1, idx + len(target)
        while j < len(text) and depth > 0:
            depth += 1 if text[j] == "{" else (-1 if text[j] == "}" else 0)
            j += 1
        if depth == 0:
            results.append(text[start:j - 1])
        i = j if j > i else i + 1
    return results[-1].strip() if results else None


def _fallback_after_equals(text):
    if not text or "=" not in text:
        return None
    tail = text.rsplit("=", 1)[1].split("\n")[0].strip()
    tail = re.sub(r"[\s.!?,;:]+$", "", tail)
    return tail or None


def extract_boxed(text):
    b = _find_boxed(text)
    return b if b is not None else _fallback_after_equals(text)


def answer_in_boxed(text):
    return _find_boxed(text) is not None


_WS_RE = re.compile(r"\s+")


def normalize(s):
    if s is None:
        return None
    s = str(s).strip()
    if s.startswith("$") and s.endswith("$"):
        s = s[1:-1].strip()
    s = _WS_RE.sub("", s)
    for junk in ("\\!", "\\,", "\\;", "\\:", "\\left", "\\right"):
        s = s.replace(junk, "")
    for variant in ("\\dfrac", "\\tfrac", "\\cfrac", "\\sfrac"):
        s = s.replace(variant, "\\frac")
    s = re.sub(r"\\sqrt(\d|[a-zA-Z])", r"\\sqrt{\1}", s)
    return s.lower()


def _try_int(s):
    if s is None:
        return None
    s = str(s).lstrip("+").lstrip("0") or "0"
    if s.startswith("-"):
        s = "-" + (s[1:].lstrip("0") or "0")
    try:
        return int(s)
    except ValueError:
        return None


def _try_float(s):
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def _sympy_parse(s):
    if not _SYMPY_OK or s is None:
        return None
    s = str(s).strip()
    if s.startswith("$") and s.endswith("$"):
        s = s[1:-1].strip()
    if not s:
        return None
    for parser in (parse_latex, sympify):
        try:
            return parser(s)
        except Exception:
            continue
    return None


def _sympy_equivalent(extracted, gold):
    a, b = _sympy_parse(extracted), _sympy_parse(gold)
    if a is None or b is None:
        return None
    try:
        diff = simplify(a - b)
        if diff == 0:
            return True
        try:
            return abs(complex(diff.evalf())) < 1e-9
        except (TypeError, ValueError):
            return False
    except Exception:
        return None


def is_correct(extracted, gold):
    a, b = normalize(extracted), normalize(gold)
    if a is None or b is None:
        return False
    if a == b:
        return True
    ai, bi = _try_int(a), _try_int(b)
    if ai is not None and bi is not None:
        return ai == bi
    af, bf = _try_float(a), _try_float(b)
    if af is not None and bf is not None:
        return abs(af - bf) < 1e-9
    return bool(_sympy_equivalent(extracted, gold))


# ======================= live requests =======================
def one_request(client, m, problem, max_tokens, max_attempts=4):
    for attempt in range(1, max_attempts + 1):
        try:
            # medium effort where the model supports it; otherwise just ensure
            # reasoning is turned on (no effort knob available).
            reasoning = {"effort": m["effort"]} if m.get("effort") else {"enabled": True}
            resp = client.chat.completions.create(
                model=m["or_model"],
                messages=[{"role": "system", "content": INSTRUCTIONS},
                          {"role": "user", "content": problem}],
                max_tokens=max_tokens,
                extra_body={"provider": provider_pref(m), "reasoning": reasoning},
            )
            msg = resp.choices[0].message
            u = resp.usage
            det = getattr(u, "completion_tokens_details", None)
            reasoning_tok = (getattr(det, "reasoning_tokens", 0) or 0) if det else 0
            return {"text": msg.content or "",
                    "reasoning": getattr(msg, "reasoning", None) or "",  # full CoT trace
                    "input_tokens": u.prompt_tokens,
                    "output_tokens": u.completion_tokens, "reasoning_tokens": reasoning_tok,
                    "provider": getattr(resp, "provider", None)}
        except Exception as e:
            if attempt < max_attempts:
                time.sleep(2 ** attempt)
                continue
            return {"text": "", "reasoning": "", "input_tokens": 0, "output_tokens": 0,
                    "reasoning_tokens": 0, "provider": None, "error": f"{type(e).__name__}: {e}"}


def run_model(client, m, problems, n_samples, max_tokens, workers):
    tasks = [(row, s) for row in problems for s in range(n_samples)]
    results = {str(row["id"]): [None] * n_samples for row in problems}
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        fut = {ex.submit(one_request, client, m, row["problem"], max_tokens): (str(row["id"]), s)
               for row, s in tasks}
        for f in as_completed(fut):
            pid, s = fut[f]
            results[pid][s] = f.result()
            done += 1
            if done % 20 == 0 or done == len(tasks):
                print(f"    {m['label']}: {done}/{len(tasks)} requests", flush=True)

    rows_out = []
    for row in problems:
        samples = [s or {"text": "", "reasoning": "", "input_tokens": 0, "output_tokens": 0,
                         "reasoning_tokens": 0}
                   for s in results[str(row["id"])]]
        gold = str(row.get("answer") if "answer" in row else row.get("final_answer")).strip()
        extracted = [extract_boxed(s["text"]) for s in samples]
        correct = [is_correct(e, gold) for e in extracted]
        rows_out.append({
            "task_id": str(row["id"]), "source": row.get("source"),
            "domain": row.get("domain"), "difficulty": row.get("difficulty"),
            "difficulty_label": row.get("difficulty_label"), "gold_answer": gold,
            "extracted_answers": extracted, "answer_in_boxed": [answer_in_boxed(s["text"]) for s in samples],
            "response_texts": [s["text"] for s in samples],
            "reasoning_texts": [s["reasoning"] for s in samples],   # full CoT traces
            "correct": correct,
            "prompt_length_tokens": [s["input_tokens"] for s in samples],
            "total_completion_tokens": [s["output_tokens"] for s in samples],
            "trace_length_tokens": [s["output_tokens"] for s in samples],
            "thinking_tokens": [s["reasoning_tokens"] for s in samples],
            "answer_tokens": [max(s["output_tokens"] - s["reasoning_tokens"], 0) for s in samples],
            "response_chars": [len(s["text"]) for s in samples],
            "providers_used": [s.get("provider") for s in samples],
            "solved_at_least_once": any(correct),
        })
    return rows_out


# ======================= main =======================
def _slug(label):
    return re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")


def select_models(spec):
    if not spec or spec == ["all"]:
        return list(MODELS)
    want = set(spec)
    return [m for m in MODELS if m["series"] in want or m["label"] in want]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="*", default=["all"],
                    help="'all', series names (deepseek-v4/kimi-k2/glm-5/...), or exact labels.")
    ap.add_argument("--n-samples", type=int, default=8)
    ap.add_argument("--n-problems", type=int, default=None)
    ap.add_argument("--max-tokens", type=int, default=40000,
                    help="Common output cap; clamped down only where a provider's max is lower.")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--dataset", default=DEFAULT_DATASET)
    ap.add_argument("--split", default=DEFAULT_SPLIT)
    ap.add_argument("--tag", default=None)
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--problem-source", default="tyrtleli/thinking-benchmark-90")
    args = ap.parse_args()

    selected = select_models(args.models)
    if not selected:
        print(f"No models matched {args.models}. Series: {sorted({m['series'] for m in MODELS})}")
        return

    # Print the pins; flag any model whose provider cap is below the common cap.
    print(f"Pinned providers (common cap {args.max_tokens:,}):")
    for m in selected:
        cap = min(args.max_tokens, m["provider_max"])
        flag = f"  <-- provider max {m['provider_max']:,} < cap (TRUNCATES)" if cap < args.max_tokens else ""
        eff = f"effort={m['effort']}" if m.get("effort") else "effort=n/a"
        print(f"  {m['label']:24} {m['provider']:12} {m['quant'] or 'unknown':7} "
              f"cap={cap:>8,}  {eff:12}{flag}")

    print(f"\nResults root: {RESULTS_ROOT}  (one <model>_shallow_pass/ folder per model)")
    if not _SYMPY_OK:
        print("WARNING: sympy not importable — string+numeric grading only.")

    tag = args.tag or args.dataset.split("/")[-1].replace("-", "_")
    print(f"Loading {args.dataset} (split={args.split})...")
    problems = list(load_dataset(args.dataset, split=args.split))
    if args.n_problems is not None:
        problems = problems[:args.n_problems]
    if any(not p.get("problem") for p in problems):
        src = {str(r["id"]): r for r in load_dataset(args.problem_source, split=args.split)}
        for p in problems:
            s = src.get(str(p["id"]), {})
            if not p.get("problem"):
                p["problem"] = s.get("problem")
            if not p.get("answer") and not p.get("final_answer"):
                p["answer"] = s.get("answer") if "answer" in s else s.get("final_answer")
    print(f"  {len(problems)} problems")

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise SystemExit(
            "OPENROUTER_API_KEY not set in this shell.\n"
            "  It's defined in ~/.bash_profile, but zsh doesn't read that file. Fix with:\n"
            "    source ~/.bash_profile            # loads it into the CURRENT shell\n"
            "  then re-run. Verify first with:  echo ${OPENROUTER_API_KEY:+SET}\n"
            "  (Permanent fix: add the same `export OPENROUTER_API_KEY=...` line to ~/.zshrc)")
    client = OpenAI(base_url=OPENROUTER_BASE, api_key=api_key)

    for m in selected:
        cap = min(args.max_tokens, m["provider_max"])
        slug = _slug(m["label"])
        # One folder per model, mirroring the proprietary data/<model>_shallow_pass/ layout.
        model_dir = RESULTS_ROOT / f"{slug}_shallow_pass"
        model_dir.mkdir(parents=True, exist_ok=True)
        res_path = model_dir / f"{slug}_{tag}.json"                       # proprietary-schema results
        trace_path = model_dir / f"{slug}_{tag}_reasoning_traces.json"    # separate CoT traces
        existing = json.load(res_path.open()) if (res_path.exists() and not args.fresh) else []
        existing_traces = json.load(trace_path.open()) if (trace_path.exists() and not args.fresh) else []
        done_ids = {r["task_id"] for r in existing}
        todo = [p for p in problems if str(p["id"]) not in done_ids]
        print(f"\n=== {m['label']}  ({m['or_model']} @ {m['provider']}/{m['quant'] or 'unknown'}, "
              f"cap={cap:,})  {len(todo)} new / {len(problems)} ===")
        if not todo:
            print("  nothing new — skipping.")
            continue
        rows = run_model(client, m, todo, args.n_samples, cap, args.workers)
        # Split: results file matches the proprietary schema (no bulky traces);
        # a parallel file holds the full reasoning traces, joinable by task_id.
        new_res = [{k: v for k, v in r.items() if k != "reasoning_texts"} for r in rows]
        new_traces = [{"task_id": r["task_id"], "reasoning_texts": r["reasoning_texts"]} for r in rows]
        results, traces = existing + new_res, existing_traces + new_traces
        with res_path.open("w") as f:
            json.dump(results, f, indent=2)
        with trace_path.open("w") as f:
            json.dump(traces, f, indent=2)
        nc = sum(sum(r["correct"]) for r in results)
        nt = sum(len(r["correct"]) for r in results)
        print(f"  wrote {res_path.name} + {trace_path.name}  ({model_dir})  "
              f"accuracy {nc}/{nt} = {nc / max(1, nt):.1%}")

    print(f"\nAll done. Per-model folders under {RESULTS_ROOT}")


if __name__ == "__main__":
    main()
