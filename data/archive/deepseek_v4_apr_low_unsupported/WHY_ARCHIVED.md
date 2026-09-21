# DeepSeek V4 Pro (April build), `effort: low` — unsupported, silently remapped

Archived 2026-09-21.

The April 2026 V4 Pro build **does not have a `low` reasoning effort** — only `high`
and `max` (Natalia, who ran the sweep). The request went out with
`reasoning_sent: {"effort": "low"}` and `effort_override: "low"` anyway, and the
provider accepted it and served something else rather than erroring.

The evidence that it was remapped rather than honoured, on the 40 competition
problems:

| run | median output tokens |
| --- | --- |
| `_low`  (this run) | 10,745 |
| `_high` | 11,862 |
| `_max`  | 19,599 |

`low` lands on top of `high`, not below it. A genuine low-effort arm looks like the GA
build, where low is 4,812 against high's 12,129 — a 2.5x gap, because GA is the
release where effort control actually arrived.

**Do not plot this file and do not read it as evidence that effort does nothing on
SiliconFlow.** It is one unsupported value on one build. Same failure mode as
`effort_medium_invalid/` (GLM), and the reason README run-hygiene item 1 exists:
reasoning effort must be a value the model actually accepts, and a provider that
accepts an unsupported value silently is worse than one that rejects it.

The valid V4 April arms are `_high` and `_max`, both still in
`data/deepseek_v4_pro_shallow_pass/`.
