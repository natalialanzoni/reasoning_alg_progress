#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Hard-but-doable sweep (k=32) for one OpenAI model, pinned to the settings every
# other model in that set was run at.
#
#   bash scripts/run_openai_hard.sh gpt-5.1
#
# Companion to scripts/run_openai_shallow.sh (k=8 over the 45 canonical problems).
# This one is the 10-problem hard-but-doable slice at k=32, which is what Figure 1
# row 3, Figure 2 and the pooled Figure 5 violins read.
#
# Settings, matching data/hard_but_doable_10q_k32/*_requests.jsonl:
#   endpoint /v1/responses | reasoning.effort = medium | max_output_tokens = 40000
#   dataset tyrtleli/thinking-benchmark-hard-but-doable-10 | split test | k = 32
#
# No --task-ids-file: the dataset IS the 10 problems. No --tag: the output name is
# derived from the dataset, giving <model>_medium_thinking_benchmark_hard_but_doable_10.json
# which is what the figure scripts expect.
#
# --max-tokens DEFAULTS TO 100000 in benchmark_math_dist.py. Every published run
# used 40000. Pinned below; do not drop the flag.
# ---------------------------------------------------------------------------
set -euo pipefail
cd "$(dirname "$0")/.."
PY=./venv/bin/python

MODEL="${1:?usage: bash scripts/run_openai_hard.sh <model-id>}"
EFFORT="medium"
K=32
MAXTOK=40000                                 # <-- comparability cap
DATASET="tyrtleli/thinking-benchmark-hard-but-doable-10"
SPLIT="test"
RUN_NAME="hard_but_doable_10q_k32"           # shared dir: every model lands here
RUN_DIR="code/results/${RUN_NAME}"
DEST="data/${RUN_NAME}"
mkdir -p "$RUN_DIR"

echo "model=$MODEL  effort=$EFFORT  k=$K  max_tokens=$MAXTOK"
echo "dataset=$DATASET"
echo

"$PY" - "$RUN_DIR/${MODEL}_run_config_hard.json" <<PYEOF
import json, subprocess, sys, datetime
cfg = {
    "model": "$MODEL", "effort": "$EFFORT", "n_samples": $K,
    "max_output_tokens": $MAXTOK, "endpoint": "/v1/responses",
    "dataset": "$DATASET", "split": "$SPLIT", "run_name": "$RUN_NAME",
    # not what we ran -- the reference runs whose saved requests these settings
    # were checked against, field by field
    "settings_verified_against": "data/hard_but_doable_10q_k32/*_requests.jsonl",
    "git_commit": subprocess.getoutput("git rev-parse HEAD"),
    "utc": datetime.datetime.utcnow().isoformat() + "Z",
}
json.dump(cfg, open(sys.argv[1], "w"), indent=2)
print("provenance ->", sys.argv[1]); print(json.dumps(cfg, indent=2))
PYEOF

"$PY" code/benchmark_math_dist.py \
    --model "$MODEL" \
    --effort "$EFFORT" \
    --n-samples "$K" \
    --max-tokens "$MAXTOK" \
    --dataset "$DATASET" \
    --split "$SPLIT" \
    --run-name "$RUN_NAME"

RESULT="$RUN_DIR/${MODEL}_${EFFORT}_thinking_benchmark_hard_but_doable_10.json"

echo
echo "=== verifying the run ==="
"$PY" code/verify_run.py "$RESULT" --cap "$MAXTOK" || true

# Copy ONLY this model's files. The run dir is shared across every model in the
# hard-but-doable set, so a blanket cp would re-copy (and could clobber) others.
mkdir -p "$DEST"
cp "$RUN_DIR/${MODEL}"_* "$DEST"/ 2>/dev/null || {
  echo "  no files matched ${MODEL}_* -- check the output name above"; exit 1; }

echo
echo "=== regrading (NEVER plot an ungraded run: see archive/README.md) ==="
"$PY" code/apply_regrade.py                 # dry run: shows what would flip
echo
read -r -p "apply the regrade to data/ ? [y/N] " ok
[ "$ok" = "y" ] && "$PY" code/apply_regrade.py --write || echo "  skipped -- run: ./venv/bin/python code/apply_regrade.py --write"

echo
echo "Done. -> $DEST/"
echo "Next: add the model to OPUS_HARD10_K32 / fs.GPT_HARD as appropriate, then"
echo "rerun bash scripts/make_paper_figs.sh."
