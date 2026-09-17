"""Deterministic offline runtime evidence for P5-006 startup reconciliation."""

from pathlib import Path
from tempfile import TemporaryDirectory

from yatl.backtest import BacktestSpec

from .journal import ExecutionIntentJournal
from .portfolio import LocalPaperPortfolioStore
from .reconcile import ReconciliationCode, reconcile_startup
from .state import LocalPaperOrderStore


START_MS = 1_699_999_200_000
END_MS = START_MS + 3_600_000


def run_runtime_check():
    """Exercise clean startup plus a fail-closed missing-schema startup."""
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
        clean_path = root / "clean.sqlite3"
        with ExecutionIntentJournal(clean_path):
            pass
        with LocalPaperOrderStore(clean_path):
            pass
        with LocalPaperPortfolioStore(clean_path, spec):
            pass

        first = reconcile_startup(clean_path, spec)
        replay = reconcile_startup(clean_path, spec)
        if (
            first != replay
            or not first.ready
            or first.code is not ReconciliationCode.MATCH
            or first.intent_count != 0
            or first.order_count != 0
            or first.fill_count != 0
        ):
            raise RuntimeError("P5-006 clean startup reconciliation diverged")

        incomplete_path = root / "incomplete.sqlite3"
        with ExecutionIntentJournal(incomplete_path):
            pass
        with LocalPaperOrderStore(incomplete_path):
            pass
        failed = reconcile_startup(incomplete_path, spec)
        if failed.ready or failed.code is not ReconciliationCode.MISSING_SCHEMA:
            raise RuntimeError("P5-006 incomplete startup did not fail closed")

    return first, failed


def main():
    ready, failed = run_runtime_check()
    print(
        "OK: P5 startup reconciliation; "
        f"clean={ready.code.value} replay_equal=true "
        f"empty_counts={ready.intent_count}/{ready.order_count}/{ready.fill_count} "
        f"missing_schema={failed.code.value} "
        f"reconciliation_sha256={ready.reconciliation_sha256}"
    )
    print(
        "PAPER ONLY | LOCAL_PAPER | LIVE_MASTER_LOCK=OFF | "
        "Read-only reconciliation | No repair | No credentials | "
        "No external transport | No exchange order"
    )


if __name__ == "__main__":
    main()
