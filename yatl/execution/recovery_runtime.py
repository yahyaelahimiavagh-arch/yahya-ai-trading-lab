"""Deterministic offline runtime evidence for P5-007 snapshot recovery."""

import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

from yatl.backtest import BacktestSpec

from .journal import ExecutionIntentJournal
from .portfolio import LocalPaperPortfolioStore
from .recovery import (
    RecoveryCode,
    confirm_pending_snapshot,
    create_recovery_snapshot,
    recover_startup,
)
from .state import LocalPaperOrderStore


START_MS = 1_699_999_200_000
END_MS = START_MS + 3_600_000


def run_runtime_check():
    spec = BacktestSpec(
        "BTCUSDT",
        START_MS,
        END_MS,
        initial_cash="10000",
        fee_bps="10",
        slippage_bps="5",
    )
    with TemporaryDirectory() as directory:
        root = Path(directory)
        database = root / "execution.sqlite3"
        snapshot_path = root / "execution.snapshot.json"
        with ExecutionIntentJournal(database):
            pass
        with LocalPaperOrderStore(database):
            pass
        with LocalPaperPortfolioStore(database, spec):
            pass

        snapshot = create_recovery_snapshot(database, snapshot_path, spec)
        ready = recover_startup(database, snapshot_path, spec)
        replay = recover_startup(database, snapshot_path, spec)
        if ready != replay or not ready.ready or ready.code is not RecoveryCode.MATCH:
            raise RuntimeError("P5-007 snapshot replay diverged")

        snapshot_path.unlink()
        rebuild = recover_startup(database, snapshot_path, spec)
        if not rebuild.ready or rebuild.code is not RecoveryCode.JOURNAL_REBUILD_READY:
            raise RuntimeError("P5-007 missing snapshot did not rebuild from journal")
        rebuilt = create_recovery_snapshot(database, snapshot_path, spec)
        if rebuilt.snapshot_sha256 != snapshot.snapshot_sha256:
            raise RuntimeError("P5-007 rebuilt snapshot identity changed")

        pending = Path(f"{snapshot_path}.pending")
        shutil.copyfile(snapshot_path, pending)
        ambiguous = recover_startup(database, snapshot_path, spec)
        if (
            ambiguous.ready
            or ambiguous.code is not RecoveryCode.AMBIGUOUS_COMMIT
            or ambiguous.manual_confirmation_sha256 is None
        ):
            raise RuntimeError("P5-007 ambiguous commit did not fail closed")
        confirm_pending_snapshot(
            snapshot_path,
            ambiguous.manual_confirmation_sha256,
        )
        final = recover_startup(database, snapshot_path, spec)
        if not final.ready or final.code is not RecoveryCode.MATCH:
            raise RuntimeError("P5-007 explicit confirmation did not restore readiness")

    return snapshot, ready, rebuild, ambiguous, final


def main():
    snapshot, ready, rebuild, ambiguous, final = run_runtime_check()
    print(
        "OK: P5 snapshot recovery; "
        f"snapshot={ready.code.value} replay_equal=true "
        f"deleted={rebuild.code.value} ambiguous={ambiguous.code.value} "
        f"confirmed={final.code.value} "
        f"snapshot_sha256={snapshot.snapshot_sha256} "
        f"recovery_sha256={final.recovery_sha256}"
    )
    print(
        "PAPER ONLY | LOCAL_PAPER | LIVE_MASTER_LOCK=OFF | "
        "Snapshot is cache only | Explicit confirmation only | No automatic repair | "
        "No credentials | No external transport | No exchange order"
    )


if __name__ == "__main__":
    main()
