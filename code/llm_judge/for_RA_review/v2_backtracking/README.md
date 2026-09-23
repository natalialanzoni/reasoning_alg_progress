# Backtracking v2 — does the "carried forward" test work?

Same 20 traces you have already reviewed twice, re-judged with a third prompt.

## What v2 asks

An instance counts when BOTH hold:

> **(a)** the writer stops pursuing a line of attack, whether by concluding it
> won't work or simply by leaving it, and
> **(b)** the subsequent derivation does not build on anything from that line.
>
> An exploratory segment that ends in "Hmm" and is never used again qualifies.
> "Let me reconsider" followed by rederiving and confirming the same result does
> not, because the result is kept.

This replaces v1's test, which asked whether the writer *concluded the approach
would fail* and *took a different route*. That was wrong twice over: it missed
ideas that were floated and quietly dropped, and it made the judge guess at intent
instead of reading the text. Whether later work builds on a line is visible on the
page.

## Where it lands

| | v0 | v1 | v2 |
| --- | ---: | ---: | ---: |
| total over the 20 traces | 207 | 42 | 42 |

Same total as v1, distributed differently. The case that prompted the rewrite —
`gpt-oss-120b hmmt_2026_feb_geo_08`, the "circumcircle of ABH ... Hmm" passage —
goes **3 → 10**, while the reconsider-rederive-confirm traces stay low
(`comb_09` 3, `comb_06` 1).

Encouraging sign: on that trace the judge *declined* to count "place coordinates
conveniently", reasoning that the specific setup which follows builds on it. That
is test (b) applied correctly to a case the prompt never mentions.

## What to check

1. **Is v2 counting real abandonments?** Each instance should quote a line that is
   dropped, and nothing downstream should use it.
2. **What is it still missing?** v1's failure was undercounting; the sheets have a
   space for abandonments v2 missed. This matters more than the false positives.
3. **The traces that went to zero** — `gpt-oss-20b hmmt_2026_feb_geo_09` (v0 28 →
   v2 0), `aime_2026_i_10` (3 → 0), `aime_2026_ii_11` (1 → 0). Are those correct
   rejections, or the undercount returning?

Each sheet has the v2 count and full reasoning, with v0 collapsed beneath for
comparison. Record in `verdicts.csv`.

## Status

`backtracking_v2.txt` is **not in use** — the shipped table still uses v0 for both
behaviours. Verification is unchanged at v0, which your manual check approved.
Nothing is re-run at scale until this review says v2 is right.
