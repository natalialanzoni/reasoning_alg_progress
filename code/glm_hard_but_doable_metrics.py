"""Flatten the GLM hard-but-doable-10 k=32 runs into one per-trial metrics table.

Lets the trace-level analysis (backtracking density, recall openers, truncation
censoring) be reproduced without committing the 108MB of raw reasoning traces.

Usage:  python code/glm_hard_but_doable_metrics.py
Writes: data/hard_but_doable_10q_k32/glm_per_trial_metrics.csv
"""
import csv, json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "code" / "results"
OUT = ROOT / "data" / "hard_but_doable_10q_k32" / "glm_per_trial_metrics.csv"
CAP = 40_000  # common requested cap; see CENSORING note in the analysis README

MODELS = ["glm_4_5", "glm_4_6", "glm_4_7", "glm_5", "glm_5_1", "glm_5_2", "glm_5_3"]
EFFORT = {"glm_5_2": "medium", "glm_5_3": "medium"}  # rest ran reasoning={"enabled":true}

BACKTRACK = re.compile(
    r"\b(wait|hmm|actually|let me (re)?check|double-check|recompute|verify|but that|hold on)\b", re.I)
RECALL = re.compile(r"\b(known|classic|recall|I remember|memor|seen this|standard problem)\b", re.I)

rows = []
for m in MODELS:
    d = SRC / f"{m}_shallow_pass"
    res = json.loads((d / f"{m}_thinking_benchmark_hard_but_doable_10.json").read_text())
    traces = {r["task_id"]: r["reasoning_texts"]
              for r in json.loads((d / f"{m}_thinking_benchmark_hard_but_doable_10_reasoning_traces.json").read_text())}
    for r in res:
        for i in range(len(r["correct"])):
            txt = traces[r["task_id"]][i]
            tot = r["total_completion_tokens"][i]
            rows.append(dict(
                model=m, effort=EFFORT.get(m, "enabled"), task_id=r["task_id"], trial=i,
                provider=r["providers_used"][i], gold_answer=r["gold_answer"],
                extracted_answer=r["extracted_answers"][i],
                correct=int(bool(r["correct"][i])),
                answer_in_boxed=int(bool(r["answer_in_boxed"][i])),
                thinking_tokens=r["thinking_tokens"][i], answer_tokens=r["answer_tokens"][i],
                total_completion_tokens=tot,
                over_cap=int(tot > CAP),          # provider ignored max_tokens
                at_cap=int(tot == CAP),           # hard-truncated by the cap
                # censored_correct: uniform 40k cap. A response still emitting at
                # token 40,000 would have been cut before its \boxed{}, so it cannot
                # count as correct -- this removes the provider advantage that let
                # GLM 4.5/4.7 run to 78,917 tokens while others hard-stopped at 40,000.
                censored_correct=int(bool(r["correct"][i]) and tot <= CAP),
                trace_chars=len(txt),
                backtrack_markers=len(BACKTRACK.findall(txt)),
                recall_opener=int(bool(RECALL.search(txt[:300]))),
                error=r["errors"][i] or "",
            ))

OUT.parent.mkdir(parents=True, exist_ok=True)
with OUT.open("w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
print(f"wrote {OUT}  ({len(rows)} trials, {len(MODELS)} models)")
