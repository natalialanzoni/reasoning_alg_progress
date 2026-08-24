#!/usr/bin/env bash
# Submit hard-but-doable-10 at MAX reasoning effort for a set of GPT models.
# Each model = one Batch API job (10 problems x k samples). Runs them in
# parallel; each polls to completion and writes results into OUTDIR.
#
# NOTE: not every model accepts effort="max" — older models (e.g. gpt-5) may
# cap at "high" and error on "max". If a job fails with an effort error, set
# EFFORT=high (or xhigh) for that model. Check each model's log in OUTDIR.
#
# Review, then run:  bash run_max_reasoning.sh
set -euo pipefail
cd "$(dirname "$0")"

# ---- config ---------------------------------------------------------------
PY=./venv/bin/python
SCRIPT=code/benchmark_math_dist.py
DATASET=tyrtleli/thinking-benchmark-hard-but-doable-10
EFFORT=max
K=8
MAX_TOKENS=40000
OUTDIR="$(pwd)/data/max_reasoning_effort"
MODELS=(gpt-5 gpt-5.4 gpt-5.6-sol)
# ---------------------------------------------------------------------------

mkdir -p "$OUTDIR"
echo "Effort=$EFFORT  k=$K  max_tokens=$MAX_TOKENS  ->  $OUTDIR"
echo "Models: ${MODELS[*]}"

for M in "${MODELS[@]}"; do
  echo ">>> launching $M ($EFFORT)"
  "$PY" "$SCRIPT" \
    --model "$M" \
    --effort "$EFFORT" \
    --max-tokens "$MAX_TOKENS" \
    --n-samples "$K" \
    --dataset "$DATASET" \
    --run-name "$OUTDIR" \
    > "$OUTDIR/${M}_${EFFORT}.log" 2>&1 &
done

wait
echo "All $EFFORT jobs finished. Results + configs in $OUTDIR"
