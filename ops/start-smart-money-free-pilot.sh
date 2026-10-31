#!/usr/bin/env bash
# YATL Smart Money Lab / free-tier experimental setup.
# Never submits orders, funds wallets or touches existing P10 services.
set -Eeuo pipefail
umask 077
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
mkdir -p data/smart_money

if ! command -v uv >/dev/null 2>&1; then
  echo "ERROR: uv is missing. Install/configure it for this Python 3.12 repo, then rerun." >&2
  exit 2
fi
if ! command -v flock >/dev/null 2>&1; then
  echo "ERROR: Linux flock required for single-runner protection." >&2
  exit 2
fi
exec 9> data/smart_money/observer.lock
if ! flock -n 9; then
  echo "ERROR: an SML pilot already holds the lock." >&2
  exit 2
fi

if [[ -z "${HELIUS_API_KEY:-}" ]]; then
  if [[ ! -t 0 ]]; then
    echo "ERROR: set HELIUS_API_KEY securely in the terminal environment." >&2
    exit 2
  fi
  read -rsp 'Helius free API key (hidden): ' HELIUS_API_KEY
  echo
  export HELIUS_API_KEY
fi
if [[ "${#HELIUS_API_KEY}" -lt 8 ]]; then
  echo "ERROR: missing/short Helius key." >&2
  exit 2
fi

if [[ -f data/smart_money/state.json ]]; then
  echo "Existing paper state found. This script never resets it." >&2
  echo "For an interrupted SAME 24h run, use observe --resume manually." >&2
  exit 2
fi
echo "[1/4] Confirm local locked Python environment"
uv sync --locked
echo "[2/4] Discover public wallet candidates (not yet vetted)"
uv run --locked python -m research.smart_money_lab discover \
  --output data/smart_money/candidates.json --max-pools 5 --per-pool 30
echo "[3/4] Screen recent wallet histories conservatively"
uv run --locked python -m research.smart_money_lab screen \
  --candidates data/smart_money/candidates.json \
  --output data/smart_money/screened.json \
  --max-wallets 30 --max-pages 20 --days 30

uv run --locked python - <<'PY'
import json
from pathlib import Path
from research.smart_money_lab.engine import rank_wallets
records = json.loads(Path('data/smart_money/screened.json').read_text())
blind, smart = rank_wallets(records)
print('Screening:', len(records), 'wallets checked;', len(smart),
      'eligible for smart copy.')
if len(smart) < 2:
    raise SystemExit(
        'STOP: fewer than two sufficiently qualified wallets. '
        'No paper trades started; inspect screening evidence first.'
    )
print('Selected: up to 4 blind + up to 4 smart; free-tier watchlist cap.')
PY

echo "[4/4] Start 24-hour PAPER ONLY observation; output every ~15 seconds"
echo "Report: $ROOT/data/smart_money/dashboard.html"
uv run --locked python -m research.smart_money_lab observe \
  --screened data/smart_money/screened.json --hours 24 \
  --poll-seconds 180 --state data/smart_money/state.json \
  --report data/smart_money/report.json --html data/smart_money/dashboard.html
