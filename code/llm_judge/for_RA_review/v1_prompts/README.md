# v1 prompts — did the tightened definitions fix it?

Your review of the v0 prompts found that most of what the judge called
backtracking was *"let me reconsider → rederive → confirm"*, which under Gandhi
et al.'s definition is not backtracking at all — it is closer to verification.
Counting it anyway would make the measured quantity "how often the model
second-guesses itself", which scales with trace length — the variable the paper
says is shrinking. That is circular, so the prompts were rewritten.

**This folder is the same 40 traces you already reviewed, re-judged with the new
prompts, so you can check whether the fix worked on text you already know.**

    backtracking/   the 20 backtracking traces, v0 vs v1
    verification/   the 20 verification traces, v0 vs v1

Each sheet shows the v1 count, the v1 reasoning in full, and the v0 reasoning
collapsed underneath for comparison. The prompts themselves are
`code/llm_judge/backtracking_v1.txt` and `verification_v1.txt`; v0 is still there
unchanged.

## What changed in the prompts

**Backtracking now requires BOTH:** (1) the writer concludes the current approach
will not work, AND (2) the writer then takes a *different* route. Re-deriving the
same thing to check it fails (2). There is an explicit NOT list: re-checking and
confirming, fixing an arithmetic slip and continuing, pausing ("Wait", "Hmm",
"Actually"), re-reading the problem, and trying to recall a known answer. The
upstream examples "Wait" and "I made a mistake" were removed as headline cases —
they are probably what taught the judge to count self-interruption.

**Verification now explicitly claims those events:** doubting a step and
re-deriving it *whatever the outcome*, re-doing a computation a second way,
catching an arithmetic slip by re-checking. One added rule to check: *each
distinct check counts once, even when the writer expresses doubt several times
about the same quantity.* Without it a model that dithers over one number scores
several verifications.

Both now require the judge to QUOTE what it counted, so over-counting is visible.

## What the pilot showed

Backtracking fell hard, concentrated exactly where you said it would:

| trace | v0 | v1 |
| --- | ---: | ---: |
| `hmmt_2026_feb_geo_06` | 30 | 1 |
| `hmmt_2026_feb_geo_09` | 28 | 4 |
| `hmmt_2026_feb_comb_09` | 27 | 3 |
| `hmmt_2026_feb_comb_06` | 25 | 1 |
| **mean over 20** | **10.35** | **1.75** |

On the same 20 traces, backtracking + verification together went 299 → 278
(−7%), so the events are mostly being *reallocated* rather than lost. But not
evenly: `comb_06` went 35 → 12 and `comb_09` 43 → 15, where the old count was
mostly pauses that qualify as neither under the new definitions.

## What we need from you

1. **Is v1 counting the right things for backtracking?** It should now only fire
   when an approach is abandoned for a different one.
2. **Is verification now picking up the doubt-and-rederive cases?** That is where
   they should have gone.
3. **One trace to look at specifically:** `hmmt_2026_feb_geo_09` verification went
   20 → 79. That is the largest single move and may be the dedup rule failing on a
   trace that re-checks one quantity many times.

Record in each `verdicts.csv`. If v1 holds up we re-run all 1,280 traces (~$14).

## One caveat to carry into the paper

v0 was Gandhi et al.'s prompt with a one-line domain edit — defensible as "their
instrument, our domain". **v1 is a redefinition of both constructs.** The appendix
must say "adapted from", the counts are not comparable to their published numbers,
and this folder is the evidence for why the change was made.
