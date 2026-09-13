import contextlib
import io
import unittest
from dataclasses import fields, replace
from unittest.mock import patch

from yatl.__main__ import main
from yatl.backtest import MarketSnapshot
from yatl.data import Candle, DATA_SOURCE, INTERVAL_MILLISECONDS
from yatl.risk import (
    CircuitBreaker,
    KillSwitchError,
    KillSwitchEvent,
    KillSwitchEventType,
    KillSwitchMode,
    KillSwitchReason,
    KillSwitchState,
    KillSwitchTransition,
    ManagedPortfolioState,
    RiskDecision,
    RiskDisposition,
    RiskReason,
    RiskRequest,
    RiskSizingError,
    apply_kill_switch_event,
    assess_circuit_breakers,
    size_entry,
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


HOUR = 3_600_000
START = 1_699_999_200_000


def _candles(interval, decision):
    duration = INTERVAL_MILLISECONDS[interval]
    opened = (decision // duration) * duration - duration
    return (Candle(
        DATA_SOURCE, "BTCUSDT", interval, opened, opened + duration - 1,
        "95", "105", "90", "100", "100", "10000", 20, True,
    ),)


def _state(offset=0, **changes):
    decision = START + offset * HOUR
    values = {
        "symbol": "BTCUSDT",
        "sequence": offset,
        "decision_time_ms": decision,
        "session_start_time_ms": START,
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
        "previous_state_sha256": None if offset == 0 else "0" * 64,
        "observation_sha256": format(offset + 1, "x") * 64,
    }
    values.update(changes)
    return ManagedPortfolioState(**values)


def _request(state, action=StrategyAction.ENTER_LONG, *, kill_switch=False):
    decision_time = state.decision_time_ms
    snapshot = MarketSnapshot(
        "BTCUSDT", decision_time,
        _candles("1h", decision_time),
        _candles("15m", decision_time),
        _candles("4h", decision_time),
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
        state.to_risk_state(kill_switch_active=kill_switch),
    )


def _assessment(offset=0, **changes):
    state = _state(offset, **changes)
    return assess_circuit_breakers(_request(state), state)


def _startup():
    event = KillSwitchEvent(0, START - 1, KillSwitchEventType.STARTUP)
    return apply_kill_switch_event(None, event).current


def _reset(previous, offset=0):
    evidence = _assessment(offset)
    event = KillSwitchEvent(
        previous.sequence + 1,
        START + offset * HOUR,
        KillSwitchEventType.MANUAL_RESET,
        evidence,
        True,
    )
    return apply_kill_switch_event(previous, event).current


class KillSwitchTests(unittest.TestCase):
    def test_startup_is_deterministic_triggered_and_fail_closed(self):
        first = _startup()
        replay = _startup()
        self.assertEqual(first, replay)
        self.assertEqual(first.mode, KillSwitchMode.TRIGGERED)
        self.assertEqual(first.reason, KillSwitchReason.FAIL_CLOSED_STARTUP)
        self.assertTrue(first.active)
        self.assertEqual(first.triggered_breakers, ())
        self.assertEqual(len(first.state_sha256), 64)

    def test_machine_cannot_bypass_or_repeat_startup(self):
        clear = _assessment()
        invalid_first = KillSwitchEvent(
            1, START, KillSwitchEventType.MANUAL_RESET, clear, True,
        )
        with self.assertRaises(KillSwitchError):
            apply_kill_switch_event(None, invalid_first)
        with self.assertRaises(KillSwitchError):
            apply_kill_switch_event(
                _startup(), KillSwitchEvent(0, START, KillSwitchEventType.STARTUP),
            )

    def test_explicit_manual_reset_with_clear_evidence_unlocks_startup(self):
        reset = _reset(_startup())
        self.assertEqual(reset.mode, KillSwitchMode.INACTIVE)
        self.assertEqual(reset.reason, KillSwitchReason.MANUAL_RESET)
        self.assertFalse(reset.active)
        self.assertEqual(reset.last_circuit_sha256, _assessment().circuit_sha256)

    def test_circuit_trigger_latches_and_preserves_stable_reasons(self):
        inactive = _reset(_startup())
        session = _assessment(1, session_realized_pnl_quote="-200")
        first = apply_kill_switch_event(
            inactive,
            KillSwitchEvent(
                2, START + HOUR, KillSwitchEventType.CIRCUIT_OBSERVATION,
                session,
            ),
        ).current
        combined = _assessment(
            2, equity_quote="9000", cash_quote="9000", consecutive_losses=3,
        )
        second = apply_kill_switch_event(
            first,
            KillSwitchEvent(
                3, START + 2 * HOUR, KillSwitchEventType.CIRCUIT_OBSERVATION,
                combined,
            ),
        ).current
        self.assertEqual(second.mode, KillSwitchMode.TRIGGERED)
        self.assertEqual(second.reason, KillSwitchReason.CIRCUIT_BREAKER_TRIGGERED)
        self.assertEqual(second.triggered_breakers, (
            CircuitBreaker.SESSION_LOSS_LIMIT,
            CircuitBreaker.DRAWDOWN_LIMIT,
            CircuitBreaker.CONSECUTIVE_LOSS_LIMIT,
        ))

    def test_clear_observation_never_resets_a_triggered_switch(self):
        inactive = _reset(_startup())
        boundary = _assessment(1, consecutive_losses=3)
        triggered = apply_kill_switch_event(
            inactive,
            KillSwitchEvent(
                2, START + HOUR, KillSwitchEventType.CIRCUIT_OBSERVATION,
                boundary,
            ),
        ).current
        clear = _assessment(2)
        latched = apply_kill_switch_event(
            triggered,
            KillSwitchEvent(
                3, START + 2 * HOUR, KillSwitchEventType.CIRCUIT_OBSERVATION,
                clear,
            ),
        ).current
        self.assertTrue(latched.active)
        self.assertEqual(latched.reason, KillSwitchReason.LATCHED_UNTIL_MANUAL_RESET)
        self.assertEqual(latched.triggered_breakers, (
            CircuitBreaker.CONSECUTIVE_LOSS_LIMIT,
        ))

    def test_manual_reset_requires_triggered_state_and_new_clear_evidence(self):
        inactive = _reset(_startup())
        with self.assertRaises(KillSwitchError):
            _reset(inactive, 1)

        boundary = _assessment(1, session_realized_pnl_quote="-200")
        triggered = apply_kill_switch_event(
            inactive,
            KillSwitchEvent(
                2, START + HOUR, KillSwitchEventType.CIRCUIT_OBSERVATION,
                boundary,
            ),
        ).current
        with self.assertRaises(KillSwitchError):
            apply_kill_switch_event(
                triggered,
                KillSwitchEvent(
                    3, START + 2 * HOUR, KillSwitchEventType.MANUAL_RESET,
                    boundary, True,
                ),
            )
        reset = _reset(triggered, 2)
        self.assertFalse(reset.active)
        self.assertEqual(reset.triggered_breakers, ())

    def test_sequence_event_time_and_circuit_time_are_strictly_monotonic(self):
        inactive = _reset(_startup())
        clear = _assessment(1)
        invalid = (
            KillSwitchEvent(
                1, START + HOUR, KillSwitchEventType.CIRCUIT_OBSERVATION, clear,
            ),
            KillSwitchEvent(
                3, START + HOUR, KillSwitchEventType.CIRCUIT_OBSERVATION, clear,
            ),
            KillSwitchEvent(
                2, START, KillSwitchEventType.CIRCUIT_OBSERVATION, _assessment(),
            ),
        )
        for event in invalid:
            with self.subTest(event=event), self.assertRaises(KillSwitchError):
                apply_kill_switch_event(inactive, event)

        observed = apply_kill_switch_event(
            inactive,
            KillSwitchEvent(
                2, START + HOUR, KillSwitchEventType.CIRCUIT_OBSERVATION, clear,
            ),
        ).current
        with self.assertRaises(KillSwitchError):
            apply_kill_switch_event(
                observed,
                KillSwitchEvent(
                    3, START + 2 * HOUR,
                    KillSwitchEventType.CIRCUIT_OBSERVATION, clear,
                ),
            )

    def test_replay_is_deterministic_and_hash_chained(self):
        events = (
            KillSwitchEvent(0, START - 1, KillSwitchEventType.STARTUP),
            KillSwitchEvent(
                1, START, KillSwitchEventType.MANUAL_RESET, _assessment(), True,
            ),
            KillSwitchEvent(
                2, START + HOUR, KillSwitchEventType.CIRCUIT_OBSERVATION,
                _assessment(1, consecutive_losses=3),
            ),
        )

        def replay():
            state = None
            states = []
            for event in events:
                state = apply_kill_switch_event(state, event).current
                states.append(state)
            return tuple(states)

        first = replay()
        second = replay()
        self.assertEqual(first, second)
        self.assertEqual(first[-1].previous_state_sha256, first[-2].state_sha256)
        self.assertNotEqual(first[-1].state_sha256, first[-2].state_sha256)

    def test_tampered_state_transition_and_event_fail_closed(self):
        startup_event = KillSwitchEvent(0, START - 1, KillSwitchEventType.STARTUP)
        transition = apply_kill_switch_event(None, startup_event)
        with self.assertRaises(KillSwitchError):
            KillSwitchTransition(
                None, startup_event,
                replace(transition.current, event_time_ms=START - 2),
            )
        with self.assertRaises(KillSwitchError):
            replace(transition.current, mode=KillSwitchMode.INACTIVE)
        with self.assertRaises(KillSwitchError):
            replace(transition.current, triggered_breakers=("SESSION_LOSS_LIMIT",))
        reset = _reset(transition.current)
        with self.assertRaises(KillSwitchError):
            replace(reset, last_circuit_time_ms=None, last_circuit_sha256=None)
        with self.assertRaises(KillSwitchError):
            KillSwitchEvent(
                1, START, KillSwitchEventType.MANUAL_RESET, _assessment(), False,
            )

    def test_kill_switch_blocks_entry_but_not_risk_reducing_exit(self):
        switch = _startup()
        flat = _state()
        entry = _request(flat, kill_switch=switch.active)
        with self.assertRaises(RiskSizingError):
            size_entry(entry)

        positioned = _state(
            position_quantity="1", open_positions=1,
            gross_exposure_quote="100", cash_quote="9900",
        )
        exit_request = _request(
            positioned, StrategyAction.EXIT_LONG, kill_switch=switch.active,
        )
        decision = RiskDecision(
            exit_request, RiskDisposition.APPROVE_PAPER,
            RiskReason.EXIT_REDUCES_RISK, "1",
        )
        self.assertEqual(decision.reason, RiskReason.EXIT_REDUCES_RISK)

    def test_invalid_inputs_fail_closed(self):
        event = KillSwitchEvent(0, START - 1, KillSwitchEventType.STARTUP)
        for previous, candidate in ((None, None), (object(), event), (_startup(), object())):
            with self.subTest(candidate=candidate), self.assertRaises(KillSwitchError):
                apply_kill_switch_event(previous, candidate)

    def test_contracts_have_no_execution_credential_or_operator_identity_fields(self):
        names = {
            item.name
            for contract in (KillSwitchEvent, KillSwitchState)
            for item in fields(contract)
        }
        forbidden = {
            "order", "broker", "api_key", "api_secret", "endpoint",
            "withdrawal_address", "account_id", "operator_id",
            "approved_quantity",
        }
        self.assertTrue(names.isdisjoint(forbidden))

    @patch("sys.argv", ["yatl", "risk-kill-switch-check"])
    def test_cli_reports_fail_closed_latch_and_manual_reset(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(), 0)
        text = output.getvalue()
        self.assertIn("P4 Kill Switch state machine", text)
        self.assertIn("TRIGGERED/INACTIVE/TRIGGERED/TRIGGERED/INACTIVE", text)
        self.assertIn("startup=FAIL_CLOSED_STARTUP", text)
        self.assertIn("clear_observation=LATCHED_UNTIL_MANUAL_RESET", text)
        self.assertIn("Manual reset only", text)
        self.assertIn("No exchange order", text)


if __name__ == "__main__":
    unittest.main()
