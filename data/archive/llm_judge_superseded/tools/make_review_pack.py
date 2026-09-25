"""Build the RA adjudication pack: N traces per behaviour, judge output vs evidence.

One folder per behaviour so there is no ambiguity about what is being judged:

    for_RA_review/backtracking/   the CONTESTED measurement
    for_RA_review/verification/   the stable one, reviewed as a control

Selection is deliberate, not random: for each model, the two largest
judge-vs-marker disagreements in each direction plus one agreement case. Random
sampling would mostly draw traces where the instruments agree, which carries no
information about which is right.

    python code/llm_judge/make_review_pack.py
"""
import json
import os
import random
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from load_traces import load_all                                    # noqa: E402
from behaviour_table import HIGH_PRECISION, count_backtracking, RECALL  # noqa: E402

OUT = os.path.join(HERE, "for_RA_review")
JUDGED = os.path.join(HERE, "out", "judge_whole_gemini.jsonl")
MODELS = ["gpt-oss-20b", "gpt-oss-120b", "GLM 5.2", "GLM 5.3"]
RX = re.compile("|".join(HIGH_PRECISION), re.I)
VERIF_RX = re.compile(r"\bcheck\w*\b|\bverif\w+\b|\bconfirm\w*\b|\bdouble[- ]check\w*\b"
                      r"|\bsanity\b|\bplug\w*\s+back\b|\bsubstitut\w+\b|\bre-?check\w*\b"
                      r"|\bmakes\s+sense\b|\blet(?:'s| us| me)?\s+test\b", re.I)

DEFN = {
    "backtracking": (
        "the writer realises a path will not work and explicitly abandons it to try a\n"
        "different approach. A routine arithmetic re-check, a clarification, expressing\n"
        "uncertainty ('Hmm'), or re-reading the problem is NOT backtracking."),
    "verification": (
        "the writer explicitly checks their own work -- substituting a result back,\n"
        "testing a special case, comparing against a known value. Simply stating a\n"
        "result, or restating the answer at the end, is NOT verification."),
}


def build(behaviour, n_per_model=5):
    rows = [json.loads(l) for l in open(JUDGED)]
    J = [r for r in rows if r["behaviour"] == behaviour and r.get("count") is not None]
    traces = {(t["model"], t["task_id"], t["sample"]): t for t in load_all()}
    from datasets import load_dataset
    probs = {str(r["id"]): r["problem"]
             for r in load_dataset("tyrtleli/thinking-benchmark-90", split="test")}
    rx = RX if behaviour == "backtracking" else VERIF_RX

    picks = []
    for m in MODELS:
        g = []
        for r in (x for x in J if x["model"] == m):
            t = traces.get((r["model"], r["task_id"], r["sample"]))
            if not t:
                continue
            mk = (count_backtracking(t["cot"], rx, True)[0] if behaviour == "backtracking"
                  else len(rx.findall(t["cot"])))
            g.append((r["count"] - mk, r, mk, t))
        g.sort(key=lambda x: x[0])
        k = n_per_model // 2
        picks += g[:k] + g[-k:] + [g[len(g) // 2]]
    random.seed(3); random.shuffle(picks)

    d = os.path.join(OUT, behaviour)
    os.makedirs(os.path.join(d, "traces"), exist_ok=True)
    index = []
    for i, (_, r, mk, t) in enumerate(picks, 1):
        cot = t["cot"]
        name = (f"{i:02d}_{behaviour}_{r['model'].replace(' ', '').replace('.', '_')}"
                f"_{r['task_id']}_s{r['sample']}")
        open(os.path.join(d, "traces", name + ".txt"), "w").write(cot)
        hits = []
        for mm in rx.finditer(cot):
            s, e = max(0, mm.start() - 260), min(len(cot), mm.end() + 300)
            hits.append((mm.group(0), cot[s:e].replace("\n", " "),
                         bool(RECALL.search(cot[max(0, mm.start() - 400):mm.end() + 400]))))
        raw = r.get("raw") or ""
        with open(os.path.join(d, name + ".md"), "w") as fh:
            fh.write(f"# {behaviour.upper()} — {r['model']}, {r['task_id']} sample {r['sample']}\n\n")
            fh.write(f"**You are judging {behaviour.upper()} in this trace.**\n\n")
            fh.write(f"| | count |\n|---|---:|\n| LLM judge (gemini-2.5-flash) | **{r['count']}** |\n")
            fh.write(f"| string markers (reference only) | **{mk}** |\n\n")
            fh.write(f"**FULL CHAIN OF THOUGHT: [`traces/{name}.txt`](traces/{name}.txt)** — "
                     f"{len(cot):,} chars, {r['tokens']:,} tokens, complete and untruncated.\n\n")
            fh.write("## The problem being solved\n\n> "
                     + probs.get(r["task_id"], "(not found)").replace("\n", "\n> ") + "\n\n")
            fh.write(f"## Definition\n\n{behaviour.capitalize()} = {DEFN[behaviour]}\n\n---\n\n")
            fh.write(f"## 1. What the judge said (complete, {len(raw):,} chars)\n\n```\n{raw}\n```\n\n")
            fh.write(f"**Genuine among the judge's named instances:** ____ of {r['count']}\n\n---\n\n")
            fh.write(f"## 2. What the string markers caught ({mk})\n\n")
            if not hits:
                fh.write("_No marker hits._\n\n")
            for j, (q, ctx, nr) in enumerate(hits[:40], 1):
                fh.write(f"**[{j}]** `{q}`{' — excluded as memory-recall context' if nr else ''}\n\n"
                         f"> ...{ctx}...\n\n")
            if len(hits) > 40:
                fh.write(f"_({len(hits)-40} further marker hits not shown.)_\n\n")
            fh.write("**Genuine among these:** ____\n\n---\n\n")
            fh.write("## 3. Did either instrument MISS anything?\n\n"
                     "Skim the full trace. This is the most valuable part of the review.\n\n"
                     "**Missed instances (quote them):**\n\n- \n- \n\n---\n\n"
                     f"## 4. Your total\n\n**Genuine {behaviour} in this trace:** ____\n")
        index.append((name, r["model"], r["task_id"], r["count"], mk))

    with open(os.path.join(d, "verdicts.csv"), "w") as fh:
        fh.write("file,behaviour,model,task,judge_count,marker_count,"
                 "RA_judge_genuine,RA_marker_genuine,RA_missed,RA_total\n")
        for n, m, tid, j, k in index:
            fh.write(f"{n},{behaviour},{m},{tid},{j},{k},,,,\n")
    return index


if __name__ == "__main__":
    for b in ("backtracking", "verification"):
        idx = build(b)
        print(f"{b}: {len(idx)} sheets -> for_RA_review/{b}/")
