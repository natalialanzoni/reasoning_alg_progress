# Kimi K2.5 — archived, provider-capped run (do not use)

Collected 2026-08-29 via OpenRouter pinned to **StreamLake**, which imposed a
hard **32,768-token output ceiling** despite the run requesting 40,000 and the
provider advertising far more.

- 102 of 376 attempts (27.1%) sit at exactly 32,768 tokens
- every one of those scored `correct: false` (a truncated response emits no `\boxed{}`)
- 0 attempts exceeded 32,768 — a hard ceiling, not a coincidence
- recorded accuracy 69.9% is therefore not comparable with the other models,
  which all ran at a 40,000-token budget

StreamLake is no longer a listed endpoint for `moonshotai/kimi-k2.5`, so this
condition cannot be reproduced. Superseded by a re-run pinned to **Phala**
(advertises 235,929 max completion tokens).

Same pathology the top-level README documents for DeepSeek V3.2 (16,384-token
provider cap pinning ~56% of trials).
