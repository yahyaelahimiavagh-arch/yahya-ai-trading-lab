#!/usr/bin/env bash
# Independent read-only uploader. Neither restarts nor imports the YATL observer.
# Remote 644 is REQUIRED: chmod each temporary file BEFORE rename, avoiding
# intermittent 403 during HTTP fetches while the static JSON is replaced.
# The pre-configured yatllive directory must remain password-protected.
set -Eeuo pipefail
umask 077
# User-owned file has connection metadata only (no private key contents).
config="$HOME/.config/yatl-hostinger.env"
if [[ -f "$config" ]]; then
  source "$config"
fi
mode="${1:-}"
if [[ "$mode" != "--init" && "$mode" != "--once" && "$mode" != "--loop" ]]; then
  echo "Usage: bash ops/publish-sml-hostinger.sh --init|--once|--loop" >&2
  exit 2
fi

: "${HOSTINGER_SFTP_HOST:?Hostinger SSH IP or hostname not configured}"
: "${HOSTINGER_SFTP_USER:?Hostinger SSH username not configured}"
: "${HOSTINGER_SFTP_REMOTE_DIR:?Dedicated protected directory not configured}"
: "${HOSTINGER_SFTP_KEY:?Private key file path not configured}"
HOSTINGER_SFTP_PORT="65002"
HOSTINGER_KNOWN_HOSTS="$HOME/.ssh/known_hosts"
YATL_REPORT_DIR="${YATL_REPORT_DIR:-/home/ubuntu/yatl-smart-money/data/smart_money}"
# Explicit cutover overrides are applied AFTER loading private SFTP config.
# Existing Hostinger credentials and dedicated protected path remain untouched.
if [[ -n "${YATL_PAPER_COPY_REPORT_DIR:-}" ]]; then
  YATL_REPORT_DIR="$YATL_PAPER_COPY_REPORT_DIR"
fi
if [[ -n "${YATL_PAPER_COPY_BUDGET_FILE:-}" ]]; then
  YATL_HELIUS_BUDGET_FILE="$YATL_PAPER_COPY_BUDGET_FILE"
fi
YATL_EXPORT_DIR="/home/ubuntu/yatl-smart-money-host-export"
# Optional explicit read-only budget path for V2; no counter reset.
budget_args=()
if [[ -n "${YATL_HELIUS_BUDGET_FILE:-}" ]]; then
  [[ -f "$YATL_HELIUS_BUDGET_FILE" ]] || { echo "Budget file missing; refusing publish" >&2; exit 2; }
  budget_args=(--budget-file "$YATL_HELIUS_BUDGET_FILE")
fi

# No special characters, paths with .., or non-dedicated destinations.
[[ "$HOSTINGER_SFTP_HOST" =~ ^[a-zA-Z0-9.-]+$ ]] || exit 2
[[ "$HOSTINGER_SFTP_USER" =~ ^[a-zA-Z0-9._-]+$ ]] || exit 2
[[ "$HOSTINGER_SFTP_REMOTE_DIR" =~ ^/?[a-zA-Z0-9._/-]+$ ]] || exit 2
[[ "$HOSTINGER_SFTP_REMOTE_DIR" != *".."* ]] || exit 2
[[ "$HOSTINGER_SFTP_REMOTE_DIR" == */yatllive ]] || {
  echo "Remote folder must be a dedicated password-protected /yatllive folder." >&2
  exit 2
}
[[ -f "$HOSTINGER_SFTP_KEY" && -f "$HOSTINGER_KNOWN_HOSTS" ]] || {
  echo "SSH key/verified known_hosts missing." >&2
  exit 2
}

mkdir -p "$YATL_EXPORT_DIR"
exec 9>"$YATL_EXPORT_DIR/publisher.lock"
flock -n 9 || { echo "A publisher is already running." >&2; exit 2; }
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

publish_once() {
  include_html="$1"
  if [[ "$include_html" == "yes" ]]; then
    python3 -m research.smart_money_lab.hostinger_export \
      --data-dir "$YATL_REPORT_DIR" --output-dir "$YATL_EXPORT_DIR" --include-html "${budget_args[@]}"
    sftp -q -b - -oBatchMode=yes -oStrictHostKeyChecking=yes \
      -oUserKnownHostsFile="$HOSTINGER_KNOWN_HOSTS" \
      -i "$HOSTINGER_SFTP_KEY" -P "$HOSTINGER_SFTP_PORT" \
      "$HOSTINGER_SFTP_USER@$HOSTINGER_SFTP_HOST" <<EOF
put "$YATL_EXPORT_DIR/index.html" "$HOSTINGER_SFTP_REMOTE_DIR/index.html.tmp"
chmod 644 "$HOSTINGER_SFTP_REMOTE_DIR/index.html.tmp"
rename "$HOSTINGER_SFTP_REMOTE_DIR/index.html.tmp" "$HOSTINGER_SFTP_REMOTE_DIR/index.html"
chmod 644 "$HOSTINGER_SFTP_REMOTE_DIR/index.html"
put "$YATL_EXPORT_DIR/status.json" "$HOSTINGER_SFTP_REMOTE_DIR/status.json.tmp"
chmod 644 "$HOSTINGER_SFTP_REMOTE_DIR/status.json.tmp"
rename "$HOSTINGER_SFTP_REMOTE_DIR/status.json.tmp" "$HOSTINGER_SFTP_REMOTE_DIR/status.json"
chmod 644 "$HOSTINGER_SFTP_REMOTE_DIR/status.json"
EOF
  else
    python3 -m research.smart_money_lab.hostinger_export \
      --data-dir "$YATL_REPORT_DIR" --output-dir "$YATL_EXPORT_DIR" "${budget_args[@]}"
    sftp -q -b - -oBatchMode=yes -oStrictHostKeyChecking=yes \
      -oUserKnownHostsFile="$HOSTINGER_KNOWN_HOSTS" \
      -i "$HOSTINGER_SFTP_KEY" -P "$HOSTINGER_SFTP_PORT" \
      "$HOSTINGER_SFTP_USER@$HOSTINGER_SFTP_HOST" <<EOF
put "$YATL_EXPORT_DIR/status.json" "$HOSTINGER_SFTP_REMOTE_DIR/status.json.tmp"
chmod 644 "$HOSTINGER_SFTP_REMOTE_DIR/status.json.tmp"
rename "$HOSTINGER_SFTP_REMOTE_DIR/status.json.tmp" "$HOSTINGER_SFTP_REMOTE_DIR/status.json"
chmod 644 "$HOSTINGER_SFTP_REMOTE_DIR/status.json"
EOF
  fi
  echo "Read-only redacted status published at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
case "$mode" in
  --init) publish_once yes ;;
  --once) publish_once no ;;
  --loop)
    while true; do
      if ! publish_once no; then
        echo "SFTP publish failed; will retry in 30 seconds." >&2
      fi
      sleep 30
    done
    ;;
esac
