# Archived: runs that sent an invalid `reasoning_effort="medium"`

`code/benchmark_math_open_source.py` had
`_EFFORT_CAPABLE = {"DeepSeek V4 Pro 0813", "Kimi K3", "GLM 5.3", "GLM 5.2"}`
and sent those four `reasoning={"effort":"medium"}`. **None of the four has a
"medium".** An unsupported effort value is not an error you will ever see —
vendors silently remap it, so the run completes clean while measuring a level you
did not choose. Every affected run here logged **zero errors**.

| model | accepted values | what `medium` became |
|-------|-----------------|----------------------|
| GLM 5.2 | max, xhigh, high, medium, low, minimal, none | remapped to **high** (vendor-documented) |
| GLM 5.3 | max, high, low only | errors natively -> OpenRouter remapped upstream |
| Kimi K3 | low, high, max (default max) | not a value -> remapped |
| DeepSeek V4 Pro 0813 | high, max | low/medium -> high (never run; no files) |

Sources: docs.z.ai/guides/capabilities/thinking, platform.kimi.ai/docs/guide/
use-reasoning-effort, api-docs.deepseek.com/guides/thinking_mode/

## The signature

On thinking-benchmark-90 every model given `{"enabled": true}` produced a median
of 14,733-22,282 reasoning tokens. GLM 5.3 produced **1,034** and Kimi K3 **1,086**
— roughly a 15x collapse. Their accuracies (73.7% and 67.3%) measure a remapped
effort level, not the model.

## Files here

- `glm_5_3_thinking_benchmark_90.json` — 73.7%, median 1,034 thinking tokens
- `kimi_k3_thinking_benchmark_90.json` — 67.3%, median 1,086 thinking tokens
- `glm_5_2_thinking_benchmark_hard_but_doable_10.json` — 94.1%
- `glm_5_3_thinking_benchmark_hard_but_doable_10.json` — 75.3%

The two hard-but-doable files are superseded by the `_high` re-run in
`data/hard_but_doable_10q_k32/`. They are kept because the published trace-level
analysis (backtrack-marker density, distinct-wrong-answer counts) was computed
from them; their reasoning traces are in
`code/results/archive_medium_run_2026-09-05/` (gitignored, 15MB).

## What this invalidated

The headline claim that GLM 5.3 was **-18.8pp** below GLM 5.2 was an artifact of
the two models landing on different effort levels. Re-run at `effort="high"` —
natively supported by both, so no remapping — the gap is **-1.9pp, 95% CI
[-8.8, +6.2]**: indistinguishable from zero. GLM 5.3 reaches that on a median of
3,084 thinking tokens against GLM 5.2's 17,742, i.e. **5.8x fewer**. The real
result is an efficiency gain, not a regression.

## Not archived

`data/glm_5_2_shallow_pass/glm_5_2_thinking_benchmark_90.json` (86.4%, median
17,292) also ran at the invalid `medium`, but Z.AI maps medium->high and the
resulting budget sits inside the 14.7k-22.3k range of its `enabled` siblings, so
the number is usable. Caveat: it is nominally `high` where every other model in
that set is at its own default. Re-run it if you need the set strictly uniform.

Kimi K3 needs a re-run at `effort="high"` before its benchmark-90 number is
citable. GLM 5.3's benchmark-90 likewise.
