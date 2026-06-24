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
