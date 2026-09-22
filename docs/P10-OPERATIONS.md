# P10 Operations — Real Forward Collection on VPS

Status: **OPERATIONAL COLLECTOR ACCEPTED — REAL FORWARD COLLECTION ACTIVE — P11 LOCKED**

This runbook deploys the completed P10 engineering stack for real forward Paper
market-data collection. It does **not** enable Live trading, account access,
credentials, order endpoints, leverage, futures, margin, shorting, withdrawals,
or AI direct execution.

## Frozen chronology

- P10 forward window start: **2026-09-22 00:00:00 UTC**
  (**2026-09-22 03:00 Istanbul**).
- The collector requires a closed candle for every registered interval.
- The first 4h candle closes at **2026-09-22 04:00:00 UTC**
  (**2026-09-22 07:00 Istanbul**).
- Before that point the collector returns stable exit code **40 / NOT_READY**.
- systemd treats exit 40 as successful/non-failing.
- The 51×4h regime warm-up means the first legal Paper decision is not earlier
  than **2026-09-30 12:00 UTC / 15:00 Istanbul**.
- The 90-calendar-day economic gate is not earlier than
  **2026-12-21 00:00 UTC** and does not waive the registered trade-count gates.

## VPS paths

Repository:

`/opt/yatl/app`

Dedicated P10 data directory:

`/var/lib/yatl/p10`

Database:

`/var/lib/yatl/p10/p10-forward.sqlite3`

Canonical current ingestion snapshot:

`/var/lib/yatl/p10/snapshot.json`

No secrets or API keys are needed. The collector uses only the allowlisted
credential-free Binance Spot public REST client.

## One-shot collector command

After deploying the accepted operational collector commit:

```bash
sudo install -d -o yatl -g yatl -m 0700 /var/lib/yatl/p10
cd /opt/yatl/app
sudo -u yatl ./.venv/bin/python -m yatl.validation.collector_cli \
  --database /var/lib/yatl/p10/p10-forward.sqlite3 \
  --snapshot /var/lib/yatl/p10/snapshot.json
```

The repository uses a non-installed local package layout, so manual module
commands must run with `/opt/yatl/app` as the working directory. The systemd
service already enforces the same directory with `WorkingDirectory=/opt/yatl/app`.

Successful collection returns JSON with `code=COLLECTED`,
`quality_pass=true`, `paper_only=true`, `live_master_lock=OFF`,
`trade_permission=false`, `order_endpoint=false` and
`ai_direct_execution=false`.

Stable operational exits:

- `0`: collection succeeded;
- `40`: the sealed window has not yet produced a closed candle for every interval;
- `41`: invalid operator request;
- `42`: source/evidence rejected;
- `43`: storage failure;
- `44`: another collector instance already holds the lock;
- `46`: internal fail-closed error.

## systemd installation

The repository contains:

- `ops/systemd/yatl-p10-forward-collector.service`
- `ops/systemd/yatl-p10-forward-collector.timer`

Install them:

```bash
sudo install -m 0644 /opt/yatl/app/ops/systemd/yatl-p10-forward-collector.service \
  /etc/systemd/system/yatl-p10-forward-collector.service
sudo install -m 0644 /opt/yatl/app/ops/systemd/yatl-p10-forward-collector.timer \
  /etc/systemd/system/yatl-p10-forward-collector.timer
sudo systemctl daemon-reload
sudo systemctl enable --now yatl-p10-forward-collector.timer
```

The timer runs hourly at minute 05 and is persistent. Missing hours do not
invalidate P10: the next run backfills the complete sealed closed-candle range
and the quality gate rejects gaps/conflicts.

Check scheduling:

```bash
systemctl list-timers yatl-p10-forward-collector.timer
```

Check the latest collector run:

```bash
sudo systemctl status yatl-p10-forward-collector.service --no-pager
sudo journalctl -u yatl-p10-forward-collector.service -n 50 --no-pager
```

## Validation status

After a successful collection and after the collector process has exited:

```bash
cd /opt/yatl/app
sudo -u yatl ./.venv/bin/python -m yatl.validation.cli status \
  --database /var/lib/yatl/p10/p10-forward.sqlite3 \
  --snapshot /var/lib/yatl/p10/snapshot.json
```

Before the 51×4h warm-up completes, `NOT_READY` with
`FORWARD_WARMUP_NOT_COMPLETE` is expected. This is not a reason to change the
candidate, thresholds, gates, symbols, or window.

## First real forward runtime evidence

The production collector was accepted through PR #78 at merge checkpoint
`eab1599d633b019a3d10f7af277bb5b5011a0753`. Matching Final-HEAD Actions
run `35645158177` passed both jobs, the **1514/1514** complete suite and the
**12/12** focused operational collector tests. PR #79 then corrected the manual
working-directory examples and merged at
`73815feb71947cf49f6d6ddace50b6ad49a4088b`.

On 2026-09-22 the VPS produced the first admissible real forward collection at
**04:05 UTC / 07:05 Istanbul**, followed by successful hourly collections at
05:05, 06:05 and 07:05 UTC. The latest observed collection contained exactly
six BTCUSDT/ETHUSDT × 15m/1h/4h datasets, `store_count=72`,
`quality_pass=true` and ingestion snapshot SHA-256
`1aaeb5bc9ef4dfdf55dddaa4366940777eaeb2f90c0908d49ff8344d03f9fbf6`.

The read-only validation status over that evidence returned
`NOT_READY/FORWARD_WARMUP_NOT_COMPLETE` with database snapshot SHA-256
`801fd6a84136b68c99d8c08d15e8e0a011b8133a10b5f7f7cdbb833b85c3a35f`.
That is the expected state before the frozen 51×4h warm-up completes. Safety
remained Paper-only, `LIVE_MASTER_LOCK=OFF`, strategy evidence insufficient and
P11 locked.

## Operational invariants

- The SQLite database is P10-owned and window-bound.
- Existing unowned non-empty databases are refused.
- Snapshot publication is canonical and atomic.
- Snapshot rollback is rejected.
- Overlapping collectors are rejected with an advisory file lock.
- Local database/snapshot paths are never printed in collector JSON output.
- Existing corrupted or noncanonical snapshots fail closed.
- Upstream P1 evidence is never modified.
- P11 remains locked throughout collection.
- A later `PASS_CANDIDATE` from real evidence can only allow separate P11
  consideration; it does not authorize Live execution by itself.


## Optional operator monitoring

The read-only Dashboard and outbound-only Telegram operational layer is documented
in [P10-MONITORING.md](P10-MONITORING.md). Monitoring is separate from collection:
it may be disabled without stopping or mutating the real P10 forward collector.
