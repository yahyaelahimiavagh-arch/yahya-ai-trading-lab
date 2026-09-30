# RIE-006 — IEI ETH Fee Data Specification Audit 001

Work Unit ID: `RIE-006-IEI-ETH-FEE-DATA-SPEC-AUDIT-001`  
Status: **METHOD_SPECIFIED / POST-DENCUN PRIMARY WINDOW FROZEN / SUPPLY PROVENANCE BLOCKED / NO PERFORMANCE READ**  
Date: 2026-09-29  
Execution route: `CHAT_DIRECTOR` under `EXECUTION-MODE-MATRIX-v1.0`.

Starting GitHub state verified directly:
- `main`: `ce8e7b747f712779ed5e16144d74bda013226948`
- branch: `research-institutional-edge-intelligence`
- starting branch HEAD: `23e73d2b28f2eeb6d14dfaa6fc1418e5a80c8e20`
- PR #152: OPEN / DRAFT / UNMERGED

Parent: `RIE-006-IEI-PIT-PUBLIC-DATA-FEASIBILITY-TRIAGE-001.md` / AF-03D-FU-04.

Boundary:
- PAPER / RESEARCH ONLY; `LIVE_MASTER_LOCK=OFF`
- no prices, returns, outcomes, backtests, parameter sweeps or candidate promotion
- Fresh OOS SEALED / NOT READ
- recent reserve SEALED / NOT READ
- P10 UNTOUCHED / NOT READ / NOT WRITTEN
- P11 LOCKED

## 1. Economic mechanism and deduplication

`IEI-MECH-024` remains one paid-blockspace-demand mechanism. Execution fees,
base-fee burn, blob fees and blob-fee burn are not counted as independent edges.
Any later normalized state must be compared against simpler raw fee/activity
controls before an incremental-information claim is possible.

## 2. Frozen post-Dencun primary window

Ethereum Foundation's Dencun mainnet announcement fixes activation at epoch
269568, **2024-03-13 13:55 UTC**. Because 2024-03-13 is a mixed pre/post-upgrade
UTC day, the primary homogeneous daily construction begins:

`2024-03-14T00:00:00Z`.

The activation day is excluded from the primary daily series before any outcome
inspection. This does not assert predictive value.

Official source:
https://blog.ethereum.org/2024/02/27/dencun-mainnet-announcement

## 3. Frozen fee numerator semantics

### 3.1 Execution paid

For transaction receipts in a canonical execution block:

`execution_paid_wei = gas_used * effective_gas_price`

Daily execution paid is the integer sum over included transactions whose canonical
block timestamp belongs to the frozen UTC day.

EIP-1559 defines the effective gas price as base fee plus the applicable priority
fee (bounded by the transaction max-fee constraints), and the base-fee component
is burned. Therefore sender-paid execution fee is distinct from validator
priority-fee revenue and from burn alone.

Official source:
https://eips.ethereum.org/EIPS/eip-1559

### 3.2 Blob paid

After Dencun, EIP-4844 defines blob gas as a gas type independent of normal
execution gas. For each blob transaction:

`blob_paid_wei = total_blob_gas * blob_base_fee_per_gas`

Blob fee is burned and is not refunded on transaction failure.

Daily blob paid is the integer sum over included canonical blob transactions for
the UTC day.

Official source:
https://eips.ethereum.org/EIPS/eip-4844

### 3.3 Total paid-blockspace numerator

For the post-Dencun primary track:

`total_fee_paid_wei = execution_paid_wei + blob_paid_wei`

This is the frozen primary numerator. Do not silently substitute:
- base-fee burn only;
- priority fee only;
- blob burn only;
- gas used;
- provider-reported aggregate fees.

Those may be separate controls/checks, not replacements.

## 4. UTC day and time semantics

Every derived daily record must distinguish:
1. `observation_time`: canonical block/receipt timestamp;
2. `as_of_time`: end of the UTC aggregation interval;
3. `public_availability_time`: when the finalized chain state required by the
   frozen finality rule is observable;
4. `retrieval_time`: YATL acquisition time;
5. `revision_version_time`: reorg/finality/source-version change time if any;
6. `decision_eligibility_time`: only after the complete UTC day and its
   preregistered finality condition.

A provider's later historical API query time is not historical decision
availability.

## 5. Finality blocker

This audit does not invent a finality lag. A next bounded protocol audit must
freeze an Ethereum consensus-native finality rule and define:
- which finalized checkpoint closes a UTC day;
- how execution block hashes are tied to finalized consensus state;
- what happens if the final block before 00:00 UTC is not finalized at day-end;
- decision eligibility after finality;
- reorg/finality exception handling.

Until that rule is frozen, `decision_eligibility_time` is unresolved.

## 6. Supply denominator blocker

The normalized hypothesis requires a reproducible ETH supply denominator.

Ethereum's official supply/issuance documentation establishes:
- supply changes through issuance and burn;
- since The Merge, execution-layer issuance is zero;
- consensus-layer issuance continues;
- EIP-1559 base fees burn ETH;
- validator penalties/slashing can reduce validator balances;
- withdrawals move validator funds to execution addresses and are not, by
  themselves, new issuance.

A current provider scalar is not acceptable as historical PIT supply proof.

A next audit must freeze from first principles:
- starting checkpoint and provenance;
- consensus issuance accounting;
- execution base-fee burn;
- blob-fee burn after Dencun;
- penalties/slashing treatment;
- withdrawal treatment;
- fork/upgrade boundaries;
- integer/rounding units;
- checkpoint validation.

Official sources:
https://ethereum.org/roadmap/merge/issuance/
https://ethereum.org/eth/supply

## 7. Raw-chain provenance requirements

Any later acquisition must preserve or deterministically identify:
- chain ID;
- execution block number/hash/parent hash/timestamp;
- transaction hash/index;
- receipt gas used and effective gas price;
- blob transaction identity and blob-gas inputs;
- consensus finalized checkpoint/root used for admission;
- source/client/provider and retrieval time;
- raw artifact or reproducible RPC/object identity where feasible;
- raw/content hashes;
- parser/schema version;
- transformation hash;
- missing-data and retry rules.

No silent forward fill is permitted.

## 8. Fail-closed rules

Reject a daily normalized record if:
1. any canonical block/receipt required for the UTC day is missing;
2. finality under the future frozen rule cannot be established;
3. execution and blob fee components cannot be reproduced deterministically;
4. provider aggregate values replace raw protocol semantics without validation;
5. supply checkpoint/derivation provenance is unresolved;
6. revised/reorged data overwrite the originally admitted version without
   lineage;
7. mixed 2024-03-13 pre/post-Dencun data enter the primary homogeneous series;
8. a retrieval timestamp is substituted for observation/public-availability time.

## 9. Adversarial findings

- Fee and burn observables are mechanically correlated and remain one economic
  cluster.
- Dencun is a structural break; ignoring blob gas before/after it creates a
  changing measurement definition.
- Raw chain history is reproducible in principle but historical queryability does
  not alone establish decision-time eligibility; finality/public-observability
  semantics are still required.
- The numerator can be protocol-defined without a third-party economic label.
- The denominator cannot yet be admitted from a modern supply API or dashboard.
- No opportunity filter is authorized. Any later candidate must preserve
  available/computable/accepted/delayed/skipped opportunities, exposure,
  completed trades, missed moves, cost saved, opportunity cost and net effect.

## 10. Disposition

`IEI-MECH-024 = METHOD_SPECIFIED / POST_DENCUN_PRIMARY_WINDOW_FROZEN / UTC_DAY_RULE_FROZEN / BLOCKED_SUPPLY_CHECKPOINT_PROVENANCE / FINALITY_RULE_NEEDS_PROTOCOL_FREEZE / BULK_ACQUISITION_NOT_STARTED / PERFORMANCE_UNTESTED`

No candidate is registered.

Next bounded work unit:
`RIE-006-IEI-ETH-SUPPLY-FINALITY-PROVENANCE-AUDIT-001`.

Expected route: `CHAT_DIRECTOR` while limited to protocol/source audit. If it
expands into genesis-to-Dencun reconstruction or substantial consensus/execution
block acquisition/transformation, stop before execution at the mandatory
`WORK_REQUIRED` gate.

## 11. Closeout

- Work Unit ID: `RIE-006-IEI-ETH-FEE-DATA-SPEC-AUDIT-001`
- execution mode: `CHAT_DIRECTOR`
- starting main: `ce8e7b747f712779ed5e16144d74bda013226948`
- starting branch HEAD: `23e73d2b28f2eeb6d14dfaa6fc1418e5a80c8e20`
- branch: `research-institutional-edge-intelligence`
- AF-03D queue item: `AF-03D-FU-04 / IEI-MECH-024`
- blocker resolved: exact post-Dencun fee numerator and homogeneous UTC start
- blockers remaining: supply checkpoint/derivation provenance; consensus-native
  finality/day-close rule; later historical acquisition integrity
- negative evidence: provider supply scalar is not PIT proof; burn is not an
  independent mechanism; activation day is structurally mixed
- tests: source/specification audit only; no code tests
- performance evidence: NOT READ
- Fresh OOS: SEALED / NOT READ
- recent reserve: SEALED / NOT READ
- P10: UNTOUCHED / NOT READ / NOT WRITTEN
- P11: LOCKED
- merge status: NO

**MERGED=NO**
