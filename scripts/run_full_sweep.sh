#!/usr/bin/env bash
# run_full_sweep.sh — DOCUMENTED WRAPPER for the per-book backtest.
#
# ⚠️ THIS SCRIPT DOES NOT RUN BY DEFAULT. It requires:
#   - a reachable RAG server (rag_server_canary.py on :8889/:8890) — NOT prod :8888
#   - a reachable Neo4j edu (bolt://localhost:7688) on the SAME host
#   - Gemma (:8080) for question generation
#   - env: EDU_NEO4J_PW, GEMMA_KEY
# The full sweep is EXPENSIVE (Gemma generates ~500 q/book × ~81 books ≈ 40k
# /retrieve calls). Per the canonical rules, do NOT run it casually and NEVER
# point it at production :8888.
#
# It is a thin loop over rag_edu/scripts/schema_v3_2026_06/backtest_book.py,
# which is the existing, unchanged scorer. This wrapper only:
#   1. enumerates (subject, grade, book, tap) triples,
#   2. invokes backtest_book.py per triple,
#   3. collects the per-book JSON into a run directory,
#   4. prints the run dir so reporters.py / compare_runs.py can consume it.
#
# USAGE:
#   DRY-RUN (default, prints the plan only, runs nothing):
#       scripts/run_full_sweep.sh
#   TARGETED (one book, e.g. the weakest slice):
#       RUN=1 PORT=8889 scripts/run_full_sweep.sh toan 4 CTST none
#   FULL (all books — only on a build host with server up):
#       RUN=1 PORT=8889 scripts/run_full_sweep.sh --all
#
# OUTPUT:
#   reports/backtest/<UTC-date>_<label>/backtest_<subject>_<grade>_<book>_t<tap>.json
#   Then:  python3 -m packages.backtest.reporters <run_dir>
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCORER="${REPO_ROOT}/rag_edu/scripts/schema_v3_2026_06/backtest_book.py"
PORT="${PORT:-8889}"          # canary; must NOT be 8888 (prod)
N="${N:-500}"                 # questions per book
RUN="${RUN:-0}"               # 0 = dry-run (print plan only)
LABEL="${LABEL:-full-sweep}"
RUN_DATE="$(date -u +%Y-%m-%d)"
RUN_DIR="${REPO_ROOT}/reports/backtest/${RUN_DATE}_${LABEL}"

# --- safety: refuse prod port ------------------------------------------------
if [[ "${PORT}" == "8888" ]]; then
  echo "REFUSING: PORT=8888 is production. Use canary 8889/8890." >&2
  exit 3
fi

# --- book matrix (subject grade book tap) ------------------------------------
# tap 'none' => whole book (single-volume subjects). Edit to match the corpus
# actually built in Neo4j; this mirrors the 65-book / 81-(subj,grade,book,tap)
# matrix from the 2026-06-17 sweep.
BOOKS=(
  "toan 4 CTST none"   "toan 5 CTST none"   "toan 6 KNTT none"
  "toan 8 CTST 1"      "toan 8 CTST 2"      "toan 8 CD 1"
  "lich_su 6 CTST none" "lich_su 7 CTST none" "lich_su 9 CTST none"
  "dia_li 9 CTST none"
  "gdcd 6 CTST none"
  "khtn 6 KNTT none"
  "ngu_van 8 CTST 1"   "ngu_van 8 CTST 2"
  # ... extend to the full matrix; see reports/backtest/2026-06-17_full-sweep/
)

run_one() {
  local subject="$1" grade="$2" book="$3" tap="$4"
  local tap_arg="$tap"; [[ "$tap" == "none" ]] && tap_arg="None"
  echo ">>> backtest ${subject} ${grade} ${book} tap=${tap_arg} N=${N} port=${PORT}"
  if [[ "${RUN}" == "1" ]]; then
    python3 "${SCORER}" "${subject}" "${grade}" "${book}" "${tap_arg}" "${N}" "${PORT}"
    # backtest_book.py writes /tmp/backtest_<...>.json — collect it
    mkdir -p "${RUN_DIR}"
    cp "/tmp/backtest_${subject}_${grade}_${book}_t${tap_arg}.json" "${RUN_DIR}/" 2>/dev/null || true
  fi
}

main() {
  echo "RUN_DIR=${RUN_DIR}"
  echo "RUN=${RUN} (0=dry-run, 1=execute)  PORT=${PORT}  N=${N}"
  if [[ "${RUN}" != "1" ]]; then
    echo "[dry-run] would score the following books (set RUN=1 to execute):"
  fi

  if [[ "${1:-}" == "--all" ]]; then
    for entry in "${BOOKS[@]}"; do
      # shellcheck disable=SC2086
      run_one $entry
    done
  elif [[ $# -ge 4 ]]; then
    run_one "$1" "$2" "$3" "$4"
  else
    echo "no target. Pass: <subject> <grade> <book> <tap>  OR  --all"
    printf '  %s\n' "${BOOKS[@]}"
    exit 0
  fi

  if [[ "${RUN}" == "1" ]]; then
    echo
    echo "DONE. Summarize with:"
    echo "  python3 -m packages.backtest.reporters '${RUN_DIR}'"
    echo "Compare against a baseline with:"
    echo "  python3 scripts/compare_backtest_runs.py <baseline_dir> '${RUN_DIR}'"
  fi
}

main "$@"
