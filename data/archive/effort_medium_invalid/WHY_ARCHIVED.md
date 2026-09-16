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
- `glm_5_2_thinking_benchmark_90.json` — 86.4%, median 17,292 thinking tokens
  (archived 2026-09-15; see "Superseded" below)
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

## Superseded (updated 2026-09-15)

`glm_5_2_thinking_benchmark_90.json` (86.4%, median 17,292) was originally kept
here rather than archived: it ran at the invalid `medium`, but Z.AI documents
medium->high for GLM 5.2, and the resulting budget sat inside the 14.7k-22.3k
range of its `enabled` siblings, so the number was judged usable.

It is now archived anyway. Both GLM 5.2 and GLM 5.3 were re-run on
thinking-benchmark-90 at an explicit `effort="high"` on 2026-09-15
(tag `_high`, log `glm_k8_high_main.log`) so that the k=8 and k=32 layers of the
GLM figure are at a matched, natively-supported level for both models. Relying on
an undocumented vendor remap is not the same as requesting the level directly.

## Still outstanding

`kimi_k3_thinking_benchmark_90.json` needs a re-run at `effort="high"` before
Kimi K3's benchmark-90 number is citable. That has not been done — Kimi K3
currently has **no valid k=8 result** in `data/`.
