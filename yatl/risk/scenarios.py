"""Deterministic P4 adversarial scenarios over accepted public Spot data."""

import hashlib
import json
import shutil
from dataclasses import dataclass
from decimal import Decimal, localcontext
from pathlib import Path
from uuid import uuid4

from yatl.backtest import (BacktestClock, BacktestClockError, DecisionEvent,
                           FillReference, IntentAction)
from yatl.backtest.loader import (AcceptedBacktestDataset, BacktestLoadError,
                                  latest_spec_from_manifest,
                                  load_accepted_dataset)
from yatl.data import Candle, SYMBOLS
from yatl.strategy import (DecisionReason, EvidenceLabel, LongSetup,
                           StrategyAction, StrategyContext, StrategyDecision,
                           TREND_PULLBACK_IDENTITY)

from .adapter import (RiskAdapterError, RiskAdapterOutcome,
                      RiskManagedPaperAdapter, authorize_paper_request)
from .circuit import CircuitAssessment, assess_circuit_breakers
from .contracts import POLICY_ID, RiskRequest
from .kill_switch import (KillSwitchEvent, KillSwitchEventType, KillSwitchState,
                          apply_kill_switch_event)
from .limits import assess_entry_limits
from .protective import ProtectiveAssessment, assess_protective_entry
from .sizing import size_entry
from .state import ManagedPortfolioState


SCENARIOS = (
    "SESSION_LOSS_BOUNDARY",
    "GAP_FAIL_CLOSED",
    "POST_COST_REJECTION",
    "LOSS_STREAK_BOUNDARY",
    "DRAWDOWN_BOUNDARY",
    "STALE_STATE_REJECTION",
    "INSUFFICIENT_EVIDENCE",
    "KILL_SWITCH_EXIT",
)
ARTIFACT_KIND = "YATL_P4_ADVERSARIAL_SCENARIO"
MATRIX_KIND = "YATL_P4_ADVERSARIAL_MATRIX"
SCHEMA_VERSION = 1
MAX_EVIDENCE_FILES = 32
MAX_ARTIFACT_BYTES = 2 * 1024 * 1024
UTC_DAY_MILLISECONDS = 86_400_000


class RiskScenarioError(Exception):
    """A P4 adversarial scenario failed or could not fail closed."""


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")) + "\n"


def _sha256(value):
    payload = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(payload).hexdigest()


def _canonical(value):
    return format(value, "f")


def _scaled(value, factor):
    with localcontext() as arithmetic:
        arithmetic.prec = 256
        return _canonical(Decimal(value) * Decimal(factor))


def _dataset_sha256(dataset):
    if not isinstance(dataset, AcceptedBacktestDataset):
        raise RiskScenarioError("Scenario requires an accepted dataset")
    payload = {
        "symbol": dataset.spec.symbol,
        "start_time_ms": dataset.spec.start_time_ms,
        "end_time_ms": dataset.spec.end_time_ms,
        "manifest_generated_at_ms": dataset.manifest_generated_at_ms,
        "intervals": {
            "1h": [item.as_record() for item in dataset.primary],
            "15m": [item.as_record() for item in dataset.context],
            "4h": [item.as_record() for item in dataset.regime],
        },
    }
    return _sha256(_json(payload))


def _events_and_fills(dataset):
    try:
        events = tuple(BacktestClock(dataset).events())
    except (BacktestClockError, BacktestLoadError):
        raise RiskScenarioError("Scenario event clock failed safely") from None
    if len(events) < 2:
        raise RiskScenarioError("Scenario dataset requires at least two events")
    by_open = {item.open_time_ms: item for item in dataset.primary}
    if len(by_open) != len(dataset.primary):
        raise RiskScenarioError("Scenario primary candles are duplicated")
    fills = tuple(by_open.get(event.eligible_fill_open_time_ms)
                  for event in events[:2])
    if any(not isinstance(item, Candle) or not item.is_closed for item in fills):
        raise RiskScenarioError("Scenario next-open candle is unavailable")
    return events[:2], fills


def _decision(event, action=StrategyAction.ENTER_LONG, *, holding=False,
              stop_factor="0.95", target_factor="1.15"):
    if not isinstance(event, DecisionEvent):
        raise RiskScenarioError("Scenario decision event is invalid")
    context = StrategyContext(TREND_PULLBACK_IDENTITY, event.snapshot)
    setup = None
    if action is StrategyAction.ENTER_LONG:
        reference = event.snapshot.latest_primary.close
        setup = LongSetup(
            reference,
            _scaled(reference, stop_factor),
            _scaled(reference, target_factor),
        )
    reason = {
        StrategyAction.ENTER_LONG: DecisionReason.TREND_PULLBACK_ENTRY,
        StrategyAction.EXIT_LONG: DecisionReason.STRATEGY_EXIT,
        StrategyAction.NO_TRADE: (
            DecisionReason.HOLD_POSITION if holding
            else DecisionReason.SETUP_ABSENT
        ),
    }[action]
    return StrategyDecision(context, action, reason, setup)


def _state(event, *, previous=None, quantity="0", equity="10000", cash=None,
           session_pnl="0", losses=0, peak="10000"):
    if not isinstance(event, DecisionEvent):
        raise RiskScenarioError("Scenario state event is invalid")
    mark = event.snapshot.latest_primary.close
    cash = equity if cash is None else cash
    with localcontext() as arithmetic:
        arithmetic.prec = 256
        exposure = _canonical(Decimal(quantity) * Decimal(mark))
    sequence = 0 if previous is None else previous.sequence + 1
    previous_sha = None if previous is None else previous.state_sha256
    observation_sha = _sha256(_json({
        "schema_version": 1,
        "symbol": event.snapshot.symbol,
        "sequence": sequence,
        "decision_time_ms": event.decision_time_ms,
        "equity_quote": equity,
        "cash_quote": cash,
        "position_quantity": quantity,
        "mark_price": mark,
        "session_realized_pnl_quote": session_pnl,
        "consecutive_losses": losses,
    }))
    return ManagedPortfolioState(
        symbol=event.snapshot.symbol,
        sequence=sequence,
        decision_time_ms=event.decision_time_ms,
        session_start_time_ms=(
            event.decision_time_ms
            - event.decision_time_ms % UTC_DAY_MILLISECONDS
        ),
        session_start_equity_quote="10000",
        equity_quote=equity,
        cash_quote=cash,
        position_quantity=quantity,
        mark_price=mark,
        peak_equity_quote=peak,
        session_realized_pnl_quote=session_pnl,
        consecutive_losses=losses,
        open_positions=0 if Decimal(quantity) == 0 else 1,
        gross_exposure_quote=exposure,
        previous_state_sha256=previous_sha,
        observation_sha256=observation_sha,
    )


def _request(event, state, *, action=StrategyAction.ENTER_LONG,
             evidence=EvidenceLabel.QUALIFIED_FOR_P4_RESEARCH,
             kill_switch=False, holding=False, stop_factor="0.95",
             target_factor="1.15"):
    return RiskRequest(
        _decision(
            event, action, holding=holding, stop_factor=stop_factor,
            target_factor=target_factor,
        ),
        evidence,
        state.to_risk_state(kill_switch_active=kill_switch),
    )


def _inactive_switch(circuit):
    startup = apply_kill_switch_event(
        None,
        KillSwitchEvent(
            0, circuit.managed_state.decision_time_ms - 1,
            KillSwitchEventType.STARTUP,
        ),
    ).current
    return apply_kill_switch_event(
        startup,
        KillSwitchEvent(
            1, circuit.managed_state.decision_time_ms,
            KillSwitchEventType.MANUAL_RESET, circuit, True,
        ),
    ).current


def _triggered_switch(circuit):
    startup = apply_kill_switch_event(
        None,
        KillSwitchEvent(
            0, circuit.managed_state.decision_time_ms - 1,
            KillSwitchEventType.STARTUP,
        ),
    ).current
    return apply_kill_switch_event(
        startup,
        KillSwitchEvent(
            1, circuit.managed_state.decision_time_ms,
            KillSwitchEventType.CIRCUIT_OBSERVATION, circuit,
        ),
    ).current


def _protective(request):
    return assess_protective_entry(assess_entry_limits(size_entry(request)))


def _fill_records(fills):
    if type(fills) is not tuple or any(not isinstance(item, FillReference)
                                       for item in fills):
        raise RiskScenarioError("Scenario fills are invalid")
    return [{
        "action": item.action.value,
        "decision_time_ms": item.decision_time_ms,
        "fill_time_ms": item.fill_time_ms,
        "quantity": item.quantity,
        "reference_price": item.reference_price,
        "reason": item.reason.value,
    } for item in fills]


def _observed(circuit, switch, authorization=None, step=None, **extra):
    if (not isinstance(circuit, CircuitAssessment)
            or not isinstance(switch, KillSwitchState)):
        raise RiskScenarioError("Scenario evidence is incomplete")
    result = {
        "circuit_disposition": circuit.disposition.value,
        "circuit_reason": circuit.reason.value,
        "triggered_breakers": [item.value for item in circuit.triggered_breakers],
        "circuit_sha256": circuit.circuit_sha256,
        "kill_switch_mode": switch.mode.value,
        "kill_switch_reason": switch.reason.value,
        "kill_switch_active": switch.active,
        "kill_switch_state_sha256": switch.state_sha256,
        "risk_disposition": None,
        "risk_reason": None,
        "approved_quantity": None,
        "authorization_sha256": None,
        "adapter_outcome": None,
        "fills": [],
    }
    if authorization is not None:
        result.update({
            "risk_disposition": authorization.decision.disposition.value,
            "risk_reason": authorization.decision.reason.value,
            "approved_quantity": authorization.decision.approved_quantity,
            "authorization_sha256": authorization.authorization_sha256,
        })
    if step is not None:
        result.update({
            "adapter_outcome": step.outcome.value,
            "fills": _fill_records(step.fills),
        })
    result.update(extra)
    return result


def _blocked_boundary(event, fill, *, equity="10000", cash=None,
                      session_pnl="0", losses=0, peak="10000"):
    state = _state(
        event, equity=equity, cash=cash, session_pnl=session_pnl,
        losses=losses, peak=peak,
    )
    request = _request(event, state, kill_switch=True)
    circuit = assess_circuit_breakers(request, state)
    switch = _triggered_switch(circuit)
    authorization = authorize_paper_request(request, state, switch, circuit)
    adapter = RiskManagedPaperAdapter(TREND_PULLBACK_IDENTITY, state.symbol)
    step = adapter.process(event, authorization, fill)
    if (not circuit.triggered_breakers or not switch.active
            or step.outcome is not RiskAdapterOutcome.ENTRY_BLOCKED
            or step.fills or adapter.has_position):
        raise RiskScenarioError("Boundary scenario did not block entry atomically")
    return state, circuit, switch, authorization, step


def _run_scenario(dataset, name):
    if name not in SCENARIOS or dataset.spec.symbol not in SYMBOLS:
        raise RiskScenarioError("Scenario name or symbol is invalid")
    (first_event, second_event), (first_fill, second_fill) = (
        _events_and_fills(dataset)
    )
    expected = {}

    if name == "SESSION_LOSS_BOUNDARY":
        state, circuit, switch, authorization, step = _blocked_boundary(
            first_event, first_fill, equity="9800", cash="9800",
            session_pnl="-200",
        )
        expected = {"breaker": "SESSION_LOSS_LIMIT", "entry_blocked": True}
        observed = _observed(circuit, switch, authorization, step,
                             atomic_state_preserved=True)
    elif name == "LOSS_STREAK_BOUNDARY":
        state, circuit, switch, authorization, step = _blocked_boundary(
            first_event, first_fill, losses=3,
        )
        expected = {"breaker": "CONSECUTIVE_LOSS_LIMIT", "entry_blocked": True}
        observed = _observed(circuit, switch, authorization, step,
                             atomic_state_preserved=True)
    elif name == "DRAWDOWN_BOUNDARY":
        state, circuit, switch, authorization, step = _blocked_boundary(
            first_event, first_fill, equity="9000", cash="9000", peak="10000",
        )
        expected = {"breaker": "DRAWDOWN_LIMIT", "entry_blocked": True}
        observed = _observed(circuit, switch, authorization, step,
                             atomic_state_preserved=True)
    elif name == "POST_COST_REJECTION":
        state = _state(first_event)
        request = _request(first_event, state, target_factor="1.001")
        circuit = assess_circuit_breakers(request, state)
        switch = _inactive_switch(circuit)
        protective = _protective(request)
        authorization = authorize_paper_request(
            request, state, switch, circuit, protective,
        )
        adapter = RiskManagedPaperAdapter(TREND_PULLBACK_IDENTITY, state.symbol)
        step = adapter.process(first_event, authorization, first_fill)
        if (protective.status.value != "REJECT"
                or step.outcome is not RiskAdapterOutcome.ENTRY_BLOCKED
                or step.fills or adapter.has_position):
            raise RiskScenarioError("Post-cost scenario did not reject safely")
        expected = {"protective_status": "REJECT", "entry_blocked": True}
        observed = _observed(
            circuit, switch, authorization, step,
            protective_status=protective.status.value,
            protective_reason=protective.reason.value,
            protective_sha256=protective.gate_sha256,
            atomic_state_preserved=True,
        )
    elif name == "INSUFFICIENT_EVIDENCE":
        state = _state(first_event)
        request = _request(
            first_event, state, evidence=EvidenceLabel.INSUFFICIENT_EVIDENCE,
        )
        circuit = assess_circuit_breakers(request, state)
        switch = _inactive_switch(circuit)
        authorization = authorize_paper_request(
            request, state, switch, circuit,
        )
        adapter = RiskManagedPaperAdapter(TREND_PULLBACK_IDENTITY, state.symbol)
        step = adapter.process(first_event, authorization, first_fill)
        if (authorization.decision.reason.value != "EVIDENCE_NOT_QUALIFIED"
                or step.outcome is not RiskAdapterOutcome.ENTRY_BLOCKED
                or step.fills or adapter.has_position):
            raise RiskScenarioError("Insufficient evidence reached P2 entry")
        expected = {"risk_reason": "EVIDENCE_NOT_QUALIFIED",
                    "entry_blocked": True}
        observed = _observed(circuit, switch, authorization, step,
                             atomic_state_preserved=True)
    elif name == "GAP_FAIL_CLOSED":
        state = _state(first_event)
        request = _request(
            first_event, state, stop_factor="0.001", target_factor="2",
        )
        circuit = assess_circuit_breakers(request, state)
        switch = _inactive_switch(circuit)
        protective = _protective(request)
        authorization = authorize_paper_request(
            request, state, switch, circuit, protective,
        )
        adapter = RiskManagedPaperAdapter(TREND_PULLBACK_IDENTITY, state.symbol)
        rejected = False
        try:
            adapter.process(first_event, authorization, second_fill)
        except RiskAdapterError:
            rejected = True
        if not rejected or adapter.has_position:
            raise RiskScenarioError("Gap scenario changed Paper state")
        retry = adapter.process(first_event, authorization, first_fill)
        if (retry.outcome is not RiskAdapterOutcome.ENTRY_APPROVED
                or not retry.fills):
            raise RiskScenarioError("Gap scenario could not retry atomically")
        expected = {"gap_rejected": True, "retry_succeeded": True}
        observed = _observed(
            circuit, switch, authorization, retry,
            gap_failure="P2_REJECTED_MISSING_EXPECTED_FILL_CANDLE",
            atomic_state_preserved=True,
            retry_succeeded=True,
        )
    elif name == "STALE_STATE_REJECTION":
        state = _state(first_event)
        request = _request(first_event, state)
        circuit = assess_circuit_breakers(request, state)
        switch = _inactive_switch(circuit)
        newer_state = _state(second_event, previous=state)
        newer_request = _request(second_event, newer_state)
        newer_circuit = assess_circuit_breakers(newer_request, newer_state)
        rejected = False
        try:
            authorize_paper_request(
                newer_request, newer_state, switch, newer_circuit,
                _protective(newer_request),
            )
        except RiskAdapterError:
            rejected = True
        if not rejected:
            raise RiskScenarioError("Stale Kill Switch evidence was accepted")
        expected = {"stale_state_rejected": True, "fills": 0}
        observed = _observed(
            newer_circuit, switch,
            stale_failure="LATEST_CIRCUIT_NOT_CONSUMED",
            atomic_state_preserved=True,
        )
    else:
        state = _state(first_event)
        entry_request = _request(
            first_event, state, stop_factor="0.001", target_factor="2",
        )
        entry_circuit = assess_circuit_breakers(entry_request, state)
        inactive = _inactive_switch(entry_circuit)
        entry_authorization = authorize_paper_request(
            entry_request, state, inactive, entry_circuit,
            _protective(entry_request),
        )
        adapter = RiskManagedPaperAdapter(TREND_PULLBACK_IDENTITY, state.symbol)
        entry_step = adapter.process(first_event, entry_authorization, first_fill)
        quantity = entry_authorization.decision.approved_quantity
        if not adapter.has_position or quantity is None:
            raise RiskScenarioError("Kill Switch exit fixture did not enter Paper")
        exit_state = _state(
            second_event, previous=state, quantity=quantity, equity="9800",
            cash="9800", session_pnl="-200",
        )
        exit_request = _request(
            second_event, exit_state, action=StrategyAction.EXIT_LONG,
            kill_switch=True,
        )
        exit_circuit = assess_circuit_breakers(exit_request, exit_state)
        active = apply_kill_switch_event(
            inactive,
            KillSwitchEvent(
                2, second_event.decision_time_ms,
                KillSwitchEventType.CIRCUIT_OBSERVATION, exit_circuit,
            ),
        ).current
        exit_authorization = authorize_paper_request(
            exit_request, exit_state, active, exit_circuit,
        )
        exit_step = adapter.process(
            second_event, exit_authorization, second_fill,
        )
        if (not active.active
                or exit_step.outcome is not RiskAdapterOutcome.EXIT_APPROVED
                or adapter.has_position
                or not exit_step.fills
                or exit_step.fills[0].quantity != quantity):
            raise RiskScenarioError("Kill Switch blocked the risk-reducing exit")
        expected = {"entry_approved": True, "exit_under_kill_switch": True,
                    "final_position_flat": True}
        observed = _observed(
            exit_circuit, active, exit_authorization, exit_step,
            entry_authorization_sha256=entry_authorization.authorization_sha256,
            entry_fills=_fill_records(entry_step.fills),
            final_position_flat=True,
        )

    record = {
        "schema_version": SCHEMA_VERSION,
        "artifact_kind": ARTIFACT_KIND,
        "policy_id": POLICY_ID,
        "scenario": name,
        "symbol": dataset.spec.symbol,
        "source": "BINANCE_SPOT_PUBLIC_CLOSED_OHLCV",
        "manifest_generated_at_ms": dataset.manifest_generated_at_ms,
        "dataset_sha256": _dataset_sha256(dataset),
        "decision_time_ms": first_event.decision_time_ms,
        "context_sha256": _decision(first_event).context_sha256,
        "expected": expected,
        "observed": observed,
        "passed": True,
        "paper_only": True,
        "live_master_lock": "OFF",
        "spot_only": True,
        "allow_short": False,
        "allow_leverage": False,
        "trade_permission": False,
        "exchange_order_submission": False,
    }
    record["result_sha256"] = _sha256(_json(record))
    return record


def scenario_artifact_json(record):
    required = {
        "schema_version", "artifact_kind", "policy_id", "scenario", "symbol",
        "source", "manifest_generated_at_ms", "dataset_sha256",
        "decision_time_ms", "context_sha256", "expected", "observed", "passed",
        "paper_only", "live_master_lock", "spot_only", "allow_short",
        "allow_leverage", "trade_permission", "exchange_order_submission",
        "result_sha256",
    }
    if (not isinstance(record, dict) or set(record) != required
            or record.get("schema_version") != SCHEMA_VERSION
            or record.get("artifact_kind") != ARTIFACT_KIND
            or record.get("policy_id") != POLICY_ID
            or record.get("scenario") not in SCENARIOS
            or record.get("symbol") not in SYMBOLS
            or record.get("passed") is not True
            or record.get("paper_only") is not True
            or record.get("live_master_lock") != "OFF"
            or record.get("spot_only") is not True
            or record.get("allow_short") is not False
            or record.get("allow_leverage") is not False
            or record.get("trade_permission") is not False
            or record.get("exchange_order_submission") is not False):
        raise RiskScenarioError("Scenario artifact identity is invalid")
    material = dict(record)
    digest = material.pop("result_sha256", None)
    if digest != _sha256(_json(material)):
        raise RiskScenarioError("Scenario artifact digest is inconsistent")
    encoded = _json(record)
    lowered = encoded.lower()
    forbidden = (
        '"api_key"', '"api_secret"', '"password"', '"credential"',
        '"database_path"', '"manifest_path"', '"broker"',
    )
    if (any(item in lowered for item in forbidden)
            or len(encoded.encode("utf-8")) > MAX_ARTIFACT_BYTES):
        raise RiskScenarioError("Scenario artifact contains forbidden material")
    return encoded


@dataclass(frozen=True, slots=True)
class RiskScenarioResult:
    name: str
    symbol: str
    artifact_json: str
    result_sha256: str

    def __post_init__(self):
        if (self.name not in SCENARIOS or self.symbol not in SYMBOLS
                or not isinstance(self.artifact_json, str)
                or not self.artifact_json.endswith("\n")
                or self.result_sha256 != _sha256(self.artifact_json)):
            raise RiskScenarioError("Scenario result is invalid")
        try:
            record = json.loads(self.artifact_json)
        except (TypeError, json.JSONDecodeError):
            raise RiskScenarioError("Scenario result JSON is invalid") from None
        if (record.get("scenario") != self.name
                or record.get("symbol") != self.symbol
                or scenario_artifact_json(record) != self.artifact_json):
            raise RiskScenarioError("Scenario result and artifact differ")


@dataclass(frozen=True, slots=True)
class RiskScenarioMatrixResult:
    runs: tuple[RiskScenarioResult, ...]
    index_json: str

    def __post_init__(self):
        expected = {(symbol, name) for symbol in SYMBOLS for name in SCENARIOS}
        actual = {(item.symbol, item.name) for item in self.runs}
        if (type(self.runs) is not tuple or actual != expected
                or len(actual) != len(self.runs)
                or not isinstance(self.index_json, str)
                or not self.index_json.endswith("\n")
                or len(self.index_json.encode("utf-8")) > MAX_ARTIFACT_BYTES):
            raise RiskScenarioError("Scenario matrix is incomplete")
        try:
            index = json.loads(self.index_json)
        except (TypeError, json.JSONDecodeError):
            raise RiskScenarioError("Scenario matrix index is invalid") from None
        expected_records = [{
            "symbol": item.symbol,
            "scenario": item.name,
            "file": _filename(item.symbol, item.name),
            "sha256": item.result_sha256,
            "passed": True,
            "replay_equal": True,
        } for item in self.runs]
        fixed = {
            "schema_version": SCHEMA_VERSION,
            "artifact_kind": MATRIX_KIND,
            "policy_id": POLICY_ID,
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
        }
        if index != fixed or _json(index) != self.index_json:
            raise RiskScenarioError("Scenario matrix index is noncanonical or inconsistent")


def _filename(symbol, name):
    return f"{symbol.lower()}-{name.lower().replace('_', '-')}.json"


def run_adversarial_scenario_matrix(database_path, manifest_path, *, hours=24):
    if type(hours) is not int or not 2 <= hours <= 24 * 365:
        raise RiskScenarioError("Scenario matrix hours are invalid")
    runs = []
    try:
        for symbol in SYMBOLS:
            spec = latest_spec_from_manifest(manifest_path, symbol, hours=hours)
            dataset = load_accepted_dataset(database_path, manifest_path, spec)
            for name in SCENARIOS:
                first = scenario_artifact_json(_run_scenario(dataset, name))
                replay = scenario_artifact_json(_run_scenario(dataset, name))
                if first != replay:
                    raise RiskScenarioError("Scenario replay is not byte-identical")
                runs.append(RiskScenarioResult(
                    name, symbol, first, _sha256(first),
                ))
    except RiskScenarioError:
        raise
    except (BacktestLoadError, BacktestClockError, RiskAdapterError,
            TypeError, ValueError):
        raise RiskScenarioError("Adversarial scenario matrix failed safely") from None

    records = [{
        "symbol": item.symbol,
        "scenario": item.name,
        "file": _filename(item.symbol, item.name),
        "sha256": item.result_sha256,
        "passed": True,
        "replay_equal": True,
    } for item in runs]
    index = {
        "schema_version": SCHEMA_VERSION,
        "artifact_kind": MATRIX_KIND,
        "policy_id": POLICY_ID,
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
    }
    return RiskScenarioMatrixResult(tuple(runs), _json(index))


def write_adversarial_scenario_matrix(result, output_dir):
    if not isinstance(result, RiskScenarioMatrixResult):
        raise RiskScenarioError("Scenario matrix output is invalid")
    target = (Path(output_dir)
              if isinstance(output_dir, (str, Path)) and str(output_dir)
              else None)
    if target is None:
        raise RiskScenarioError("Scenario evidence output directory is invalid")
    if target.exists():
        raise RiskScenarioError("Existing scenario evidence will not be overwritten")
    temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
    try:
        temporary.mkdir(parents=True)
        files = {"p4-009-index.json": result.index_json}
        for item in result.runs:
            files[_filename(item.symbol, item.name)] = item.artifact_json
        if not 1 <= len(files) <= MAX_EVIDENCE_FILES:
            raise RiskScenarioError("Scenario evidence file count is invalid")
        for name, content in files.items():
            (temporary / name).write_text(content, encoding="utf-8", newline="\n")
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary.replace(target)
    except RiskScenarioError:
        raise
    except OSError:
        raise RiskScenarioError("Cannot publish scenario evidence atomically") from None
    finally:
        if temporary.exists():
            shutil.rmtree(temporary, ignore_errors=True)
    return target


def scenario_matrix_sha256(result):
    if not isinstance(result, RiskScenarioMatrixResult):
        raise RiskScenarioError("Scenario matrix digest input is invalid")
    return _sha256(result.index_json)


def run_and_write_adversarial_matrix(database_path, manifest_path, output_dir,
                                     *, hours=24):
    result = run_adversarial_scenario_matrix(
        database_path, manifest_path, hours=hours,
    )
    write_adversarial_scenario_matrix(result, output_dir)
    return result
