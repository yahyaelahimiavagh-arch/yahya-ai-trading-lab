"""Deterministic offline runtime evidence for the P5 guarded operator CLI."""

import hashlib
import json
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

from yatl.backtest import BacktestSpec
from yatl.execution import (
    ExecutionIntentJournal,
    LocalPaperOrderStore,
    LocalPaperPortfolioStore,
)
from yatl.execution.runner import (
    OperatorCode,
    operator_reconcile,
    operator_recover,
    operator_status,
)


HOUR = 3_600_000
START = 1_700_002_800_000


def _canonical(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _digest(payload):
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def main():
    spec = BacktestSpec(
        "BTCUSDT",
        START,
        START + 2 * HOUR,
        initial_cash="10000",
        fee_bps="10",
        slippage_bps="5",
    )
    with TemporaryDirectory() as temporary:
        root = Path(temporary)
        database = root / "execution.sqlite3"
        snapshot = root / "execution.snapshot.json"
        with ExecutionIntentJournal(database):
            pass
        with LocalPaperOrderStore(database):
            pass
        with LocalPaperPortfolioStore(database, spec):
            pass

        initial = operator_status(database, snapshot, spec)
        reconciliation = operator_reconcile(database, spec)
        created = operator_recover(
            database, snapshot, spec, create_snapshot=True
        )
        stable = operator_status(database, snapshot, spec)

        pending = Path(f"{snapshot}.pending")
        shutil.copyfile(snapshot, pending)
        ambiguous = operator_status(database, snapshot, spec)
        if ambiguous.confirmation_sha256 is None:
            raise RuntimeError("Missing explicit pending confirmation")
        confirmed = operator_recover(
            database,
            snapshot,
            spec,
            confirmation=ambiguous.confirmation_sha256,
        )
        final = operator_status(database, snapshot, spec)

        if (
            not initial.ready
            or initial.source_code != "JOURNAL_REBUILD_READY"
            or not reconciliation.ready
            or reconciliation.source_code != "MATCH"
            or created.code is not OperatorCode.SNAPSHOT_CREATED
            or stable.source_code != "MATCH"
            or ambiguous.ready
            or ambiguous.source_code != "AMBIGUOUS_COMMIT"
            or confirmed.code is not OperatorCode.PENDING_CONFIRMED
            or not confirmed.ready
            or final.source_code != "MATCH"
            or final != operator_status(database, snapshot, spec)
        ):
            raise RuntimeError("P5 guarded operator runtime gate failed")

        material = {
            "initial": initial.as_record(),
            "reconciliation": reconciliation.as_record(),
            "created": created.as_record(),
            "stable": stable.as_record(),
            "ambiguous": ambiguous.as_record(),
            "confirmed": confirmed.as_record(),
            "final": final.as_record(),
        }
        operator_sha256 = _digest(material)

    print(
        "OK: P5 guarded operator CLI; "
        "initial=JOURNAL_REBUILD_READY reconcile=MATCH "
        "snapshot=SNAPSHOT_CREATED ambiguous=AMBIGUOUS_COMMIT "
        "confirmed=MATCH replay_equal=true "
        f"operator_sha256={operator_sha256}"
    )
    print(
        "PAPER ONLY | LOCAL_PAPER | LIVE_MASTER_LOCK=OFF | "
        "Bounded local operator | No interactive repair | No credentials | "
        "No external transport | No exchange order"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
