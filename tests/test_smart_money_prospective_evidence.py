"""Offline-only validation of private V3.1 forward evidence receipts."""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import tempfile
import time
import unittest
from unittest.mock import patch

from research.smart_money_lab.prospective_evidence import (
    EvidenceJournal, audit_journal, read_journal,
)


def source_times():
    now = int(time.time())
    # cutoff < chain < observed < decision with observed later than chain+134.
    return now, now - 600, now - 400, now - 320, now - 270


class JournalTests(unittest.TestCase):
    def test_hash_chained_private_journal_and_sanitized_coverage(self):
        now, cutoff, chain, observed, quote_at = source_times()
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "raw" / "evidence.jsonl"
            with EvidenceJournal(path) as writer:
                writer.signal(wallet="WALLET_PRIVATE_A", mint="MINT_PRIVATE_X",
                              signature="SIG_PRIVATE_1", side="BUY",
                              chain_time=chain, observed_at=observed)
                writer.quote(mint="MINT_PRIVATE_X", captured_at=quote_at,
                             price_usd="0.01005", liquidity_usd="50000")
                self.assertEqual(writer.sequence, 2)
            records, digest = read_journal(path)
            self.assertEqual(len(records), 2)
            self.assertEqual(records[-1]["record_sha256"], digest)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            outcome = audit_journal(path, cutoff=cutoff)
            self.assertEqual(outcome["signal_receipt_rows"], 1)
            self.assertEqual(outcome["indicative_quote_receipt_rows"], 1)
            self.assertEqual(outcome["coverage"]["indicative_quotes_available"], 1)
            self.assertIsNone(outcome["coverage"]["realized_or_copy_pnl"])
            for marker in ("WALLET_PRIVATE_A", "SIG_PRIVATE_1", "MINT_PRIVATE_X"):
                self.assertNotIn(marker, json.dumps(outcome))

    def test_journal_can_resume_without_rewriting_prior_evidence(self):
        now, cutoff, chain, observed, quote_at = source_times()
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "evidence.jsonl"
            with EvidenceJournal(path) as writer:
                writer.signal(wallet="WALLET_PRIVATE_A", mint="MINT_PRIVATE_X",
                              signature="SIG_PRIVATE_1", side="BUY",
                              chain_time=chain, observed_at=observed)
            original = path.read_bytes()
            with EvidenceJournal(path) as writer:
                self.assertEqual(writer.sequence, 1)
                writer.quote(mint="MINT_PRIVATE_X", captured_at=quote_at,
                             price_usd="1.0", liquidity_usd="30000")
            self.assertTrue(path.read_bytes().startswith(original))
            self.assertEqual(len(read_journal(path)[0]), 2)

    def test_tampered_or_truncated_entry_is_rejected(self):
        now, cutoff, chain, observed, quote_at = source_times()
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "evidence.jsonl"
            with EvidenceJournal(path) as writer:
                writer.signal(wallet="WALLET_PRIVATE_A", mint="MINT_PRIVATE_X",
                              signature="SIG_PRIVATE_1", side="BUY",
                              chain_time=chain, observed_at=observed)
            raw = path.read_bytes()
            path.write_bytes(raw.replace(b"SIG_PRIVATE_1", b"SIG_PRIVATE_9"))
            with self.assertRaisesRegex(ValueError, "hash chain"):
                read_journal(path)
            with self.assertRaisesRegex(ValueError, "hash chain"):
                EvidenceJournal(path)
            path.write_bytes(raw[:-1])
            with self.assertRaisesRegex(ValueError, "incomplete journal"):
                read_journal(path)

    def test_no_public_directory_no_relative_path_and_no_world_readable(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for bad in (Path("evidence.jsonl"), root / "public_html" / "evidence.jsonl"):
                with self.subTest(path=str(bad)):
                    with self.assertRaises(ValueError):
                        EvidenceJournal(bad)
            path = root / "journal.jsonl"
            path.write_text("", encoding="utf-8")
            os.chmod(path, 0o644)
            with self.assertRaises(PermissionError):
                EvidenceJournal(path)
            with self.assertRaises(PermissionError):
                read_journal(path)

    def test_symlink_and_concurrent_writer_are_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            real = root / "evidence.jsonl"
            link = root / "symlink.jsonl"
            with EvidenceJournal(real) as first:
                link.symlink_to(real)
                with self.assertRaises((OSError, ValueError)):
                    EvidenceJournal(link)
                with self.assertRaises((OSError, ValueError)):
                    EvidenceJournal(real)

    def test_quote_payload_cannot_be_self_declared_future_or_invalid(self):
        now, cutoff, chain, observed, quote_at = source_times()
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "evidence.jsonl"
            with EvidenceJournal(path) as writer:
                with self.assertRaisesRegex(ValueError, "future"):
                    writer.quote(mint="MINT_PRIVATE_X", captured_at=now+3600,
                                 price_usd="1", liquidity_usd="50000")
                for bad in ("0", "-2", "NaN", "Infinity"):
                    with self.subTest(price=bad):
                        with self.assertRaisesRegex(ValueError, "payload"):
                            writer.quote(mint="MINT_PRIVATE_X", captured_at=now,
                                         price_usd=bad, liquidity_usd="50000")
                with self.assertRaisesRegex(ValueError, "payload"):
                    writer.signal(wallet="WALLET_PRIVATE_A", mint="MINT_PRIVATE_X",
                                  signature="SIG_PRIVATE_1", side="BUY",
                                  chain_time=observed+1, observed_at=observed)
                self.assertEqual(writer.sequence, 0)

    def test_quote_after_decision_is_not_used_as_historical_fill(self):
        now, cutoff, chain, observed, quote_at = source_times()
        # decision = max(now-320, now-266) = now-266.
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "evidence.jsonl"
            with EvidenceJournal(path) as writer:
                writer.signal(wallet="WALLET_PRIVATE_A", mint="MINT_PRIVATE_X",
                              signature="SIG_PRIVATE_1", side="BUY",
                              chain_time=chain, observed_at=observed)
                writer.quote(mint="MINT_PRIVATE_X", captured_at=now-260,
                             price_usd="1", liquidity_usd="50000")
            outcome = audit_journal(path, cutoff=cutoff)
            self.assertEqual(outcome["coverage"]["indicative_quotes_available"], 0)
            self.assertEqual(outcome["coverage"]["rejection_reasons"]["no_asof_quote"], 1)


if __name__ == "__main__":
    unittest.main()
