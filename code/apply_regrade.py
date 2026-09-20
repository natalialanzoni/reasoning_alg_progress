"""
Bake robust re-grading into every result file's `correct` field.

For each trial: keeps it correct if it already was; otherwise re-grades the answer
with regrade.is_correct (robust to prefixes, shown work, units, leading zeros,
tuples/sets, \\pi, mixed numbers, and symbolic equivalence). The ORIGINAL grades
are preserved in a new `correct_original` field (idempotent: re-runs always regrade
from `correct_original`). `solved_at_least_once` is updated when present.

    ./venv/bin/python code/apply_regrade.py            # dry-run report
    ./venv/bin/python code/apply_regrade.py --write    # write changes in place
"""
import glob
import json
import os
import sys
import warnings

warnings.filterwarnings("ignore")
import importlib.util as _ilu
_spec = _ilu.spec_from_file_location("rg", os.path.join(os.path.dirname(__file__), "regrade.py"))
rg = _ilu.module_from_spec(_spec); _spec.loader.exec_module(rg)

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
SKIP = ("_requests.jsonl", "_batch_id.txt", "run_config", "metrics", ".csv", ".log", ".txt")


def _process_oss(path, doc, write):
    """Schema B: {"results": [{"answer", "completions": [{"is_correct", ...}]}]}.

    gpt-oss runs use this shape, and the schema-A test below silently returned None
    for them -- so four result files were never regraded at all and nothing said so.
    Re-grading them today flips 0 of 1,360 completions, but that was luck, not design.
    """
    og = on = flips = 0
    for e in doc.get("results", []):
        gold = e.get("answer")
        for c in e.get("completions", []):
            base = c.get("is_correct_original", c.get("is_correct"))
            if "is_correct_original" not in c:
                c["is_correct_original"] = bool(base)
            on += 1; og += int(bool(base))
            if base:
                c["is_correct"] = True
                continue
            ext = c.get("extracted_answer") or rg.extract_boxed(c.get("text") or "")
            ok = bool(rg.is_correct(ext, gold))
            c["is_correct"] = ok; flips += int(ok)
    if write:
        json.dump(doc, open(path, "w"), indent=2)
    return og, og + flips, on, flips


def process(path, write):
    try:
        rows = json.load(open(path))
    except Exception:
        return None
    # schema B before the schema-A shape test, which would reject it
    if isinstance(rows, dict):
        if isinstance(rows.get("results"), list) and rows["results"] \
                and isinstance(rows["results"][0], dict) \
                and "completions" in rows["results"][0]:
            return _process_oss(path, rows, write)
        return None
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
        return None
    if "correct" not in rows[0] or "gold_answer" not in rows[0]:
        return None
    og = on = flips = 0
    for r in rows:
        base = r.get("correct_original", r["correct"])
        if "correct_original" not in r:
            r["correct_original"] = list(base)
        gold = r.get("gold_answer")
        ext = r.get("extracted_answers")
        texts = r.get("response_texts")
        new = []
        for i in range(len(base)):
            old = bool(base[i]); on += 1; og += int(old)
            if old:
                new.append(True); continue
            e = ext[i] if ext else (rg.extract_boxed(texts[i]) if texts else None)
            ok = rg.is_correct(e, gold)
            new.append(bool(ok)); flips += int(ok)
        r["correct"] = new
        if "solved_at_least_once" in r:
            r["solved_at_least_once"] = any(new)
    if write:
        json.dump(rows, open(path, "w"), indent=2)
    ng = og + flips
    return og, ng, on, flips


def main():
    write = "--write" in sys.argv
    files = [f for f in glob.glob(os.path.join(DATA, "**", "*.json"), recursive=True)
             if not any(s in os.path.basename(f) for s in SKIP)]
    print(f"{'MODE: WRITE' if write else 'MODE: DRY-RUN'}  ({len(files)} json files)\n")
    tot_flip = done = 0
    unhandled = []
    for f in sorted(files):
        res = process(f, write)
        if res is None:
            # A file that looks like results but no handler understood it is a
            # silent hole exactly like the gpt-oss one -- name it.
            try:
                doc = json.load(open(f))
            except Exception:
                doc = None
            looks_like_results = (isinstance(doc, dict) and "results" in doc) or (
                isinstance(doc, list) and doc and isinstance(doc[0], dict)
                and any(k in doc[0] for k in ("correct", "completions", "is_correct")))
            if looks_like_results:
                unhandled.append(os.path.relpath(f, DATA))
            continue
        og, ng, on, flips = res
        done += 1; tot_flip += flips
        if flips:
            rel = os.path.relpath(f, DATA)
            print(f"  {rel:70s} {100*og/on:5.1f}% -> {100*ng/on:5.1f}%  (+{flips})")
    print(f"\nprocessed {done} result files; {tot_flip} trials grade correct that the "
          f"ORIGINAL grader marked wrong")
    print("   NOTE: in a dry run this is the CUMULATIVE total, not pending work. Files")
    print("   already regraded keep their pre-regrade grades in `correct_original`, and")
    print("   the count is recomputed from those every time, so a run that changes")
    print("   nothing still prints the same number. To see what is genuinely NEW, look")
    print("   for files lacking `correct_original` (or `is_correct_original`).")
    if unhandled:
        print(f"\n!! {len(unhandled)} file(s) look like results but NO handler matched -- "
              f"these are NOT regraded:")
        for u in unhandled:
            print(f"     {u}")
        print("   Add a schema handler rather than leaving them unread.")
    if not write:
        print("DRY-RUN only. Re-run with --write to bake into the files.")


if __name__ == "__main__":
    main()
