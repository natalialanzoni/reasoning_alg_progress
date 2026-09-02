#!/usr/bin/env bash
# One-shot setup + launch of the open-source (OpenRouter) benchmark on a server.
# The dataset is pulled from HuggingFace at runtime, so NO local data/ is needed —
# just this repo, python3, and OPENROUTER_API_KEY.
#
#   git clone <repo> && cd reasoning_alg_progress
#   export OPENROUTER_API_KEY=sk-or-v1-...
#   screen -S bench          # or tmux
#   bash run_on_server.sh    # edit MODELS/flags below first if you like
#
set -euo pipefail
cd "$(dirname "$0")"

# ---- config (edit to taste) ------------------------------------------------
MODELS=(glm-4 glm-5)
N_SAMPLES=8
MAX_TOKENS=40000
DATASET=tyrtleli/thinking-benchmark-90
WORKERS=16
# ---------------------------------------------------------------------------

: "${OPENROUTER_API_KEY:?Set it first:  export OPENROUTER_API_KEY=sk-or-v1-...}"

# venv + only the deps this benchmark needs (no numpy/matplotlib/etc.)
if [ ! -d venv ]; then
  python3 -m venv venv
fi
./venv/bin/pip install -q --upgrade pip
# antlr4 pinned: sympy 1.14's parse_latex requires exactly 4.11.x, and a newer
# runtime fails at call time inside a bare except -> silent grading degradation.
./venv/bin/pip install -q datasets openai sympy 'antlr4-python3-runtime==4.11.1'

echo "Launching: models=${MODELS[*]}  k=$N_SAMPLES  max_tokens=$MAX_TOKENS  workers=$WORKERS"
./venv/bin/python code/benchmark_math_open_source.py \
  --models "${MODELS[@]}" \
  --n-samples "$N_SAMPLES" \
  --max-tokens "$MAX_TOKENS" \
  --dataset "$DATASET" \
  --workers "$WORKERS"

echo "Done. Results in code/results/<model>_shallow_pass/ — copy them back with scp/rsync."
