#!/usr/bin/env bash
# DeepSeek family on ONE provider (SiliconFlow, fp8), 45-problem sample, k=8,
# cap 40k. Single provider so sampling defaults and quantization are constant
# across the series -- we set no temperature/top_p/seed, so provider defaults
# would otherwise be a confound in the within-family comparison.
#
# R1-0528 is NOT here: it was already running on SiliconFlow at the right
# settings when this was written, and is being left to finish. If that run dies,
# add:  pass "DeepSeek R1 0528" deepseek_r1_0528 "" ds45_r1_0528
#
# Requires ERA_OPENROUTER_V2 (preferred) or OPENROUTER_API_KEY in the environment.
REPO=/home/nfl234/reasoning_trace_efficiency/reasoning_alg_progress
cd "$REPO" || exit 1
source ~/.bash_profile 2>/dev/null
if [ -z "${ERA_OPENROUTER_V2:-}" ] && [ -z "${OPENROUTER_API_KEY:-}" ]; then
  echo "FATAL: no OpenRouter key in the environment"; exit 1
fi
# key source is printed safely by the python script itself (never echo a key here)                

zeros() { # $1=slug $2=suffix
  ./venv/bin/python -c "
import json
try:
    d=json.load(open('code/results/$1_shallow_pass/$1_thinking_benchmark_90$2.json'))
    print(sum(1 for r in d for v in r['total_completion_tokens'] if v==0))
except Exception: print(-1)
"
}
pass() { # $1=label $2=slug $3=effort(may be empty) $4=logprefix
  local eff=() sfx=""
  [ -n "$3" ] && { eff=(--effort "$3"); sfx="_$3"; }
  echo "=== $1 ${3:-noeffort} main (workers=8) $(date '+%F %T') ==="
  ./venv/bin/python -u code/benchmark_math_open_source.py --models "$1" "${eff[@]}" \
    --solutions-only --n-samples 8 --max-tokens 40000 \
    --dataset tyrtleli/thinking-benchmark-90 --workers 8 >> "${4}_main.log" 2>&1
  echo "  main rc=$? zeros=$(zeros $2 $sfx) $(date '+%F %T')"
  for p in 1 2 3; do
    z=$(zeros $2 $sfx); [ "$z" -eq 0 ] && { echo "  $1 ${3:-noeffort} CLEAN"; break; }
    echo "  repair $p (zeros=$z) $(date '+%F %T')"
    ./venv/bin/python -u code/benchmark_math_open_source.py --models "$1" "${eff[@]}" \
      --solutions-only --n-samples 8 --max-tokens 40000 \
      --dataset tyrtleli/thinking-benchmark-90 --workers 4 >> "${4}_repair${p}.log" 2>&1
    echo "  repair $p done zeros=$(zeros $2 $sfx) $(date '+%F %T')"
  done
}
# Oldest first: if the clock runs out, the timeline keeps its early anchor.
pass "DeepSeek V3.1 Terminus" deepseek_v3_1_terminus ""     ds45_v3_1_terminus
pass "DeepSeek V3.2"          deepseek_v3_2          ""     ds45_v3_2
pass "DeepSeek V4 Pro"        deepseek_v4_pro        high   ds45_v4pro_high
pass "DeepSeek V4 Pro"        deepseek_v4_pro        low    ds45_v4pro_low
pass "DeepSeek V4 Pro"        deepseek_v4_pro        max    ds45_v4pro_max
echo "SILICONFLOW CHAIN DONE $(date '+%F %T')"
