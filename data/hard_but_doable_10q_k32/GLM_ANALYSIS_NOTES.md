# GLM on hard-but-doable-10 (k=32) — run notes and caveats

10 problems x 32 samples = 320 trials/model. Zero API errors and zero zero-token
trials throughout. Per-trial data in `glm_per_trial_metrics.csv` (regenerate with
`code/glm_hard_but_doable_metrics.py`); the ~108MB of raw traces stay uncommitted
in `code/results/`.

- GLM 4.5-5.1: run 2026-09-05/06, `reasoning={"enabled": true}` (log `hard_glm_main.log`)
- GLM 5.2 / 5.3: **re-run 2026-09-14** at `reasoning={"effort":"high"}`
  (log `hard_glm_high_main.log`). Their original runs are archived — see below.

> **Correction, 2026-09-14.** An earlier version of this file reported GLM 5.3 as
> **-18.8pp** below GLM 5.2 and called that pair "the one clean comparison, same
> effort=medium". **Both claims were wrong.** Neither model has a "medium", each
> vendor silently remapped it to a different level, and the gap was an artifact.
> Re-run at a level both support natively, the gap is **-1.9pp**. Details below.

## The headline: an efficiency gain, not a regression

At `effort="high"` — natively supported by both, so no remapping:

| | GLM 5.2 | GLM 5.3 |
|---|---|---|
| accuracy | 290/320 = **90.9%** | 285/320 = **89.1%** |
| median thinking tokens | 17,742 | **3,084** |

Paired over the 10 problems: **-1.9pp, 95% CI [-8.8, +6.2]** (cluster bootstrap;
320 trials are 10 clusters of 32, not 320 independent draws). Indistinguishable
from zero. Truncation is minor and *lower* for 5.3 (14 vs 29 of 320), so it is not
propping the number up.

**GLM 5.3 matches its predecessor's accuracy on 17% of the thinking budget — 5.8x
fewer tokens.** For a reasoning-trace-efficiency paper that is the result.

Caveat: this is matched on the effort *label*, not on compute. The same instruction
buys 5.8x different spend, and that asymmetry is the finding — state it explicitly
or a reader will assume equal budgets.

## Confound 1 — the 40k cap binds unequally by provider (affects 4.5-5.1)

A response that hits the cap emits no `\boxed{}` and grades wrong. Providers did not
honour `max_tokens` consistently: Z.AI let GLM 4.5 reach **78,917 tokens** (29 trials
over cap), Novita the same for 4.7, while StreamLake hard-stopped GLM 5 at exactly
40,000 on 73 trials.

**Censoring rule (`censored_correct`):** a trial whose output exceeded 40,000 tokens
cannot count as correct — a real 40k cap would have cut it before its `\boxed{}`.
A certainty, not an estimate. Affects only 4.5 and 4.7.

| model | effort | raw | censored@40k | median thinking | still truncated | genuine errors |
|-------|--------|-----|--------------|-----------------|-----------------|----------------|
| GLM 5.1 | enabled | 91.2% | **91.2%** | 21,894 | 23 | 5 |
| GLM 5.2 | high    | 90.9% | **90.9%** | 17,742 | 29 | 0 |
| GLM 5.3 | high    | 89.1% | **89.1%** |  3,084 | 14 | 21 |
| GLM 4.5 | enabled | 96.9% | **89.1%** | 15,104 | 29 | 6 |
| GLM 4.7 | enabled | 88.8% | **85.9%** | 15,730 | 40 | 5 |
| GLM 4.6 | enabled | 78.8% | **78.8%** | 15,014 | 66 | 2 |
| GLM 5   | enabled | 76.6% | **76.6%** | 19,487 | 75 | 0 |

Censoring equalises the cap but does not rescue the metric. **GLM 5 has zero genuine
errors**: 75 truncations put its ceiling at 245/320 = 76.6% and it scored exactly
that — it solved every trial it was allowed to finish. For GLM 5 and 4.6, accuracy
here is `1 - truncation_rate` and carries no capability signal. Fix: re-run at
`--max-tokens 120000` (these providers advertise >=200k). Same pathology as
DeepSeek V3.2 (README) and Kimi K2.5/StreamLake (`data/archive/`).

## Confound 2 — effort levels are still not uniform across the seven

`reasoning_effort` is exposed only by GLM 5.2 and 5.3 (all their endpoints); 4.5,
4.6, 4.7, 5 and 5.1 expose it on **none**, so they can only take
`reasoning={"enabled": true}`. An effort-matched run across all seven is impossible.

A 2026-09-14 probe (40 requests, 5 settings, both models, same pins/prompt —
`code/effort_probe.py`; raw output not retained) measured what each
setting actually buys, in reasoning tokens:

| setting | GLM 5.2 | GLM 5.3 | ratio |
|---------|---------|---------|-------|
| low     |  9,007  |   652   | 13.8x |
| high    | 12,643  | 1,123   | 11.3x |
| max     | 24,546  | 14,268  |  1.7x |
| enabled | 10,756  | 7,271   |  1.5x |

Two things follow:

1. **`enabled: true` resolves to the model's own default (near `max`), NOT to
   medium** as OpenRouter's docs state. So the five `enabled` models above ran
   effectively unthrottled — at a *higher* level than the 5.2/5.3 `high` rows.
   Comparing 5.3's 89.1% against them understates it.
2. **GLM 5.3's effort ladder is stretched.** `low` and `high` are genuinely shallow,
   then `max` jumps ~10x. At `high` it spends a tenth of what 5.2 spends at `high`.
   That recalibration is real and independent of the medium bug.

Probe caveat: n=2 per cell, wide spread (5.2 `low` spans 3,725-14,994). Only the
order-of-magnitude gaps are trustworthy; the full sweep put 5.3's `high` median at
3,084, well above the probe's 1,123.

## What was retracted

The earlier trace-level contrast (5.3 median 8 backtrack markers vs 5.2's 32; 6.7
distinct wrong answers per problem vs 1.6; 39% of 5.3 runs under 1,000 thinking
tokens) was computed from the mismatched-effort files. Those measurements are real
but describe two different effort levels, so they **do not** evidence a model
regression. They were pointing at compression, which the matched re-run confirms is
real and accuracy-neutral.

## Open

- Re-run 4.5-5.1 at `--max-tokens 120000`; GLM 5 and 4.6 are pure truncation-rate
  measurements as they stand.
- Kimi K3 and GLM 5.3 need `effort="high"` re-runs on thinking-benchmark-90; both
  currently sit at ~1,050 median thinking tokens there for the same reason.
