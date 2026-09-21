"""P10-007 deterministic evaluation of the frozen forward-validation gates.

Consumes only accepted P10 store/snapshot/Paper/economics evidence. It adds no
market-data transport, execution, sizing, system clock or evidence promotion.
"""

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal, DecimalException, localcontext
from enum import Enum

from yatl.backtest import BacktestClock
from yatl.backtest.costs import DECIMAL_PRECISION
from yatl.strategy import (
    MarketRegime,
    RegimeError,
    StrategyContext,
    TREND_PULLBACK_IDENTITY,
    classify_regime,
)

from .economics import (
    ForwardEconomicsError,
    ForwardEconomicsReport,
    calculate_forward_economics,
)
from .forward_store import ForwardStoreError
from .ingestion import ForwardIngestionSnapshot
from .paper_runner import (
    ForwardPaperRunResult,
    ForwardPaperRunnerError,
    _dataset_for_symbol,
)
from .registration import EconomicGateRegistry
from .window import ForwardWindowSeal


FORWARD_GATE_ID = "P10_FORWARD_GATE_V1"
ZERO = Decimal(0)


class ForwardGateError(Exception):
    """P10 gate inputs cannot be evaluated without weakening frozen evidence."""


class CriterionStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class GateDisposition(str, Enum):
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    FAIL = "FAIL"
    PASS_CANDIDATE = "PASS_CANDIDATE"


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _plain(value):
    if type(value) is not Decimal or not value.is_finite():
        raise ForwardGateError("Gate arithmetic requires finite Decimal values")
    if value == 0:
        return "0"
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


@dataclass(frozen=True, slots=True)
class ForwardGateReport:
    """Canonical immutable P10-007 payload."""

    canonical_json: str

    def as_record(self):
        return json.loads(self.canonical_json)

    @property
    def report_sha256(self):
        return hashlib.sha256(self.canonical_json.encode("utf-8")).hexdigest()


def _criterion(name, status, evidence, thresholds):
    if not isinstance(status, CriterionStatus):
        raise ForwardGateError("Criterion status is invalid")
    return {
        "criterion": name,
        "status": status.value,
        "evidence": evidence,
        "thresholds": thresholds,
    }


def _segment_summary(economics, gates):
    start = economics["observation_start_ms"]
    end = economics["observation_end_ms"]
    duration = economics["observation_duration_ms"]
    if (
        type(start) is not int
        or type(end) is not int
        or type(duration) is not int
        or duration <= 0
        or end - start != duration
    ):
        raise ForwardGateError("Economics observation interval is invalid")
    capital = Decimal(economics["pooled"]["initial_equity_quote"])
    if capital <= 0:
        raise ForwardGateError("Segment capital basis must be positive")

    pnls = [ZERO for _ in range(gates.segment_count)]
    trade_count = [0 for _ in range(gates.segment_count)]
    for symbol in economics["symbols"]:
        for trade in symbol["trades"]:
            exit_time = trade["exit_time_ms"]
            if type(exit_time) is not int or not start <= exit_time < end:
                raise ForwardGateError("Completed trade lies outside gate interval")
            index = min(
                ((exit_time - start) * gates.segment_count) // duration,
                gates.segment_count - 1,
            )
            pnls[index] += Decimal(trade["net_pnl_quote"])
            trade_count[index] += 1

    # Reconcile time-segment PnL to P10-006 net equity. Open positions are not
    # completed trades; their accepted net-liquidation PnL belongs only to the
    # final observed segment.
    pnls[-1] += sum(
        (
            Decimal(symbol["unrealized_liquidation_net_pnl_quote"])
            for symbol in economics["symbols"]
        ),
        ZERO,
    )
    returns = [value / capital for value in pnls]
    if sum(pnls, ZERO) != Decimal(economics["pooled"]["net_pnl_after_costs_quote"]):
        raise ForwardGateError("Segment PnL does not reconcile to pooled economics")
    return {
        "attribution": (
            "COMPLETED_TRADE_EXIT_PLUS_FINAL_OPEN_NET_LIQUIDATION_TO_LAST_SEGMENT"
        ),
        "capital_basis_quote": _plain(capital),
        "segments": [
            {
                "index": index + 1,
                "net_pnl_after_costs_quote": _plain(pnls[index]),
                "net_return_after_costs": _plain(returns[index]),
                "completed_trades": trade_count[index],
                "positive": pnls[index] > 0,
            }
            for index in range(gates.segment_count)
        ],
        "positive_segments": sum(value > 0 for value in pnls),
        "worst_segment_return": _plain(min(returns)),
    }


def _regime_summary(store, snapshot, run, gates):
    observed = set()
    unknown_observations = 0
    entries_outside = 0
    entries_while_kill = 0
    risk_policy_violations = 0
    per_symbol = []

    for symbol_result in run.symbols:
        dataset, _ = _dataset_for_symbol(store, snapshot, symbol_result.symbol)
        events = tuple(BacktestClock(dataset).events())
        if len(events) != len(symbol_result.trace):
            raise ForwardGateError("Runner trace length differs from point-in-time replay")
        counts = {}
        symbol_outside = 0
        for event, trace in zip(events, symbol_result.trace):
            context = StrategyContext(TREND_PULLBACK_IDENTITY, event.snapshot)
            if (
                trace.get("sequence") != event.sequence
                or trace.get("decision_time_ms") != event.decision_time_ms
                or trace.get("context_sha256") != context.context_sha256
            ):
                raise ForwardGateError("Runner trace differs from regime replay")
            result = classify_regime(context)
            regime = result.regime.value
            counts[regime] = counts.get(regime, 0) + 1
            if result.regime is MarketRegime.UNKNOWN:
                unknown_observations += 1
            else:
                observed.add(regime)

            effective = trace.get("effective_intent")
            veto = trace.get("entry_veto")
            strategy_action = trace.get("strategy_action")
            kill_active = trace.get("risk_state", {}).get("kill_switch_active")
            if effective == "ENTER_LONG":
                if regime not in gates.allowed_entry_regimes:
                    entries_outside += 1
                    symbol_outside += 1
                if kill_active is True:
                    entries_while_kill += 1

            violation = False
            if strategy_action == "ENTER_LONG":
                if not isinstance(veto, dict):
                    violation = True
                elif veto.get("allowed") is True:
                    violation = effective != "ENTER_LONG" or veto.get("reasons") != []
                else:
                    violation = effective != "HOLD" or not veto.get("reasons")
            else:
                violation = veto is not None or effective == "ENTER_LONG"
            if violation:
                risk_policy_violations += 1

        per_symbol.append(
            {
                "symbol": symbol_result.symbol,
                "observed_regime_counts": {
                    key: counts[key] for key in sorted(counts)
                },
                "entries_outside_allowed_regimes": symbol_outside,
            }
        )

    return {
        "distinct_non_unknown_regimes": sorted(observed),
        "distinct_non_unknown_regime_count": len(observed),
        "unknown_observations": unknown_observations,
        "entries_outside_allowed_regimes": entries_outside,
        "entries_while_kill_switch_active": entries_while_kill,
        "risk_policy_violations": risk_policy_violations,
        "symbols": per_symbol,
    }


def _sample_met(economics):
    return (
        economics.get("sample_status") == "MINIMUM_SAMPLE_MET_ONLY"
        and economics.get("insufficiency_reasons") == []
    )


def _criteria(snapshot, run, economics, regime, gates):
    sample_met = _sample_met(economics)
    pooled = economics["pooled"]
    symbols = economics["symbols"]

    results = []

    net_return = Decimal(pooled["net_return_after_costs"])
    profit_factor = pooled["profit_factor_after_costs"]
    pf_defined = pooled["profit_factor_status"] == "DEFINED" and profit_factor is not None
    profitability_pass = (
        net_return >= Decimal(gates.minimum_net_return_after_costs)
        and pf_defined
        and Decimal(profit_factor) >= Decimal(gates.minimum_profit_factor_after_costs)
    )
    results.append(_criterion(
        "NET_PNL_AFTER_COSTS",
        (
            CriterionStatus.PASS if sample_met and profitability_pass
            else CriterionStatus.FAIL if sample_met
            else CriterionStatus.INSUFFICIENT_DATA
        ),
        {
            "net_return_after_costs": pooled["net_return_after_costs"],
            "profit_factor_after_costs": profit_factor,
            "profit_factor_status": pooled["profit_factor_status"],
            "fee_quote": pooled["executed_fee_quote"],
            "slippage_quote": pooled["executed_slippage_quote"],
        },
        {
            "minimum_net_return_after_costs": gates.minimum_net_return_after_costs,
            "minimum_profit_factor_after_costs": gates.minimum_profit_factor_after_costs,
            "fee_and_slippage_must_be_included": gates.fee_and_slippage_must_be_included,
        },
    ))

    realized_dd = Decimal(
        pooled["realized_drawdown"]["maximum_drawdown_fraction"]
    )
    sampled_dd = Decimal(
        pooled["sampled_liquidation_drawdown"]["maximum_drawdown_fraction"]
    )
    validation_dd = max(realized_dd, sampled_dd)
    dd_breached = validation_dd > Decimal(gates.maximum_validation_drawdown_fraction)
    results.append(_criterion(
        "MAX_DRAWDOWN",
        (
            CriterionStatus.FAIL if dd_breached
            else CriterionStatus.PASS if sample_met
            else CriterionStatus.INSUFFICIENT_DATA
        ),
        {
            "realized_drawdown_fraction": _plain(realized_dd),
            "sampled_liquidation_drawdown_fraction": _plain(sampled_dd),
            "validation_drawdown_fraction": _plain(validation_dd),
        },
        {
            "maximum_validation_drawdown_fraction":
                gates.maximum_validation_drawdown_fraction,
            "comparison": "MAX_OF_REALIZED_AND_SAMPLED_LIQUIDATION",
        },
    ))

    results.append(_criterion(
        "SAMPLE_SIZE",
        CriterionStatus.PASS if sample_met else CriterionStatus.INSUFFICIENT_DATA,
        {
            "observed_days": economics["observed_days"],
            "pooled_completed_trades": pooled["completed_trades"],
            "completed_trades_per_symbol": {
                item["symbol"]: item["completed_trades"] for item in symbols
            },
            "insufficiency_reasons": list(economics["insufficiency_reasons"]),
        },
        {
            "minimum_validation_days": gates.minimum_validation_days,
            "minimum_total_completed_trades": gates.minimum_total_completed_trades,
            "minimum_completed_trades_per_symbol":
                gates.minimum_completed_trades_per_symbol,
        },
    ))

    segments = _segment_summary(economics, gates)
    symbols_positive = {
        item["symbol"]: Decimal(item["net_pnl_after_costs_quote"]) > 0
        for item in symbols
    }
    consistency_pass = (
        segments["positive_segments"] >= gates.minimum_positive_segments
        and Decimal(segments["worst_segment_return"])
        >= -Decimal(gates.maximum_segment_loss_fraction)
        and (not gates.positive_net_pnl_each_symbol_required
             or all(symbols_positive.values()))
    )
    results.append(_criterion(
        "CONSISTENCY",
        (
            CriterionStatus.PASS if sample_met and consistency_pass
            else CriterionStatus.FAIL if sample_met
            else CriterionStatus.INSUFFICIENT_DATA
        ),
        {
            **segments,
            "positive_net_pnl_each_symbol": symbols_positive,
        },
        {
            "segment_count": gates.segment_count,
            "minimum_positive_segments": gates.minimum_positive_segments,
            "maximum_segment_loss_fraction": gates.maximum_segment_loss_fraction,
            "positive_net_pnl_each_symbol_required":
                gates.positive_net_pnl_each_symbol_required,
        },
    ))

    regime_hard_fail = (
        regime["entries_outside_allowed_regimes"]
        > gates.maximum_entries_outside_allowed_regimes
    )
    regime_coverage = (
        regime["distinct_non_unknown_regime_count"]
        >= gates.minimum_distinct_regimes_observed
    )
    results.append(_criterion(
        "REGIME_STABILITY",
        (
            CriterionStatus.FAIL if regime_hard_fail
            else CriterionStatus.PASS if sample_met and regime_coverage
            else CriterionStatus.FAIL if sample_met
            else CriterionStatus.INSUFFICIENT_DATA
        ),
        regime,
        {
            "minimum_distinct_regimes_observed":
                gates.minimum_distinct_regimes_observed,
            "allowed_entry_regimes": list(gates.allowed_entry_regimes),
            "maximum_entries_outside_allowed_regimes":
                gates.maximum_entries_outside_allowed_regimes,
            "unknown_regime_counts_toward_distinct_requirement": False,
        },
    ))

    snapshot_quality = (
        snapshot.quality_pass is True
        and all(item.quality_pass is True for item in snapshot.datasets)
    )
    unresolved_quality = 0 if snapshot_quality else 1
    unresolved_reconciliation = 0
    safety_breaches = sum([
        run.paper_only is not True,
        run.live_master_lock != "OFF",
        run.p3_qualification_fabricated is not False,
        run.p4_risk_authorization_created is not False,
        run.quantity_authority_created is not False,
        run.external_transport_used is not False,
        run.trade_permission is not False,
        run.order_endpoint is not False,
        run.ai_direct_execution is not False,
        any(item.point_in_time_verified is not True for item in run.symbols),
        any(item.replay_from_start is not True for item in run.symbols),
    ])
    latched = sorted(item.symbol for item in run.symbols if item.kill_switch_latched)
    unresolved_recovery = len(latched)
    failure_pass = (
        unresolved_quality <= gates.maximum_unresolved_data_quality_failures
        and unresolved_reconciliation
        <= gates.maximum_unresolved_reconciliation_failures
        and safety_breaches <= gates.maximum_safety_breaches
        and regime["entries_while_kill_switch_active"]
        <= gates.maximum_entries_while_kill_switch_active
        and unresolved_recovery == 0
    )
    results.append(_criterion(
        "FAILURE_RECOVERY",
        CriterionStatus.PASS if failure_pass else CriterionStatus.FAIL,
        {
            "unresolved_data_quality_failures": unresolved_quality,
            "unresolved_reconciliation_failures": unresolved_reconciliation,
            "safety_breaches": safety_breaches,
            "entries_while_kill_switch_active":
                regime["entries_while_kill_switch_active"],
            "kill_switch_latched_symbols": latched,
            "unresolved_recovery_events": unresolved_recovery,
            "recovery_semantics": (
                "P10_005_HAS_NO_AUTO_RESET; ANY_LATCH_WITHOUT_ACCEPTED_CLEAR_AND_"
                "MANUAL_RESET_EVIDENCE_REMAINS_UNRESOLVED"
            ),
        },
        {
            "maximum_unresolved_data_quality_failures":
                gates.maximum_unresolved_data_quality_failures,
            "maximum_unresolved_reconciliation_failures":
                gates.maximum_unresolved_reconciliation_failures,
            "maximum_safety_breaches": gates.maximum_safety_breaches,
            "maximum_entries_while_kill_switch_active":
                gates.maximum_entries_while_kill_switch_active,
            "recovery_requires_clear_observation_and_manual_reset":
                gates.recovery_requires_clear_observation_and_manual_reset,
        },
    ))

    order_events = int(run.order_endpoint is True)
    ai_events = int(run.ai_direct_execution is True)
    risk_pass = (
        regime["risk_policy_violations"] <= gates.maximum_risk_policy_violations
        and order_events <= gates.maximum_order_endpoint_events
        and ai_events <= gates.maximum_ai_direct_execution_events
    )
    results.append(_criterion(
        "RISK_CONTROLS",
        CriterionStatus.PASS if risk_pass else CriterionStatus.FAIL,
        {
            "risk_policy_violations": regime["risk_policy_violations"],
            "order_endpoint_events": order_events,
            "ai_direct_execution_events": ai_events,
        },
        {
            "maximum_risk_policy_violations":
                gates.maximum_risk_policy_violations,
            "maximum_order_endpoint_events": gates.maximum_order_endpoint_events,
            "maximum_ai_direct_execution_events":
                gates.maximum_ai_direct_execution_events,
        },
    ))

    expected = [item.value for item in gates.criteria]
    actual = [item["criterion"] for item in results]
    if actual != expected or len(actual) != len(set(actual)):
        raise ForwardGateError("Registered criteria were not evaluated exactly once")
    return results


def _disposition(criteria):
    statuses = [item["status"] for item in criteria]
    if CriterionStatus.FAIL.value in statuses:
        return GateDisposition.FAIL
    if CriterionStatus.INSUFFICIENT_DATA.value in statuses:
        return GateDisposition.INSUFFICIENT_DATA
    if all(value == CriterionStatus.PASS.value for value in statuses):
        return GateDisposition.PASS_CANDIDATE
    raise ForwardGateError("Gate disposition cannot be resolved")


def _assemble(snapshot, run, economics, regime):
    gates = EconomicGateRegistry()
    criteria = _criteria(snapshot, run, economics, regime, gates)
    disposition = _disposition(criteria)
    return ForwardGateReport(_json({
        "gate_id": FORWARD_GATE_ID,
        "input_economics_sha256": hashlib.sha256(
            _json(economics).encode("utf-8")
        ).hexdigest(),
        "input_run_sha256": run.run_sha256,
        "ingestion_snapshot_sha256": snapshot.snapshot_sha256,
        "window_sha256": run.window_sha256,
        "candidate_sha256": run.candidate_sha256,
        "gate_registry_sha256": run.gate_registry_sha256,
        "criteria": criteria,
        "disposition": disposition.value,
        "semantics": {
            "criterion_count": len(criteria),
            "fail_precedence": "FAIL_OVER_INSUFFICIENT_OVER_PASS_CANDIDATE",
            "sample_dependent_gates_wait_for_registered_minimum_sample": True,
            "drawdown_breach_fails_immediately": True,
            "unknown_regime_not_counted_as_distinct_market_regime": True,
            "thresholds_changed": False,
            "cherry_picking_allowed": False,
        },
        "safety": {
            **run.as_record()["safety"],
            "strategy_evidence": "INSUFFICIENT_EVIDENCE",
            "p11_unlocked": False,
            "pass_candidate_is_live_authorization": False,
            "trade_permission": False,
            "order_endpoint": False,
            "ai_direct_execution": False,
        },
    }))


def evaluate_forward_gate(store, snapshot, run, economics):
    """Reconcile accepted inputs and evaluate every P10-002 criterion exactly once."""
    try:
        if type(snapshot) is not ForwardIngestionSnapshot:
            raise ForwardGateError("Gate requires accepted ingestion snapshot evidence")
        if type(run) is not ForwardPaperRunResult:
            raise ForwardGateError("Gate requires accepted Paper run evidence")
        if type(economics) is not ForwardEconomicsReport:
            raise ForwardGateError("Gate requires accepted economics evidence")
        if run.ingestion_snapshot_sha256 != snapshot.snapshot_sha256:
            raise ForwardGateError("Paper run is bound to a different ingestion snapshot")
        if (
            run.window_sha256 != ForwardWindowSeal().window_sha256
            or run.gate_registry_sha256 != EconomicGateRegistry().registry_sha256
        ):
            raise ForwardGateError("Gate input identities differ from frozen registration")

        reproduced = calculate_forward_economics(store, snapshot, run)
        if reproduced.canonical_json != economics.canonical_json:
            raise ForwardGateError("Economics evidence differs from exact reconciliation")

        with localcontext() as arithmetic:
            arithmetic.prec = DECIMAL_PRECISION
            record = economics.as_record()
            regime = _regime_summary(store, snapshot, run, EconomicGateRegistry())
            return _assemble(snapshot, run, record, regime)
    except ForwardGateError:
        raise
    except (
        ForwardEconomicsError,
        ForwardPaperRunnerError,
        ForwardStoreError,
        RegimeError,
        DecimalException,
        ValueError,
        TypeError,
        KeyError,
        IndexError,
    ) as exc:
        raise ForwardGateError("Forward gate evidence failed closed") from exc
