import inspect
import json
import tempfile
import unittest
from pathlib import Path

from research.crisis_lab import acquisition as acq
from research.crisis_lab import controls
from yatl.data import Candle, DATA_SOURCE, INTERVAL_MILLISECONDS
from yatl.validation.paper_runner import RUNNER_QUANTITY


DAY_MS = 86_400_000
START_MS = 1_704_067_200_000
ANALYSIS_START_MS = START_MS + 10 * DAY_MS
ANALYSIS_END_MS = START_MS + 12 * DAY_MS
CORPUS_END_MS = START_MS + 14 * DAY_MS


def iso(value):
    return acq._ms_to_iso(value)


def candles(symbol, interval, start=START_MS, end=CORPUS_END_MS):
    duration = INTERVAL_MILLISECONDS[interval]
    base = 100_000 if symbol == "BTCUSDT" else 5_000
    out = []
    for index, open_ms in enumerate(range(start, end, duration)):
        price = base + index
        out.append(
            Candle(
                source=DATA_SOURCE,
                symbol=symbol,
                interval=interval,
                open_time_ms=open_ms,
                close_time_ms=open_ms + duration - 1,
                open=str(price),
                high=str(price + 2),
                low=str(price - 1),
                close=str(price + 1),
                base_volume="10",
                quote_volume="100",
                trade_count=10,
                is_closed=True,
            )
        )
    return tuple(out)


def corpus():
    return controls.AdmittedControlCorpus(
        event_id=controls.CONTROL_CORPUS_ID,
        designation="DEVELOPMENT",
        quality_manifest_relative_path=(
            "quality/event-catalog-v0.1.0/"
            "CRL-CONTROL-DEV-POOL-001/event-quality-" + "a" * 24 + ".json"
        ),
        quality_manifest_file_sha256="a" * 64,
        event_acquisition_manifest_relative_path=(
            "manifests/event-catalog-v0.1.0/"
            "CRL-CONTROL-DEV-POOL-001/event-acquisition-" + "b" * 24 + ".json"
        ),
        event_acquisition_manifest_sha256="b" * 64,
        retrieved_at_ms=CORPUS_END_MS + DAY_MS,
        datasets={
            (symbol, interval): candles(symbol, interval)
            for symbol in acq.ALLOWED_SYMBOLS
            for interval in acq.ALLOWED_INTERVALS
        },
    )


def window():
    return {
        "control_id": "CRL-TC001",
        "acquisition_start_utc": iso(START_MS),
        "analysis_start_utc": iso(ANALYSIS_START_MS),
        "analysis_end_utc": iso(ANALYSIS_END_MS),
    }


class CrisisLabControlRuntimeTests(unittest.TestCase):
    def test_registered_protocol_freezes_baseline_semantics(self):
        protocol, digest = controls.load_protocol()
        self.assertEqual(len(digest), 64)
        self.assertEqual(
            set(protocol["baseline_definitions"]),
            {"NO_TRADE_CASH", "BUY_AND_HOLD_RESEARCH"},
        )
        buy_hold = protocol["baseline_definitions"][
            "BUY_AND_HOLD_RESEARCH"
        ]
        self.assertEqual(
            buy_hold["quantity_policy"],
            "MATCH_FROZEN_YATL_RESEARCH_QUANTITY",
        )
        self.assertIn("FEE_BPS", buy_hold["fee_policy"])
        self.assertIn("SLIPPAGE_BPS", buy_hold["slippage_policy"])

    def test_window_slice_excludes_all_future_candles(self):
        event = controls._event_for_window(
            corpus=corpus(),
            protocol_sha256="c" * 64,
            window=window(),
        )
        for symbol in acq.ALLOWED_SYMBOLS:
            for interval in acq.ALLOWED_INTERVALS:
                values = event.datasets[(symbol, interval)]
                self.assertEqual(values[0].open_time_ms, START_MS)
                self.assertLess(values[-1].open_time_ms, ANALYSIS_END_MS)
                self.assertEqual(
                    values[-1].open_time_ms,
                    ANALYSIS_END_MS
                    - INTERVAL_MILLISECONDS[interval],
                )
                self.assertTrue(
                    all(
                        item.open_time_ms < ANALYSIS_END_MS
                        for item in values
                    )
                )

    def test_ordinary_window_replay_is_deterministic(self):
        first = controls._run_window(
            corpus=corpus(),
            protocol_sha256="d" * 64,
            window=window(),
        )
        second = controls._run_window(
            corpus=corpus(),
            protocol_sha256="d" * 64,
            window=window(),
        )
        self.assertEqual(
            controls._canonical_json(first),
            controls._canonical_json(second),
        )
        self.assertTrue(first["deterministic_replay_verified"])
        self.assertTrue(first["point_in_time_verified"])
        self.assertFalse(first["future_data_visible_to_strategy"])
        self.assertFalse(first["selection"]["outcome_selected"])
        self.assertFalse(first["selection"]["strategy_result_selected"])

        for item in first["symbols"]:
            yatl = item["yatl"]
            self.assertEqual(yatl["event_count"], 48)
            self.assertEqual(
                yatl["first_decision_time_ms"], ANALYSIS_START_MS
            )
            self.assertEqual(yatl["end_time_ms"], ANALYSIS_END_MS)
            self.assertTrue(
                all(
                    ANALYSIS_START_MS
                    <= row["decision_time_ms"]
                    < ANALYSIS_END_MS
                    for row in yatl["trace"]
                )
            )
            self.assertEqual(
                item["baselines"]["NO_TRADE_CASH"][
                    "net_return_after_costs"
                ],
                "0",
            )
            self.assertEqual(
                item["baselines"]["BUY_AND_HOLD_RESEARCH"]["quantity"],
                str(RUNNER_QUANTITY),
            )

    def test_buy_hold_is_matched_quantity_and_costed(self):
        primary = tuple(
            item
            for item in candles("BTCUSDT", "1h")
            if ANALYSIS_START_MS
            <= item.open_time_ms
            < ANALYSIS_END_MS
        )
        result = controls._buy_hold_baseline(primary)
        self.assertEqual(
            result["quantity_policy"],
            "MATCH_FROZEN_YATL_RESEARCH_QUANTITY",
        )
        self.assertEqual(result["quantity"], str(RUNNER_QUANTITY))
        self.assertGreater(
            float(result["executed_total_cost_quote"]), 0.0
        )
        self.assertNotEqual(
            result["entry_reference_price"],
            result["entry_execution_price"],
        )
        self.assertNotEqual(
            result["exit_reference_price"],
            result["exit_execution_price"],
        )

    def test_protocol_missing_baseline_definition_fails_closed(self):
        original, _ = controls.load_protocol()
        broken = dict(original)
        broken["baseline_definitions"] = {
            "NO_TRADE_CASH": original["baseline_definitions"][
                "NO_TRADE_CASH"
            ]
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "protocol.json"
            path.write_text(
                json.dumps(broken, sort_keys=True),
                encoding="utf-8",
            )
            with self.assertRaises(controls.ControlError):
                controls.load_protocol(path)

    def test_p10_runtime_root_is_forbidden(self):
        with self.assertRaises(controls.ControlError):
            controls.replay_control_windows(
                runtime_root=Path("/var/lib/yatl/p10"),
                quality_manifest_relative_path=(
                    "quality/event-quality-" + "0" * 24 + ".json"
                ),
                quality_manifest_file_sha256="0" * 64,
                control_ids=["CRL-C001"],
            )

    def test_control_source_has_no_network_or_execution_capability(self):
        source = inspect.getsource(controls)
        for forbidden in (
            "urllib",
            "requests",
            "httpx",
            "aiohttp",
            "websockets",
            "socket",
            "/api/v3/order",
            "/fapi",
            "/dapi",
            "withdraw(",
            "api_key",
            "api_secret",
            "os.environ",
            "os.getenv",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
