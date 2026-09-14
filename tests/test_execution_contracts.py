import contextlib
import io
import unittest
from dataclasses import fields, replace
from decimal import Decimal
from unittest.mock import patch

from yatl.__main__ import main
from yatl.backtest import IntentAction, MarketSnapshot
from yatl.data import Candle, DATA_SOURCE, INTERVAL_MILLISECONDS
from yatl.execution import (
    ExecutionContractError,
    ExecutionDisposition,
    ExecutionReason,
    LocalPaperExecutionDecision,
    LocalPaperExecutionPolicy,
    RecoveryReadiness,
    RecoveryReason,
    RecoveryStatus,
    assess_local_paper_authorization,
)
from yatl.risk import (
    KillSwitchEvent,
    KillSwitchEventType,
    ManagedPortfolioState,
    RiskAdapterError,
    RiskDecision,
    RiskDisposition,
    RiskReason,
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


START = 1_699_999_200_000
HOUR = 3_600_000


def _candle(interval, decision_time=START):
    duration = INTERVAL_MILLISECONDS[interval]
    opened = (decision_time // duration) * duration - duration
    return Candle(
        DATA_SOURCE,
        "BTCUSDT",
        interval,
        opened,
        opened + duration - 1,
        "100",
        "106",
        "95",
        "100",
        "100",
        "10000",
        20,
        True,
    )


def _decision(action, *, decision_time=START, holding=False):
    snapshot = MarketSnapshot(
        "BTCUSDT",
        decision_time,
        (_candle("1h", decision_time),),
        (_candle("15m", decision_time),),
        (_candle("4h", decision_time),),
    )
    reason = {
        StrategyAction.ENTER_LONG: DecisionReason.TREND_PULLBACK_ENTRY,
        StrategyAction.EXIT_LONG: DecisionReason.STRATEGY_EXIT,
        StrategyAction.NO_TRADE: (
            DecisionReason.HOLD_POSITION
            if holding
            else DecisionReason.SETUP_ABSENT
        ),
    }[action]
    setup = LongSetup("100", "95", "115") if action is StrategyAction.ENTER_LONG else None
    return StrategyDecision(
        StrategyContext(TREND_PULLBACK_IDENTITY, snapshot),
        action,
        reason,
        setup,
    )


def _managed(*, decision_time=START, quantity="0", digest="1"):
    exposure = Decimal(quantity) * Decimal("100")
    return ManagedPortfolioState(
        "BTCUSDT",
        (decision_time - START) // HOUR,
        decision_time,
        START,
        "10000",
        "10000",
        "10000" if quantity == "0" else "9000",
        quantity,
        "100",
        "10000",
        "0",
        0,
        0 if quantity == "0" else 1,
        format(exposure, "f"),
        None if decision_time == START else "0" * 64,
        digest * 64,
    )


def _authorization(
    action=StrategyAction.ENTER_LONG,
    *,
    evidence=EvidenceLabel.QUALIFIED_FOR_P4_RESEARCH,
):
    positioned = action is StrategyAction.EXIT_LONG
    state = _managed(quantity="1" if positioned else "0")
    decision = _decision(action)
    request = RiskRequest(
        decision,
        evidence,
        state.to_risk_state(kill_switch_active=positioned),
    )
    circuit = assess_circuit_breakers(request, state)
    switch = apply_kill_switch_event(
        None,
        KillSwitchEvent(0, START - 1, KillSwitchEventType.STARTUP),
    ).current
    if not positioned:
        switch = apply_kill_switch_event(
            switch,
            KillSwitchEvent(
                1,
                START,
                KillSwitchEventType.MANUAL_RESET,
                circuit,
                True,
            ),
        ).current
    protective = None
    if (
        action is StrategyAction.ENTER_LONG
        and evidence is EvidenceLabel.QUALIFIED_FOR_P4_RESEARCH
    ):
        protective = assess_protective_entry(
            assess_entry_limits(size_entry(request))
        )
    return authorize_paper_request(
        request,
        state,
        switch,
        circuit,
        protective,
    )


def _ready(character="a"):
    return RecoveryReadiness(
        RecoveryStatus.READY,
        RecoveryReason.RECONCILIATION_PASSED,
        character * 64,
    )


class LocalPaperExecutionContractTests(unittest.TestCase):
    def test_policy_is_frozen_local_paper_only(self):
        policy = LocalPaperExecutionPolicy()
        self.assertEqual(policy.execution_mode, "LOCAL_PAPER")
        self.assertTrue(policy.paper_only)
        for change in (
            {"execution_mode": "TESTNET"},
            {"live_master_lock": "ON"},
            {"allow_external_transport": True},
            {"allow_credentials": True},
            {"allow_order_endpoint": True},
            {"allow_leverage": True},
            {"allow_withdrawal": True},
            {"allow_ai_direct_execution": True},
        ):
            with self.subTest(change=change), self.assertRaises(
                ExecutionContractError
            ):
                replace(policy, **change)

    def test_recovery_readiness_is_fail_closed_and_hash_bound(self):
        startup = RecoveryReadiness()
        failed = RecoveryReadiness(
            RecoveryStatus.RECOVERY_REQUIRED,
            RecoveryReason.RECONCILIATION_FAILED,
            "b" * 64,
        )
        ready = _ready()
        self.assertNotEqual(startup.readiness_sha256, failed.readiness_sha256)
        self.assertNotEqual(failed.readiness_sha256, ready.readiness_sha256)
        self.assertEqual(ready.readiness_sha256, _ready().readiness_sha256)

    def test_invalid_recovery_combinations_fail_closed(self):
        invalid = (
            (RecoveryStatus.READY, RecoveryReason.RECONCILIATION_PASSED, None),
            (RecoveryStatus.READY, RecoveryReason.FAIL_CLOSED_STARTUP, "a" * 64),
            (
                RecoveryStatus.RECOVERY_REQUIRED,
                RecoveryReason.RECONCILIATION_FAILED,
                None,
            ),
            (
                RecoveryStatus.RECOVERY_REQUIRED,
                RecoveryReason.FAIL_CLOSED_STARTUP,
                "a" * 64,
            ),
        )
        for values in invalid:
            with self.subTest(values=values), self.assertRaises(
                ExecutionContractError
            ):
                RecoveryReadiness(*values)

    def test_default_startup_blocks_qualified_entry(self):
        authorization = _authorization()
        decision = assess_local_paper_authorization(authorization)
        self.assertEqual(decision.disposition, ExecutionDisposition.BLOCKED)
        self.assertEqual(decision.reason, ExecutionReason.RECOVERY_NOT_READY)
        self.assertEqual(decision.action, IntentAction.HOLD)
        self.assertIsNone(decision.approved_quantity)

    def test_reconciled_entry_preserves_exact_p4_quantity(self):
        authorization = _authorization()
        decision = assess_local_paper_authorization(authorization, _ready())
        self.assertEqual(
            decision.disposition, ExecutionDisposition.ACCEPT_LOCAL_PAPER
        )
        self.assertEqual(decision.action, IntentAction.ENTER_LONG)
        self.assertEqual(
            decision.approved_quantity,
            authorization.decision.approved_quantity,
        )
        self.assertEqual(decision.authorization_sha256, authorization.authorization_sha256)

    def test_insufficient_evidence_never_becomes_executable(self):
        authorization = _authorization(
            evidence=EvidenceLabel.INSUFFICIENT_EVIDENCE
        )
        for readiness in (RecoveryReadiness(), _ready()):
            with self.subTest(readiness=readiness.status):
                decision = assess_local_paper_authorization(
                    authorization, readiness
                )
                self.assertEqual(decision.disposition, ExecutionDisposition.BLOCKED)
                self.assertEqual(decision.reason, ExecutionReason.RISK_NOT_APPROVED)
                self.assertEqual(decision.action, IntentAction.HOLD)
                self.assertIsNone(decision.approved_quantity)

    def test_no_trade_is_no_action_without_quantity(self):
        authorization = _authorization(StrategyAction.NO_TRADE)
        decision = assess_local_paper_authorization(authorization, _ready())
        self.assertEqual(decision.disposition, ExecutionDisposition.NO_ACTION)
        self.assertEqual(decision.reason, ExecutionReason.NO_STRATEGY_ACTION)
        self.assertEqual(decision.action, IntentAction.HOLD)
        self.assertIsNone(decision.approved_quantity)

    def test_exit_is_blocked_until_reconciled_then_exact(self):
        authorization = _authorization(StrategyAction.EXIT_LONG)
        blocked = assess_local_paper_authorization(authorization)
        accepted = assess_local_paper_authorization(authorization, _ready())
        self.assertEqual(blocked.reason, ExecutionReason.RECOVERY_NOT_READY)
        self.assertEqual(blocked.action, IntentAction.HOLD)
        self.assertEqual(
            accepted.disposition, ExecutionDisposition.ACCEPT_LOCAL_PAPER
        )
        self.assertEqual(accepted.action, IntentAction.EXIT_LONG)
        self.assertEqual(accepted.approved_quantity, "1")

    def test_raw_or_forged_inputs_fail_closed(self):
        authorization = _authorization()
        for invalid in (
            authorization.decision,
            authorization.request.strategy_decision,
            object(),
        ):
            with self.subTest(invalid=type(invalid)), self.assertRaises(
                ExecutionContractError
            ):
                assess_local_paper_authorization(invalid, _ready())
        valid = assess_local_paper_authorization(authorization, _ready())
        with self.assertRaises(ExecutionContractError):
            replace(valid, approved_quantity="1")
        forged_risk = RiskDecision(
            authorization.request,
            RiskDisposition.APPROVE_PAPER,
            RiskReason.RISK_CHECKS_PASSED,
            "1",
        )
        with self.assertRaises((ExecutionContractError, RiskAdapterError)):
            replace(authorization, decision=forged_risk)

    def test_mutated_boundary_records_fail_reconstruction(self):
        authorization = _authorization()
        readiness = _ready()
        object.__setattr__(readiness, "reason", RecoveryReason.RECONCILIATION_FAILED)
        with self.assertRaises(ExecutionContractError):
            assess_local_paper_authorization(authorization, readiness)

        policy = LocalPaperExecutionPolicy()
        object.__setattr__(policy, "allow_external_transport", True)
        with self.assertRaises(ExecutionContractError):
            assess_local_paper_authorization(authorization, _ready(), policy)

    def test_decision_digest_is_deterministic_and_material(self):
        authorization = _authorization()
        first = assess_local_paper_authorization(authorization, _ready("a"))
        replay = assess_local_paper_authorization(authorization, _ready("a"))
        changed = assess_local_paper_authorization(authorization, _ready("b"))
        self.assertEqual(first.decision_sha256, replay.decision_sha256)
        self.assertNotEqual(first.decision_sha256, changed.decision_sha256)
        self.assertEqual(len(first.decision_sha256), 64)

    def test_contracts_expose_no_external_execution_or_secret_fields(self):
        names = {
            item.name
            for contract in (
                LocalPaperExecutionPolicy,
                RecoveryReadiness,
                LocalPaperExecutionDecision,
            )
            for item in fields(contract)
        }
        forbidden = {
            "api_key",
            "api_secret",
            "credential",
            "endpoint_url",
            "account_id",
            "broker",
            "transport",
        }
        self.assertTrue(names.isdisjoint(forbidden))

    @patch("sys.argv", ["yatl", "paper-execution-contract-check"])
    def test_cli_reports_safe_deterministic_boundary(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(), 0)
        text = output.getvalue()
        self.assertIn("P5 local Paper execution contract", text)
        self.assertIn("startup=BLOCKED/RECOVERY_NOT_READY", text)
        self.assertIn("candidate=BLOCKED/RISK_NOT_APPROVED", text)
        self.assertIn("entry=ACCEPT_LOCAL_PAPER", text)
        self.assertIn("No exchange order", text)


if __name__ == "__main__":
    unittest.main()
