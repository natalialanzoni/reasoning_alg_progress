"""Build for_RA_review/v6_backtracking/: the RA checks the soft answer key, then v6 against it.

  python code/llm_judge/make_v6_review_pack.py

Same 20 traces as the v3 pack (linked there, not copied). Per trace, one sheet:
  Part 1  the two blind annotators' entries (gold_soft/annotations/), merged where both found
          the same episode -- the RA confirms or rejects each, and adds any that were missed
  Part 2  every v6 entry (out/pilot_v6_gemini-3.1-pro-preview.jsonl) with the key entry it
          was matched to -- done AFTER Part 1, so the judge's list cannot steer the key
Verdicts go in key_verdicts.csv and v6_verdicts.csv.
"""
import csv
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pilot as P                                       # noqa: E402
import pilot_v4 as p                                    # noqa: E402

RT = os.path.join(HERE, "for_RA_review", "review_traces")    # traces, index, problems
OUT = os.path.join(HERE, "for_RA_review", "v6_backtracking")
ANN = os.path.join(HERE, "gold_soft", "annotations")
JUDGE = "google/gemini-3.1-pro-preview"
SL = 5


def ann(a, t):
    try:
        return json.load(open(os.path.join(ANN, f"{a}_{t}.json")))
    except (OSError, ValueError):
        return None


def spans(i):
    return [tuple(v) for v in i.get("visits") or []] or [(i["abandon_line"], i["abandon_line"])]


def same(x, y):
    return any(s1 - SL <= e2 and s2 - SL <= e1 for s1, e1 in spans(x) for s2, e2 in spans(y))


def key_for(t):
    """Merge the two annotators' lists: an entry both found is one row."""
    A, B = ann("a1", t), ann("a2", t)
    a, b = (A or {}).get("instances", []), (B or {}).get("instances", [])
    used, rows = set(), []
    for x in a:
        j = next((j for j, y in enumerate(b) if j not in used and same(x, y)), None)
        if j is not None:
            used.add(j)
        rows.append((x, b[j] if j is not None else None))
    rows += [(None, y) for j, y in enumerate(b) if j not in used]
    rows.sort(key=lambda r: min(s for s, _ in spans(r[0] or r[1])))
    rej = (A or {}).get("rejected", []) + (B or {}).get("rejected", [])
    return rows, rej, [n for n, d in (("annotator 1", A), ("annotator 2", B)) if d]


def link(f, s, e=None):
    e = e if e is not None and e != s else None
    return f"[L{s}{'–' + str(e) if e else ''}](../review_traces/traces/{f}#L{s}{'-L' + str(e) if e else ''})"


PROBLEMS = json.load(open(os.path.join(RT, "problems.json")))


def problem(t):
    return PROBLEMS.get(t) or "(see trace)"


def main():
    os.makedirs(OUT, exist_ok=True)
    meta = {r["file"][:2]: r for r in csv.DictReader(open(os.path.join(RT, "index.csv")))}
    recs = {d["trace"]: d for d in map(json.loads, open(P.out_path("v6", JUDGE)))}
    kcsv, vcsv = [], []
    for t in sorted(meta):
        m = meta[t]; f = m["file"] + ".txt"
        lines = open(os.path.join(RT, "traces", f)).read().split("\n")
        rows, rej, who = key_for(t)
        # key entries in gold format, so v6 is matched exactly as the scorer matched it
        gold = [{"id": f"K{i}", "spans": [list(s) for s in sorted(set(spans(x or y)) | set(spans(y) if x and y else []))],
                 "anchors": [z["abandon_line"] for z in (x, y) if z]} for i, (x, y) in enumerate(rows, 1)]
        out = [f"# {t} — {m['model']}, {m['task']} sample {m['sample']}", "",
               f"**Trace:** [`{f}`](../review_traces/traces/{f}) ({len(lines)} lines). "
               "Line links open GitHub with those lines highlighted.", "",
               "## The problem", "", problem(t), ""]
        out += ["## Part 1 — check the answer key", "",
                f"Counted by: {', '.join(who) if who else '**nobody** (both annotators were stopped)'}."
                + (" Only one annotator finished this trace, so check it with extra care." if len(who) == 1 else ""), ""]
        if not who:
            out += ["There is no key for this trace. Please count it from scratch and add each entry "
                    "to `key_verdicts.csv` as a new row.", ""]
        elif not rows:
            out += ["The annotators found **no** abandoned approaches here.", ""]
        else:
            out += ["| # | approach | lines | given up at | tier | found by |", "|---|---|---|---|---|---|"]
            for i, (x, y) in enumerate(rows, 1):
                z = x or y
                vis = ", ".join(link(f, s, e) for s, e in sorted(set(spans(x or y)) | set(spans(y) if x and y else [])))
                tier = "/".join(sorted({w["tier"] for w in (x, y) if w}))
                by = "both" if x and y else ("annotator 1" if x else "annotator 2")
                out.append(f"| K{i} | {z['approach']} | {vis} | {link(f, z['abandon_line'])} “{z['abandon_quote']}” "
                           f"| {tier} | {by} |")
                kcsv.append({"trace": t, "entry": f"K{i}", "approach": z["approach"],
                             "lines": ";".join(f"{s}-{e}" for s, e in spans(z)), "tier": tier, "found_by": by,
                             "RA_verdict": "", "RA_note": ""})
            out.append("")
        if rej:
            out += ["<details><summary>Places the annotators considered and decided <b>not</b> to count "
                    f"({len(rej)})</summary>", "", "| lines | what | why not |", "|---|---|---|"]
            out += [f"| {link(f, r['lines'][0], r['lines'][-1])} | {r['what']} | {r['why_not']} |"
                    for r in sorted(rej, key=lambda r: r["lines"][0])]
            out += ["", "</details>", ""]
        # Part 2
        r = recs[t]
        ver = [d for d in p.parse(r.get("raw"), lines) if d["verified"]]
        mt, dup = p.match(ver, gold)
        out += ["## Part 2 — check the judge (do this after Part 1)", "",
                f"The v6 judge listed **{len(ver)}** entries"
                + (" (its reply was cut off before the end)" if r.get("finish") == "length" else "") + ".", ""]
        if ver:
            out += ["| # | judge's approach | lines | matched to key |", "|---|---|---|---|"]
            for i, d in enumerate(ver, 1):
                s = d["adopt_found"] or d["adopt_line"] or d["abandon_found"]; e = d["abandon_found"]
                mk = (mt.get(i - 1) and f"{mt[i - 1]}") or (dup.get(i - 1) and f"{dup[i - 1]} (a second entry for it)") or "none"
                out.append(f"| J{i} | {d['approach']} | {link(f, min(s, e), max(s, e))} | {mk} |")
                vcsv.append({"trace": t, "entry": f"J{i}", "approach": d["approach"], "lines": f"{min(s, e)}-{max(s, e)}",
                             "matched_to_key": mk, "RA_verdict": "", "RA_note": ""})
            out.append("")
        open(os.path.join(OUT, f"{t}_{m['model'].replace(' ', '').replace('.', '_')}_{m['task']}_s{m['sample']}.md"),
             "w").write("\n".join(out) + "\n")
    for name, rows in (("key_verdicts.csv", kcsv), ("v6_verdicts.csv", vcsv)):
        with open(os.path.join(OUT, name), "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader(); w.writerows(rows)
    print(f"{OUT}: 20 sheets, {len(kcsv)} key entries, {len(vcsv)} judge entries")


if __name__ == "__main__":
    main()
