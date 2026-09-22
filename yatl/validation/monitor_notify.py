"""Outbound-only P10 operational Telegram notifier.

This wrapper reuses the accepted P9 guarded notifier runner. It creates temporary
canonical notification inputs from the read-only P10 validation summary and lets
P9 own credentials, Telegram transport, retry, deduplication and delivery state.
"""

import argparse
import json
import os
import tempfile
from pathlib import Path

from yatl.notifications import SYMBOLS
from yatl.notifications.runner import NotifierRunnerError, notifier_run

from .cli import ValidationCliError, validation_summary
from .monitor import notification_json


MONITOR_NOTIFY_ID = "P10_OPERATIONS_TELEGRAM_V1"
MONITOR_NOTIFY_SCHEMA_VERSION = 1
EXIT_OK = 0
EXIT_INVALID = 70
EXIT_SOURCE = 71
EXIT_DELIVERY = 72
EXIT_STORAGE = 73
EXIT_INTERNAL = 74


class P10MonitorNotifyError(RuntimeError):
    def __init__(self, code):
        if code not in {
            "INVALID_REQUEST",
            "SOURCE_REJECTED",
            "DELIVERY_REJECTED",
            "STORAGE_ERROR",
            "INTERNAL_ERROR",
        }:
            raise TypeError("P10 monitor notifier code is invalid")
        self.code = code
        super().__init__(code)


def _json(value):
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def _state_root(value):
    if not isinstance(value, (str, os.PathLike)) or not str(value):
        raise P10MonitorNotifyError("INVALID_REQUEST")
    root = Path(value)
    try:
        if not root.exists() or not root.is_dir() or root.is_symlink():
            raise P10MonitorNotifyError("STORAGE_ERROR")
    except P10MonitorNotifyError:
        raise
    except OSError:
        raise P10MonitorNotifyError("STORAGE_ERROR") from None
    return root


def send_monitor_notifications(database_path, snapshot_path, state_dir):
    """Send one P10 status notification per accepted symbol using P9 delivery."""

    try:
        summary = validation_summary(database_path, snapshot_path)
    except ValidationCliError:
        raise P10MonitorNotifyError("SOURCE_REJECTED") from None

    root = _state_root(state_dir)
    results = []
    failure = False

    for symbol in SYMBOLS:
        batch, encoded = notification_json(summary, symbol)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="",
                prefix=f".p10-{symbol.lower()}-",
                suffix=".json",
                dir=root,
                delete=False,
            ) as handle:
                temporary = Path(handle.name)
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            state = root / f"telegram-{symbol.lower()}-state.json"
            try:
                delivered = notifier_run(
                    temporary,
                    batch.batch_sha256,
                    state,
                    symbol,
                )
                results.append({
                    "symbol": symbol,
                    "ok": True,
                    "code": delivered["code"],
                    "batch_sha256": batch.batch_sha256,
                    "notification_sha256": delivered["notification_sha256"],
                    "delivery_state_sha256": delivered["delivery_state_sha256"],
                    "duplicate_suppressed": delivered["duplicate_suppressed"],
                })
            except NotifierRunnerError as exc:
                failure = True
                results.append({
                    "symbol": symbol,
                    "ok": False,
                    "code": exc.code.value,
                    "batch_sha256": batch.batch_sha256,
                })
        except OSError:
            raise P10MonitorNotifyError("STORAGE_ERROR") from None
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass

    return {
        "schema_version": MONITOR_NOTIFY_SCHEMA_VERSION,
        "notifier_id": MONITOR_NOTIFY_ID,
        "ok": not failure,
        "code": "DELIVERY_COMPLETE" if not failure else "DELIVERY_REJECTED",
        "summary_code": summary["code"],
        "results": results,
        "paper_only": True,
        "live_master_lock": "OFF",
        "strategy_evidence": "INSUFFICIENT_EVIDENCE",
        "p11_unlocked": False,
    }


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise P10MonitorNotifyError("INVALID_REQUEST")


def _parser():
    parser = SafeArgumentParser(description="P10 outbound-only Telegram monitor")
    parser.add_argument("--database", required=True)
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--state-dir", required=True)
    return parser


def _error(code):
    return {
        "schema_version": MONITOR_NOTIFY_SCHEMA_VERSION,
        "notifier_id": MONITOR_NOTIFY_ID,
        "ok": False,
        "code": code,
    }


def main(argv=None):
    try:
        args = _parser().parse_args(argv)
        record = send_monitor_notifications(
            args.database,
            args.snapshot,
            args.state_dir,
        )
        print(_json(record), end="")
        return EXIT_OK if record["ok"] else EXIT_DELIVERY
    except P10MonitorNotifyError as exc:
        print(_json(_error(exc.code)), end="")
        return {
            "INVALID_REQUEST": EXIT_INVALID,
            "SOURCE_REJECTED": EXIT_SOURCE,
            "DELIVERY_REJECTED": EXIT_DELIVERY,
            "STORAGE_ERROR": EXIT_STORAGE,
            "INTERNAL_ERROR": EXIT_INTERNAL,
        }[exc.code]
    except Exception:
        print(_json(_error("INTERNAL_ERROR")), end="")
        return EXIT_INTERNAL


if __name__ == "__main__":
    raise SystemExit(main())
