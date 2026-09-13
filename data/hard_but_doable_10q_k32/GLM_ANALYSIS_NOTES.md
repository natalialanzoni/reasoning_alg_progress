# GLM on hard-but-doable-10 (k=32) — run notes and caveats

Run: 2026-09-05 → 2026-09-06, single invocation of
`code/benchmark_math_open_source.py`, 10 problems x 32 samples = 320 trials/model.
Log: `hard_glm_main.log`. Zero API errors, zero zero-token trials across all 7 models.

**Do not read the raw accuracy column as capability.** Two independent confounds,
below. Per-trial data for all of this is in `glm_per_trial_metrics.csv`
(regenerate with `code/glm_hard_but_doable_metrics.py`; the 108MB raw traces stay
uncommitted in `code/results/`).

## Confound 1 — the 40k cap binds unequally by provider

A response that hits the output cap emits no `\boxed{}` and grades wrong. Providers
did not honour `max_tokens` consistently: Z.AI let GLM 4.5 run to **78,917 tokens**
(29 trials over cap) and Novita let GLM 4.7 to the same, while StreamLake hard-stopped
GLM 5 at exactly 40,000 on 73 trials. So the raw ranking is substantially a ranking of
which provider ignored the cap.

**Censoring rule (`censored_correct` in the CSV):** a trial whose output exceeded
40,000 tokens cannot count as correct, because a real 40k cap would have cut it before
its `\boxed{}`. This is a certainty, not an estimate. It affects only 4.5 and 4.7.

| model | provider | effort | raw | censored@40k | still truncated | genuine errors |
|-------|----------|--------|-----|--------------|-----------------|----------------|
| GLM 5.2 | Phala      | medium  | 94.1% | **94.1%** |  9 | 10 |
| GLM 5.1 | Baidu      | enabled | 91.2% | **91.2%** | 23 |  5 |
| GLM 4.5 | Z.AI       | enabled | 96.9% | **89.1%** | 29 |  6 |
| GLM 4.7 | Novita     | enabled | 88.8% | **85.9%** | 40 |  5 |
| GLM 4.6 | Novita     | enabled | 78.8% | **78.8%** | 66 |  2 |
| GLM 5   | StreamLake | enabled | 76.6% | **76.6%** | 75 |  0 |
| GLM 5.3 | Z.AI       | medium  | 75.3% | **75.3%** |  6 | 73 |

Censoring equalises the cap but does not rescue the metric. GLM 5 has **zero** genuine
errors: 75 truncations out of 320 put its ceiling at 245/320 = 76.6%, and it scored
exactly 76.6% — it solved every trial it was allowed to finish. For 4.6 and GLM 5,
accuracy here is `1 - truncation_rate` and carries no capability signal.
**Fix: re-run at `--max-tokens 120000`** (all these providers advertise >=200k).
Same pathology as DeepSeek V3.2 (README) and Kimi K2.5/StreamLake
(`data/archive/kimi_k2_5_streamlake_cap32768/WHY_ARCHIVED.md`).

## Confound 2 — `reasoning_effort` is not compute-matched across versions

Only GLM 5.3 and 5.2 are in `_EFFORT_CAPABLE`, so they got
`reasoning={"effort":"medium"}`; the other five got `reasoning={"enabled":true}` with
no effort ceiling. Any effort-held-constant claim across these 7 models is confounded.

The 5.2 vs 5.3 pair is the one clean comparison: same `effort="medium"`, same fp8,
truncation negligible for both (9 vs 6 of 320).

- **Paired difference -18.8pp**, 95% CI **[-29.1, -9.1]** (cluster bootstrap over the
  10 problems — 320 trials are 10 clusters of 32, not 320 independent draws).
  9 of 10 problems worse, sign test p ~ 0.02. The gap is real.
- But the *same string* buys very different compute: median thinking **12,505** tokens
  (5.2) vs **1,482** (5.3). Trials under 1,000 thinking tokens: **1/320** vs **124/320**.

### What 5.3 is actually doing

Not truncation, and not memorised lookup. The traces are complete and coherent — real
setup, real algebra — just in compressed shorthand with no verification pass.

| | GLM 5.2 | GLM 5.3 |
|---|---|---|
| median backtrack/verify markers per trace | 32 | 8 |
| traces with zero such markers | 1/320 | 35/320 |
| distinct wrong answers per problem | 1.6 | 6.7 |

6.7 distinct wrong answers per problem is the signature of unverified arithmetic — a
different slip each trial — not a systematic misunderstanding (5.2's 1.6). Within 5.3,
splitting each problem at its own median trace length: short half 68.8%, long half
81.9%; by overall thinking-token quartile 60.0 / 75.0 / 78.8 / **87.5%**. When 5.3 does
think, it approaches 5.2's 94.1%.

78% of 5.3 traces open with a recall claim ("Known AIME answer 175.") vs 1% for 5.2,
but on inspection it usually floats a half-remembered prior and then discards it and
solves anyway. Treat the recall opener as a stylistic tic, not the failure mode — the
accuracy split on it runs the *other* way (77% vs 69%) and does not support a
memorisation story.

## Open question — the decisive run

Whether GLM 5.3 is a capability regression or pure effort recalibration is **untested**.
One run settles it: 5.3 with `reasoning={"enabled":true}` like its predecessors.
Closes to ~94% => recalibration, and the 19pp gap is the cost of 5.3's default
verification budget. Stays at ~75% => genuine regression.

Until then the supportable claim is about effort calibration, not ability:
*nominal effort labels are not a compute-matched control across model versions.*

## Not in this run

The 5 Kimi models on hard-but-doable-10 (`kimi_jobs_driver.log` JOB 2, started
2026-09-07 06:35) died ~7 min in at "Kimi K3: 60/320". Results are written only after a
model completes, so nothing was saved. Needs a re-run under `nohup`/`setsid`.
