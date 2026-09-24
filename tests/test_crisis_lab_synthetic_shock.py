import unittest
from decimal import Decimal

from research.crisis_lab import acquisition as acq
from research.crisis_lab import controls
from research.crisis_lab import synthetic_shock as shock
from yatl.data import Candle, DATA_SOURCE, INTERVAL_MILLISECONDS


START_MS = 1_704_067_200_000
DAY_MS = 86_400_000
END_MS = START_MS + 14 * DAY_MS
ENTRY_MS = START_MS + 10 * DAY_MS


def series(symbol, interval, step):
    duration = INTERVAL_MILLISECONDS[interval]
    values = []
    for index, open_ms in enumerate(range(START_MS, END_MS, duration)):
        price = 10_000 + index * step
        pad = max(step // 5, 1)
        values.append(
            Candle(
                source=DATA_SOURCE,
                symbol=symbol,
                interval=interval,
                open_time_ms=open_ms,
                close_time_ms=open_ms + duration - 1,
                open=str(price),
                high=str(price + pad * 2),
                low=str(price - pad),
                close=str(price + pad),
                base_volume="10",
                quote_volume="100000",
                trade_count=100,
                is_closed=True,
            )
        )
    return tuple(values)


def corpus():
    symbol = "BTCUSDT"
    return controls.AdmittedControlCorpus(
        event_id=controls.CONTROL_CORPUS_ID,
        designation="DEVELOPMENT",
        quality_manifest_relative_path="quality/event-quality-" + "a" * 24 + ".json",
        quality_manifest_file_sha256="a" * 64,
        event_acquisition_manifest_relative_path=(
            "manifests/event-acquisition-" + "b" * 24 + ".json"
        ),
        event_acquisition_manifest_sha256="b" * 64,
        retrieved_at_ms=END_MS + DAY_MS,
        datasets={
            (symbol, "15m"): series(symbol, "15m", 1),
            (symbol, "1h"): series(symbol, "1h", 10),
            (symbol, "4h"): series(symbol, "4h", 100),
        },
    )


def episode():
    primary = series("BTCUSDT", "1h", 10)
    entry = next(item for item in primary if item.open_time_ms == ENTRY_MS)
    reference = entry.close
    return {
        "decision_time_ms": ENTRY_MS,
        "fill_time_ms": ENTRY_MS,
        "symbol": "BTCUSDT",
        "context_sha256": "c" * 64,
        "regime": "TREND_UP",
        "strategy_reason": "TREND_PULLBACK_ENTRY",
        "active_setup": {
            "reference_price": reference,
            "invalidation_price": "10500",
            "target_price": "15000",
        },
        "risk_state_before_entry": {},
        "portfolio_before_entry": {},
        "portfolio_after_entry": {
            "symbol": "BTCUSDT",
            "cash": "9987.5",
            "asset_quantity": "0.001",
            "cost_basis_quote": "12.5",
            "liquidation_value_quote": "12.3",
            "realized_pnl_quote": "0",
            "unrealized_pnl_quote": "-0.2",
            "equity_quote": "9999.8",
            "total_fee_quote": "0.01",
            "total_slippage_quote": "0.01",
            "closed_trades": 0,
        },
        "entry_fill": {
            "action": "ENTER_LONG",
            "decision_time_ms": ENTRY_MS,
            "fill_time_ms": ENTRY_MS,
            "quantity": "0.001",
            "reference_price": entry.open,
            "reason": "NEXT_PRIMARY_OPEN",
        },
        "entry_candle": entry.as_record(),
        "source_state_confirmed_at_ms": entry.close_time_ms,
    }


def scenario(gap, multiplier):
    return {
        "scenario_id": f"TEST-G{gap}-S{multiplier}",
        "adverse_gap_bps": gap,
        "slippage_multiplier": multiplier,
        "fee_multiplier": 1,
    }


class CrisisLabImmediateShockTests(unittest.TestCase):
    def test_registry_is_exact_nine_scenario_matrix(self):
        registry, digest = shock.load_registry()
        self.assertEqual(len(digest), 64)
        self.assertEqual(registry["matrix"]["scenario_count"], 9)
        self.assertEqual(
            registry["matrix"]["adverse_gap_bps"],
            [500, 1000, 2000],
        )
        self.assertEqual(
            registry["matrix"]["slippage_multipliers"],
            [1, 2, 5],
        )

    def test_synthetic_gap_price_is_exact_decimal(self):
        self.assertEqual(shock._synthetic_price("100", 500), "95")
        self.assertEqual(shock._synthetic_price("100", 1000), "90")
        self.assertEqual(shock._synthetic_price("100", 2000), "80")

    def test_scenario_slippage_scales_but_source_spec_does_not(self):
        source = shock._source_spec(
            symbol="BTCUSDT",
            decision_time_ms=ENTRY_MS + INTERVAL_MILLISECONDS["1h"],
        )
        one = shock._scenario_spec(
            symbol="BTCUSDT",
            decision_time_ms=ENTRY_MS + INTERVAL_MILLISECONDS["1h"],
            multiplier=1,
        )
        five = shock._scenario_spec(
            symbol="BTCUSDT",
            decision_time_ms=ENTRY_MS + INTERVAL_MILLISECONDS["1h"],
            multiplier=5,
        )
        self.assertEqual(str(source.slippage_bps), "5")
        self.assertEqual(str(one.slippage_bps), "5")
        self.assertEqual(str(five.slippage_bps), "25")
        self.assertEqual(str(source.fee_bps), str(five.fee_bps))

    def test_gap_through_stop_exits_at_gap_open(self):
        item = episode()
        entry = Candle(**item["entry_candle"])
        setup = shock.LongSetup(
            item["active_setup"]["reference_price"],
            item["active_setup"]["invalidation_price"],
            item["active_setup"]["target_price"],
        )
        decision_time = entry.open_time_ms + INTERVAL_MILLISECONDS["1h"]
        price = shock._synthetic_price(entry.close, 2000)
        candle = shock._synthetic_candle(
            source=entry,
            decision_time_ms=decision_time,
            price=price,
        )
        reference = shock._exit_reference(
            strategy_action="NO_TRADE",
            setup=setup,
            shock=candle,
            quantity="0.001",
        )
        self.assertIsNotNone(reference)
        self.assertEqual(reference.reason.value, "STOP")
        self.assertEqual(reference.reference_price, candle.open)

    def test_five_percent_can_remain_open_while_twenty_percent_stops(self):
        source = corpus()
        item = episode()
        five = shock._run_scenario(
            corpus=source,
            episode=item,
            scenario=scenario(500, 1),
            registry_sha256="d" * 64,
        )
        twenty = shock._run_scenario(
            corpus=source,
            episode=item,
            scenario=scenario(2000, 1),
            registry_sha256="d" * 64,
        )
        self.assertEqual(
            five["strategy_before_shock_fill"]["action"],
            "NO_TRADE",
        )
        self.assertFalse(
            five["strategy_before_shock_fill"]["future_shock_visible"]
        )
        self.assertEqual(
            five["immediate"]["position_quantity_after_shock"],
            "0.001",
        )
        self.assertIsNone(
            five["immediate"]["protective_exit_reason"]
        )
        self.assertEqual(
            twenty["immediate"]["position_quantity_after_shock"],
            "0",
        )
        self.assertEqual(
            twenty["immediate"]["protective_exit_reason"],
            "STOP",
        )
        self.assertEqual(
            twenty["immediate"]["time_to_zero_exposure_ms_if_immediate"],
            0,
        )

    def test_pre_shock_equity_is_invariant_to_stressed_slippage(self):
        source = corpus()
        item = episode()
        one = shock._run_scenario(
            corpus=source,
            episode=item,
            scenario=scenario(500, 1),
            registry_sha256="e" * 64,
        )
        five = shock._run_scenario(
            corpus=source,
            episode=item,
            scenario=scenario(500, 5),
            registry_sha256="e" * 64,
        )
        self.assertEqual(
            one["immediate"]["equity_before_shock"],
            five["immediate"]["equity_before_shock"],
        )
        self.assertNotEqual(
            one["immediate"]["equity_after_shock"],
            five["immediate"]["equity_after_shock"],
        )
        self.assertEqual(one["scenario"]["source_slippage_bps"], "5")
        self.assertEqual(five["scenario"]["source_slippage_bps"], "5")
        self.assertEqual(five["scenario"]["slippage_bps"], "25")

    def test_exit_reference_enforces_volume_gate(self):
        item = episode()
        entry = Candle(**item["entry_candle"])
        setup = shock.LongSetup(
            item["active_setup"]["reference_price"],
            item["active_setup"]["invalidation_price"],
            item["active_setup"]["target_price"],
        )
        decision_time = entry.open_time_ms + INTERVAL_MILLISECONDS["1h"]
        candle = Candle(
            source=entry.source,
            symbol=entry.symbol,
            interval="1h",
            open_time_ms=decision_time,
            close_time_ms=decision_time + INTERVAL_MILLISECONDS["1h"] - 1,
            open="9000",
            high="9000",
            low="9000",
            close="9000",
            base_volume="0.0001",
            quote_volume="1",
            trade_count=1,
            is_closed=True,
        )
        with self.assertRaises(shock.ShockError):
            shock._exit_reference(
                strategy_action="NO_TRADE",
                setup=setup,
                shock=candle,
                quantity="0.001",
            )

    def test_p10_runtime_root_is_forbidden(self):
        with self.assertRaises(shock.ShockError):
            shock.run_immediate_shock_matrix(
                runtime_root=shock.Path("/var/lib/yatl/p10"),
                active_diagnostic_relative_path=(
                    "active-diagnostic/strategy-active-" + "0" * 24 + ".json"
                ),
                active_diagnostic_file_sha256="0" * 64,
            )


if __name__ == "__main__":
    unittest.main()
