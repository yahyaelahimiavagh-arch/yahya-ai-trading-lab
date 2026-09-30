# RIE-006 — IEI PIT Public-Data Feasibility Triage 001

Work Unit ID: `RIE-006-IEI-PIT-PUBLIC-DATA-FEASIBILITY-TRIAGE-001`  
Status: **TRIAGE COMPLETE / ETH FEE INTENSITY SELECTED FOR DATA-SPEC AUDIT / NO PERFORMANCE READ**  
Date: 2026-09-29  
Execution route: `CHAT_DIRECTOR` under `EXECUTION-MODE-MATRIX-v1.0`.

Starting GitHub state:
- `main`: `ce8e7b747f712779ed5e16144d74bda013226948`
- branch: `research-institutional-edge-intelligence`
- starting branch HEAD: `51a17446de73eaa9db60570a7121e3ae84401d08`
- PR #152: OPEN / DRAFT / UNMERGED

Parent checkpoint:
- `AF-03D-CORPUS-SYNTHESIS-CHECKPOINT-v1.0.md`
- queue item: **AF-03D-FU-04 PIT public-data feasibility triage**

Boundary:
- PAPER / RESEARCH ONLY
- `LIVE_MASTER_LOCK=OFF`
- no Futures execution / leverage / short / Live / order endpoint / AI execution
- no return, PnL, Sharpe, hit-rate, candidate ranking by outcomes, backtest or parameter sweep
- Fresh OOS SEALED / NOT READ
- recent reserve SEALED / NOT READ
- P10 UNTOUCHED / NOT READ / NOT WRITTEN
- P11 LOCKED

## 1. Frozen triage question

Choose **at most one** of the three AF-03D tracks for the next bounded data/method
audit, using only PIT availability, revision risk, reproducibility and source
semantics:

1. `IEI-MECH-021` token dilution / vesting;
2. `IEI-MECH-024` Ethereum demand-side fee intensity;
3. `IEI-MECH-002` cross-sectional same-weekday seasonality.

Reported returns or external performance are not selection inputs. Zero usable
tracks would have been an acceptable result.

## 2. Track A — IEI-MECH-021 token dilution / vesting

Disposition: **NOT SELECTED / BLOCKED_PIT_LABEL_AND_SNAPSHOT_PROVENANCE**

The committed RIE-006 record already requires point-in-time circulating supply,
then-known vesting schedules, token age, PIT Spot eligibility/liquidity and
historically documented holder type where used.

The central problem remains structural:
- circulating supply is not an immutable chain primitive for many tokens;
- project/provider wallet labels can determine what is called circulating;
- historical supply/market-cap series can be revised;
- a modern API historical response does not prove the value or schedule known at
  the historical decision time;
- scheduled unlock and continuous dilution are separate hypotheses and cannot be
  combined to rescue missing data.

A future unlock audit would first need contemporaneous schedule snapshots plus
versioned supply/label evidence. No such corpus is admitted by this triage.

No modern provider backfill is accepted as a substitute.

## 3. Track B — IEI-MECH-002 cross-sectional same-weekday

Disposition: **NOT SELECTED / BLOCKED_ON_ADMITTED_PIT_UNIVERSE**

The committed mechanism requires:
- point-in-time Spot listing/delisting universe;
- historical eligibility/liquidity;
- completed lagged daily observations;
- minimum-history rule;
- no future delisting/survival knowledge.

AF-03D explicitly records the PIT listed/delisted Spot universe as a required gate
and states that AF-01C acquisition being in progress is **not assumed admitted**.

Therefore this track is not the first usable immutable public-data path at this
checkpoint. Selecting it now would make the calendar statistic depend on a
still-unadmitted cross-sectional membership/eligibility corpus.

No current universe may be projected backward.

## 4. Track C — IEI-MECH-024 Ethereum demand-side fee intensity

Disposition: **SELECTED FOR NEXT BOUNDED DATA-SPEC AUDIT / CHAIN-NATIVE INPUTS
MOST REPRODUCIBLE / SUPPLY DERIVATION STILL UNRESOLVED**

This track has the strongest first-party reproducibility path of the three because
its fee primitives arise from Ethereum protocol state rather than retrospective
provider labels or a changing token universe.

Protocol facts used for feasibility only:

- EIP-1559 defines execution base fee per gas and burns the base-fee component;
- Ethereum transaction fee accounting separates protocol base fee from priority
  fee/tip;
- EIP-4844 introduced a distinct blob-gas fee market and blob fee, which is also
  burned;
- the Ethereum Foundation announced Dencun activation on mainnet at epoch 269568,
  2024-03-13 13:55 UTC;
- Ethereum's official supply documentation describes supply as dynamic, affected
  by issuance and burn.

Official protocol sources inspected:
- https://eips.ethereum.org/EIPS/eip-1559
- https://eips.ethereum.org/EIPS/eip-4844
- https://ethereum.org/developers/docs/gas/
- https://ethereum.org/eth/supply
- https://blog.ethereum.org/2024/02/27/dencun-mainnet-announcement

These facts establish **method/data feasibility**, not predictability.

### Why selected before 021 and 002

The next audit can derive fee components from immutable protocol/block data under
a frozen chain rule. It does not require:
- retrospective token-team/treasury labels;
- historical vesting-provider snapshots;
- a cross-sectional listed/delisted asset universe.

This materially lowers PIT label and survivorship risk.

However, `Fees_t / Supply_t` is **not yet admitted** because the denominator must
be derived reproducibly under explicit historical issuance/burn semantics rather
than copied from a modern provider series.

## 5. Mandatory structural-break semantics

Dencun is a real protocol boundary, not a cosmetic date.

For the next audit:
- pre-Dencun execution fee semantics and post-Dencun execution + blob fee
  semantics must be represented separately;
- blob fees MUST NOT be retroactively inserted before activation;
- execution base-fee burn and blob-fee burn must not be counted as two independent
  economic edges;
- priority fees/tips must not be silently conflated with burned base fees;
- a later daily fee definition must freeze whether `Fees_t` means total user-paid
  execution fees, burned execution base fees, blob fees, or a preregistered sum;
- the source transformation cannot change after outcomes.

No claim is made here that pre/post-Dencun observations form one stationary
process.

## 6. Six-clock / version contract for the next audit

Even chain-native data must preserve:
1. `observation_time`;
2. `as_of_time`;
3. `public_availability_time`;
4. `retrieval_time`;
5. `revision_version_time`;
6. `decision_eligibility_time`.

For canonical daily construction:
- UTC day boundary must be frozen;
- only finalized/accepted chain state under a preregistered finality rule may close
  a day;
- node/provider retrieval time is not substituted for block observation time;
- reorg/finality handling must be explicit;
- derived daily files require raw-source identity/hash and transformation hash.

Historical API queryability alone does not prove PIT availability, although
canonical chain history can provide a stronger reproducibility basis than
revision-prone off-chain labels.

## 7. ETH supply denominator blocker

The denominator is the principal remaining data-spec blocker.

A next-stage specification must define from first principles:
- starting supply/checkpoint and its provenance;
- PoW issuance semantics if pre-Merge history is in scope;
- PoS consensus issuance after the Merge;
- EIP-1559 execution burn;
- blob-fee burn after Dencun if total supply is reconstructed through that era;
- withdrawals/rewards/penalties/slashing treatment where they affect supply;
- fork/upgrade boundaries;
- UTC aggregation and rounding;
- validation against an external explorer only as a cross-check, not as hidden
  authoritative backfill.

If an exact reproducible supply derivation cannot be frozen, the normalized
`Fees/Supply` track remains blocked. Raw fee intensity may be retained only as a
separate comparator, not silently substituted as the same hypothesis.

## 8. Deduplication and economic cluster

`IEI-MECH-024` remains one paid-blockspace-demand mechanism.

Do not count:
- fee intensity;
- base-fee burn;
- blob-fee burn;
- ETH burn rate

as four independent edges. Burn is mechanically downstream of fee demand under
protocol rules.

The future method must also compare any normalized fee state against simpler raw
fee/activity controls before claiming incremental information.

## 9. Opportunity-starvation preservation

No filter is authorized here.

Any later candidate using this state must retain:
- opportunities available;
- state-computable opportunities;
- accepted/delayed/skipped opportunities;
- exposure;
- completed trades;
- missed moves/opportunity cost;
- costs saved;
- net economic effect.

A state that rarely permits exposure cannot be called successful merely because
it avoids adverse periods.

## 10. Triage decision

| Track | PIT/revision condition | Reproducibility | Decision |
|---|---|---|---|
| 021 unlock/dilution | historical supply labels and vesting snapshots unresolved | provider/project-label dependent | NOT SELECTED |
| 002 same-weekday cross-section | admitted PIT Spot universe/eligibility unresolved | blocked on dynamic membership corpus | NOT SELECTED |
| 024 ETH fee intensity | chain-native fee primitives reproducible; supply denominator still needs exact derivation | strongest first-party protocol path | **SELECTED FOR DATA-SPEC AUDIT** |

Selection is by data admissibility only, not reported return.

## 11. Next allowed action

Bounded next work unit:

`RIE-006-IEI-ETH-FEE-DATA-SPEC-AUDIT-001`

Expected route: **CHAT_DIRECTOR** while limited to specification/source audit.

It must freeze:
- exact execution fee components;
- blob-fee treatment;
- Dencun boundary;
- UTC day/finality rule;
- exact ETH supply derivation/versioning;
- raw chain/source provenance;
- decision clock;
- fail-closed rules.

No bulk historical chain acquisition is authorized by this triage.

If the next step expands into substantial block-level acquisition/transformation,
the Execution Mode Matrix requires a separate **WORK_REQUIRED** gate before
execution.

No AF-04 candidate preregistration is authorized until data admissibility is
resolved.

## 12. Closeout

- Work Unit ID: `RIE-006-IEI-PIT-PUBLIC-DATA-FEASIBILITY-TRIAGE-001`
- execution mode: `CHAT_DIRECTOR`
- GitHub authoritative starting main:
  `ce8e7b747f712779ed5e16144d74bda013226948`
- starting branch HEAD:
  `51a17446de73eaa9db60570a7121e3ae84401d08`
- branch: `research-institutional-edge-intelligence`
- AF-03D queue item addressed: `AF-03D-FU-04`
- selected track: `IEI-MECH-024 Ethereum demand-side fee intensity`
- rejected/deferred tracks: `IEI-MECH-021`, `IEI-MECH-002`
- blocker resolved: which bounded PIT path to inspect first
- blockers remaining: ETH supply derivation/versioning; exact fee-component
  definition; finality/day-close rule; later historical acquisition integrity
- negative evidence preserved: modern supply/vesting labels are not PIT proof;
  current-universe projection is forbidden; fee/burn are not independent edges
- tests: source/specification audit only; no code tests
- performance evidence: NOT READ
- Fresh OOS: SEALED / NOT READ
- recent reserve: SEALED / NOT READ
- P10: UNTOUCHED / NOT READ / NOT WRITTEN
- P11: LOCKED
- next allowed action: `RIE-006-IEI-ETH-FEE-DATA-SPEC-AUDIT-001`
- merge status: NO

**MERGED=NO**
