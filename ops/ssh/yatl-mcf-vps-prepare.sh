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
    [[ "$YATL_EXPECTED_GIT_SHA" =~ ^[0-9a-f]{40}$ ]] || { echo "invalid Git SHA" >&2; exit 2; }
    ;;
  *) echo "invalid Git SHA" >&2; exit 2 ;;
esac

[[ "$YATL_RUNNER_INPUT_SHA256" =~ ^[0-9a-f]{64}$ ]] || { echo "invalid runner SHA" >&2; exit 2; }
[[ "$YATL_RUNNER_INPUT_RELATIVE" =~ ^runner-input/input-[0-9a-f]{64}\.json$ ]] || {
  echo "invalid runner-input relative path" >&2; exit 2;
}
command -v setfacl >/dev/null || { echo "Missing free OS utility: install acl, then rerun prepare." >&2; exit 2; }
id yatl >/dev/null || { echo "existing yatl service user missing" >&2; exit 2; }
[[ -x "$PY" ]] || { echo "missing YATL Python: $PY" >&2; exit 2; }
[[ -d "$RUNTIME_ROOT" ]] || { echo "missing runtime root: $RUNTIME_ROOT" >&2; exit 2; }

runuser -u yatl -- git -C "$SOURCE_REPO" fetch origin
runuser -u yatl -- git -C "$SOURCE_REPO" cat-file -e "$YATL_EXPECTED_GIT_SHA^{commit}"

if [[ -e "$WORKTREE/.git" || -f "$WORKTREE/.git" ]]; then
  actual="$(runuser -u yatl -- git -C "$WORKTREE" rev-parse HEAD)"
  [[ "$actual" = "$YATL_EXPECTED_GIT_SHA" ]] || {
    echo "existing distributed worktree is pinned to $actual, expected $YATL_EXPECTED_GIT_SHA" >&2
    exit 2
  }
else
  [[ ! -e "$WORKTREE" ]] || { echo "worktree path exists but is not a Git worktree" >&2; exit 2; }
  install -d -o yatl -g yatl -m 0750 "$WORKTREE"
  runuser -u yatl -- git -C "$SOURCE_REPO" worktree add --detach "$WORKTREE" "$YATL_EXPECTED_GIT_SHA"
fi

getent group yatl-mcf >/dev/null || groupadd --system yatl-mcf
id yatl-node >/dev/null 2>&1 || useradd --system --create-home --user-group --shell /bin/sh yatl-node
usermod -a -G yatl-mcf yatl
usermod -a -G yatl-mcf yatl-node
install -d -o yatl -g yatl-mcf -m 2770 "$DIST_ROOT" "$RESULTS_ROOT" "$INCOMING_ROOT"
install -d -o yatl -g yatl-mcf -m 2750 "$EXPORT_ROOT"

# Grant only traversal of private ancestors, and read/execute of the isolated
# code worktree and Python environment. Do not grant access to app .env, P10,
# source runtime datasets or any sibling research evidence.
for parent in /opt /opt/yatl "$SOURCE_REPO" /var /var/lib /var/lib/yatl /var/lib/yatl/research; do
  setfacl -m u:yatl-node:--x "$parent"
done
setfacl -R -m u:yatl-node:r-X "$WORKTREE" "$SOURCE_REPO/.venv"
install -d -o root -g root -m 0755 /usr/local/libexec
install -o root -g root -m 0755 "$WORKTREE/ops/ssh/yatl-mcf-node-command" /usr/local/libexec/yatl-mcf-node-command

run_yatl() {
  runuser -u yatl -g yatl-mcf -- bash -lc "umask 007; cd '$WORKTREE' && $*"
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

install -d -o yatl-node -g yatl-node -m 0700 /home/yatl-node/.ssh

AUTH_TMP="$(mktemp)"
trap 'rm -f "$AUTH_TMP"' EXIT
[[ ! -f /home/yatl-node/.ssh/authorized_keys ]] || cp /home/yatl-node/.ssh/authorized_keys "$AUTH_TMP"

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
  local kept
  kept="$(mktemp)"
  grep -v "yatl-mcf-node-command $node_id" "$AUTH_TMP" > "$kept" || true
  cat "$kept" > "$AUTH_TMP"
  rm -f "$kept"
  printf 'restrict,command="%s %s" %s\n' /usr/local/libexec/yatl-mcf-node-command "$node_id" "$key" >> "$AUTH_TMP"
}

add_node_key NODE-LAPTOP "${YATL_LAPTOP_PUBKEY_FILE:-}"
add_node_key NODE-WORKPC "${YATL_WORKPC_PUBKEY_FILE:-}"

if [[ -s "$AUTH_TMP" ]]; then
  install -o yatl-node -g yatl-node -m 0600 "$AUTH_TMP" /home/yatl-node/.ssh/authorized_keys
  echo "NODE_ENROLLMENT=INSTALLED"
else
  echo "NODE_ENROLLMENT=PENDING_PUBLIC_KEYS"
fi

runuser -u yatl-node -- env SSH_ORIGINAL_COMMAND=status /usr/local/libexec/yatl-mcf-node-command NODE-LAPTOP
echo "SSH_GATEWAY_LOCAL_PREFLIGHT=PASS"

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
