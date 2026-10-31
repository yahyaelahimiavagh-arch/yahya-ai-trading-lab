#!/usr/bin/env bash
# Switch only the READ-ONLY Hostinger publisher to the v2 report.
# Does not modify V1/V2 observer state, place trades or access Helius.
set -Eeuo pipefail
umask 077

V2="/home/ubuntu/yatl-smart-money-v2"
MONITOR="/home/ubuntu/yatl-smart-money-monitor"
CONFIG="$HOME/.config/yatl-hostinger.env"
REPORT="$V2/data/smart_money/report.json"
[[ "$(id -un)" == "ubuntu" ]] || { echo "Run as ubuntu only" >&2; exit 2; }
[[ -f "$CONFIG" && -f "$REPORT" ]] || {
  echo "V2 report/config not ready. Keep publishing V1 for now." >&2; exit 2;
}
[[ -d "$MONITOR/.git" ]] || { echo "Monitor checkout missing" >&2; exit 2; }
python3 - <<'PY'
import json, time
from pathlib import Path
p = Path('/home/ubuntu/yatl-smart-money-v2/data/smart_money/report.json')
r = json.loads(p.read_text(encoding='utf-8'))
assert r.get('kind') == 'YATL_SMART_MONEY_PAPER_ONLY'
assert r.get('selection_mode') in ('qualified','exploratory_unvetted')
assert time.time() - int(r.get('as_of') or 0) < 120, 'V2 report is stale'
assert int(r.get('as_of') or 0) >= int(r.get('start_at') or 0)
print('V2 paper report is recent and internally consistent; switching only web publisher.')
PY

git -C "$MONITOR" pull --ff-only
# Only the SFTP publishing session is briefly restarted.
if tmux has-session -t yatl-sml-hostinger 2>/dev/null; then
  tmux kill-session -t yatl-sml-hostinger
fi

backup="$CONFIG.bak-v1"
if [[ ! -f "$backup" ]]; then
  cp -p "$CONFIG" "$backup"
fi
tmp="$(mktemp "$CONFIG.XXXXXX")"
chmod 600 "$tmp"
grep -v '^YATL_REPORT_DIR=' "$CONFIG" > "$tmp" || true
printf '%s\n' 'YATL_REPORT_DIR="/home/ubuntu/yatl-smart-money-v2/data/smart_money"' >> "$tmp"
mv -f "$tmp" "$CONFIG"
chmod 600 "$CONFIG"

cd "$MONITOR"
bash ops/publish-sml-hostinger.sh --init
tmux new-session -d -s yatl-sml-hostinger \
  'cd /home/ubuntu/yatl-smart-money-monitor && exec bash ops/publish-sml-hostinger.sh --loop'
echo "HOSTINGER NOW SHOWS V2: https://elahimiavagh.com/yatllive/"
echo "This script did not modify or restart the v2 observer."
