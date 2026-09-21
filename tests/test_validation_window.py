import hashlib
import inspect
import json
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

from yatl.strategy.runs import EVALUATION_END_MS
from yatl.validation.registration import CandidateGateRegistration
from yatl.validation.window import (
    ACCEPTED_HISTORICAL_SOURCE_END_MS,
    ACCEPTED_SOURCE_ID,
    ACCEPTED_SOURCE_MANIFEST_GENERATED_AT_MS,
    ACCEPTED_SOURCE_MANIFEST_GIT_BLOB_SHA1,
    ACCEPTED_SOURCE_MANIFEST_PATH,
    DAY_MS,
    FORWARD_WINDOW_START_MS,
    INTERVAL_MILLISECONDS,
    MINIMUM_EVALUATION_NOT_BEFORE_MS,
    MINIMUM_VALIDATION_DAYS,
    P10_002_CHECKPOINT,
    P3_DEVELOPMENT_EVIDENCE_END_MS,
    SEALED_AT_MS,
    ForwardCollectionState,
    ForwardObservationIdentity,
    ForwardWindowSeal,
    WindowEvidenceState,
    WindowSealError,
    WindowSealState,
    EconomicEvaluationState,
    observation_identity_from_record,
    window_from_record,
)


def _git_blob_sha1(path):
    payload = Path(path).read_bytes()
    framed = f"blob {len(payload)}\0".encode("ascii") + payload
    return hashlib.sha1(framed).hexdigest()


def _identity(*, symbol="BTCUSDT", interval="1h", open_time_ms=None,
              source_id=ACCEPTED_SOURCE_ID, is_closed=True):
    if open_time_ms is None:
        open_time_ms = FORWARD_WINDOW_START_MS
    duration = INTERVAL_MILLISECONDS.get(interval, 300_000)
    return ForwardObservationIdentity(
        source_id=source_id,
        symbol=symbol,
        interval=interval,
        open_time_ms=open_time_ms,
        close_time_ms=open_time_ms + duration - 1,
        is_closed=is_closed,
    )


class ForwardWindowSealTests(unittest.TestCase):
    def test_window_binds_exact_accepted_p10_002_registration(self):
        registration = CandidateGateRegistration()
        window = ForwardWindowSeal()
        self.assertEqual(
            window.p10_002_registration_sha256,
            registration.registration_sha256,
        )
        self.assertEqual(
            window.candidate_sha256,
            registration.candidate.candidate_sha256,
        )
        self.assertEqual(
            window.gate_registry_sha256,
            registration.gates.registry_sha256,
        )
        self.assertEqual(
            window.p10_002_checkpoint,
            "e327e2b99a0883fc096941db18b27e572561a7d1",
        )

    def test_window_binds_exact_accepted_source_manifest(self):
        window = ForwardWindowSeal()
        self.assertEqual(window.accepted_source_id, "BINANCE_SPOT_PUBLIC")
        self.assertEqual(
            window.accepted_source_manifest_path,
            "manifests/p1-market-data.json",
        )
        self.assertEqual(
            _git_blob_sha1(ACCEPTED_SOURCE_MANIFEST_PATH),
            ACCEPTED_SOURCE_MANIFEST_GIT_BLOB_SHA1,
        )

        manifest = json.loads(Path(ACCEPTED_SOURCE_MANIFEST_PATH).read_text())
        self.assertEqual(
            manifest["generated_at_ms"],
            ACCEPTED_SOURCE_MANIFEST_GENERATED_AT_MS,
        )
        self.assertEqual(
            max(item["requested_end_time_ms"] for item in manifest["datasets"]),
            ACCEPTED_HISTORICAL_SOURCE_END_MS,
        )
        self.assertEqual(
            {item["source"] for item in manifest["datasets"]},
            {ACCEPTED_SOURCE_ID},
        )

    def test_development_evidence_cutoff_matches_accepted_p3(self):
        self.assertEqual(
            P3_DEVELOPMENT_EVIDENCE_END_MS,
            EVALUATION_END_MS,
        )
        self.assertEqual(P3_DEVELOPMENT_EVIDENCE_END_MS, 1_788_912_000_000)

    def test_cutoffs_are_strictly_ordered_for_no_peek(self):
        window = ForwardWindowSeal()
        self.assertLess(
            window.p3_development_evidence_end_ms,
            window.accepted_historical_source_end_ms,
        )
        self.assertLess(
            window.accepted_historical_source_end_ms,
            window.sealed_at_ms,
        )
        self.assertLess(
            window.sealed_at_ms,
            window.forward_window_start_ms,
        )

    def test_forward_start_is_exact_utc_boundary_for_all_intervals(self):
        window = ForwardWindowSeal()
        self.assertEqual(window.forward_window_start_ms, 1_790_035_200_000)
        self.assertEqual(window.time_basis, "UTC_UNIX_MILLISECONDS")
        for interval in window.intervals:
            with self.subTest(interval=interval):
                self.assertEqual(
                    window.forward_window_start_ms
                    % INTERVAL_MILLISECONDS[interval],
                    0,
                )

    def test_minimum_evaluation_date_is_exactly_90_days_after_start(self):
        window = ForwardWindowSeal()
        self.assertEqual(window.minimum_validation_days, 90)
        self.assertEqual(
            window.minimum_evaluation_not_before_ms,
            window.forward_window_start_ms + 90 * DAY_MS,
        )
        self.assertEqual(
            window.minimum_evaluation_not_before_ms,
            1_797_811_200_000,
        )
        self.assertTrue(window.evaluation_may_extend_for_sample_gate)

    def test_window_is_sealed_but_contains_no_forward_data_or_result(self):
        window = ForwardWindowSeal()
        self.assertEqual(window.window_state, WindowSealState.SEALED)
        self.assertEqual(
            window.forward_collection_state,
            ForwardCollectionState.NOT_COLLECTED,
        )
        self.assertEqual(
            window.economic_evaluation_state,
            EconomicEvaluationState.NOT_EVALUATED,
        )
        self.assertEqual(
            window.strategy_evidence,
            WindowEvidenceState.INSUFFICIENT_EVIDENCE,
        )
        self.assertTrue(window.forward_data_admission_authorized)
        self.assertFalse(window.economic_evaluation_allowed)

    def test_window_is_paper_only_and_p11_stays_locked(self):
        window = ForwardWindowSeal()
        self.assertTrue(window.paper_only)
        self.assertEqual(window.live_master_lock, "OFF")
        self.assertTrue(window.p11_locked)
        self.assertFalse(window.live_candidate)
        self.assertFalse(window.trade_permission)
        self.assertFalse(window.order_endpoint)
        self.assertFalse(window.ai_direct_execution)

    def test_no_peek_flags_are_all_fail_closed(self):
        window = ForwardWindowSeal()
        self.assertTrue(window.future_only)
        self.assertTrue(window.reject_pre_window_data)
        self.assertTrue(window.reject_historical_backfill_as_forward)
        self.assertTrue(window.require_closed_observations)
        self.assertTrue(window.require_exact_source)
        self.assertTrue(window.require_exact_symbol_interval_scope)
        self.assertFalse(window.candidate_mutation_allowed)
        self.assertFalse(window.gate_mutation_allowed)
        self.assertFalse(window.source_substitution_allowed)
        self.assertFalse(window.lookahead_allowed)

    def test_first_closed_observation_identity_is_admissible_for_each_interval(self):
        for interval in ("15m", "1h", "4h"):
            with self.subTest(interval=interval):
                identity = _identity(interval=interval)
                self.assertEqual(identity.open_time_ms, FORWARD_WINDOW_START_MS)
                self.assertEqual(identity.interval, interval)
                self.assertEqual(identity.source_id, ACCEPTED_SOURCE_ID)
                self.assertTrue(identity.is_closed)

    def test_pre_window_observation_is_rejected(self):
        with self.assertRaises(WindowSealError):
            _identity(
                open_time_ms=(
                    FORWARD_WINDOW_START_MS - INTERVAL_MILLISECONDS["1h"]
                )
            )

    def test_misaligned_observation_is_rejected(self):
        with self.assertRaises(WindowSealError):
            _identity(open_time_ms=FORWARD_WINDOW_START_MS + 1)

    def test_wrong_close_boundary_is_rejected(self):
        with self.assertRaises(WindowSealError):
            ForwardObservationIdentity(
                source_id=ACCEPTED_SOURCE_ID,
                symbol="BTCUSDT",
                interval="1h",
                open_time_ms=FORWARD_WINDOW_START_MS,
                close_time_ms=FORWARD_WINDOW_START_MS + 3_600_000,
                is_closed=True,
            )

    def test_open_observation_is_rejected(self):
        with self.assertRaises(WindowSealError):
            _identity(is_closed=False)

    def test_wrong_source_symbol_and_interval_are_rejected(self):
        with self.assertRaises(WindowSealError):
            _identity(source_id="OTHER")
        with self.assertRaises(WindowSealError):
            _identity(symbol="BNBUSDT")
        with self.assertRaises(WindowSealError):
            _identity(interval="5m")

    def test_observation_is_bound_to_exact_window_digest(self):
        identity = _identity()
        with self.assertRaises(WindowSealError):
            ForwardObservationIdentity(
                source_id=identity.source_id,
                symbol=identity.symbol,
                interval=identity.interval,
                open_time_ms=identity.open_time_ms,
                close_time_ms=identity.close_time_ms,
                is_closed=True,
                window_sha256="0" * 64,
            )

    def test_window_digest_is_deterministic_and_frozen(self):
        first = ForwardWindowSeal()
        second = ForwardWindowSeal()
        self.assertEqual(first, second)
        self.assertEqual(first.window_sha256, second.window_sha256)
        self.assertEqual(len(first.window_sha256), 64)
        with self.assertRaises(FrozenInstanceError):
            first.window_id = "OTHER"

    def test_window_rejects_candidate_gate_source_or_cutoff_mutation(self):
        cases = (
            {"candidate_sha256": "0" * 64},
            {"gate_registry_sha256": "0" * 64},
            {"p10_002_registration_sha256": "0" * 64},
            {"accepted_source_id": "OTHER"},
            {"accepted_source_manifest_git_blob_sha1": "0" * 40},
            {"p3_development_evidence_end_ms":
                 P3_DEVELOPMENT_EVIDENCE_END_MS + 1},
            {"accepted_historical_source_end_ms":
                 ACCEPTED_HISTORICAL_SOURCE_END_MS + 1},
            {"sealed_at_ms": SEALED_AT_MS + 1},
            {"forward_window_start_ms": FORWARD_WINDOW_START_MS - 3_600_000},
            {"minimum_evaluation_not_before_ms":
                 MINIMUM_EVALUATION_NOT_BEFORE_MS - DAY_MS},
            {"minimum_validation_days": 30},
            {"candidate_mutation_allowed": True},
            {"gate_mutation_allowed": True},
            {"lookahead_allowed": True},
            {"economic_evaluation_allowed": True},
            {"trade_permission": True},
            {"order_endpoint": True},
            {"ai_direct_execution": True},
        )
        for change in cases:
            with self.subTest(change=change), self.assertRaises(WindowSealError):
                ForwardWindowSeal(**change)

    def test_window_record_round_trip_is_strict(self):
        window = ForwardWindowSeal()
        restored = window_from_record(window.as_record())
        self.assertEqual(restored, window)
        self.assertEqual(restored.window_sha256, window.window_sha256)

        record = window.as_record()
        record["forward_candles"] = []
        with self.assertRaises(WindowSealError):
            window_from_record(record)

        record = window.as_record()
        record["cutoffs"]["forward_window_start_ms"] -= 3_600_000
        with self.assertRaises(WindowSealError):
            window_from_record(record)

    def test_observation_record_round_trip_is_strict(self):
        identity = _identity()
        restored = observation_identity_from_record(identity.as_record())
        self.assertEqual(restored, identity)
        self.assertEqual(restored.identity_sha256, identity.identity_sha256)

        record = identity.as_record()
        record["close"] = "100"
        with self.assertRaises(WindowSealError):
            observation_identity_from_record(record)

    def test_window_record_contains_no_market_values_or_economic_result(self):
        encoded = json.dumps(ForwardWindowSeal().as_record(), sort_keys=True)
        for forbidden in (
            "open_price",
            "high",
            "low",
            "close_price",
            "volume",
            "net_pnl",
            "profit_factor_result",
            "PASS_CANDIDATE",
            "QUALIFIED",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, encoded)

    def test_window_source_has_no_market_data_execution_network_or_clock_capability(self):
        import yatl.validation.window as window_module

        source = inspect.getsource(window_module)
        for forbidden in (
            "from yatl.data",
            "import yatl.data",
            "from yatl.strategy",
            "import yatl.strategy",
            "from yatl.execution",
            "import yatl.execution",
            "from yatl.account",
            "import yatl.account",
            "from yatl.risk",
            "import yatl.risk",
            "from yatl.analytics",
            "import yatl.analytics",
            "urllib",
            "http.client",
            "requests",
            "httpx",
            "aiohttp",
            "websockets",
            "socket",
            "openai",
            "anthropic",
            "os.getenv",
            "os.environ",
            "sqlite3",
            "pathlib",
            "open(",
            "time.time",
            "time.monotonic",
            "datetime",
            "/api/v3/order",
            "/fapi",
            "/dapi",
            "withdraw(",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
