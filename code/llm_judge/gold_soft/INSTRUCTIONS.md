# Annotating abandoned approaches in math reasoning traces

You are building a hand-labelled answer key. Each trace is the chain of thought of a language
model solving a competition math problem (AIME / HMMT). Read the WHOLE trace carefully, top to
bottom. Do not skim or sample; the point is a careful count.

Traces live in:
/home/nfl234/reasoning_trace_efficiency/reasoning_alg_progress/code/llm_judge/for_RA_review/v3_backtracking/traces/

Line numbers are the file's own 1-based line numbers, blank lines included. Use `Read` on the
file, which prints these numbers; read long files in chunks with offset/limit until you have
read every line.

## Blindness — important

Other judges have labelled these traces already. You must not see their answers. Do NOT open
or grep any other file: not `out/`, not `gold_strict.json`, not the `.md` review sheets,
not `verdicts.csv`, not the README. Read ONLY your assigned trace files and this instruction file.

## The definition

Count each place where **the writer tries an approach and gives it up to do something different.**

- If the writer comes back to the same approach later, or continues it after a pause, that is
  ONE entry, not several. List every visit's line range under that one entry.
- An "approach" can be a method, a construction, a coordinate setup, a formula, a guessed
  answer or candidate value, or an interpretation of the problem. It can be tried briefly.

Do NOT count:
- **Verification**: checking or re-deriving a step or result that was already completed, then
  keeping it. This is the most important exclusion. "Let me double-check... yes, correct" is
  not an abandonment, and neither is re-deriving the same thing a second way to confirm it.
- **Required cases**: ruling out a case that the solution has to rule out (e.g. case 1 of a
  case split the argument needs) is part of the solution, not an abandoned approach.
- **Error fixes within the same method**: fixing an arithmetic or algebra slip and carrying on
  with the same method is not giving up an approach. (If the slip makes the writer drop the
  method and switch to a different one, the dropped method is an entry.)
- Restating or re-reading the problem, planning aloud, and summarising are not entries.

## Tiers

- `firm`: the writer clearly took up the approach (did at least some work on it, or committed
  to a candidate) and then dropped it for something different.
- `borderline`: it fits the definition but is thin. For example, an idea is raised in a line
  or two and set aside with no work done ("Could use coordinates? Maybe not needed."), or it
  is unclear whether it was really dropped.

## Output

Write one JSON file per trace to
/tmp/claude-121228/-home-nfl234/eb11dca9-6cc9-4365-a83d-2fe2909fdaa6/scratchpad/soft_gold/<ANNOTATOR>_<NN>.json
where NN is the two-digit trace prefix. Format:

```json
{"trace": "07", "annotator": "<ANNOTATOR>", "nlines": 323,
 "instances": [
   {"approach": "short name",
    "visits": [[start_line, end_line], ...],
    "abandon_line": 123,
    "abandon_quote": "5-15 words copied exactly from the abandon line",
    "switched_to": "what the writer did instead",
    "tier": "firm",
    "reason": "one sentence on why it counts"}
 ],
 "rejected": [
   {"lines": [start, end], "what": "short description",
    "why_not": "verification | required case | error fix | restatement | other: ..."}
 ]}
```

`abandon_line` is the line where the writer gives the approach up for the last time. In
`rejected`, list the most tempting non-instances you decided against, especially verifications
and required cases (up to ~15 per trace). These show where the line falls.

Be consistent across traces. When finished, reply with one line per trace: trace, number of
firm and borderline entries, and anything that was hard to decide.
