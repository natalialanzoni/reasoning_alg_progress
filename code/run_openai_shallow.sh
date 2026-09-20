#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Shallow-pass sweep for one OpenAI model, pinned to EXACTLY the settings every
# other model in the paper was run at, so the result drops straight into the
# figures without a caveat.
#
#   bash code/run_openai_shallow.sh gpt-5.1
#   bash code/run_openai_shallow.sh o4-mini
#
# Settings, verified against data/o3_shallow_pass/o3_medium_thinking_bench_requests.jsonl:
#   endpoint /v1/responses | reasoning.effort = medium | max_output_tokens = 40000
#   dataset tyrtleli/thinking-benchmark-90 | split test | k = 8
#   restricted to the 45 canonical problems (code/canon45_ids.txt)
#
# --max-tokens DEFAULTS TO 100000 in benchmark_math_dist.py. Every published run
# used 40000. It is pinned below; do not drop the flag.
#
# NOTE ON MODEL IDS (checked 2026-09-20 against /v1/models):
#   gpt-5.1   exists (also pinned: gpt-5.1-2025-11-13)
#   o4        DOES NOT EXIST -- only o4-mini. o4-mini is a different size tier
#             from the rest of the frontier series, so adding it to the GPT
#             trend line mixes tiers; treat it as its own series or leave it out.
# Both accept reasoning.effort = medium and echo it back (probed, not assumed).
# ---------------------------------------------------------------------------
set -euo pipefail
cd "$(dirname "$0")/.."
PY=./venv/bin/python

MODEL="${1:?usage: bash code/run_openai_shallow.sh <model-id>}"
EFFORT="medium"
K=8
MAXTOK=40000                                 # <-- comparability cap
DATASET="tyrtleli/thinking-benchmark-90"
SPLIT="test"
TAG="thinking_bench"
IDS="code/canon45_ids.txt"

SLUG="$(echo "$MODEL" | tr -d '-')"          # gpt-5.1 -> gpt5.1 ; o4-mini -> o4mini
RUN_NAME="${SLUG}_shallow_pass"
RUN_DIR="code/results/${RUN_NAME}"
DEST="data/${RUN_NAME}"
mkdir -p "$RUN_DIR"

echo "model=$MODEL  effort=$EFFORT  k=$K  max_tokens=$MAXTOK  ids=$IDS"
echo "run_name=$RUN_NAME"
echo

# ---- provenance: record what we ran at, BEFORE running -------------------
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
print("provenance ->", sys.argv[1]); print(json.dumps(cfg, indent=2))
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

RESULT="$RUN_DIR/${MODEL}_${EFFORT}_${TAG}.json"

# ---- checks that fail silently otherwise (README run hygiene) -------------
echo
echo "=== verifying the run ==="
"$PY" code/verify_run.py "$RESULT" --cap "$MAXTOK" || true

# ---- promote into data/, THEN regrade -------------------------------------
# apply_regrade.py walks everything under data/ and takes no path argument, so the
# file has to be in place first. It only ever flips wrong->correct and never
# demotes, so re-running it across the whole tree is idempotent and safe.
mkdir -p "$DEST"
cp "$RUN_DIR"/* "$DEST"/

echo
echo "=== regrading (NEVER plot an ungraded run: see archive/README.md) ==="
"$PY" code/apply_regrade.py                 # dry run: shows what would flip
echo
read -r -p "apply the regrade to data/ ? [y/N] " ok
[ "$ok" = "y" ] && "$PY" code/apply_regrade.py --write || echo "  skipped -- run: ./venv/bin/python code/apply_regrade.py --write"

echo
echo "Done. -> $DEST/"
echo "Next: add the model to MAIN_K8 in code/paper_figures_71226.py with its release"
echo "date, then rerun bash code/make_paper_figs.sh."
