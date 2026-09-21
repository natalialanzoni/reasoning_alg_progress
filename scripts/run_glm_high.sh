#!/usr/bin/env bash
# GLM 5.2 + 5.3 on hard-but-doable-10, k=32, at reasoning_effort="high".
# "high" is natively supported by BOTH models, unlike the "medium" the
# 2026-09-05/06 run sent (which each vendor silently remapped differently).
set -u
cd "$(dirname "$0")/.."   # repo root (script moved into scripts/)
LOG=hard_glm_high_driver.log
echo "START $(date '+%F %T')" >> $LOG
./venv/bin/python code/benchmark_math_open_source.py \
    --models "GLM 5.2" "GLM 5.3" \
    --dataset tyrtleli/thinking-benchmark-hard-but-doable-10 \
    --split test \
    --tag thinking_benchmark_hard_but_doable_10_high \
    --n-samples 32 \
    --max-tokens 40000 \
    --workers 8 \
    --fresh >> hard_glm_high_main.log 2>&1
echo "DONE rc=$? $(date '+%F %T')" >> $LOG
