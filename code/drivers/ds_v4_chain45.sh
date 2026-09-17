#!/usr/bin/env bash
# DeepSeek chain, 45-problem sample (--solutions-only), k=8, cap 40k.
# Replaces ds_v4pro.sh + ds_rest2_45.sh: one driver, no file-watching handoff,
# so nothing gets pkill'd mid-repair. R1-0528 runs concurrently in ds_r1.sh
# (different provider, no rate contention).
REPO=/home/nfl234/reasoning_trace_efficiency/reasoning_alg_progress
cd "$REPO" || exit 1
source ~/.bash_profile 2>/dev/null
: "${OPENROUTER_API_KEY:?key missing}"

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
  echo "=== $1 ${3:-noeffort} main (workers=6) $(date '+%F %T') ==="
  ./venv/bin/python -u code/benchmark_math_open_source.py --models "$1" "${eff[@]}" \
    --solutions-only --n-samples 8 --max-tokens 40000 \
    --dataset tyrtleli/thinking-benchmark-90 --workers 6 >> "${4}_main.log" 2>&1
  echo "  main rc=$? zeros=$(zeros $2 $sfx) $(date '+%F %T')"
  for p in 1 2 3; do
    z=$(zeros $2 $sfx); [ "$z" -eq 0 ] && { echo "  $1 ${3:-noeffort} CLEAN"; break; }
    echo "  repair $p (zeros=$z) $(date '+%F %T')"
    ./venv/bin/python -u code/benchmark_math_open_source.py --models "$1" "${eff[@]}" \
      --solutions-only --n-samples 8 --max-tokens 40000 \
      --dataset tyrtleli/thinking-benchmark-90 --workers 2 >> "${4}_repair${p}.log" 2>&1
    echo "  repair $p done zeros=$(zeros $2 $sfx) $(date '+%F %T')"
  done
}
pass "DeepSeek V4 Pro" deepseek_v4_pro high ds45_v4pro_high
pass "DeepSeek V4 Pro" deepseek_v4_pro max  ds45_v4pro_max
pass "DeepSeek V4 Pro" deepseek_v4_pro low  ds45_v4pro_low
pass "DeepSeek V3.2"   deepseek_v3_2   ""   ds45_v3_2
echo "CHAIN DONE $(date '+%F %T')"
