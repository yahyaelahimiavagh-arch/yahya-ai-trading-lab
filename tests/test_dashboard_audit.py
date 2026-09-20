import json
import shutil
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from yatl.dashboard.audit import (
    EXPECTED_EXPORTS,
    EXPECTED_EXPORT_SET_SHA256,
    EXPECTED_INDEX_SHA256,
    EXPECTED_POLICY_SHA256,
    P8AuditError,
    P8AuditResult,
    _audit_evidence_records,
    _audit_published_artifacts,
    _audit_source_safety,
    _load_exports,
    _policy_sha256,
    _read_evidence,
    audit_p8,
)
from yatl.dashboard.audit_runtime import _accepted_exports
from yatl.dashboard.cli import dashboard_build
from yatl.dashboard.scenarios import (
    SYMBOLS,
    run_adversarial_dashboard_matrix,
    write_adversarial_dashboard_matrix,
)


class P8IndependentAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.exports, cls.fixtures = _accepted_exports(cls.root)
        cls.matrix = run_adversarial_dashboard_matrix(cls.fixtures)
        cls.evidence = cls.root / "p8-009-evidence"
        write_adversarial_dashboard_matrix(cls.matrix, cls.evidence)

        cls.published = {}
        for symbol in SYMBOLS:
            output = cls.root / f"{symbol.lower()}-dashboard.html"
            dashboard_build(
                cls.exports[symbol],
                EXPECTED_EXPORTS[symbol],
                output,
            )
            cls.published[symbol] = output

        cls.before = {
            symbol: cls.exports[symbol].read_bytes()
            for symbol in SYMBOLS
        }
        cls.result = audit_p8(cls.exports, cls.evidence, cls.published)
        cls.after = {
            symbol: cls.exports[symbol].read_bytes()
            for symbol in SYMBOLS
        }
        (
            cls.loaded_fixtures,
            cls.loaded,
            cls.renderer_identity,
            cls.export_set_sha,
        ) = _load_exports(cls.exports)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_audit_result_exact_counts(self):
        self.assertEqual(
            (
                self.result.symbols,
                self.result.scenarios,
                self.result.runs,
                self.result.files,
                self.result.published_artifacts,
            ),
            (2, 9, 18, 19, 2),
        )

    def test_audit_policy_sha_is_frozen(self):
        self.assertEqual(self.result.policy_sha256, EXPECTED_POLICY_SHA256)
        self.assertEqual(_policy_sha256(), EXPECTED_POLICY_SHA256)

    def test_audit_adversarial_index_sha_is_frozen(self):
        self.assertEqual(self.result.index_sha256, EXPECTED_INDEX_SHA256)

    def test_audit_export_set_sha_is_frozen(self):
        self.assertEqual(self.result.export_set_sha256, EXPECTED_EXPORT_SET_SHA256)
        self.assertEqual(self.export_set_sha, EXPECTED_EXPORT_SET_SHA256)

    def test_audit_renderer_set_sha_is_valid(self):
        self.assertEqual(len(self.result.renderer_set_sha256), 64)
        int(self.result.renderer_set_sha256, 16)

    def test_audit_all_acceptance_booleans_true(self):
        self.assertTrue(self.result.exact_outcomes)
        self.assertTrue(self.result.replay_equal)
        self.assertTrue(self.result.projections_recomputed)
        self.assertTrue(self.result.renderer_recomputed)
        self.assertTrue(self.result.artifacts_verified)
        self.assertTrue(self.result.no_write)
        self.assertTrue(self.result.source_safe)

    def test_audit_does_not_mutate_accepted_exports(self):
        self.assertEqual(self.before, self.after)

    def test_loaded_export_symbols_are_exact(self):
        self.assertEqual(tuple(self.loaded), SYMBOLS)
        for symbol in SYMBOLS:
            self.assertEqual(self.loaded[symbol].source.symbol, symbol)
            self.assertEqual(
                self.loaded[symbol].export_sha256,
                EXPECTED_EXPORTS[symbol],
            )

    def test_loaded_fixture_export_bytes_match_source(self):
        for symbol in SYMBOLS:
            self.assertEqual(
                self.loaded_fixtures[symbol].canonical_export_json.encode("utf-8"),
                self.exports[symbol].read_bytes(),
            )

    def test_renderer_identity_exists_for_both_symbols(self):
        self.assertEqual(tuple(self.renderer_identity), SYMBOLS)
        for symbol in SYMBOLS:
            identity = self.renderer_identity[symbol]
            self.assertGreater(identity["bytes"], 0)
            self.assertEqual(len(identity["view_model_sha256"]), 64)
            self.assertEqual(len(identity["dashboard_sha256"]), 64)

    def test_published_artifacts_match_recomputed_renderer(self):
        result = _audit_published_artifacts(
            self.published,
            self.renderer_identity,
            self.loaded,
        )
        self.assertEqual(tuple(result), SYMBOLS)
        for symbol in SYMBOLS:
            self.assertEqual(
                result[symbol]["dashboard_sha256"],
                self.renderer_identity[symbol]["dashboard_sha256"],
            )

    def test_source_safety_recomputes_true(self):
        self.assertTrue(_audit_source_safety())

    def test_evidence_reader_returns_exact_19_files(self):
        evidence, records = _read_evidence(self.evidence)
        self.assertEqual(len(evidence), 19)
        self.assertEqual(len(records), 19)
        self.assertIn("p8-009-index.json", records)

    def test_evidence_records_independently_validate(self):
        _, records = _read_evidence(self.evidence)
        self.assertIsNone(_audit_evidence_records(records))

    def test_missing_export_symbol_is_rejected(self):
        with self.assertRaises(P8AuditError):
            _load_exports({"BTCUSDT": self.exports["BTCUSDT"]})

    def test_wrong_export_path_content_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            btc = root / "btc.json"
            eth = root / "eth.json"
            btc.write_bytes(self.exports["BTCUSDT"].read_bytes() + b" ")
            eth.write_bytes(self.exports["ETHUSDT"].read_bytes())
            with self.assertRaises(P8AuditError):
                _load_exports({"BTCUSDT": btc, "ETHUSDT": eth})

    def test_swapped_export_paths_are_rejected(self):
        with self.assertRaises(P8AuditError):
            _load_exports({
                "BTCUSDT": self.exports["ETHUSDT"],
                "ETHUSDT": self.exports["BTCUSDT"],
            })

    def test_missing_evidence_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "evidence"
            shutil.copytree(self.evidence, target)
            next(target.glob("btcusdt-*.json")).unlink()
            with self.assertRaises(P8AuditError):
                _read_evidence(target)

    def test_extra_evidence_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "evidence"
            shutil.copytree(self.evidence, target)
            (target / "extra.json").write_text("{}\n", encoding="utf-8")
            with self.assertRaises(P8AuditError):
                _read_evidence(target)

    def test_noncanonical_evidence_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "evidence"
            shutil.copytree(self.evidence, target)
            index = target / "p8-009-index.json"
            index.write_bytes(index.read_bytes() + b" ")
            with self.assertRaises(P8AuditError):
                _read_evidence(target)

    def test_tampered_index_safety_is_rejected(self):
        _, records = _read_evidence(self.evidence)
        records = dict(records)
        index = dict(records["p8-009-index.json"])
        index["strategy_evidence"] = "PROVEN"
        records["p8-009-index.json"] = index
        with self.assertRaises(P8AuditError):
            _audit_evidence_records(records)

    def test_tampered_index_export_identity_is_rejected(self):
        _, records = _read_evidence(self.evidence)
        records = dict(records)
        index = json.loads(json.dumps(records["p8-009-index.json"]))
        index["accepted_source_identities"]["BTCUSDT"]["export_sha256"] = "a" * 64
        records["p8-009-index.json"] = index
        with self.assertRaises(P8AuditError):
            _audit_evidence_records(records)

    def test_tampered_scenario_digest_is_rejected(self):
        _, records = _read_evidence(self.evidence)
        records = dict(records)
        name = next(
            key for key in records
            if key != "p8-009-index.json"
        )
        scenario = dict(records[name])
        scenario["result_sha256"] = "a" * 64
        records[name] = scenario
        with self.assertRaises(P8AuditError):
            _audit_evidence_records(records)

    def test_missing_published_symbol_is_rejected(self):
        with self.assertRaises(P8AuditError):
            _audit_published_artifacts(
                {"BTCUSDT": self.published["BTCUSDT"]},
                self.renderer_identity,
                self.loaded,
            )

    def test_tampered_published_html_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            published = {}
            for symbol in SYMBOLS:
                path = root / f"{symbol}.html"
                path.write_bytes(self.published[symbol].read_bytes())
                published[symbol] = path
            data = published["BTCUSDT"].read_text(encoding="utf-8")
            published["BTCUSDT"].write_text(
                data.replace("YATL Local Dashboard", "XATL Local Dashboard", 1),
                encoding="utf-8",
            )
            with self.assertRaises(P8AuditError):
                _audit_published_artifacts(
                    published,
                    self.renderer_identity,
                    self.loaded,
                )

    def test_published_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            link = root / "btc.html"
            link.symlink_to(self.published["BTCUSDT"])
            published = {
                "BTCUSDT": link,
                "ETHUSDT": self.published["ETHUSDT"],
            }
            with self.assertRaises(P8AuditError):
                _audit_published_artifacts(
                    published,
                    self.renderer_identity,
                    self.loaded,
                )

    def test_full_audit_rejects_tampered_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "evidence"
            shutil.copytree(self.evidence, target)
            index = target / "p8-009-index.json"
            record = json.loads(index.read_text(encoding="utf-8"))
            record["strategy_evidence"] = "PROVEN"
            index.write_text(
                json.dumps(
                    record,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ) + "\n",
                encoding="utf-8",
            )
            with self.assertRaises(P8AuditError):
                audit_p8(self.exports, target, self.published)

    def test_audit_result_rejects_wrong_policy(self):
        with self.assertRaises(P8AuditError):
            replace(self.result, policy_sha256="a" * 64)

    def test_audit_result_rejects_wrong_index(self):
        with self.assertRaises(P8AuditError):
            replace(self.result, index_sha256="a" * 64)

    def test_audit_result_rejects_false_acceptance_flag(self):
        with self.assertRaises(P8AuditError):
            replace(self.result, renderer_recomputed=False)

    def test_audit_result_rejects_invalid_renderer_set_sha(self):
        with self.assertRaises(P8AuditError):
            replace(self.result, renderer_set_sha256="bad")

    def test_audit_source_has_no_analytics_runtime_or_execution_import(self):
        import inspect
        import yatl.dashboard.audit as audit_module

        source = inspect.getsource(audit_module)
        for forbidden in (
            "from yatl.analytics",
            "import yatl.analytics",
            "from yatl.execution",
            "import yatl.execution",
            "from yatl.account",
            "import yatl.account",
            "from yatl.risk",
            "import yatl.risk",
            "urllib",
            "http.client",
            "requests",
            "httpx",
            "aiohttp",
            "websockets",
            "openai",
            "anthropic",
            "/api/v3/order",
            "/fapi",
            "/dapi",
            "withdraw(",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
