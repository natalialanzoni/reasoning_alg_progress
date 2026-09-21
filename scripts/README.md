# `scripts/` — shell entry points

Every script here `cd`s to the repo root first, so they work from anywhere:
`bash scripts/<name>.sh`.

## Rebuilding the paper — the only two you normally need

| script | what it does |
| --- | --- |
| `make_paper_figs.sh` | **the paper.** Runs each producing script once, copies the cited artifacts into `paper_figs/`, writes `paper_figs/MANIFEST.md` with the commit and the artifact→script map. |
| `make_all_figures.sh` | everything the live scripts emit, sensitivity variants included, into `figures/figs_sept/`. Takes `main`, `appendix` or `all` (default). |

`figures/figs_sept/` is a build intermediate and is gitignored — it is recreated on
every run. `paper_figs/` is the committed deliverable.

## Launching new benchmark runs

These call the OpenAI API and cost money. **Read the header comment before using
one** — each is pinned to the exact settings the published runs used, and the header
says which reference run those settings were verified against.

| script | sweep |
| --- | --- |
| `run_openai_shallow.sh <model>` | k=8 over the 45 canonical problems, medium effort, 40k cap |
| `run_openai_hard.sh <model>` | k=32 over the hard-but-doable-10, medium effort |
| `run_openai_effort.sh <model> <low\|high>` | k=8 over the hard-but-doable-10 at one effort |
| `run_o1.sh`, `run_o1_hard.sh` | the o1 anchor runs, kept for provenance |

Two traps these scripts exist to prevent, both of which have bitten this project:

- `benchmark_math_dist.py`'s `--max-tokens` **defaults to 100000**. Every published
  run used **40000**. The scripts pin it; do not drop the flag.
- **k differs by sweep.** The effort arms are k=8 while the hard-but-doable set is
  k=32, on the *same* dataset. Using the wrong one makes a new model incomparable
  with every existing point. See README run-hygiene item 12.

After any run: `./venv/bin/python code/apply_regrade.py --write`. Never plot an
ungraded run.

## Legacy sweep drivers

`run_on_server.sh`, `run_glm_high.sh` and `run_{low,medium,high,max}_reasoning.sh`
predate the pinned `run_openai_*.sh` scripts and were used for the GLM and
open-source sweeps. Kept for provenance. They were written to sit at the repo root and
their `cd` was corrected when they moved here; check the settings they send against
the run hygiene section before reusing one.
