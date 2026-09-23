import hashlib
import io
import json
import tempfile
import unittest
import urllib.parse
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path

from research.crisis_lab import acquisition as acq
from research.crisis_lab import quality


def ms(value):
    return int(
        datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        * 1000
    )


def minimal_registration(
    *,
    designation="DEVELOPMENT",
    replay_eligible=True,
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
                "event_id": "CRL-T003",
                "designation": designation,
                "replay_eligible": replay_eligible,
                "semantic_range": {
                    "start_utc": "2024-01-01T00:00:00Z",
                    "end_utc": "2024-01-01T04:00:00Z",
                },
            }
        ],
    }


def source_row(open_ms, interval, *, close="100"):
    duration = acq.INTERVAL_MILLISECONDS[interval]
    return [
        str(open_ms),
        "100",
        "101",
        "99",
        close,
        "1",
        str(open_ms + duration - 1),
        "100",
        "10",
        "0.5",
        "50",
        "0",
    ]


def source_csv(period, interval):
    start = datetime.fromisoformat(period + "T00:00:00+00:00")
    end = start + acq.timedelta(days=1)
    cursor = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)
    duration = acq.INTERVAL_MILLISECONDS[interval]
    output = io.StringIO(newline="")
    writer = acq.csv.writer(output, lineterminator="\n")
    while cursor < end_ms:
        writer.writerow(source_row(cursor, interval))
        cursor += duration
    return output.getvalue().encode("utf-8")


class MockArchiveFetcher:
    def __init__(self):
        self._zips = {}
        self._history = {}

    def _zip_for(self, url):
        if url in self._zips:
            return self._zips[url]
        name = urllib.parse.urlsplit(url).path.rsplit("/", 1)[-1]
        stem = name[:-4]
        parts = stem.split("-")
        interval = parts[1]
        period = "-".join(parts[2:])
        payload = source_csv(period, interval)
        out = io.BytesIO()
        with zipfile.ZipFile(
            out, "w", compression=zipfile.ZIP_DEFLATED
        ) as bundle:
            bundle.writestr(stem + ".csv", payload)
        self._zips[url] = out.getvalue()
        return self._zips[url]

    def fetch(self, url, *, max_bytes):
        self._history.setdefault(url, []).append(
            {"attempt": 1, "outcome": "SUCCESS", "http_status": 200}
        )
        if url.endswith(".CHECKSUM"):
            zip_url = url[:-9]
            payload = self._zip_for(zip_url)
            filename = urllib.parse.urlsplit(
                zip_url
            ).path.rsplit("/", 1)[-1]
            return (
                f"{hashlib.sha256(payload).hexdigest()}  {filename}\n"
            ).encode("utf-8")
        return self._zip_for(url)

    def transport_summary(self, url):
        events = tuple(self._history.get(url, ()))
        return {
            "attempts": len(events),
            "failures": [],
            "final_outcome": (
                events[-1]["outcome"] if events else "NOT_ATTEMPTED"
            ),
        }


class MockRestFetcher:
    def __init__(self):
        self._history = {}

    def fetch(self, url, *, max_bytes):
        self._history.setdefault(url, []).append(
            {"attempt": 1, "outcome": "SUCCESS", "http_status": 200}
        )
        query = urllib.parse.parse_qs(
            urllib.parse.urlsplit(url).query
        )
        interval = query["interval"][0]
        open_ms = int(query["startTime"][0])
        row = source_row(open_ms, interval)
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

    def transport_summary(self, url):
        events = tuple(self._history.get(url, ()))
        return {
            "attempts": len(events),
            "failures": [],
            "final_outcome": (
                events[-1]["outcome"] if events else "NOT_ATTEMPTED"
            ),
        }


def acquire_fixture(
    runtime_root,
    *,
    designation="DEVELOPMENT",
    replay_eligible=True,
):
    return acq.acquire_event(
        minimal_registration(
            designation=designation,
            replay_eligible=replay_eligible,
        ),
        "CRL-T003",
        runtime_root=runtime_root,
        archive_fetcher=MockArchiveFetcher(),
        rest_fetcher=MockRestFetcher(),
        retrieved_at_utc="2024-01-02T00:00:00Z",
    )


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


class CrisisLabQualityTests(unittest.TestCase):
    def test_realistic_acquired_event_passes_all_six_datasets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            acquired = acquire_fixture(root)
            result = quality.validate_event(
                runtime_root=root,
                event_manifest_relative_path=acquired[
                    "manifest_relative_path"
                ],
                event_manifest_sha256=acquired[
                    "manifest_file_sha256"
                ],
            )
            self.assertEqual(result["overall_status"], "PASS")
            self.assertEqual(result["dataset_count"], 6)
            self.assertEqual(result["pass_count"], 6)
            self.assertEqual(result["fail_count"], 0)
            self.assertTrue(result["replay_admitted"])
            self.assertFalse(result["market_outcomes_exposed"])

    def test_quality_output_is_deterministic_for_same_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            acquired = acquire_fixture(root)
            kwargs = {
                "runtime_root": root,
                "event_manifest_relative_path": acquired[
                    "manifest_relative_path"
                ],
                "event_manifest_sha256": acquired[
                    "manifest_file_sha256"
                ],
            }
            first = quality.validate_event(**kwargs)
            second = quality.validate_event(**kwargs)
            self.assertEqual(
                first["quality_manifest_file_sha256"],
                second["quality_manifest_file_sha256"],
            )
            self.assertEqual(
                first["quality_manifest_relative_path"],
                second["quality_manifest_relative_path"],
            )

    def test_event_manifest_digest_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            acquired = acquire_fixture(root)
            with self.assertRaises(quality.QualityError):
                quality.validate_event(
                    runtime_root=root,
                    event_manifest_relative_path=acquired[
                        "manifest_relative_path"
                    ],
                    event_manifest_sha256="0" * 64,
                )

    def test_p10_runtime_root_is_forbidden(self):
        with self.assertRaises(quality.QualityError):
            quality.validate_event(
                runtime_root=Path("/var/lib/yatl/p10"),
                event_manifest_relative_path="manifest.json",
                event_manifest_sha256="0" * 64,
            )

    def test_canonical_tamper_is_detected_without_value_exposure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            acquired = acquire_fixture(root)
            event_path = root / acquired["manifest_relative_path"]
            event = load_json(event_path)
            dataset_ref = event["datasets"][0]
            dataset_path = root / dataset_ref["manifest_relative_path"]
            dataset = load_json(dataset_path)
            canonical_path = root / dataset["canonical"]["relative_path"]
            canonical_path.write_bytes(
                canonical_path.read_bytes() + b"\n"
            )
            result = quality.validate_event(
                runtime_root=root,
                event_manifest_relative_path=acquired[
                    "manifest_relative_path"
                ],
                event_manifest_sha256=acquired[
                    "manifest_file_sha256"
                ],
            )
            self.assertEqual(result["overall_status"], "FAIL")
            failed = next(
                item
                for item in result["datasets"]
                if item["symbol"] == dataset_ref["symbol"]
                and item["interval"] == dataset_ref["interval"]
            )
            self.assertIn(
                "CANONICAL_DIGEST_MISMATCH",
                failed["failure_codes"],
            )
            safe = json.dumps(quality.safe_summary(result))
            self.assertNotIn('"open":', safe)
            self.assertNotIn('"close":', safe)
            self.assertNotIn('"return"', safe)
            self.assertNotIn('"pnl"', safe.lower())

    def test_dataset_content_address_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            acquired = acquire_fixture(root)
            event = load_json(root / acquired["manifest_relative_path"])
            dataset_ref = dict(event["datasets"][0])
            original = root / dataset_ref["manifest_relative_path"]
            wrong_rel = (
                Path(dataset_ref["manifest_relative_path"]).parent
                / "acquisition-000000000000000000000000.json"
            )
            target = root / wrong_rel
            target.write_bytes(original.read_bytes())
            dataset_ref["manifest_relative_path"] = wrong_rel.as_posix()
            report = quality.validate_dataset(
                runtime_root=root,
                event_manifest=event,
                dataset_ref=dataset_ref,
            )
            self.assertEqual(report["quality_status"], "FAIL")
            self.assertIn(
                "DATASET_MANIFEST_CONTENT_ADDRESS_MISMATCH",
                report["failure_codes"],
            )

    def test_replay_ineligible_event_can_quality_pass_but_not_admit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            acquired = acquire_fixture(
                root, replay_eligible=False
            )
            result = quality.validate_event(
                runtime_root=root,
                event_manifest_relative_path=acquired[
                    "manifest_relative_path"
                ],
                event_manifest_sha256=acquired[
                    "manifest_file_sha256"
                ],
            )
            self.assertEqual(result["overall_status"], "PASS")
            self.assertFalse(result["replay_admitted"])
            self.assertEqual(
                result["admission_reason"],
                "CATALOG_REPLAY_INELIGIBLE",
            )

    def test_blind_holdout_summary_is_structural_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            acquired = acquire_fixture(
                root, designation="BLIND_HOLDOUT"
            )
            result = quality.validate_event(
                runtime_root=root,
                event_manifest_relative_path=acquired[
                    "manifest_relative_path"
                ],
                event_manifest_sha256=acquired[
                    "manifest_file_sha256"
                ],
            )
            summary = quality.safe_summary(result)
            self.assertEqual(
                summary["designation"], "BLIND_HOLDOUT"
            )
            self.assertFalse(summary["market_outcomes_exposed"])
            rendered = json.dumps(summary).lower()
            for forbidden in (
                '"price"',
                '"return"',
                '"drawdown"',
                '"volatility"',
                '"trade_metrics"',
                '"pnl"',
            ):
                self.assertNotIn(forbidden, rendered)

    def test_invalid_ohlc_relation_fails_quality(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            event = {
                "event_id": "CRL-X001",
                "designation": "DEVELOPMENT",
                "replay_eligible": True,
            }
            interval = "1h"
            open_ms = ms("2024-01-01T00:00:00Z")
            row = [
                str(open_ms),
                "100",
                "90",
                "99",
                "100",
                "1",
                str(open_ms + 3600000 - 1),
                "100",
                "10",
                "0.5",
                "50",
                "0",
            ]
            out = io.StringIO(newline="")
            acq.csv.writer(out, lineterminator="\n").writerow(row)
            canonical_payload = out.getvalue().encode("utf-8")
            canonical_sha = hashlib.sha256(
                canonical_payload
            ).hexdigest()
            canonical_rel = (
                Path("canonical")
                / "event-catalog-v0.1.0"
                / "CRL-X001"
                / "BTCUSDT"
                / interval
                / f"dataset-{canonical_sha}.csv"
            )
            canonical_target = root / canonical_rel
            canonical_target.parent.mkdir(parents=True)
            canonical_target.write_bytes(canonical_payload)

            source_sha = "a" * 64
            dataset = {
                "schema": "YATL_CRL_DATASET_ACQUISITION_PROVENANCE",
                "schema_version": "0.1.0",
                "implementation_id": "CRL-002/0.1.0",
                "catalog_version": "0.1.0",
                "event_id": "CRL-X001",
                "designation": "DEVELOPMENT",
                "replay_eligible": True,
                "symbol": "BTCUSDT",
                "interval": interval,
                "semantic_range": {
                    "start_utc": "2024-01-01T00:00:00Z",
                    "end_utc": "2024-01-01T01:00:00Z",
                },
                "transport_range": {
                    "start_utc": "2024-01-01T00:00:00Z",
                    "end_utc": "2024-01-01T01:00:00Z",
                },
                "retrieved_at_utc": "2024-01-02T00:00:00Z",
                "source_objects": [{
                    "expected_zip_sha256": source_sha,
                    "downloaded_zip_sha256": source_sha,
                    "extracted_csv_sha256": "b" * 64,
                }],
                "canonical": {
                    "relative_path": canonical_rel.as_posix(),
                    "sha256": canonical_sha,
                    "row_count": 1,
                    "expected_row_count": 1,
                    "first_open_time_ms": open_ms,
                    "last_open_time_ms": open_ms,
                    "gap_count": 0,
                    "duplicate_count": 0,
                },
                "rest_verification": {"status": "MATCH"},
                "acquisition_status": "ACQUIRED_NEEDS_CRL003",
                "quality_gate": "PENDING_CRL003",
                "research_only": True,
                "p10_write_allowed": False,
                "p11_locked": True,
                "trade_permission": False,
                "order_endpoint": False,
                "ai_direct_execution": False,
            }
            dataset_payload = acq._canonical_json(dataset)
            dataset_sha = hashlib.sha256(dataset_payload).hexdigest()
            dataset_rel = (
                Path("manifests")
                / "event-catalog-v0.1.0"
                / "CRL-X001"
                / "BTCUSDT"
                / interval
                / f"acquisition-{dataset_sha[:24]}.json"
            )
            dataset_target = root / dataset_rel
            dataset_target.parent.mkdir(parents=True)
            dataset_target.write_bytes(dataset_payload)
            report = quality.validate_dataset(
                runtime_root=root,
                event_manifest=event,
                dataset_ref={
                    "symbol": "BTCUSDT",
                    "interval": interval,
                    "manifest_relative_path": dataset_rel.as_posix(),
                    "manifest_file_sha256": dataset_sha,
                },
            )
            self.assertEqual(report["quality_status"], "FAIL")
            self.assertIn(
                "HIGH_RELATION_INVALID", report["failure_codes"]
            )

    def test_quality_manifest_contains_no_market_values(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            acquired = acquire_fixture(root)
            result = quality.validate_event(
                runtime_root=root,
                event_manifest_relative_path=acquired[
                    "manifest_relative_path"
                ],
                event_manifest_sha256=acquired[
                    "manifest_file_sha256"
                ],
            )
            payload = (
                root / result["quality_manifest_relative_path"]
            ).read_text(encoding="utf-8").lower()
            for forbidden in (
                '"open":',
                '"high":',
                '"low":',
                '"close":',
                '"base_volume":',
                '"quote_volume":',
                '"return":',
                '"pnl":',
                '"drawdown":',
            ):
                self.assertNotIn(forbidden, payload)


if __name__ == "__main__":
    unittest.main()
