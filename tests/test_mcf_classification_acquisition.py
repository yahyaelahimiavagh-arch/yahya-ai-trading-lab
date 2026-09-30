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
WAVE2 = ROOT / "docs/research/alpha-factory/MCF-PROD-001-CLASSIFICATION-WAVE-002.json"
SHARDS = ROOT / "docs/research/alpha-factory/classification-wave-001"
WAVE2_SHARDS = ROOT / "docs/research/alpha-factory/classification-wave-002"


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


def _wave2_ledger():
    wave, wave_sha = load_wave(WAVE2)
    entries = {}
    for symbol in wave["frontier_symbols"]:
        entries[symbol] = {
            "classification": "ORDINARY_SPOT_CONFIRMED",
            "evidence_basis": "FIRST_PARTY_BINANCE_HISTORICAL_SPOT_PAIR_RECORD",
            "reviewed": True,
            "source_published_at": "2020-01-01T00:00:00Z",
            "source_reference": (
                "https://www.binance.com/en/support/announcement/detail/"
                + symbol.lower()
            ),
            "source_title": f"Historical Spot record for {symbol}",
        }
    return {
        "entries": entries,
        "generation_id": "MCF-PROD-001",
        "safety": EXPECTED_SAFETY,
        "schema": ACQUISITION_SCHEMA,
        "source_preflight_sha256": wave["source_preflight_sha256"],
        "state": "REVIEWED_BEFORE_PERFORMANCE",
        "unresolved": {},
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

    def test_frozen_source_shards_cover_wave_and_materialize(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "out"
            output.mkdir()

            result = materialize(
                source_shards_dir=SHARDS,
                wave_path=WAVE,
                output_root=output,
            )

            self.assertEqual(result["resolved_count"], 176)
            self.assertEqual(result["unresolved_count"], 0)

            wave, _ = load_wave(WAVE)
            cmap = json.loads((output / result["classification_map"]).read_text())
            self.assertEqual(
                set(cmap["entries"]),
                set(wave["frontier_symbols"]),
            )

            classifications = {}
            for symbol, relative in cmap["entries"].items():
                classification, identity = _classification_evidence(
                    output, symbol, relative
                )
                classifications[classification] = (
                    classifications.get(classification, 0) + 1
                )
                self.assertTrue(relative.endswith(f"{identity}.json"))

            self.assertEqual(
                classifications,
                {
                    "NONORDINARY_CONFIRMED": 3,
                    "ORDINARY_SPOT_CONFIRMED": 173,
                },
            )

    def test_later_wave_extends_prior_map_without_replacing_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "out"
            output.mkdir()

            first = materialize(
                source_shards_dir=SHARDS,
                wave_path=WAVE,
                output_root=output,
            )
            first_map = json.loads(
                (output / first["classification_map"]).read_text()
            )
            btc_relative = first_map["entries"]["BTCUSDT"]

            ledger = root / "wave2-ledger.json"
            ledger.write_bytes(canonical(_wave2_ledger()))
            second = materialize(
                acquisition_path=ledger,
                wave_path=WAVE2,
                output_root=output,
                base_classification_map=first["classification_map"],
            )

            self.assertEqual(second["resolved_count"], 2)
            self.assertEqual(second["unresolved_count"], 0)
            self.assertEqual(second["cumulative_resolved_count"], 178)
            self.assertEqual(
                second["base_classification_map_sha256"],
                first["classification_map_sha256"],
            )

            cumulative = json.loads(
                (output / second["classification_map"]).read_text()
            )
            self.assertEqual(len(cumulative["entries"]), 178)
            self.assertEqual(cumulative["entries"]["BTCUSDT"], btc_relative)
            self.assertIn("BTSUSDT", cumulative["entries"])
            self.assertIn("OCEANUSDT", cumulative["entries"])

    def test_frozen_wave2_source_shard_extends_wave1_cumulatively(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "out"
            output.mkdir()

            first = materialize(
                source_shards_dir=SHARDS,
                wave_path=WAVE,
                output_root=output,
            )
            second = materialize(
                source_shards_dir=WAVE2_SHARDS,
                wave_path=WAVE2,
                output_root=output,
                base_classification_map=first["classification_map"],
            )

            self.assertEqual(second["resolved_count"], 2)
            self.assertEqual(second["unresolved_count"], 0)
            self.assertEqual(second["cumulative_resolved_count"], 178)
            cumulative = json.loads(
                (output / second["classification_map"]).read_text()
            )
            self.assertEqual(len(cumulative["entries"]), 178)
            for symbol in ("BTSUSDT", "OCEANUSDT"):
                classification, identity = _classification_evidence(
                    output, symbol, cumulative["entries"][symbol]
                )
                self.assertEqual(classification, "ORDINARY_SPOT_CONFIRMED")
                self.assertTrue(
                    cumulative["entries"][symbol].endswith(f"{identity}.json")
                )

    def test_overlap_is_rejected_before_new_evidence_is_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "out"
            output.mkdir()

            ledger = root / "wave2-ledger.json"
            ledger.write_bytes(canonical(_wave2_ledger()))
            first = materialize(
                acquisition_path=ledger,
                wave_path=WAVE2,
                output_root=output,
            )

            changed = _wave2_ledger()
            changed["entries"]["BTSUSDT"]["source_title"] += " changed"
            changed_ledger = root / "wave2-changed-ledger.json"
            changed_ledger.write_bytes(canonical(changed))
            before = {
                path.relative_to(output)
                for path in output.rglob("*")
                if path.is_file()
            }

            with self.assertRaises(MCFError):
                materialize(
                    acquisition_path=changed_ledger,
                    wave_path=WAVE2,
                    output_root=output,
                    base_classification_map=first["classification_map"],
                )

            after = {
                path.relative_to(output)
                for path in output.rglob("*")
                if path.is_file()
            }
            self.assertEqual(after, before)

    def test_base_map_requires_immutable_referenced_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "out"
            output.mkdir()

            first = materialize(
                source_shards_dir=SHARDS,
                wave_path=WAVE,
                output_root=output,
            )
            first_map = json.loads(
                (output / first["classification_map"]).read_text()
            )
            relative = first_map["entries"]["BTCUSDT"]
            (output / relative).unlink()

            ledger = root / "wave2-ledger.json"
            ledger.write_bytes(canonical(_wave2_ledger()))
            with self.assertRaises(MCFError):
                materialize(
                    acquisition_path=ledger,
                    wave_path=WAVE2,
                    output_root=output,
                    base_classification_map=first["classification_map"],
                )

    def test_noncanonical_ledger_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.json"
            path.write_text("\n" + canonical(_ledger()).decode("utf-8"), encoding="utf-8")
            with self.assertRaises(MCFError):
                load_acquisition(path, WAVE)


if __name__ == "__main__":
    unittest.main()
