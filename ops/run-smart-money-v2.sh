#!/usr/bin/env bash
# Start a NEW v2 research window in an isolated tmux session.
# The old experiment is never opened for writes. Helius uses its original cap.
set -Eeuo pipefail
umask 077

ROOT="/home/ubuntu/yatl-smart-money-v2"
OLD="/home/ubuntu/yatl-smart-money"
cd "$ROOT"
BUDGET="$OLD/data/smart_money/helius_budget.json"
[[ -f "$BUDGET" ]] || { echo "ERROR: original quota file missing. Refusing new key quota." >&2; exit 2; }
[[ -f data/smart_money/screened.json ]] || { echo "ERROR: screened cohort missing." >&2; exit 2; }

echo "V2: paper-only; no trading keys, real orders or funding."
echo "Source cohort: historical cached exploratory selection (UNVETTED)."
echo "Original Helius quota ledger remains in use: $BUDGET"
read -rsp "Enter Helius free API key (hidden): " HELIUS_API_KEY
echo
[[ "${#HELIUS_API_KEY}" -ge 8 ]] || { echo "ERROR: short or missing API key" >&2; exit 2; }
export HELIUS_API_KEY
export YATL_SML_HELIUS_BUDGET_FILE="$BUDGET"
trap 'unset HELIUS_API_KEY' EXIT

uv sync --locked
arguments=(observe --exploratory
    --screened data/smart_money/screened.json
    --state data/smart_money/state.json
    --report data/smart_money/report.json
    --html data/smart_money/dashboard.html
    --hours 24 --poll-seconds 180)
if [[ -f data/smart_money/state.json ]]; then
    # Do not reset/rewrite a previously started v2 experiment.
    arguments+=(--resume)
    echo "Resuming existing v2 paper state; original start time retained."
else
    echo "Starting NEW 24h v2 experiment with distinct ledger and results."
fi
uv run --locked python -m research.smart_money_lab "${arguments[@]}"
