# MCF-PROD-001 — Production Binding Preflight v1.0

Status: **PRE-PERFORMANCE / DATA-BINDING AUDIT ONLY**

Purpose: inspect the accepted AF-01C P-C Development corpus using the frozen
MCF-PROD-001 universe policy before any candidate PnL is emitted.

This checkpoint answers:

1. Which historical symbols have at least 60 days of admitted history?
2. Which satisfy >=99.5% trailing-30d 15m continuity at each UTC month start?
3. Which of those have independently verified historical product
   classification?
4. Is monthly lagged-liquidity top-50 ranking safe to freeze without silently
   excluding an unresolved symbol?

## Accepted inputs

Repository main before this work unit:

`f3803ebe0bd9ec43f71940d463098fde58aa4d1d`

AF-01C P-C:

- plan SHA:
  `5bc6fc2baa8e32d096c88e755763a79e222f1c7a43d0649e5074fd969b4d296a`
- population reconciliation SHA:
  `1ecf1cbeec6473414d559fa433c0bda2e86de02cd89ab3a6f455dcf2af45dc17`
- population state:
  `POPULATION_COMPLETE_WITH_SOURCE_GAPS`
- 9,306 final identities;
- 6,443 successful archive identities;
- source gaps/anomalies remain negative evidence.

## Bias rule

A symbol that satisfies the frozen history/continuity test but lacks a
historical product classification is **not silently dropped**.

Instead the whole binding preflight returns:

`CLASSIFICATION_INCOMPLETE`

This prevents an unresolved high-liquidity symbol from being excluded before
the monthly top-50 is ranked.

Current `exchangeInfo` is not accepted as historical product evidence.

Valid classification evidence must be content-addressed, reviewed, and use:

- schema: `MCF_HISTORICAL_PRODUCT_CLASSIFICATION/1.0.0`
- source type: `INDEPENDENT_HISTORICAL_PRODUCT_RECORD`
- classification:
  - `ORDINARY_SPOT_CONFIRMED`, or
  - `NONORDINARY_CONFIRMED`

## First VPS run — audit only

This first pass intentionally uses no classification map. It identifies only
the unresolved symbols that are actually capable of entering the frozen
monthly ranking.

```bash
PC_ROOT=/var/lib/yatl/research/opportunity-data-pc
OUT_ROOT=/var/lib/yatl/research/mcf-prod-001-binding
PLAN_REF=plans/plan-5bc6fc2baa8e32d096c88e755763a79e222f1c7a43d0649e5074fd969b4d296a.json
RECON_REF=population/reconciliation-1ecf1cbeec6473414d559fa433c0bda2e86de02cd89ab3a6f455dcf2af45dc17.json

sudo install -d -o yatl -g yatl -m 0750 "$OUT_ROOT"

# Resolve the frozen P-A inventory copy by its accepted raw-file SHA.
INVENTORY_REF="$(
  cd "$PC_ROOT" &&
  find . -type f -name '*.json' -print0 |
  xargs -0 sha256sum |
  awk '$1=="3c27c203e188095cc6a0f1ab7bafbd9bd534ed786bccf8cfe3c240644ccedeb6"{sub(/^\.\//,"",$2);print $2;exit}'
)"

test -n "$INVENTORY_REF" || { echo "FROZEN_INVENTORY_NOT_FOUND"; exit 2; }

cd /opt/yatl/app
git fetch origin
git checkout main
git pull --ff-only origin main

sudo -u yatl /opt/yatl/app/.venv/bin/python -m   research.mass_candidate_factory.production_binding_preflight   --pc-root "$PC_ROOT"   --plan "$PLAN_REF"   --inventory "$INVENTORY_REF"   --population-reconciliation "$RECON_REF"   --output-root "$OUT_ROOT"
```

Audit-only exit states:

- exit `0`: classification already complete and binding is ready;
- exit `40`: expected audit result when one or more data-eligible symbols
  remain unclassified;
- exit `2`: integrity/contract failure.

The artifact is written under:

`/var/lib/yatl/research/mcf-prod-001-binding/binding-preflight/`

## Classification map

After independent historical product evidence exists, freeze one canonical map:

```json
{
  "schema": "MCF_HISTORICAL_PRODUCT_CLASSIFICATION_MAP/1.0.0",
  "generation_id": "MCF-PROD-001",
  "state": "FROZEN_BEFORE_PERFORMANCE",
  "entries": {
    "BTCUSDT": "evidence/BTCUSDT-<sha256>.json"
  }
}
```

Each referenced evidence file is independently content-addressed.

Rerun the preflight with:

```bash
--classification-root /var/lib/yatl/research/mcf-prod-001-classification \
--classification-map classification-map-<sha256>.json
```

Only when every symbol that passes history/continuity has a resolved product
classification may monthly top-50 rankings be emitted as binding-ready.

## Memory behavior

The scanner is intentionally symbol-at-a-time:

- it never loads the full 5.9GB P-C corpus into a single Python index;
- monthly files are verified through their immutable ledger/content SHA;
- one symbol is assembled, audited and reduced to monthly statistics;
- only compact monthly ranking evidence remains in memory.

This avoids converting the entire AF-01C corpus into millions of simultaneous
Python row objects.

## Safety

This preflight reads only:

- registered Development 15m bars;
- archive/ledger provenance;
- row continuity;
- trailing quote volume;
- historical product classification.

It does **not** read:

- candidate returns;
- PnL;
- Sharpe;
- drawdown;
- Fresh OOS;
- recent reserve;
- P10.

Hard state remains:

- PAPER / RESEARCH ONLY
- LIVE_MASTER_LOCK=OFF
- NO FUTURES
- NO LEVERAGE
- NO SHORT
- NO LIVE EXECUTION
- NO ORDER ENDPOINT
- NO AI DIRECT EXECUTION
- P10 untouched
- P11 locked

## Next gate

After `READY_FOR_PRODUCTION_BINDING`:

1. freeze the exact monthly membership snapshots;
2. derive/materialize only the selected-union 15m/1h/4h runtime bars;
3. freeze the Development runner input manifest;
4. only then permit the first MCF-PROD-001 candidate outcome.
