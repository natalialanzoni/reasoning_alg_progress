#!/usr/bin/env bash
# Verify each sweep file the moment it appears. Polls on a 60s cycle (cheap: one
# stat per known path, no filesystem traversal -- this is a shared node).
REPO=/home/nfl234/reasoning_trace_efficiency/reasoning_alg_progress
cd "$REPO" || exit 1
R=code/results
FILES=(
  "$R/deepseek_r1_0528_shallow_pass/deepseek_r1_0528_thinking_benchmark_90.json"
  "$R/deepseek_v3_1_terminus_shallow_pass/deepseek_v3_1_terminus_thinking_benchmark_90.json"
  "$R/deepseek_v3_2_shallow_pass/deepseek_v3_2_thinking_benchmark_90.json"
  "$R/deepseek_v4_pro_shallow_pass/deepseek_v4_pro_thinking_benchmark_90_high.json"
  "$R/deepseek_v4_pro_shallow_pass/deepseek_v4_pro_thinking_benchmark_90_low.json"
  "$R/deepseek_v4_pro_shallow_pass/deepseek_v4_pro_thinking_benchmark_90_max.json"
)
declare -A seen
while :; do
  all=1
  for f in "${FILES[@]}"; do
    if [ -f "$f" ]; then
      if [ -z "${seen[$f]}" ]; then
        seen[$f]=1
        echo "############ $(date '+%F %T')  $f"
        ./venv/bin/python -u code/verify_run.py "$f" --cap 40000 2>&1
        ./venv/bin/python -u code/recover_trace_answers.py "$f" 2>&1   # report only
      fi
    else
      all=0
    fi
  done
  [ "$all" = 1 ] && { echo "ALL SIX VERIFIED $(date '+%F %T')"; break; }
  sleep 60
done
