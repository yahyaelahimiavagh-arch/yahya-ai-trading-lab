"""Bounded local operator CLI for P5 Paper status and explicit recovery."""

import argparse
import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from yatl.backtest import BacktestConfigError, BacktestSpec

from .reconcile import reconcile_startup
from .recovery import (
    RecoveryCode,
    RecoverySnapshotError,
    confirm_pending_snapshot,
    create_recovery_snapshot,
    recover_startup,
)


OPERATOR_SCHEMA_VERSION = 1
MAX_SPEC_BYTES = 16 * 1024
MAX_OUTPUT_BYTES = 4 * 1024
EXIT_READY = 0
EXIT_NOT_READY = 20
EXIT_INVALID = 21
EXIT_STORAGE = 22

SPEC_KEYS = {
    "symbol",
    "start_time_ms",
    "end_time_ms",
    "initial_cash",
    "fee_bps",
    "slippage_bps",
    "seed",
    "paper_only",
    "live_master_lock",
    "spot_only",
    "allow_short",
    "allow_leverage",
    "execution_price_policy",
}


class OperatorCode(str, Enum):
    READY = "READY"
    NOT_READY = "NOT_READY"
    SNAPSHOT_CREATED = "SNAPSHOT_CREATED"
    SNAPSHOT_PRESENT = "SNAPSHOT_PRESENT"
    PENDING_CONFIRMED = "PENDING_CONFIRMED"
    ACTION_REFUSED = "ACTION_REFUSED"
    INVALID_SPEC = "INVALID_SPEC"
    INVALID_REQUEST = "INVALID_REQUEST"
    STORAGE_ERROR = "STORAGE_ERROR"


class OperatorError(Exception):
    """Stable local operator failure that never exposes paths or raw payloads."""

    def __init__(self, code):
        if not isinstance(code, OperatorCode):
            raise TypeError("Operator error code is invalid")
        self.code = code
        super().__init__(code.value)


def _valid_digest(value):
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _canonical_json(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True, slots=True)
class OperatorReport:
    command: str
    ok: bool
    ready: bool
    code: OperatorCode
    source_code: str | None = None
    spec_sha256: str | None = None
    reconciliation_sha256: str | None = None
    snapshot_sha256: str | None = None
    confirmation_sha256: str | None = None
    intents: int = 0
    orders: int = 0
    fills: int = 0
    tail_intents: int = 0
    tail_order_events: int = 0
    tail_fills: int = 0

    def __post_init__(self):
        if self.command not in {"status", "reconcile", "recover", "invalid"}:
            raise OperatorError(OperatorCode.INVALID_REQUEST)
        if type(self.ok) is not bool or type(self.ready) is not bool:
            raise OperatorError(OperatorCode.INVALID_REQUEST)
        if not isinstance(self.code, OperatorCode):
            raise OperatorError(OperatorCode.INVALID_REQUEST)
        for value in (
            self.spec_sha256,
            self.reconciliation_sha256,
            self.snapshot_sha256,
            self.confirmation_sha256,
        ):
            if value is not None and not _valid_digest(value):
                raise OperatorError(OperatorCode.INVALID_REQUEST)
        for value in (
            self.intents,
            self.orders,
            self.fills,
            self.tail_intents,
            self.tail_order_events,
            self.tail_fills,
        ):
            if type(value) is not int or value < 0:
                raise OperatorError(OperatorCode.INVALID_REQUEST)

    def as_record(self):
        return {
            "schema_version": OPERATOR_SCHEMA_VERSION,
            "command": self.command,
            "ok": self.ok,
            "ready": self.ready,
            "code": self.code.value,
            "source_code": self.source_code,
            "spec_sha256": self.spec_sha256,
            "reconciliation_sha256": self.reconciliation_sha256,
            "snapshot_sha256": self.snapshot_sha256,
            "confirmation_sha256": self.confirmation_sha256,
            "counts": {
                "intents": self.intents,
                "orders": self.orders,
                "fills": self.fills,
            },
            "tail": {
                "intents": self.tail_intents,
                "order_events": self.tail_order_events,
                "fills": self.tail_fills,
            },
        }

    @property
    def sha256(self):
        return hashlib.sha256(_canonical_json(self.as_record()).encode("utf-8")).hexdigest()

    def to_json(self):
        payload = _canonical_json({**self.as_record(), "report_sha256": self.sha256})
        if len(payload.encode("utf-8")) > MAX_OUTPUT_BYTES:
            raise OperatorError(OperatorCode.STORAGE_ERROR)
        return payload

    def to_text(self):
        record = self.as_record()
        fields = (
            ("command", record["command"]),
            ("ok", str(record["ok"]).lower()),
            ("ready", str(record["ready"]).lower()),
            ("code", record["code"]),
            ("source_code", record["source_code"] or "-"),
            ("spec_sha256", record["spec_sha256"] or "-"),
            ("reconciliation_sha256", record["reconciliation_sha256"] or "-"),
            ("snapshot_sha256", record["snapshot_sha256"] or "-"),
            ("confirmation_sha256", record["confirmation_sha256"] or "-"),
            ("intents", record["counts"]["intents"]),
            ("orders", record["counts"]["orders"]),
            ("fills", record["counts"]["fills"]),
            ("tail_intents", record["tail"]["intents"]),
            ("tail_order_events", record["tail"]["order_events"]),
            ("tail_fills", record["tail"]["fills"]),
            ("report_sha256", self.sha256),
        )
        payload = "\n".join(f"{key}={value}" for key, value in fields)
        if len(payload.encode("utf-8")) > MAX_OUTPUT_BYTES:
            raise OperatorError(OperatorCode.STORAGE_ERROR)
        return payload


def load_operator_spec(path):
    if not isinstance(path, (str, Path)) or not str(path):
        raise OperatorError(OperatorCode.INVALID_SPEC)
    try:
        with Path(path).open("rb") as handle:
            raw = handle.read(MAX_SPEC_BYTES + 1)
    except OSError:
        raise OperatorError(OperatorCode.INVALID_SPEC) from None
    if len(raw) > MAX_SPEC_BYTES:
        raise OperatorError(OperatorCode.INVALID_SPEC)
    try:
        payload = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError):
        raise OperatorError(OperatorCode.INVALID_SPEC) from None
    if not isinstance(payload, dict) or set(payload) != SPEC_KEYS:
        raise OperatorError(OperatorCode.INVALID_SPEC)
    try:
        return BacktestSpec(**payload)
    except (BacktestConfigError, TypeError, ValueError):
        raise OperatorError(OperatorCode.INVALID_SPEC) from None


def operator_status(database, snapshot, spec):
    report = recover_startup(database, snapshot, spec)
    return OperatorReport(
        "status",
        True,
        report.ready,
        OperatorCode.READY if report.ready else OperatorCode.NOT_READY,
        report.code.value,
        reconciliation_sha256=report.reconciliation_sha256,
        snapshot_sha256=report.snapshot_sha256,
        confirmation_sha256=report.manual_confirmation_sha256,
        tail_intents=report.tail_intents,
        tail_order_events=report.tail_order_events,
        tail_fills=report.tail_fills,
    )


def operator_reconcile(database, spec):
    report = reconcile_startup(database, spec)
    return OperatorReport(
        "reconcile",
        True,
        report.ready,
        OperatorCode.READY if report.ready else OperatorCode.NOT_READY,
        report.code.value,
        report.spec_sha256,
        report.reconciliation_sha256,
        intents=report.intent_count,
        orders=report.order_count,
        fills=report.fill_count,
    )


def operator_recover(database, snapshot, spec, *, create_snapshot=False, confirmation=None):
    if type(create_snapshot) is not bool:
        raise OperatorError(OperatorCode.INVALID_REQUEST)
    if (create_snapshot and confirmation is not None) or (
        not create_snapshot and confirmation is None
    ):
        raise OperatorError(OperatorCode.INVALID_REQUEST)

    before = recover_startup(database, snapshot, spec)
    if create_snapshot:
        if before.code is RecoveryCode.MATCH:
            return OperatorReport(
                "recover",
                True,
                True,
                OperatorCode.SNAPSHOT_PRESENT,
                before.code.value,
                reconciliation_sha256=before.reconciliation_sha256,
                snapshot_sha256=before.snapshot_sha256,
            )
        if before.code is not RecoveryCode.JOURNAL_REBUILD_READY:
            return OperatorReport(
                "recover",
                False,
                before.ready,
                OperatorCode.ACTION_REFUSED,
                before.code.value,
                reconciliation_sha256=before.reconciliation_sha256,
                snapshot_sha256=before.snapshot_sha256,
                confirmation_sha256=before.manual_confirmation_sha256,
                tail_intents=before.tail_intents,
                tail_order_events=before.tail_order_events,
                tail_fills=before.tail_fills,
            )
        try:
            created = create_recovery_snapshot(database, snapshot, spec)
        except RecoverySnapshotError:
            raise OperatorError(OperatorCode.STORAGE_ERROR) from None
        after = recover_startup(database, snapshot, spec)
        if not after.ready or after.code is not RecoveryCode.MATCH:
            raise OperatorError(OperatorCode.STORAGE_ERROR)
        return OperatorReport(
            "recover",
            True,
            True,
            OperatorCode.SNAPSHOT_CREATED,
            after.code.value,
            reconciliation_sha256=after.reconciliation_sha256,
            snapshot_sha256=created.snapshot_sha256,
        )

    if (
        before.code is not RecoveryCode.AMBIGUOUS_COMMIT
        or before.manual_confirmation_sha256 is None
        or confirmation != before.manual_confirmation_sha256
    ):
        return OperatorReport(
            "recover",
            False,
            before.ready,
            OperatorCode.ACTION_REFUSED,
            before.code.value,
            reconciliation_sha256=before.reconciliation_sha256,
            snapshot_sha256=before.snapshot_sha256,
            confirmation_sha256=before.manual_confirmation_sha256,
        )
    try:
        confirm_pending_snapshot(snapshot, confirmation)
    except RecoverySnapshotError:
        raise OperatorError(OperatorCode.STORAGE_ERROR) from None
    after = recover_startup(database, snapshot, spec)
    return OperatorReport(
        "recover",
        True,
        after.ready,
        OperatorCode.PENDING_CONFIRMED,
        after.code.value,
        reconciliation_sha256=after.reconciliation_sha256,
        snapshot_sha256=after.snapshot_sha256,
        confirmation_sha256=confirmation,
        tail_intents=after.tail_intents,
        tail_order_events=after.tail_order_events,
        tail_fills=after.tail_fills,
    )


def _exit_code(report):
    if report.ok and report.ready:
        return EXIT_READY
    if report.code in {OperatorCode.INVALID_REQUEST, OperatorCode.INVALID_SPEC}:
        return EXIT_INVALID
    if report.code is OperatorCode.STORAGE_ERROR:
        return EXIT_STORAGE
    return EXIT_NOT_READY


class SafeArgumentParser(argparse.ArgumentParser):
    """Argparse without echoing rejected operator-supplied values."""

    def error(self, message):
        raise OperatorError(OperatorCode.INVALID_REQUEST)


def _parser():
    parser = SafeArgumentParser(
        description="Bounded local P5 Paper operator commands; no exchange execution"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("status", "reconcile"):
        command = commands.add_parser(name)
        command.add_argument("--database", required=True)
        command.add_argument("--spec", required=True)
        if name == "status":
            command.add_argument("--snapshot", required=True)
        command.add_argument("--format", choices=("json", "text"), default="json")
    recover = commands.add_parser("recover")
    recover.add_argument("--database", required=True)
    recover.add_argument("--snapshot", required=True)
    recover.add_argument("--spec", required=True)
    action = recover.add_mutually_exclusive_group(required=True)
    action.add_argument("--create-snapshot", action="store_true")
    action.add_argument("--confirmation")
    recover.add_argument("--format", choices=("json", "text"), default="json")
    return parser


def main(argv=None):
    try:
        args = _parser().parse_args(argv)
    except OperatorError as exc:
        report = OperatorReport(
            "invalid",
            False,
            False,
            exc.code,
        )
        print(report.to_json())
        return _exit_code(report)
    try:
        spec = load_operator_spec(args.spec)
        if args.command == "status":
            report = operator_status(args.database, args.snapshot, spec)
        elif args.command == "reconcile":
            report = operator_reconcile(args.database, spec)
        else:
            report = operator_recover(
                args.database,
                args.snapshot,
                spec,
                create_snapshot=args.create_snapshot,
                confirmation=args.confirmation,
            )
    except OperatorError as exc:
        report = OperatorReport(
            args.command,
            False,
            False,
            exc.code,
        )
    output = report.to_json() if args.format == "json" else report.to_text()
    print(output)
    return _exit_code(report)


if __name__ == "__main__":
    raise SystemExit(main())
