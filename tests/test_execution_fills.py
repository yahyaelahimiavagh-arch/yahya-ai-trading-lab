import contextlib
import io
import unittest
from dataclasses import replace
from decimal import Decimal
from unittest.mock import patch

from yatl.__main__ import _paper_execution_contract_runtime_check, main
from yatl.backtest import BacktestSpec, DecisionEvent, FillReason, IntentAction
from yatl.data import Candle, DATA_SOURCE
from yatl.execution import (
    LocalOrderEventType,
    LocalOrderStatus,
    LocalPaperFillCostAdapter,
    LocalPaperFillError,
    LocalPaperIntentRecord,
    apply_local_order_event,
    build_local_order_event,
)


HOUR = 3_600_000


class LocalPaperFillCostTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, _, cls.entry_decision, cls.exit_decision = (
            _paper_execution_contract_runtime_check()
        )
        cls.entry_time = cls.entry_decision.authorization.request.strategy_decision.decision_time_ms
        cls.exit_time = cls.exit_decision.authorization.request.strategy_decision.decision_time_ms

    def setUp(self):
        self.spec = BacktestSpec(
            "BTCUSDT",
            self.entry_time,
            self.exit_time + HOUR,
            fee_bps="10",
            slippage_bps="5",
        )

    def _event(self, decision, sequence):
        strategy = decision.authorization.request.strategy_decision
        return DecisionEvent(
            sequence,
            strategy.decision_time_ms,
            strategy.decision_time_ms,
            strategy.context.snapshot,
        )

    def _bar(self, decision, *, opened=None, price="100", low="99", high="106",
             volume="100", closed=True):
        strategy = decision.authorization.request.strategy_decision
        opened = strategy.decision_time_ms if opened is None else opened
        return Candle(
            DATA_SOURCE,
            "BTCUSDT",
            "1h",
            opened,
            opened + HOUR - 1,
            price,
            high,
            low,
            price,
            volume,
            "10000",
            20,
            closed,
        )

    def _evidence(self, decision, *, status="active"):
        intent = LocalPaperIntentRecord.from_decision(decision)
        created_event = build_local_order_event(
            intent,
            0,
            decision.authorization.request.strategy_decision.decision_time_ms - 2,
            LocalOrderEventType.CREATE,
        )
        created = apply_local_order_event(intent, None, created_event).current
        if status == "pending":
            return intent, created
        active_event = build_local_order_event(
            intent,
            1,
            created.updated_time_ms + 1,
            LocalOrderEventType.ACTIVATE,
            created,
        )
        active = apply_local_order_event(intent, created, active_event).current
        if status == "active":
            return intent, active
        cancelled_event = build_local_order_event(
            intent,
            2,
            active.updated_time_ms + 1,
            LocalOrderEventType.CANCEL,
            active,
        )
        return intent, apply_local_order_event(
            intent, active, cancelled_event,
        ).current

    def _entry(self, adapter=None, **bar_changes):
        adapter = adapter or LocalPaperFillCostAdapter("BTCUSDT", self.spec)
        intent, order = self._evidence(self.entry_decision)
        step = adapter.process(
            self._event(self.entry_decision, 0),
            self.entry_decision,
            intent,
            order,
            self._bar(self.entry_decision, **bar_changes),
            self.spec,
        )
        return adapter, step

    def test_exact_p4_quantity_reaches_accepted_p2_fill_and_costs(self):
        adapter, step = self._entry()
        quantity = self.entry_decision.approved_quantity
        self.assertEqual(step.p2_intent.quantity, quantity)
        self.assertEqual(step.references[0].quantity, quantity)
        self.assertEqual(step.fills[0].asset_delta, Decimal(quantity))
        self.assertEqual(step.fills[0].execution_price, Decimal("100.0500"))
        self.assertTrue(adapter.has_position)
        self.assertEqual(adapter.active_quantity, quantity)

    def test_entry_then_exit_uses_same_p2_engine_and_finishes_flat(self):
        adapter, entry = self._entry()
        intent, order = self._evidence(self.exit_decision)
        exit_step = adapter.process(
            self._event(self.exit_decision, 1),
            self.exit_decision,
            intent,
            order,
            self._bar(self.exit_decision, price="101", low="100", high="102"),
            self.spec,
        )
        self.assertEqual(entry.references[0].action, IntentAction.ENTER_LONG)
        self.assertEqual(exit_step.references[0].action, IntentAction.EXIT_LONG)
        self.assertEqual(exit_step.references[0].reason, FillReason.SCRIPTED_EXIT)
        self.assertFalse(adapter.has_position)
        self.assertIsNone(adapter.active_quantity)

    def test_fill_step_digest_is_deterministic_and_material(self):
        _, first = self._entry()
        _, replay = self._entry()
        self.assertEqual(first, replay)
        self.assertEqual(first.fill_step_sha256, replay.fill_step_sha256)
        self.assertEqual(len(first.fill_step_sha256), 64)
        self.assertNotIn("path", first.as_record())

    def test_intent_or_decision_mismatch_fails_before_fill(self):
        adapter = LocalPaperFillCostAdapter("BTCUSDT", self.spec)
        exit_intent, exit_order = self._evidence(self.exit_decision)
        with self.assertRaises(LocalPaperFillError):
            adapter.process(
                self._event(self.entry_decision, 0),
                self.entry_decision,
                exit_intent,
                exit_order,
                self._bar(self.entry_decision),
                self.spec,
            )
        self.assertFalse(adapter.has_position)

    def test_pending_or_cancelled_order_cannot_fill(self):
        for status in ("pending", "cancelled"):
            adapter = LocalPaperFillCostAdapter("BTCUSDT", self.spec)
            intent, order = self._evidence(self.entry_decision, status=status)
            with self.subTest(status=status), self.assertRaises(LocalPaperFillError):
                adapter.process(
                    self._event(self.entry_decision, 0),
                    self.entry_decision,
                    intent,
                    order,
                    self._bar(self.entry_decision),
                    self.spec,
                )
            self.assertFalse(adapter.has_position)

    def test_missing_open_future_and_gapped_candles_fail_atomically(self):
        invalid = (
            None,
            self._bar(self.entry_decision, closed=False),
            self._bar(self.entry_decision, opened=self.entry_time + HOUR),
            self._bar(self.entry_decision, opened=self.entry_time - HOUR),
        )
        intent, order = self._evidence(self.entry_decision)
        for candle in invalid:
            adapter = LocalPaperFillCostAdapter("BTCUSDT", self.spec)
            with self.subTest(candle=candle), self.assertRaises(LocalPaperFillError):
                adapter.process(
                    self._event(self.entry_decision, 0),
                    self.entry_decision,
                    intent,
                    order,
                    candle,
                    self.spec,
                )
            self.assertFalse(adapter.has_position)

    def test_volume_breach_rolls_back_candidate_p2_state(self):
        adapter = LocalPaperFillCostAdapter("BTCUSDT", self.spec)
        with self.assertRaises(LocalPaperFillError):
            self._entry(adapter, volume="1")
        self.assertFalse(adapter.has_position)
        _, valid = self._entry(adapter)
        self.assertEqual(valid.references[0].quantity, self.entry_decision.approved_quantity)

    def test_next_open_outside_bracket_rolls_back_candidate_state(self):
        adapter = LocalPaperFillCostAdapter("BTCUSDT", self.spec)
        with self.assertRaises(LocalPaperFillError):
            self._entry(adapter, price="94", low="93", high="95")
        self.assertFalse(adapter.has_position)
        self._entry(adapter)
        self.assertTrue(adapter.has_position)

    def test_cost_policy_mismatch_fails_before_p2_state_change(self):
        adapter = LocalPaperFillCostAdapter("BTCUSDT", self.spec)
        intent, order = self._evidence(self.entry_decision)
        changed = replace(self.spec, fee_bps="11")
        with self.assertRaises(LocalPaperFillError):
            adapter.process(
                self._event(self.entry_decision, 0),
                self.entry_decision,
                intent,
                order,
                self._bar(self.entry_decision),
                changed,
            )
        self.assertFalse(adapter.has_position)

    def test_duplicate_or_out_of_order_event_does_not_change_position(self):
        adapter, _ = self._entry()
        intent, order = self._evidence(self.exit_decision)
        for sequence in (0, 2):
            with self.subTest(sequence=sequence), self.assertRaises(LocalPaperFillError):
                adapter.process(
                    self._event(self.exit_decision, sequence),
                    self.exit_decision,
                    intent,
                    order,
                    self._bar(self.exit_decision, price="101", low="100", high="102"),
                    self.spec,
                )
            self.assertTrue(adapter.has_position)

    def test_overlapping_entry_and_exit_without_position_fail_closed(self):
        adapter = LocalPaperFillCostAdapter("BTCUSDT", self.spec)
        exit_intent, exit_order = self._evidence(self.exit_decision)
        with self.assertRaises(LocalPaperFillError):
            adapter.process(
                self._event(self.exit_decision, 0),
                self.exit_decision,
                exit_intent,
                exit_order,
                self._bar(self.exit_decision),
                self.spec,
            )
        adapter, _ = self._entry(adapter)
        entry_intent, entry_order = self._evidence(self.entry_decision)
        with self.assertRaises(LocalPaperFillError):
            adapter.process(
                self._event(self.entry_decision, 1),
                self.entry_decision,
                entry_intent,
                entry_order,
                self._bar(self.entry_decision),
                self.spec,
            )

    def test_same_bar_stop_uses_accepted_p2_conservative_rule(self):
        adapter, step = self._entry(low="94", high="116")
        self.assertEqual(len(step.fills), 2)
        self.assertEqual(
            step.references[1].reason,
            FillReason.AMBIGUOUS_STOP_PRIORITY,
        )
        self.assertEqual(step.references[1].reference_price, "95")
        self.assertFalse(adapter.has_position)

    def test_wrong_event_snapshot_fails_closed(self):
        intent, order = self._evidence(self.entry_decision)
        wrong = self._event(self.exit_decision, 0)
        adapter = LocalPaperFillCostAdapter("BTCUSDT", self.spec)
        with self.assertRaises(LocalPaperFillError):
            adapter.process(
                wrong,
                self.entry_decision,
                intent,
                order,
                self._bar(self.entry_decision),
                self.spec,
            )

    def test_constructor_rejects_wrong_symbol_or_spec(self):
        with self.assertRaises(LocalPaperFillError):
            LocalPaperFillCostAdapter("ETHUSDT", self.spec)
        with self.assertRaises(LocalPaperFillError):
            LocalPaperFillCostAdapter("BTCUSDT", object())

    @patch("sys.argv", ["yatl", "paper-fill-cost-check"])
    def test_cli_reports_safe_deterministic_p2_delegation(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(), 0)
        text = output.getvalue()
        self.assertIn("accepted P2 fill and cost integration", text)
        self.assertIn("steps=2", text)
        self.assertIn("replay_equal=true", text)
        self.assertIn("No exchange order", text)


if __name__ == "__main__":
    unittest.main()
