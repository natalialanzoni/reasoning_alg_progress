"""
Benchmark OpenAI reasoning models on the tyrtleli/thinking-benchmark dataset
via the Batch API (50% cheaper than live).

Loads the dataset from HuggingFace, submits one batch per (model, effort)
configuration, polls until done, and writes per-task results that include
the gold answer, the model's extracted final answer for each sample, and
the full response text alongside the usual token usage / correctness.

Usage:
    python benchmark_math_dist.py --model o4-mini --effort medium
    python benchmark_math_dist.py --model o3-mini --effort low --n-problems 5 --n-samples 10
"""
import argparse
import json
import re
import time
from datetime import datetime
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

DEFAULT_DATASET = "tyrtleli/thinking-benchmark"
DEFAULT_SPLIT = "test"

INSTRUCTIONS = (
    "Solve the problem step by step. End your response with your final answer "
    "inside \\boxed{}. The answer may be an integer, a fraction (e.g. "
    "\\frac{1}{2}), a closed-form expression with radicals, or a tuple/set."
)


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

def parse_output_text(body):
    chunks = []
    for item in body.get("output", []):
        if item.get("type") == "message":
            for c in item.get("content", []):
                if c.get("type") == "output_text":
                    chunks.append(c.get("text", ""))
    return "".join(chunks)


def _dump_error_file(client, batch, n_show=3):
    """Print a few representative errors from a batch's error_file, so failures
    (e.g. an unsupported effort level) are visible instead of silent."""
    efid = getattr(batch, "error_file_id", None)
    if not efid:
        print("  (no error_file_id available to explain the failure)")
        return
    try:
        text = client.files.content(efid).text
    except Exception as e:
        print(f"  could not download error file: {e}")
        return
    lines = [ln for ln in text.splitlines() if ln.strip()]
    print(f"  error file: {len(lines)} error line(s); first {min(n_show, len(lines))}:")
    for ln in lines[:n_show]:
        try:
            rec = json.loads(ln)
            err = (rec.get("response", {}) or {}).get("body", {}).get("error") or rec.get("error")
            print(f"    - {rec.get('custom_id', '?')}: {err}")
        except Exception:
            print(f"    - {ln[:200]}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True,
                        help="OpenAI reasoning model id (e.g. o3-mini, o4-mini, o3).")
    parser.add_argument("--effort",
                        choices=["minimal", "low", "medium", "high", "xhigh", "max"],
                        default="medium",
                        help="reasoning.effort. Note: not every model accepts every "
                             "level (older models may cap at 'high').")
    parser.add_argument("--n-samples", type=int, default=1)
    parser.add_argument("--n-problems", type=int, default=None,
                        help="Limit to first N problems. Default = all in the split.")
    parser.add_argument("--task-ids-file", default=None,
                        help="Path to a newline-delimited list of task ids. If given, "
                             "restrict the run to exactly those problems (order and "
                             "membership from the file). Use to run only the canonical "
                             "subset so results drop into the figures unchanged. "
                             "Composes with everything else; only model params are "
                             "unaffected (this just subsets which problems are sent).")
    parser.add_argument("--max-tokens", type=int, default=100000)
    parser.add_argument("--run-name", default=None,
                        help="Subfolder under results/. Defaults to a timestamp.")
    parser.add_argument("--dataset", default=DEFAULT_DATASET,
                        help=f"HuggingFace dataset id. Default: {DEFAULT_DATASET}")
    parser.add_argument("--split", default=DEFAULT_SPLIT,
                        help=f"Dataset split. Default: {DEFAULT_SPLIT}")
    parser.add_argument("--tag", default=None,
                        help="Tag used in output filenames. Default: auto-derived "
                             "from dataset id (e.g. tyrtleli/thinking-benchmark-hard-but-doable "
                             "→ thinking_benchmark_hard_but_doable).")
    parser.add_argument("--fresh", action="store_true",
                        help="Re-run ALL problems even if an output file exists "
                             "(default: resume — skip problems already done and "
                             "append only the new ones).")
    parser.add_argument("--from-batch", default=None,
                        help="COLLECT mode: attach to an existing batch id and "
                             "download/parse its results instead of submitting a "
                             "new batch. Use to recover an orphaned batch (e.g. one "
                             "whose poller died) without paying again. Pass the SAME "
                             "--model/--effort/--dataset/--run-name/--n-samples as the "
                             "original run so results parse and land at the right path.")
    parser.add_argument("--problem-source", default="tyrtleli/thinking-benchmark-90",
                        help="Dataset to join by id for the full `problem` text (and "
                             "`answer`) when the main --dataset omits them. "
                             "Default: tyrtleli/thinking-benchmark-90.")
    parser.add_argument("--seed-from", nargs="*", default=[],
                        help="Prior results JSON file(s) to REUSE rows from for any "
                             "overlapping task_ids (e.g. an earlier run on a "
                             "different-but-overlapping benchmark). Reused rows are "
                             "copied into this run's output; only non-overlapping "
                             "problems are submitted. Seed from the SAME model/effort "
                             "run for validity.")
    args = parser.parse_args()

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

    print(f"Loading {args.dataset} (split={args.split})...")
    ds = load_dataset(args.dataset, split=args.split)
    problems = list(ds)
    if args.n_problems is not None:
        problems = problems[:args.n_problems]
    if args.task_ids_file:
        wanted = [ln.strip() for ln in Path(args.task_ids_file).expanduser().read_text().splitlines()
                  if ln.strip()]
        by_id = {str(p["id"]): p for p in problems}
        missing = [t for t in wanted if t not in by_id]
        problems = [by_id[t] for t in wanted if t in by_id]
        print(f"  restricted to {len(problems)} task id(s) from {args.task_ids_file}"
              + (f"; {len(missing)} not found in split: {missing[:5]}"
                 f"{'...' if len(missing) > 5 else ''}" if missing else ""))
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

    client = OpenAI()

    if args.from_batch:
        # Collect mode: attach to an already-submitted batch instead of
        # creating a new one. Results are parsed + merged into out_path below,
        # so a later normal run resumes by problem (skips what we recovered).
        print(f"Collect mode: attaching to existing batch {args.from_batch} "
              f"(no new submission)...")
        batch = client.batches.retrieve(args.from_batch)
    else:
        n_reqs = len(problems) * args.n_samples
        print(f"Building {n_reqs} requests "
              f"({len(problems)} problems x {args.n_samples} samples)...")

        with requests_path.open("w") as f:
            for row in problems:
                for s in range(args.n_samples):
                    req = {
                        "custom_id": f"{row['id']}__sample_{s}",
                        "method": "POST",
                        "url": "/v1/responses",
                        "body": {
                            "model": args.model,
                            "reasoning": {"effort": args.effort},
                            "max_output_tokens": args.max_tokens,
                            "instructions": INSTRUCTIONS,
                            "input": row["problem"],
                        },
                    }
                    f.write(json.dumps(req) + "\n")

        # Upload + submit, retrying transient connection errors so a network
        # blip (common when several models submit in parallel) doesn't lose the
        # run before a batch_id is even saved.
        print("Uploading + submitting batch...")
        batch = None
        for attempt in range(1, 6):
            try:
                upload = client.files.create(file=requests_path.open("rb"), purpose="batch")
                batch = client.batches.create(
                    input_file_id=upload.id,
                    endpoint="/v1/responses",
                    completion_window="24h",
                )
                break
            except Exception as e:
                wait = 5 * 2 ** (attempt - 1)
                print(f"  submit attempt {attempt} failed ({type(e).__name__}: {e}); "
                      f"retrying in {wait}s...", flush=True)
                time.sleep(wait)
        if batch is None:
            print("  submission failed after 5 attempts — skipping this model.")
            return
        print(f"  batch_id = {batch.id}")
        sidecar_path.write_text(batch.id + "\n")
        print(f"  saved batch_id to {sidecar_path.name}")

    print("\nPolling every 30s...")
    while True:
        try:
            b = client.batches.retrieve(batch.id)
        except Exception as e:
            # A transient network/read timeout on a poll must NOT kill the run —
            # the batch keeps processing server-side. Log and retry.
            print(f"  poll failed ({type(e).__name__}: {e}); retrying in 30s...",
                  flush=True)
            time.sleep(30)
            continue
        c = b.request_counts
        print(
            f"  [{b.status}] {c.completed}/{c.total} completed, {c.failed} failed",
            flush=True,
        )
        if b.status in ("completed", "failed", "expired", "cancelled"):
            batch = b
            break
        time.sleep(30)

    if batch.status != "completed":
        print(f"\nBatch ended with status: {batch.status}")
        _dump_error_file(client, batch)
        return

    # A "completed" batch can still have zero successful outputs — e.g. every
    # request errored on an unsupported param (an older model rejecting a too-new
    # effort level). Then output_file_id is None; don't try to download it.
    if not batch.output_file_id:
        print(f"\nBatch completed but produced NO output file — "
              f"{batch.request_counts.failed}/{batch.request_counts.total} "
              f"request(s) errored.")
        _dump_error_file(client, batch)
        return

    print("Downloading results...")
    text = None
    last_err = None
    for attempt in range(1, 6):
        try:
            text = client.files.content(batch.output_file_id).text
            break
        except Exception as e:
            last_err = e
            wait = 5 * 2 ** (attempt - 1)
            print(f"  download attempt {attempt} failed ({type(e).__name__}: {e});"
                  f" retrying in {wait}s...")
            time.sleep(wait)
    if text is None:
        print(f"\nDownload failed after 5 attempts: {last_err}")
        print(f"Recover later: batch_id={batch.id} (also in {sidecar_path.name})")
        return

    # Index results by problem_id (treated as string).
    by_problem = {str(row["id"]): [None] * args.n_samples for row in problems}
    for line in text.splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        cid = rec["custom_id"]
        problem_id, _, sample_part = cid.rpartition("__sample_")
        sample_idx = int(sample_part)
        if problem_id not in by_problem:
            continue
        if rec.get("error") or not rec.get("response"):
            by_problem[problem_id][sample_idx] = {
                "output_text": "",
                "input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0,
            }
            continue
        body = rec["response"]["body"]
        u = body["usage"]
        by_problem[problem_id][sample_idx] = {
            "output_text": parse_output_text(body),
            "input_tokens": u["input_tokens"],
            "output_tokens": u["output_tokens"],
            "reasoning_tokens": u.get("output_tokens_details", {}).get(
                "reasoning_tokens", 0
            ),
        }

    rows_out = []
    for row in problems:
        raw_slots = by_problem[str(row["id"])]
        # In collect mode the loaded dataset may be larger than the batch's
        # problem set; skip problems with no result at all so we don't write
        # bogus empty rows (they stay unrun and a later resume picks them up).
        if args.from_batch and all(s is None for s in raw_slots):
            continue
        samples = [
            s or {"output_text": "", "input_tokens": 0,
                  "output_tokens": 0, "reasoning_tokens": 0}
            for s in raw_slots
        ]
        # Some datasets use "answer", others "final_answer"
        gold_raw = row.get("answer") if "answer" in row else row.get("final_answer")
        gold = str(gold_raw).strip()
        extracted = [extract_boxed(s["output_text"]) for s in samples]
        boxed_flags = [answer_in_boxed(s["output_text"]) for s in samples]
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
            "response_texts": [s["output_text"] for s in samples],
            "correct": correct,
            "prompt_length_tokens": [s["input_tokens"] for s in samples],
            "total_completion_tokens": [s["output_tokens"] for s in samples],
            "trace_length_tokens": [s["output_tokens"] for s in samples],
            "thinking_tokens": [s["reasoning_tokens"] for s in samples],
            "answer_tokens": [
                s["output_tokens"] - s["reasoning_tokens"] for s in samples
            ],
            "response_chars": [len(s["output_text"]) for s in samples],
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
