# hard-but-doable-10, k=32

Same 10 problems x 32 samples for every model. **Two different file schemas live here**
— check which one you have before writing analysis code.

## Schema A — OpenRouter / API harness
`code/benchmark_math_open_source.py` (open-weight) and `code/benchmark_claude_opus.py`
(closed). Files: `glm_*`, `claude-*`, `gpt-5*`, `o3_*`, `claude-fable-*`.

Top level is a **list** of per-problem dicts. Per-trial values are parallel lists:
`correct`, `extracted_answers`, `answer_in_boxed`, `total_completion_tokens`,
`thinking_tokens`, `answer_tokens`, `providers_used`, `errors`.

## Schema B — local GPU harness
`~/extract_mvt/test_scaling_laws/bench.py`, graded by `grade.py` there. Files: `gpt-oss-*`.

Top level is a **dict**: `model`, `k`, `max_tokens`, `temperature`, `top_p`,
`overall_accuracy`, `pass_at_k`, `results`. Each entry in `results` has `n_correct`,
`success_rate`, and a `completions` list whose items are
`{text, n_tokens, finish_reason, extracted_answer, is_correct}`.

Note `completions[].text` holds the full generation, so these files are large
(gpt-oss-20b is 12MB). Unlike Schema A, traces are **not** split into a separate file.

## Open-weight coverage

| model | status | accuracy |
|-------|--------|----------|
| GLM 4.5 / 4.6 / 4.7 / 5 / 5.1 / 5.2 / 5.3 | present | see `GLM_ANALYSIS_NOTES.md` — do not read raw accuracy as capability |
| gpt-oss-120b | present | 273/320 = **85.3%**, pass@32 100%, **0 truncations** |
| gpt-oss-20b  | present | 259/320 = **80.9%**, pass@32 100%, 10/320 truncated |
| Kimi K3 / K2.7 Code / K2.6 / K2.5 / K2 Thinking | **missing** | driver died 2026-09-07, nothing written |
| DeepSeek V4 Pro 0813 / V3.1 Terminus / R1 0528 | **missing** | never run on this benchmark |

## Caveats that apply across schemas

- **40k output cap.** A response that hits it emits no `\boxed{}` and grades wrong.
  This dominates several GLM numbers (see `GLM_ANALYSIS_NOTES.md`). gpt-oss-120b never
  reached the cap (max 37,955 tokens); gpt-oss-20b hit it on 10/320.
- **Reasoning effort is not comparable across models.** gpt-oss ran `re-medium`;
  GLM 5.2/5.3 ran `effort="medium"` via OpenRouter while the other five GLMs ran
  `reasoning={"enabled":true}` with no ceiling. The same nominal label buys very
  different token budgets across vendors and versions.

## Provenance

gpt-oss files were generated on GPU in `~/extract_mvt/test_scaling_laws/` (2026-07-27)
and graded with that folder's `grade.py`. gpt-oss-20b's grading pass had only covered
4/10 problems (it ran before generation finished); completed 2026-09-13. The grader was
re-validated first by reproducing gpt-oss-120b's stored `overall_accuracy` (0.8531) and
all 10 per-problem counts exactly.
