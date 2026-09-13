import contextlib
import io
import unittest
from dataclasses import fields, replace
from decimal import localcontext
from unittest.mock import patch

from yatl.__main__ import main
from yatl.backtest import MarketSnapshot
from yatl.data import Candle, DATA_SOURCE, INTERVAL_MILLISECONDS
from yatl.risk import (
    CircuitAssessment,
    CircuitBreaker,
    CircuitBreakerError,
    CircuitDisposition,
    CircuitReason,
    ManagedPortfolioState,
    RiskRequest,
    assess_circuit_breakers,
)
from yatl.strategy import (
    DecisionReason,
    EvidenceLabel,
    LongSetup,
    StrategyAction,
    StrategyContext,
    StrategyDecision,
    StrategyIdentity,
)


DECISION = 1_699_999_200_000


def _candles(interval):
    duration = INTERVAL_MILLISECONDS[interval]
    opened = (DECISION // duration) * duration - duration
    return (Candle(
        DATA_SOURCE, "BTCUSDT", interval, opened, opened + duration - 1,
        "95", "105", "90", "100", "100", "10000", 20, True,
    ),)


def _state(**changes):
    values = {
        "symbol": "BTCUSDT",
        "sequence": 3,
        "decision_time_ms": DECISION,
        "session_start_time_ms": DECISION,
        "session_start_equity_quote": "10000",
        "equity_quote": "10000",
        "cash_quote": "10000",
        "position_quantity": "0",
        "mark_price": "100",
        "peak_equity_quote": "10000",
        "session_realized_pnl_quote": "0",
        "consecutive_losses": 0,
        "open_positions": 0,
        "gross_exposure_quote": "0",
        "previous_state_sha256": "0" * 64,
        "observation_sha256": "1" * 64,
    }
    values.update(changes)
    return ManagedPortfolioState(**values)


def _request(state, action=StrategyAction.ENTER_LONG):
    snapshot = MarketSnapshot(
        "BTCUSDT", DECISION, _candles("1h"), _candles("15m"), _candles("4h"),
    )
    context = StrategyContext(StrategyIdentity("RISK_FIXTURE", "1.0.0"), snapshot)
    setup = LongSetup("100", "95", "115") if action is StrategyAction.ENTER_LONG else None
    reason = {
        StrategyAction.ENTER_LONG: DecisionReason.TREND_PULLBACK_ENTRY,
        StrategyAction.EXIT_LONG: DecisionReason.STRATEGY_EXIT,
        StrategyAction.NO_TRADE: DecisionReason.SETUP_ABSENT,
    }[action]
    decision = StrategyDecision(context, action, reason, setup)
    return RiskRequest(
        decision,
        EvidenceLabel.QUALIFIED_FOR_P4_RESEARCH,
        state.to_risk_state(),
    )


def _assessment(state=None, action=StrategyAction.ENTER_LONG):
    state = _state() if state is None else state
    return assess_circuit_breakers(_request(state, action), state)


class CircuitBreakerTests(unittest.TestCase):
    def test_clear_entry_is_deterministic_and_bound_to_request_and_state(self):
        first = _assessment()
        replay = _assessment()
        self.assertIsInstance(first, CircuitAssessment)
        self.assertEqual(first.disposition, CircuitDisposition.CLEAR)
        self.assertEqual(first.reason, CircuitReason.WITHIN_LIMITS)
        self.assertEqual(first.triggered_breakers, ())
        self.assertEqual(first, replay)
        self.assertEqual(first.circuit_sha256, replay.circuit_sha256)
        self.assertEqual(len(first.request_sha256), 64)
        self.assertEqual(len(first.state_sha256), 64)

    def test_session_loss_triggers_at_exact_boundary_and_recovers_below_it(self):
        boundary = _assessment(_state(session_realized_pnl_quote="-200"))
        recovered = _assessment(_state(session_realized_pnl_quote="-199.999999"))
        self.assertEqual(boundary.disposition, CircuitDisposition.BLOCK_ENTRY)
        self.assertEqual(boundary.reason, CircuitReason.SESSION_LOSS_LIMIT)
        self.assertEqual(boundary.session_loss_quote, "200")
        self.assertEqual(boundary.session_loss_limit_quote, "200.00")
        self.assertEqual(recovered.disposition, CircuitDisposition.CLEAR)

    def test_new_session_state_clears_session_loss(self):
        prior = _assessment(_state(session_realized_pnl_quote="-250"))
        reset = _assessment(_state(
            session_start_equity_quote="9750",
            equity_quote="9750",
            cash_quote="9750",
            session_realized_pnl_quote="0",
        ))
        self.assertEqual(prior.disposition, CircuitDisposition.BLOCK_ENTRY)
        self.assertEqual(reset.disposition, CircuitDisposition.CLEAR)
        self.assertEqual(reset.session_loss_limit_quote, "195.00")

    def test_drawdown_triggers_at_exact_boundary_and_recovers_above_it(self):
        boundary = _assessment(_state(equity_quote="9000", cash_quote="9000"))
        recovered = _assessment(_state(
            equity_quote="9000.000001", cash_quote="9000.000001",
        ))
        self.assertEqual(boundary.disposition, CircuitDisposition.BLOCK_ENTRY)
        self.assertEqual(boundary.reason, CircuitReason.DRAWDOWN_LIMIT)
        self.assertEqual(boundary.drawdown_quote, "1000")
        self.assertEqual(boundary.drawdown_limit_quote, "1000.00")
        self.assertEqual(recovered.disposition, CircuitDisposition.CLEAR)

    def test_streak_triggers_at_three_and_win_state_recovers(self):
        boundary = _assessment(_state(consecutive_losses=3))
        recovered = _assessment(_state(consecutive_losses=0))
        self.assertEqual(boundary.reason, CircuitReason.CONSECUTIVE_LOSS_LIMIT)
        self.assertEqual(boundary.triggered_breakers, (
            CircuitBreaker.CONSECUTIVE_LOSS_LIMIT,
        ))
        self.assertEqual(recovered.disposition, CircuitDisposition.CLEAR)

    def test_multiple_breakers_have_stable_order(self):
        result = _assessment(_state(
            equity_quote="9000", cash_quote="9000",
            session_realized_pnl_quote="-200", consecutive_losses=3,
        ))
        self.assertEqual(result.reason, CircuitReason.MULTIPLE_LIMITS)
        self.assertEqual(result.triggered_breakers, (
            CircuitBreaker.SESSION_LOSS_LIMIT,
            CircuitBreaker.DRAWDOWN_LIMIT,
            CircuitBreaker.CONSECUTIVE_LOSS_LIMIT,
        ))

    def test_breakers_never_block_risk_reducing_exit(self):
        state = _state(
            equity_quote="9000", cash_quote="8900", position_quantity="1",
            gross_exposure_quote="100", open_positions=1,
            session_realized_pnl_quote="-200", consecutive_losses=3,
        )
        result = _assessment(state, StrategyAction.EXIT_LONG)
        self.assertEqual(
            result.disposition, CircuitDisposition.ALLOW_RISK_REDUCING_EXIT,
        )
        self.assertEqual(result.reason, CircuitReason.EXIT_REDUCES_RISK)
        self.assertEqual(len(result.triggered_breakers), 3)

    def test_no_trade_is_no_action_even_when_breakers_are_active(self):
        state = _state(session_realized_pnl_quote="-200")
        result = _assessment(state, StrategyAction.NO_TRADE)
        self.assertEqual(result.disposition, CircuitDisposition.NO_ACTION)
        self.assertEqual(result.reason, CircuitReason.NO_STRATEGY_ACTION)

    def test_request_and_managed_state_mismatch_fails_closed(self):
        state = _state()
        changed = _state(cash_quote="9999")
        with self.assertRaises(CircuitBreakerError):
            assess_circuit_breakers(_request(state), changed)

    def test_tampered_assessment_fails_closed(self):
        result = _assessment(_state(session_realized_pnl_quote="-200"))
        for change in (
            {"disposition": CircuitDisposition.CLEAR},
            {"reason": CircuitReason.WITHIN_LIMITS},
            {"triggered_breakers": ()},
            {"triggered_breakers": ("SESSION_LOSS_LIMIT",)},
            {"session_loss_quote": "199"},
            {"consecutive_loss_limit": 4},
        ):
            with self.subTest(change=change), self.assertRaises(CircuitBreakerError):
                replace(result, **change)

    def test_invalid_inputs_fail_closed(self):
        state = _state()
        request = _request(state)
        for args in ((None, state), (request, None), ("request", state)):
            with self.subTest(args=args), self.assertRaises(CircuitBreakerError):
                assess_circuit_breakers(*args)

    def test_decimal_result_is_independent_of_ambient_precision(self):
        state = _state(
            session_start_equity_quote="123456789.123456789",
            equity_quote="100000000.000000001",
            cash_quote="100000000.000000001",
            peak_equity_quote="123456789.123456789",
            session_realized_pnl_quote="-2469135.78246913578",
        )
        expected = _assessment(state)
        with localcontext() as context:
            context.prec = 6
            replay = _assessment(state)
        self.assertEqual(expected, replay)
        self.assertEqual(expected.session_loss_limit_quote, "2469135.78246913578")

    def test_contract_has_no_execution_credential_or_approval_fields(self):
        names = {item.name for item in fields(CircuitAssessment)}
        forbidden = {
            "order", "broker", "api_key", "api_secret", "endpoint",
            "withdrawal_address", "account_id", "approval", "approved_quantity",
        }
        self.assertTrue(names.isdisjoint(forbidden))

    @patch("sys.argv", ["yatl", "risk-circuit-check"])
    def test_cli_reports_boundary_block_and_recovery(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(), 0)
        text = output.getvalue()
        self.assertIn("P4 circuit breakers", text)
        self.assertIn("boundary=BLOCK_ENTRY/MULTIPLE_LIMITS", text)
        self.assertIn("recovered=CLEAR/WITHIN_LIMITS", text)
        self.assertIn("session_loss=200/200.00", text)
        self.assertIn("No approval", text)
        self.assertIn("No exchange order", text)


if __name__ == "__main__":
    unittest.main()
