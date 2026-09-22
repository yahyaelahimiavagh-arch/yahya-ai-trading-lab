"""Read-only operational monitor for real P10 forward validation evidence.

This module projects the accepted P10 validation summary into a self-contained
local HTML dashboard and canonical P9 notification batches. It has no network,
credential, account, execution, risk-authority or order capability.
"""

import argparse
import hashlib
import html
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from yatl.notifications import (
    build_notification_batch,
    project_p10_validation_status,
)
from yatl.notifications.contracts import SYMBOLS

from .cli import ValidationCliError, validation_summary


MONITOR_ID = "P10_OPERATIONS_MONITOR_V1"
MONITOR_SCHEMA_VERSION = 1
MAX_DASHBOARD_BYTES = 512 * 1024
MAX_NOTIFICATION_BYTES = 256 * 1024

EXIT_OK = 0
EXIT_INVALID = 60
EXIT_SOURCE = 61
EXIT_STORAGE = 62
EXIT_OUTPUT = 63
EXIT_INTERNAL = 64


class P10MonitorError(RuntimeError):
    """Stable monitor failure with no caller paths or source payloads."""

    def __init__(self, code):
        if code not in {
            "INVALID_REQUEST",
            "SOURCE_REJECTED",
            "STORAGE_ERROR",
            "OUTPUT_TOO_LARGE",
            "INTERNAL_ERROR",
        }:
            raise TypeError("P10 monitor error code is invalid")
        self.code = code
        super().__init__(code)


def _json(value):
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def _sha256_text(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _safe_path(value):
    if not isinstance(value, (str, os.PathLike)) or not str(value):
        raise P10MonitorError("INVALID_REQUEST")
    return Path(value)


def _atomic_replace(path, text, maximum):
    if not isinstance(text, str) or type(maximum) is not int or maximum <= 0:
        raise P10MonitorError("INVALID_REQUEST")
    encoded = text.encode("utf-8")
    if not encoded or len(encoded) > maximum:
        raise P10MonitorError("OUTPUT_TOO_LARGE")
    target = _safe_path(path)
    parent = target.parent
    temporary = None
    try:
        if (
            not parent.exists()
            or not parent.is_dir()
            or parent.is_symlink()
            or target.is_symlink()
        ):
            raise P10MonitorError("STORAGE_ERROR")
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{target.name}.",
            suffix=".tmp",
            dir=parent,
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        temporary = None
        if target.read_bytes() != encoded:
            raise P10MonitorError("STORAGE_ERROR")
    except P10MonitorError:
        raise
    except OSError:
        raise P10MonitorError("STORAGE_ERROR") from None
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def _observed_at_ms(summary):
    if summary.get("code") == "NOT_READY":
        value = summary.get("generated_at_ms")
    else:
        value = summary.get("observation_end_ms")
    if type(value) is not int or value < 0:
        raise P10MonitorError("SOURCE_REJECTED")
    return value


def _validate_summary(summary):
    """Reuse the accepted P9 projection as the strict summary admission gate."""

    try:
        messages = tuple(
            project_p10_validation_status(summary, symbol)
            for symbol in SYMBOLS
        )
    except (TypeError, ValueError):
        raise P10MonitorError("SOURCE_REJECTED") from None
    return messages


def build_monitor_record(summary):
    """Build a bounded presentation record from one accepted P10 summary."""

    messages = _validate_summary(summary)
    observed_at_ms = _observed_at_ms(summary)
    summary_json = _json(summary)
    record = {
        "schema_version": MONITOR_SCHEMA_VERSION,
        "monitor_id": MONITOR_ID,
        "summary_sha256": _sha256_text(summary_json),
        "summary_code": summary["code"],
        "observed_at_ms": observed_at_ms,
        "paper_only": True,
        "live_master_lock": "OFF",
        "strategy_evidence": "INSUFFICIENT_EVIDENCE",
        "p11_unlocked": False,
        "notification_sha256": {
            message.symbol: message.message_sha256
            for message in messages
        },
    }
    if summary["code"] == "NOT_READY":
        record.update({
            "state": "WARMUP",
            "reason": summary["reason"],
        })
    else:
        record.update({
            "state": "VALIDATION",
            "sample_status": summary["sample_status"],
            "disposition": summary["disposition"],
            "observed_days": summary["observed_days"],
            "completed_trades": summary["completed_trades"],
            "net_pnl_after_costs_quote": summary["net_pnl_after_costs_quote"],
            "net_return_after_costs": summary["net_return_after_costs"],
            "profit_factor_after_costs": summary["profit_factor_after_costs"],
            "maximum_validation_drawdown_fraction":
                summary["maximum_validation_drawdown_fraction"],
            "criteria": summary["criteria"],
            "symbols": summary["symbols"],
        })
    return record


def _utc_text(milliseconds):
    try:
        value = datetime.fromtimestamp(
            milliseconds / 1000,
            tz=timezone.utc,
        )
    except (OSError, OverflowError, ValueError):
        raise P10MonitorError("SOURCE_REJECTED") from None
    return value.strftime("%Y-%m-%d %H:%M:%S UTC")


def _e(value):
    return html.escape(str(value), quote=True)


def render_dashboard(summary):
    """Render one deterministic, self-contained and network-free P10 dashboard."""

    record = build_monitor_record(summary)
    observed = _utc_text(record["observed_at_ms"])
    state = record["state"]
    if state == "WARMUP":
        primary = (
            '<section class="hero"><div><div class="eyebrow">REAL FORWARD VALIDATION</div>'
            '<h1>P10 warm-up in progress</h1>'
            '<p>The sealed forward dataset is collecting normally. Strategy decisions remain '
            'blocked until the registered 51 × 4h warm-up is complete.</p></div>'
            '<div class="state waiting">NOT READY</div></section>'
            '<section class="grid">'
            f'<article><span>Reason</span><strong>{_e(record["reason"])}</strong></article>'
            f'<article><span>Observed</span><strong>{_e(observed)}</strong></article>'
            f'<article><span>Evidence</span><strong>{_e(record["strategy_evidence"])}</strong></article>'
            '<article><span>P11</span><strong>LOCKED</strong></article>'
            '</section>'
        )
        details = ""
    else:
        disposition = record["disposition"]
        css_class = "fail" if disposition == "FAIL" else "active"
        primary = (
            '<section class="hero"><div><div class="eyebrow">REAL FORWARD VALIDATION</div>'
            f'<h1>P10 {_e(disposition)}</h1>'
            '<p>Descriptive Paper validation only. Results include the frozen cost and risk '
            'semantics; P11 remains locked.</p></div>'
            f'<div class="state {css_class}">{_e(disposition)}</div></section>'
            '<section class="grid">'
            f'<article><span>Observed days</span><strong>{_e(record["observed_days"])}</strong></article>'
            f'<article><span>Completed trades</span><strong>{_e(record["completed_trades"])}</strong></article>'
            f'<article><span>Net return after costs</span><strong>{_e(record["net_return_after_costs"])}</strong></article>'
            f'<article><span>Profit factor</span><strong>{_e(record["profit_factor_after_costs"])}</strong></article>'
            f'<article><span>Maximum drawdown</span><strong>{_e(record["maximum_validation_drawdown_fraction"])}</strong></article>'
            f'<article><span>Sample</span><strong>{_e(record["sample_status"])}</strong></article>'
            '</section>'
        )
        criteria_rows = "".join(
            f"<tr><td>{_e(name)}</td><td>{_e(status)}</td></tr>"
            for name, status in sorted(record["criteria"].items())
        )
        symbol_rows = "".join(
            "<tr>"
            f"<td>{_e(item['symbol'])}</td>"
            f"<td>{_e(item['completed_trades'])}</td>"
            f"<td>{_e(item['net_pnl_after_costs_quote'])}</td>"
            f"<td>{_e(item['net_return_after_costs'])}</td>"
            f"<td>{_e(item['open_positions'])}</td>"
            "</tr>"
            for item in record["symbols"]
        )
        details = (
            '<section class="tables">'
            '<div><h2>Registered gates</h2><table><thead><tr><th>Criterion</th><th>Status</th></tr></thead>'
            f'<tbody>{criteria_rows}</tbody></table></div>'
            '<div><h2>Symbols</h2><table><thead><tr><th>Symbol</th><th>Trades</th>'
            '<th>Net PnL</th><th>Net return</th><th>Open</th></tr></thead>'
            f'<tbody>{symbol_rows}</tbody></table></div></section>'
        )

    document = (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<title>YATL P10 Forward Monitor</title><style>"
        ":root{color-scheme:dark;--bg:#07111f;--panel:#0d1b2d;--line:#24364c;"
        "--text:#edf3fa;--muted:#9fb0c4;--ok:#63d49b;--warn:#f4c76b;--bad:#ff7d7d}"
        "*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);"
        "font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}"
        "main{max-width:1180px;margin:auto;padding:36px 22px 64px}"
        ".top{display:flex;justify-content:space-between;gap:20px;align-items:center;margin-bottom:28px}"
        ".brand{font-weight:800;letter-spacing:.08em}.lock{color:var(--muted);font-size:13px}"
        ".hero{display:flex;justify-content:space-between;gap:30px;align-items:center;"
        "padding:28px;border:1px solid var(--line);background:var(--panel);border-radius:18px}"
        ".eyebrow{font-size:12px;letter-spacing:.15em;color:var(--muted)}h1{margin:6px 0 8px;"
        "font-size:34px}p{margin:0;color:var(--muted);max-width:720px}.state{font-weight:800;"
        "padding:10px 14px;border-radius:999px;white-space:nowrap}.waiting{color:var(--warn);"
        "border:1px solid var(--warn)}.active{color:var(--ok);border:1px solid var(--ok)}"
        ".fail{color:var(--bad);border:1px solid var(--bad)}.grid{display:grid;"
        "grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:14px;margin-top:18px}"
        "article{padding:18px;border:1px solid var(--line);background:var(--panel);border-radius:14px}"
        "article span{display:block;color:var(--muted);font-size:12px;margin-bottom:7px}"
        "article strong{font-size:16px;word-break:break-word}.tables{display:grid;"
        "grid-template-columns:1fr 1fr;gap:18px;margin-top:18px}.tables>div{padding:20px;"
        "border:1px solid var(--line);background:var(--panel);border-radius:14px}h2{font-size:17px;"
        "margin:0 0 12px}table{width:100%;border-collapse:collapse}th,td{text-align:left;"
        "padding:9px 8px;border-bottom:1px solid var(--line);font-size:13px}th{color:var(--muted)}"
        ".foot{margin-top:22px;color:var(--muted);font-size:12px;word-break:break-all}"
        "@media(max-width:760px){.hero{align-items:flex-start;flex-direction:column}.tables{grid-template-columns:1fr}}"
        "</style></head><body><main>"
        '<div class="top"><div class="brand">YATL / P10</div>'
        '<div class="lock">PAPER ONLY · LIVE_MASTER_LOCK=OFF · P11 LOCKED</div></div>'
        f"{primary}{details}"
        '<div class="foot">'
        f'Observed: {_e(observed)} · Summary SHA-256: {_e(record["summary_sha256"])}'
        "</div></main></body></html>"
    )
    if len(document.encode("utf-8")) > MAX_DASHBOARD_BYTES:
        raise P10MonitorError("OUTPUT_TOO_LARGE")
    lowered = document.casefold()
    if any(marker in lowered for marker in ("http://", "https://", "<script", "websocket", "fetch(")):
        raise P10MonitorError("OUTPUT_TOO_LARGE")
    return document


def notification_batch_for_summary(summary, symbol):
    """Create exactly one canonical symbol-scoped P10 notification batch."""

    _validate_summary(summary)
    try:
        message = project_p10_validation_status(summary, symbol)
        return build_notification_batch(message)
    except (TypeError, ValueError):
        raise P10MonitorError("SOURCE_REJECTED") from None


def notification_json(summary, symbol):
    batch = notification_batch_for_summary(summary, symbol)
    encoded = _json(batch.as_record()) + "\n"
    if len(encoded.encode("utf-8")) > MAX_NOTIFICATION_BYTES:
        raise P10MonitorError("OUTPUT_TOO_LARGE")
    return batch, encoded


def build_dashboard(database_path, snapshot_path, output_path):
    try:
        summary = validation_summary(database_path, snapshot_path)
    except ValidationCliError:
        raise P10MonitorError("SOURCE_REJECTED") from None
    document = render_dashboard(summary)
    _atomic_replace(output_path, document, MAX_DASHBOARD_BYTES)
    record = build_monitor_record(summary)
    return {
        "schema_version": MONITOR_SCHEMA_VERSION,
        "monitor_id": MONITOR_ID,
        "ok": True,
        "code": "DASHBOARD_UPDATED",
        "summary_code": summary["code"],
        "summary_sha256": record["summary_sha256"],
        "bytes": len(document.encode("utf-8")),
        "paper_only": True,
        "live_master_lock": "OFF",
        "p11_unlocked": False,
    }


def build_notification(database_path, snapshot_path, symbol, output_path):
    try:
        summary = validation_summary(database_path, snapshot_path)
    except ValidationCliError:
        raise P10MonitorError("SOURCE_REJECTED") from None
    batch, encoded = notification_json(summary, symbol)
    _atomic_replace(output_path, encoded, MAX_NOTIFICATION_BYTES)
    return {
        "schema_version": MONITOR_SCHEMA_VERSION,
        "monitor_id": MONITOR_ID,
        "ok": True,
        "code": "NOTIFICATION_UPDATED",
        "summary_code": summary["code"],
        "symbol": symbol,
        "batch_sha256": batch.batch_sha256,
        "notification_sha256": batch.notifications[0].message_sha256,
        "paper_only": True,
        "live_master_lock": "OFF",
        "p11_unlocked": False,
    }


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise P10MonitorError("INVALID_REQUEST")


def _parser():
    parser = SafeArgumentParser(description="Read-only P10 operational monitor")
    subparsers = parser.add_subparsers(dest="command", required=True)

    dashboard = subparsers.add_parser("dashboard")
    dashboard.add_argument("--database", required=True)
    dashboard.add_argument("--snapshot", required=True)
    dashboard.add_argument("--output", required=True)

    notification = subparsers.add_parser("notification")
    notification.add_argument("--database", required=True)
    notification.add_argument("--snapshot", required=True)
    notification.add_argument("--symbol", required=True, choices=SYMBOLS)
    notification.add_argument("--output", required=True)
    return parser


def _error_record(code):
    return {
        "schema_version": MONITOR_SCHEMA_VERSION,
        "monitor_id": MONITOR_ID,
        "ok": False,
        "code": code,
    }


def _exit(code):
    return {
        "INVALID_REQUEST": EXIT_INVALID,
        "SOURCE_REJECTED": EXIT_SOURCE,
        "STORAGE_ERROR": EXIT_STORAGE,
        "OUTPUT_TOO_LARGE": EXIT_OUTPUT,
        "INTERNAL_ERROR": EXIT_INTERNAL,
    }.get(code, EXIT_INTERNAL)


def main(argv=None):
    try:
        args = _parser().parse_args(argv)
        if args.command == "dashboard":
            result = build_dashboard(args.database, args.snapshot, args.output)
        else:
            result = build_notification(
                args.database,
                args.snapshot,
                args.symbol,
                args.output,
            )
        output = _json(result)
        if len(output.encode("utf-8")) > 32 * 1024:
            raise P10MonitorError("OUTPUT_TOO_LARGE")
        print(output, end="")
        return EXIT_OK
    except P10MonitorError as exc:
        print(_json(_error_record(exc.code)), end="")
        return _exit(exc.code)
    except Exception:
        print(_json(_error_record("INTERNAL_ERROR")), end="")
        return EXIT_INTERNAL


if __name__ == "__main__":
    raise SystemExit(main())
