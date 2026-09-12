import contextlib
import io
import unittest
from dataclasses import fields, replace
from unittest.mock import patch

from yatl.__main__ import main
from yatl.backtest import MarketSnapshot
from yatl.data import Candle, DATA_SOURCE, INTERVAL_MILLISECONDS
from yatl.risk import (
    PortfolioRiskState,
    RiskContractError,
    RiskDecision,
    RiskDisposition,
    RiskPolicy,
    RiskReason,
    RiskRequest,
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
    return (Candle(DATA_SOURCE, "BTCUSDT", interval, opened,
                   opened + duration - 1, "100", "110", "90", "105",
                   "10", "1000", 20, True),)


def _strategy_decision(action=StrategyAction.ENTER_LONG):
    snapshot = MarketSnapshot("BTCUSDT", DECISION, _candles("1h"),
                              _candles("15m"), _candles("4h"))
    context = StrategyContext(StrategyIdentity("TREND_PULLBACK", "1.0.0"), snapshot)
    if action is StrategyAction.ENTER_LONG:
        return StrategyDecision(context, action, DecisionReason.TREND_PULLBACK_ENTRY,
                                LongSetup("105", "100", "115"))
    if action is StrategyAction.EXIT_LONG:
        return StrategyDecision(context, action, DecisionReason.STRATEGY_EXIT)
    return StrategyDecision(context, action, DecisionReason.SETUP_ABSENT)


def _state(*, positioned=False, **changes):
    values = {
        "symbol": "BTCUSDT",
        "decision_time_ms": DECISION,
        "equity_quote": "10000",
        "cash_quote": "10000" if not positioned else "9000",
        "position_quantity": "0" if not positioned else "0.01",
        "mark_price": "105",
        "peak_equity_quote": "10100",
        "open_positions": 0 if not positioned else 1,
    }
    values.update(changes)
    return PortfolioRiskState(**values)


class RiskContractTests(unittest.TestCase):
    def test_policy_is_frozen_and_safety_tampering_fails_closed(self):
        policy = RiskPolicy()
        self.assertEqual(policy.risk_per_trade_fraction, "0.01")
        for change in (
            {"risk_per_trade_fraction": "0.02"},
            {"live_master_lock": "ON"},
            {"paper_only": False},
            {"allow_leverage": True},
            {"allow_order_endpoint": True},
            {"allow_ai_direct_execution": True},
        ):
            with self.subTest(change=change), self.assertRaises(RiskContractError):
                replace(policy, **change)

    def test_portfolio_state_requires_exact_consistent_values(self):
        self.assertEqual(_state().equity_quote, "10000")
        invalid = (
            {"equity_quote": 10000.0},
            {"equity_quote": "1e4"},
            {"peak_equity_quote": "9999"},
            {"position_quantity": "1", "open_positions": 0},
            {"decision_time_ms": DECISION + 1},
            {"symbol": "BNBUSDT"},
        )
        for change in invalid:
            with self.subTest(change=change), self.assertRaises(RiskContractError):
                _state(**change)

    def test_request_is_bound_to_strategy_state_policy_and_evidence(self):
        first = RiskRequest(_strategy_decision(), EvidenceLabel.INSUFFICIENT_EVIDENCE,
                            _state())
        replay = RiskRequest(_strategy_decision(), EvidenceLabel.INSUFFICIENT_EVIDENCE,
                             _state())
        self.assertEqual(first.request_sha256, replay.request_sha256)
        self.assertEqual(len(first.request_sha256), 64)
        changed = replace(first, portfolio=replace(first.portfolio, cash_quote="9999"))
        self.assertNotEqual(first.request_sha256, changed.request_sha256)

    def test_request_rejects_mismatch_and_overlapping_entry(self):
        request = _strategy_decision()
        with self.assertRaises(RiskContractError):
            RiskRequest(request, EvidenceLabel.INSUFFICIENT_EVIDENCE,
                        _state(symbol="ETHUSDT"))
        with self.assertRaises(RiskContractError):
            RiskRequest(request, EvidenceLabel.INSUFFICIENT_EVIDENCE,
                        _state(positioned=True))

    def test_insufficient_candidate_cannot_be_approved(self):
        request = RiskRequest(_strategy_decision(), EvidenceLabel.INSUFFICIENT_EVIDENCE,
                              _state())
        rejected = RiskDecision(request, RiskDisposition.REJECT,
                                RiskReason.EVIDENCE_NOT_QUALIFIED)
        self.assertIsNone(rejected.approved_quantity)
        with self.assertRaises(RiskContractError):
            RiskDecision(request, RiskDisposition.APPROVE_PAPER,
                         RiskReason.RISK_CHECKS_PASSED, "0.01")

    def test_qualified_entry_contract_is_still_paper_only(self):
        request = RiskRequest(_strategy_decision(),
                              EvidenceLabel.QUALIFIED_FOR_P4_RESEARCH, _state())
        approved = RiskDecision(request, RiskDisposition.APPROVE_PAPER,
                                RiskReason.RISK_CHECKS_PASSED, "0.01")
        self.assertEqual(approved.approved_quantity, "0.01")
        self.assertTrue(approved.request.policy.paper_only)

    def test_kill_switch_blocks_entry_but_never_risk_reducing_exit(self):
        entry = RiskRequest(_strategy_decision(),
                            EvidenceLabel.QUALIFIED_FOR_P4_RESEARCH,
                            _state(kill_switch_active=True))
        with self.assertRaises(RiskContractError):
            RiskDecision(entry, RiskDisposition.APPROVE_PAPER,
                         RiskReason.RISK_CHECKS_PASSED, "0.01")
        exit_request = RiskRequest(_strategy_decision(StrategyAction.EXIT_LONG),
                                   EvidenceLabel.INSUFFICIENT_EVIDENCE,
                                   _state(positioned=True, kill_switch_active=True))
        approved = RiskDecision(exit_request, RiskDisposition.APPROVE_PAPER,
                                RiskReason.EXIT_REDUCES_RISK, "0.01")
        self.assertEqual(approved.approved_quantity, "0.01")

    def test_no_trade_maps_only_to_no_action(self):
        request = RiskRequest(_strategy_decision(StrategyAction.NO_TRADE),
                              EvidenceLabel.INSUFFICIENT_EVIDENCE, _state())
        result = RiskDecision(request, RiskDisposition.NO_ACTION,
                              RiskReason.NO_STRATEGY_ACTION)
        self.assertEqual(result.disposition, RiskDisposition.NO_ACTION)
        with self.assertRaises(RiskContractError):
            RiskDecision(request, RiskDisposition.REJECT,
                         RiskReason.EVIDENCE_NOT_QUALIFIED)

    def test_contract_has_no_execution_or_credential_fields(self):
        names = {
            item.name
            for contract in (RiskPolicy, PortfolioRiskState, RiskRequest, RiskDecision)
            for item in fields(contract)
        }
        forbidden = {"order", "broker", "api_key", "api_secret", "endpoint",
                     "withdrawal_address", "account_id"}
        self.assertTrue(names.isdisjoint(forbidden))

    @patch("sys.argv", ["yatl", "risk-contract-check"])
    def test_cli_reports_fail_closed_paper_boundary(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(), 0)
        text = output.getvalue()
        self.assertIn("P4 risk contract", text)
        self.assertIn("EVIDENCE_NOT_QUALIFIED", text)
        self.assertIn("exit_under_kill_switch=APPROVE_PAPER", text)
        self.assertIn("No exchange order", text)


if __name__ == "__main__":
    unittest.main()
