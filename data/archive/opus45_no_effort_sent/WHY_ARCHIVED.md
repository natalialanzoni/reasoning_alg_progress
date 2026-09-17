# Archived: Opus 4.5 runs that sent no `effort` parameter

Both files are named `_medium` but **no effort parameter was ever sent**. The
RA's request body was:

```json
{"model": "claude-opus-4-5", "max_tokens": 40000,
 "thinking": {"type": "enabled", "budget_tokens": 20000}}
```

`code/benchmark_claude_opus.py`'s "budget" branch derived `budget_tokens` from
`--effort medium` (`0.5 x max_tokens`) and returned **only** the thinking block —
it never emitted `output_config.effort`. So `medium` was consumed as budget
arithmetic and the model ran at the API default, which Anthropic documents as
**`high`**.

Opus 4.5 does *not* predate effort: it is the one extended-thinking-only model
that supports `effort` alongside `budget_tokens`. Effort is live on it —
measured 2026-09-17 on `aime_2026_i_02`, same problem, same non-binding budget:

| effort | thinking tokens |
|--------|-----------------|
| low    | 1,475 |
| medium | 1,903 |
| high   | 12,082 |

Superseded by the 2026-09-17 re-run at an explicit `effort="medium"` with
`budget_tokens=38976` (non-binding, so thinking is limited by the same 40,000
total cap as the adaptive models 4.6+). Those runs carry a `_runconfig.json`
recording the literal parameters sent.

| run | archived (no effort -> high) | re-run (effort=medium) |
|-----|------------------------------|------------------------|
| k=8 accuracy    | 91.0% | 91.8% |
| k=8 median out  | 11,662 | 5,839 |
| k=8 mean think  | 11,073 | 8,630 |

Same accuracy at roughly half the median trace length.

Note both archived files were re-graded by `code/apply_regrade.py`; their
accuracies above use the corrected grades (`correct`), not `correct_original`.
