# Archive — pre-grader-fix artifacts (do not use)

These are outputs produced **before** the answer-grader bug was fixed (branch
`fix-grader-and-o1`, 2026-09). They are kept only for provenance. **Do not use them
for the paper or copy numbers from them.**

## What was wrong

The original grader (`code/benchmark_math_dist.py::is_correct`) marked many
**correct** answers **wrong** because it was brittle to formatting:

- answer prefixes — `BC=\sqrt{17}-1`, `\angle APC = 74^\circ`
- work shown inside `\boxed{}` — `(20+1)(20+1)=441`, `48+84+25=157`
- units / degree symbols — `74^\circ` vs `74`
- leading zeros — AIME `070` vs `70`
- `\frac32` shorthand vs `\frac{3}{2}`, `\dfrac`, tuples/points
- algebraically-equivalent radical forms — `2\sqrt{435}/3` == `\sqrt{580/3}`

Because **efficient models write terser answers**, they were penalised far more than
verbose ones. Impact example: gpt-6-astra shallow accuracy **85.3% → 99.5%** after
re-grading; verbose models (GLM, o3) barely moved (+0 to +1). The apparent "astra
regression" and "astra underperforms" findings were **entirely a grading artifact**.

## The fix

- `code/regrade.py` — robust grader (`is_correct`) with prefix stripping,
  RHS-of-work extraction, unit removal, leading-zero-safe integer compare,
  tuple/set handling, and symbolic equivalence via `sympy.parse_latex` (antlr
  backend). Conservative: only ever promotes wrong→correct on a genuine match,
  never demotes. Audited: 469 flips, 0 false positives.
- `code/apply_regrade.py` — applied it to every result file. Each trial keeps its
  pre-fix grade in `correct_original` (standard schema) or `is_correct_original`
  (gpt-oss nested schema); the authoritative field is `correct` / `is_correct`.

## For future sessions

- The authoritative grader is **`code/regrade.py`**. Grade any NEW runs with it.
- Figures read the corrected `correct` field; never read `correct_original`.
- `figures/figs_sept/` (produced by the `code/*_ft.py` scripts) is the current
  figure set. The dirs archived here (`figure1/`, `time_series/`,
  `effective_compute/`) came from the legacy `paper_figures_71226.py` figure
  functions and predate the fix.
