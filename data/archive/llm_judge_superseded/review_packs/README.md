# Which instrument is right?

**Two folders, one per behaviour. Every sheet says which at the top — do not mix them.**

    backtracking/   20 traces — THE CONTESTED MEASUREMENT, do these first
    verification/   20 traces — the stable one, included as a control

Backtracking is where the two instruments disagree and where your judgement
decides what the paper claims. Verification is included so we can tell a judge
that is wrong everywhere from one that is wrong only on the hard behaviour — if
you find it accurate on verification and loose on backtracking, that is itself
the answer.

Regenerate either with `python code/llm_judge/make_review_pack.py`.

## The disagreement

| instrument | what it is | GLM 5.2 → 5.3 | 20B → 120B |
| --- | --- | ---: | ---: |
| LLM judge | gemini-2.5-flash reads the whole trace, returns a count | 1.48× | 0.88× |
| string markers | regex for explicit abandonment language | 4.29× | 0.51× |

Same direction, ~3× apart on size. The paper's claim about algorithmic progress
depends on which we trust.

## What we already know

* The judge's individual calls verified well where checked. On
  `gpt-oss-20b hmmt_2026_feb_geo_09` it found 2 instances and quoted both
  verbatim; both are real.
* The markers have **recall gaps**. On that same trace they found 1, because the
  set has "different approach" but not "another approach", and "is wrong" but not
  "step wrong" — all present in the text.
* **But the judge may over-count on long traces.** Across 1,253 traces its count
  correlates more with how often the model writes "wait" (r = +0.50) than with
  explicit abandonment language (r = +0.35), and its own justifications sometimes
  read *"expresses uncertainty ('Hmm.')"* or *"proposes an idea then immediately
  questions it"* — self-interruption, not abandoning a path. **This is the central
  question.**
* Two judges (gemini-2.5-flash, sonnet-4.5) correlate only **+0.52** with each
  other on backtracking, against a preserved model ranking on verification.

## The definitions

From Gandhi et al. (2025), the instrument both methods implement.

**Backtracking** — the writer realises a path will not work and explicitly
abandons it to try a different approach. A routine arithmetic re-check, a
clarification, expressing uncertainty ("Hmm"), or re-reading the problem is NOT
backtracking.

**Verification** — the writer explicitly checks their own work: substituting a
result back, testing a special case, comparing against a known value. Simply
stating a result, or restating the answer at the end, is NOT verification.

**Watch for:** GLM 5.3 spends a lot of its traces trying to remember whether it
has seen the problem ("let me reconsider the memory one final time..."). That is
neither behaviour. Marker hits in that context are flagged in the sheets.

## How to review

Each sheet has the counts, a link to the **complete untruncated trace** in
`traces/`, the problem being solved, the definition, then four sections:

1. **What the judge said** — its reasoning names specific instances. Check each
   against the trace; how many are genuine?
2. **What the markers caught** — each hit with context. Same question.
3. **Did either miss anything?** — skim for instances neither caught. This decides
   the recall question and is the most valuable part.
4. **Your total.**

Record in each folder's `verdicts.csv`. If time is short, do the largest
judge-vs-marker gaps first — they carry the most information.

Traces are **chain of thought only**: for gpt-oss everything before
`assistantfinal`, for GLM the thinking block with the answer stored separately.
That is exactly the text the judge saw, so a trace ending without a boxed answer
is expected.

## What we will do with it

If the judge's precision holds (say ≥80% of named instances genuine) and the
markers keep missing cases, we report the judge's 1.48×. If the judge is naming
routine checks, we keep the markers and fix their recall gaps. If both are bad,
the honest outcome is that backtracking is not measurable at this scale and we
report verification only.
