import csv
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from research.crisis_lab import acquisition as acq
from research.crisis_lab import replay


START_MS = 1_704_067_200_000
END_MS = START_MS + 12 * 86_400_000


def canonical_json(record):
    return (
        json.dumps(record, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def write_bound(root, relative, payload):
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)


def canonical_payload(interval):
    duration = acq.INTERVAL_MILLISECONDS[interval]
    out = io.StringIO(newline="")
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(acq.CANONICAL_COLUMNS)
    for index, open_ms in enumerate(
        range(START_MS, END_MS, duration)
    ):
        price = 100000 + index
        writer.writerow([
            str(open_ms),
            str(price),
            str(price + 2),
            str(price - 1),
            str(price + 1),
            "10",
            str(open_ms + duration - 1),
            "100",
            "1",
            "5",
            "50",
            "0",
        ])
    return out.getvalue().encode("utf-8")


def build_runtime(root, *, designation="DEVELOPMENT"):
    dataset_event_refs = []
    event_quality_refs = []
    for symbol in acq.ALLOWED_SYMBOLS:
        for interval in acq.ALLOWED_INTERVALS:
            payload = canonical_payload(interval)
            canonical_sha = hashlib.sha256(payload).hexdigest()
            canonical_rel = (
                Path("canonical")
                / "event-catalog-v0.1.0"
                / "CRL-T004"
                / symbol
                / interval
                / f"dataset-{canonical_sha}.csv"
            )
            write_bound(root, canonical_rel, payload)
            row_count = (
                (END_MS - START_MS)
                // acq.INTERVAL_MILLISECONDS[interval]
            )

            acquisition = {
                "schema": (
                    "YATL_CRL_DATASET_ACQUISITION_PROVENANCE"
                ),
                "schema_version": "0.1.0",
                "event_id": "CRL-T004",
                "designation": designation,
                "replay_eligible": True,
                "symbol": symbol,
                "interval": interval,
                "research_only": True,
                "p10_write_allowed": False,
                "p11_locked": True,
                "canonical": {
                    "relative_path": canonical_rel.as_posix(),
                    "sha256": canonical_sha,
                    "row_count": row_count,
                    "expected_row_count": row_count,
                },
            }
            acq_payload = canonical_json(acquisition)
            acq_sha = hashlib.sha256(acq_payload).hexdigest()
            acq_rel = (
                Path("manifests")
                / "event-catalog-v0.1.0"
                / "CRL-T004"
                / symbol
                / interval
                / f"acquisition-{acq_sha[:24]}.json"
            )
            write_bound(root, acq_rel, acq_payload)
            dataset_event_refs.append({
                "symbol": symbol,
                "interval": interval,
                "manifest_relative_path": (
                    acq_rel.as_posix()
                ),
                "manifest_file_sha256": acq_sha,
            })

            quality = {
                "schema": "YATL_CRL_DATASET_QUALITY_MANIFEST",
                "schema_version": "0.1.0",
                "event_id": "CRL-T004",
                "designation": designation,
                "replay_eligible": True,
                "symbol": symbol,
                "interval": interval,
                "input_acquisition_manifest_relative_path": (
                    acq_rel.as_posix()
                ),
                "input_acquisition_manifest_sha256": acq_sha,
                "quality_status": "PASS",
                "replay_admitted": True,
                "failure_codes": [],
                "canonical_evidence": {
                    "canonical_sha256": canonical_sha,
                    "row_count": row_count,
                    "expected_row_count": row_count,
                    "first_open_time_ms": START_MS,
                    "last_open_time_ms": (
                        END_MS
                        - acq.INTERVAL_MILLISECONDS[interval]
                    ),
                },
                "market_outcomes_exposed": False,
                "research_only": True,
                "p10_write_allowed": False,
                "p11_locked": True,
            }
            quality_payload = canonical_json(quality)
            quality_sha = hashlib.sha256(
                quality_payload
            ).hexdigest()
            quality_rel = (
                Path("quality")
                / "event-catalog-v0.1.0"
                / "CRL-T004"
                / symbol
                / interval
                / f"quality-{quality_sha[:24]}.json"
            )
            write_bound(root, quality_rel, quality_payload)
            event_quality_refs.append({
                "symbol": symbol,
                "interval": interval,
                "quality_status": "PASS",
                "replay_admitted": True,
                "failure_codes": [],
                "quality_manifest_relative_path": (
                    quality_rel.as_posix()
                ),
                "quality_manifest_file_sha256": quality_sha,
            })

    event_acquisition = {
        "schema": "YATL_CRL_EVENT_ACQUISITION_PROVENANCE",
        "schema_version": "0.1.0",
        "event_id": "CRL-T004",
        "designation": designation,
        "replay_eligible": True,
        "retrieved_at_utc": "2026-09-24T00:00:00Z",
        "overall_status": "COMPLETE",
        "datasets": dataset_event_refs,
        "failures": [],
        "research_only": True,
        "p10_write_allowed": False,
        "p11_locked": True,
    }
    event_acq_payload = canonical_json(event_acquisition)
    event_acq_sha = hashlib.sha256(
        event_acq_payload
    ).hexdigest()
    event_acq_rel = (
        Path("manifests")
        / "event-catalog-v0.1.0"
        / "CRL-T004"
        / f"event-acquisition-{event_acq_sha[:24]}.json"
    )
    write_bound(root, event_acq_rel, event_acq_payload)

    event_quality = {
        "schema": "YATL_CRL_EVENT_QUALITY_MANIFEST",
        "schema_version": "0.1.0",
        "event_id": "CRL-T004",
        "designation": designation,
        "replay_eligible": True,
        "input_event_acquisition_manifest_relative_path": (
            event_acq_rel.as_posix()
        ),
        "input_event_acquisition_manifest_sha256": event_acq_sha,
        "dataset_count": 6,
        "pass_count": 6,
        "fail_count": 0,
        "overall_status": "PASS",
        "replay_admitted": True,
        "admission_reason": "QUALITY_PASS",
        "datasets": event_quality_refs,
        "market_outcomes_exposed": False,
        "research_only": True,
        "p10_write_allowed": False,
        "p11_locked": True,
        "trade_permission": False,
        "order_endpoint": False,
        "ai_direct_execution": False,
    }
    event_quality_payload = canonical_json(event_quality)
    event_quality_sha = hashlib.sha256(
        event_quality_payload
    ).hexdigest()
    event_quality_rel = (
        Path("quality")
        / "event-catalog-v0.1.0"
        / "CRL-T004"
        / f"event-quality-{event_quality_sha[:24]}.json"
    )
    write_bound(root, event_quality_rel, event_quality_payload)
    return event_quality_rel.as_posix(), event_quality_sha


class CrisisLabReplayTests(unittest.TestCase):
    def test_admitted_development_event_replays_deterministically(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            relative, digest = build_runtime(root)
            first = replay.replay_event(
                runtime_root=root,
                quality_manifest_relative_path=relative,
                quality_manifest_file_sha256=digest,
            )
            second = replay.replay_event(
                runtime_root=root,
                quality_manifest_relative_path=relative,
                quality_manifest_file_sha256=digest,
            )
            self.assertEqual(
                first["replay_manifest_file_sha256"],
                second["replay_manifest_file_sha256"],
            )
            self.assertTrue(
                first["deterministic_replay_verified"]
            )
            self.assertTrue(first["point_in_time_verified"])
            self.assertFalse(
                first["future_data_visible_to_strategy"]
            )
            self.assertFalse(
                first["post_event_label_visible_to_strategy"]
            )
            self.assertEqual(
                [
                    item["symbol"]
                    for item in first["symbols"]
                ],
                ["BTCUSDT", "ETHUSDT"],
            )
            for item in first["symbols"]:
                self.assertGreater(item["event_count"], 0)
                self.assertEqual(item["entries_blocked"], 0)
                self.assertEqual(item["fills"], [])
                self.assertEqual(
                    item["economics"][
                        "net_pnl_after_costs_quote"
                    ],
                    "0",
                )
                self.assertEqual(
                    item["economics"]["completed_trades"], 0
                )
                self.assertTrue(
                    item["point_in_time_verified"]
                )

    def test_quality_manifest_digest_tamper_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            relative, _ = build_runtime(root)
            with self.assertRaises(replay.ReplayError):
                replay.replay_event(
                    runtime_root=root,
                    quality_manifest_relative_path=relative,
                    quality_manifest_file_sha256="0" * 64,
                )

    def test_holdout_is_rejected_before_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            relative, digest = build_runtime(
                root, designation="BLIND_HOLDOUT"
            )
            with self.assertRaises(replay.ReplayError):
                replay.replay_event(
                    runtime_root=root,
                    quality_manifest_relative_path=relative,
                    quality_manifest_file_sha256=digest,
                )

    def test_p10_runtime_root_is_forbidden(self):
        with self.assertRaises(replay.ReplayError):
            replay.replay_event(
                runtime_root=Path("/var/lib/yatl/p10"),
                quality_manifest_relative_path=(
                    "quality/event-catalog-v0.1.0/CRL-X/"
                    "event-quality-" + "0" * 24 + ".json"
                ),
                quality_manifest_file_sha256="0" * 64,
            )

    def test_summary_is_bounded_and_records_no_p10_effect(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            relative, digest = build_runtime(root)
            result = replay.replay_event(
                runtime_root=root,
                quality_manifest_relative_path=relative,
                quality_manifest_file_sha256=digest,
            )
            summary = replay.safe_summary(result)
            self.assertFalse(summary["p10_read"])
            self.assertFalse(summary["p10_write_allowed"])
            self.assertEqual(
                summary["p10_evidence_effect"], "NONE"
            )
            self.assertTrue(summary["p11_locked"])
            self.assertNotIn(
                '"trace"', json.dumps(summary)
            )

    def test_replay_source_has_no_network_or_execution_capability(self):
        import inspect

        source = inspect.getsource(replay)
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
