import contextlib
import io
import unittest
from dataclasses import replace
from decimal import getcontext
from unittest.mock import patch

from yatl.__main__ import main
from yatl.risk import (
    CloseOutcome,
    PortfolioObservation,
    PortfolioStateTransition,
    RiskStateError,
    apply_portfolio_observation,
)


HOUR = 3_600_000
START = 1_699_999_200_000


def _observation(sequence, *, time=None, **changes):
    values = {
        "symbol": "BTCUSDT",
        "sequence": sequence,
        "decision_time_ms": START + sequence * HOUR if time is None else time,
        "equity_quote": "10000",
        "cash_quote": "10000",
        "position_quantity": "0",
        "mark_price": "100",
        "start_new_session": sequence == 0,
    }
    values.update(changes)
    return PortfolioObservation(**values)


def _initial():
    return apply_portfolio_observation(None, _observation(0)).current


class RiskStateTests(unittest.TestCase):
    def test_initial_state_is_canonical_deterministic_and_flat(self):
        first = _initial()
        second = _initial()
        self.assertEqual(first, second)
        self.assertEqual(first.state_sha256, second.state_sha256)
        self.assertEqual(len(first.state_sha256), 64)
        self.assertEqual(first.gross_exposure_quote, "0")
        self.assertEqual(first.session_start_equity_quote, "10000")

    def test_open_and_mark_update_exposure_and_equity_peak(self):
        initial = _initial()
        opened = apply_portfolio_observation(
            initial,
            _observation(1, cash_quote="9000", position_quantity="10"),
        ).current
        marked = apply_portfolio_observation(
            opened,
            _observation(2, equity_quote="10100", cash_quote="9000",
                         position_quantity="10", mark_price="110"),
        ).current
        self.assertEqual(opened.gross_exposure_quote, "1000")
        self.assertEqual(marked.gross_exposure_quote, "1100")
        self.assertEqual(marked.peak_equity_quote, "10100")
        self.assertEqual(marked.open_positions, 1)

    def test_loss_close_updates_session_pnl_and_consecutive_losses(self):
        initial = _initial()
        opened = apply_portfolio_observation(
            initial, _observation(1, cash_quote="9000", position_quantity="10"),
        ).current
        closed = apply_portfolio_observation(
            opened,
            _observation(
                2, equity_quote="9900", cash_quote="9900",
                realized_pnl_delta_quote="-100", close_outcome=CloseOutcome.LOSS,
            ),
        ).current
        self.assertEqual(closed.session_realized_pnl_quote, "-100")
        self.assertEqual(closed.consecutive_losses, 1)
        self.assertEqual(closed.open_positions, 0)

    def test_win_and_breakeven_reset_consecutive_losses(self):
        state = replace(_initial(), consecutive_losses=2)
        opened = apply_portfolio_observation(
            state, _observation(1, cash_quote="9000", position_quantity="10"),
        ).current
        won = apply_portfolio_observation(
            opened,
            _observation(
                2, equity_quote="10100", cash_quote="10100",
                realized_pnl_delta_quote="100", close_outcome=CloseOutcome.WIN,
            ),
        ).current
        self.assertEqual(won.consecutive_losses, 0)

        reopened = apply_portfolio_observation(
            won, _observation(3, cash_quote="9100", position_quantity="10"),
        ).current
        even = apply_portfolio_observation(
            reopened,
            _observation(4, equity_quote="10100", cash_quote="10100",
                         close_outcome=CloseOutcome.BREAKEVEN),
        ).current
        self.assertEqual(even.consecutive_losses, 0)

    def test_utc_session_reset_zeros_session_pnl_but_preserves_peak_and_losses(self):
        previous = replace(
            _initial(), decision_time_ms=1_699_999_200_000,
            peak_equity_quote="10200", session_realized_pnl_quote="-50",
            consecutive_losses=2,
        )
        midnight = 1_700_006_400_000
        reset = apply_portfolio_observation(
            previous,
            _observation(1, time=midnight, equity_quote="9950", cash_quote="9950",
                         start_new_session=True),
        ).current
        self.assertEqual(reset.session_start_time_ms, midnight)
        self.assertEqual(reset.session_start_equity_quote, "9950")
        self.assertEqual(reset.session_realized_pnl_quote, "0")
        self.assertEqual(reset.peak_equity_quote, "10200")
        self.assertEqual(reset.consecutive_losses, 2)

    def test_duplicate_missing_stale_and_wrong_symbol_fail_closed(self):
        initial = _initial()
        invalid = (
            _observation(0, time=START + HOUR, start_new_session=False),
            _observation(2, start_new_session=False),
            _observation(1, time=START, start_new_session=False),
            _observation(1, symbol="ETHUSDT", start_new_session=False),
        )
        for observation in invalid:
            with self.subTest(observation=observation), self.assertRaises(RiskStateError):
                apply_portfolio_observation(initial, observation)

    def test_close_and_session_semantics_are_strict(self):
        with self.assertRaises(RiskStateError):
            _observation(1, realized_pnl_delta_quote="-1",
                         close_outcome=CloseOutcome.WIN)
        with self.assertRaises(RiskStateError):
            apply_portfolio_observation(
                _initial(),
                _observation(1, realized_pnl_delta_quote="-1",
                             close_outcome=CloseOutcome.LOSS,
                             start_new_session=False),
            )
        with self.assertRaises(RiskStateError):
            apply_portfolio_observation(
                _initial(), _observation(1, start_new_session=True),
            )

    def test_open_position_cannot_change_or_disappear_silently(self):
        opened = apply_portfolio_observation(
            _initial(), _observation(1, cash_quote="9000", position_quantity="10"),
        ).current
        for quantity in ("9", "0"):
            with self.subTest(quantity=quantity), self.assertRaises(RiskStateError):
                apply_portfolio_observation(
                    opened,
                    _observation(2, cash_quote="9000", position_quantity=quantity),
                )

    def test_transition_rejects_tampered_current_state(self):
        initial = _initial()
        observation = _observation(1, cash_quote="9000", position_quantity="10")
        transition = apply_portfolio_observation(initial, observation)
        with self.assertRaises(RiskStateError):
            PortfolioStateTransition(
                initial, observation,
                replace(transition.current, peak_equity_quote="10001"),
            )

    def test_decimal_result_is_independent_of_ambient_precision(self):
        original = getcontext().prec
        try:
            getcontext().prec = 6
            low = apply_portfolio_observation(
                _initial(),
                _observation(1, cash_quote="1", position_quantity="123456789.123456789",
                             mark_price="987654321.987654321"),
            ).current
            getcontext().prec = 80
            high = apply_portfolio_observation(
                _initial(),
                _observation(1, cash_quote="1", position_quantity="123456789.123456789",
                             mark_price="987654321.987654321"),
            ).current
        finally:
            getcontext().prec = original
        self.assertEqual(low, high)
        self.assertEqual(
            low.gross_exposure_quote, "121932631356500531.347203169112635269",
        )

        loss_base = replace(
            _initial(), session_realized_pnl_quote="-123456789.123456789",
            position_quantity="1", open_positions=1, gross_exposure_quote="100",
        )
        loss_observation = _observation(
            1, equity_quote="9000", cash_quote="9000",
            realized_pnl_delta_quote="-0.000000001",
            close_outcome=CloseOutcome.LOSS,
        )
        try:
            getcontext().prec = 6
            low_pnl = apply_portfolio_observation(loss_base, loss_observation).current
            getcontext().prec = 80
            high_pnl = apply_portfolio_observation(loss_base, loss_observation).current
        finally:
            getcontext().prec = original
        self.assertEqual(low_pnl, high_pnl)
        self.assertEqual(low_pnl.session_realized_pnl_quote, "-123456789.123456790")

    def test_projection_to_p4_contract_preserves_managed_facts(self):
        managed = _initial()
        projected = managed.to_risk_state(kill_switch_active=False)
        self.assertEqual(projected.equity_quote, managed.equity_quote)
        self.assertEqual(projected.session_realized_pnl_quote, "0")
        self.assertEqual(projected.open_positions, 0)

    @patch("sys.argv", ["yatl", "risk-state-check"])
    def test_cli_reports_deterministic_loss_transition(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(), 0)
        text = output.getvalue()
        self.assertIn("P4 portfolio/session state", text)
        self.assertIn("session_pnl=-100", text)
        self.assertIn("consecutive_losses=1", text)
        self.assertIn("No exchange order", text)


if __name__ == "__main__":
    unittest.main()
