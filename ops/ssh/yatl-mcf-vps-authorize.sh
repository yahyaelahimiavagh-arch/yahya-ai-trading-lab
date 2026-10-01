#!/usr/bin/env bash
set -euo pipefail

# Freezes but does NOT execute the 6,852-candidate authorization artifact.

: "${YATL_EXPECTED_GIT_SHA:?set exact accepted Git SHA}"
[[ "$(id -u)" -eq 0 ]] || { echo "Run with sudo" >&2; exit 2; }
[[ "$YATL_EXPECTED_GIT_SHA" =~ ^[0-9a-f]{40}$ ]] || { echo "invalid Git SHA" >&2; exit 2; }
: "${YATL_DIRECTOR_AUTHORIZATION:?explicit Director token required}"

WORKTREE=/opt/yatl/mcf-distributed
PY=/opt/yatl/app/.venv/bin/python
RUNTIME_ROOT=/var/lib/yatl/research/mcf-prod-001-runtime-input
DIST_ROOT=/var/lib/yatl/research/mcf-prod-001-distributed
EXPORT_ROOT=/var/lib/yatl/research/mcf-prod-001-worker-export
PLAN="$DIST_ROOT/plan.json"
REFREEZE="$DIST_ROOT/runner-input-refreeze.json"
BENCHMARK="$DIST_ROOT/capacity-benchmark.json"
AUTH="$DIST_ROOT/authorization.json"

[[ "$(runuser -u yatl -- git -C "$WORKTREE" rev-parse HEAD)" = "$YATL_EXPECTED_GIT_SHA" ]] || {
  echo "distributed worktree Git SHA mismatch" >&2
  exit 2
}
[[ -f "$PLAN" && -f "$REFREEZE" && -f "$BENCHMARK" ]] || {
  echo "plan/refreeze/benchmark evidence incomplete" >&2
  exit 2
}

RUNNER_SHA="$("$PY" -c 'import json,sys; print(json.load(open(sys.argv[1]))["runner_input_sha256"])' "$REFREEZE")"
RUNNER_RELATIVE="$("$PY" -c 'import json,sys; print(json.load(open(sys.argv[1]))["artifact"])' "$REFREEZE")"

runuser -u yatl -- bash -lc "cd '$WORKTREE' && '$PY' -m   research.mass_candidate_factory.production_execution_authorization   --plan '$PLAN'   --runtime-root '$RUNTIME_ROOT'   --runner-input-relative '$RUNNER_RELATIVE'   --runner-input-sha256 '$RUNNER_SHA'   --benchmark '$BENCHMARK'   --expected-git-sha '$YATL_EXPECTED_GIT_SHA'   --output '$AUTH'   --director-authorization '$YATL_DIRECTOR_AUTHORIZATION'"   | tee "$DIST_ROOT/authorization-freeze.json"

AUTH_SEMANTIC="$("$PY" -c 'import json,sys; print(json.load(open(sys.argv[1]))["authorization_sha256"])' "$AUTH")"
AUTH_RAW="$(sha256sum "$AUTH" | awk '{print $1}')"
AUTH_BYTES="$(stat -c %s "$AUTH")"
EXPORT="$EXPORT_ROOT/authorization-$AUTH_SEMANTIC-$AUTH_RAW.json"

if [[ -e "$EXPORT" ]]; then
  cmp -s "$AUTH" "$EXPORT" || { echo "authorization export collision" >&2; exit 2; }
else
  ln "$AUTH" "$EXPORT"
fi
chgrp yatl-mcf "$AUTH" "$EXPORT" "$DIST_ROOT/authorization-freeze.json"
chmod 0640 "$AUTH" "$EXPORT" "$DIST_ROOT/authorization-freeze.json"

echo "FULL_6852_AUTHORIZATION_STATUS=FROZEN_NOT_STARTED"
echo "AUTHORIZATION_SHA256=$AUTH_SEMANTIC"
echo "AUTHORIZATION_RAW_SHA256=$AUTH_RAW"
echo "AUTHORIZATION_BYTES=$AUTH_BYTES"
echo "FULL_6852_EXECUTION_STARTED=NO"
