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
  figure1_grid_ft.py          # Fig 1 (+ _thinking, + _alltraces, + _fulldiff)
  figure2_ft.py               # Fig 2 hard-problem distributions
  figure_mechanism_ft.py      # Fig 3 case study: scale vs algorithm
  figure_forecast_ft.py       # Fig 4 two-panel (+ contamination + sensitivities)
  figure_latent_floor_ft.py   # Fig 5 distance to the floor
  table_decay.py              # main regression table
)
APPENDIX=(
  figure_effort_ft.py         # trace length by reasoning effort
  table_floor_robustness.py   # floors, thinking-only row
  figure1_deepseek_ft.py      # open-source: DeepSeek timeline
  figure_deepseek_branch_ft.py  # open-source: DeepSeek effort branch
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
  all)      run "${MAIN[@]}" "${APPENDIX[@]}" ;;
  *) echo "usage: $0 [main|appendix|all]"; exit 2 ;;
esac

echo
echo "Done. Sanity-check the startup lines above: every script on the paper's sample"
echo "reports 40 competition problems and a 316-token floor. The DeepSeek scripts"
echo "additionally report a 32,768 ceiling -- see README run-hygiene item 13."
echo
echo "This regenerates figures/figs_sept/ (the working directory, variants included)."
echo "For the curated set the paper actually uses, run: bash code/make_paper_figs.sh"
