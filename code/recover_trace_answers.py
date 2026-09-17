#!/usr/bin/env python3
"""Recover answers from the reasoning channel when `content` came back empty.

Some provider/model pairs never close the <think> block, so OpenRouter labels the
ENTIRE generation -- final answer included -- as reasoning and returns empty
content. Measured on DeepSeek V3.1 Terminus @ SiliconFlow 2026-09-17: two of two
requests gave content_chars=0, finish_reason=stop, and a \\boxed{} answer sitting
at the tail of the trace. V3.2 on the same provider splits correctly, so this is
per-model, not per-provider.

Nothing needs re-running: the full trace is in <slug>_<tag>_reasoning_traces.json,
joinable to the results file by task_id. This re-extracts from the trace for
exactly those trials whose response_text is empty, and regrades them.

Report-only unless --write. Original values are preserved in
`correct_before_trace_recovery` / `extracted_before_trace_recovery` the first
time a file is written, matching apply_regrade.py.

Caveat this cannot fix: for these trials `thinking_tokens` includes the answer
and `answer_tokens` is 0, so the trace length is inflated by the size of the
answer (~5% on V3.2's numbers). That is a real bias in the measured quantity and
belongs in the caveats, not in a correction here.

Usage:  recover_trace_answers.py <results.json> [...] [--write]
        recover_trace_answers.py --all [--write]
"""
import argparse, glob, json, os, sys, importlib.util

spec = importlib.util.spec_from_file_location(
    "b", os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "benchmark_math_open_source.py"))
B = importlib.util.module_from_spec(spec); spec.loader.exec_module(B)


def recover(res_path, write):
    tr_path = res_path.replace(".json", "_reasoning_traces.json")
    if not os.path.exists(tr_path):
        print(f"\n=== {os.path.basename(res_path)} ===\n  no traces file -- skipped")
        return 0
    rows = json.load(open(res_path))
    traces = {t["task_id"]: t["reasoning_texts"] for t in json.load(open(tr_path))}

    empty = fixed = flipped = 0
    for r in rows:
        texts = r.get("response_texts") or []
        rsn = traces.get(r["task_id"]) or []
        gold = str(r.get("gold_answer", "")).strip()
        for i, t in enumerate(texts):
            if (t or "").strip():
                continue
            empty += 1
            if i >= len(rsn) or not (rsn[i] or "").strip():
                continue
            got = B.extract_boxed(rsn[i])
            if got is None:
                continue
            fixed += 1
            ok = B.is_correct(got, gold)
            if write:
                r.setdefault("extracted_before_trace_recovery",
                             list(r.get("extracted_answers", [])))
                r.setdefault("correct_before_trace_recovery", list(r.get("correct", [])))
                r["extracted_answers"][i] = got
                r["answer_in_boxed"][i] = True
            if ok and not r.get("correct", [])[i]:
                flipped += 1
            if write:
                r["correct"][i] = ok

    print(f"\n=== {os.path.basename(res_path)} ===")
    print(f"  trials with empty content : {empty}")
    print(f"  recoverable from the trace: {fixed}")
    print(f"  would flip wrong -> right : {flipped}")
    if empty and not fixed:
        print("  WARNING: empty content and nothing extractable -- this run is not salvageable")
    if write and fixed:
        json.dump(rows, open(res_path, "w"), indent=2)
        print(f"  WROTE {res_path}")
    elif fixed:
        print("  (report only -- pass --write to apply)")
    return flipped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    paths = a.paths or (sorted(
        p for p in glob.glob("code/results/*_shallow_pass/*.json")
        if not p.endswith(("_runconfig.json", "_reasoning_traces.json"))) if a.all else [])
    if not paths:
        sys.exit("nothing to do")
    total = sum(recover(p, a.write) for p in paths)
    print(f"\ntotal trials flipped wrong -> right: {total}")


if __name__ == "__main__":
    main()
