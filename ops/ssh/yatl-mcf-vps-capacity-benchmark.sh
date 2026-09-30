#!/usr/bin/env bash
set -euo pipefail

# Runs only the already-approved blind 24-candidate capacity benchmark.
# It does not expose or persist candidate economics and does not authorize 6,852.

: "${YATL_EXPECTED_GIT_SHA:?set exact accepted Git SHA}"

WORKTREE=/opt/yatl/mcf-distributed
PY=/opt/yatl/app/.venv/bin/python
RUNTIME_ROOT=/var/lib/yatl/research/mcf-prod-001-runtime-input
DIST_ROOT=/var/lib/yatl/research/mcf-prod-001-distributed
REFREEZE_JSON="$DIST_ROOT/runner-input-refreeze.json"
OUT="$DIST_ROOT/capacity-benchmark.json"
ERR="$DIST_ROOT/capacity-benchmark.stderr.log"

[[ -d "$WORKTREE" ]] || { echo "missing distributed worktree" >&2; exit 2; }
[[ "$(git -C "$WORKTREE" rev-parse HEAD)" = "$YATL_EXPECTED_GIT_SHA" ]] || {
  echo "distributed worktree Git SHA mismatch" >&2
  exit 2
}
[[ -f "$REFREEZE_JSON" ]] || { echo "runner refreeze evidence missing" >&2; exit 2; }

RUNNER_SHA="$("$PY" -c 'import json,sys; print(json.load(open(sys.argv[1]))["runner_input_sha256"])' "$REFREEZE_JSON")"
RUNNER_RELATIVE="$("$PY" -c 'import json,sys; print(json.load(open(sys.argv[1]))["artifact"])' "$REFREEZE_JSON")"

runuser -u yatl -- bash -lc "cd '$WORKTREE' &&   '$PY' -m research.mass_candidate_factory.production_capacity_benchmark benchmark   --runtime-root '$RUNTIME_ROOT'   --input-relative '$RUNNER_RELATIVE'   --expected-input-sha256 '$RUNNER_SHA'   --director-authorization MCF-PROD-001-CAPACITY-BENCHMARK-001   > '$OUT' 2> '$ERR'"

"$PY" - "$OUT" <<'PY'
import json, sys
p=sys.argv[1]
doc=json.load(open(p))
assert doc["status"] == "CAPACITY_BENCHMARK_COMPLETE_NO_SELECTION"
assert doc["benchmark_candidate_count"] == 24
assert doc["candidate_performance_exposed"] is False
assert doc["performance_artifacts_written"] is False
assert doc["selection_authorized"] is False
assert doc["full_batch_authorized"] is False
print("CAPACITY_BENCHMARK_CONTRACT=PASS")
print("WALL_SECONDS="+str(doc["wall_seconds"]))
print("PEAK_RSS_KIB="+str(doc["peak_rss_kib"]))
PY

BENCHMARK_SHA="$(sha256sum "$OUT" | awk '{print $1}')"
echo "CAPACITY_BENCHMARK_SHA256=$BENCHMARK_SHA"
echo "CAPACITY_STDERR_LOG=$ERR"
echo "FULL_6852_EXECUTION_STARTED=NO"
