"""Deterministic adversarial matrix for local-only P5 execution boundaries."""

import hashlib
import json
import shutil
import sqlite3
from dataclasses import dataclass, replace
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from yatl.backtest import BacktestSpec, DecisionEvent, MarketSnapshot
from yatl.data import Candle, DATA_SOURCE, INTERVAL_MILLISECONDS, SYMBOLS
from yatl.risk import (
    KillSwitchEvent,
    KillSwitchEventType,
    ManagedPortfolioState,
    RiskRequest,
    apply_kill_switch_event,
    assess_circuit_breakers,
    assess_entry_limits,
    assess_protective_entry,
    authorize_paper_request,
    size_entry,
)
from yatl.strategy import (
    DecisionReason,
    EvidenceLabel,
    LongSetup,
    StrategyAction,
    StrategyContext,
    StrategyDecision,
    TREND_PULLBACK_IDENTITY,
)

from .contracts import (
    EXECUTION_POLICY_ID,
    RecoveryReadiness,
    RecoveryReason,
    RecoveryStatus,
    assess_local_paper_authorization,
)
from .fills import LocalPaperFillCostAdapter, LocalPaperFillError
from .journal import ExecutionIntentJournal, ExecutionJournalError, IntentConflict
from .portfolio import LocalPaperPortfolioStore
from .reconcile import ReconciliationCode, reconcile_startup
from .recovery import RecoveryCode, create_recovery_snapshot, recover_startup
from .state import (
    LocalOrderEventType,
    LocalOrderTransitionError,
    LocalPaperOrderStore,
    apply_local_order_event,
    build_local_order_event,
)


SCENARIOS = (
    "DUPLICATE_INTENT",
    "CRASH_ROLLBACK",
    "STALE_AUTHORIZATION",
    "OUT_OF_ORDER_EVENT",
    "JOURNAL_CORRUPTION",
    "SNAPSHOT_CORRUPTION",
    "MISSING_FILL_CANDLE",
    "COST_POLICY_MISMATCH",
    "UNCERTAIN_COMMIT",
)
SCHEMA_VERSION = 1
ARTIFACT_KIND = "YATL_P5_ADVERSARIAL_EXECUTION_SCENARIO"
MATRIX_KIND = "YATL_P5_ADVERSARIAL_EXECUTION_MATRIX"
MAX_ARTIFACT_BYTES = 2 * 1024 * 1024
MAX_EVIDENCE_FILES = 32
HOUR = 3_600_000
START = 1_699_999_200_000


class ExecutionScenarioError(Exception):
    """One deterministic local P5 adversarial scenario failed its invariant."""


def _json(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ) + "\n"


def _sha256(value):
    payload = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(payload).hexdigest()


def _snapshot(symbol, decision_time):
    def completed(interval):
        duration = INTERVAL_MILLISECONDS[interval]
        opened = (decision_time // duration) * duration - duration
        return (
            Candle(
                DATA_SOURCE,
                symbol,
                interval,
                opened,
                opened + duration - 1,
                "95",
                "106",
                "90",
                "100",
                "100",
                "10000",
                20,
                True,
            ),
        )

    return MarketSnapshot(
        symbol,
        decision_time,
        completed("1h"),
        completed("15m"),
        completed("4h"),
    )


def _managed(symbol, decision_time, *, quantity="0", equity="10000",
             cash="10000", session_pnl="0", losses=0, digest="1"):
    exposure = Decimal(quantity) * Decimal("100")
    return ManagedPortfolioState(
        symbol,
        (decision_time - START) // HOUR,
        decision_time,
        START,
        "10000",
        equity,
        cash,
        quantity,
        "100",
        "10000",
        session_pnl,
        losses,
        0 if Decimal(quantity) == 0 else 1,
        format(exposure, "f"),
        None if decision_time == START else "0" * 64,
        digest * 64,
    )


@dataclass(frozen=True, slots=True)
class _Fixture:
    symbol: str
    spec: BacktestSpec
    entry_decision: object
    exit_decision: object
    entry_event: DecisionEvent
    exit_event: DecisionEvent
    entry_bar: Candle
    exit_bar: Candle


def _fixture(symbol):
    if symbol not in SYMBOLS:
        raise ExecutionScenarioError("Scenario symbol is not approved")

    entry_view = _snapshot(symbol, START)
    entry_event = DecisionEvent(0, START, START, entry_view)
    entry_strategy = StrategyDecision(
        StrategyContext(TREND_PULLBACK_IDENTITY, entry_view),
        StrategyAction.ENTER_LONG,
        DecisionReason.TREND_PULLBACK_ENTRY,
        LongSetup("100", "95", "115"),
    )
    entry_state = _managed(symbol, START)
    entry_request = RiskRequest(
        entry_strategy,
        EvidenceLabel.QUALIFIED_FOR_P4_RESEARCH,
        entry_state.to_risk_state(),
    )
    entry_circuit = assess_circuit_breakers(entry_request, entry_state)
    startup = apply_kill_switch_event(
        None,
        KillSwitchEvent(0, START - 1, KillSwitchEventType.STARTUP),
    ).current
    inactive = apply_kill_switch_event(
        startup,
        KillSwitchEvent(
            1,
            START,
            KillSwitchEventType.MANUAL_RESET,
            entry_circuit,
            True,
        ),
    ).current
    protective = assess_protective_entry(
        assess_entry_limits(size_entry(entry_request))
    )
    entry_authorization = authorize_paper_request(
        entry_request,
        entry_state,
        inactive,
        entry_circuit,
        protective,
    )

    exit_time = START + HOUR
    exit_view = _snapshot(symbol, exit_time)
    exit_event = DecisionEvent(1, exit_time, exit_time, exit_view)
    exit_strategy = StrategyDecision(
        StrategyContext(TREND_PULLBACK_IDENTITY, exit_view),
        StrategyAction.EXIT_LONG,
        DecisionReason.STRATEGY_EXIT,
    )
    quantity = entry_authorization.decision.approved_quantity
    if quantity is None:
        raise ExecutionScenarioError("Engineering entry fixture was not P4-approved")
    exit_state = _managed(
        symbol,
        exit_time,
        quantity=quantity,
        equity="9800",
        cash="8800",
        session_pnl="-200",
        losses=3,
        digest="2",
    )
    exit_request = RiskRequest(
        exit_strategy,
        EvidenceLabel.QUALIFIED_FOR_P4_RESEARCH,
        exit_state.to_risk_state(kill_switch_active=True),
    )
    exit_circuit = assess_circuit_breakers(exit_request, exit_state)
    active = apply_kill_switch_event(
        inactive,
        KillSwitchEvent(
            2,
            exit_time,
            KillSwitchEventType.CIRCUIT_OBSERVATION,
            exit_circuit,
        ),
    ).current
    exit_authorization = authorize_paper_request(
        exit_request,
        exit_state,
        active,
        exit_circuit,
    )

    ready = RecoveryReadiness(
        RecoveryStatus.READY,
        RecoveryReason.RECONCILIATION_PASSED,
        "a" * 64,
    )
    entry_decision = assess_local_paper_authorization(
        entry_authorization,
        ready,
    )
    exit_decision = assess_local_paper_authorization(
        exit_authorization,
        ready,
    )
    spec = BacktestSpec(
        symbol,
        START,
        exit_time + HOUR,
        initial_cash="10000",
        fee_bps="10",
        slippage_bps="5",
    )
    entry_bar = Candle(
        DATA_SOURCE,
        symbol,
        "1h",
        START,
        START + HOUR - 1,
        "100",
        "106",
        "99",
        "100",
        "100",
        "10000",
        20,
        True,
    )
    exit_bar = Candle(
        DATA_SOURCE,
        symbol,
        "1h",
        exit_time,
        exit_time + HOUR - 1,
        "101",
        "102",
        "100",
        "101",
        "100",
        "10000",
        20,
        True,
    )
    return _Fixture(
        symbol,
        spec,
        entry_decision,
        exit_decision,
        entry_event,
        exit_event,
        entry_bar,
        exit_bar,
    )


def _initialize_database(path, spec):
    with ExecutionIntentJournal(path):
        pass
    with LocalPaperOrderStore(path):
        pass
    with LocalPaperPortfolioStore(path, spec):
        pass


def _record_active(path, decision):
    with ExecutionIntentJournal(path) as journal:
        intent = journal.record(decision)
    decision_time = decision.authorization.request.strategy_decision.decision_time_ms
    with LocalPaperOrderStore(path) as store:
        created = store.apply(
            build_local_order_event(
                intent,
                0,
                decision_time - 2,
                LocalOrderEventType.CREATE,
            )
        ).current
        active = store.apply(
            build_local_order_event(
                intent,
                1,
                decision_time - 1,
                LocalOrderEventType.ACTIVATE,
                created,
            )
        ).current
    return intent, active


def _memory_active(decision):
    from .journal import LocalPaperIntentRecord

    intent = LocalPaperIntentRecord.from_decision(decision)
    decision_time = decision.authorization.request.strategy_decision.decision_time_ms
    create = build_local_order_event(
        intent,
        0,
        decision_time - 2,
        LocalOrderEventType.CREATE,
    )
    created = apply_local_order_event(intent, None, create).current
    activate = build_local_order_event(
        intent,
        1,
        decision_time - 1,
        LocalOrderEventType.ACTIVATE,
        created,
    )
    active = apply_local_order_event(intent, created, activate).current
    return intent, active


def _scenario_duplicate_intent(root, fixture):
    path = root / "execution.sqlite3"
    with ExecutionIntentJournal(path) as journal:
        first = journal.record(fixture.entry_decision)
        second = journal.record(fixture.entry_decision)
        count = journal.count()
        canonical = journal.canonical_json()
    passed = first == second and count == 1
    return (
        {"intent_count": 1, "duplicate_effect": False},
        {
            "intent_count": count,
            "duplicate_effect": first != second,
            "journal_sha256": _sha256(canonical),
        },
        passed,
    )


def _scenario_crash_rollback(root, fixture):
    path = root / "execution.sqlite3"
    with ExecutionIntentJournal(path):
        pass
    connection = sqlite3.connect(path)
    with connection:
        connection.execute(
            "CREATE TRIGGER reject_local_intent BEFORE INSERT ON local_paper_intents "
            "BEGIN SELECT RAISE(ABORT, 'injected rollback'); END"
        )
    connection.close()
    rejected = False
    with ExecutionIntentJournal(path) as journal:
        try:
            journal.record(fixture.entry_decision)
        except (ExecutionJournalError, IntentConflict):
            rejected = True
        count = journal.count()
    return (
        {"failure_rejected": True, "intent_count": 0},
        {"failure_rejected": rejected, "intent_count": count},
        rejected and count == 0,
    )


def _scenario_stale_authorization(root, fixture):
    path = root / "execution.sqlite3"
    stale_readiness = RecoveryReadiness(
        RecoveryStatus.READY,
        RecoveryReason.RECONCILIATION_PASSED,
        "b" * 64,
    )
    stale = assess_local_paper_authorization(
        fixture.entry_decision.authorization,
        stale_readiness,
    )
    conflict = False
    with ExecutionIntentJournal(path) as journal:
        original = journal.record(fixture.entry_decision)
        try:
            journal.record(stale)
        except IntentConflict:
            conflict = True
        count = journal.count()
        restored = journal.get(fixture.entry_decision.authorization_sha256)
    return (
        {"stale_rejected": True, "intent_count": 1},
        {
            "stale_rejected": conflict,
            "intent_count": count,
            "original_preserved": restored == original,
        },
        conflict and count == 1 and restored == original,
    )


def _scenario_out_of_order_event(root, fixture):
    path = root / "execution.sqlite3"
    with ExecutionIntentJournal(path) as journal:
        intent = journal.record(fixture.entry_decision)
    rejected = False
    with LocalPaperOrderStore(path) as store:
        created = store.apply(
            build_local_order_event(
                intent,
                0,
                START - 2,
                LocalOrderEventType.CREATE,
            )
        )
        skipped = build_local_order_event(
            intent,
            2,
            START - 1,
            LocalOrderEventType.ACTIVATE,
            created.current,
        )
        try:
            store.apply(skipped)
        except LocalOrderTransitionError:
            rejected = True
        events = store.events(intent.authorization_sha256)
        state = store.get_state(intent.authorization_sha256)
    return (
        {"out_of_order_rejected": True, "event_count": 1, "state_sequence": 0},
        {
            "out_of_order_rejected": rejected,
            "event_count": len(events),
            "state_sequence": None if state is None else state.sequence,
        },
        rejected and len(events) == 1 and state is not None and state.sequence == 0,
    )


def _scenario_journal_corruption(root, fixture):
    path = root / "execution.sqlite3"
    _initialize_database(path, fixture.spec)
    _record_active(path, fixture.entry_decision)
    clean = reconcile_startup(path, fixture.spec)
    connection = sqlite3.connect(path)
    with connection:
        connection.execute(
            "UPDATE local_paper_intents SET intent_sha256 = ?",
            ("0" * 64,),
        )
    connection.close()
    corrupt = reconcile_startup(path, fixture.spec)
    return (
        {"clean": "MATCH", "corrupt": "INTENT_INVALID", "ready": False},
        {
            "clean": clean.code.value,
            "corrupt": corrupt.code.value,
            "ready": corrupt.ready,
        },
        (
            clean.ready
            and clean.code is ReconciliationCode.MATCH
            and not corrupt.ready
            and corrupt.code is ReconciliationCode.INTENT_INVALID
        ),
    )


def _scenario_snapshot_corruption(root, fixture):
    path = root / "execution.sqlite3"
    snapshot = root / "recovery.snapshot.json"
    _initialize_database(path, fixture.spec)
    create_recovery_snapshot(path, snapshot, fixture.spec)
    snapshot.write_text("{", encoding="utf-8")
    report = recover_startup(path, snapshot, fixture.spec)
    return (
        {"code": "SNAPSHOT_CORRUPT", "ready": False},
        {"code": report.code.value, "ready": report.ready},
        not report.ready and report.code is RecoveryCode.SNAPSHOT_CORRUPT,
    )


def _scenario_missing_fill(root, fixture):
    del root
    intent, order = _memory_active(fixture.entry_decision)
    adapter = LocalPaperFillCostAdapter(fixture.symbol, fixture.spec)
    rejected = False
    try:
        adapter.process(
            fixture.entry_event,
            fixture.entry_decision,
            intent,
            order,
            None,
            fixture.spec,
        )
    except LocalPaperFillError:
        rejected = True
    return (
        {"missing_candle_rejected": True, "has_position": False},
        {
            "missing_candle_rejected": rejected,
            "has_position": adapter.has_position,
        },
        rejected and not adapter.has_position,
    )


def _scenario_cost_mismatch(root, fixture):
    del root
    intent, order = _memory_active(fixture.entry_decision)
    adapter = LocalPaperFillCostAdapter(fixture.symbol, fixture.spec)
    changed = replace(fixture.spec, fee_bps="11")
    rejected = False
    try:
        adapter.process(
            fixture.entry_event,
            fixture.entry_decision,
            intent,
            order,
            fixture.entry_bar,
            changed,
        )
    except LocalPaperFillError:
        rejected = True
    return (
        {"cost_mismatch_rejected": True, "has_position": False},
        {
            "cost_mismatch_rejected": rejected,
            "has_position": adapter.has_position,
        },
        rejected and not adapter.has_position,
    )


def _scenario_uncertain_commit(root, fixture):
    path = root / "execution.sqlite3"
    snapshot = root / "recovery.snapshot.json"
    _initialize_database(path, fixture.spec)
    create_recovery_snapshot(path, snapshot, fixture.spec)
    pending = Path(f"{snapshot}.pending")
    shutil.copyfile(snapshot, pending)
    report = recover_startup(path, snapshot, fixture.spec)
    return (
        {"code": "AMBIGUOUS_COMMIT", "ready": False, "pending_preserved": True},
        {
            "code": report.code.value,
            "ready": report.ready,
            "pending_preserved": pending.is_file(),
            "confirmation_available": report.manual_confirmation_sha256 is not None,
        },
        (
            not report.ready
            and report.code is RecoveryCode.AMBIGUOUS_COMMIT
            and pending.is_file()
            and report.manual_confirmation_sha256 is not None
        ),
    )


_HANDLERS = {
    "DUPLICATE_INTENT": _scenario_duplicate_intent,
    "CRASH_ROLLBACK": _scenario_crash_rollback,
    "STALE_AUTHORIZATION": _scenario_stale_authorization,
    "OUT_OF_ORDER_EVENT": _scenario_out_of_order_event,
    "JOURNAL_CORRUPTION": _scenario_journal_corruption,
    "SNAPSHOT_CORRUPTION": _scenario_snapshot_corruption,
    "MISSING_FILL_CANDLE": _scenario_missing_fill,
    "COST_POLICY_MISMATCH": _scenario_cost_mismatch,
    "UNCERTAIN_COMMIT": _scenario_uncertain_commit,
}


def scenario_artifact_json(record):
    if not isinstance(record, dict):
        raise ExecutionScenarioError("Scenario artifact record is invalid")
    payload = _json(record)
    if len(payload.encode("utf-8")) > MAX_ARTIFACT_BYTES:
        raise ExecutionScenarioError("Scenario artifact exceeds the bounded size")
    return payload


def _run_scenario(symbol, name):
    if symbol not in SYMBOLS or name not in SCENARIOS:
        raise ExecutionScenarioError("Scenario symbol or name is invalid")
    fixture = _fixture(symbol)
    with TemporaryDirectory() as temporary:
        root = Path(temporary)
        expected, observed, passed = _HANDLERS[name](root, fixture)
    if not passed:
        raise ExecutionScenarioError(f"Scenario failed closed invariant: {name}")
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_kind": ARTIFACT_KIND,
        "execution_policy_id": EXECUTION_POLICY_ID,
        "symbol": symbol,
        "scenario": name,
        "expected": expected,
        "observed": observed,
        "passed": True,
        "atomic_state_preserved": True,
        "engineering_fixture": True,
        "real_strategy_qualification": False,
        "paper_only": True,
        "live_master_lock": "OFF",
        "spot_only": True,
        "allow_short": False,
        "allow_leverage": False,
        "trade_permission": False,
        "exchange_order_submission": False,
        "ai_direct_execution": False,
    }


@dataclass(frozen=True, slots=True)
class ExecutionScenarioResult:
    symbol: str
    name: str
    artifact_json: str
    result_sha256: str

    def __post_init__(self):
        if (
            self.symbol not in SYMBOLS
            or self.name not in SCENARIOS
            or not isinstance(self.artifact_json, str)
            or not self.artifact_json.endswith("\n")
            or self.result_sha256 != _sha256(self.artifact_json)
        ):
            raise ExecutionScenarioError("Scenario result identity is invalid")
        try:
            record = json.loads(self.artifact_json)
        except json.JSONDecodeError:
            raise ExecutionScenarioError("Scenario result JSON is invalid") from None
        if (
            record.get("symbol") != self.symbol
            or record.get("scenario") != self.name
            or scenario_artifact_json(record) != self.artifact_json
        ):
            raise ExecutionScenarioError("Scenario result and artifact differ")


@dataclass(frozen=True, slots=True)
class ExecutionScenarioMatrixResult:
    runs: tuple[ExecutionScenarioResult, ...]
    index_json: str

    def __post_init__(self):
        expected_order = tuple(
            (symbol, name)
            for symbol in SYMBOLS
            for name in SCENARIOS
        )
        actual_order = tuple((item.symbol, item.name) for item in self.runs)
        if (
            type(self.runs) is not tuple
            or actual_order != expected_order
            or not isinstance(self.index_json, str)
            or not self.index_json.endswith("\n")
            or len(self.index_json.encode("utf-8")) > MAX_ARTIFACT_BYTES
        ):
            raise ExecutionScenarioError("Scenario matrix is incomplete or unordered")
        expected_records = [
            {
                "symbol": item.symbol,
                "scenario": item.name,
                "file": _filename(item.symbol, item.name),
                "sha256": item.result_sha256,
                "passed": True,
                "replay_equal": True,
            }
            for item in self.runs
        ]
        expected_index = {
            "schema_version": SCHEMA_VERSION,
            "artifact_kind": MATRIX_KIND,
            "execution_policy_id": EXECUTION_POLICY_ID,
            "symbols": list(SYMBOLS),
            "scenarios": list(SCENARIOS),
            "runs": expected_records,
            "paper_only": True,
            "live_master_lock": "OFF",
            "spot_only": True,
            "allow_short": False,
            "allow_leverage": False,
            "trade_permission": False,
            "exchange_order_submission": False,
            "ai_direct_execution": False,
        }
        try:
            actual_index = json.loads(self.index_json)
        except json.JSONDecodeError:
            raise ExecutionScenarioError("Scenario matrix index is invalid") from None
        if actual_index != expected_index or _json(actual_index) != self.index_json:
            raise ExecutionScenarioError("Scenario matrix index is noncanonical")


def _filename(symbol, name):
    return f"{symbol.lower()}-{name.lower().replace('_', '-')}.json"


def run_adversarial_execution_matrix():
    runs = []
    for symbol in SYMBOLS:
        for name in SCENARIOS:
            first = scenario_artifact_json(_run_scenario(symbol, name))
            replay = scenario_artifact_json(_run_scenario(symbol, name))
            if first != replay:
                raise ExecutionScenarioError(
                    f"Scenario replay diverged: {symbol}/{name}"
                )
            runs.append(
                ExecutionScenarioResult(
                    symbol,
                    name,
                    first,
                    _sha256(first),
                )
            )
    records = [
        {
            "symbol": item.symbol,
            "scenario": item.name,
            "file": _filename(item.symbol, item.name),
            "sha256": item.result_sha256,
            "passed": True,
            "replay_equal": True,
        }
        for item in runs
    ]
    index = {
        "schema_version": SCHEMA_VERSION,
        "artifact_kind": MATRIX_KIND,
        "execution_policy_id": EXECUTION_POLICY_ID,
        "symbols": list(SYMBOLS),
        "scenarios": list(SCENARIOS),
        "runs": records,
        "paper_only": True,
        "live_master_lock": "OFF",
        "spot_only": True,
        "allow_short": False,
        "allow_leverage": False,
        "trade_permission": False,
        "exchange_order_submission": False,
        "ai_direct_execution": False,
    }
    return ExecutionScenarioMatrixResult(tuple(runs), _json(index))


def write_adversarial_execution_matrix(result, output_dir):
    if not isinstance(result, ExecutionScenarioMatrixResult):
        raise ExecutionScenarioError("Scenario matrix output is invalid")
    target = (
        Path(output_dir)
        if isinstance(output_dir, (str, Path)) and str(output_dir)
        else None
    )
    if target is None:
        raise ExecutionScenarioError("Scenario evidence output directory is invalid")
    if target.exists():
        raise ExecutionScenarioError("Existing scenario evidence will not be overwritten")
    temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
    try:
        temporary.mkdir(parents=True)
        files = {"p5-009-index.json": result.index_json}
        for item in result.runs:
            files[_filename(item.symbol, item.name)] = item.artifact_json
        if not 1 <= len(files) <= MAX_EVIDENCE_FILES:
            raise ExecutionScenarioError("Scenario evidence file count is invalid")
        for name, payload in files.items():
            if len(payload.encode("utf-8")) > MAX_ARTIFACT_BYTES:
                raise ExecutionScenarioError("Scenario evidence file is too large")
            (temporary / name).write_text(
                payload,
                encoding="utf-8",
                newline="\n",
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary.replace(target)
    except ExecutionScenarioError:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    except OSError:
        shutil.rmtree(temporary, ignore_errors=True)
        raise ExecutionScenarioError("Cannot atomically publish scenario evidence") from None
    return target


def execution_matrix_sha256(result):
    if not isinstance(result, ExecutionScenarioMatrixResult):
        raise ExecutionScenarioError("Scenario matrix digest input is invalid")
    return _sha256(result.index_json)


def run_and_write_adversarial_execution_matrix(output_dir):
    result = run_adversarial_execution_matrix()
    write_adversarial_execution_matrix(result, output_dir)
    return result
