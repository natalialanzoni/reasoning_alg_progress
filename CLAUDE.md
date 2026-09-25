# Working in this repo

Paper on LLM reasoning-trace length falling toward a minimal-human-derivation floor.
`README.md` is the full guide; this is the short version you need before editing.

## Rebuilding

```bash
bash scripts/make_paper_figs.sh     # THE PAPER -> paper_figs/
bash scripts/make_all_figures.sh    # everything incl. variants -> figures/figs_sept/
```

`paper_figs/` is the paper. If an artifact is not in there it is not cited. Both
scripts must exit 0 with no traceback; `figures/` is a gitignored build directory.

## Five rules, each of which has already been broken here

**1. Never re-implement "did this trial count" or "was it correct".**
Use `figures_sept._trial_ok(tok, txt)` for the denominator and
`figures_sept._trial_correct(tok, c)` for the numerator. A cap-hit trace is a real
attempt that FAILED. The same rule once lived in four scripts and the fix reached
three of them.

**2. Never use a single floor.** `L` is in each provider's own tokens and Anthropic
changed tokenizer at Opus 4.7, so the floor is 316 (OpenAI), 355 (Opus 4.5–4.6), 441
(Opus 4.7+), 303 (DeepSeek). Use `pf.floor_for(label, task_id)` and
`pf.mean_floor(label, keys)`; in `figure_forecast_ft.py` use `ref_of(mfiles)`. There is
deliberately no module-level floor constant any more, and `_floor()` raises if you do
not tell it which one to draw. An unmapped Anthropic-looking label prints a warning
rather than silently using the OpenAI floor — do not ignore it.

**3. The DV is `log(L - MHD_j)`, in absolute tokens.** It is NOT interchangeable with
`log(headroom - 1)`. That identity held only while the floor depended on the problem
alone; with per-model floors the `-log(C_j)` term is no longer absorbed by the problem
fixed effect and leaks into beta — it put Anthropic at 48.6%/quarter against the
correct 44.1%. There is no `hhat()`; take `ehat()` (excess tokens) and add or divide by
the floor you are actually drawing against.

**4. One regression, one set of numbers.** The decay table, the Figure 4 band and the
Figure 4 annotation are three readings of the same fit and must print the same
interval. If they disagree, something is fitting the wrong thing — that is exactly how
a whole-panel error survived review.

**5. The sample is the 40 competition problems.** Every script prints its sample on
startup; one reporting 45 problems or a 303-token floor is on the wrong sample and its
output must not be used. MATH-500 is excluded because 20–67% of recent-model traces
there fall below the floor, where `log(L - C_j)` is undefined.

## Before saying a change is cosmetic

Check the verification anchors in `README.md`. The load-bearing ones:

| | OpenAI | Anthropic |
| --- | --- | --- |
| Fig 1 tokens | 9,547 → 1,121 (8.5x) | 8,617 → 1,799 (4.8x) |
| Decay | −0.126, 31.5%/qtr, p = 0.022 | −0.194, 44.1%/qtr, p = 0.067 |
| Within 10% of floor | 2029-02 | 2028-02 |
| N / clusters | 2,609 / 9 | 1,794 / 6 |

Anthropic is **not** significant at 5%, and the two families' CIs overlap heavily — do
not write that one is declining significantly faster.

## Other things that bite

- **Data must be regraded before it is plotted.** A file is regraded when it carries
  `correct_original` (or `is_correct_original`, gpt-oss schema). After adding a run:
  `./venv/bin/python code/apply_regrade.py --write`. There is one grader,
  `code/regrade.py`; the benchmark drivers delegate to it.
- **DeepSeek is compared at a common 32,768-token ceiling**, because the provider
  honoured `max_tokens` for V4 and ignored it for R1 and V3.2. Never quote raw
  DeepSeek accuracies across models.
- **k differs by sweep.** Effort arms are k=8, hard-but-doable is k=32, on the same
  dataset. Check `Counter(len(r["correct"]) for r in rows)` before comparing.
- **House style is vendored** in `code/ft_style/`, not taken from the
  `futuretech-charts` skill. Figures build byte-identically without the skill
  installed; do not repoint the imports at it.
- The venv must be called `venv` — every script invokes `./venv/bin/python`.

`README.md` has all of this as numbered run-hygiene items 1–15, each with the numbers
it moved. They are real bugs found in this codebase, not hypotheticals.
