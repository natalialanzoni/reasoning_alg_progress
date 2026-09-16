#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Benchmark o1 on the hard-but-doable-10 set (k=32), matching the o3 run so o1
# drops into Fig 2 / Fig 5 / CV as the earliest GPT anchor.
#
# Verified against data/hard_but_doable_10q_k32/*_requests.jsonl:
#   endpoint /v1/responses | reasoning.effort=medium | max_output_tokens=40000
#   dataset tyrtleli/thinking-benchmark-hard-but-doable-10 | k=32
# (10 problems, no id filter — the dataset IS the hard-but-doable set.)
#
#   bash code/run_o1_hard.sh
# ---------------------------------------------------------------------------
set -euo pipefail
cd "$(dirname "$0")/.."
PY=./venv/bin/python

MODEL="o1"
EFFORT="medium"
K=32
MAXTOK=40000
DATASET="tyrtleli/thinking-benchmark-hard-but-doable-10"
SPLIT="test"
RUN_NAME="hard_but_doable_10q_k32"

RUN_DIR="code/results/${RUN_NAME}"
DEST="data/${RUN_NAME}"
mkdir -p "$RUN_DIR"

"$PY" - "$RUN_DIR/o1_run_config_hard.json" <<PYEOF
import json, subprocess, sys, datetime
cfg = {"model":"$MODEL","effort":"$EFFORT","n_samples":$K,"max_output_tokens":$MAXTOK,
       "endpoint":"/v1/responses","dataset":"$DATASET","split":"$SPLIT","run_name":"$RUN_NAME",
       "matches":"data/hard_but_doable_10q_k32/*_requests.jsonl",
       "git_commit":subprocess.getoutput("git rev-parse HEAD"),
       "utc":datetime.datetime.utcnow().isoformat()+"Z"}
json.dump(cfg, open(sys.argv[1],"w"), indent=2); print(json.dumps(cfg, indent=2))
PYEOF

"$PY" code/benchmark_math_dist.py \
    --model "$MODEL" \
    --effort "$EFFORT" \
    --n-samples "$K" \
    --max-tokens "$MAXTOK" \
    --dataset "$DATASET" \
    --split "$SPLIT" \
    --run-name "$RUN_NAME"

mkdir -p "$DEST"
cp "$RUN_DIR"/o1_* "$DEST"/ 2>/dev/null || true
echo
echo "Done. Result copied to $DEST/"
echo "Output file: $DEST/o1_${EFFORT}_thinking_benchmark_hard_but_doable_10.json"
