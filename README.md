# Reasoning Algorithmic Efficiency

Analysis of how the **reasoning trace length** of frontier LLMs evolves across
model generations on a fixed math benchmark. The central question: as models get
better, does the amount of "thinking" (output/completion tokens) they spend per
problem fall toward an irreducible floor — the length of a canonical human
solution — while accuracy holds or improves?

The headline finding (Figure 1) is that across generations — OpenAI
`o1 → o3 → gpt-5 → 5.2 → 5.4 → 5.5 → 5.6-sol → gpt-6-astra` and Anthropic
`Opus 4.5 → 4.6 → 4.7 → 4.8 → Opus 5 → Fable 5.1` — mean trace length falls
steadily toward the minimal-human-derivation floor while accuracy rises.
Mean tokens per correct solution fall **8.5x** for OpenAI (20 months) and **4.8x**
for Anthropic (9 months); the excess over the floor decays **31%/quarter** and
**38%/quarter** respectively.

## Sample definition — read this before touching a figure

Every current figure uses the **40 competition problems**: AIME 2026 I/II (28) plus
HMMT February 2026 (12). The five MATH-500 problems in the benchmark are
**excluded**, and the floor is recomputed over the same 40.

- **floor = 316 tokens**, the mean shortest human solution over those 40.
  `pf.canon_short` is **303** — that is the all-45 value and includes MATH-500's
  short solutions. Do not draw 303 on a 40-problem figure; `figure_effort_ft.py`
  did exactly that until it was caught.
- MATH-500 is excluded because the newest models sit *at or below* the floor on
  those easy problems, where `log(L - C_j)` is undefined: 20-67% of recent-model
  traces there get dropped by the `L > C_j` filter, against 0.3% on the 40
  competition problems. MATH-500-only regressions are unusable for that reason
  (the rate swings 31.3% -> 23.4% depending on which models you keep). Descriptive
  statistics on MATH-500 are fine; regressions are not.
- Difficulty tiers are a-priori, from competition position: AIME 1-10 medium,
  AIME 11-15 hard, **HMMT (any position) very hard** — HMMT ranks above all AIME
  rather than interleaving by number. Defined in `figure1_grid_ft.py::human_tier`
  and duplicated in the other figure scripts; change all of them together.

## Repository layout

```
code/        Analysis + plotting scripts (Python)
data/        Benchmark result files (per-model JSON, k=8 / k=32 runs)
figures/     Generated plots (figure1/ and time_series/)
```

### `code/`

| Script | What it produces |
| --- | --- |
| `figure1_grid_ft.py` | **Figure 1** (3x2): accuracy / mean tokens + floor / per-problem IQR by difficulty, OpenAI vs Anthropic on one shared time axis. Also writes the all-traces appendix replica. |
| `figure_forecast_ft.py` | **Figure 4**: one row, two panels, both families overlaid — tokens and multiple-of-floor — plus the forecast, the pre-cutoff contamination appendix, and sensitivity variants. |
| `figure_latent_floor_ft.py` | **Figure 5**: distance to the floor by family, violins of L/C_j with the minimum and average human solution drawn. |
| `figure_mechanism_ft.py` | Case study: scale (gpt-oss 20B->120B) vs algorithm (GLM 5.2->5.3), in Figure 1 style. |
| `figure_effort_ft.py` | Appendix: trace length over generations by reasoning effort (low/medium/high). |
| `table_floor_robustness.py` | Appendix table: beta re-estimated under four floor definitions (shortest / median / mean / none). |
| `regrade.py`, `apply_regrade.py` | The corrected answer grader and the script that bakes it into `correct`. See `archive/README.md`. |
| `censor_over_cap.py` | Right-censors runs whose provider ignored `max_tokens`. |

Legacy `plot_figure1.py` / `analyze_time_series_*.py` live in `code/archive/` and
still expect the old `code/results/` layout. The `_ft` scripts above read `data/`
directly and run end-to-end.

### `data/`

Each model run is a JSON array of per-task records. Key fields per record:

- `task_id`, `source` (AIME / HMMT / MATH-500), `difficulty`, `gold_answer`
- `correct` — list of booleans, one per attempt (k attempts per task)
- `total_completion_tokens`, `thinking_tokens`, `answer_tokens` — per attempt
- `removed_from_dataset` — tasks dropped from the current dataset version

Subdirectories:

- `*_shallow_pass/` — main k=8 thinking-benchmark runs per model
- `edge_of_capability_k32/` — k=32 runs on the harder problem slice
- `hard_but_doable_k32/` — k=32 runs on the "hard but doable" slice

The canonical-solution floor in Figure 1 is computed from the
[`tyrtleli/thinking-benchmark-90`](https://huggingface.co/datasets/tyrtleli/thinking-benchmark-90)
dataset on the Hugging Face Hub, tokenized with `tiktoken` (`o200k_base`).

## Reproducing the paper

```bash
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
bash code/make_paper_figs.sh             # <- ONLY what the paper includes -> paper_figs/
bash code/make_all_figures.sh all        # everything, incl. variants -> figures/figs_sept/
```

`paper_figs/` is the curated set: **if it is not in there, it is not in the paper.**
It is rebuilt from scratch by `make_paper_figs.sh`, which also writes
`paper_figs/MANIFEST.md` recording the commit and which script produced each file.
`figures/figs_sept/` remains the working directory where scripts drop everything
they make, including sensitivities and variants. To retire a figure, remove its line
from `ARTIFACTS` in `make_paper_figs.sh`.

Currently in the paper:

| Artifact | Script | Role |
| --- | --- | --- |
| `fig1_grid` | `figure1_grid_ft.py` | Figure 1, main text |
| `fig2_hard_distributions_success` | `figure2_ft.py` | Figure 2, main text |
| `fig4_forecast_2panel` | `figure_forecast_ft.py` | Figure 4, main text |
| `fig1_grid_alltraces` | `figure1_grid_ft.py` | appendix: all attempts |
| `fig4_forecast_excess_appendix` | `figure_forecast_ft.py` | appendix: excess tokens |
| `fig4_forecast_precutoff_appendix` | `figure_forecast_ft.py` | appendix: contamination |
| `fig1_grid_thinking` | `figure1_grid_ft.py` | appendix: thinking tokens only |
| `table_decay.tex` | `table_decay.py` | main regression table |
| `table_floor_robustness.tex` | `table_floor_robustness.py` | appendix robustness + thinking-only row |

Everything reads `data/` directly and writes to `figures/figs_sept/`. The canonical
human solutions are pulled from the
[`tyrtleli/thinking-benchmark-90`](https://huggingface.co/datasets/tyrtleli/thinking-benchmark-90)
dataset at run time and tokenized with `tiktoken` (`o200k_base`), so the first run
needs network access. Model results in `data/` are already regraded — `correct`
holds the corrected verdict (see failure mode 4).

### Verification anchors

If a change is supposed to be cosmetic, these numbers must not move. If they do,
something about the sample or the spec changed.

| Artifact | Script | Numbers to check |
| --- | --- | --- |
| sample + floor | all | **40** competition problems, floor **316** tok |
| accuracy denominator | all | **N = 320** per model (40 x k=8); o3 is 317 |
| Fig 1 | `figure1_grid_ft.py` | OpenAI 9,547 -> 1,121 tok (**8.5x**), acc 70.0% -> 99.4%; Anthropic 8,617 -> 1,799 (**4.8x**), acc 90.6% -> 97.8% |
| Fig 4 | `figure_forecast_ft.py` | beta **-0.126** (31.5%/qtr, CI 24-37) and **-0.178** (41.4%/qtr, CI 31-50); within-10% **2029-02** / **2028-06** |
| Decay table | `table_decay.py` | same betas; N 2,609 / 1,811; 9 / 6 model clusters |
| Thinking-only | `table_floor_robustness.py` | `thinking only` row: **33.1%** / **42.1%** (log L comparator 27.6% / 36.2%, not in the table) |
| Fig 1 thinking | `figure1_grid_ft.py` | OpenAI 8,309 -> 649 (**12.8x**); Anthropic 7,804 -> 1,173 (**6.7x**) |
| Fig 5 | `figure_latent_floor_ft.py` | astra 2.5% below min, 35.3% below average; Fable 5.1 0% below min, 10.1% below average, 30.0% zero-thinking |
| Case study | `figure_mechanism_ft.py` | scale 7,842 -> 4,693 (**1.7x**), acc 68.4% -> 73.8%; algorithm 14,241 -> 8,539 (**1.7x**), acc 83.4% -> 85.6%. NOT in `paper_figs/`. |
| Floor table | `table_floor_robustness.py` | OpenAI **31.5-34.1**%/qtr, Anthropic **41.4-43.1**%/qtr across three floor definitions |
| Contamination | `figure_forecast_ft.py` | `fig4_forecast_precutoff_appendix`: GPT **22.0%**/qtr (7 models), Anthropic **29.5%** (4) |

### Which scripts are on the paper's sample

Not all of them, and the runner does not enforce it — check before promoting any
figure into the paper.

| Status | Scripts |
| --- | --- |
| **On the 40-problem sample** (prints it on startup) | `figure1_grid_ft.py`, `figure_forecast_ft.py`, `figure_latent_floor_ft.py`, `figure_mechanism_ft.py`, `figure_effort_ft.py`, `table_floor_robustness.py` |
| **Effectively on it** (hard-but-doable-10 contains no MATH-500) | `figure2_ft.py`, `figure_cv_ft.py` |
| **NOT on it** — include MATH-500 via `valid_stats(..., restrict_canon=False)` | `figure3_pareto_ft.py`, `figures_sept_ft.py` |
| **PARKED** — MATH-500 included, 303-token floor, and the superseded `pos + 5` difficulty tiering | `figure1_grid_glm_ft.py`, `figure1_glm_algo_ft.py`, `figure1_oss_ft.py` |

The parked GLM figures are additionally provider-confounded (failure mode 7). Bring
a script onto the 40-problem sample by copying the `KEYS` / `FLOOR` block from
`figure1_grid_ft.py` before using its output.

### Re-running the benchmarks themselves

Only needed if adding a model; the committed `data/` is sufficient to rebuild every
figure.

```bash
bash code/run_o1.sh                       # OpenAI, pinned to the comparable settings
./venv/bin/python code/benchmark_math_open_source.py --help
./venv/bin/python code/apply_regrade.py   # ALWAYS regrade a new run before plotting
```

Read the run-hygiene section below first — all three original failure modes complete
with zero errors.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Running

```bash
MPLBACKEND=Agg ./venv/bin/python code/figure1_grid_ft.py
MPLBACKEND=Agg ./venv/bin/python code/figure_forecast_ft.py
./venv/bin/python code/table_floor_robustness.py
```

Each figure script prints its sample size and floor on startup — check that line
says `40 competition problems ... floor = 316 tok` before trusting the output.

## Notes

- DeepSeek **V3.2** is excluded from length analyses: the provider imposed a
  16,384-token output cap that pinned ~56% of trials at exactly that value,
  biasing mean/SD/CV downward.
- "Damaged" trials (`thinking_tokens == 0`) are dropped from statistics.
- Analyses use a consistent problem set — the intersection of `task_id`s present
  across all included models, after removing `removed_from_dataset` tasks.

## Run hygiene — read before launching a sweep

Three failure modes have silently corrupted runs in this project. All three
complete with **zero errors**, so a clean log proves nothing.

### 1. Reasoning effort must be a value the model actually accepts

An unsupported `reasoning={"effort": ...}` is not an error you will see. Vendors
silently remap it, so the run looks clean while measuring a level you did not
choose. Sending `"medium"` to GLM 5.2/5.3 and Kimi K3 — none of which has a
`"medium"` — produced a spurious 18.8pp accuracy gap that vanished on re-run.

`code/benchmark_math_open_source.py` now carries an explicit `_EFFORT` map with
per-model accepted values and vendor doc links. **Before adding a model, check
its docs and put the accepted level in that map.** Models with no effort knob
get `{"enabled": True}`.

Verify empirically, not from docs: run the same model on the same problems at
two effort levels and compare median thinking tokens. If they differ, the levels
are distinct. GLM 5.2 medium vs high differed by 42% despite Z.AI documenting
medium→high, so the doc-stated mapping did not hold in practice.

Effort is recorded in the filename (`_high` suffix) and in the startup log.

### 2. Providers do not reliably honor `max_tokens`

Pinning a provider does not guarantee the token budget:

| behavior | seen on | effect |
|---|---|---|
| ignores the cap | Z.AI (GLM 4.5), Novita (GLM 4.7, Kimi K2 Thinking) | completions to 87,718 against a 40,000 request |
| caps below the request | StreamLake (Kimi K2.5) | hard 32,768 ceiling; 27% of trials pinned there |

Both break cross-model comparison — one model gets double the budget, another
two-thirds. `provider_max` in `MODELS` is a hand-entered hint and **has been
wrong** (K2.5 listed 230,400, actually delivered 32,768).

Check after every sweep: `max(total_completion_tokens)` per model should equal
the requested cap. Above it → over-cap; well below it with a spike at a round
number → a provider ceiling. Over-cap runs can be right-censored with
`code/censor_over_cap.py`; under-cap runs must be re-run on another provider.

### 3. A failed request is recorded as a wrong answer

When a request exhausts its retries, `one_request` returns a zero-token
placeholder. Grading sees empty text, finds no `\boxed{}`, and records
`correct: false` — indistinguishable from a genuine miss unless you check the
token count. A rate-limited run therefore reports depressed accuracy rather
than failing. Kimi K3 once showed 45.5% when its true figure was 65.5%.

**Always check `total_completion_tokens == 0` before reading any accuracy.**
Attempts now carry an `errors` field (`None` on success) recording the
exception. Truncated-but-real attempts (tokens == cap) also score 0% — that is
genuine truncation, not an error, and is worth reporting as a finding.

Client settings that matter: `max_retries=5` on the OpenAI client so the SDK
backs off on 429s honoring `Retry-After` (setting it to 0 raised Kimi K3's
failures from 115 to 174), and `timeout=900` to cover a full 40k-token
generation. Reduce `--workers` before anything else when 429s appear.

### 4. The grader penalised terse models — fixed, but check before trusting old numbers

The original grader marked correct answers wrong on formatting alone (answer
prefixes, work inside `\boxed{}`, units, leading zeros, equivalent radicals).
Because efficient models write terser answers, it penalised exactly the models the
paper is about: gpt-6-astra read **85.3%** when its true accuracy was **99.5%**.
`code/regrade.py` fixes it and `correct` now holds the corrected verdict, with the
original preserved in `correct_original`. **Never read `correct_original`.** Full
write-up in `archive/README.md`; outputs produced before the fix are in
`archive/pre_grader_fix_figures/`.

### 5. A zero-length thinking block does not make a trace invalid

Several code paths used `thinking_tokens > 0` as a proxy for "this trace is real,
not an API failure". That proxy broke the moment a model started answering *without*
a thinking block. **Fable 5.1 answers with zero thinking tokens on 25% of the
competition problems (81 of 320), every one of them correct**, with 179-1,177 answer
tokens -- and those are its shortest traces (median 366 vs 2,073 for the rest).
Dropping them inflated Fable's measured length and flattened the Anthropic trend
from **41.4%** to 38.3% per quarter.

`figures_sept._trial_ok` (`tok >= 50` and non-empty text) is the correct test and
Figure 1 always used it; the forecast path did not until 2026-09. Validity is "did
it produce an answer", never "did it think out loud". Note the old test also *kept*
degenerate traces that had a thinking block but no answer, which `_trial_ok` rejects.

### 6. A truncated attempt is a FAILED attempt, not an invalid one

`_trial_ok` used "non-empty response text" as its validity test. A trace that spends
its whole budget thinking and never writes an answer has empty text and
`answer_tokens == 0`, so it was discarded — removing a genuine failure from the
accuracy DENOMINATOR and inflating accuracy for exactly the models that hit the cap:

| model | was | corrected | dropped truncations |
| --- | --- | --- | --- |
| Opus 4.6 | 98.0% | **90.3%** | 25 |
| gpt-5 | 91.6% | **88.4%** | 11 |
| Opus 4.5 | 92.1% | 90.6% | 5 |
| o3 | 84.5% | 84.2% | 4 |
| Opus 4.7 / 4.8 / o1 / gpt-5.1 | | −0.3 to −0.9 pts | 1–3 each |

Everything from gpt-5.2 and Opus 5 onward never hits the cap and is unaffected. The
bias therefore ran **against** the trend: it flattered the early models. `_trial_ok`
now counts a trace as a real attempt if `tok >= 50` and (text is non-empty **or** it
hit the cap). Token means are unaffected — those traces contribute no usable length
either way; only the denominator changes.

This was known and worked around locally in `figure1_deepseek_ft.py` before being
fixed at source, so check whether a rule you are about to re-implement already
exists in `figures_sept`.

**The denominator and the numerator are two separate fixes.** `_trial_ok` only made
truncated attempts *count*; they were still scored on the grader's verdict. But a
truncated response never delivered an answer, so it cannot be right whatever the
grader extracted from the fragment — and the grader falls back to "text after the
last `=`" when there is no `\boxed{}`, which on a truncated trace is fishing in
incomplete work. One real case: gpt-5 on `aime_2026_ii_15`, 38,720 thinking + 1,280
answer, cut off mid-sentence at *"...the number of ordered 7"*, but an earlier working
line read `= 393.` — the gold answer — so it scored **correct**. Use
`fs._trial_correct(tok, c)` for the numerator alongside `fs._trial_ok(tok, txt)` for
the denominator. All 56 cap-hit traces sit at exactly 40,000 (none overshoot) and only
that one was scored correct, so this moved gpt-5 88.4% -> **88.1%** and nothing else.

Watch the comparison operator: `tok <= CAP` counts a trace sitting exactly at the cap
as fine. It must be `tok < CAP`. `figure_mechanism_ft.py` had `<=` in four places.

### 7. The regression drops traces below the floor

The DV is `log(L - C_j)`, undefined when a trace is shorter than the shortest human
solution, so those traces are silently excluded. On the 40 competition problems this
is **0.3%** (13 of 4,084) and concentrated in two models — gpt-6-astra (11) and
Opus 4.7 (2) — so it is immaterial. It is *not* immaterial if you change the sample
or the floor: on MATH-500 it reaches 67%.

**Do not "fix" this by clipping at the bound.** Clipping `h` at 1.10 / 1.01 / 1.001
gives 29.5% / 30.9% / 32.0% per quarter — it diverges as the clip tightens, so any
number it produces is an artifact of the clip. The defensible check is the nonlinear
form `L = C_j + exp(a_j + b*month)` fitted on log L, which needs no drop and no clip:
it gives 27.4% against the headline 29.1% pooled, i.e. censoring is worth ~0.3pp and
the rest is functional form.

### 8. Reasoning effort must match before comparing absolute lengths across models

Within-model-pair comparisons are safe; cross-family ones usually are not. gpt-oss
exists **only at medium** effort (`_re-medium`), while GLM 5.2/5.3 are usable **only
at high** (their medium runs were silently remapped — see failure mode 1). So in the
case-study figure the *ratios* within each column are valid but GLM's absolute trace
lengths are not comparable to gpt-oss's. The same applies to any table that lines up
open-source models side by side.

### 9. GLM version-over-version trends are provider-confounded

Every GLM version was served by a **different** OpenRouter provider — 4.5 Z.AI,
4.6/4.7 Novita, 5 StreamLake, 5.1 Baidu, 5.2 Phala, 5.3 Z.AI — and pre-5.2 GLMs
expose no thinking-budget knob at all, so the provider's default governs how much
the model thinks. Median thinking tokens track the provider, not the version, which
is why the raw version line *rises* 14.4k -> 21.6k from 4.5 to 5.1. **Do not plot
the 7-point GLM version line.** The usable comparisons are (a) GLM vs frontier
verbosity on identical problems, which is robust, and (b) 4.5 vs 5.3, the one
provider-matched pair (both Z.AI), giving 2.2x compression at flat accuracy.

### 10. The regrader silently skipped a whole result schema

`apply_regrade.process` required a **list** of dicts with `correct`/`gold_answer`.
gpt-oss runs are a **dict** with `results[].completions[].is_correct`, so `process`
returned `None` and four result files were never regraded — with no message saying so.

Re-grading them flips **0 of 1,360** completions, so nothing in the paper moved. That
was luck, not design: the same hole would have swallowed a genuinely mis-graded run.

Fixed two ways. `_process_oss` handles the schema, and `main` now **names** any file
that looks like results but matched no handler, instead of skipping it in silence.
A file counts as regraded when it carries `correct_original` (schema A) or
`is_correct_original` (schema B) — that, not the summary line, is the check.

The dry-run summary was also misleading: it prints the CUMULATIVE flip count
recomputed from `*_original` every run, so a run that changes nothing still reports
489. It now says so.

### 11. `L` conflates reasoning length with answer verbosity — gpt-5.1 exposes it

gpt-5.1 looks like a broken point in Figure 4: it sits **above** the fit (9,496 tok vs
gpt-5's 8,372) while scoring **worse** (84.7% vs 88.4%). Both halves were checked and
the run is sound — all 360 requests carry `model=gpt-5.1`, `reasoning.effort=medium`,
`max_output_tokens=40000`, structurally identical to every other OpenAI run.

**Its reasoning did not grow. Its answers did.** On the paper sample, correct traces:

| | thinking | answer | L |
| --- | --- | --- | --- |
| gpt-5 | 7,829 | 543 | 8,372 |
| gpt-5.1 | **7,798** | **1,698** | 9,496 |

Thinking is flat to within 0.4%; the whole +1,124 is a 3.1x longer written answer.
Since `L = thinking + answer`, a purely presentational change registers as an
efficiency regression.

**The longer answer is LaTeX markup, and it is a series-wide format switch, not a
gpt-5.1 quirk.** The tokens are real text — 2.35 chars per answer token, in line with
every other model (2.23–2.70) — so this is not an accounting artifact. But reading the
answers side by side on the same problem, gpt-5 writes plain-text math
(`x^2 + y^2`, `√`, `⇒`) while gpt-5.1 wraps everything in `\(...\)` and `\[...\]`
display blocks with `\quad\Longrightarrow\quad` spacing. Same argument, same steps:

| | o1 | o3 | gpt-5 | **gpt-5.1** | 5.2 | 5.4 | 5.5 | 5.6-sol | astra |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| LaTeX command chars | 0.3% | 2.0% | 0.6% | **22.5%** | 25.4% | 22.9% | 22.5% | 22.2% | 19.5% |
| display equations | 0.1 | 0.3 | 0.0 | **23.4** | 14.0 | 19.7 | 14.3 | 11.1 | 8.1 |

gpt-5.1 is simply the first model to switch and the most verbose *within* the new
format. Every model after it keeps the format.

**Which way it biases the headline: against recent models, so the result is
conservative.** Stripping markup-only control sequences leaves pre-5.1 models
unchanged (0.0 to -0.1%) and shortens post-5.1 models by 1.8-4.4%, the largest being
astra because answers are 42% of its `L`. The o1 -> astra compression would read
**8.9x instead of 8.5x**. Small, and in the safe direction — but quote 8.5x, since
markup is genuinely emitted output.

**This motivated a thinking-only robustness check, now a paper artifact** —
the `thinking only` row of `table_floor_robustness.py`, same wild cluster bootstrap
as the main table. Thinking takes NO floor (see below), so `log L` is the
like-for-like comparison:

| DV | OpenAI | Anthropic |
| --- | --- | --- |
| `log(thinking)` | **33.1%**/qtr ** | **42.1%**/qtr * |
| `log L` (think+answer) | 27.6%/qtr ** | 36.2%/qtr * |
| `log(L - MHD_j)` (headline) | 31.5%/qtr ** | 41.4%/qtr * |

Reasoning falls **5-6pp/quarter faster** than total output in both families, so
keeping answers in `L` makes the headline **conservative**. Dropping gpt-5.1 entirely
moves the OpenAI slope only 27.3% -> 26.7%, so it is not distorting anything.

Two spec notes, both pushing the same way:
* **No floor on thinking.** The MHD is a human's *written* derivation — the analogue
  of the model's answer, not its scratch work. Subtracting it is also empirically
  unusable: `log(thinking - MHD_j)` censors **38.4%** of gpt-6-astra's traces and
  **26.2%** of Fable 5.1's, the defect that disqualified MATH-500 as a panel.
* **Zero-thinking traces cannot enter `log(thinking)`.** All 81 dropped are Fable 5.1,
  the newest model's shortest traces, so their loss *understates* the decline.

**Its accuracy drop is real. The grader was ruled out four ways:**

1. `_find_boxed` returns the **last** `\boxed{}` with proper brace nesting, so the
   usual first-vs-last bug cannot apply. Multi-boxing is rare anyway: 46 of the 49
   wrong traces contain exactly one.
2. Zero-padded AIME golds are handled — `is_correct("29", "029")` is `True`.
3. A deliberately **lenient** re-grade (strip `\text{}`/braces/`$`, then numeric
   compare with tolerance) flips **0 of 256** wrong traces — across all nine GPT
   models, not just gpt-5.1. There is no extraction slack left to recover.
4. It reproduces on an **independent run**: hard-but-doable k=32 gives gpt-5 96.2% /
   7,798 tok vs gpt-5.1 95.9% / 9,805 tok — same direction on both axes, different
   problems, different k.

Known grader gaps, none of which any trace hits: `29.0` vs `029`, `\text{29}` vs
`029`, and an unbalanced `29}` all score wrong.

**The two models fail differently**, which is the actual finding:

| | wrong | committed wrong value | hedged box | no box (cap truncation) |
| --- | --- | --- | --- | --- |
| gpt-5 | 37 | 26 | 0 | 11 |
| gpt-5.1 | 49 | 40 | **7** | 2 |

gpt-5 fails by running out of budget; gpt-5.1 fails by committing to a wrong value or
by **declining to commit** — boxing `\text{Not determined}`, `\text{Cannot reliably
determine}`. gpt-5.1 is the only mid-series model that does this at all (o1, o3,
gpt-5, 5.2, 5.4, 5.5 are all zero). Longer answers, hedging language and slightly
weaker competition math are one coherent signature of an instruction-tuned release,
not a measurement fault.

### 12. Six model clusters cannot support a 5% significance claim

`Month` is constant within a model, so the bootstrap must resample over MODELS — 8
for OpenAI, 6 for Anthropic. Two things go wrong if this is done casually, and the
second is the one that bites:

**Rademacher weights run out of resolution.** With `G` clusters a Rademacher
bootstrap has only `2^G` sign patterns, so the smallest attainable two-sided p is
`2^(1-G)`: 0.008 at G=8 but **0.031 at G=6**, where `p < 0.01` is unreachable
regardless of effect size. Use **Webb six-point weights** (`6^G` patterns).

**A percentile interval from an unrestricted bootstrap is anti-conservative.** It
excludes zero for both families here, which looks like significance at 5%. A proper
**bootstrap-t imposing H0 and studentizing with a cluster-robust SE each
replication** disagrees:

| family | beta | t | WCR bootstrap-t p |
| --- | --- | --- | --- |
| OpenAI (G=8) | −0.124 | −6.26 | **0.020** |
| Anthropic (G=6) | −0.178 | −5.80 | **0.066** |

So **Anthropic's decay is not significant at 5%** despite t = −5.8. The percentile
CI is still reported (it is what the Figure 4 band draws) but the stars in
`table_decay.py` come from the bootstrap-t, and a p-value row is printed so the two
cannot be confused. Do not read significance off the interval, and do not claim
either family compresses significantly faster than the other — the intervals
overlap. Clustering by *problem* gives SEs about a quarter as wide and is worse
still.

### Benchmark composition — known asymmetries

- **AIME is nearly complete**, 29 of 30 problems (all of 2026 I, and II minus #2).
  **HMMT is a subset and skewed**: 12 of 30, and both the Combinatorics and Geometry
  rounds start at problem #5, so the easier front half is absent. Algebra/NT
  contributes a single problem. The selection rule is not recorded anywhere in this
  repo — if you know it, write it down here.
- `aime_2026_i_15` is in the benchmark but has **no canonical solution**, so the
  hardest AIME I problem is absent from every floor-based analysis.
- Canonical solutions come from the AoPS Wiki: 122 solutions over 45 problems,
  **1 to 8 per problem (median 3 on the competition set)**. Audited clean — no
  empties, duplicates, count mismatches, truncation or wiki markup. Two caveats:
  **11 of the 40 competition problems have only one solution**, so no minimum is
  actually being taken there and the floor is likely an overestimate; and 6
  solutions embed `[asy]` diagram source, though stripping it leaves the floor
  unchanged at 316 because a diagram-free solution is already shortest in every
  such problem.
- Competition dates, needed for the contamination cutoff: **AIME 2026 I 2026-02-05**,
  **AIME 2026 II 2026-02-11**, **HMMT February 2026 2026-02-14**.
- **The contamination check keys on the TRAINING-DATA cutoff, not the release date.**
  What decides whether a model could have memorised a problem is whether the problem
  was inside its training data — not whether the model shipped afterwards. gpt-5.5
  (released 2026-04-23) and Opus 4.7/4.8 (2026-04/05) all have cutoffs before
  February 2026 and are therefore clean. Published cutoffs, read off the vendors'
  model pages 2026-09-20 and hard-coded in `TRAIN_CUTOFF` in `figure_forecast_ft.py`:

  | | o1 | o3 | gpt-5 | gpt-5.1 | gpt-5.2 | gpt-5.4 | gpt-5.5 | gpt-5.6-sol | gpt-6-astra |
  | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
  | cutoff | 2023-10 | 2024-06 | 2024-09 | 2024-09 | 2025-08 | 2025-08 | 2025-12 | **2026-02-16** | 2026-04-30 |

  | | Opus 4.5 | Opus 4.6 | Opus 4.7 | Opus 4.8 | Opus 5 | Fable 5.1 |
  | --- | --- | --- | --- | --- | --- | --- |
  | training-data cutoff | 2025-08 | 2025-08 | 2026-01 | 2026-01 | 2026-05 | 2026-06 |

  Anthropic publishes both a "reliable knowledge cutoff" and a broader "training data
  cutoff"; take the **broader** one — it is the conservative choice here. gpt-5.6-sol
  misses by two days (cutoff 2026-02-16 vs HMMT 2026-02-14), so it is excluded.
  A model absent from `TRAIN_CUTOFF` is **dropped**, never assumed clean, so adding a
  model without its cutoff shrinks this check rather than silently widening it.

### Conventions

- `data/<model>_shallow_pass/` — k=8 on thinking-benchmark-90
- `data/hard_but_doable_10q_k32/` — k=32 on the 10-problem hard slice
- `data/archive/<reason>/` — superseded runs, each with a `WHY_ARCHIVED.md`
  stating what invalidated them. Archive rather than delete.
- Reasoning traces (`*_reasoning_traces.json`, ~225MB) stay uncommitted in
  `code/results/`; only the results JSON is promoted into `data/`.
