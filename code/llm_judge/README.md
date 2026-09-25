# LLM judge — counting backtracking and verification in reasoning traces

**The deliverable is `paper_figs/table_behaviours.tex`, built by
`behaviour_table.py` from two judge runs: `out/judge_whole_gemini.jsonl`
(verification) and `out/judge_backtracking_v6.jsonl` (backtracking). Nothing else
in this folder feeds the paper.** Everything else is either a script that produced
those files, documentation of how we got there, or an RA adjudication pack.

Counts two of Gandhi et al.'s cognitive behaviours in the traces behind
`fig_mechanism`, to ask what actually changes when a model gets more efficient:
does it verify less, backtrack less, or just write less?

Run everything from the repo root with the project venv (`./venv/bin/python`); the
system `python3` lacks numpy and tiktoken.

```
./venv/bin/python code/llm_judge/judge_traces.py --send          # verification, ~$6, ~40 min
./venv/bin/python code/llm_judge/judge_traces.py --retry-unparsable --max-out 65535 --send   # re-send cut-off replies
./venv/bin/python code/llm_judge/run_backtracking_v6.py          # backtracking: volume + cost, sends nothing
./venv/bin/python code/llm_judge/run_backtracking_v6.py --send   # backtracking, ~$280, resumable
./venv/bin/python code/llm_judge/behaviour_table.py --tex paper_figs/table_behaviours.tex
./venv/bin/python code/llm_judge/behaviour_table.py --correct-only --tex paper_figs/table_behaviours_correct.tex
./venv/bin/python code/llm_judge/prompt_robustness_table.py --tex paper_figs/table_backtracking_prompts.tex
./venv/bin/python code/llm_judge/make_prompt_image.py            # appendix prompt figures
```

Needs `ERA_OPENROUTER_V2` (or `OPENROUTER_API_KEY`). **Nothing is sent without
`--send`.** Both runs resume where they stopped. `behaviour_table.py` refuses to
write the `.tex` while any trace has no record, so a half-finished run cannot
reach the paper. By default it uses one sample for both behaviours: traces with both
counts (`--no-common-sample` to turn this off). RESULTS.md has what the 29 dropped
traces do.

## Files

| File | Role |
| --- | --- |
| `verification_v0.txt` | **in use.** Gandhi et al.'s template + one domain edit |
| `backtracking_v6.txt` | **in use.** See "The backtracking prompt, v4 → v6" |
| `backtracking_v0.txt` … `v5.txt` | superseded; kept so old runs stay readable |
| `load_traces.py` | loads the CoT for the four fig_mechanism models, normalised |
| `judge_traces.py` | the verification run (and the superseded backtracking v0–v3 runs) |
| `run_backtracking_v6.py` | the backtracking run: line-numbers each trace, checks the judge's quotes |
| `behaviour_table.py` | **builds `paper_figs/table_behaviours.tex`** (and `_correct.tex` with `--correct-only`) |
| `prompt_robustness_table.py` | appendix table: backtracking levers under prompts v0/v2/v3/v6, and v6 with problems weighted equally |
| `make_prompt_image.py` | appendix figures of the two prompts the paper's runs used |
| `out/judge_whole_gemini.jsonl` | **the verification run the paper uses** (its v0 backtracking records are superseded and never read) |
| `out/judge_backtracking_v6.jsonl` | **the backtracking run the paper uses** |
| `out/judge_backtracking_v2.jsonl`, `_v3.jsonl` | superseded backtracking runs |
| `pilot.py`, `pilot_v4.py` | prompt × judge pilots on the 20 review traces (`--compare` prints all) |
| `gold_strict.json` | strict key on the 20 traces (commit + explicit failure + switch) |
| `gold_soft/` | **the soft key v6 is validated against**; `score_soft.py` scores a pilot against it |
| `for_RA_review/v6_backtracking/` | RA pack: check the soft key, then v6 against it |
| `for_RA_review/v3_backtracking/` | 20 sheets, v0/v2/v3 side by side; also holds the 20 traces |

## The prompts

**Verification** is verbatim from `pretraining_analysis/prompts/` in the upstream repo, with **one
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
GLM 5.2 -> GLM 5.3 (post-training), on the 40 competition problems at k=8 = 1,280
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
longest-trace model; at 2000 it lost 81/766 on Gemini. Now 24000. If you change
judges, check the unparsable rate first, and note that `behaviour_table.py` DROPS
unparsable records rather than counting them as zero.

**The drop is never random — it takes the longest traces**, which is the variable
under study. Always print the loss as a share of each model's TOKENS, not as a
count of traces: v3 loses 25 of 1,280 traces, which sounds negligible, but that is
10.8% of GLM 5.3's tokens against 3.5% of GLM 5.2's. RESULTS.md carries the
sensitivity check that shows the levers survive it.

**`--limit N` must spread across problems.** Taking the first N traces takes N
samples of ONE problem — the easiest one — which is how an early pilot "showed"
zero backtracking everywhere. It now walks distinct problems.

## Reading the output

`behaviour_table.py` prints per-trace counts and rates **per 10k reasoning
tokens** — CoT tokens, not whole-completion tokens, because that is where the
behaviours are counted. Exact for GLM (`thinking_tokens`); estimated by character
share for gpt-oss, which logs no reasoning-token field. Use the **rate**
when comparing models of different verbosity: GLM 5.2's traces are ~3.4x longer
than 5.3's, so a per-trace difference partly just restates a length difference.
"Verifies less" and "writes less" are different claims and the two columns
separate them.

## The backtracking prompt, v0 → v3

Four versions. v3 is in use; the history is here so nobody re-derives a rejected
one. Verification never moved off v0 — review found it sound.

**v0** (upstream, verbatim + domain edit) counted self-interruption as
abandonment: most of what it called backtracking was "let me reconsider", then
rederive, then confirm the same result. That is the model second-guessing itself,
which scales with trace length — the variable the paper says is shrinking.

**v2** tested whether the line of attack is CARRIED FORWARD. It fixed the
over-count and then undercounted differently: it refused candidates as "too brief
and undeveloped to count as a distinct line of attack", and treated a failed case
inside a continuing strategy as not-abandoned.

**v3** counts a candidate however briefly raised and drops the computation
requirement. Three refinements came out of review:

* **Cases.** Ruling out case 1 of a required case split is work the shortest human
  solution also does, so counting it inflates every model with necessary
  derivation. v3 counts a guessed case that was abandoned, not one the argument
  forced.
* **Arithmetic slips** count: a recomputed value replaces a discarded one, which
  is the rule as written. Stating this once was not enough — the judge overrode it
  with "not an abandonment of a line of attack" — so v3 rebuts that framing.
* **Interpretations.** Re-reading the problem does not count; adopting an
  interpretation, dropping it and proceeding under another does.

Two pilot defects, both fixed before the full run. Stating the arithmetic rule as
"no other exclusions" let the judge treat a *remembered answer* as a dropped
candidate — one GLM 5.3 trace scored 63, counting the same recalled value
seven-plus times. And the dedup rule only covered adjacent sentences, so it now
spans the whole trace.

**The v3 format section must forbid listing non-instances.** Without that clause
the judge walks long traces sentence by sentence emitting thousands of entries
reading "this is a verification", and never reaches `<count>`. That clause cut the
unparsable rate from 28/1280 to 25/1280; raising the output cap does not help
(48,000 tokens recovered 1 of 28) and neither does retrying (2 of 27 over four
attempts), so the failure is deterministic per trace.

### Two rewrites we tried and dropped

Recorded so nobody re-derives them.

**Backtracking v1** required that the writer both conclude the approach fails AND
take a different route, with an explicit NOT-list for re-checking, arithmetic
fixes, pausing, and re-reading the problem. It cut the mean over 20 traces from
10.35 to 1.75, removing the self-interruption the RA flagged — but on manual
review it then **undercounted**, missing genuine abandonments stated tersely.
Trading over-counting for under-counting is not progress when the direction of the
bias is what the paper's claim rests on.

**Verification v1** widened the definition to claim doubt-and-rederive events, and
also added a deduplication rule of my own: *each distinct check counts once, even
when the writer expresses doubt several times about the same quantity.* That rule
did most of the damage — on `GLM 5.2 aime_2026_ii_04` it took the count 28 → 9,
almost entirely by collapsing separately-tested examples (n=19, n=23, n=90) into
one instance. It also violated its own NOT-list, counting "checking for a
misunderstanding of the problem". Manual review found v0 verification was fine as
it stood.

**The open question v1 was trying to answer** is still open: is testing three
examples to confirm one rule three verifications or one? v0 counts three, so the
count partly measures how many examples a model tries, which scales with trace
length. If the paper leans on verification counts, it should say which it means.

## The backtracking prompt, v4 → v6

v3 was replaced after review. The paper measures **wasted search**, so the
construct is deliberately soft: *"tries an approach and gives it up to do
something different"*. The writer need not commit to the approach or say it failed.
v6 is a rewrite, not the upstream template plus an edit — **say so in the
appendix**, and quote `backtracking_v6.txt` in full.

* **v4** asked for each instance with the lines where it was adopted and
  abandoned, each with a verbatim quote, so every instance can be checked on the
  page. The count used is the number of instances whose abandon quote is found in
  the trace; the judge's own `<count>` is recorded but not trusted.
* **v5** and **v6** simplified the definition to the soft construct above,
  keeping two exclusions: verification of a completed step, and ruling out a case
  the solution requires. Returning to the same approach is one entry.
* **Judge:** gemini-3.1-pro-preview (`pilot.py --compare` has the others). The
  pilot's 24,000-token output cap cut off 1/20 replies, because the judge's
  reasoning counts against it; the full run uses the model's 65,536.

**Validation.** `gold_strict.json` measures the stricter construct and cannot
validate v6. `gold_soft/` is a key for the soft construct: two annotators (Claude
models) counted each of the 20 traces blind to every judge. Anthropic's
usage-policy filter stopped four annotator runs, so 12 traces are double-counted,
7 single, and trace 04 has none; they were not retried. Against it
(`gold_soft/score_soft.py`), of v6's 121 entries:

* 80 match a key entry;
* 27 land on an entry already matched — about half are the same approach listed
  twice, the rest separate ideas inside a long episode;
* 14 match nothing: 3 at spots an annotator rejected as verification, 4 as error
  fixes, 7 other.

v6 misses most one-line ideas the annotators marked borderline (9/35 found) and 7
of 36 firm ones. On the same traces its newer/older ratios track the annotator's:
GLM 5.3/5.2 0.70 vs 0.71, gpt-oss 120b/20b 1.24 vs 1.18 (annotator 2, 2–5 traces
per model, so suggestive, not proof). The two annotators agree with each other
(mean difference 1.5 per trace) better than v6 agrees with either (3.0–3.5).

**Open until the RA pack comes back:** the key is not person-checked, and whether
one-line ideas count is undecided.
