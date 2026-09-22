# LLM judge — counting backtracking and verification in reasoning traces

**The deliverable is `paper_figs/table_behaviours.tex`, built by
`behaviour_table.py` from `out/judge_whole_gemini.jsonl`. Nothing else in this
folder feeds the paper.** Everything else is either the script that produced that
JSONL, documentation of how we got there, or the RA adjudication pack.

Counts two of Gandhi et al.'s cognitive behaviours in the traces behind
`fig_mechanism`, to ask what actually changes when a model gets more efficient:
does it verify less, backtrack less, or just write less?

```
python code/llm_judge/judge_traces.py --estimate            # volume + cost, sends nothing
python code/llm_judge/judge_traces.py --show-one            # print one real payload
python code/llm_judge/judge_traces.py --limit 6 --send      # pilot, spread over problems
python code/llm_judge/judge_traces.py --send                # full run, ~$6, ~40 min
python code/llm_judge/behaviour_table.py --tex paper_figs/table_behaviours.tex
```

Needs `ERA_OPENROUTER_V2` (or `OPENROUTER_API_KEY`). **Nothing is sent without
`--send`.**

## Files

| File | Role |
| --- | --- |
| `backtracking_v0.txt`, `verification_v0.txt` | the two prompts, from `kanishkg/cognitive-behaviors` |
| `load_traces.py` | loads the CoT for the four fig_mechanism models, normalised |
| `judge_traces.py` | sends each whole trace to the judge, parses `<count>` |
| `behaviour_table.py` | **builds `paper_figs/table_behaviours.tex`** |
| `out/judge_whole_gemini.jsonl` | the run; one record per trace per behaviour |

## The prompts

Verbatim from `pretraining_analysis/prompts/` in the upstream repo, with **one
documented edit**: line 2 read

> You will be provided with text from the internet.

and now reads

> You will be provided with the reasoning trace of a language model solving a
> competition mathematics problem.

Everything else is untouched, there is **no system message** (upstream's
`relabel_pretrain.py` sends the formatted template as the only user message), and
every output record carries the template's `prompt_sha` so the claim is checkable.
**State the edit in the appendix.**

Note what is *not* here: the repo's `behavioral_evals/` prompts are hardcoded to
the CountDown game (`{numbers}`, `{target}`, and a backtracking definition about
"combinations of numbers"), so they cannot be used on AIME/HMMT traces.
`gpt_api_eval.py` takes `--task-type math` but the `MathAnalyzer` class it would
instantiate does not exist in the file — the math path was never released. These
pretraining templates are the only domain-general pair upstream.

## Traces

The four models in `fig_mechanism`: gpt-oss-20b -> gpt-oss-120b (scale) and
GLM 5.2 -> GLM 5.3 (algorithm), on the 40 competition problems at k=8 = 1,280
traces. **CoT only on both sides**, which needs normalising because the two
families store it differently:

* GLM keeps the thinking block in a parallel `*_reasoning_traces.json` and the
  answer write-up separately in `response_texts`; we take the thinking block.
* gpt-oss packs both into one `text` field in Harmony channel format as literal
  text — `analysis` + CoT + `assistantfinal` + answer — so we take everything
  before `assistantfinal`. Verified: 338/360 (20b) and 360/360 (120b) contain the
  separator, all 720 start with `analysis`, no split yields an empty CoT.

Counting over "CoT" for one family and "CoT + answer" for the other would not be a
matched comparison.

## Why whole-trace, and not chunked

The prompts ask the judge to COUNT occurrences, which requires seeing the whole
chain: you cannot tell a backtrack from a first attempt by looking at a fragment.
Two localised protocols were tested and both **over-count by ~5-6x** against a
hand count of 2-3 on one trace:

| method | count |
| --- | --- |
| hand count | 2-3 |
| whole trace, gemini-2.5-flash | 2 |
| whole trace, sonnet-4.5 | 3 |
| chunk into 3k windows and sum | 13 |
| marker-anchored windows, yes/no each | 14-18 |

Worse, the inflation scales with the number of pieces, i.e. with trace length —
and trace length is the variable this project measures, so it would have
manufactured a trend. The rejected runs are in
`data/archive/llm_judge_abandoned/` with a WHY_ARCHIVED.md.

## Why this judge

Twelve judges on the same full trace. `gpt-4o-mini` returns a constant **12**
regardless of input. `gpt-4.1-mini`, `gemini-3.1-flash-lite` and `haiku-4.5`
collapse toward 0. `gpt-5-mini` and `gpt-5-nano` emit unparsable replies.
**`claude-opus-5` and `claude-fable-5.1` refuse the task outright** —
`finish_reason: content_filter`, citing Anthropic's ToS on "reverse engineering or
duplicating model outputs" — which is a reproducibility constraint worth stating.
Only `sonnet-4.5` and `gemini-2.5-flash` matched the hand count; gemini is ~10x
cheaper, so it is the judge. Temperature 0, recorded per record.

## Two things that silently corrupt this

**`max_tokens` truncates the count.** The template puts `## Thoughts` first and
`<count>` last, so a verbose judge is cut off before it emits the number — an
unparsable record, not a zero. At 600 this lost 7/96 replies, all from the
longest-trace model; at 2000 it lost 81/766 on Gemini. Now 4000. If you change
judges, check the unparsable rate first, and note that `behaviour_table.py` DROPS
unparsable records rather than counting them as zero.

**`--limit N` must spread across problems.** Taking the first N traces takes N
samples of ONE problem — the easiest one — which is how an early pilot "showed"
zero backtracking everywhere. It now walks distinct problems.

## Reading the output

`behaviour_table.py` prints per-trace counts and per-10k-token rates. Use the **rate**
when comparing models of different verbosity: GLM 5.2's traces are ~3.4x longer
than 5.3's, so a per-trace difference partly just restates a length difference.
"Verifies less" and "writes less" are different claims and the two columns
separate them.
