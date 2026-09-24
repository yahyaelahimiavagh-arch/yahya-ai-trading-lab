import inspect
import io
import json
import tempfile
import unittest
import urllib.error
import urllib.parse
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path

from research.crisis_lab import acquisition as acq


def ms(value):
    return int(
        datetime.fromisoformat(
            value.replace("Z", "+00:00")
        ).timestamp() * 1000
    )


def minimal_registration(
    *,
    designation="DEVELOPMENT",
    replay_eligible=True,
    start="2024-01-01T00:00:00Z",
    end="2024-01-01T04:00:00Z",
):
    return {
        "schema": "YATL_CRL_DATA_ACQUISITION_REGISTER",
        "version": "0.1.0",
        "catalog": {"version": "0.1.0"},
        "symbols": ["BTCUSDT", "ETHUSDT"],
        "intervals": ["15m", "1h", "4h"],
        "protected_runtime_prefixes": ["/var/lib/yatl/p10/"],
        "p11_locked": True,
        "events": [
            {
                "event_id": "CRL-T001",
                "designation": designation,
                "replay_eligible": replay_eligible,
                "semantic_range": {
                    "start_utc": start,
                    "end_utc": end,
                },
            }
        ],
    }


def source_row(open_ms, interval, *, unit="MILLISECOND", close="100"):
    duration = acq.INTERVAL_MILLISECONDS[interval]
    close_ms = open_ms + duration - 1
    if unit == "MICROSECOND":
        open_value = open_ms * 1000
        close_value = close_ms * 1000 + 999
    else:
        open_value = open_ms
        close_value = close_ms
    return [
        str(open_value),
        "100",
        "101",
        "99",
        close,
        "1",
        str(close_value),
        "100",
        "10",
        "0.5",
        "50",
        "0",
    ]


def source_csv(period, interval, unit):
    if len(period) == 7:
        start = datetime.fromisoformat(
            period + "-01T00:00:00+00:00"
        )
        if start.month == 12:
            end = datetime(
                start.year + 1, 1, 1, tzinfo=timezone.utc
            )
        else:
            end = datetime(
                start.year, start.month + 1, 1, tzinfo=timezone.utc
            )
    else:
        start = datetime.fromisoformat(
            period + "T00:00:00+00:00"
        )
        end = start + acq.timedelta(days=1)

    start_ms = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)
    duration = acq.INTERVAL_MILLISECONDS[interval]
    output = io.StringIO(newline="")
    writer = acq.csv.writer(output, lineterminator="\n")
    cursor = start_ms
    while cursor < end_ms:
        writer.writerow(
            source_row(cursor, interval, unit=unit)
        )
        cursor += duration
    return output.getvalue().encode("utf-8")


class MockArchiveFetcher:
    def __init__(self):
        self._zips = {}

    def _zip_for(self, url):
        if url in self._zips:
            return self._zips[url]
        name = urllib.parse.urlsplit(url).path.rsplit("/", 1)[-1]
        stem = name[:-4]
        parts = stem.split("-")
        interval = parts[1]
        period = "-".join(parts[2:])
        period_day = date.fromisoformat(
            period + "-01" if len(period) == 7 else period
        )
        unit = acq.source_timestamp_unit_for_day(period_day)
        payload = source_csv(period, interval, unit)
        out = io.BytesIO()
        with zipfile.ZipFile(
            out,
            "w",
            compression=zipfile.ZIP_DEFLATED,
        ) as bundle:
            bundle.writestr(stem + ".csv", payload)
        self._zips[url] = out.getvalue()
        return self._zips[url]

    def fetch(self, url, *, max_bytes):
        if url.endswith(".CHECKSUM"):
            zip_url = url[:-9]
            payload = self._zip_for(zip_url)
            filename = urllib.parse.urlsplit(
                zip_url
            ).path.rsplit("/", 1)[-1]
            return (
                f"{acq._sha256(payload)}  {filename}\n"
            ).encode("utf-8")
        return self._zip_for(url)

class CloseBoundaryArchiveFetcher(MockArchiveFetcher):
    def _zip_for(self, url):
        if url in self._zips:
            return self._zips[url]
        name = urllib.parse.urlsplit(url).path.rsplit("/", 1)[-1]
        stem = name[:-4]
        parts = stem.split("-")
        interval = parts[1]
        period = "-".join(parts[2:])
        period_day = date.fromisoformat(
            period + "-01" if len(period) == 7 else period
        )
        unit = acq.source_timestamp_unit_for_day(period_day)
        payload = source_csv(period, interval, unit)
        rows = list(acq.csv.reader(io.StringIO(payload.decode("utf-8"))))
        if rows:
            if unit == "MICROSECOND":
                rows[0][6] = str(int(rows[0][6]) - 1_000_000)
            else:
                rows[0][6] = str(int(rows[0][6]) - 1_000)
        output = io.StringIO(newline="")
        writer = acq.csv.writer(output, lineterminator="\n")
        writer.writerows(rows)
        out = io.BytesIO()
        with zipfile.ZipFile(
            out,
            "w",
            compression=zipfile.ZIP_DEFLATED,
        ) as bundle:
            bundle.writestr(stem + ".csv", output.getvalue().encode("utf-8"))
        self._zips[url] = out.getvalue()
        return self._zips[url]



class MockRestFetcher:
    def __init__(
        self,
        *,
        mismatch=False,
        close_boundary_anomaly=False,
        empty_exact_window=False,
    ):
        self.mismatch = mismatch
        self.close_boundary_anomaly = close_boundary_anomaly
        self.empty_exact_window = empty_exact_window

    def fetch(self, url, *, max_bytes):
        query = urllib.parse.parse_qs(
            urllib.parse.urlsplit(url).query
        )
        interval = query["interval"][0]
        open_ms = int(query["startTime"][0])
        if self.empty_exact_window and "endTime" in query:
            return b"[]"
        row = source_row(
            open_ms,
            interval,
            close="100.5" if self.mismatch else "100",
        )
        if self.close_boundary_anomaly:
            row[6] = str(int(row[6]) - 1000)
        return json.dumps(
            [[
                int(row[0]),
                *row[1:6],
                int(row[6]),
                row[7],
                int(row[8]),
                row[9],
                row[10],
                row[11],
            ]]
        ).encode("utf-8")


class CrisisLabAcquisitionTests(unittest.TestCase):
    def test_real_register_is_consistent_with_code_scope(self):
        registration = acq.load_acquisition_register()
        self.assertEqual(registration["version"], "0.1.0")
        self.assertEqual(len(registration["events"]), 16)
        self.assertTrue(registration["p11_locked"])

    def test_p10_runtime_path_is_forbidden(self):
        candidates = (
            Path("/var/lib/yatl/p10"),
            Path("/var/lib/yatl/p10/p10-forward.sqlite3"),
            Path("/var/lib/yatl/p10/nested/file"),
        )
        for candidate in candidates:
            with self.subTest(candidate=candidate):
                with self.assertRaises(acq.AcquisitionError):
                    acq.assert_safe_runtime_path(candidate)

    def test_register_input_cannot_point_into_p10_runtime(self):
        with self.assertRaises(acq.AcquisitionError):
            acq.load_acquisition_register(
                Path("/var/lib/yatl/p10/snapshot.json")
            )

    def test_unrelated_runtime_path_is_allowed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "crisis"
            self.assertEqual(
                acq.assert_safe_runtime_path(path),
                path.resolve(),
            )

    def test_timestamp_unit_transition_is_explicit(self):
        self.assertEqual(
            acq.source_timestamp_unit_for_day(
                date(2024, 12, 31)
            ),
            "MILLISECOND",
        )
        self.assertEqual(
            acq.source_timestamp_unit_for_day(
                date(2025, 1, 1)
            ),
            "MICROSECOND",
        )

    def test_archive_planner_uses_monthly_object_for_full_month(self):
        start = ms("2024-02-01T00:00:00Z")
        end = ms("2024-03-01T00:00:00Z")
        objects = acq.build_archive_objects(
            "BTCUSDT", "1h", start, end
        )
        self.assertEqual(len(objects), 1)
        self.assertEqual(objects[0].cadence, "monthly")
        self.assertEqual(objects[0].period, "2024-02")

    def test_archive_planner_uses_daily_edges_around_full_month(self):
        start = ms("2024-01-31T00:00:00Z")
        end = ms("2024-03-02T00:00:00Z")
        objects = acq.build_archive_objects(
            "BTCUSDT", "4h", start, end
        )
        self.assertEqual(
            [
                (item.cadence, item.period)
                for item in objects
            ],
            [
                ("daily", "2024-01-31"),
                ("monthly", "2024-02"),
                ("daily", "2024-03-01"),
            ],
        )

    def test_plan_rounds_transport_only_not_semantic_window(self):
        registration = minimal_registration(
            start="2024-01-01T00:07:00Z",
            end="2024-01-01T03:53:00Z",
        )
        plan = acq.plan_dataset(
            registration,
            "CRL-T001",
            "BTCUSDT",
            "1h",
        )
        self.assertEqual(
            plan.semantic_start_ms,
            ms("2024-01-01T00:07:00Z"),
        )
        self.assertEqual(
            plan.semantic_end_ms,
            ms("2024-01-01T03:53:00Z"),
        )
        self.assertEqual(
            plan.transport_start_ms,
            ms("2024-01-01T00:00:00Z"),
        )
        self.assertEqual(
            plan.transport_end_ms,
            ms("2024-01-01T04:00:00Z"),
        )

    def test_checksum_parser_rejects_wrong_filename(self):
        with self.assertRaises(acq.AcquisitionError):
            acq.parse_checksum(
                (("a" * 64) + "  wrong.zip\n").encode(),
                "BTCUSDT-1h-2024-01-01.zip",
            )

    def test_microsecond_archive_normalizes_boundaries(self):
        start = ms("2025-01-01T00:00:00Z")
        plan = acq.DatasetPlan(
            event_id="CRL-T001",
            designation="DEVELOPMENT",
            replay_eligible=True,
            symbol="BTCUSDT",
            interval="1h",
            semantic_start_ms=start,
            semantic_end_ms=start + 3_600_000,
            transport_start_ms=start,
            transport_end_ms=start + 3_600_000,
            archive_objects=(),
        )
        archive = acq._archive_object(
            "daily",
            "BTCUSDT",
            "1h",
            "2025-01-01",
            date(2025, 1, 1),
        )
        output = io.StringIO(newline="")
        acq.csv.writer(
            output,
            lineterminator="\n",
        ).writerow(
            source_row(
                start,
                "1h",
                unit="MICROSECOND",
            )
        )
        rows = acq.normalize_archive_csv(
            output.getvalue().encode(),
            archive,
            plan,
        )
        self.assertEqual(rows[0].open_time_ms, start)
        self.assertEqual(
            rows[0].close_time_ms,
            start + 3_600_000 - 1,
        )

    def test_microsecond_archive_rejects_bad_submillisecond_boundary(self):
        start = ms("2025-01-01T00:00:00Z")
        plan = acq.DatasetPlan(
            event_id="CRL-T001",
            designation="DEVELOPMENT",
            replay_eligible=True,
            symbol="BTCUSDT",
            interval="1h",
            semantic_start_ms=start,
            semantic_end_ms=start + 3_600_000,
            transport_start_ms=start,
            transport_end_ms=start + 3_600_000,
            archive_objects=(),
        )
        archive = acq._archive_object(
            "daily",
            "BTCUSDT",
            "1h",
            "2025-01-01",
            date(2025, 1, 1),
        )
        row = source_row(
            start,
            "1h",
            unit="MICROSECOND",
        )
        row[0] = str(int(row[0]) + 1)
        output = io.StringIO(newline="")
        acq.csv.writer(
            output,
            lineterminator="\n",
        ).writerow(row)
        with self.assertRaises(acq.AcquisitionError):
            acq.normalize_archive_csv(
                output.getvalue().encode(),
                archive,
                plan,
            )

    def test_close_boundary_anomaly_is_rest_verified_and_normalized(self):
        plan = acq.plan_dataset(
            minimal_registration(),
            "CRL-T001",
            "BTCUSDT",
            "1h",
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "crl"
            result = acq.acquire_dataset(
                plan,
                runtime_root=root,
                archive_fetcher=CloseBoundaryArchiveFetcher(),
                rest_fetcher=MockRestFetcher(),
                retrieved_at_utc="2026-09-24T18:00:00Z",
            )
            self.assertEqual(
                result["acquisition_status"],
                "ACQUIRED_NEEDS_CRL003",
            )
            self.assertEqual(
                result["canonical"][
                    "close_boundary_normalization_count"
                ],
                1,
            )
            self.assertEqual(
                result["canonical"][
                    "close_boundary_rest_verified_count"
                ],
                1,
            )
            source = result["source_objects"][0]
            self.assertEqual(
                source["close_boundary_normalization_count"],
                1,
            )
            self.assertEqual(
                source["close_boundary_rest_verified_count"],
                1,
            )

    def test_empty_exact_rest_window_retries_by_open_time(self):
        start = ms("2024-01-01T00:00:00Z")
        target = acq.CanonicalRow(
            tuple(source_row(start, "1h"))
        )
        result = acq._verify_exact_rest_rows(
            [target],
            symbol="BTCUSDT",
            interval="1h",
            fetcher=MockRestFetcher(empty_exact_window=True),
        )
        self.assertEqual(result["status"], "MATCH")
        self.assertEqual(result["start_only_fallback_count"], 1)

    def test_rest_close_boundary_anomaly_is_canonicalized_for_exact_match(self):
        start = ms("2024-01-01T00:00:00Z")
        target = acq.CanonicalRow(
            tuple(source_row(start, "1h"))
        )
        result = acq._verify_exact_rest_rows(
            [target],
            symbol="BTCUSDT",
            interval="1h",
            fetcher=MockRestFetcher(close_boundary_anomaly=True),
        )
        self.assertEqual(result["status"], "MATCH")
        self.assertEqual(
            result["close_boundary_normalization_count"],
            1,
        )

    def test_close_boundary_anomaly_fails_on_rest_field_conflict(self):
        plan = acq.plan_dataset(
            minimal_registration(),
            "CRL-T001",
            "BTCUSDT",
            "1h",
        )
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(
                acq.AcquisitionError,
                "close-boundary anomaly conflicts with REST",
            ):
                acq.acquire_dataset(
                    plan,
                    runtime_root=Path(directory) / "crl",
                    archive_fetcher=CloseBoundaryArchiveFetcher(),
                    rest_fetcher=MockRestFetcher(mismatch=True),
                    retrieved_at_utc="2026-09-24T18:00:00Z",
                )

    def test_dataset_acquisition_is_immutable_and_structural_only(self):
        plan = acq.plan_dataset(
            minimal_registration(),
            "CRL-T001",
            "BTCUSDT",
            "1h",
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "crl"
            result = acq.acquire_dataset(
                plan,
                runtime_root=root,
                archive_fetcher=MockArchiveFetcher(),
                rest_fetcher=MockRestFetcher(),
                retrieved_at_utc="2026-09-22T21:00:00Z",
            )
            self.assertEqual(
                result["acquisition_status"],
                "ACQUIRED_NEEDS_CRL003",
            )
            self.assertEqual(
                result["quality_gate"],
                "PENDING_CRL003",
            )
            self.assertEqual(
                result["rest_verification"]["status"],
                "MATCH",
            )
            self.assertFalse(
                result["market_outcomes_exposed"]
            )
            self.assertFalse(
                result["p10_write_allowed"]
            )
            self.assertTrue(result["p11_locked"])

            manifest = root / result[
                "manifest_relative_path"
            ]
            canonical = root / result[
                "canonical"
            ]["relative_path"]
            self.assertTrue(manifest.is_file())
            self.assertTrue(canonical.is_file())
            before = canonical.read_bytes()

            repeated = acq.acquire_dataset(
                plan,
                runtime_root=root,
                archive_fetcher=MockArchiveFetcher(),
                rest_fetcher=MockRestFetcher(),
                retrieved_at_utc="2026-09-22T21:00:00Z",
            )
            self.assertEqual(
                result["canonical"]["sha256"],
                repeated["canonical"]["sha256"],
            )
            self.assertEqual(
                result["canonical"]["relative_path"],
                repeated["canonical"]["relative_path"],
            )
            self.assertFalse(
                result["source_objects"][0]["archive_cache_hit"]
            )
            self.assertTrue(
                repeated["source_objects"][0]["archive_cache_hit"]
            )
            self.assertEqual(
                canonical.read_bytes(),
                before,
            )

    def test_rest_mismatch_quarantines_source_conflict(self):
        plan = acq.plan_dataset(
            minimal_registration(),
            "CRL-T001",
            "ETHUSDT",
            "4h",
        )
        with tempfile.TemporaryDirectory() as directory:
            result = acq.acquire_dataset(
                plan,
                runtime_root=Path(directory),
                archive_fetcher=MockArchiveFetcher(),
                rest_fetcher=MockRestFetcher(
                    mismatch=True
                ),
                retrieved_at_utc="2026-09-22T21:00:00Z",
            )
            self.assertEqual(
                result["acquisition_status"],
                "QUARANTINED_SOURCE_CONFLICT",
            )
            self.assertEqual(
                result["quality_gate"],
                "PENDING_CRL003",
            )

    def test_full_event_has_exact_six_structural_datasets(self):
        with tempfile.TemporaryDirectory() as directory:
            result = acq.acquire_event(
                minimal_registration(),
                "CRL-T001",
                runtime_root=Path(directory),
                archive_fetcher=MockArchiveFetcher(),
                rest_fetcher=MockRestFetcher(),
                retrieved_at_utc="2026-09-22T21:00:00Z",
            )
            self.assertEqual(
                result["overall_status"],
                "COMPLETE",
            )
            self.assertEqual(
                result["dataset_count"],
                6,
            )
            self.assertEqual(
                {
                    (
                        item["symbol"],
                        item["interval"],
                    )
                    for item in result["datasets"]
                },
                {
                    ("BTCUSDT", "15m"),
                    ("BTCUSDT", "1h"),
                    ("BTCUSDT", "4h"),
                    ("ETHUSDT", "15m"),
                    ("ETHUSDT", "1h"),
                    ("ETHUSDT", "4h"),
                },
            )

    def test_holdout_manifest_exposes_no_outcome_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            result = acq.acquire_event(
                minimal_registration(
                    designation="BLIND_HOLDOUT"
                ),
                "CRL-T001",
                runtime_root=Path(directory),
                archive_fetcher=MockArchiveFetcher(),
                rest_fetcher=MockRestFetcher(),
                retrieved_at_utc="2026-09-22T21:00:00Z",
            )
            encoded = json.dumps(
                result,
                sort_keys=True,
            ).lower()
            for forbidden in (
                '"pnl"',
                '"return"',
                '"drawdown"',
                '"profit"',
                '"loss"',
                '"volatility_rank"',
                '"trade_result"',
                '"price"',
            ):
                with self.subTest(forbidden=forbidden):
                    self.assertNotIn(
                        forbidden,
                        encoded,
                    )
            self.assertEqual(
                result["designation"],
                "BLIND_HOLDOUT",
            )
            self.assertFalse(
                result["market_outcomes_exposed"]
            )

    def test_replay_ineligible_event_stays_ineligible(self):
        with tempfile.TemporaryDirectory() as directory:
            result = acq.acquire_event(
                minimal_registration(
                    replay_eligible=False
                ),
                "CRL-T001",
                runtime_root=Path(directory),
                archive_fetcher=MockArchiveFetcher(),
                rest_fetcher=None,
                retrieved_at_utc="2026-09-22T21:00:00Z",
            )
            self.assertFalse(
                result["replay_eligible"]
            )
            self.assertEqual(
                result["quality_gate"],
                "PENDING_CRL003",
            )

    def test_plan_is_no_network_and_no_market_outcome(self):
        plan = acq.plan_event(
            minimal_registration(),
            "CRL-T001",
        )
        self.assertFalse(
            plan["market_data_downloaded"]
        )
        self.assertFalse(
            plan["market_outcomes_exposed"]
        )
        self.assertEqual(
            len(plan["datasets"]),
            6,
        )

    def test_https_fetcher_records_bounded_retry_provenance(self):
        class Response:
            status = 200
            headers = {}

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self, size):
                return b"ok"

        class Opener:
            def __init__(self):
                self.calls = 0

            def open(self, request, timeout):
                self.calls += 1
                if self.calls == 1:
                    raise urllib.error.HTTPError(
                        request.full_url,
                        500,
                        "server error",
                        {},
                        None,
                    )
                return Response()

        fetcher = acq.HttpsFetcher(
            (acq.ARCHIVE_HOST,),
            attempts=2,
            sleeper=lambda _: None,
        )
        fetcher._opener = Opener()
        url = "https://data.binance.vision/test"
        self.assertEqual(
            fetcher.fetch(url, max_bytes=10),
            b"ok",
        )
        summary = fetcher.transport_summary(url)
        self.assertEqual(summary["attempts"], 2)
        self.assertEqual(summary["final_outcome"], "SUCCESS")
        self.assertEqual(len(summary["failures"]), 1)
        self.assertEqual(
            summary["failures"][0]["http_status"],
            500,
        )

    def test_https_guard_rejects_wrong_sources(self):
        urls = (
            "http://data.binance.vision/a",
            "https://evil.example/a",
            "https://user:pass@data.binance.vision/a",
            "https://data.binance.vision:8443/a",
        )
        for url in urls:
            with self.subTest(url=url):
                with self.assertRaises(
                    acq.AcquisitionError
                ):
                    acq._validate_https_url(
                        url,
                        (acq.ARCHIVE_HOST,),
                    )

    def test_source_has_no_execution_account_secret_or_ai_capability(self):
        source = inspect.getsource(acq)
        forbidden = (
            "from yatl.execution",
            "import yatl.execution",
            "from yatl.account",
            "import yatl.account",
            "from yatl.risk",
            "import yatl.risk",
            "from yatl.notifications",
            "import yatl.notifications",
            "os.getenv",
            "os.environ",
            "API_KEY",
            "API_SECRET",
            "openai",
            "anthropic",
            "websockets",
            "/api/v3/order",
            "/fapi",
            "/dapi",
            "withdraw(",
        )
        for value in forbidden:
            with self.subTest(forbidden=value):
                self.assertNotIn(value, source)


if __name__ == "__main__":
    unittest.main()
