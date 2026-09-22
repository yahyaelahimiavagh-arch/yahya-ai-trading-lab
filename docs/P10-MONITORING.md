# P10 Operations Monitoring — Dashboard + Telegram

Status: **OPERATIONAL CANDIDATE — READ ONLY — P11 LOCKED**

This runbook adds operator visibility over the real P10 forward-validation
evidence already collected by `yatl-p10-forward-collector`.

It does not add trading authority. The monitoring path remains:

- PAPER ONLY;
- `LIVE_MASTER_LOCK=OFF`;
- no account/API-key access;
- no trade permission or order endpoint;
- no Futures, margin, leverage, shorting or withdrawal capability;
- no AI direct execution;
- `p11_unlocked=false`.

The monitor reads the accepted P10 SQLite/snapshot through the existing P10-008
validation summary. Telegram delivery reuses the accepted P9 outbound-only
transport, bounded retry and persistent duplicate suppression.

## Runtime layout

Repository:

`/opt/yatl/app`

P10 source evidence:

- `/var/lib/yatl/p10/p10-forward.sqlite3`
- `/var/lib/yatl/p10/snapshot.json`

Monitor-owned output:

- dashboard: `/var/lib/yatl/p10/monitor/public/index.html`
- Telegram state: `/var/lib/yatl/p10/monitor/state/`

Telegram credentials are never stored in Git. They live only in:

`/etc/yatl/p10-telegram.env`

## 1. Create monitor-owned directories

```bash
sudo install -d -o yatl -g yatl -m 0700 /var/lib/yatl/p10/monitor
sudo install -d -o yatl -g yatl -m 0700 /var/lib/yatl/p10/monitor/public
sudo install -d -o yatl -g yatl -m 0700 /var/lib/yatl/p10/monitor/state
```

## 2. Install dashboard units

```bash
sudo install -m 0644 /opt/yatl/app/ops/systemd/yatl-p10-monitor-dashboard.service \
  /etc/systemd/system/yatl-p10-monitor-dashboard.service
sudo install -m 0644 /opt/yatl/app/ops/systemd/yatl-p10-monitor-dashboard.timer \
  /etc/systemd/system/yatl-p10-monitor-dashboard.timer
sudo install -m 0644 /opt/yatl/app/ops/systemd/yatl-p10-monitor-http.service \
  /etc/systemd/system/yatl-p10-monitor-http.service
sudo systemctl daemon-reload
```

Build the first dashboard manually:

```bash
sudo systemctl start yatl-p10-monitor-dashboard.service
sudo systemctl status yatl-p10-monitor-dashboard.service --no-pager
```

Enable hourly refresh at minute `:07`, two minutes after the P10 collector:

```bash
sudo systemctl enable --now yatl-p10-monitor-dashboard.timer
```

Enable the loopback-only HTTP server:

```bash
sudo systemctl enable --now yatl-p10-monitor-http.service
sudo systemctl status yatl-p10-monitor-http.service --no-pager
```

The HTTP service binds only to `127.0.0.1:8765`; it is not exposed publicly.

From the operator computer, open an SSH tunnel:

```powershell
ssh -L 8765:127.0.0.1:8765 ubuntu@<VPS-IP>
```

Then browse locally to:

`http://127.0.0.1:8765`

Before P10 warm-up completes the dashboard must show the explicit warm-up state,
not a fabricated strategy result. After warm-up, it switches to the accepted P10
summary: observed days, completed trades, Net PnL/return after costs, profit
factor, drawdown, registered gate statuses and per-symbol summaries.

## 3. Configure Telegram credentials

Do this only on the VPS:

```bash
sudo install -d -o root -g yatl -m 0750 /etc/yatl
sudo nano /etc/yatl/p10-telegram.env
```

Enter exactly these two variables with the real values:

```text
YATL_TELEGRAM_BOT_TOKEN=<telegram-bot-token>
YATL_TELEGRAM_CHAT_ID=<telegram-chat-id>
```

Then lock the file:

```bash
sudo chown root:yatl /etc/yatl/p10-telegram.env
sudo chmod 0640 /etc/yatl/p10-telegram.env
```

Never paste the real token into Git, logs, screenshots or chat.

## 4. Install Telegram monitoring units

```bash
sudo install -m 0644 /opt/yatl/app/ops/systemd/yatl-p10-monitor-telegram.service \
  /etc/systemd/system/yatl-p10-monitor-telegram.service
sudo install -m 0644 /opt/yatl/app/ops/systemd/yatl-p10-monitor-telegram.timer \
  /etc/systemd/system/yatl-p10-monitor-telegram.timer
sudo systemctl daemon-reload
```

Test one real outbound delivery:

```bash
sudo systemctl start yatl-p10-monitor-telegram.service
sudo systemctl status yatl-p10-monitor-telegram.service --no-pager
sudo journalctl -u yatl-p10-monitor-telegram.service -n 50 --no-pager
```

A successful first run sends one information-only message for BTCUSDT and one for
ETHUSDT. Re-running against the identical P10 summary is duplicate-suppressed by
the accepted P9 delivery guard.

Enable the daily timer:

```bash
sudo systemctl enable --now yatl-p10-monitor-telegram.timer
systemctl list-timers yatl-p10-monitor-telegram.timer
```

The timer is fixed at **05:10 UTC / 08:10 Istanbul**, after the 05:05 UTC P10
collector run.

## Operational behavior

Dashboard refresh:

- hourly at minute `:07`;
- no network capability in the builder;
- reads P10 evidence only through the accepted validation summary;
- writes only the monitor-owned public HTML file;
- current warm-up `NOT_READY` is a valid dashboard state.

Telegram:

- daily outbound-only status;
- no inbound bot commands, callbacks, polling or webhooks;
- no BUY/SELL/control surface;
- credentials are loaded only by the accepted P9 transport boundary;
- one delivery-state file per symbol keeps duplicate suppression restart-safe;
- transport/provider errors remain redacted.

HTTP:

- loopback only;
- use SSH tunneling for access;
- do not open TCP/8765 in the VPS firewall.

## Checks

```bash
systemctl list-timers yatl-p10-forward-collector.timer
systemctl list-timers yatl-p10-monitor-dashboard.timer
systemctl list-timers yatl-p10-monitor-telegram.timer

sudo systemctl status yatl-p10-monitor-http.service --no-pager
sudo journalctl -u yatl-p10-monitor-dashboard.service -n 30 --no-pager
sudo journalctl -u yatl-p10-monitor-telegram.service -n 30 --no-pager
```

The collector remains the source of real forward market evidence. Monitoring
failure must never modify, reset or replace the P10 collector database/snapshot.

## Disable monitoring without touching collection

```bash
sudo systemctl disable --now yatl-p10-monitor-dashboard.timer
sudo systemctl disable --now yatl-p10-monitor-telegram.timer
sudo systemctl disable --now yatl-p10-monitor-http.service
```

This leaves `yatl-p10-forward-collector.timer` unchanged and running.
