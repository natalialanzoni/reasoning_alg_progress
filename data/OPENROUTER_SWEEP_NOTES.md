# OpenRouter GLM / Kimi sweep — provenance notes

12 open-source models benchmarked via OpenRouter on
`tyrtleli/thinking-benchmark-90` (split=test, 47 problems), k=8 samples,
common output cap 40,000 tokens, `reasoning` enabled.

Collected 2026-08-29 → 2026-09-02. Each provider was pinned
(`provider.only`, `allow_fallbacks=False`) — see `providers_used` per record.

## Data quality

All 12 models are **error-free**: zero attempts with
`total_completion_tokens == 0`, and zero with `thinking_tokens == 0`.
`task_id` sets are identical across all 12 (47 common), so no intersection
loss when comparing models.

Reaching that took repeated passes. Provider HTTP 429s produce zero-token
placeholder records that grade as `correct: false`, i.e. **an API failure is
indistinguishable from a wrong answer** unless you check the token count.
Affected models were re-run until clean (`kimi-k3`: 115 → 174 → 13 → 2 → 0
failed attempts; `kimi-k2.6`: 92 → 42 → 0). Records now carry an `errors`
field (`None` when the call succeeded) so this is checkable directly.

## Caveats for analysis

- **Output-cap truncation.** 0–105 of 376 attempts per model sit at exactly
  40,000 tokens (worst: `glm_5` 105, `kimi_k2_6` 99, `kimi_k2_thinking` 82).
  Mean/SD and p90/p95 of trace length are biased low for those models — the
  same effect the top-level README flags for DeepSeek V3.2. `glm_5_3` (14)
  and `kimi_k2_5` / `kimi_k3` (0) are least affected.
- **Mixed collection dates.** `kimi-k3` and `kimi-k2.6` re-runs were
  collected 2026-09-02, up to four days after the rest. If a provider changed
  a deployment in between, that is an uncontrolled variable for those two
  models only; `providers_used` will not reveal it.
- Reasoning traces (`*_reasoning_traces.json`, ~225 MB) are **not** committed,
  matching the existing `data/` convention. They remain in `code/results/`.
