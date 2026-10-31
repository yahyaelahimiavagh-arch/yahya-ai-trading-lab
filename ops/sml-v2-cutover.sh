#!/usr/bin/env bash
# Controlled V1 -> V2 paper-pilot cutover. Never trade or overwrite old output.
set -Eeuo pipefail
umask 077

OLD="/home/ubuntu/yatl-smart-money"
NEW="/home/ubuntu/yatl-smart-money-v2"
ARCHIVES="/home/ubuntu/yatl-sml-archives"

fail() { echo "SAFE STOP: $*" >&2; exit 2; }
old_active() {
  pgrep -f '^/home/ubuntu/yatl-smart-money/\.venv/bin/python -m research[.]smart_money_lab observe ' >/dev/null
}
preflight() {
  [[ "$(id -un)" == "ubuntu" ]] || fail "Run only as ubuntu on the YATL VPS."
  [[ "$(pwd -P)" == "$NEW" ]] || fail "Run from exactly $NEW; never from active $OLD."
  [[ "$(git branch --show-current)" == "research/smart-money-lab-paper-v1" ]] || fail "Unexpected Git branch."
  for binary in tmux python3 tar sha256sum uv pgrep; do
    command -v "$binary" >/dev/null || fail "Missing $binary"
  done
  for file in screened.json report.json state.json helius_budget.json; do
    [[ -f "$OLD/data/smart_money/$file" ]] || fail "Old $file absent. Do not proceed."
  done
  [[ ! -f "$NEW/data/smart_money/state.json" ]] || fail "V2 state already exists; never overwrite it."
  if tmux has-session -t yatl-sml-v2 2>/dev/null; then
    fail "V2 tmux session already exists."
  fi
  python3 - <<'PY'
import json
from pathlib import Path
from research.smart_money_lab.pilot import exploratory_watchlist
old = Path('/home/ubuntu/yatl-smart-money/data/smart_money')
rows = json.loads((old / 'screened.json').read_text(encoding='utf-8'))
blind, smart = exploratory_watchlist(rows)
budget = json.loads((old / 'helius_budget.json').read_text(encoding='utf-8'))
count = budget.get('calls')
assert type(count) is int and 0 <= count < 5000, "Helius budget exhausted/invalid"
assert len(smart) >= 2, "Insufficient paper candidates"
print(f"Read-only preflight: {len(set(blind)|set(smart))} unvetted monitored wallets; "
      f"{count}/5000 Helius calls reserved (shared across pilot versions).")
PY
  echo "Checking isolated V2 deterministic gates..."
  python3 -m unittest discover -s tests -p 'test_smart_money_lab.py' -q
  python3 -m unittest discover -s tests -p 'test_smart_money_live_monitor.py' -q
  python3 -m unittest discover -s tests -p 'test_smart_money_hostinger.py' -q
  bash -n ops/run-smart-money-v2.sh
  echo "SAFE: V2 ready for controlled cutover. No API calls made by preflight."
}

mode="${1:---prepare}"
[[ "$mode" == "--prepare" || "$mode" == "--switch" ]] ||
  fail "Use --prepare or --switch."
[[ -d "$OLD/.git" ]] || fail "Old experiment checkout missing."
[[ -d "$NEW/.git" ]] || fail "Isolated V2 checkout missing."
cd "$NEW"
preflight
if [[ "$mode" == "--prepare" ]]; then
  echo "PREPARE PASS. Re-run with --switch to stop V1, archive, and stage V2."
  exit 0
fi

echo "Stopping ONLY tmux session yatl-sml-paper (V1)..."
if old_active; then
  tmux has-session -t yatl-sml-paper 2>/dev/null ||
    fail "Old observer appears active but its tmux session is missing."
  tmux send-keys -t yatl-sml-paper:0.0 C-c
  for i in $(seq 1 20); do
    if ! old_active; then break; fi
    sleep 1
  done
  if old_active; then
    fail "Old Python observer still running: do not start overlapping V2. Inspect tmux."
  fi
fi
echo "V1 observer stopped; archiving its *final* snapshots now."
mkdir -p "$ARCHIVES" "$NEW/data/smart_money"
chmod 700 "$ARCHIVES" "$NEW/data/smart_money"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
archive="$ARCHIVES/smart-money-v1-$stamp.tar.gz"
tar -czf "$archive" -C "$OLD" data/smart_money
sha256sum "$archive" > "$archive.sha256"
cp -n "$OLD/data/smart_money/screened.json" "$NEW/data/smart_money/screened.json"
chmod 600 "$NEW/data/smart_money/screened.json"
[[ -s "$NEW/data/smart_money/screened.json" ]] || fail "V2 screened cohort was not copied."
[[ ! -f "$NEW/data/smart_money/state.json" ]] || fail "Unexpected V2 existing state."

# Remove old tmux shell only AFTER archiving the completed V1 snapshots.
if tmux has-session -t yatl-sml-paper 2>/dev/null; then
  tmux kill-session -t yatl-sml-paper
fi

echo "V1 ARCHIVED: $archive"
echo "Starting detached V2 terminal. It will prompt for the Helius key only"
echo "after you attach; no key is stored or echoed by this script."
tmux new-session -d -s yatl-sml-v2 \
  'cd /home/ubuntu/yatl-smart-money-v2 && exec bash ops/run-smart-money-v2.sh'
echo "NEXT: tmux attach -t yatl-sml-v2"
echo "Then enter the Helius free API key invisibly. Detach with Ctrl+B then D."
echo "Do not restart V1 or start any additional Helius processes."
