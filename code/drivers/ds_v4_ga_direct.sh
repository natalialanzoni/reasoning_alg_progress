#!/usr/bin/env bash
# DeepSeek V4 Pro GA via DeepSeek's OWN API (api.deepseek.com), 45-problem
# sample, k=8, cap 40k, at all three effort levels.
#
# This is NEW DATA, a different model from the OpenRouter "DeepSeek V4 Pro"
# results: OpenRouter's deepseek/deepseek-v4-pro is a fixed 2026-04-24 listing,
# while deepseek-v4-pro on the direct API is a rolling pointer to the latest GA
# build (release note 2026-08-13). Results land in deepseek_v4_pro_ga_shallow_pass/
# so the two can never be merged by accident.
#
# Needs DEEPSEEK_API (in ~/.bashrc, not ~/.bash_profile).
REPO=/home/nfl234/reasoning_trace_efficiency/reasoning_alg_progress
cd "$REPO" || exit 1
source ~/.bashrc 2>/dev/null
: "${DEEPSEEK_API:?DEEPSEEK_API not set}"

zeros() { # $1=effort
  ./venv/bin/python -c "
import json
try:
    d=json.load(open('code/results/deepseek_v4_pro_ga_shallow_pass/deepseek_v4_pro_ga_thinking_benchmark_90_$1.json'))
    print(sum(1 for r in d for v in r['total_completion_tokens'] if v==0))
except Exception: print(-1)
"
}
pass() { # $1=effort
  echo "=== GA effort=$1 main (workers=8) $(date '+%F %T') ==="
  ./venv/bin/python -u code/benchmark_math_open_source.py \
    --models "DeepSeek V4 Pro GA" --effort "$1" --solutions-only \
    --n-samples 8 --max-tokens 40000 \
    --dataset tyrtleli/thinking-benchmark-90 --workers 8 >> "ds45_v4ga_$1_main.log" 2>&1
  echo "  main rc=$? zeros=$(zeros $1) $(date '+%F %T')"
  for p in 1 2 3; do
    z=$(zeros $1); [ "$z" -eq 0 ] && { echo "  effort=$1 CLEAN"; break; }
    echo "  repair $p (zeros=$z)"
    ./venv/bin/python -u code/benchmark_math_open_source.py \
      --models "DeepSeek V4 Pro GA" --effort "$1" --solutions-only \
      --n-samples 8 --max-tokens 40000 \
      --dataset tyrtleli/thinking-benchmark-90 --workers 4 >> "ds45_v4ga_$1_repair${p}.log" 2>&1
    echo "  repair $p done zeros=$(zeros $1)"
  done
}
for EFF in high low max; do pass "$EFF"; done
echo "V4 GA DIRECT CHAIN DONE $(date '+%F %T')"
