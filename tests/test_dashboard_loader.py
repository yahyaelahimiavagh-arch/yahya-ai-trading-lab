import hashlib
import json
import os
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

from yatl.analytics.cli import _export_payload
from yatl.analytics.quality import run_quality_gate
from yatl.analytics.quality_runtime import SNAPSHOT, _fixture
from yatl.dashboard.loader import (
    MAX_P7_EXPORT_BYTES,
    P7ExportLoadCode,
    P7ExportLoadError,
    load_p7_export,
)


def file_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class P7ExportLoaderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        source_root = self.root / "source"
        source_root.mkdir()
        self.p5, self.p6, specs = _fixture(source_root)
        gate = run_quality_gate(SNAPSHOT, specs)
        self.record, self.encoded = _export_payload(gate)
        self.path = self.root / "accepted.json"
        self.path.write_text(self.encoded, encoding="utf-8")
        self.expected = self.record["export_sha256"]

    def tearDown(self):
        self.temp.cleanup()

    def load(self):
        return load_p7_export(self.path, self.expected)

    def write_record(self, record, path=None):
        target = self.path if path is None else path
        target.write_text(
            json.dumps(
                record,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )
        return target

    def resign(self, record):
        material = {
            "schema_version": record["schema_version"],
            "quality": record["quality"],
            "analytics": record["analytics"],
        }
        record["export_sha256"] = hashlib.sha256(
            json.dumps(
                material,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        return record["export_sha256"]

    def test_load_is_deterministic_and_bound_to_expected_export_digest(self):
        first = self.load()
        second = self.load()
        self.assertEqual(first, second)
        self.assertEqual(first.export_sha256, self.expected)
        self.assertEqual(first.source.export_sha256, self.expected)
        self.assertEqual(
            first.segmentation_sha256,
            self.record["quality"]["accepted_chain"]["segmentation_sha256"],
        )

    def test_load_is_read_only_for_export_and_upstream_sources(self):
        before = (
            file_sha(self.path),
            file_sha(self.p5),
            file_sha(self.p6),
            self.path.stat().st_mtime_ns,
        )
        self.load()
        after = (
            file_sha(self.path),
            file_sha(self.p5),
            file_sha(self.p6),
            self.path.stat().st_mtime_ns,
        )
        self.assertEqual(before, after)

    def test_loaded_identity_is_frozen_and_preserves_paper_evidence_state(self):
        loaded = self.load()
        self.assertTrue(loaded.source.accepted)
        self.assertTrue(loaded.source.sanitized)
        self.assertTrue(loaded.source.read_only)
        self.assertEqual(
            loaded.source.strategy_evidence.value,
            "INSUFFICIENT_EVIDENCE",
        )
        with self.assertRaises(FrozenInstanceError):
            loaded.byte_length = 0

    def test_wrong_expected_export_digest_fails_closed(self):
        with self.assertRaises(P7ExportLoadError) as caught:
            load_p7_export(self.path, "0" * 64)
        self.assertEqual(caught.exception.code, P7ExportLoadCode.DIGEST_MISMATCH)

    def test_invalid_expected_digest_is_invalid_request(self):
        with self.assertRaises(P7ExportLoadError) as caught:
            load_p7_export(self.path, "bad")
        self.assertEqual(caught.exception.code, P7ExportLoadCode.INVALID_REQUEST)

    def test_missing_file_does_not_echo_path(self):
        missing = self.root / "sensitive-name.json"
        with self.assertRaises(P7ExportLoadError) as caught:
            load_p7_export(missing, self.expected)
        self.assertEqual(caught.exception.code, P7ExportLoadCode.NOT_FOUND)
        self.assertNotIn(str(missing), str(caught.exception))

    def test_symlink_is_rejected(self):
        link = self.root / "link.json"
        try:
            link.symlink_to(self.path)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        with self.assertRaises(P7ExportLoadError) as caught:
            load_p7_export(link, self.expected)
        self.assertEqual(caught.exception.code, P7ExportLoadCode.STORAGE_ERROR)

    def test_oversized_input_is_rejected_before_json_processing(self):
        oversized = self.root / "oversized.json"
        with oversized.open("wb") as stream:
            stream.truncate(MAX_P7_EXPORT_BYTES + 1)
        with self.assertRaises(P7ExportLoadError) as caught:
            load_p7_export(oversized, self.expected)
        self.assertEqual(caught.exception.code, P7ExportLoadCode.TOO_LARGE)

    def test_invalid_utf8_is_rejected(self):
        self.path.write_bytes(b"\xff\xfe")
        with self.assertRaises(P7ExportLoadError) as caught:
            self.load()
        self.assertEqual(caught.exception.code, P7ExportLoadCode.INVALID_UTF8)

    def test_duplicate_json_key_is_rejected(self):
        self.path.write_text(
            '{"analytics":{},"analytics":{},"export_sha256":"' + "0" * 64
            + '","quality":{},"schema_version":1}\n',
            encoding="utf-8",
        )
        with self.assertRaises(P7ExportLoadError) as caught:
            self.load()
        self.assertEqual(caught.exception.code, P7ExportLoadCode.DUPLICATE_KEY)

    def test_noncanonical_whitespace_is_rejected(self):
        parsed = json.loads(self.encoded)
        self.path.write_text(json.dumps(parsed, indent=2) + "\n", encoding="utf-8")
        with self.assertRaises(P7ExportLoadError) as caught:
            self.load()
        self.assertEqual(caught.exception.code, P7ExportLoadCode.NONCANONICAL)

    def test_missing_terminal_newline_is_noncanonical(self):
        self.path.write_text(self.encoded.rstrip("\n"), encoding="utf-8")
        with self.assertRaises(P7ExportLoadError) as caught:
            self.load()
        self.assertEqual(caught.exception.code, P7ExportLoadCode.NONCANONICAL)

    def test_unsupported_export_version_is_rejected_even_if_resigned(self):
        record = json.loads(self.encoded)
        record["schema_version"] = 2
        expected = self.resign(record)
        self.write_record(record)
        with self.assertRaises(P7ExportLoadError) as caught:
            load_p7_export(self.path, expected)
        self.assertEqual(caught.exception.code, P7ExportLoadCode.UNSUPPORTED_VERSION)

    def test_unknown_top_level_field_is_schema_smuggling(self):
        record = json.loads(self.encoded)
        record["trade_permission"] = True
        expected = self.resign(record)
        self.write_record(record)
        with self.assertRaises(P7ExportLoadError) as caught:
            load_p7_export(self.path, expected)
        self.assertEqual(caught.exception.code, P7ExportLoadCode.SCHEMA_INVALID)

    def test_secret_bearing_nested_field_is_rejected_even_if_resigned(self):
        record = json.loads(self.encoded)
        record["quality"]["credential"] = "should-never-appear"
        expected = self.resign(record)
        self.write_record(record)
        with self.assertRaises(P7ExportLoadError) as caught:
            load_p7_export(self.path, expected)
        self.assertEqual(caught.exception.code, P7ExportLoadCode.SECRET_BEARING)

    def test_quality_must_be_pass_and_publication_allowed(self):
        for key, value in (("status", "FAIL"), ("publication_allowed", False)):
            record = json.loads(self.encoded)
            record["quality"][key] = value
            expected = self.resign(record)
            self.write_record(record)
            with self.subTest(key=key), self.assertRaises(P7ExportLoadError) as caught:
                load_p7_export(self.path, expected)
            self.assertEqual(caught.exception.code, P7ExportLoadCode.QUALITY_REJECTED)

    def test_quality_safety_cannot_be_weakened(self):
        record = json.loads(self.encoded)
        record["quality"]["safety"]["trade_permission"] = True
        expected = self.resign(record)
        self.write_record(record)
        with self.assertRaises(P7ExportLoadError) as caught:
            load_p7_export(self.path, expected)
        self.assertEqual(caught.exception.code, P7ExportLoadCode.SAFETY_MISMATCH)

    def test_analytics_safety_cannot_be_weakened(self):
        record = json.loads(self.encoded)
        record["analytics"]["safety"]["quantity_authority"] = True
        expected = self.resign(record)
        self.write_record(record)
        with self.assertRaises(P7ExportLoadError) as caught:
            load_p7_export(self.path, expected)
        self.assertEqual(caught.exception.code, P7ExportLoadCode.SAFETY_MISMATCH)

    def test_strategy_evidence_cannot_be_upgraded(self):
        record = json.loads(self.encoded)
        record["analytics"]["strategy_evidence"] = "PROVEN_EDGE"
        expected = self.resign(record)
        self.write_record(record)
        with self.assertRaises(P7ExportLoadError) as caught:
            load_p7_export(self.path, expected)
        self.assertEqual(caught.exception.code, P7ExportLoadCode.IDENTITY_MISMATCH)

    def test_quality_chain_must_match_segmentation_identity(self):
        record = json.loads(self.encoded)
        record["quality"]["accepted_chain"]["segmentation_sha256"] = "0" * 64
        expected = self.resign(record)
        self.write_record(record)
        with self.assertRaises(P7ExportLoadError) as caught:
            load_p7_export(self.path, expected)
        self.assertEqual(caught.exception.code, P7ExportLoadCode.DIGEST_MISMATCH)

    def test_chain_symbol_and_counts_must_match_analytics(self):
        for key, value in (
            ("symbol", "ETHUSDT"),
            ("completed_trade_count", 999),
            ("analyst_trace_count", 999),
        ):
            record = json.loads(self.encoded)
            record["quality"]["accepted_chain"][key] = value
            expected = self.resign(record)
            self.write_record(record)
            with self.subTest(key=key), self.assertRaises(P7ExportLoadError) as caught:
                load_p7_export(self.path, expected)
            self.assertEqual(caught.exception.code, P7ExportLoadCode.IDENTITY_MISMATCH)

    def test_segment_digest_tampering_is_detected_even_if_export_is_resigned(self):
        record = json.loads(self.encoded)
        self.assertTrue(record["analytics"]["trade_segments"])
        record["analytics"]["trade_segments"][0]["segment_sha256"] = "0" * 64
        record["quality"]["accepted_chain"]["segmentation_sha256"] = hashlib.sha256(
            json.dumps(
                record["analytics"],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        expected = self.resign(record)
        self.write_record(record)
        with self.assertRaises(P7ExportLoadError) as caught:
            load_p7_export(self.path, expected)
        self.assertEqual(caught.exception.code, P7ExportLoadCode.DIGEST_MISMATCH)

    def test_loaded_record_reopens_to_exact_canonical_payload(self):
        loaded = self.load()
        self.assertEqual(loaded.record(), json.loads(self.encoded))
        self.assertEqual(
            loaded.canonical_json.encode("utf-8"),
            self.path.read_bytes(),
        )


if __name__ == "__main__":
    unittest.main()
