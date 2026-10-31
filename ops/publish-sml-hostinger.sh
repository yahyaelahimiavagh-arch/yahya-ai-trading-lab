#!/usr/bin/env bash
# Independent read-only uploader. Neither restarts nor imports the YATL observer.
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
YATL_REPORT_DIR="/home/ubuntu/yatl-smart-money/data/smart_money"
YATL_EXPORT_DIR="/home/ubuntu/yatl-smart-money-host-export"

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
      --data-dir "$YATL_REPORT_DIR" --output-dir "$YATL_EXPORT_DIR" --include-html
    sftp -q -b - -oBatchMode=yes -oStrictHostKeyChecking=yes \
      -oUserKnownHostsFile="$HOSTINGER_KNOWN_HOSTS" \
      -i "$HOSTINGER_SFTP_KEY" -P "$HOSTINGER_SFTP_PORT" \
      "$HOSTINGER_SFTP_USER@$HOSTINGER_SFTP_HOST" <<EOF
put "$YATL_EXPORT_DIR/index.html" "$HOSTINGER_SFTP_REMOTE_DIR/index.html.tmp"
rename "$HOSTINGER_SFTP_REMOTE_DIR/index.html.tmp" "$HOSTINGER_SFTP_REMOTE_DIR/index.html"
put "$YATL_EXPORT_DIR/status.json" "$HOSTINGER_SFTP_REMOTE_DIR/status.json.tmp"
rename "$HOSTINGER_SFTP_REMOTE_DIR/status.json.tmp" "$HOSTINGER_SFTP_REMOTE_DIR/status.json"
EOF
  else
    python3 -m research.smart_money_lab.hostinger_export \
      --data-dir "$YATL_REPORT_DIR" --output-dir "$YATL_EXPORT_DIR"
    sftp -q -b - -oBatchMode=yes -oStrictHostKeyChecking=yes \
      -oUserKnownHostsFile="$HOSTINGER_KNOWN_HOSTS" \
      -i "$HOSTINGER_SFTP_KEY" -P "$HOSTINGER_SFTP_PORT" \
      "$HOSTINGER_SFTP_USER@$HOSTINGER_SFTP_HOST" <<EOF
put "$YATL_EXPORT_DIR/status.json" "$HOSTINGER_SFTP_REMOTE_DIR/status.json.tmp"
rename "$HOSTINGER_SFTP_REMOTE_DIR/status.json.tmp" "$HOSTINGER_SFTP_REMOTE_DIR/status.json"
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
