# MCF-PROD-001 runtime data and runner-input freeze — v1.0

Work unit: `MCF-PROD-001-RUNTIME-DATA-MATERIALIZATION-AND-RUNNER-INPUT-FREEZE`.
Baseline: `b71ae8fee40ab0b80c3dbc0349fbe7fb3b8be55a`, merged PR #168,
final PR HEAD `bfc752e4574c2faca99eca004a5a7376e5df6487`, green Actions run
`36687440489` / #398. GitHub was read directly before implementation.

## Accepted identities

| Input | SHA-256 |
|---|---|
| Monthly membership | `c75aa5c4347dff5daeed1ca2625fb86e2df3f4e105fde55aed0248df4ce868b7` |
| Source preflight | `f0a177cc98d3946ead55dc69016d65178539ecd0c778c9c4ae0a193e3ba61cfc` |
| Classification map | `e19cb8539c29e6a95c453b6a680b56b5b88bddad65df8a67ca32a14ceab41012` |
| AF-01C plan | `5bc6fc2baa8e32d096c88e755763a79e222f1c7a43d0649e5074fd969b4d296a` |
| AF-01C population reconciliation | `1ecf1cbeec6473414d559fa433c0bda2e86de02cd89ab3a6f455dcf2af45dc17` |
| Executable candidate freeze | `84d4f8ec6234ffb5afccf44ea044661d72af8b4de525b111118ae087907d1dc6` |
| Candidate ledger | `084150778f2270c2ce96dac631f2e0fb1e6f84fed3325a197a80aa3d59db8e73` |
| Neighbor graph | `4eb36ca827b5b458147e6ba2a74308353dfa047cd368d72e106f568b1f4fc4bb` |

The membership contains 34 schedules and a union of 175 symbols: 22 months of
50 members, 11 empty months, one month of 15 members. No carry-forward,
interpolation or later selection repair exists. Unresolved lower-ranked symbols
do not trigger another classification wave.

## Deterministic data contract

`production_runtime_data.materialize` first verifies the accepted membership
against its exact source preflight. It verifies the AF-01C inventory/plan and
reproduces the adapter reconciliation from the ordered ledger hashes. The
9,306 metadata records must retain 6,443 successes and 2,863 failures/gaps.
Only selected-union successful CSVs are read. Failure records remain in each
symbol's provenance; partial failure CSVs are never silently admitted.

Successful monthly data must match its ledger content hash, row count, source
gap count and monthly boundaries. Duplicate times, invalid OHLC/activity,
off-grid candles, pre-population data and future data fail closed.

Population: `[2020-01-01T00:00:00Z, 2023-01-01T00:00:00Z)`.
Scoring: `[2020-03-01T00:00:00Z, 2023-01-01T00:00:00Z)`.
Earlier registered observations are feature warmup only. Entry and forced
membership exit accounting remain the accepted MCF-03 semantics.

For each symbol, `15m`, `1h`, `4h` outputs have content-addressed canonical CSVs
and gap JSONs. Derivation uses accepted `opportunity_data.views.derive` with a
fixed Decimal context. A higher-timeframe bucket requires every 15m component;
otherwise no candle is produced. Completely absent buckets and leading/trailing
absence are represented over the whole registered evidence interval. The
incomplete-bucket dropped count separately counts buckets with some but not all
components. Gaps are missing expected buckets, not just contiguous gap ranges.

Every index row records dataset identity, symbol, timeframe, row count, first
and last open time, content/gap SHA-256, immutable source records and their
aggregate hash, source 15m hash, evidence boundaries, validity and dropped
bucket count. Less than two complete runtime bars blocks the stage. Reruns
produce the same bytes and hashes; write-once collisions fail closed. The
index is published last, after all 525 data/gap pairs exist. One symbol is
materialized at a time; no 6,852-candidate loop is present.

## Runner-input contract

`production_runner_input.freeze_input` verifies the entire index, reads every
bound data/gap pair, regenerates each higher-timeframe output and compares the
exact bytes and dropped-bucket counts. It then reproduces the accepted executable
identity checkpoint and freezes:

- candidate freeze, ledger, graph and complete executable-object hash;
- exact membership and all 34 snapshots, source preflight, classification,
  AF-01C plan/reconciliation and universe policy;
- every runtime data/gap identity and full coverage report in the embedded index;
- exact cost policy and universe-binding digest;
- warmup/scoring/end boundaries, three allowed timeframes, safety locks;
- SHA-256 of the runtime/feature/accounting/derivation implementation files.

State: `RUNNER_INPUT_FROZEN_BEFORE_PERFORMANCE`.
The independent `runner_input_sha256` hashes the canonical document without its
own hash field. It is printed and must be pinned externally by the Director.
The manifest is content addressed; no mutable “latest” pointer is consumed.
`performance_authorized=false` is part of the freeze.

`FrozenRunnerInput` has no lookup or external data fallback. It checks the pinned
input and current implementation identity, accepted candidate freeze,
membership, cost and index. Its loader rejects an outside symbol/timeframe
before any data read, verifies data and gap hashes and recomputes coverage before
building feature bars. `ProductionRuntime.from_frozen_input` wires exactly these
inputs and loads one requested timeframe lazily. Raw production bar dictionaries
are rejected. The explicit synthetic-test mode admits only one synthetic
candidate with `SYNTHETIC-` bars, never the production freeze.

Production `run()` remains closed by default and needs the separate explicit
Director authorization argument after acceptance. The prepare/freeze/verify
commands cannot execute it. They only instantiate runtime wiring. There is no
batch performance CLI in this work unit. The later batch execution needs its own
capacity planning and Director approval; preparing data does not authorize it.

## VPS preparation — no performance

Use an isolated worktree at the exact final PR SHA reported to the Director.
Do not switch or modify `/opt/yatl/app`'s active checkout, services or P10 state.
Replace `REVIEWED_FINAL_HEAD` with that reported SHA before running:

```bash
set -euo pipefail
YATL_REVIEWED_HEAD='REVIEWED_FINAL_HEAD'
YATL_RUNTIME_WT="$HOME/yatl-runtime-input-${YATL_REVIEWED_HEAD:0:12}"
git -C /opt/yatl/app fetch origin mcf-prod-001-runtime-data-and-runner-input-freeze
git -C /opt/yatl/app cat-file -e "$YATL_REVIEWED_HEAD^{commit}"
git -C /opt/yatl/app worktree add --detach "$YATL_RUNTIME_WT" "$YATL_REVIEWED_HEAD"
cd "$YATL_RUNTIME_WT"
test "$(git rev-parse HEAD)" = "$YATL_REVIEWED_HEAD"
/opt/yatl/app/.venv/bin/python -m research.mass_candidate_factory.production_input_vps \
  --pc-root /var/lib/yatl/research/opportunity-data-pc \
  --search-root /var/lib/yatl/research \
  --output-root "$HOME/yatl-mcf-prod-001-runtime-input" \
  > "$HOME/yatl-runtime-input-preparation.json"
cat "$HOME/yatl-runtime-input-preparation.json"
```

The guarded discovery prunes sealed/P10/performance/results and symlink
directories before traversing them. It finds exactly one pair of accepted
membership/preflight artifacts; ambiguity blocks instead of guessing. An
explicit `--evidence-root /exact/accepted/root` can resolve duplicate copies.
The AF-01C inventory reference is read from the immutable bootstrap, verified
again by the accepted inventory/plan functions. No acquisition/network API is
called. The output root is separate from the accepted AF-01C source.

If a worktree at the chosen path already exists, inspect it; do not remove it
with `--force`. Use a new worktree path if needed. Any command returning nonzero
blocks the stage. A JSON `*_BLOCKED` is evidence, not permission to bypass it.
The preparation output includes the real index hash, real runner-input hash,
dataset count and safety flags. Until that output is received, no real
materialization, reconciliation or runner freeze is claimed.

An independent later re-verification consumes exactly the returned identities:

```bash
/opt/yatl/app/.venv/bin/python -m research.mass_candidate_factory.production_runner_input verify \
  --runtime-root "$HOME/yatl-mcf-prod-001-runtime-input" \
  --input-relative 'runner-input/input-RETURNED_SHA256.json' \
  --expected-input-sha256 'RETURNED_SHA256'
```

This prints `RUNNER_INPUT_VERIFIED_NO_PERFORMANCE` after rechecking all derived
data and runtime wiring. It does not call candidate accounting.

## Safety and acceptance

PAPER/RESEARCH ONLY; LIVE_MASTER_LOCK=OFF; no futures, leverage, short, Live,
order endpoint or AI direct execution; P11 locked; P10 read/write=false;
Fresh OOS/recent reserve sealed and unread; performance read=false. No result
is deleted, repaired or used to alter membership. RIE-006 / PR #152 are untouched.

Synthetic tests cover membership identity/tampering, admission boundaries,
outside symbol/timeframe, gaps and incomplete buckets, idempotency/collisions,
data/gap substitution, empty and 15-member months, manifest-only runtime,
sealed roots, symlinks, safety and lack of performance side effects. Actual VPS
outputs and Director acceptance remain separate checkpoints. Draft PR only;
no merge, rebase, force-push or history rewrite is authorized.
