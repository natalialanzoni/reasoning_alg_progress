"""
Right-censor attempts that exceeded the requested output cap.

Why: some OpenRouter providers do not honor `max_tokens`. In our sweeps Z.AI
(GLM 4.5), Novita (GLM 4.7, Kimi K2 Thinking) returned completions well past
the 40,000-token request -- up to 87,718. Models served by compliant providers
were hard-stopped at exactly 40,000. Comparing trace length or accuracy across
that mix measures the provider, not the model.

Fix: clamp any attempt above the cap to the cap and mark it incorrect, i.e.
treat it exactly as the truncation that a compliant provider would have
produced. This is not an assumption -- every attempt that actually hit 40,000
in our data scored correct=False, because a truncated response emits no
\\boxed{} answer.

Leaves raw files untouched; use --write to emit *_censored.json alongside.

    python code/censor_over_cap.py data/**/*.json            # report only
    python code/censor_over_cap.py --write --cap 40000 <files>
"""
import argparse
import json
from pathlib import Path

TOKEN_FIELDS = ("total_completion_tokens", "trace_length_tokens")


def censor_record(rec, cap):
    """Clamp over-cap attempts in one task record. Returns n_censored."""
    n = 0
    over = [i for i, v in enumerate(rec.get("total_completion_tokens", [])) if v > cap]
    for i in over:
        for f in TOKEN_FIELDS:
            if f in rec and i < len(rec[f]):
                rec[f][i] = cap
        # thinking_tokens/answer_tokens: scale thinking down to the cap, answer to 0
        if "thinking_tokens" in rec and i < len(rec["thinking_tokens"]):
            rec["thinking_tokens"][i] = min(rec["thinking_tokens"][i], cap)
        if "answer_tokens" in rec and i < len(rec["answer_tokens"]):
            rec["answer_tokens"][i] = 0
        # a truncated completion has no boxed answer and cannot be graded correct
        if "correct" in rec and i < len(rec["correct"]):
            rec["correct"][i] = False
        if "answer_in_boxed" in rec and i < len(rec["answer_in_boxed"]):
            rec["answer_in_boxed"][i] = False
        if "extracted_answers" in rec and i < len(rec["extracted_answers"]):
            rec["extracted_answers"][i] = None
        n += 1
    if "correct" in rec:
        rec["solved_at_least_once"] = any(rec["correct"])
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--cap", type=int, default=40000)
    ap.add_argument("--write", action="store_true",
                    help="write <name>_censored.json next to each input")
    args = ap.parse_args()

    for p in (Path(f) for f in args.files):
        try:
            data = json.loads(p.read_text())
        except Exception as e:
            print(f"{p.name}: skipped ({type(e).__name__})")
            continue
        if not isinstance(data, list):
            print(f"{p.name}: skipped (not a task list)")
            continue
        before = [v for r in data for v in r.get("total_completion_tokens", [])]
        n = sum(censor_record(r, args.cap) for r in data)
        if not n:
            print(f"{p.name}: clean (no attempt over {args.cap:,})")
            continue
        after = [v for r in data for v in r.get("total_completion_tokens", [])]
        corr = [c for r in data for c in r.get("correct", [])]
        print(f"{p.name}: censored {n}/{len(before)} attempts "
              f"(max {max(before):,} -> {max(after):,}, "
              f"mean {sum(before)/len(before):,.0f} -> {sum(after)/len(after):,.0f}, "
              f"acc now {100*sum(corr)/len(corr):.1f}%)")
        if args.write:
            out = p.with_name(p.stem + "_censored.json")
            out.write_text(json.dumps(data, indent=2))
            print(f"    wrote {out.name}")


if __name__ == "__main__":
    main()
