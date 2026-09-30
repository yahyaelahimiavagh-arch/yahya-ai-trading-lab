#!/usr/bin/env bash
set -euo pipefail

# NO PERFORMANCE EXECUTION occurs in this script.
# It prepares a detached distributed worktree, freezes the distributed plan,
# verifies the already-refrozen runner input, builds a portable worker archive,
# initializes the local coordinator, and optionally enrolls restricted SSH keys.

: "${YATL_EXPECTED_GIT_SHA:?set exact accepted 40-char Git SHA}"
: "${YATL_RUNNER_INPUT_SHA256:?set exact refrozen runner-input SHA-256}"
: "${YATL_RUNNER_INPUT_RELATIVE:?set runner-input relative path}"
: "${YATL_SSH_HOST_LABEL:?set VPS hostname or IP used by workers}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root (sudo) because SSH node enrollment needs system-user access." >&2
  exit 2
fi

SOURCE_REPO=/opt/yatl/app
WORKTREE=/opt/yatl/mcf-distributed
PY=/opt/yatl/app/.venv/bin/python
RUNTIME_ROOT=/var/lib/yatl/research/mcf-prod-001-runtime-input
DIST_ROOT=/var/lib/yatl/research/mcf-prod-001-distributed
RESULTS_ROOT=/var/lib/yatl/research/mcf-prod-001-results
INCOMING_ROOT=/var/lib/yatl/research/mcf-prod-001-incoming
EXPORT_ROOT=/var/lib/yatl/research/mcf-prod-001-worker-export
PLAN="$DIST_ROOT/plan.json"
DB="$DIST_ROOT/coordinator.sqlite3"
MANIFEST="$DIST_ROOT/worker-bundle-manifest.json"

case "$YATL_EXPECTED_GIT_SHA" in
  [0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]*)
    [[ "${#YATL_EXPECTED_GIT_SHA}" -eq 40 ]] || { echo "invalid Git SHA length" >&2; exit 2; }
    ;;
  *) echo "invalid Git SHA" >&2; exit 2 ;;
esac

[[ "${#YATL_RUNNER_INPUT_SHA256}" -eq 64 ]] || { echo "invalid runner SHA length" >&2; exit 2; }
[[ -x "$PY" ]] || { echo "missing YATL Python: $PY" >&2; exit 2; }
[[ -d "$RUNTIME_ROOT" ]] || { echo "missing runtime root: $RUNTIME_ROOT" >&2; exit 2; }

git -C "$SOURCE_REPO" fetch origin
git -C "$SOURCE_REPO" cat-file -e "$YATL_EXPECTED_GIT_SHA^{commit}"

if [[ -e "$WORKTREE/.git" || -f "$WORKTREE/.git" ]]; then
  actual="$(git -C "$WORKTREE" rev-parse HEAD)"
  [[ "$actual" = "$YATL_EXPECTED_GIT_SHA" ]] || {
    echo "existing distributed worktree is pinned to $actual, expected $YATL_EXPECTED_GIT_SHA" >&2
    exit 2
  }
else
  [[ ! -e "$WORKTREE" ]] || { echo "worktree path exists but is not a Git worktree" >&2; exit 2; }
  git -C "$SOURCE_REPO" worktree add --detach "$WORKTREE" "$YATL_EXPECTED_GIT_SHA"
fi

install -d -o yatl -g yatl -m 0750   "$DIST_ROOT" "$RESULTS_ROOT" "$INCOMING_ROOT" "$EXPORT_ROOT"

run_yatl() {
  runuser -u yatl -- bash -lc "cd '$WORKTREE' && $*"
}

if [[ ! -f "$PLAN" ]]; then
  run_yatl "$PY -m research.mass_candidate_factory.production_distributed freeze-plan --output '$PLAN'"
fi

run_yatl "$PY -m research.mass_candidate_factory.production_distributed coordinator-init --db '$DB' --plan '$PLAN'"
chgrp yatl-mcf "$DB" "$PLAN"
chmod 0660 "$DB"
chmod 0640 "$PLAN"

run_yatl "$PY -m research.mass_candidate_factory.production_runner_input verify   --runtime-root '$RUNTIME_ROOT'   --input-relative '$YATL_RUNNER_INPUT_RELATIVE'   --expected-input-sha256 '$YATL_RUNNER_INPUT_SHA256'"

if [[ ! -f "$MANIFEST" ]]; then
  run_yatl "$PY -m research.mass_candidate_factory.production_worker_bundle freeze     --runtime-root '$RUNTIME_ROOT'     --runner-input-relative '$YATL_RUNNER_INPUT_RELATIVE'     --expected-runner-input-sha256 '$YATL_RUNNER_INPUT_SHA256'     --plan '$PLAN'     --git-sha '$YATL_EXPECTED_GIT_SHA'     --output '$MANIFEST'"
fi

chgrp yatl-mcf "$MANIFEST"
chmod 0640 "$MANIFEST"

run_yatl "$PY -m research.mass_candidate_factory.production_worker_bundle verify   --runtime-root '$RUNTIME_ROOT'   --plan '$PLAN'   --manifest '$MANIFEST'"

run_yatl "$PY -m research.mass_candidate_factory.production_worker_bundle archive   --runtime-root '$RUNTIME_ROOT'   --plan '$PLAN'   --manifest '$MANIFEST'   --output-root '$EXPORT_ROOT'"   | tee "$DIST_ROOT/worker-archive.json"

chgrp -R yatl-mcf "$EXPORT_ROOT"
chmod 0640 "$DIST_ROOT/worker-archive.json"
chgrp yatl-mcf "$DIST_ROOT/worker-archive.json"
find "$EXPORT_ROOT" -type d -exec chmod 2770 {} +
find "$EXPORT_ROOT" -type f -exec chmod 0640 {} +

install -o root -g root -m 0644 \
  "$WORKTREE/ops/systemd/yatl-mcf-auto-worker.service" \
  /etc/systemd/system/yatl-mcf-auto-worker.service
systemctl daemon-reload

chmod 0755 "$WORKTREE/ops/ssh/yatl-mcf-node-command"

install -d -o yatl-node -g yatl-node -m 0700 /home/yatl-node/.ssh

AUTH_TMP="$(mktemp)"
trap 'rm -f "$AUTH_TMP"' EXIT
: > "$AUTH_TMP"

add_node_key() {
  local node_id="$1"
  local pub_file="$2"
  [[ -n "$pub_file" && -f "$pub_file" ]] || return 0
  local key
  key="$(tr -d '\r\n' < "$pub_file")"
  case "$key" in
    ssh-ed25519\ *) ;;
    *) echo "Only ssh-ed25519 node keys are accepted: $pub_file" >&2; exit 2 ;;
  esac
  printf 'restrict,command="%s %s" %s\n'     "$WORKTREE/ops/ssh/yatl-mcf-node-command" "$node_id" "$key" >> "$AUTH_TMP"
}

add_node_key NODE-LAPTOP "${YATL_LAPTOP_PUBKEY_FILE:-}"
add_node_key NODE-WORKPC "${YATL_WORKPC_PUBKEY_FILE:-}"

if [[ -s "$AUTH_TMP" ]]; then
  install -o yatl-node -g yatl-node -m 0600 "$AUTH_TMP" /home/yatl-node/.ssh/authorized_keys
  echo "NODE_ENROLLMENT=INSTALLED"
else
  echo "NODE_ENROLLMENT=PENDING_PUBLIC_KEYS"
fi

echo
echo "=== VPS SSH HOST KEY FINGERPRINT ==="
ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub

echo
echo "=== PINNED known_hosts LINE FOR WORKERS ==="
awk -v host="$YATL_SSH_HOST_LABEL" '{print host" "$1" "$2}' /etc/ssh/ssh_host_ed25519_key.pub

echo
echo "=== DISTRIBUTED STATUS ==="
run_yatl "$PY -m research.mass_candidate_factory.production_distributed coordinator-status --db '$DB' --plan '$PLAN'"

echo
echo "=== WORKER ARCHIVE METADATA ==="
cat "$DIST_ROOT/worker-archive.json"

echo
echo "PREPARATION_STATUS=READY_NO_PERFORMANCE"
echo "FULL_6852_EXECUTION_STARTED=NO"
