# Superseded LLM-judge material — nothing here feeds the paper

Archived 2026-09-25, when the paper settled on its two judge runs:

| behaviour | prompt | judge | run (in `code/llm_judge/out/`) |
| --- | --- | --- | --- |
| verification | `verification_v0.txt` | gemini-2.5-flash | `judge_whole_gemini.jsonl` |
| backtracking | `backtracking_v6.txt` | gemini-3.1-pro-preview | `judge_backtracking_v6.jsonl` |

Everything below is how we got there. It is kept so the prompt history is
auditable. For the reasoning behind each version, see `code/llm_judge/README.md`
("The backtracking prompt, v0 → v3" and "v4 → v6").

**Still in `code/llm_judge/`, although superseded.** The v0, v2 and v3 backtracking
RUNS (`out/judge_whole_gemini.jsonl`'s backtracking records,
`out/judge_backtracking_v2.jsonl`, `_v3.jsonl`) stay there. The appendix table
`paper_figs/table_backtracking_prompts.tex` reads them, to show the result under every
prompt definition. Only their prompt TEXTS are here.

## Contents

- `prompts/backtracking_v0.txt` … `v5.txt`: the superseded backtracking prompts.
  - v0 is Gandhi et al.'s template plus a one-line domain edit.
  - v2 and v3 were rewrites after RA review.
  - v4 and v5 are the quoted-instance pilots that led to v6.
- `gold_strict.json`: the strict key on the 20 review traces (commit, explicit
  failure, switch). It measures a stricter construct than the paper's, so it cannot
  validate v6. The soft key that does is `code/llm_judge/gold_soft/`.
  `pilot_v4.GOLD` still points here, so `pilot.py --compare` keeps working.
- `out/`: pilot outputs and logs for prompts v4 and v5, and for the v6 judges not
  chosen (gemini-2.5-pro, gemini-3.8-flash).
  - Scored with the strict key; `pilot.py --compare` reads `code/llm_judge/out/`,
    so copy a file back there to include it.
  - The chosen v6 pilot (`pilot_v6_gemini-3.1-pro-preview.jsonl`) is NOT here. It is
    the validation run and stays in `code/llm_judge/out/`.
- `tools/audit.py`, `tools/make_review_pack.py`: built for the v0-era "## Thoughts"
  output format and the v0/v2/v3 review packs.
- `review_packs/`: the RA packs for v0 (`backtracking/`, `verification/`), v2 and v3.
  - The v0 and v2 packs keep their own `traces/` copies.
  - The v3 pack's `traces/` and `verdicts.csv` moved to
    `code/llm_judge/for_RA_review/review_traces/` (the latter as `index.csv`), because
    the v6 pack, the v6 pilot and `gold_soft/` all read them. The v3 sheets' trace
    links are therefore broken; open the traces from `review_traces/traces/`.
