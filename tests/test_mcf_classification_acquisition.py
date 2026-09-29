import json
import tempfile
import unittest
from pathlib import Path

from research.mass_candidate_factory.classification_acquisition import (
    ACQUISITION_SCHEMA,
    load_acquisition,
    materialize,
)
from research.mass_candidate_factory.classification_wave import EXPECTED_SAFETY, load_wave
from research.mass_candidate_factory.models import MCFError, canonical
from research.mass_candidate_factory.production_binding_preflight import (
    _classification_evidence,
)

ROOT = Path(__file__).resolve().parents[1]
WAVE = ROOT / "docs/research/alpha-factory/MCF-PROD-001-CLASSIFICATION-WAVE-001.json"


def _ledger():
    wave, wave_sha = load_wave(WAVE)
    first = wave["frontier_symbols"][0]
    unresolved = {
        symbol: "SOURCE_REVIEW_PENDING"
        for symbol in wave["frontier_symbols"]
        if symbol != first
    }
    return {
        "entries": {
            first: {
                "classification": "ORDINARY_SPOT_CONFIRMED",
                "evidence_basis": "FIRST_PARTY_BINANCE_LISTING_ANNOUNCEMENT",
                "reviewed": True,
                "source_published_at": "2020-12-25T03:17:00Z",
                "source_reference": "https://www.binance.com/en/support/announcement/detail/example",
                "source_title": "Binance Will List Example",
            }
        },
        "generation_id": "MCF-PROD-001",
        "safety": EXPECTED_SAFETY,
        "schema": ACQUISITION_SCHEMA,
        "source_preflight_sha256": wave["source_preflight_sha256"],
        "state": "REVIEWED_BEFORE_PERFORMANCE",
        "unresolved": unresolved,
        "wave_id": wave["wave_id"],
        "wave_manifest_sha256": wave_sha,
    }


class ClassificationAcquisitionTest(unittest.TestCase):
    def test_exact_wave_accounting_is_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.json"
            doc = _ledger()
            doc["unresolved"].pop(next(iter(doc["unresolved"])))
            path.write_bytes(canonical(doc))
            with self.assertRaises(MCFError):
                load_acquisition(path, WAVE)

    def test_current_exchangeinfo_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.json"
            doc = _ledger()
            first = next(iter(doc["entries"]))
            doc["entries"][first]["source_reference"] = (
                "https://api.binance.com/api/v3/exchangeInfo?symbol=1INCHUSDT"
            )
            path.write_bytes(canonical(doc))
            with self.assertRaises(MCFError):
                load_acquisition(path, WAVE)

    def test_materialization_is_content_addressed_and_preflight_compatible(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ledger = root / "ledger.json"
            output = root / "out"
            output.mkdir()
            doc = _ledger()
            ledger.write_bytes(canonical(doc))

            result = materialize(
                acquisition_path=ledger,
                wave_path=WAVE,
                output_root=output,
            )

            self.assertEqual(result["resolved_count"], 1)
            self.assertEqual(result["unresolved_count"], 175)

            cmap = json.loads((output / result["classification_map"]).read_text())
            self.assertEqual(len(cmap["entries"]), 1)
            symbol, relative = next(iter(cmap["entries"].items()))
            classification, identity = _classification_evidence(
                output, symbol, relative
            )
            self.assertEqual(classification, "ORDINARY_SPOT_CONFIRMED")
            self.assertTrue(relative.endswith(f"{identity}.json"))

    def test_noncanonical_ledger_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.json"
            path.write_text("\n" + canonical(_ledger()).decode("utf-8"), encoding="utf-8")
            with self.assertRaises(MCFError):
                load_acquisition(path, WAVE)


if __name__ == "__main__":
    unittest.main()
