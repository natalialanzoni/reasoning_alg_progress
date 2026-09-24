"""Build the soft answer key from the two blind annotations and score a pilot run against it.

  python code/llm_judge/gold_soft/score_soft.py                 # v6, gemini-3.1-pro-preview
  python code/llm_judge/gold_soft/score_soft.py v5 google/gemini-2.5-pro

The key counts "tries an approach and gives it up to do something different"
(INSTRUCTIONS.md). annotations/ holds one file per annotator (a1, a2) per trace. Some
traces have one annotator or none, because Anthropic's usage-policy filter stopped
four annotator runs; those were not retried. gold_soft.json is written here: the union
of both lists, with agreed = both annotators found the episode.

Pair ratios are compared ONE ANNOTATOR AT A TIME, over the traces that annotator
counted, judge and annotator on the same traces. The union key is not used for them:
a double-counted trace gets more entries than a single-counted one, and the mix
differs by model, so a union-key ratio measures coverage, not backtracking.
"""
import json
import os
import sys

D = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(D))
import pilot as P                                       # noqa: E402
import pilot_v4 as p                                    # noqa: E402

PR = sys.argv[1] if len(sys.argv) > 1 else "v6"
J = sys.argv[2] if len(sys.argv) > 2 else "google/gemini-3.1-pro-preview"
SL = 5                    # line slack when deciding two entries are the same episode
PAIRS = [("GLM 5.2", "GLM 5.3"), ("gpt-oss-20b", "gpt-oss-120b")]
MODEL = {r.split(",")[0][:2]: r.split(",")[1] for r in open(p.VERDICTS).read().splitlines()[1:]}


def load(a):
    out = {}
    for f in sorted(os.listdir(os.path.join(D, "annotations"))):
        if f.startswith(a + "_"):
            d = json.load(open(os.path.join(D, "annotations", f)))
            out[d["trace"]] = d
    return out


def spans(i):
    return [tuple(v) for v in i.get("visits") or []] or [(i["abandon_line"], i["abandon_line"])]


def same(x, y):
    return any(s1 - SL <= e2 and s2 - SL <= e1 for s1, e1 in spans(x) for s2, e2 in spans(y))


A = {"a1": load("a1"), "a2": load("a2")}
traces = sorted(set(A["a1"]) | set(A["a2"]))
both = [t for t in traces if t in A["a1"] and t in A["a2"]]
print(f"annotated: {len(traces)} traces; both {len(both)}; a1 only "
      f"{[t for t in traces if t not in A['a2']]}; a2 only {[t for t in traces if t not in A['a1']]}")

# ---- the key: union of both lists, one entry per episode
gold = []
for t in traces:
    a = A["a1"].get(t, {}).get("instances", []); b = A["a2"].get(t, {}).get("instances", [])
    used = set()
    for x in a:
        j = next((j for j, y in enumerate(b) if j not in used and same(x, y)), None)
        used |= {j} - {None}
        pair = [x] + ([b[j]] if j is not None else [])
        gold.append({"trace": t, "id": f"{t}s{len(gold)}", "agreed": len(pair) == 2,
                     "spans": sorted({s for z in pair for s in spans(z)}),
                     "anchors": [z["abandon_line"] for z in pair], "tiers": [z["tier"] for z in pair],
                     "by": ["a1", "a2"][:len(pair)], "approach": x["approach"]})
    for j, y in enumerate(b):
        if j not in used:
            gold.append({"trace": t, "id": f"{t}s{len(gold)}", "agreed": False, "spans": spans(y),
                         "anchors": [y["abandon_line"]], "tiers": [y["tier"]], "by": ["a2"],
                         "approach": y["approach"]})
json.dump({"note": 'Soft backtracking key: "tries an approach and gives it up to do something '
                   'different". Two blind Claude annotators; union, agreed = both found it. '
                   'NOT RA-checked.', "instances": gold},
          open(os.path.join(D, "gold_soft.json"), "w"), indent=1)

# ---- judge entries against the key
recs = {d["trace"]: d for d in map(json.loads, open(P.out_path(PR, J)))}
rows, why_counts = [], {}
hit_by_tier = {k: [0, 0, 0] for k in ("firm", "mixed", "borderline")}  # matched / inside a judge span / missed
for t in traces:
    r = recs[t]
    lines = open(os.path.join(p.TRACES, r["file"])).read().split("\n")
    ver = [d for d in p.parse(r.get("raw"), lines) if d["verified"]]
    g = [x for x in gold if x["trace"] == t]
    m, dup = p.match(ver, g)
    rej = [x for a in ("a1", "a2") for x in A[a].get(t, {}).get("rejected", [])]
    for i, d in enumerate(ver):
        if i not in m and i not in dup:
            why = next((x["why_not"].split(":")[0].strip() for x in rej
                        if x["lines"][0] - SL <= d["abandon_found"] <= x["lines"][-1] + SL), "not flagged")
            why_counts[why] = why_counts.get(why, 0) + 1
    for x in g:
        if not x["agreed"]:
            continue
        k = "firm" if set(x["tiers"]) == {"firm"} else "borderline" if set(x["tiers"]) == {"borderline"} else "mixed"
        inside = any(min(d["adopt_found"] or d["abandon_found"], d["abandon_found"]) <= e
                     and s <= max(d["adopt_found"] or 0, d["abandon_found"]) for d in ver for s, e in x["spans"])
        hit_by_tier[k][0 if x["id"] in m.values() else 1 if inside else 2] += 1
    rows.append({"t": t, "model": MODEL[t], "judge": len(ver), "tp": len(m), "dup": len(dup),
                 **{a: len(A[a][t]["instances"]) if t in A[a] else None for a in ("a1", "a2")},
                 **{a + "_firm": sum(i["tier"] == "firm" for i in A[a][t]["instances"]) if t in A[a] else None
                    for a in ("a1", "a2")}})

print(f"\n{'tr':3} {'model':13} {'a1':>3} {'a2':>3} | {'judge':>5} {'match':>5} {'2nd':>3}")
for x in rows:
    f = lambda v: "-" if v is None else v
    print(f"{x['t']:3} {x['model']:13} {f(x['a1']):>3} {f(x['a2']):>3} | {x['judge']:>5} {x['tp']:>5} {x['dup']:>3}")
n = sum(x["judge"] for x in rows); tp = sum(x["tp"] for x in rows); dp = sum(x["dup"] for x in rows)
print(f"\njudge entries: {n} = {tp} match a key entry + {dp} land on an already-matched entry "
      f"+ {n - tp - dp} match nothing")
print(f"  the {n - tp - dp} that match nothing, by what the annotators said about that spot: {why_counts}")
print("key entries both annotators found, by tier: matched / inside a judge span / missed")
for k, (a, b, c) in hit_by_tier.items():
    print(f"  {k:10} {a:3} / {b:3} / {c:3}")

B = [x for x in rows if x["t"] in both]
print(f"\nagreement on the {len(B)} double-counted traces (Spearman, mean abs. difference per trace):")
for u, v in (("judge", "a1"), ("judge", "a2"), ("a1", "a2")):
    print(f"  {u:5} vs {v}: {P.spearman([x[u] for x in B], [x[v] for x in B]):.2f}   "
          f"{sum(abs(x[u] - x[v]) for x in B) / len(B):.1f}")

print("\nnewer/older, per-trace means, judge and annotator on the SAME traces:")
for a in ("a1", "a2"):
    for key, label in ((a, "all"), (a + "_firm", "firm")):
        out = []
        for old, new in PAIRS:
            mean = lambda m, k: [sum(x[k] for x in R) / len(R) for R in [[x for x in rows if x["model"] == m and x[a] is not None]]][0]
            lo, hi = mean(old, key), mean(new, key)
            jlo, jhi = mean(old, "judge"), mean(new, "judge")
            nn = [sum(x["model"] == m and x[a] is not None for x in rows) for m in (old, new)]
            out.append(f"{new} (n={nn[0]}+{nn[1]}): {a} {hi / lo:.2f}, judge {jhi / jlo:.2f}" if lo and jlo else f"{new}: n/a")
        print(f"  {a} {label:4}  " + "   ".join(out))
