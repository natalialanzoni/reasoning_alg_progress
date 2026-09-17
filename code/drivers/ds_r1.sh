#!/usr/bin/env bash
# R1-0528, 45-problem sample, k=8, cap 40k. Runs CONCURRENTLY with the V4 Pro
# passes: different provider (siliconflow vs parasail), so no rate contention.
REPO=/home/nfl234/reasoning_trace_efficiency/reasoning_alg_progress
cd "$REPO" || exit 1
source ~/.bash_profile 2>/dev/null
: "${OPENROUTER_API_KEY:?key missing}"
zeros() {
  ./venv/bin/python -c "
import json
try:
    d=json.load(open('code/results/deepseek_r1_0528_shallow_pass/deepseek_r1_0528_thinking_benchmark_90.json'))
    print(sum(1 for r in d for v in r['total_completion_tokens'] if v==0))
except Exception: print(-1)
"
}
run() { ./venv/bin/python -u code/benchmark_math_open_source.py \
    --models "DeepSeek R1 0528" --solutions-only \
    --n-samples 8 --max-tokens 40000 \
    --dataset tyrtleli/thinking-benchmark-90 --workers "$1"; }
echo "=== R1-0528 main (workers=12) $(date '+%F %T') ==="
run 12 >> ds45_r1_0528_main.log 2>&1
echo "  rc=$? zeros=$(zeros) $(date '+%F %T')"
for p in 1 2 3; do
  z=$(zeros); [ "$z" -eq 0 ] && { echo "  CLEAN"; break; }
  echo "  repair $p (zeros=$z)"; run 4 >> "ds45_r1_0528_repair${p}.log" 2>&1
  echo "  repair $p done zeros=$(zeros)"
done
echo "R1-0528 DONE zeros=$(zeros) $(date '+%F %T')"
