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

## 7. In flight as of 2026-09-17 15:50

- **DeepSeek R1-0528** on SiliconFlow, 45 problems, k=8, cap 40k, 12 workers —
  running, 20/360 at 15:47. **Leave it alone.**
- The V4 Pro run on Parasail was stopped when the family was standardized on
  SiliconFlow; nothing had been written.
- `ds_siliconflow_chain.sh` is ready but **not launched**, pending
  `ERA_OPENROUTER_V2`.

**Measured throughput, so nobody re-derives it:** one R1-0528 request at these
exact settings took **265.7s** (5,651 output tokens, `finish_reason: stop`).
V4 Pro on Parasail ran ~65s/request effective at 6 workers. The completion
counter prints every 20 requests and **decelerates** as a pass proceeds, because
short generations finish first and what remains in flight skews long. A counter
that has not moved in 20 minutes is normal; confirm with an I/O delta
(`/proc/<pid>/io` rchar over two minutes) before concluding anything is stuck.

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
