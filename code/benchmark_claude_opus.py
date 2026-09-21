"""
Benchmark Claude Opus models on the tyrtleli/thinking-benchmark dataset
via the Anthropic Message Batches API (50% cheaper than live).

This is the Claude counterpart to benchmark_math_dist.py (which targets
OpenAI reasoning models via the OpenAI Batch API). The two scripts share
CLI shape, dataset handling, resume/seed-from logic, and answer-matching
code, but differ in every provider-specific detail:

  - OpenAI's Responses Batch API needs a file upload before batch
    submission; Anthropic's Message Batches API takes requests inline.
  - OpenAI's "reasoning.effort" maps to Anthropic's "output_config.effort"
    (on adaptive-thinking models) or a "thinking.budget_tokens" fraction
    (on claude-opus-4-5, which predates adaptive thinking).
  - OpenAI's usage.output_tokens_details.reasoning_tokens has a direct
    Anthropic equivalent: usage.output_tokens_details.thinking_tokens,
    present on both live and batch Messages API responses. (The raw
    chain-of-thought text itself is still hidden -- thinking content
    blocks come back empty or summarized -- but the exact token COUNT
    is reported regardless of whether the text is.) answer_tokens is
    derived as total_output_tokens - thinking_tokens.

Usage:
    python benchmark_claude_opus.py --model claude-opus-5 --effort medium
    python benchmark_claude_opus.py --model claude-opus-4-5 --effort high \
        --dataset tyrtleli/thinking-benchmark-hard-but-doable-10 --n-samples 32
"""
import argparse
import json
import re
import time
from datetime import datetime
from pathlib import Path

import anthropic
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request
from datasets import load_dataset

try:
    from sympy import simplify, sympify
    from sympy.parsing.latex import parse_latex
    _SYMPY_OK = True
except ImportError:
    _SYMPY_OK = False

ROOT = Path(__file__).parent
RESULTS_ROOT = ROOT / "results"

DEFAULT_DATASET = "tyrtleli/thinking-benchmark"
DEFAULT_SPLIT = "test"

INSTRUCTIONS = (
    "Solve the problem step by step. End your response with your final answer "
    "inside \\boxed{}. The answer may be an integer, a fraction (e.g. "
    "\\frac{1}{2}), a closed-form expression with radicals, or a tuple/set."
)

# Per-model thinking configuration.
#   "adaptive" models: thinking={"type": "adaptive"}, output_config.effort
#     controls depth (low/medium/high/xhigh/max, except opus-4-6 which caps
#     at "max" -- no "xhigh").
#   "budget" models (claude-opus-4-5 predates adaptive thinking): thinking=
#     {"type": "enabled", "budget_tokens": N}, where N is derived from
#     `effort` as a fraction of --max-tokens. Only low/medium/high are
#     supported (no xhigh/max).
MODEL_CONFIGS = {
    "claude-fable-5-1": {"style": "adaptive", "efforts": ["low", "medium", "high", "xhigh", "max"]},
    "claude-fable-5":  {"style": "adaptive", "efforts": ["low", "medium", "high", "xhigh", "max"]},
    "claude-opus-5":   {"style": "adaptive", "efforts": ["low", "medium", "high", "xhigh", "max"]},
    "claude-opus-4-8": {"style": "adaptive", "efforts": ["low", "medium", "high", "xhigh", "max"]},
    "claude-opus-4-7": {"style": "adaptive", "efforts": ["low", "medium", "high", "xhigh", "max"]},
    "claude-opus-4-6": {"style": "adaptive", "efforts": ["low", "medium", "high", "max"]},
    "claude-opus-4-5": {"style": "budget",   "efforts": ["low", "medium", "high"]},
}

_BUDGET_FRACTION = {"low": 0.25, "medium": 0.5, "high": 0.75}
_DEFAULT_MAX_TOKENS = 40_000


def _find_boxed(text: str):
    """Return the content of the LAST \\boxed{...} in `text` (handles nested braces),
    or None if no \\boxed{} is present."""
    if not text:
        return None
    target = "\\boxed{"
    results = []
    i = 0
    while True:
        idx = text.find(target, i)
        if idx == -1:
            break
        start = idx + len(target)
        depth = 1
        j = start
        while j < len(text) and depth > 0:
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
            j += 1
        if depth == 0:
            results.append(text[start:j - 1])
        i = j if j > i else i + 1
    return results[-1].strip() if results else None


def _fallback_after_equals(text: str):
    """Return text after the LAST `=`, capped at its line, trailing punctuation stripped."""
    if not text or "=" not in text:
        return None
    tail = text.rsplit("=", 1)[1]
    tail = tail.split("\n")[0].strip()
    tail = re.sub(r"[\s.!?,;:]+$", "", tail)
    return tail or None


def extract_boxed(text: str):
    """Return the model's answer string. Tries \\boxed{} first; falls back to the
    last `=` tail. Returns None if both fail or text is empty.

    Use answer_in_boxed() if you also want to know which path succeeded.
    """
    boxed = _find_boxed(text)
    if boxed is not None:
        return boxed
    return _fallback_after_equals(text)


def answer_in_boxed(text: str) -> bool:
    """True if the model placed an answer inside \\boxed{} (i.e. followed format)."""
    return _find_boxed(text) is not None


_WS_RE = re.compile(r"\s+")


def normalize(s):
    """Light normalization for string-level answer matching."""
    if s is None:
        return None
    s = str(s).strip()
    if s.startswith("$") and s.endswith("$"):
        s = s[1:-1].strip()
    s = _WS_RE.sub("", s)
    s = s.replace("\\!", "").replace("\\,", "").replace("\\;", "").replace("\\:", "")
    s = s.replace("\\left", "").replace("\\right", "")
    # Collapse fraction macros: \dfrac, \tfrac, \cfrac, \sfrac all mean \frac
    for variant in ("\\dfrac", "\\tfrac", "\\cfrac", "\\sfrac"):
        s = s.replace(variant, "\\frac")
    # \sqrt<single token>  ->  \sqrt{<single token>}   (LaTeX allows the omission)
    s = re.sub(r"\\sqrt(\d|[a-zA-Z])", r"\\sqrt{\1}", s)
    return s.lower()


def _try_int(s):
    if s is None:
        return None
    s = str(s).lstrip("+")
    s = s.lstrip("0") or "0"
    if s.startswith("-"):
        body = s[1:].lstrip("0") or "0"
        s = "-" + body
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
    """Try to parse `s` as a sympy expression. LaTeX first, then plain. Returns None on failure."""
    if not _SYMPY_OK or s is None:
        return None
    s = str(s).strip()
    if s.startswith("$") and s.endswith("$"):
        s = s[1:-1].strip()
    if not s:
        return None
    # Try LaTeX parser first; some inputs are plain (e.g. "42"), so also try sympify.
    for parser in (parse_latex, sympify):
        try:
            return parser(s)
        except Exception:
            continue
    return None


def _sympy_equivalent(extracted, gold):
    """Symbolic equivalence via sympy. Returns True/False/None (None = could not determine)."""
    a = _sympy_parse(extracted)
    b = _sympy_parse(gold)
    if a is None or b is None:
        return None
    try:
        diff = simplify(a - b)
        if diff == 0:
            return True
        # Numerical fallback for expressions sympy can't fully simplify
        try:
            n = complex(diff.evalf())
            return abs(n) < 1e-9
        except (TypeError, ValueError):
            return False
    except Exception:
        return None


def is_correct(extracted, gold):
    """Grade one answer. DELEGATES to code/regrade.py -- the single grader.

    There used to be a second, independent implementation here, and it was the source
    of a systematic bias: it under-counted terse models because it failed on answer
    prefixes, work shown inside \\boxed{{}}, units, leading zeros and equivalent
    radicals. Having two graders in the tree meant a run could be scored by whichever
    one its driver happened to call. Now there is one.

    The import is deliberately LAZY. regrade.py loads this module (for extract_boxed),
    so importing it at module level here would be circular -- an earlier attempt at
    this consolidation did exactly that and recursed. By the time this function is
    called both modules exist, so the cycle cannot form. This module is import-safe
    (everything executable sits behind __main__), so loading it from regrade costs
    nothing.
    """
    import importlib.util as _i, os as _o
    global _RG
    try:
        _RG
    except NameError:
        _s = _i.spec_from_file_location(
            "_rg_grader", _o.path.join(_o.path.dirname(_o.path.abspath(__file__)), "regrade.py"))
        _RG = _i.module_from_spec(_s); _s.loader.exec_module(_RG)
    return _RG.is_correct(extracted, gold)

def parse_message_content(content_blocks):
    """Split an Anthropic Message's content blocks into (thinking_text, answer_text)."""
    thinking_chunks = []
    answer_chunks = []
    for block in content_blocks:
        if block.type == "thinking":
            thinking_chunks.append(block.thinking or "")
        elif block.type == "text":
            answer_chunks.append(block.text or "")
    return "".join(thinking_chunks), "".join(answer_chunks)


def thinking_kwargs_for(model: str, effort: str, max_tokens: int) -> dict:
    """Build the {"thinking": ..., "output_config": ...} kwargs for a request body."""
    cfg = MODEL_CONFIGS[model]
    if effort not in cfg["efforts"]:
        raise ValueError(
            f"--effort {effort!r} is not supported on {model} "
            f"(supported: {cfg['efforts']})"
        )
    if cfg["style"] == "adaptive":
        return {
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": effort},
        }
    # "budget" style (claude-opus-4-5): predates adaptive thinking, so
    # `budget_tokens` is mandatory -- but it DOES support output_config.effort
    # alongside it, and effort is live (measured 2026-09-17 on aime_2026_i_02:
    # low 1,475 / medium 1,903 / high 12,082 thinking tokens).
    #
    # The budget is set just under max_tokens so it never binds. That reproduces
    # the adaptive models' regime -- thinking limited only by the total output
    # cap -- leaving `effort` as the one active control, so 4.5 is comparable
    # with 4.6+. Deriving the budget from effort (the old _BUDGET_FRACTION
    # behaviour) was a stand-in for the effort parameter it failed to send, and
    # left 4.5 at the API default of "high" with a 20,000-token budget.
    budget = max(1024, max_tokens - 1024)
    return {
        "thinking": {"type": "enabled", "budget_tokens": budget},
        "output_config": {"effort": effort},
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, choices=list(MODEL_CONFIGS),
                        help="Claude Opus model id.")
    parser.add_argument("--effort", choices=["low", "medium", "high", "xhigh", "max"],
                        default="medium",
                        help="Thinking effort. Supported values depend on --model "
                             "(see MODEL_CONFIGS).")
    parser.add_argument("--n-samples", type=int, default=1)
    parser.add_argument("--n-problems", type=int, default=None,
                        help="Limit to first N problems. Default = all in the split.")
    parser.add_argument("--max-tokens", type=int, default=None,
                        help="Default: 40000.")
    parser.add_argument("--run-name", default=None,
                        help="Subfolder under results/. Defaults to a timestamp.")
    parser.add_argument("--dataset", default=DEFAULT_DATASET,
                        help=f"HuggingFace dataset id. Default: {DEFAULT_DATASET}")
    parser.add_argument("--split", default=DEFAULT_SPLIT,
                        help=f"Dataset split. Default: {DEFAULT_SPLIT}")
    parser.add_argument("--tag", default=None,
                        help="Tag used in output filenames. Default: auto-derived "
                             "from dataset id (e.g. tyrtleli/thinking-benchmark-hard-but-doable-10 "
                             "→ thinking_benchmark_hard_but_doable_10).")
    parser.add_argument("--fresh", action="store_true",
                        help="Re-run ALL problems even if an output file exists "
                             "(default: resume — skip problems already done and "
                             "append only the new ones).")
    parser.add_argument("--problem-source", default="tyrtleli/thinking-benchmark-90",
                        help="Dataset to join by id for the full `problem` text (and "
                             "`answer`) when the main --dataset omits them. "
                             "Default: tyrtleli/thinking-benchmark-90.")
    parser.add_argument("--from-batch-id", default=None,
                        help="Recover an already-submitted batch instead of "
                             "submitting a new one (e.g. after interrupted "
                             "polling — the id is in the run dir's "
                             "*_batch_id.txt). All other args must match the "
                             "original submission.")
    parser.add_argument("--seed-from", nargs="*", default=[],
                        help="Prior results JSON file(s) to REUSE rows from for any "
                             "overlapping task_ids (e.g. an earlier run on a "
                             "different-but-overlapping benchmark). Reused rows are "
                             "copied into this run's output; only non-overlapping "
                             "problems are submitted. Seed from the SAME model/effort "
                             "run for validity.")
    args = parser.parse_args()

    if args.max_tokens is None:
        args.max_tokens = _DEFAULT_MAX_TOKENS

    # Fail fast on an unsupported model/effort pairing rather than after
    # building thousands of requests.
    thinking_kwargs_for(args.model, args.effort, args.max_tokens)

    run_name = args.run_name or f"thinking_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    run_dir = RESULTS_ROOT / run_name
    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"Run dir: {run_dir}")

    if not _SYMPY_OK:
        print("WARNING: sympy / sympy.parsing.latex not importable.")
        print("         Falling back to string + numeric matching only.")
        print("         Install with: pip install sympy antlr4-python3-runtime")

    # Derive tag if not provided: drop "tyrtleli/" prefix, swap hyphens to underscores
    tag = args.tag or args.dataset.split("/")[-1].replace("-", "_")

    model_tag = args.model.replace("/", "_")
    requests_path = run_dir / f"{model_tag}_{args.effort}_{tag}_requests.jsonl"
    out_path      = run_dir / f"{model_tag}_{args.effort}_{tag}.json"
    sidecar_path  = run_dir / f"{model_tag}_{args.effort}_{tag}_batch_id.txt"
    runcfg_path   = run_dir / f"{model_tag}_{args.effort}_{tag}_runconfig.json"

    print(f"Loading {args.dataset} (split={args.split})...")
    ds = load_dataset(args.dataset, split=args.split)
    problems = list(ds)
    if args.n_problems is not None:
        problems = problems[:args.n_problems]
    print(f"  {len(problems)} problems loaded.")

    # Some benchmark datasets ship only ids/metadata (no full `problem` text, and
    # sometimes no `answer`). Join by id against --problem-source to fill them in.
    need_join = any(not p.get("problem") for p in problems)
    if need_join:
        print(f"  'problem' text missing — joining by id against {args.problem_source}")
        src = load_dataset(args.problem_source, split=args.split)
        text_by_id = {str(r["id"]): r.get("problem") for r in src}
        ans_by_id = {str(r["id"]): (r.get("answer") if "answer" in r
                                    else r.get("final_answer")) for r in src}
        missing = []
        for p in problems:
            pid = str(p["id"])
            if not p.get("problem"):
                t = text_by_id.get(pid)
                if t is None:
                    missing.append(pid)
                else:
                    p["problem"] = t
            if not p.get("answer") and not p.get("final_answer") and ans_by_id.get(pid) is not None:
                p["answer"] = ans_by_id[pid]
        if missing:
            print(f"  WARNING: {len(missing)} id(s) not found in source (will send empty "
                  f"input): {missing[:5]}{'...' if len(missing) > 5 else ''}")

    # Resume + reuse (unless --fresh):
    #   (a) skip problems already in THIS run's out_path, and
    #   (b) reuse rows from prior result files given via --seed-from (e.g. an
    #       earlier run on an overlapping benchmark), copying them into this
    #       output so shared problems aren't re-run.
    # Only the genuinely new problems are submitted.
    existing_rows = []
    if out_path.exists() and not args.fresh:
        existing_rows = json.load(out_path.open())
    done_ids = {r["task_id"] for r in existing_rows}

    seed_map = {}
    for sp in args.seed_from:
        for r in json.load(open(Path(sp).expanduser())):
            if r["task_id"] not in done_ids:
                seed_map.setdefault(r["task_id"], r)

    if not args.fresh and (done_ids or seed_map):
        before = len(problems)
        carried, remaining = [], []
        for p in problems:
            pid = str(p["id"])
            if pid in done_ids:
                continue
            elif pid in seed_map:
                row = seed_map[pid]
                if len(row.get("correct", [])) != args.n_samples:
                    print(f"    NOTE: reused {pid} has k={len(row.get('correct', []))} "
                          f"(this run is k={args.n_samples}) — carried over as-is.")
                carried.append(row)
            else:
                remaining.append(p)
        existing_rows = existing_rows + carried
        problems = remaining
        print(f"  resume: {len(done_ids)} already in output, "
              f"{len(carried)} reused from --seed-from, {len(problems)} new to run "
              f"(was {before}). Use --fresh to re-run all.")
        if not problems:
            print("  Nothing new to run — writing carried-over rows.")
            with out_path.open("w") as f:
                json.dump(existing_rows, f, indent=2)
            return

    client = anthropic.Anthropic()

    if args.from_batch_id:
        # Recover a batch that was already submitted (e.g. polling was
        # interrupted). The dataset/model/effort/n-samples args must match
        # what that batch was submitted with — custom_ids are joined against
        # the problem list loaded above.
        print(f"Recovering existing batch {args.from_batch_id}...")
        batch = client.messages.batches.retrieve(args.from_batch_id)
    else:
        n_reqs = len(problems) * args.n_samples
        print(f"Building {n_reqs} requests "
              f"({len(problems)} problems x {args.n_samples} samples)...")

        extra_kwargs = thinking_kwargs_for(args.model, args.effort, args.max_tokens)

        # Record exactly what is being sent, next to the results. The filename's
        # effort tag asserts a setting; this file proves it. Without it, a run
        # whose parameters were silently remapped (or never sent) is
        # indistinguishable from a correct one after the fact.
        runcfg = {
            "run_started": datetime.now().astimezone().isoformat(timespec="seconds"),
            "model": args.model,
            "effort_flag": args.effort,
            "max_tokens": args.max_tokens,
            "n_samples": args.n_samples,
            "dataset": args.dataset,
            "split": args.split,
            "n_problems": len(problems),
            "request_params_sent": extra_kwargs,
            "system": INSTRUCTIONS,
        }
        runcfg_path.write_text(json.dumps(runcfg, indent=2) + "\n")
        print(f"  wrote run config -> {runcfg_path.name}")
        print(f"  params sent: {json.dumps(extra_kwargs)}")

        batch_requests = []
        with requests_path.open("w") as f:
            for row in problems:
                for s in range(args.n_samples):
                    custom_id = f"{row['id']}__sample_{s}"
                    body = {
                        "model": args.model,
                        "max_tokens": args.max_tokens,
                        "system": INSTRUCTIONS,
                        "messages": [{"role": "user", "content": row["problem"]}],
                        **extra_kwargs,
                    }
                    f.write(json.dumps({"custom_id": custom_id, "body": body}) + "\n")
                    batch_requests.append(
                        Request(
                            custom_id=custom_id,
                            params=MessageCreateParamsNonStreaming(**body),
                        )
                    )

        print("Submitting batch...")
        batch = client.messages.batches.create(requests=batch_requests)
    print(f"  batch_id = {batch.id}")
    sidecar_path.write_text(batch.id + "\n")
    print(f"  saved batch_id to {sidecar_path.name}")

    print("\nPolling every 30s...")
    while True:
        b = client.messages.batches.retrieve(batch.id)
        c = b.request_counts
        print(
            f"  [{b.processing_status}] {c.succeeded} succeeded, "
            f"{c.errored} errored, {c.processing} processing",
            flush=True,
        )
        if b.processing_status == "ended":
            batch = b
            break
        time.sleep(30)

    print("Downloading results...")
    by_problem = {str(row["id"]): [None] * args.n_samples for row in problems}
    for result in client.messages.batches.results(batch.id):
        cid = result.custom_id
        problem_id, _, sample_part = cid.rpartition("__sample_")
        sample_idx = int(sample_part)
        if problem_id not in by_problem:
            continue
        if result.result.type != "succeeded":
            by_problem[problem_id][sample_idx] = {
                "thinking_text": "", "answer_text": "",
                "input_tokens": 0, "output_tokens": 0, "thinking_tokens": 0,
            }
            continue
        msg = result.result.message
        thinking_text, answer_text = parse_message_content(msg.content)
        by_problem[problem_id][sample_idx] = {
            "thinking_text": thinking_text,
            "answer_text": answer_text,
            "input_tokens": msg.usage.input_tokens,
            "output_tokens": msg.usage.output_tokens,
            "thinking_tokens": msg.usage.output_tokens_details.thinking_tokens,
        }

    print("Scoring results...")
    rows_out = []
    for row in problems:
        samples = [
            s or {"thinking_text": "", "answer_text": "",
                  "input_tokens": 0, "output_tokens": 0, "thinking_tokens": 0}
            for s in by_problem[str(row["id"])]
        ]
        # Exact server-reported split (usage.output_tokens_details.thinking_tokens),
        # not an approximation.
        thinking_tok = [s["thinking_tokens"] for s in samples]
        answer_tok = [s["output_tokens"] - s["thinking_tokens"] for s in samples]
        # Some datasets use "answer", others "final_answer"
        gold_raw = row.get("answer") if "answer" in row else row.get("final_answer")
        gold = str(gold_raw).strip()
        extracted = [extract_boxed(s["answer_text"]) for s in samples]
        boxed_flags = [answer_in_boxed(s["answer_text"]) for s in samples]
        correct = [is_correct(e, gold) for e in extracted]
        rows_out.append({
            "task_id": str(row["id"]),
            "source": row.get("source"),
            "domain": row.get("domain"),
            "difficulty": row.get("difficulty"),
            "difficulty_label": row.get("difficulty_label"),
            "requires_diagram": row.get("requires_diagram"),
            "contamination_risk": row.get("contamination_risk"),
            "gold_answer": gold,
            "extracted_answers": extracted,
            "answer_in_boxed": boxed_flags,
            "response_texts": [s["answer_text"] for s in samples],
            "correct": correct,
            "prompt_length_tokens": [s["input_tokens"] for s in samples],
            "total_completion_tokens": [s["output_tokens"] for s in samples],
            "trace_length_tokens": [s["output_tokens"] for s in samples],
            "thinking_tokens": thinking_tok,
            "answer_tokens": answer_tok,
            "response_chars": [len(s["answer_text"]) for s in samples],
            "total_latency_sec": [0.0] * len(samples),  # batch API doesn't expose this
            "solved_at_least_once": any(correct),
        })

    # Append newly-run problems to any pre-existing rows (resume mode)
    combined = existing_rows + rows_out
    with out_path.open("w") as f:
        json.dump(combined, f, indent=2)

    total = sum(sum(r["correct"]) for r in combined)
    denom = sum(len(r["correct"]) for r in combined)
    size_mb = out_path.stat().st_size / 1024 / 1024
    print(f"\nDone. {len(rows_out)} new task(s) added; {len(combined)} total.")
    print(f"Overall accuracy: {total}/{denom} = {total / denom:.1%}")
    print(f"Wrote {out_path}  ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
