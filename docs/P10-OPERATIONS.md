# P10 Operations — Real Forward Collection on VPS

Status: **OPERATIONAL COLLECTOR CANDIDATE — P11 LOCKED**

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
