# `code/archive/` — superseded scripts

Kept, not deleted. Nothing here is called by `make_all_figures.sh` or
`make_paper_figs.sh`, and nothing live imports any of it (checked before archiving).
Their outputs are in `figures/archive_figs/`, which has a table mapping each figure to
its script and the reason it was retired.

## Archived 2026-09-21 — superseded figure scripts

| script | produced | retired because |
| --- | --- | --- |
| `figures_sept_ft.py` | `fig1_ft_frontier*` | superseded by `figure1_grid_ft.py`; on the 45-problem sample |
| `figure1_glm_algo_ft.py` | `fig1_glm_algo` | GLM cross-version line is provider-confounded |
| `figure1_grid_glm_ft.py` | `fig1_grid_glm*` | same, plus the old `pos + 5` difficulty tiering |
| `figure1_oss_ft.py` | `fig1_oss` | superseded by the Scale column of `figure_mechanism_ft.py` |
| `figure3_pareto_ft.py` | `fig3_pareto` | on the 45-problem sample (includes MATH-500) |
| `figure_cv_ft.py` | `fig_cv` | never used in the write-up |

**Two reasons a script lands here**, and they are different:

1. *Superseded* — a better figure answers the same question. Nothing wrong with it.
2. *On the wrong sample* — it includes MATH-500, so it reports 45 problems and a
   303-token floor instead of the paper's 40 and 316. Those scripts would need to be
   brought onto the paper's sample before any output of theirs could be cited. See the
   sample-definition section at the top of the main README.

## Earlier archive (pre-2026-09)

`analyze_time_series_*.py`, `plot_figure1.py` and friends expect the old
`code/results/` layout rather than `data/`, so they do not run as-is. The `_ft`
scripts in `code/` replaced them and read `data/` directly.
