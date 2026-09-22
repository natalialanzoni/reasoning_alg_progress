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
for Anthropic (9 months); the excess over the floor decays **31.5%/quarter** and
**41.4%/quarter** respectively.

---

## Replication — start here

Everything in the paper is rebuilt from `data/` by two scripts. No API keys, no model
calls, no GPU. You need **network access on the first run** (the canonical human
solutions are pulled from Hugging Face and tokenized with `tiktoken`).

```bash
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt

bash scripts/make_paper_figs.sh     # the paper's figures + tables -> paper_figs/
bash scripts/make_all_figures.sh    # everything, variants included -> figures/figs_sept/
```

`make_paper_figs.sh` is the one that matters: **`paper_figs/` is the paper.** If an
artifact is not in there, it is not cited. The script also writes
`paper_figs/MANIFEST.md` recording the commit and which script produced each file.

### Did it work?

Each script prints its sample on startup. Every one must say:

```
40 competition problems (MATH-500 excluded), floor = 316 tok
```

A script reporting **45 problems** or a **303-token floor** is on the wrong sample and
its output must not be used. The two DeepSeek scripts additionally report a
**32,768-token ceiling** — that is correct and required (run-hygiene item 13).

Then check these against the "Verification anchors" table further down. If a change
was meant to be cosmetic and one of these moved, something about the sample or the
spec changed:

| | OpenAI | Anthropic |
| --- | --- | --- |
| Fig 1 mean tokens | 9,547 -> 1,121 (**8.5x**) | 8,617 -> 1,799 (**4.8x**) |
| Fig 1 accuracy | 70.0% -> 99.4% | 90.6% -> 97.8% |
| Decay rate | **31.5%**/qtr (p = 0.022) | **44.1%**/qtr (p = 0.067) |
| Within 10% of floor | **2029-02** | **2028-02** |

### Two things that will bite a fresh machine

1. **The house style is an external dependency.** The figure scripts look for the
   `futuretech-charts` skill at `~/.claude/skills/futuretech-charts/python`. If it is
   absent they fall back to `code/_ft_style_local.py`, which reproduces the same
   palette and helpers, and print `STYLE_SRC = LOCAL RECONSTRUCTION`. Figures render
   either way — this was tested by hiding the skill and rebuilding everything — but
   the fallback is a reconstruction, so treat small typographic differences as
   expected and colours as exact.
2. **`data/` must be regraded before anything is plotted.** It already is in this
   repo: a file is regraded when it carries `correct_original` (or
   `is_correct_original` for the gpt-oss schema). If you add a run, do
   `./venv/bin/python code/apply_regrade.py --write` first. See run-hygiene items 4
   and 10.

### Layout

| path | what it is |
| --- | --- |
| `paper_figs/` | **the curated set — this is the paper** |
| `scripts/` | shell entry points: the two build scripts and the run launchers — see its README |
| `code/` | live analysis and plotting scripts |
| `code/archive/` | superseded scripts, kept not deleted — see its README |
| `data/` | benchmark results, one JSON per run |
| `data/archive/` | invalidated runs, each with a `WHY_ARCHIVED.md` |
| `figures/figs_sept/` | build intermediate, gitignored, recreated by every run |
| `archive/figures/` | snapshot of the old working output + superseded figures |

Before changing anything, read **Sample definition** immediately below and the
**Run hygiene** section near the end. The run-hygiene items are all real bugs that
were found in this codebase, each with the numbers it moved.

---

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
paper_figs/           THE PAPER: curated figures + tables (scripts/make_paper_figs.sh)
scripts/              shell entry points: build scripts + run launchers
code/                 live analysis + plotting scripts
code/archive/         superseded scripts (see its README)
data/                 benchmark results, one JSON per run
data/archive/         invalidated runs, each with a WHY_ARCHIVED.md
figures/figs_sept/    build intermediate -- gitignored, recreated on every run
archive/figures/      snapshot of the old working output + superseded figures
```

### `code/`

| Script | What it produces |
| --- | --- |
| `figure1_grid_ft.py` | **Figure 1** (3x2): accuracy / mean tokens + floor / per-problem IQR by difficulty, OpenAI vs Anthropic on one shared time axis. Also writes the all-traces appendix replica. |
| `figure_forecast_ft.py` | **Figure 4**: one row, two panels, both families overlaid — tokens and multiple-of-floor — plus the forecast, the pre-cutoff contamination appendix, and sensitivity variants. |
| `figure_latent_floor_ft.py` | **Figure 5**: distance to the floor by family, violins of L/C_j with the minimum and average human solution drawn. |
| `figure_mechanism_ft.py` | Case study: scale (gpt-oss 20B->120B) vs algorithm (GLM 5.2->5.3), in Figure 1 style. |
| `figure2_ft.py` | **Figure 2**: within-problem distributions on the hard-but-doable-10 (k=32). |
| `figure_effort_ft.py` | Appendix: trace length by reasoning effort (low/medium/high), k matched at 8. |
| `figure1_deepseek_ft.py` | Appendix: the DeepSeek open-source timeline, censored at 32,768. |
| `figure_deepseek_branch_ft.py` | Appendix: the DeepSeek effort branch (GA build). |
| `table_decay.py` | **Main regression table**: per-family excess-trend slope, WCR bootstrap-t. |
| `table_floor_robustness.py` | Appendix table: beta under three floor definitions plus a thinking-only row. |

Shared libraries, imported by the above rather than run directly:

| Module | Role |
| --- | --- |
| `figures_sept.py` | `_trial_ok` (validity) and `_trial_correct` (success) — the single source of truth for both. Also `valid_stats`. |
| `paper_figures_71226.py` | data loading (`load_rows`), the canonical floor (`CANON`), model lists and dates, `_fit_headroom_forecast`, `TRAIN_CUTOFF`. |
| `_ft_style_local.py` | stand-in for the `futuretech-charts` house style when the skill is absent. |

Infrastructure:

| Script | Role |
| --- | --- |
| `regrade.py`, `apply_regrade.py` | the corrected answer grader, and the script that bakes it into `correct`. Run `apply_regrade.py --write` after adding any run. |
| `benchmark_math_dist.py` and friends | the sweep drivers. `--max-tokens` defaults to 100000; every published run used 40000. |
| `run_openai_shallow.sh`, `run_openai_hard.sh`, `run_openai_effort.sh` | new runs pinned to the published settings. Read the header before using one. |
| `verify_run.py` | post-run checks, including `--cap` for cap compliance. |
| `censor_over_cap.py` | right-censors runs whose provider ignored `max_tokens`. |

`code/archive/` holds superseded scripts and a README explaining each. The oldest of
them (`plot_figure1.py`, `analyze_time_series_*.py`) expect the pre-`data/` layout and
do not run as-is.

### `data/`

Each model run is a JSON array of per-task records. Key fields per record:

- `task_id`, `source` (AIME / HMMT / MATH-500), `difficulty`, `gold_answer`
- `correct` — list of booleans, one per attempt (k attempts per task)
- `total_completion_tokens`, `thinking_tokens`, `answer_tokens` — per attempt
- `removed_from_dataset` — tasks dropped from the current dataset version

Subdirectories:

- `*_shallow_pass/` — main k=8 thinking-benchmark runs per model
- `hard_but_doable_10q_k32/` — k=32 runs on the 10-problem hard slice (Figure 2)
- `low_reasoning_effort/`, `high_reasoning_effort/` — k=8 effort arms (the medium arm
  reuses `hard_but_doable_10q_k32/`)
- `edge_of_capability_k32/` — earlier k=32 slice, not used by any current figure
- `archive/` — invalidated runs, each with a `WHY_ARCHIVED.md` saying what killed it

The canonical-solution floor in Figure 1 is computed from the
[`tyrtleli/thinking-benchmark-90`](https://huggingface.co/datasets/tyrtleli/thinking-benchmark-90)
dataset on the Hugging Face Hub, tokenized with `tiktoken` (`o200k_base`).

## Reproducing the paper

The commands are in **Replication — start here** at the top. This section is the
artifact inventory and the verification anchors.

Currently in the paper:

| Artifact | Script | Role |
| --- | --- | --- |
| `fig1_grid` | `figure1_grid_ft.py` | Figure 1, main text |
| `fig2_hard_distributions_success` | `figure2_ft.py` | Figure 2, main text |
| `fig_mechanism` | `figure_mechanism_ft.py` | Figure 3, main text: scale vs algorithm |
| `fig4_forecast_2panel` | `figure_forecast_ft.py` | Figure 4, main text |
| `fig5_latent_floor` | `figure_latent_floor_ft.py` | Figure 5, main text: distance to the floor |
| `fig1_grid_alltraces` | `figure1_grid_ft.py` | appendix: all attempts |
| `fig4_forecast_excess_appendix` | `figure_forecast_ft.py` | appendix: excess tokens |
| `fig4_forecast_precutoff_appendix` | `figure_forecast_ft.py` | appendix: contamination |
| `fig1_grid_thinking` | `figure1_grid_ft.py` | appendix: thinking tokens only |
| `fig_effort` | `figure_effort_ft.py` | appendix: low / medium / high reasoning effort |
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
| sample + floor | all | **40** competition problems; floor **316** tok (o200k) / **355** (Opus 4.5-4.6) / **441** (Opus 4.7+) |
| accuracy denominator | all | **N = 320** per model (40 x k=8); o3 is 317 |
| Fig 1 | `figure1_grid_ft.py` | OpenAI 9,547 -> 1,121 tok (**8.5x**), acc 70.0% -> 99.4%; Anthropic 8,617 -> 1,799 (**4.8x**), acc 90.6% -> 97.8% |
| Fig 4 | `figure_forecast_ft.py` | beta **-0.126** (31.5%/qtr) and **-0.194** (44.1%/qtr); within-10% **2029-02** / **2028-02** |
| Decay table | `table_decay.py` | same betas; N 2,609 / 1,794; 9 / 6 model clusters |
| Thinking-only | `table_floor_robustness.py` | `thinking only` row: **33.1%** / **42.1%** (log L comparator 27.6% / 36.2%, not in the table) |
| Fig 1 thinking | `figure1_grid_ft.py` | OpenAI 8,309 -> 649 (**12.8x**); Anthropic 7,804 -> 1,173 (**6.7x**) |
| Fig 5 | `figure_latent_floor_ft.py` | pooled n~630/model. astra **2.83%** below min, **25.0%** below average; Fable 5.1 **2.38%** / **20.5%** / **27.7%** zero-thinking |
| Case study | `figure_mechanism_ft.py` | scale 7,842 -> 4,693 (**1.7x**), acc 68.4% -> 73.8%; algorithm 14,241 -> 8,539 (**1.7x**), acc 83.4% -> 85.6% |
| Floor table | `table_floor_robustness.py` | OpenAI **31.5-34.1**%/qtr (floor 316), Anthropic **44.1-47.8**%/qtr (floor 441) |
| Effort | `figure_effort_ft.py` | 8 GPT models x 3 efforts, **k truncated to 8** (`K_CAP`); **low 33.5%**, **medium 35.6%**, **high 36.3%**/qtr |
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
bash scripts/run_o1.sh                       # OpenAI, pinned to the comparable settings
./venv/bin/python code/benchmark_math_open_source.py --help
./venv/bin/python code/apply_regrade.py   # ALWAYS regrade a new run before plotting
```

Read the run-hygiene section below first — all three original failure modes complete
with zero errors.

## Running one script at a time

Setup and the full rebuild are in **Replication — start here** at the top. The venv
must be called `venv`, not `.venv`: every script and runner invokes
`./venv/bin/python` by that exact path.

```bash
MPLBACKEND=Agg ./venv/bin/python code/figure1_grid_ft.py
./venv/bin/python code/table_decay.py
```

`MPLBACKEND=Agg` is needed for the figure scripts on a headless machine; the table
scripts do not plot. Each script prints its sample and floor on startup — check it
says `40 competition problems ... floor = 316 tok` before trusting the output.

## Conventions that are easy to get wrong

- **A trace is valid if it produced >= 50 tokens.** A zero-length *thinking* block
  does **not** invalidate it — Fable 5.1 answers correctly with no thinking block on a
  quarter of problems, and those are its shortest traces. An older version of this
  file said `thinking_tokens == 0` trials were dropped; that filter was a bug and is
  gone. See run-hygiene item 5.
- **A cap-truncated trace is a real attempt that FAILED.** It counts in the accuracy
  denominator and scores wrong. Use `figures_sept._trial_ok` for validity and
  `figures_sept._trial_correct` for success rather than re-implementing either — that
  duplication is what let the same bug live in four scripts at once. Items 6 and 10.
- **Analyses use the intersection of `task_id`s present across all included models,**
  after removing `removed_from_dataset` tasks.
- **DeepSeek runs must be compared at a common 32,768-token ceiling.** Item 13. (An
  older note here said V3.2 was excluded for a 16,384-token provider cap pinning ~56%
  of trials — that is not true of the current data: V3.2 has **zero** trials at 16,384
  and runs to 82,918. The note predates the re-run and has been removed.)

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

### 4. The grader penalised terse models — fixed, and there is now only ONE grader

The original grader marked correct answers wrong on formatting alone (answer
prefixes, work inside `\boxed{}`, units, leading zeros, equivalent radicals).
Because efficient models write terser answers, it penalised exactly the models the
paper is about: gpt-6-astra read **85.3%** when its true accuracy was **99.5%**.
`code/regrade.py` fixes it and `correct` now holds the corrected verdict, with the
original preserved in `correct_original`. **Never read `correct_original`.** Full
write-up in `archive/README.md`; outputs produced before the fix are in
`archive/pre_grader_fix_figures/`.


**There is one grader: `code/regrade.py::is_correct`.** `benchmark_math_dist.py`,
`benchmark_claude_opus.py` and `benchmark_math_open_source.py` each used to carry
their own independent implementation, so a run was scored by whichever one its driver
happened to call. All three now delegate to `regrade.py`; verified to agree with it
case-for-case, and `apply_regrade.py` still reports the same 517 historical flips
after the change.

The delegating import is deliberately **lazy**, because `regrade.py` loads
`benchmark_math_dist` for `extract_boxed` — importing it at module level from there
would be circular, and an earlier attempt at this consolidation recursed on exactly
that.

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

### 12. One model was run at a different k, which faked an effort effect

`fig_effort` compares low / medium / high. The raw runs are **not** on a common k:

| | low | medium | high |
| --- | --- | --- | --- |
| o3 ... gpt-5.6-sol | k=8 | k=32 | k=8 |
| **gpt-6-astra** | **k=32** | k=32 | **k=32** |

gpt-6-astra is the newest and **shortest** model, so it carried four times the weight
of every other model in the low and high regressions but not in medium — unequal
weighting across the very arms being compared, concentrated on the most extreme point.

`K_CAP = 8` truncates every problem to its first 8 attempts. What it changes:

| | uncapped | k=8 |
| --- | --- | --- |
| low | 37.7% | **33.5%** |
| medium | 36.3% | **35.6%** |
| high | 40.1% | **36.3%** |

Uncapped, low (37.7%) appeared to beat medium (36.3%), which is backwards for an
effort story. Capped, the three are close and ordered in effort. **Check k before
comparing any two lines**: `Counter(len(r["correct"]) for r in rows)`.

### 13. Compare accuracy only at a COMMON token budget

A provider that ignores `max_tokens` for one model and honours it for another makes
accuracy incomparable across those models, and the bias always favours the model that
was allowed to overrun. The DeepSeek timeline is the clean example: all three runs
requested **40,000**, and SiliconFlow honoured it only on V4 Pro while ignoring it
entirely on R1-0528 (ran to **66,106**) and V3.2 (**82,918**). The earlier models kept
thinking past the budget and were credited for answers V4 was cut off before
reaching.

**Fix: cut every model off at ONE ceiling, and pick the LOWEST ceiling any model
actually hit.** Score an over-ceiling trial wrong and clamp its length — that is what a
backend enforcing that ceiling would have produced.

For DeepSeek that ceiling is **32,768**, not the 40,000 that was requested, because at
32,768 nothing is unknown for any model:

- R1 and V3.2 never truncated, so their full lengths are known and anything over
  32,768 would have been cut.
- V4 either stopped **at** 32,768 (so it needed more) or ran past it (needed more).
  Either way it fails at that ceiling.

At 40,000 instead, V4's 41 trials that the provider cut at 32,768 are **censored** — we
cannot tell whether they would have finished by 40,000. A 40k comparison has to guess
about 41 of V4's 320 trials, so it is not well defined.

| run | @32,768 accuracy | median tokens | over 32,768 |
| --- | --- | --- | --- |
| R1-0528 | 61.9% | 23,554 | 108 (33.8%) |
| V3.2 | **83.8%** | 13,946 | 43 (13.4%) |
| V4 Pro Apr `high` | **75.3%** | 11,862 | 76 (23.8%) |

The V3.2 -> V4 dip is ~8.5 points and **survives a matched budget**. But the mechanism
is the tail, not typical verbosity: V4 has the **shortest median** of the three while
running over 32,768 nearly **twice as often**. It is more concise on a typical problem
and blows up more often on a hard one, so a fixed budget costs it more. Report that,
not "V4 reasons worse".

**Do not instead drop the truncated trials from the denominator.** That is asymmetric:
it discards V4's hard cases while keeping R1's and V3.2's long trials and scoring them
as successes. It puts V4 at 98.8% and is meaningless.

The general rule: name the ceiling, pick the lowest one any model actually hit, and
report how many trials each model lost to it.

### 14. The case-study columns are at DIFFERENT reasoning efforts

`fig_mechanism` compares gpt-oss 20B->120B against GLM 5.2->5.3. The gpt-oss runs are
**medium** effort; the GLM runs are **high** (their medium runs were silently remapped
by the provider and are archived in `data/archive/effort_medium_invalid/`).

So the WITHIN-column comparisons are clean — each pair is matched on effort, which is
what the 1.7x ratios measure — but the token LEVELS are not comparable across columns.
GLM's 14.2k against gpt-oss's 7.8k is partly the effort setting, not the model. The
caption should say the figure compares ratios, not levels. See failure mode 8.

### 15. `L` and the floor are in DIFFERENT token units for Anthropic

Trace lengths `L` come from each provider's own usage counter, so they are in that
provider's tokens. The floor `C_j` is tokenized with tiktoken `o200k_base` for every
model — OpenAI units. For OpenAI models that matches. **For Anthropic it does not**,
so `L / C_j` and `L - C_j` mix two units.

It is also not constant across the series, because **Anthropic changed tokenizer at
Opus 4.7** (their docs: 1M tokens is ~555k words on the current tokenizer, ~750k on
the earlier one). Measured on this benchmark's own solution text, framing removed:

| tokenizer | mean shortest solution, 40 problems | vs `o200k` |
| --- | --- | --- |
| `o200k_base` (all OpenAI) | **316** tok | 1.000 |
| Opus 4.5, 4.6 | **355** tok | 1.123 |
| Opus 4.7, 4.8, Opus 5, Fable 5.1 | **441** tok | 1.396 |

The tell is chars-per-answer-token, which is flat for OpenAI (2.23–2.70 across nine
models) and steps at 4.7 for Anthropic: 2.08, 2.18, then **1.71, 1.69, 1.66, 1.71**.

`code/build_floor_by_tokenizer.py` counts every canonical solution through each
tokenizer and caches the result in `code/canonical_floors_by_tokenizer.json`, so the
right floor can be used per model and reproduction needs no API key.

**Direction: using 316 for Anthropic understates its floor, overstates its excess, and
therefore UNDERSTATES its decline.** Correcting it:

| | floor = 316 for all | each model's own floor |
| --- | --- | --- |
| OpenAI | −0.1261, 31.5%/qtr | unchanged (o200k is already correct) |
| Anthropic | −0.1781, **41.4%**/qtr | −0.1936, **44.1%**/qtr |

Anthropic's median multiple of the floor also drops — Fable 5.1 from 4.63x to 3.49x —
and its below-floor share rises (Fable 5.1 0.64% to 4.47%), because the floor it is
being measured against is 40% higher than the one used.

**Now wired through every figure and table.** `pf.floor_for(label, task_id)` returns the
floor in that model's units and `pf.mean_floor(label, keys)` the number a floor LINE
draws. Figures 1 and 2 draw a floor per family; Figure 4 uses each family's own; Figure
5's `L/C_j` is per model.

Two traps this exposed, both now handled:

1. **The DV had to change.** The code fitted `log(headroom - 1) = log(L - C_j) -
   log(C_j)`, justified by `-log(C_j)` being absorbed by the problem fixed effect.
   That holds only while `C_j` depends on the problem ALONE. With per-model floors it
   varies by model too and correlates with time, so it leaks into beta — it put
   Anthropic at 48.6%/qtr against the correct **44.1%**. Everything now fits the
   paper's stated equation, `log(L - MHD_j)`, in absolute tokens.
2. **Expressing a milestone needs the GEOMETRIC mean floor.** The mean-FE intercept
   lives in log space, so "within 10% of the floor" is `log(0.10 * exp(mean_j log
   C_j))`. Using the arithmetic mean moved OpenAI's date two months even though its
   floor never changed.

OpenAI is unchanged throughout (o200k is already its tokenizer) — that is the check
that the wiring is isolated. gpt-oss, GLM and DeepSeek report their own tokenizers and
are **not** covered: they keep the o200k floor and inherit the caveat. An unmapped
Anthropic-looking label now prints a warning instead of silently using o200k, which is
how `claude-fable-5-1` (Figure 5's spelling, against the tables' `Fable 5.1`) was found
to be falling through.

### 16. Six model clusters cannot support a 5% significance claim

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
