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
    # The Apr-2026 V4 Pro launch build -- the frontier point on the DeepSeek
    # timeline (R1-0528 -> V3.1 Terminus -> V3.2 -> V4 Pro).
    # EFFORT: DeepSeek has exactly three levels -- low, high, max. OpenRouter's
    # API accepts seven (max|xhigh|high|medium|low|minimal|none; anything else is
    # a 400, verified 2026-09-17) and routes the rest INTERNALLY down to those
    # three. So sending "medium" here would be silently remapped -- the same trap
    # that invalidated the GLM 5.2/5.3 sweep. Send only low/high/max, which are
    # native and pass through unchanged.
    # SILICONFLOW FOR THE WHOLE FAMILY: all four DeepSeek models below are pinned
    # to SiliconFlow at fp8 so provider is not a confound in the within-family
    # comparison. fp8 is the best quantization any OpenRouter provider offers for
    # these (the alternatives are fp8 or fp4, never bf16), and SiliconFlow's
    # advertised max_completion is >= 147,456 on every one, far above our 40k cap.
    # This matters because we set no temperature/top_p/seed, so provider sampling
    # defaults apply -- one provider means one set of defaults across the series.
    dict(label="DeepSeek V4 Pro", series="deepseek-v4", or_model="deepseek/deepseek-v4-pro",
         provider="siliconflow", quant="fp8", provider_max=393_216, price_in=1.50, price_out=3.14),
    # NEW DATA, NOT the same model as "DeepSeek V4 Pro" above. Served by DeepSeek's
    # OWN API, where `deepseek-v4-pro` is a ROLLING pointer to the latest GA build
    # (release note 2026-08-13: "simply set the model name to deepseek-v4-pro to use
    # the latest version"), i.e. the 0813 GA build -- while OpenRouter's
    # `deepseek/deepseek-v4-pro` is a fixed 2026-04-24 listing. Keep the two apart.
    # Why it exists: SiliconFlow truncated ~11% of V4 trials at 32,768 despite a
    # 40,000 request, varying PER REQUEST. Direct has one backend, and a measured
    # 39,946-token completion with finish_reason "stop" -- the cap behaves.
    # provider/quant are unused on this path (no routing); provider_max is DeepSeek's
    # documented 64K output ceiling.
    dict(label="DeepSeek V4 Pro GA", series="deepseek-v4-ga", or_model="deepseek-v4-pro",
         api="deepseek", provider="deepseek-direct", quant=None, provider_max=65_536,
         price_in=0.28, price_out=0.42),
    dict(label="DeepSeek V4 Pro 0813", series="deepseek-v4", or_model="deepseek/deepseek-v4-pro-0813",
         provider="novita", quant="fp8", provider_max=393_216, price_in=1.32, price_out=3.96),
    # DeepSeek V4 Flash removed: efficiency variant, not a frontier model.
    # V3.2 (Dec 2025). The earlier run of this model was pinned to a provider that
    # imposed a hard 16,384-token ceiling (39% of trials pinned there), which is why
    # the top-level README excludes V3.2 from length analyses. SiliconFlow advertises
    # 147,456, so a fresh run sits under the common 40k cap like everything else.
    # Hybrid thinking model: reasoning is toggled, so verify reasoning_tokens > 0.
    dict(label="DeepSeek V3.2", series="deepseek-v3", or_model="deepseek/deepseek-v3.2",
         provider="siliconflow", quant="fp8", provider_max=147_456, price_in=0.26, price_out=0.42),
    dict(label="DeepSeek V3.1 Terminus", series="deepseek-v3", or_model="deepseek/deepseek-v3.1-terminus",
         provider="siliconflow", quant="fp8", provider_max=147_456, price_in=0.27, price_out=1.00),
    dict(label="DeepSeek R1 0528", series="deepseek-r1", or_model="deepseek/deepseek-r1-0528",
         provider="siliconflow", quant="fp8", provider_max=147_456, price_in=0.50, price_out=2.18),
    # DeepSeek V3 (deepseek-chat) removed: non-reasoning model (no reasoning
    # params on OpenRouter) and hard-capped at ~16k everywhere.
    # Kimi K3 moved off DeepInfra (16k) to BaseTen fp8 (262k) so the cap doesn't truncate.
    dict(label="Kimi K3", series="kimi-k3", or_model="moonshotai/kimi-k3",
         provider="baseten", quant="fp8", provider_max=262_144, price_in=3.00, price_out=15.00),
    dict(label="Kimi K2.7 Code", series="kimi-k2", or_model="moonshotai/kimi-k2.7-code",
         provider="siliconflow", quant="fp8", provider_max=235_929, price_in=0.86, price_out=3.80),
    dict(label="Kimi K2.6", series="kimi-k2", or_model="moonshotai/kimi-k2.6",
         provider="crusoe", quant="bf16", provider_max=235_929, price_in=0.70, price_out=3.50),
    # Repinned from streamlake: it imposed a hard 32,768-token output ceiling
    # (27% of k=8 trials pinned there, all graded wrong) despite advertising more,
    # and is no longer a listed endpoint for this model. Phala advertises 235,929.
    # quant left None: no current k2.5 endpoint advertises fp8, and a quantizations
    # pin would fail to route. int4/fp4 providers avoided deliberately.
    dict(label="Kimi K2.5", series="kimi-k2", or_model="moonshotai/kimi-k2.5",
         provider="phala", quant=None, provider_max=235_929, price_in=0.54, price_out=2.70),
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

# Per-model reasoning effort. MUST be a value the model actually accepts -- an
# unsupported value is NOT an error you will see. Vendors silently remap it, so
# the run looks clean while measuring a level you did not choose.
#
# This bit us: the 2026-09-05/06 GLM run sent "medium" to GLM 5.2 and 5.3, and
# neither model has a "medium". Per Z.AI's docs (docs.z.ai/guides/capabilities/
# thinking) GLM 5.2 accepts max/xhigh/high/medium/low/minimal/none but maps
# low and medium onto HIGH, while GLM 5.3 accepts only max/high/low and errors
# on anything else -- yet that run logged zero errors, so OpenRouter had already
# remapped it upstream ("maps your requested effort to the nearest supported
# level"). The two models therefore ran at different, unrecorded levels and are
# not comparable. See data/hard_but_doable_10q_k32/GLM_ANALYSIS_NOTES.md.
#
# "high" is used below because it is natively supported by BOTH GLM 5.2 and 5.3,
# so it is a genuinely matched setting. None => send {"enabled": True}, which is
# the only reasoning control the pre-5.2 GLMs expose at all.
_EFFORT = {
    "GLM 5.3": "high",   # accepts max/high/low only
    "GLM 5.2": "high",   # accepts the full ladder, but low/medium collapse to high
    # Same bug, same fix: neither of these has a "medium" either.
    "Kimi K3": "high",              # platform.kimi.ai: low/high/max, default max
    "DeepSeek V4 Pro 0813": "high", # api-docs.deepseek.com: high/max; low+medium -> high
    # Three native levels: low/high/max (default high). Everything else OpenRouter
    # accepts is remapped onto these internally -- see the MODELS comment above.
    "DeepSeek V4 Pro": "high",
    # Same three levels, confirmed by DeepSeek's 2026-08-13 release note:
    # "low / high / max ... use low for simple tasks, high for daily Agent tasks,
    # and max for more complex scenarios."
    "DeepSeek V4 Pro GA": "high",
}
# "high" is the one level natively supported by all four of these models, which is
# what makes it the matched setting. Every other model here exposes no effort knob
# at all and gets {"enabled": True}.
for _m in MODELS:
    _m["effort"] = _EFFORT.get(_m["label"])


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
            if m.get("api") == "deepseek":
                # DeepSeek's own API: no provider routing (one backend, so
                # max_tokens means one thing on every request -- the reason for
                # using it), effort is a TOP-LEVEL reasoning_effort, and the CoT
                # comes back as reasoning_content rather than reasoning.
                kw = {"reasoning_effort": m["effort"]} if m.get("effort") else {}
                resp = client.chat.completions.create(
                    model=m["or_model"],
                    messages=[{"role": "system", "content": INSTRUCTIONS},
                              {"role": "user", "content": problem}],
                    max_tokens=max_tokens, **kw)
                reasoning = kw or {"reasoning_effort": None}
            else:
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
                    # DeepSeek direct returns reasoning_content; OpenRouter returns reasoning.
                    "reasoning": (getattr(msg, "reasoning", None)
                                  or getattr(msg, "reasoning_content", None) or ""),
                    "input_tokens": u.prompt_tokens,
                    "output_tokens": u.completion_tokens, "reasoning_tokens": reasoning_tok,
                    # DeepSeek direct has no provider field; system_fingerprint is
                    # the only build identifier, and "deepseek-v4-pro" there is a
                    # ROLLING pointer to the latest GA build (release note 2026-08-13).
                    "provider": getattr(resp, "provider", None) or m.get("api"),
                    "fingerprint": getattr(resp, "system_fingerprint", None),
                    # recorded so a run is self-documenting: gen_id can be replayed
                    # against GET /api/v1/generation?id=... and reasoning_sent shows
                    # what we asked for (vendors may silently remap it -- see _EFFORT)
                    "gen_id": getattr(resp, "id", None),
                    "reasoning_sent": reasoning,
                    # model_served is the RESOLVED snapshot (we may ask for
                    # "deepseek/deepseek-v3.2" and be served "...-20251201"), so
                    # mid-study snapshot drift is visible. finish_reason == "length"
                    # is truncation as a fact rather than inferred from
                    # output_tokens == cap.
                    "model_served": getattr(resp, "model", None),
                    "finish_reason": getattr(resp.choices[0], "finish_reason", None)}
        except Exception as e:
            if attempt < max_attempts:
                time.sleep(2 ** attempt)
                continue
            return {"text": "", "reasoning": "", "input_tokens": 0, "output_tokens": 0,
                    "reasoning_tokens": 0, "provider": None, "gen_id": None,
                    "reasoning_sent": reasoning, "model_served": None,
                    "fingerprint": None,
                    "finish_reason": None, "error": f"{type(e).__name__}: {e}"}


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
            "generation_ids": [s.get("gen_id") for s in samples],
            "reasoning_sent": [s.get("reasoning_sent") for s in samples],
            "models_served": [s.get("model_served") for s in samples],
            "fingerprints": [s.get("fingerprint") for s in samples],
            "finish_reasons": [s.get("finish_reason") for s in samples],
            "errors": [s.get("error") for s in samples],  # None when the call succeeded
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
    ap.add_argument("--solutions-only", action="store_true",
                    help="Keep only problems that have canonical solutions. On "
                         "thinking-benchmark-90 this is the 45-problem analysis "
                         "sample (2 of the 47 rows have solution_count 0 and are "
                         "excluded from every figure). Unlike --n-problems, which "
                         "slices the first N rows by position, this selects the "
                         "right set.")
    ap.add_argument("--effort", default=None,
                    help="Override the per-model _EFFORT level (low/high/max/...). "
                         "Applies ONLY to models that have an effort entry -- models "
                         "with no knob keep {'enabled': True}. The value lands in the "
                         "output filename, so two efforts never collide.")
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

    # --effort overrides the curated _EFFORT level. Only models that already have
    # an effort entry are touched: sending an effort to a model with no knob is
    # exactly the silent-remap bug this map exists to prevent.
    if args.effort:
        touched, skipped = [], []
        for m in selected:
            if m.get("effort"):
                m["effort"] = args.effort; touched.append(m["label"])
            else:
                skipped.append(m["label"])
        if not touched:
            raise SystemExit(f"--effort {args.effort!r} given, but none of the selected "
                             f"models has an effort knob: {skipped}")
        print(f"Effort override -> {args.effort!r} for: {', '.join(touched)}")
        if skipped:
            print(f"  (no effort knob, left at {{'enabled': True}}: {', '.join(skipped)})")
        # Effort MUST be in the filename. Without it a second run at a different
        # level resumes off the first one's file, reports "nothing new -- skipping",
        # and silently produces no data.
        tag = f"{tag}_{args.effort}"
    print(f"Loading {args.dataset} (split={args.split})...")
    problems = list(load_dataset(args.dataset, split=args.split))
    if args.solutions_only:
        before = len(problems)
        problems = [p for p in problems if p.get("solutions")]
        print(f"  --solutions-only: {before} -> {len(problems)} problems "
              f"(dropped {before - len(problems)} without canonical solutions)")
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

    # ERA_OPENROUTER_V2 wins when both are set: it is the funded key, and a sweep
    # that dies mid-model on an exhausted key loses everything in flight (results
    # are written only when a model completes). Which one was used is printed, and
    # recorded in the runconfig as key_env -- never the key itself.
    key_env = next((k for k in ("ERA_OPENROUTER_V2", "OPENROUTER_API_KEY")
                    if os.environ.get(k)), None)
    api_key = os.environ.get(key_env) if key_env else None
    if not api_key:
        raise SystemExit(
            "No OpenRouter key in this shell (looked for ERA_OPENROUTER_V2, then\n"
            "  OPENROUTER_API_KEY). They're defined in ~/.bash_profile, which zsh does\n"
            "  not read. Fix with:\n"
            "    source ~/.bash_profile            # loads it into the CURRENT shell\n"
            "  then re-run. Verify first with:  echo ${ERA_OPENROUTER_V2:+SET}\n"
            "  (Permanent fix: add the same `export ...` line to ~/.zshrc)")
    print(f"Using API key from ${key_env}")
    # timeout must cover a full 40k-token generation (~800s at slow providers).
    # Requests are NOT streamed (no stream=True below), so the read timeout spans
    # the ENTIRE generation -- the first byte arrives only when the model is done.
    # Do not lower it on the theory that a silent socket is a dead one; that logic
    # only holds for streaming, and at 240s it aborts every long trace.
    # max_retries=5: providers (baseten especially) return 429s under concurrency.
    # The SDK honors Retry-After and backs off properly; one_request's own 2/4/8s
    # sleeps are far too short for a rate-limit cooldown. Setting this to 0 raised
    # kimi-k3's failed requests from 115 to 174 -- do not disable it.
    client = OpenAI(base_url=OPENROUTER_BASE, api_key=api_key,
                    timeout=900.0, max_retries=5)

    # Models on DeepSeek's own API need a different base_url and key. Built lazily
    # so an OpenRouter-only run never requires DEEPSEEK_API to be set.
    ds_client = None
    if any(m.get("api") == "deepseek" for m in selected):
        ds_key = os.environ.get("DEEPSEEK_API") or os.environ.get("DEEPSEEK_API_KEY")
        if not ds_key:
            raise SystemExit("DEEPSEEK_API not set, but a selected model uses the "
                             "DeepSeek API directly. source ~/.bashrc first.")
        ds_client = OpenAI(base_url="https://api.deepseek.com", api_key=ds_key,
                           timeout=1800.0, max_retries=5)
        print("DeepSeek direct API client ready (base_url=https://api.deepseek.com)")

    for m in selected:
        cap = min(args.max_tokens, m["provider_max"])
        slug = _slug(m["label"])
        # One folder per model, mirroring the proprietary data/<model>_shallow_pass/ layout.
        model_dir = RESULTS_ROOT / f"{slug}_shallow_pass"
        model_dir.mkdir(parents=True, exist_ok=True)
        # runconfig: what this run ASKED for, next to what it got. The filename
        # asserts a setting; this proves it.
        runcfg = model_dir / f"{slug}_{tag}_runconfig.json"
        runcfg.write_text(json.dumps({
            "run_started": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "label": m["label"], "or_model": m["or_model"],
            "api": m.get("api", "openrouter"),
            "base_url": ("https://api.deepseek.com" if m.get("api") == "deepseek"
                         else OPENROUTER_BASE),
            "provider_pin": None if m.get("api") == "deepseek" else provider_pref(m),
            "reasoning_sent": (({"reasoning_effort": m["effort"]} if m.get("effort") else {})
                               if m.get("api") == "deepseek"
                               else ({"effort": m["effort"]} if m.get("effort")
                                     else {"enabled": True})),
            "effort_override": args.effort,
            "max_tokens_requested": args.max_tokens, "cap_applied": cap,
            "key_env": "DEEPSEEK_API" if m.get("api") == "deepseek" else key_env,
            "n_samples": args.n_samples, "dataset": args.dataset, "split": args.split,
            "n_problems": len(problems), "tag": tag,
        }, indent=2) + "\n")

        res_path = model_dir / f"{slug}_{tag}.json"                       # proprietary-schema results
        trace_path = model_dir / f"{slug}_{tag}_reasoning_traces.json"    # separate CoT traces
        existing = json.load(res_path.open()) if (res_path.exists() and not args.fresh) else []
        existing_traces = json.load(trace_path.open()) if (trace_path.exists() and not args.fresh) else []
        # Self-healing resume: a problem counts as done ONLY if every trial has
        # tokens > 0. Failed/partial ones (0 tokens, e.g. a killed run or a 402)
        # are dropped from existing and re-run — no manual cleanup needed.
        def _done(r):
            tc = r.get("total_completion_tokens") or []
            return len(tc) > 0 and all(t > 0 for t in tc)
        done_ids = {r["task_id"] for r in existing if _done(r)}
        existing = [r for r in existing if r["task_id"] in done_ids]
        existing_traces = [r for r in existing_traces if r["task_id"] in done_ids]
        todo = [p for p in problems if str(p["id"]) not in done_ids]
        print(f"\n=== {m['label']}  ({m['or_model']} @ {m['provider']}/{m['quant'] or 'unknown'}, "
              f"cap={cap:,})  {len(todo)} new / {len(problems)} ===")
        if not todo:
            print("  nothing new — skipping.")
            continue
        rows = run_model(ds_client if m.get("api") == "deepseek" else client,
                         m, todo, args.n_samples, cap, args.workers)
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
