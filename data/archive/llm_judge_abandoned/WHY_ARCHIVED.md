# Abandoned LLM-judge runs — do not use these numbers

All of these come from methods that were tested and rejected on 2026-09-21.
They are kept only so the rejection is auditable. The live pipeline is
`code/llm_judge/` and its only valid output is `out/judge_whole_gemini.jsonl`.

## What was rejected, and why

**Chunk-and-sum** (`judge_chunked_linebased_SUPERSEDED.jsonl`, `judge_sent.jsonl`,
`verify_chunked.jsonl`). Split each trace into <=3,072-token windows, judge each,
sum. It **over-counts ~5x**: on a hand-counted trace with 2-3 genuine backtracking
instances it returned 13 (per-chunk [5,1,1,6]). A window cannot tell a backtrack
from a first attempt, because that is a property of the whole solution, so routine
arithmetic re-checks get counted. Worse, the inflation scales with the number of
chunks, i.e. with trace length -- and trace length is the variable this project
measures, so it would have manufactured a trend.

**Site yes/no classification** (not saved; tested inline). Locate candidate
passages by marker regex, give the judge ~3 paragraphs of preceding context with
the candidate marked, ask yes/no. Same failure for the same reason: 14-18 YES on
the same trace whose truth is 2-3. Localising the judgment primes a yes.

**Whole-trace with Haiku 4.5** (`judge_none.jsonl`, `pilot_spread*.jsonl`).
Right method, wrong judge: haiku under-counts on long input (1 where the hand
count is 2-3; 0 on a 30k-token GLM trace). `pilot_spread.jsonl` is additionally
invalid because `--limit` took the first N traces, which are N samples of ONE
easy problem rather than N different problems.

## What was checked before settling

Twelve judges on the same full trace (hand count ~2-3 on a comparable trace):
gpt-4o-mini returned a constant 12 regardless of input; gpt-4.1-mini,
gemini-3.1-flash-lite and haiku-4.5 collapsed toward 0; gpt-5-mini and gpt-5-nano
emitted unparsable replies; **claude-opus-5 and claude-fable-5.1 REFUSE the task
outright** (`finish_reason: content_filter`, Anthropic ToS on "reverse
engineering or duplicating model outputs"). Only sonnet-4.5 and gemini-2.5-flash
tracked the hand count; gemini-2.5-flash is 10x cheaper, so it is the judge.
