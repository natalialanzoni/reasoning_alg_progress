# Reasoning Algorithmic Efficiency

Analysis of how the **reasoning trace length** of frontier LLMs evolves across
model generations on a fixed math benchmark. The central question: as models get
better, does the amount of "thinking" (output/completion tokens) they spend per
problem fall toward an irreducible floor — the length of a canonical human
solution — while accuracy holds or improves?

The headline finding (Figure 1) is that across GPT generations
(`o3 → gpt-5 → gpt-5.2 → gpt-5.4 → gpt-5.5`), mean trace length on the reference
problems falls steadily toward the canonical-solution floor, while accuracy on
the same problems stays flat or rises.

## Repository layout

```
code/        Analysis + plotting scripts (Python)
data/        Benchmark result files (per-model JSON, k=8 / k=32 runs)
figures/     Generated plots (figure1/ and time_series/)
```

### `code/`

| Script | What it produces |
| --- | --- |
| `plot_figure1.py` | Figure 1: trace length falling toward the canonical floor, across GPT generations (overall, per-problem, and faceted-by-source views). |
| `analyze_time_series_overall.py` | Mean ± SD, coefficient of variation (CV), and p90/p95 tail of trace length over model release dates. |
| `analyze_time_series_by_difficulty.py` | Token distribution per task, sorted by AoPS difficulty. |
| `analyze_time_series_by_difficulty_bins.py` | Trace length stratified by per-model per-task success rate (easy / medium / hard bins). |
| `analyze_time_series_cv_successes.py` | CV computed over *successful* trials only. |

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

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Running

```bash
python code/plot_figure1.py
python code/analyze_time_series_overall.py
# ...etc
```

> **⚠️ Data paths need wiring up.** These scripts were lifted from another
> codebase and still expect their inputs under `code/results/` with the
> original run-directory names (e.g. `thinking_20260612_100207/`), and write
> figures to `code/new_graphs/`. The data in this repo lives under `data/` with
> renamed directories (e.g. `gpt5_shallow_pass/`), and committed figures are in
> `figures/`. Before the scripts will run end-to-end you'll need to reconcile
> the `RESULTS` path and the per-model file paths at the top of each script with
> the actual `data/` layout. See the `MODELS` / `FILES` lists in each file.

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

### Conventions

- `data/<model>_shallow_pass/` — k=8 on thinking-benchmark-90
- `data/hard_but_doable_10q_k32/` — k=32 on the 10-problem hard slice
- `data/archive/<reason>/` — superseded runs, each with a `WHY_ARCHIVED.md`
  stating what invalidated them. Archive rather than delete.
- Reasoning traces (`*_reasoning_traces.json`, ~225MB) stay uncommitted in
  `code/results/`; only the results JSON is promoted into `data/`.
