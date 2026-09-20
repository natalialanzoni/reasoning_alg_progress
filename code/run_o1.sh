#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Benchmark o1 as the earliest GPT anchor, using the SAME settings as every
# other OpenAI/Anthropic run in this paper so it is a fair drop-in.
#
# Verified against data/o3_shallow_pass/o3_medium_thinking_bench_requests.jsonl:
#   endpoint /v1/responses | reasoning.effort=medium | max_output_tokens=40000
#   dataset tyrtleli/thinking-benchmark-90 | k=8 | same INSTRUCTIONS
# Restricted to the 45 canonical problems (code/canon45_ids.txt) — the set the
# figures actually use.
#
#   bash code/run_o1.sh
# ---------------------------------------------------------------------------
set -euo pipefail
cd "$(dirname "$0")/.."                      # repo root
PY=./venv/bin/python

MODEL="o1"                                   # bare alias, exactly as o3 was run
EFFORT="medium"
K=8
MAXTOK=40000                                 # <-- comparability cap (matches all runs)
DATASET="tyrtleli/thinking-benchmark-90"
SPLIT="test"
TAG="thinking_bench"
RUN_NAME="o1_shallow_pass"
IDS="code/canon45_ids.txt"

RUN_DIR="code/results/${RUN_NAME}"
DEST="data/${RUN_NAME}"
mkdir -p "$RUN_DIR"

# ---- provenance: save exactly what we ran at, before we run it -------------
"$PY" - "$RUN_DIR/run_config.json" <<PYEOF
import json, subprocess, sys, datetime
cfg = {
    "model": "$MODEL", "effort": "$EFFORT", "n_samples": $K,
    "max_output_tokens": $MAXTOK, "endpoint": "/v1/responses",
    "dataset": "$DATASET", "split": "$SPLIT", "tag": "$TAG",
    "run_name": "$RUN_NAME", "task_ids_file": "$IDS", "n_task_ids": 45,
    # not what we ran -- the reference run whose saved requests these
    # settings were checked against, field by field
    "settings_verified_against": "data/o3_shallow_pass/o3_medium_thinking_bench_requests.jsonl",
    "git_commit": subprocess.getoutput("git rev-parse HEAD"),
    "utc": datetime.datetime.utcnow().isoformat() + "Z",
}
json.dump(cfg, open(sys.argv[1], "w"), indent=2)
print("wrote provenance ->", sys.argv[1]); print(json.dumps(cfg, indent=2))
PYEOF

# ---- the run --------------------------------------------------------------
"$PY" code/benchmark_math_dist.py \
    --model "$MODEL" \
    --effort "$EFFORT" \
    --n-samples "$K" \
    --max-tokens "$MAXTOK" \
    --dataset "$DATASET" \
    --split "$SPLIT" \
    --tag "$TAG" \
    --run-name "$RUN_NAME" \
    --task-ids-file "$IDS"

# ---- drop into data/ where the figures read -------------------------------
mkdir -p "$DEST"
cp "$RUN_DIR"/* "$DEST"/
echo
echo "Done. Result + provenance copied to $DEST/"
echo "Output file: $DEST/${MODEL}_${EFFORT}_${TAG}.json"
echo "Next: add o1 to MAIN_K8 in code/paper_figures_71226.py at datetime(2024, 12, 17)."
