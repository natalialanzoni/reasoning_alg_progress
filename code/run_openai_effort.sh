#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Reasoning-effort robustness sweep: one OpenAI model at LOW or HIGH effort,
# pinned to the settings every other model in that appendix figure was run at.
#
#   bash code/run_openai_effort.sh gpt-5.1 low
#   bash code/run_openai_effort.sh gpt-5.1 high
#
# Feeds figure_effort_ft.py -> fig_effort (appendix: trace length by effort).
# Companions: run_openai_shallow.sh (k=8, 45 problems, medium)
#             run_openai_hard.sh    (k=32, hard-but-doable-10, medium)
#
# Settings, verified against data/low_reasoning_effort/*_requests.jsonl and
# data/high_reasoning_effort/*_requests.jsonl (all 80 requests each, checked
# field by field on 2026-09-20):
#   endpoint /v1/responses | reasoning.effort = low|high | max_output_tokens = 40000
#   dataset tyrtleli/thinking-benchmark-hard-but-doable-10 | split test | k = 8
#
# NOTE THE k. This is k=8, NOT the k=32 used by run_openai_hard.sh. The effort
# figure's runs are 80 requests = 10 problems x 8 samples. Using 32 here would
# make the new model incomparable with every other point on that figure.
#
# --max-tokens DEFAULTS TO 100000 in benchmark_math_dist.py. Every published run
# used 40000. Pinned below; do not drop the flag.
#
# The medium arm of that figure comes from the k=32 hard-but-doable runs, so do
# NOT run medium here -- it already exists via run_openai_hard.sh.
# ---------------------------------------------------------------------------
set -euo pipefail
cd "$(dirname "$0")/.."
PY=./venv/bin/python

MODEL="${1:?usage: bash code/run_openai_effort.sh <model-id> <low|high>}"
EFFORT="${2:?usage: bash code/run_openai_effort.sh <model-id> <low|high>}"
case "$EFFORT" in
  low|high) ;;
  medium) echo "medium already exists via run_openai_hard.sh (k=32); refusing"; exit 1 ;;
  *) echo "effort must be low or high (got '$EFFORT')"; exit 1 ;;
esac

K=8
MAXTOK=40000                                 # <-- comparability cap
DATASET="tyrtleli/thinking-benchmark-hard-but-doable-10"
SPLIT="test"
RUN_NAME="${EFFORT}_reasoning_effort"        # shared dir, one per effort level
RUN_DIR="code/results/${RUN_NAME}"
DEST="data/${RUN_NAME}"
mkdir -p "$RUN_DIR"

echo "model=$MODEL  effort=$EFFORT  k=$K  max_tokens=$MAXTOK"
echo "dataset=$DATASET  ->  $DEST/"
echo

"$PY" - "$RUN_DIR/${MODEL}_run_config_${EFFORT}.json" <<PYEOF
import json, subprocess, sys, datetime
cfg = {
    "model": "$MODEL", "effort": "$EFFORT", "n_samples": $K,
    "max_output_tokens": $MAXTOK, "endpoint": "/v1/responses",
    "dataset": "$DATASET", "split": "$SPLIT", "run_name": "$RUN_NAME",
    # not what we ran -- the reference runs whose saved requests these settings
    # were checked against, field by field
    "settings_verified_against": "data/${EFFORT}_reasoning_effort/*_requests.jsonl",
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

# Copy ONLY this model's files: the effort dirs are shared across models, so a
# blanket cp would re-copy (and could clobber) the others.
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
echo "Next: add \"$MODEL\" to the ${EFFORT} list in code/figure_effort_ft.py, then"
echo "rerun: MPLBACKEND=Agg ./venv/bin/python code/figure_effort_ft.py"
