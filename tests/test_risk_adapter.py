import contextlib
import io
import unittest
from dataclasses import fields, replace
from decimal import Decimal, localcontext
from unittest.mock import patch

from yatl.__main__ import main
from yatl.backtest import DecisionEvent, IntentAction, MarketSnapshot
from yatl.data import Candle, DATA_SOURCE, INTERVAL_MILLISECONDS
from yatl.risk import (
    KillSwitchEvent,
    KillSwitchEventType,
    RiskAdapterError,
    RiskAdapterOutcome,
    RiskAuthorization,
    RiskDecision,
    RiskDisposition,
    RiskManagedPaperAdapter,
    RiskReason,
    RiskRequest,
    apply_kill_switch_event,
    assess_circuit_breakers,
    assess_entry_limits,
    assess_protective_entry,
    authorize_paper_request,
    size_entry,
)
from yatl.risk.state import ManagedPortfolioState
from yatl.strategy import (
    DecisionReason,
    EvidenceLabel,
    LongSetup,
    StrategyAction,
    StrategyContext,
    StrategyDecision,
    TREND_PULLBACK_IDENTITY,
)


HOUR = 3_600_000
START = 1_699_999_200_000


def _candle(interval, opened, *, price="100", low="99", high="106", volume="100"):
    duration = INTERVAL_MILLISECONDS[interval]
    return Candle(
        DATA_SOURCE, "BTCUSDT", interval, opened, opened + duration - 1,
        price, high, low, price, volume, "10000", 20, True,
    )


def _event(sequence, offset=None):
    offset = sequence if offset is None else offset
    decision = START + offset * HOUR

    def history(interval):
        duration = INTERVAL_MILLISECONDS[interval]
        opened = (decision // duration) * duration - duration
        return (_candle(interval, opened),)

    snapshot = MarketSnapshot(
        "BTCUSDT", decision, history("1h"), history("15m"), history("4h"),
    )
    return DecisionEvent(sequence, decision, decision, snapshot)


def _fill_bar(event, **changes):
    values = {"price": "100", "low": "99", "high": "106", "volume": "100"}
    values.update(changes)
    return _candle("1h", event.decision_time_ms, **values)


def _strategy(event, action=StrategyAction.ENTER_LONG, *, target="115",
              holding=False):
    context = StrategyContext(TREND_PULLBACK_IDENTITY, event.snapshot)
    setup = LongSetup("100", "95", target) if action is StrategyAction.ENTER_LONG else None
    reason = {
        StrategyAction.ENTER_LONG: DecisionReason.TREND_PULLBACK_ENTRY,
        StrategyAction.EXIT_LONG: DecisionReason.STRATEGY_EXIT,
        StrategyAction.NO_TRADE: (
            DecisionReason.HOLD_POSITION if holding else DecisionReason.SETUP_ABSENT
        ),
    }[action]
    return StrategyDecision(context, action, reason, setup)


def _state(event, *, quantity="0", equity="10000", cash=None,
           session_pnl="0", losses=0, peak="10000"):
    cash = equity if cash is None else cash
    exposure = Decimal(quantity) * Decimal("100")
    return ManagedPortfolioState(
        symbol="BTCUSDT",
        sequence=(event.decision_time_ms - START) // HOUR,
        decision_time_ms=event.decision_time_ms,
        session_start_time_ms=START,
        session_start_equity_quote="10000",
        equity_quote=equity,
        cash_quote=cash,
        position_quantity=quantity,
        mark_price="100",
        peak_equity_quote=peak,
        session_realized_pnl_quote=session_pnl,
        consecutive_losses=losses,
        open_positions=0 if Decimal(quantity) == 0 else 1,
        gross_exposure_quote=format(exposure, "f"),
        previous_state_sha256=(
            None if event.decision_time_ms == START else "0" * 64
        ),
        observation_sha256=(
            format((event.decision_time_ms - START) // HOUR + 1, "x") * 64
        ),
    )


def _request(event, state, *, action=StrategyAction.ENTER_LONG,
             evidence=EvidenceLabel.QUALIFIED_FOR_P4_RESEARCH,
             kill_switch=False, target="115", holding=False):
    return RiskRequest(
        _strategy(event, action, target=target, holding=holding),
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


def _entry_authorization(*, evidence=EvidenceLabel.QUALIFIED_FOR_P4_RESEARCH,
                         target="115"):
    event = _event(0)
    state = _state(event)
    request = _request(event, state, evidence=evidence, target=target)
    circuit = assess_circuit_breakers(request, state)
    switch = _inactive_switch(circuit)
    protective = None
    if evidence is EvidenceLabel.QUALIFIED_FOR_P4_RESEARCH:
        protective = assess_protective_entry(
            assess_entry_limits(size_entry(request)),
        )
    return event, authorize_paper_request(
        request, state, switch, circuit, protective,
    )


class RiskAdapterTests(unittest.TestCase):
    def test_complete_p4_evidence_approves_exact_quantity(self):
        _, authorization = _entry_authorization()
        self.assertIsInstance(authorization, RiskAuthorization)
        self.assertEqual(
            authorization.decision.disposition, RiskDisposition.APPROVE_PAPER,
        )
        self.assertEqual(
            authorization.decision.approved_quantity,
            authorization.protective_assessment.quantity,
        )
        self.assertEqual(len(authorization.authorization_sha256), 64)

    def test_only_exact_approved_quantity_reaches_p2_entry(self):
        event, authorization = _entry_authorization()
        adapter = RiskManagedPaperAdapter(TREND_PULLBACK_IDENTITY, "BTCUSDT")
        step = adapter.process(event, authorization, _fill_bar(event))
        quantity = authorization.decision.approved_quantity
        self.assertEqual(step.outcome, RiskAdapterOutcome.ENTRY_APPROVED)
        self.assertEqual(step.intent.action, IntentAction.ENTER_LONG)
        self.assertEqual(step.intent.quantity, quantity)
        self.assertEqual(step.fills[0].quantity, quantity)
        self.assertTrue(adapter.has_position)
        self.assertEqual(adapter.active_quantity, quantity)

    def test_insufficient_evidence_becomes_hold_without_fill(self):
        event, authorization = _entry_authorization(
            evidence=EvidenceLabel.INSUFFICIENT_EVIDENCE,
        )
        self.assertEqual(
            authorization.decision.reason, RiskReason.EVIDENCE_NOT_QUALIFIED,
        )
        adapter = RiskManagedPaperAdapter(TREND_PULLBACK_IDENTITY, "BTCUSDT")
        step = adapter.process(event, authorization, _fill_bar(event))
        self.assertEqual(step.outcome, RiskAdapterOutcome.ENTRY_BLOCKED)
        self.assertEqual(step.intent.action, IntentAction.HOLD)
        self.assertEqual(step.fills, ())
        self.assertFalse(adapter.has_position)

    def test_protective_rejection_cannot_reach_p2_entry(self):
        event, authorization = _entry_authorization(target="100.1")
        self.assertEqual(
            authorization.decision.reason, RiskReason.PENDING_RISK_EVALUATION,
        )
        adapter = RiskManagedPaperAdapter(TREND_PULLBACK_IDENTITY, "BTCUSDT")
        step = adapter.process(event, authorization, _fill_bar(event))
        self.assertEqual(step.outcome, RiskAdapterOutcome.ENTRY_BLOCKED)
        self.assertEqual(step.fills, ())

    def test_active_kill_switch_rejects_qualified_entry(self):
        clear_event, clear_authorization = _entry_authorization()
        inactive = clear_authorization.kill_switch_state
        event = _event(0, 1)
        state = _state(
            event, equity="9800", cash="9800", session_pnl="-200", losses=3,
        )
        request = _request(event, state, kill_switch=True)
        circuit = assess_circuit_breakers(request, state)
        active = apply_kill_switch_event(
            inactive,
            KillSwitchEvent(
                2, event.decision_time_ms,
                KillSwitchEventType.CIRCUIT_OBSERVATION, circuit,
            ),
        ).current
        authorization = authorize_paper_request(
            request, state, active, circuit,
        )
        self.assertEqual(
            authorization.decision.reason, RiskReason.KILL_SWITCH_ACTIVE,
        )
        adapter = RiskManagedPaperAdapter(TREND_PULLBACK_IDENTITY, "BTCUSDT")
        step = adapter.process(event, authorization, _fill_bar(event))
        self.assertEqual(step.outcome, RiskAdapterOutcome.ENTRY_BLOCKED)
        self.assertEqual(step.fills, ())

    def test_entry_requires_latest_circuit_consumed_by_switch(self):
        _, old = _entry_authorization()
        event = _event(0, 1)
        state = _state(event)
        request = _request(event, state)
        circuit = assess_circuit_breakers(request, state)
        with self.assertRaises(RiskAdapterError):
            authorize_paper_request(
                request, state, old.kill_switch_state, circuit,
                assess_protective_entry(assess_entry_limits(size_entry(request))),
            )

    def test_tampered_or_mismatched_authorization_fails_closed(self):
        _, authorization = _entry_authorization()
        altered = RiskDecision(
            authorization.request,
            RiskDisposition.APPROVE_PAPER,
            RiskReason.RISK_CHECKS_PASSED,
            "1",
        )
        with self.assertRaises(RiskAdapterError):
            replace(authorization, decision=altered)
        with self.assertRaises(RiskAdapterError):
            authorize_paper_request(
                authorization.request,
                replace(authorization.managed_state, cash_quote="9999"),
                authorization.kill_switch_state,
                authorization.circuit_assessment,
                authorization.protective_assessment,
            )

    def test_raw_risk_decision_or_strategy_decision_cannot_enter_adapter(self):
        event, authorization = _entry_authorization()
        adapter = RiskManagedPaperAdapter(TREND_PULLBACK_IDENTITY, "BTCUSDT")
        for invalid in (authorization.decision, authorization.request.strategy_decision):
            with self.subTest(invalid=invalid), self.assertRaises(RiskAdapterError):
                adapter.process(event, invalid, _fill_bar(event))
        self.assertFalse(adapter.has_position)

    def test_exit_remains_authorized_under_triggered_kill_switch(self):
        entry_event, entry_auth = _entry_authorization()
        adapter = RiskManagedPaperAdapter(TREND_PULLBACK_IDENTITY, "BTCUSDT")
        adapter.process(entry_event, entry_auth, _fill_bar(entry_event))
        quantity = entry_auth.decision.approved_quantity

        exit_event = _event(1)
        state = _state(
            exit_event, quantity=quantity, equity="9800", cash="8800",
            session_pnl="-200", losses=3,
        )
        request = _request(
            exit_event, state, action=StrategyAction.EXIT_LONG, kill_switch=True,
        )
        circuit = assess_circuit_breakers(request, state)
        active = apply_kill_switch_event(
            entry_auth.kill_switch_state,
            KillSwitchEvent(
                2, exit_event.decision_time_ms,
                KillSwitchEventType.CIRCUIT_OBSERVATION, circuit,
            ),
        ).current
        authorization = authorize_paper_request(
            request, state, active, circuit,
        )
        step = adapter.process(
            exit_event, authorization,
            _fill_bar(exit_event, price="101", low="100", high="102"),
        )
        self.assertTrue(active.active)
        self.assertEqual(step.outcome, RiskAdapterOutcome.EXIT_APPROVED)
        self.assertEqual(step.fills[0].quantity, quantity)
        self.assertFalse(adapter.has_position)

    def test_protective_exit_remains_active_during_kill_switch_hold(self):
        entry_event, entry_auth = _entry_authorization()
        adapter = RiskManagedPaperAdapter(TREND_PULLBACK_IDENTITY, "BTCUSDT")
        adapter.process(entry_event, entry_auth, _fill_bar(entry_event))
        quantity = entry_auth.decision.approved_quantity

        hold_event = _event(1)
        state = _state(
            hold_event, quantity=quantity, equity="9800", cash="8800",
            session_pnl="-200", losses=3,
        )
        request = _request(
            hold_event, state, action=StrategyAction.NO_TRADE,
            kill_switch=True, holding=True,
        )
        circuit = assess_circuit_breakers(request, state)
        active = apply_kill_switch_event(
            entry_auth.kill_switch_state,
            KillSwitchEvent(
                2, hold_event.decision_time_ms,
                KillSwitchEventType.CIRCUIT_OBSERVATION, circuit,
            ),
        ).current
        authorization = authorize_paper_request(
            request, state, active, circuit,
        )
        step = adapter.process(
            hold_event, authorization,
            _fill_bar(hold_event, price="100", low="94", high="101"),
        )
        self.assertTrue(active.active)
        self.assertEqual(step.outcome, RiskAdapterOutcome.NO_ACTION)
        self.assertEqual(step.fills[0].action, IntentAction.EXIT_LONG)
        self.assertFalse(adapter.has_position)

    def test_p2_rejection_is_atomic_and_event_can_be_retried(self):
        event, authorization = _entry_authorization()
        adapter = RiskManagedPaperAdapter(TREND_PULLBACK_IDENTITY, "BTCUSDT")
        with self.assertRaises(RiskAdapterError):
            adapter.process(
                event, authorization,
                _fill_bar(event, price="120", low="119", high="121"),
            )
        self.assertFalse(adapter.has_position)
        accepted = adapter.process(event, authorization, _fill_bar(event))
        self.assertEqual(accepted.outcome, RiskAdapterOutcome.ENTRY_APPROVED)

    def test_flat_no_trade_is_atomic_no_action(self):
        event = _event(0)
        state = _state(event)
        request = _request(event, state, action=StrategyAction.NO_TRADE)
        circuit = assess_circuit_breakers(request, state)
        switch = _inactive_switch(circuit)
        authorization = authorize_paper_request(request, state, switch, circuit)
        adapter = RiskManagedPaperAdapter(TREND_PULLBACK_IDENTITY, "BTCUSDT")
        step = adapter.process(event, authorization, _fill_bar(event))
        self.assertEqual(step.outcome, RiskAdapterOutcome.NO_ACTION)
        self.assertEqual(step.fills, ())

    def test_duplicate_and_wrong_event_identity_fail_without_state_change(self):
        event, authorization = _entry_authorization(
            evidence=EvidenceLabel.INSUFFICIENT_EVIDENCE,
        )
        adapter = RiskManagedPaperAdapter(TREND_PULLBACK_IDENTITY, "BTCUSDT")
        adapter.process(event, authorization, _fill_bar(event))
        with self.assertRaises(RiskAdapterError):
            adapter.process(event, authorization, _fill_bar(event))
        self.assertFalse(adapter.has_position)

    def test_replay_and_authorization_hash_ignore_ambient_decimal_precision(self):
        def replay():
            event, authorization = _entry_authorization()
            adapter = RiskManagedPaperAdapter(TREND_PULLBACK_IDENTITY, "BTCUSDT")
            return authorization, adapter.process(
                event, authorization, _fill_bar(event),
            )

        expected = replay()
        with localcontext() as context:
            context.prec = 6
            actual = replay()
        self.assertEqual(expected, actual)
        self.assertEqual(
            expected[0].authorization_sha256, actual[0].authorization_sha256,
        )

    def test_contracts_have_no_credential_network_or_exchange_order_fields(self):
        names = {
            item.name
            for contract in (RiskAuthorization,)
            for item in fields(contract)
        }
        forbidden = {
            "api_key", "api_secret", "endpoint", "broker", "account_id",
            "withdrawal_address", "exchange_order", "operator_id",
        }
        self.assertTrue(names.isdisjoint(forbidden))

    @patch("sys.argv", ["yatl", "risk-adapter-check"])
    def test_cli_reports_exact_entry_block_and_safe_exit(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(), 0)
        text = output.getvalue()
        self.assertIn("P4-authorized P2 adapter", text)
        self.assertIn("entry=ENTRY_APPROVED", text)
        self.assertIn("blocked=ENTRY_BLOCKED", text)
        self.assertIn("exit_under_kill_switch=EXIT_APPROVED", text)
        self.assertIn("No exchange order", text)


if __name__ == "__main__":
    unittest.main()
