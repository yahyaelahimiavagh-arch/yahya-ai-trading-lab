# YATL Smart Money Lab — private live HTML monitor

## Safety boundary

This is a **separate, read-only web process**. It does not import or control the
24h observer, change configuration, place orders, restart the collector, write
state/report files, access Helius, or consume provider credits. It reads
`report.json` and `helius_budget.json` and exposes **redacted aggregates only**.
It intentionally does not expose wallet addresses, full signatures, API tokens,
the full snapshot, or arbitrary filesystem paths.

It listens exclusively on **127.0.0.1** on the VPS. Do **not** reverse proxy
`/api/status` publicly or change its bind address to `0.0.0.0`.
Use authenticated SSH port-forwarding or an identity-gated tunnel (e.g. Cloudflare
Access) when needed.

## Start without touching the live experiment

Run on the VPS **from a separate SSH shell** (not inside the observer's pane).
Use a second, **independent Git clone**, so the currently running observer's
code directory never gets touched by a `git pull`:

```bash
git clone --depth 1 --branch research/smart-money-lab-paper-v1 --single-branch \
  https://github.com/yahyaelahimiavagh-arch/yahya-ai-trading-lab.git \
  ~/yatl-smart-money-monitor
cd ~/yatl-smart-money-monitor
python3 -m unittest discover -s tests -p 'test_smart_money_live_monitor.py' -v
tmux has-session -t yatl-sml-monitor 2>/dev/null || \
  tmux new-session -d -s yatl-sml-monitor \
    'cd /home/ubuntu/yatl-smart-money-monitor && exec python3 -m research.smart_money_lab.live_monitor --port 8765 --data-dir /home/ubuntu/yatl-smart-money/data/smart_money'
curl --fail --silent --show-error http://127.0.0.1:8765/api/status | python3 -m json.tool | head -n 26
```

The last command must show live aggregate JSON. The observer's existing
`yatl-sml-paper` session, P10, and their uptime are untouched.

## Open in a browser securely

On the **computer whose web browser will show the dashboard**, create an SSH
local-port forwarding session. Replace YOUR_VPS_HOST with the same trusted IP
or hostname you normally SSH to:

```bash
ssh -N -L 127.0.0.1:8765:127.0.0.1:8765 ubuntu@YOUR_VPS_HOST
```

Keep the tunnel open and browse to **http://127.0.0.1:8765** on that same
computer. The HTML refreshes read-only status every 10 seconds, without any new
Helius requests. On a phone, use a mobile SSH client that supports local port
forwarding, or a *properly authenticated* private tunnel. A public quick tunnel
without authentication is not an appropriate default.

## Troubleshooting

```bash
tmux ls
pgrep -af 'research.smart_money_lab'
curl -fsS http://127.0.0.1:8765/api/status | python3 -m json.tool
```

If the monitor is not running, the observer may still be healthy: they are
independent. An initial `initializing` response indicates no readable
report yet. A `stale` response means the file timestamp has not advanced
for over two minutes; it does **not** prove the observer failed. Diagnostic
numbers such as unique signals can include earlier historical transactions,
and modeled delays are after detection, not end-to-end execution latency.
