#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Regenerate every figure and table in the paper, in order.
#
#   bash code/make_all_figures.sh          # everything
#   bash code/make_all_figures.sh main     # only the main-text artifacts
#
# Each script prints its sample size and floor on startup. Every one that uses
# the paper's sample must say "40 competition problems ... floor = 316 tok".
# If a script prints 45 problems or a 303-token floor, it is on the wrong sample
# and its output must not go in the paper.
#
# Outputs land in figures/figs_sept/. Exits non-zero on the first failure.
# ---------------------------------------------------------------------------
set -euo pipefail
cd "$(dirname "$0")/.."
PY="./venv/bin/python"
export MPLBACKEND=Agg

MAIN=(
  figure1_grid_ft.py          # Fig 1 (+ _fulldiff, + _alltraces appendix)
  figure_forecast_ft.py       # Fig 4 two-panel (+ contamination + sensitivities)
  figure_latent_floor_ft.py   # Fig 5 distance to floor: 2x2, samples x families
  figure_mechanism_ft.py      # case study: scale vs algorithm
  table_floor_robustness.py   # appendix table: four floor definitions
)
APPENDIX=(
  figure_effort_ft.py         # trace length by reasoning effort
  figure2_ft.py               # hard-problem distributions
  figure3_pareto_ft.py        # accuracy/token pareto
  figure_cv_ft.py             # coefficient of variation over generations
  figures_sept_ft.py          # fig1_ft_frontier variants
)
# Open-source GLM figures. PARKED: the cross-version GLM line is provider
# confounded (see README failure mode 7) and these still use the OLD difficulty
# tiering and include MATH-500. Do not put their output in the paper without
# bringing them onto the 40-problem sample first.
PARKED=(
  figure1_grid_glm_ft.py
  figure1_glm_algo_ft.py
  figure1_oss_ft.py
)

run() {
  for s in "$@"; do
    printf '\n\033[1m=== %s ===\033[0m\n' "$s"
    "$PY" "code/$s" 2>&1 | grep -vE "UserWarning|warnings.warn|^\s*plt\.tight_layout" || true
    # shellcheck disable=SC2181
    [ "${PIPESTATUS[0]}" -eq 0 ] || { echo "FAILED: $s"; exit 1; }
  done
}

case "${1:-all}" in
  main)     run "${MAIN[@]}" ;;
  appendix) run "${APPENDIX[@]}" ;;
  parked)   run "${PARKED[@]}" ;;
  all)      run "${MAIN[@]}" "${APPENDIX[@]}" ;;
  *) echo "usage: $0 [main|appendix|parked|all]"; exit 2 ;;
esac

echo
echo "Done. Sanity-check the startup lines above: scripts on the paper's sample"
echo "report 40 competition problems and a 316-token floor. NOT every script is --"
echo "figure3_pareto_ft.py and figures_sept_ft.py still include MATH-500. See the"
echo "\"Which scripts are on the paper's sample\" table in README.md."
