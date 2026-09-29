import unittest

from research.mass_candidate_factory.production_manifest import (
    VERSION,
    compile_manifests,
    manifest_index,
    validate_manifest,
)


class ProductionManifestTest(unittest.TestCase):
    def test_all_frozen_families_compile_with_stable_identity(self):
        a = compile_manifests()
        b = compile_manifests()
        self.assertEqual(a, b)
        self.assertEqual(len(a), 12)
        self.assertEqual(len({x["family_spec_sha256"] for x in a}), 12)
        for record in a:
            body = {k: v for k, v in record.items() if k != "family_spec_sha256"}
            self.assertEqual(record["schema"], VERSION)
            self.assertEqual(validate_manifest(body), record["family_spec_sha256"])
            self.assertEqual(record["evidence_partition"], "DEVELOPMENT")
            self.assertFalse(record["safety"]["fresh_oos_read"])
            self.assertFalse(record["safety"]["p10_read"])

    def test_dependency_identity_is_explicit(self):
        index = manifest_index()
        self.assertEqual(index["LEAD_LAG"]["data_dependencies"], ("PRICE_OHLC", "MULTI_ASSET"))
        self.assertEqual(index["TRADE_COUNT_CONFIRMED_DIRECTION"]["data_dependencies"], ("PRICE_OHLC", "TRADE_COUNT"))
        self.assertEqual(index["VOLUME_CONFIRMED_DIRECTION"]["data_dependencies"], ("PRICE_OHLC", "VOLUME"))


if __name__ == "__main__":
    unittest.main()
