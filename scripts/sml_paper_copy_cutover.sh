#!/usr/bin/env bash
# Controlled V2 -> six-wallet PAPER ONLY cutover. No real orders.
set -Eeuo pipefail
umask 077
MODE="${1:-preflight}"
if [[ "$MODE" != "preflight" && "$MODE" != "switch" ]]; then
  echo "Usage: bash scripts/sml_paper_copy_cutover.sh preflight|switch" >&2
  exit 2
fi
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Original V2 directories vary with Unix user and initial checkout.
# Use an operator-verified absolute path; NEVER auto-select a budget ledger.
V2DIR="${YATL_V2_DATA_DIR:-$HOME/yatl-smart-money-v2/data/smart_money}"
BUDGET="${YATL_SML_HELIUS_BUDGET_FILE:-$V2DIR/helius_budget.json}"
OUTPUT="$HOME/yatl-paper-copy-forward-20261101"
WATCH="$ROOT/research/smart_money_lab/data/selected_forward_paper_wallets_20261101.json"
HOURS="${YATL_PAPER_HOURS:-6}"
POLL="${YATL_PAPER_POLL_SECONDS:-300}"
if [[ "$BUDGET" != /* ]]; then
  echo "Helius budget path must be absolute and refer to the ORIGINAL V2 file." >&2
  exit 2
fi
if [[ ! -f "$BUDGET" ]]; then
  echo "Original V2 cumulative budget file is missing: $BUDGET" >&2
  echo "Verify original V2 process working directory / env; do NOT create or reset the counter." >&2
  echo "Use YATL_SML_HELIUS_BUDGET_FILE=/real/absolute/path to override only after verification." >&2
  exit 2
fi
cd "$ROOT"
python3 -m research.smart_money_lab.paper_copy_next \
  --watchlist "$WATCH" --existing-budget-file "$BUDGET" \
  --output-dir "$OUTPUT" --hours "$HOURS" --poll-seconds "$POLL"

if [[ "$MODE" == "preflight" ]]; then
  echo "Preflight only: no API requests and NO process changes."
  exit 0
fi
if [[ -z "${HELIUS_API_KEY:-}" ]]; then
  echo "No HELIUS_API_KEY in current shell: load your EXISTING VPS secret privately." >&2
  echo "V2 has NOT been stopped." >&2
  exit 2
fi
if [[ -f "$OUTPUT/paper_copy_state.json" ]]; then
  echo "A forward paper-copy state exists. Do not overwrite or start duplicate." >&2
  exit 2
fi

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
ARCHIVE="$HOME/yatl-v2-final-archive/$STAMP"
mkdir -p "$ARCHIVE"
for name in state.json report.json; do
  [[ ! -f "$V2DIR/$name" ]] || cp -p "$V2DIR/$name" "$ARCHIVE/$name.before"
done
cp -p "$BUDGET" "$ARCHIVE/helius_budget.json.before"

# Stop only the known V2 observer pane; keep the dashboard publisher alone.
if command -v tmux >/dev/null 2>&1 && tmux has-session -t yatl-sml-v2 2>/dev/null; then
  tmux send-keys -t yatl-sml-v2 C-c
  sleep 4
fi
if pgrep -af 'research[.]smart_money_lab observe' >/dev/null 2>&1; then
  echo "V2 observer is STILL running; no second Helius poller launched." >&2
  echo "Archive: $ARCHIVE" >&2
  exit 3
fi
for name in state.json report.json; do
  [[ ! -f "$V2DIR/$name" ]] || cp -p "$V2DIR/$name" "$ARCHIVE/$name.final"
done
cp -p "$BUDGET" "$ARCHIVE/helius_budget.json.final"

mkdir -p "$OUTPUT"
chmod 700 "$OUTPUT"
# Python receives key from current environment, not command-line arguments.
nohup python3 -u -m research.smart_money_lab.paper_copy_next \
  --watchlist "$WATCH" --existing-budget-file "$BUDGET" \
  --output-dir "$OUTPUT" --hours "$HOURS" --poll-seconds "$POLL" \
  --start-paper > "$OUTPUT/console.log" 2>&1 < /dev/null &
PID=$!
printf '%s\n' "$PID" > "$OUTPUT/paper_copy.pid"
sleep 2
if ! kill -0 "$PID" 2>/dev/null; then
  echo "Forward paper-copy process exited early; review private log:" >&2
  echo "tail -n 40 $OUTPUT/console.log" >&2
  exit 4
fi
echo "V2 archived at $ARCHIVE; forward 6-wallet PAPER pilot PID=$PID."
echo "NO real-money orders. Original 5000-call Helius budget preserved."
echo "Live status: tail -f $OUTPUT/console.log"
echo "Saved report: $OUTPUT/paper_copy_report.json"
echo "Stop safely: kill -TERM $(cat "$OUTPUT/paper_copy.pid")"
