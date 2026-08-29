#!/usr/bin/env bash
# Submit hard-but-doable-10 at LOW reasoning effort for a set of GPT models.
# Each model = one Batch API job (10 problems x k samples). Runs them in
# parallel; each polls to completion and writes results into OUTDIR.
#
# Review, then run:  bash run_low_reasoning.sh
set -euo pipefail
cd "$(dirname "$0")"

# ---- config ---------------------------------------------------------------
PY=./venv/bin/python
SCRIPT=code/benchmark_math_dist.py
DATASET=tyrtleli/thinking-benchmark-hard-but-doable-10
EFFORT=low
K=8
MAX_TOKENS=40000
OUTDIR="$(pwd)/data/low_reasoning_effort"
MODELS=(o3 gpt-5 gpt-5.2 gpt-5.4 gpt-5.5 gpt-5.6-sol)
# ---------------------------------------------------------------------------
# Resume-safe: any model whose result json already exists is skipped
# ("Nothing new to run"); only missing models/problems are (re)submitted.
# So you can just list every model — completed ones won't re-run or re-charge.

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
