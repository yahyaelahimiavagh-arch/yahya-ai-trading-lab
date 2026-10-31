"""Read-only, loopback-only live monitor for the independent SML paper pilot.

This server NEVER imports the observer, uses provider APIs, or writes project data.
Use an authenticated SSH port forward to view it from another computer.
"""
from __future__ import annotations

import argparse
import json
import time
from decimal import Decimal, InvalidOperation
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

MAX_JSON_BYTES = 8_000_000
RUN_SECONDS = 24 * 3600
DATA_FILES = ("report.json", "helius_budget.json")
SKIP_FIELDS = (
    "unparsed_or_unsupported", "provider_failure", "market_failure",
    "sol_quote_unavailable", "unverifiable_history_gap",
    "helius_budget_exhausted",
)


def _read_json(path: Path) -> dict | None:
    try:
        if path.stat().st_size > MAX_JSON_BYTES:
            return None
        raw = path.read_bytes()
        if len(raw) > MAX_JSON_BYTES:
            return None
        value = json.loads(raw)
        return value if isinstance(value, dict) else None
    except (OSError, ValueError, UnicodeError):
        return None


def _integer(value, *, fallback=0) -> int:
    try:
        v = int(value)
        return max(0, v)
    except (TypeError, ValueError, OverflowError):
        return fallback


def _amount(value) -> str | None:
    try:
        n = Decimal(str(value))
        if not n.is_finite() or n < 0:
            return None
        return f"{n:.4f}"
    except (InvalidOperation, TypeError, ValueError):
        return None


def build_status(report: dict | None, budget: dict | None, *, now: int | None = None) -> dict:
    """Return only whitelisted aggregates. No wallet addresses, raw tx, or secrets."""
    current = int(time.time()) if now is None else int(now)
    calls = (budget or {}).get("calls")
    calls = calls if type(calls) is int and calls >= 0 else None
    initial = {
        "status": "initializing", "mode": "unknown",
        "server_time": current, "updated_at": None, "started_at": None,
        "ends_at": None, "elapsed_seconds": 0, "progress_percent": 0,
        "wallets_followed": 0, "polls": 0, "signals_seen": 0,
        "paper_fills": 0, "open_positions": 0, "feed_complete": None,
        "api_requests_reserved": calls, "api_safety_cap": 5000,
        "portfolios": [], "skips": {}, "recent_fills": [],
        "notice": "No valid paper report yet. Observer is not controlled by this dashboard.",
    }
    if not isinstance(report, dict) or report.get("kind") != "YATL_SMART_MONEY_PAPER_ONLY":
        return initial
    start = _integer(report.get("start_at"))
    as_of = _integer(report.get("as_of"))
    if start <= 0 or as_of <= 0:
        return initial
    end = start + RUN_SECONDS
    elapsed = max(0, min(as_of - start, RUN_SECONDS))
    status = "running"
    if report.get("interrupted") is True:
        status = "interrupted"
    elif as_of >= end:
        status = "completed"
    elif as_of > current + 45 or current - as_of > 120:
        status = "stale"

    source = report.get("portfolios")
    safe_portfolios = []
    recent = []
    total_fills = 0
    open_positions = 0
    if isinstance(source, list):
        for p in source[:9]:
            if not isinstance(p, dict):
                continue
            pid = p.get("id")
            if not isinstance(pid, str) or pid not in {
                f"{kind}_{sec}s" for kind in ("blind", "smart", "consensus")
                for sec in (1, 3, 10)
            }:
                continue
            cash, equity = _amount(p.get("cash_usd")), _amount(p.get("equity_usd"))
            fills = p.get("fills", [])
            if not isinstance(fills, list):
                fills = []
            positions = p.get("open_positions", [])
            if not isinstance(positions, list):
                positions = []
            rejects = p.get("rejected", {})
            if not isinstance(rejects, dict):
                rejects = {}
            net = None
            if equity is not None:
                net = f"{Decimal(equity) - Decimal('1000'):.4f}"
            safe_portfolios.append({
                "id": pid, "cash_usd": cash, "equity_usd": equity,
                "pnl_usd": net, "fills": len(fills), "open": len(positions),
                "halted": p.get("halted") is True,
                "rejected": sum(_integer(v) for v in rejects.values()),
            })
            total_fills += len(fills)
            open_positions += len(positions)
            for fill in fills[-12:]:
                if not isinstance(fill, dict):
                    continue
                side = fill.get("side")
                if side not in ("BUY", "SELL", "RISK_EXIT"):
                    continue
                mint = fill.get("mint")
                token = (mint[:4] + "…" + mint[-4:]
                         if isinstance(mint, str) and len(mint) >= 12 else "—")
                recent.append({
                    "portfolio": pid, "side": side, "token": token,
                    "time": _integer(fill.get("time")),
                    "usd_price": _amount(fill.get("usd_price")),
                })

    skips = report.get("skips", {})
    if not isinstance(skips, dict):
        skips = {}
    # These sets are only counted, never exposed to client.
    blind = report.get("wallets_blind", [])
    smart = report.get("wallets_smart", [])
    wallets = set()
    for group in (blind, smart):
        if isinstance(group, list):
            wallets.update(x for x in group if isinstance(x, str))
    return {
        "status": status,
        "mode": ("exploratory_unvetted"
                 if report.get("selection_mode") == "exploratory_unvetted"
                 else "qualified"),
        "server_time": current, "updated_at": as_of,
        "started_at": start, "ends_at": end,
        "elapsed_seconds": elapsed,
        "progress_percent": round(100 * elapsed / RUN_SECONDS, 2),
        "wallets_followed": len(wallets),
        "polls": _integer(report.get("polls")),
        "signals_seen": _integer(report.get("unique_signals_seen")),
        "paper_fills": total_fills, "open_positions": open_positions,
        "feed_complete": report.get("feed_complete") is True,
        "api_requests_reserved": calls, "api_safety_cap": 5000,
        "portfolios": safe_portfolios,
        "skips": {k: _integer(skips.get(k)) for k in SKIP_FIELDS},
        "recent_fills": sorted(recent, key=lambda f: f["time"], reverse=True)[:15],
        "notice": ("This is an UNVETTED technical paper-only pilot, NOT validated copy-trading alpha."
                   if report.get("selection_mode") == "exploratory_unvetted"
                   else "Qualified-wallet paper evaluation; modeled fills are not executable quotes."),
    }


def make_handler(data_dir: Path):
    page = Path(__file__).with_name("live_monitor.html").read_bytes()

    class Handler(BaseHTTPRequestHandler):
        server_version = "YATL-ReadOnlyMonitor"
        sys_version = ""

        def _send(self, code: int, body: bytes, mime: str):
            self.send_response(code)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy",
                             "default-src 'none'; connect-src 'self'; "
                             "script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
                             "img-src 'none'; base-uri 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            route = urlsplit(self.path).path
            if route == "/":
                self._send(200, page, "text/html; charset=utf-8")
            elif route == "/api/status":
                payload = build_status(
                    _read_json(data_dir / DATA_FILES[0]),
                    _read_json(data_dir / DATA_FILES[1]),
                )
                self._send(200, json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                           "application/json; charset=utf-8")
            elif route == "/favicon.ico":
                self._send(204, b"", "text/plain; charset=utf-8")
            else:
                self._send(404, b"Not found", "text/plain; charset=utf-8")

        def do_POST(self):
            self._send(405, b"Read only", "text/plain; charset=utf-8")

        def log_message(self, format_string, *args):
            pass  # No sensitive path, IP or token logs.

    return Handler


def main(argv=None):
    parser = argparse.ArgumentParser(description="YATL SML private read-only monitor")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data-dir", type=Path, default=Path("data/smart_money"))
    opts = parser.parse_args(argv)
    if not 1024 <= opts.port <= 65535:
        parser.error("choose an unprivileged port")
    with ThreadingHTTPServer(("127.0.0.1", opts.port), make_handler(opts.data_dir)) as server:
        print(f"YATL monitor is read-only on http://127.0.0.1:{opts.port}", flush=True)
        print("Remote access requires SSH port forwarding; not open to public internet.",
              flush=True)
        try:
            server.serve_forever(poll_interval=0.5)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
