#!/usr/bin/env bash
set -euo pipefail

NODE_ID="${1:-}"
PUBLIC_KEY="${2:-}"
WORKTREE=/opt/yatl/mcf-distributed
AUTH_KEYS=/home/yatl-node/.ssh/authorized_keys

case "$NODE_ID" in
  NODE-LAPTOP|NODE-WORKPC) ;;
  *) echo "Node must be NODE-LAPTOP or NODE-WORKPC" >&2; exit 2 ;;
esac
case "$PUBLIC_KEY" in
  ssh-ed25519\ *) ;;
  *) echo "Only an ssh-ed25519 public key is accepted" >&2; exit 2 ;;
esac

id yatl-node >/dev/null 2>&1 || { echo "run VPS prepare first" >&2; exit 2; }
[[ -x "$WORKTREE/ops/ssh/yatl-mcf-node-command" ]] || {
  echo "restricted gateway command missing" >&2
  exit 2
}

TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT
if [[ -f "$AUTH_KEYS" ]]; then
  grep -v "yatl-mcf-node-command $NODE_ID" "$AUTH_KEYS" > "$TMP" || true
fi
printf 'restrict,command="%s %s" %s\n' \
  "$WORKTREE/ops/ssh/yatl-mcf-node-command" "$NODE_ID" "$PUBLIC_KEY" >> "$TMP"

install -o yatl-node -g yatl-node -m 0600 "$TMP" "$AUTH_KEYS"
echo "NODE_ENROLLMENT_STATUS=INSTALLED"
echo "NODE_ID=$NODE_ID"
