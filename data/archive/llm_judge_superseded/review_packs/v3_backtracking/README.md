# Backtracking prompt v3 — review pack

Same 20 traces as the v0 and v2 packs, so the three columns in each sheet are
directly comparable. Counts on these 20: **v0 207, v2 44, v3 137.**

## What v3 changes, and why

Three objections to the first v3 draft, all adopted:

1. **Enumerated cases.** The draft counted a failed case 1 as backtracking. But if
   the proof needs a case split, ruling out case 1 is required work that the
   shortest human solution also does — counting it inflates every model's number
   with necessary derivation. v3 distinguishes: a case the writer HAD to
   eliminate does not count; a case the writer guessed and abandoned does. The
   framing gives it away ("we consider two cases" vs "suppose n is even").
2. **Arithmetic slips.** The draft excluded them, but a recomputed value replaces
   a discarded one, which is exactly rule (a)+(b), and Section 3 of the paper
   defines a backtrack as identifying a wrong step and reconsidering. Counting
   them is the consistent choice, so v3 counts them.
3. **Interpretations.** Re-reading the problem does not count; adopting an
   interpretation, dropping it, and proceeding under another does.

## Two defects found while piloting, and fixed

- Stating the arithmetic rule bluntly ("no other exclusions") let the judge treat
  a remembered answer as a dropped candidate. One GLM 5.3 trace scored **63**,
  counting the same recalled value seven-plus times. v3 now says a remembered
  answer is not a candidate, and one episode of recall counts 0 however often it
  recurs. That trace is now 7.
- The dedup rule only covered adjacent sentences. v3 extends it across the whole
  trace: raising, dropping, and re-raising one idea five times is 1, not 5.

## Repeatability

The same prompt run twice on these 20 traces: 18 identical, 2 moved (2 vs 5, and
19 vs 36), totals 137 vs 157. Per-trace counts are not fully deterministic even at
temperature 0; pooled rates over 1,280 traces are far more stable, but do not read
a single trace's number as exact.

## What to check

Each sheet has the problem, a link to the full trace, the v3 judge output in full
(never truncated), and v2 underneath for comparison. The questions at the bottom
of each sheet target the three changes above. Record verdicts in `verdicts.csv`.
