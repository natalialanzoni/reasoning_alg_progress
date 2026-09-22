# Backtracking: which instrument is right?

We have two ways of counting backtracking in a reasoning trace and they disagree
by ~3x on the headline result. **We do not know which is correct.** This folder is
20 traces where you can decide.

| instrument | what it is | GLM 5.2 -> 5.3 lever |
| --- | --- | ---: |
| LLM judge | gemini-2.5-flash reads the whole trace and returns a count | 1.48x |
| string markers | regex for explicit abandonment language | 4.29x |

The paper's claim about algorithmic progress depends on which we trust.

## What we already know

* The judge's individual judgments look **good** where we have checked them. On
  `gpt-oss-20b hmmt_2026_feb_geo_09` it found 2 instances and quoted both
  verbatim; both are real.
* The markers have **recall gaps**. On that same trace they found 1, because the
  set contains "different approach" but not "another approach", and "is wrong" but
  not "step wrong" — all of which appear in the text.
* The markers' **precision** looked good on a 20-hit hand check (GLM 5.2 ~14/14
  genuine), but precision was only ever checked for GLM 5.2 and 5.3.
* Two judges (gemini-2.5-flash, sonnet-4.5) correlate only **+0.52** with each
  other on backtracking, which is why we stopped trusting the judge in the first
  place — possibly wrongly.

## The definition

From Gandhi et al. (2025), which is the instrument both methods are trying to
implement:

> backtracking behavior, where the writer realizes a path won't work and
> explicitly goes back to try a different approach ... instances where the writer
> abandons a thought and backtracks to a previous computation

**Not backtracking:** a routine arithmetic re-check ("wait, 372/39 = 12?"), a
clarification, re-reading the problem statement, or verifying an answer at the
end. These are common and they are what inflate a naive count.

**Watch for:** GLM 5.3 spends a lot of its traces trying to remember whether it
has seen the problem before ("let me reconsider the memory one final time...").
That is not backtracking either. Marker hits in that context are flagged
`EXCLUDED as memory-recall context` in the files.

## How to review

Each `NN_model_task_sN.md` has four sections:

1. **What the judge said** — its reasoning names specific instances. Check each
   against the trace and count how many are genuine.
2. **What the markers caught** — each hit with surrounding context. Same question.
3. **Did either miss anything?** — skim for abandonment neither caught. This is
   the part that decides the recall question, and it is the most valuable.
4. **Your total** — how many genuine instances are in this trace.

Full traces are in `traces/`. They are long (up to 116k chars); you do not have to
read every word — sections 1 and 2 point you at the places that matter, and
section 3 only needs a skim.

Record results in `verdicts.csv`. If you only have time for some, **do the ones
with the largest judge-vs-marker gap first** (01, 02, 05, 07, 11, 19) — they carry
the most information about which instrument is wrong.

## What we will do with it

If the judge's precision holds up (say >=80% of named instances genuine) and the
markers keep missing cases, we retire the marker result and report the judge's
1.48x. If the judge is inflating — naming routine checks as backtracking — we keep
the markers and fix their recall gaps. If both are bad, the honest outcome is that
backtracking is not measurable at this scale and we report only verification.
