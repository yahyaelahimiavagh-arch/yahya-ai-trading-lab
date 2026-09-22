# CRL-002 VPS Runbook — Historical Data Acquisition

Status: **IMPLEMENTATION READY / REAL ACQUISITION PENDING**

This runbook executes the research-only CRL-002 downloader on the Linux VPS.
It does not stop, reconfigure, read or write the active P10 collector.

## Preconditions

Repository checkout:

`/opt/yatl/app`

Active P10 remains at:

`/var/lib/yatl/p10/`

Crisis Lab runtime root:

`/opt/yatl/app/data/research/crisis-lab/`

The Crisis Lab process is forbidden from using `/var/lib/yatl/p10/` as an
input or output path.

## 1. Update the repository

```bash
cd /opt/yatl/app
git pull --ff-only origin main
```

Do not change any P10 service, timer, database, candidate, gate or sealed window.

## 2. Record external no-P10-write evidence

The research process itself does not open P10 artifacts. The operator records
hashes outside the process before and after acquisition:

```bash
sudo sha256sum   /var/lib/yatl/p10/p10-forward.sqlite3   /var/lib/yatl/p10/snapshot.json   | sudo tee /tmp/crl-p10-before.sha256 >/dev/null
```

This is verification evidence only. Do not copy either P10 file into the Crisis
Lab runtime tree.

## 3. No-network plan check

Example:

```bash
cd /opt/yatl/app
uv run --locked python -m research.crisis_lab plan --event CRL-E001
```

Expected safety fields include:

- `research_only=true`;
- `market_data_downloaded=false`;
- `market_outcomes_exposed=false`;
- `p10_write_allowed=false`;
- `p11_locked=true`.

## 4. Acquire one event

Start with a Development event:

```bash
cd /opt/yatl/app
uv run --locked python -m research.crisis_lab acquire-event   --event CRL-E001   --runtime-root data/research/crisis-lab
```

Default acquisition:

- downloads official Binance Public Data ZIPs;
- verifies each sibling `.CHECKSUM`;
- stores raw/extracted bytes immutably under the ignored research data tree;
- normalizes only BTCUSDT/ETHUSDT × 15m/1h/4h;
- verifies first/last canonical candle against the credential-free
  `data-api.binance.vision` kline endpoint;
- emits only bounded structural/provenance output;
- never prints return, PnL, direction, drawdown or strategy results;
- leaves final quality admission at `PENDING_CRL003`.

A source disagreement is `QUARANTINED_SOURCE_CONFLICT`; it is never silently
overwritten.

## 5. Blind Holdout handling

Blind Holdout acquisition may run automatically, but do not open, chart or
summarize its OHLCV files before the final holdout evaluation.

The allowed operator view is the sanitized event summary and structural manifest
metadata: row counts, time bounds, gaps, duplicate counts, source digests and
verification status.

Events whose catalog entry has `replay_eligible=false` may be structurally
acquired but remain forbidden from CRL-004 replay.

## 6. Re-check P10 hashes

After the Crisis Lab process exits:

```bash
sudo sha256sum   /var/lib/yatl/p10/p10-forward.sqlite3   /var/lib/yatl/p10/snapshot.json   | sudo tee /tmp/crl-p10-after.sha256 >/dev/null

sudo diff -u /tmp/crl-p10-before.sha256 /tmp/crl-p10-after.sha256
```

A zero diff is required for the CRL acquisition interval used as no-write
evidence. Because the production P10 collector runs hourly, perform this proof
inside a bounded interval where the P10 collector is not expected to execute, or
record the collector's legitimate independent update separately. Never disable
or retune the P10 collector merely to make the proof pass.

## 7. CRL-002 runtime acceptance evidence

CRL-002 remains IN PROGRESS until a real VPS run records:

- one or more successful source downloads with official checksums;
- immutable raw/extracted/canonical SHA-256 provenance;
- REST boundary-verification result;
- six dataset manifests per completed event;
- event-level acquisition manifest;
- external evidence that Crisis Lab did not write P10;
- no credential/account/order/AI capability.

Only after real acquisition evidence is reviewed may CRL-002 be accepted and
CRL-003 become the active gate.

No CRL-002 result is profitability evidence or Live authorization.
