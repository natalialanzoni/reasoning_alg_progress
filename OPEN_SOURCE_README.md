# Open-source sweeps (`benchmark_math_open_source.py`) — handoff

Written for whoever picks this up next. It covers the OpenRouter sweep script
only; the top-level [README](README.md) covers the project, and its **Run
hygiene** section covers the three failure modes that complete with zero errors.
Read that section first — this file assumes it.

Last updated 2026-09-17, mid-run.

---

## 1. The sample is 45 problems, not 47

`tyrtleli/thinking-benchmark-90` (split=test) has **47** rows; **45** have
canonical solutions. The canonical-solution floor — the point of the whole
trace-length comparison — only exists for those 45, so every figure is over 45.

Use the new `--solutions-only` flag. **Do not use `--n-problems 45`**: that
slices the first 45 rows by dataset position, which is a different set.

The two excluded rows are long and expensive, so running 47 wastes noticeably
more than the 4% the row count suggests.

`hard-but-doable-10` is a separate 10-problem set at k=32; all 10 are inside
the 45.

## 2. Effort must land in the filename

`--effort LEVEL` overrides the curated `_EFFORT` entry. Two things it does
deliberately:

- **It refuses to apply to models with no effort knob.** Sending an effort to a
  model that has none is the silent-remap bug `_EFFORT` exists to prevent. If
  none of the selected models has a knob it exits non-zero rather than running.
- **It appends the level to the output tag**, so `..._high.json` and
  `..._max.json` are separate files. Without this, a second run at a different
  level resumes off the first one's file, prints `nothing new — skipping`, and
  produces no data while looking like a success.

Which models actually have a working knob is in the memory note
`benchmark-effort-parameter-trap`; the short version is that only the newest
model in each family does, and vendor docs have been wrong (GLM 5.2's
documented medium→high mapping did not hold in practice — verify empirically).

## 3. Provenance is now recorded on both sides

A filename asserts a setting. These prove it.

**Request side** — `<slug>_<tag>_runconfig.json`, written next to the results
before the sweep starts: `provider_pin`, `reasoning_sent`, `effort_override`,
`max_tokens_requested`, `cap_applied`, `n_problems`, `dataset`, timestamp.

**Response side** — per attempt, surfaced per task:

| field | why |
|---|---|
| `providers_used` | pin held, or fallback happened |
| `generation_ids` | joinable to `GET /api/v1/generation?id=...` |
| `reasoning_sent` | what we asked for |
| `models_served` | the **resolved** snapshot — catches mid-study drift when a rolling pointer like `deepseek/deepseek-v3.2` resolves to a dated build |
| `finish_reasons` | `"length"` is truncation as a fact, not inferred from `output_tokens == cap` |

Check the runconfig before trusting any result's filename.

## 4. Do not lower the client timeout

```python
client = OpenAI(..., timeout=900.0, max_retries=5)
```

Both numbers have been broken before and restored:

- **`timeout=900.0`.** Requests are **not** streamed — there is no `stream=True`
  on the `chat.completions.create` call — so the read timeout spans the *entire*
  generation; the first byte arrives only when the model is done. On 2026-09-17 I
  replaced this with `httpx.Timeout(read=240)` on the theory that a silent socket
  is a dead one. That reasoning only holds for streaming responses, and at 240s it
  aborts every trace longer than four minutes. Reverted.
- **`max_retries=5`.** Setting it to 0 removes the SDK's `Retry-After` handling;
  `one_request`'s own 2/4/8s sleeps are far too short for a rate-limit cooldown.
  This raised Kimi K3's failed requests from 115 to 174.

**Slow is not stalled.** DeepSeek V4 Pro at `effort=high` under a 40k cap runs
about **2 minutes per request**, roughly 2.5–3 req/min at `--workers 6`, so a
360-request pass is about two hours. Diagnostics that look alarming but are
normal: near-zero CPU time (the work is network wait), ESTAB sockets exactly
equal to the worker count (all workers busy), and a few CLOSE-WAIT sockets
(idle pooled connections the remote closed). None of these indicate a hang.

The progress counter prints every 20 completed requests with `flush=True`, so
with six workers at 2 min/request the first line appears ~6–7 minutes in.
Silence before that is expected.

## 5. Resume semantics

`_done(r)` requires **all** of a task's trials to have `total_completion_tokens
> 0`. A task with any zero-token trial is discarded and re-run whole, which is
what makes the repair loop work — a failed request is otherwise stored as a
zero-token record and graded as a wrong answer, indistinguishable from a real
miss.

Consequence: **results are written only when a model finishes.** Killing a
running pass discards everything in flight. Before restarting anything, check
whether a results JSON exists yet.

## 5a. One provider for the DeepSeek family

All four DeepSeek models are pinned to **SiliconFlow at fp8**. The reason is not
price or speed — it is that we set no `temperature`, `top_p` or `seed`, so
**provider sampling defaults apply**. One provider across the series means one
set of defaults, so provider is not a confound in the within-family comparison.

Two things that are easy to get wrong here:

- **fp8 is not a compromise, it is the ceiling.** No OpenRouter provider offers
  bf16/fp16 for any of these models; the menu is fp8 or fp4. Every pin is already
  at fp8, so there is no quantization upgrade available.
- **SiliconFlow is not the cheapest.** For V4 Pro, GMICloud is fp8 at 943k
  max_out for $0.96/$1.91 vs SiliconFlow's $1.50/$3.14. Single-provider
  consistency is being bought, deliberately, at roughly a 55% premium on that
  model. If the budget matters more than the confound, that is the tradeoff to
  revisit.

SiliconFlow advertises `max_completion_tokens` >= 147,456 on all four, far above
the 40k cap, so the cap binds uniformly.

Prices in `MODELS` were corrected to SiliconFlow's at the same time; several
entries had carried a different provider's numbers, which quietly skews any cost
estimate computed from them.

## 5b. API keys

The script looks for **`ERA_OPENROUTER_V2` first**, then `OPENROUTER_API_KEY`,
and prints which one it used. The runconfig records `key_env` — the variable
name, never the key.

`ERA_OPENROUTER_V2` wins because it is the funded key, and a sweep that dies
mid-model on an exhausted key loses everything in flight (see §5).

Keys live in `~/.bash_profile`, which zsh does not read — `source` it first.
That file has been mode 644 on this shared node; `chmod 600` it.

## 6. Drivers

[`code/drivers/`](code/drivers/) — copied out of a session scratchpad, which is
ephemeral. A previous chain died when the scratchpad was cleared between
sessions; launch with `setsid nohup ... &` so the driver survives.

- `ds_siliconflow_chain.sh` — the current one. V3.1 Terminus → V3.2 → V4 Pro
  high → low → max, all on SiliconFlow, `--solutions-only`, `--workers 8`, with
  up to 3 repair passes at 4. Oldest model first, so if the clock runs out the
  timeline keeps its early anchor.
- `ds_r1.sh` — R1-0528 at `--workers 12`, run concurrently. It was already
  running on SiliconFlow at the right settings, so it was left alone rather than
  folded into the chain; that is why the chain omits R1.
- `ds_v4_chain45.sh` — superseded (it pinned V4 Pro to Parasail).

Both follow the same shape: main pass at `--workers 6`, then loop up to three
repair passes until the zero-token count reaches 0.

This replaced a two-script handoff where a supervisor waited for the high-pass
JSON and then `pkill`ed the first driver. That was a latent bug: the JSON is
written *before* the repair loop runs, so the supervisor would have killed the
driver mid-repair. One driver, one process, no file-watching handoff.

## 7. In flight as of 2026-09-18 10:30

Complete, 45 problems, k=8, cap 40,000, all on SiliconFlow via OpenRouter.
Accuracy shown raw and right-censored at 32,768:

| model | raw | censored @32,768 | median tokens | over 40k cap |
|---|---|---|---|---|
| R1-0528 | 76.9% | 63.9% | 21,535 | 76 |
| V3.2 | 91.1% | 84.4% | 11,572 | 25 |
| V4 Pro (Apr build) high | 80.3% | 78.1% | 8,518 | 0 (41 cut at 32,768) |
| V3.1 Terminus | 60.6% | 60.6% | 2,940 | 0 — **dropped**, see 7c |

R1's 13-point drop under censoring is the measure of how much SiliconFlow
ignoring `max_tokens` was flattering it. Read those raw numbers with care: V3.2
beating the frontier model is substantially an artifact of V3.2 being allowed
82,918 tokens while V4 Pro was held to 40,000.

Running: V4 Pro (Apr build) `max` on OpenRouter, and the full
`DeepSeek V4 Pro GA` chain (high → low → max) on the direct API.

**Measured throughput, so nobody re-derives it:** one R1-0528 request at these
exact settings took **265.7s** (5,651 output tokens, `finish_reason: stop`).
V4 Pro on Parasail ran ~65s/request effective at 6 workers. The completion
counter prints every 20 requests and **decelerates** as a pass proceeds, because
short generations finish first and what remains in flight skews long. A counter
that has not moved in 20 minutes is normal; confirm with an I/O delta
(`/proc/<pid>/io` rchar over two minutes) before concluding anything is stuck.

## 7a. DeepSeek: which build is which

Two V4 Pro results exist and they are **different models**. Never merge them.

| our label | endpoint | model string | build |
|---|---|---|---|
| `DeepSeek V4 Pro` | OpenRouter | `deepseek/deepseek-v4-pro` | fixed **2026-04-24** listing |
| `DeepSeek V4 Pro GA` | api.deepseek.com | `deepseek-v4-pro` | **rolling**, currently the 0813 GA build |

OpenRouter lists `deepseek/deepseek-v4-pro` (2026-04-24) and
`deepseek/deepseek-v4-pro-0813` (2026-08-12) as separate entries, so the
OpenRouter pin is stable. DeepSeek's own API is not: their 2026-08-13 release
note says "simply set the model name to `deepseek-v4-pro` to use **the latest
version**." The only build identifier it returns is `system_fingerprint`, which
is why that is now recorded per attempt as `fingerprints` (observed
`a307abda487cd1b463329ccb945ce396`). **Check it before pooling runs** — if it
changes between passes, DeepSeek shipped a new build mid-study.

Results go to `deepseek_v4_pro_ga_shallow_pass/`, a separate folder, so the two
cannot be merged by accident.

**Effort levels are low / high / max**, confirmed by that same release note
("use low for simple tasks, high for daily Agent tasks, and max for more complex
scenarios"). OpenRouter's API accepts seven values
(`max|xhigh|high|medium|low|minimal|none`; anything else is a 400) and routes the
rest internally onto those three — so sending `medium` gets silently remapped,
the trap that invalidated the GLM 5.2/5.3 sweep. Send only the three native ones.

On the direct API, effort is a **top-level `reasoning_effort`**, not
`extra_body.reasoning.effort`, and the CoT arrives as **`reasoning_content`**,
not `reasoning`. Both are handled in `one_request`.

**Do not request `deepseek-reasoner` on the direct API.** It is served as
`deepseek-flash` — measured, three for three. Flash is the efficiency variant,
explicitly out of scope. Always name `deepseek-v4-pro` and check `models_served`.

## 7b. Why V4 was re-run directly

SiliconFlow truncated V4 Pro trials at **32,768** despite a 40,000 request — 41
of 360 on the `high` pass — while other trials on the same model and effort ran
to the full 40,000. The truncation point varied **per request**, so two trials of
the same problem were not measuring the same thing. It looks like load-balancing
across backends with different output limits.

The direct API has one backend. A measured request on the problem that truncated
under OpenRouter returned **39,946 tokens with `finish_reason: "stop"`** — it
generated to the cap and stopped naturally.

Separately, SiliconFlow ignores `max_tokens` entirely for the models with no
effort knob: R1-0528 ran to 66,106 (76 trials over cap) and V3.2 to 82,918 (25
over). Those need `censor_over_cap.py`; the decision recorded so far is **40,000
as primary** (matching GLM/Kimi/Opus so cross-family comparisons stay valid) with
32,768 as a robustness check.

## 7c. SiliconFlow mangles V3.1 Terminus

Dropped from the study, recorded so nobody re-runs it there. Same problem, same
request, varying only the provider:

| provider | completion tokens | content chars |
|---|---|---|
| SiliconFlow | 4,419 | **0** |
| AtlasCloud | 9,956 | 4,784 |
| Novita | 9,746 | 1,494 |
| StreamLake | 11,280 | 3,934 |

SiliconFlow returns under half the tokens and **no answer content at all** —
359 of 360 trials in the full run. The `<think>` block is never closed, so the
whole generation including the answer is labelled reasoning. Recoverable
(`recover_trace_answers.py` took it from 0.3% to 60.6%) but the trace lengths are
not trustworthy, so the model was dropped rather than re-run.

This was nearly missed: the run had zero errors, zero zero-token trials, reasoning
tokens present, one provider, one snapshot, and every trial `finish: stop`.
`reasoning_tokens > 0` is **not** sufficient evidence that thinking is on.

## 7d. Results, and why there are two groups

**Compare only within provider.** Measured 2026-09-18: after censoring both to a
common 32,768 ceiling, the same V4 Pro family scored **6-14 points** differently
across endpoints, so truncation is not the explanation. Three things differ between
the groups at once - model version (Apr vs GA build), quantization (SiliconFlow
fp8 vs DeepSeek native), and serving behaviour - and this data cannot decompose
them. Running `deepseek/deepseek-v4-pro-0813` (the GA build at fp8) would isolate
quantization from version; not done.

**Group 1 - timeline.** OpenRouter -> SiliconFlow, fp8, censored @32,768:

| model | released | accuracy | median tokens |
|---|---|---|---|
| R1-0528 | May 2025 | **66.1%** | 21,535 |
| V3.2 | Dec 2025 | **85.6%** | 11,572 |
| V4 Pro (Apr build) | Apr 2026 | 78.1% | 8,518 |

Trace length falls monotonically, 21,535 -> 8,518, a 2.5x reduction. Raw
(uncensored) accuracies were 76.9 / 91.1 / 80.3; R1 loses **10 points** to
censoring because SiliconFlow let it run to 66,106 tokens. Never quote raw numbers
across models with different cap compliance.

> **Accuracy column corrected 2026-09-21.** It previously read 63.9 / 84.4 / 78.1,
> which are the **PRE-REGRADE** grades (verified: `correct_original` reproduces those
> three figures exactly). The regrade flips 8 R1 trials and 4 V3.2 trials and **none**
> for V4 — which is why V4 alone looked consistent. Note the direction: regrading
> raises the two EARLIER models only, so the true V4 dip is **larger** than the old
> table implied, 85.6 -> 78.1 (-7.5 points) rather than 84.4 -> 78.1 (-6.3).
> Medians are unaffected and reproduce exactly (all 45 problems, all traces, clamped
> at 32,768 — that is the sample definition for this table).

The **V4 dip to 78.1% is partly artifact**: censoring penalises whichever model hits
the ceiling most, and V4 Pro April had 76 trials >=32,768 against V3.2's 43.

**But censoring is not the whole story, and two further confounds sit on this line.**

*The requested cap bound on V4 and not on its predecessors.* All three runs asked for
`max_tokens=40000`. SiliconFlow enforced it exactly on V4 (max token count exactly
40,000, zero trials above) and **ignored it** on R1 (ran to 66,106; 76 trials >40k, 24
of them correct) and V3.2 (82,918; 25 trials >40k, 7 correct). So the earlier models
were allowed to keep thinking past the budget and got credit for answers V4 was cut
off before reaching. Scoring everything at the cap that was actually requested, on the
40 competition problems: R1 **69.1%**, V3.2 **89.1%**, V4 **77.8%**. The dip shrinks
but does not vanish, so it is not purely a ceiling artifact.

*The timeline is not effort-matched, but this is unavoidable rather than an error.*
From the runconfigs, R1 and V3.2 were sent `{"enabled": true}` with
`effort_override: null` — no effort at all, i.e. the provider default — while V4 was
sent `{"effort": "high"}`. **The April V4 build has no `low`**, only `high` and `max`
(Natalia), so `high` is the lowest available arm and there is no setting that matches
an unspecified-effort run. Worth stating in any caption; it cannot be fixed by
re-running.

*The `_low` V4 file is not evidence about effort.* `low` does not exist on that build,
so the request was silently remapped: its median lands on `high` (10,745 vs 11,862),
not below it. Archived to `data/archive/deepseek_v4_apr_low_unsupported/`. A real
low-effort arm looks like the GA build's 4,812 against high's 12,129. So the earlier
reading that "SiliconFlow collapses low and high" was wrong — nothing was collapsed,
an unsupported value was substituted.

**USE A COMMON CEILING OF 32,768, AND THE DIP SURVIVES.**

This section has been wrong twice. The resolution: cutting every model off at one
ceiling IS the right comparable sample (Natalia's point), and the ceiling has to be
**32,768**, not the 40,000 that was requested.

*Why 32,768 and not 40,000.* At 32,768 nothing is unknown for any model. R1 and V3.2
never truncated, so their full lengths are known and anything over 32,768 would have
been cut -> wrong. V4 either stopped AT 32,768 (so it needed more -> wrong) or ran past
it (needed more -> wrong). At 40,000, by contrast, V4's 41 trials that the provider cut
at 32,768 are **censored**: we cannot tell whether they would have finished by 40,000.
A 40,000 comparison therefore requires guessing about 41 of V4's 320 trials, and the
earlier table in this file that quoted 69.1 / 89.1 / 77.8 at a 40k ceiling was doing
exactly that.

*Where the truncation actually is.* Trials at an exact ceiling value, 40 competition
problems:

| run | @32,768 | @40,000 | max | over 32,768 |
|---|---|---|---|---|
| R1-0528 | 0 | 0 | 66,106 | 108 (33.8%) |
| V3.2 | 0 | 0 | 82,918 | 43 (13.4%) |
| V4 Pro Apr `high` | 41 | 27 | 40,000 | 76 (23.8%) |

R1 and V3.2 have no spike anywhere: `max_tokens=40000` was ignored and they always ran
to completion. V4 hit two hard ceilings, and all 68 of those trials grade wrong with 66
carrying empty response text.

*The answer, at a common 32,768 ceiling:*

| run | accuracy | median tokens |
|---|---|---|
| R1-0528 | 61.9% | 23,554 |
| V3.2 | **83.8%** | 13,946 |
| V4 Pro Apr `high` | **75.3%** | 11,862 |

**The V3.2 -> V4 dip is about 8.5 points and it is real at a matched budget.**

*But the mechanism is the tail, not typical verbosity.* V4 has the SHORTEST median of
the three (11,862 against V3.2's 13,946) while running over 32,768 nearly twice as
often (23.8% against 13.4%). p75 tells the same story: 31,717 against 25,412. V4 is
more concise on a typical problem and blows up more often on a hard one, so under a
fixed budget it fails more. That is a real and reportable property, and it is a
different claim from "V4 reasons worse".

*Retracted:* an earlier version of this section led with V4 at **98.8%** (249/252),
computed by dropping V4's provider-truncated trials from the denominator. That is an
asymmetric selection — it discards V4's hard cases while keeping R1's and V3.2's long
trials and counting them as successes. Do not quote it.

Whatever ceiling a figure uses, use the same one for every model — but for DeepSeek,
also say how many trials each model lost to it.

*Cross-endpoint gap, for reference only:* V4 Pro at nominally the same effort scores
SiliconFlow 77.8% against DeepSeek-direct GA 85.9%. GA is a different build AND a
different provider AND native precision, so this does not belong on the timeline; it
only bounds how much of V4's level is serving-specific.

**Group 2 - effort branch.** DeepSeek direct API, GA build, censored @32,768. Zero
trials cut at 32,768:

| effort | accuracy | median tokens |
|---|---|---|
| low | **92.5%** | **3,963** |
| high | 84.4% | 9,901 |
| max | 81.4% | 8,325 |

`low` dominates - best accuracy on ~40% of `high`'s tokens - and `max` is both
worse and shorter than `high`. Unusual shape; verify before publishing.

**Effort control is build-dependent.** The Apr-2026 build collapses `low` and
`high` (9,098 vs 8,518 median, 80.6% vs 80.3%); only `max` differs (15,268). Effort
arrived with the GA release. So the effort branch must come from GA, and it is
reported as its own panel rather than hung off the timeline's V4 point.

**Single-problem probes lie about effort.** n=1 and n=5 samples showed `low` >
`high`; at 360 trials the ordering was clean. Judge effort response only at scale.

## 8. Known gaps

- **DeepSeek hard-but-doable-10 at k=32**: nothing usable. Old files in
  `~/deepseek_test` cover only 5 of the 10.
- **Kimi K3 has no valid k=8 result** — the original ran at an invalid
  `"medium"`, was archived, and was never re-run. It is the only effort-capable
  Kimi, so that line currently has no effort-matched member.
- **Kimi has no k=32 data at all** (that sweep was cancelled).
- **Over-cap censoring not yet applied**: GLM 4.5 and 4.7 only, 108 attempts
  across 4 files, max 78,917 against a 40,000 request. `code/censor_over_cap.py`
  is report-only without `--write`.
- Optional GLM effort branching: 5.2 @ `max`, 5.3 @ `low` and `max` (~$113).

## 9. Shared-system rules

This runs on MIT ORCD, a quota-limited multi-user HPC node. Never traverse
`/orcd/scratch` or `/orcd/pool`; scope every filesystem command to a known
directory with bounded depth; read `~/orcd/.quota` rather than computing usage.
Check `/etc/motd.d/` before substantial work.

Two shell traps that have produced wrong answers here repeatedly:

- `pgrep -f <pattern>` **matches its own command line**. Filter with
  `ps ... | grep -v grep | grep -v snapshot`, or kill by PID.
- `pkill -f "<pattern>"` will kill **the shell running the pkill** if the
  pattern appears in that command line. Prefer explicit PIDs.

## 10. Comparability rules

- Compare accuracies **only on the same grader**. Mixing regraded and
  un-regraded numbers produced a false "+4 point" result during this work; the
  real figure was +1.0.
- A single easy problem is not a cost estimate. Extrapolating from 3 easy
  problems overstated a model's cost by 2×; the easy problems are 2–6× cheaper
  than average across every model.
- Right-censor to a common ceiling before comparing trace lengths across
  providers with different caps.
