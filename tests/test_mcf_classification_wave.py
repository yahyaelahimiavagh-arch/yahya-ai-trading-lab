import copy
import tempfile
import unittest
from pathlib import Path

from research.mass_candidate_factory.classification_wave import (
    EXPECTED_SAFETY,
    load_wave,
    validate_wave,
)
from research.mass_candidate_factory.models import MCFError, canonical


ROOT = Path(__file__).resolve().parents[1]
WAVE = ROOT / "docs/research/alpha-factory/MCF-PROD-001-CLASSIFICATION-WAVE-001.json"
EXPECTED_WAVE_SHA256 = "1a2a2b35efbec3a1cd96174e190d5dce0352e2a43d6da7a975928062c5aaad58"


class ClassificationWaveTest(unittest.TestCase):
    def test_wave_001_is_exact_and_canonical(self):
        doc, identity = load_wave(WAVE)
        self.assertEqual(identity, EXPECTED_WAVE_SHA256)
        self.assertEqual(doc["frontier_symbol_count"], 176)
        self.assertEqual(len(doc["frontier_symbols"]), 176)
        self.assertEqual(len(set(doc["frontier_symbols"])), 176)
        self.assertEqual(doc["frontier_symbols"], sorted(doc["frontier_symbols"]))
        self.assertEqual(
            doc["source_preflight_sha256"],
            "eff8f60b4a92be2a2e3266de86f9ad5a7c0bb9aaa8f25dc1a4a35805f058aa34",
        )
        self.assertEqual(doc["safety"], EXPECTED_SAFETY)

    def test_wave_rejects_duplicate_or_reordered_frontier(self):
        doc, _ = load_wave(WAVE)

        duplicate = copy.deepcopy(doc)
        duplicate["frontier_symbols"][-1] = duplicate["frontier_symbols"][0]
        with self.assertRaises(MCFError):
            validate_wave(duplicate)

        reordered = copy.deepcopy(doc)
        reordered["frontier_symbols"][0], reordered["frontier_symbols"][1] = (
            reordered["frontier_symbols"][1],
            reordered["frontier_symbols"][0],
        )
        with self.assertRaises(MCFError):
            validate_wave(reordered)

    def test_wave_rejects_safety_mutation(self):
        doc, _ = load_wave(WAVE)
        mutated = copy.deepcopy(doc)
        mutated["safety"]["performance_read"] = True
        with self.assertRaises(MCFError):
            validate_wave(mutated)

    def test_wave_rejects_noncanonical_json(self):
        doc, _ = load_wave(WAVE)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "wave.json"
            path.write_text("\n" + canonical(doc).decode("utf-8"), encoding="utf-8")
            with self.assertRaises(MCFError):
                load_wave(path)


if __name__ == "__main__":
    unittest.main()
