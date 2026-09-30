#!/usr/bin/env bash
set -euo pipefail

# Refreezes the runner input against the accepted runtime code identity.
# No candidate performance is executed.

: "${YATL_EXPECTED_GIT_SHA:?set exact accepted Git SHA}"

WORKTREE=/opt/yatl/mcf-distributed
PY=/opt/yatl/app/.venv/bin/python
RUNTIME_ROOT=/var/lib/yatl/research/mcf-prod-001-runtime-input
EVIDENCE_ROOT=/var/lib/yatl/research/mcf-prod-001-binding
DIST_ROOT=/var/lib/yatl/research/mcf-prod-001-distributed
INDEX_SHA=55c8c476cd5043a652c09f060e2a58b6b1dd9cfd9bffef33e3d8ff7a3a6092c3
INDEX_RELATIVE="runtime-data/index-${INDEX_SHA}.json"
OUT="${DIST_ROOT}/runner-input-refreeze.json"

[[ -d "$WORKTREE" ]] || { echo "missing distributed worktree" >&2; exit 2; }
[[ "$(git -C "$WORKTREE" rev-parse HEAD)" = "$YATL_EXPECTED_GIT_SHA" ]] || {
  echo "distributed worktree Git SHA mismatch" >&2
  exit 2
}
[[ -f "$RUNTIME_ROOT/$INDEX_RELATIVE" ]] || { echo "accepted runtime index missing" >&2; exit 2; }
[[ -d "$EVIDENCE_ROOT" ]] || { echo "accepted evidence root missing" >&2; exit 2; }

install -d -o yatl -g yatl -m 0750 "$DIST_ROOT"

run_yatl() {
  runuser -u yatl -- bash -lc "cd '$WORKTREE' && $*"
}

run_yatl "$PY -m research.mass_candidate_factory.production_runner_input freeze   --runtime-root '$RUNTIME_ROOT'   --evidence-root '$EVIDENCE_ROOT'   --index-relative '$INDEX_RELATIVE'   --expected-index-sha256 '$INDEX_SHA'" | tee "$OUT"

RUNNER_SHA="$("$PY" -c 'import json,sys; print(json.load(open(sys.argv[1]))["runner_input_sha256"])' "$OUT")"
RUNNER_RELATIVE="$("$PY" -c 'import json,sys; print(json.load(open(sys.argv[1]))["artifact"])' "$OUT")"

run_yatl "$PY -m research.mass_candidate_factory.production_runner_input verify   --runtime-root '$RUNTIME_ROOT'   --input-relative '$RUNNER_RELATIVE'   --expected-input-sha256 '$RUNNER_SHA'"   | tee "$DIST_ROOT/runner-input-verify.json"

echo "RUNNER_REFREEZE_STATUS=VERIFIED_NO_PERFORMANCE"
echo "YATL_RUNNER_INPUT_SHA256=$RUNNER_SHA"
echo "YATL_RUNNER_INPUT_RELATIVE=$RUNNER_RELATIVE"
echo "FULL_6852_EXECUTION_STARTED=NO"
