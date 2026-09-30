"""Synthetic infrastructure fixtures only; never runs the production candidates."""
import copy
import json
import runpy
import sys
import tempfile
import unittest
from decimal import localcontext, ROUND_DOWN
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from research.crisis_lab.acquisition import CanonicalRow
from research.mass_candidate_factory.models import MCFError, canonical, digest, safe_path
from research.mass_candidate_factory.production import DEVELOPMENT_END_MS, DEVELOPMENT_START_MS
from research.mass_candidate_factory.production_features import POPULATION_START_MS
from research.mass_candidate_factory.production_membership_freeze import build_freeze
from research.mass_candidate_factory import production_runtime_data as data
from research.mass_candidate_factory import production_runner_input as runner
from research.mass_candidate_factory import production_input_vps as vps
from research.mass_candidate_factory.production_runtime import ProductionRuntime
from research.opportunity_data.models import OpportunityError
from test_mcf_production_membership_freeze import ready_preflight
from test_mcf_production_runtime import bars, binding, freeze_artifact


def candle(t):
    return CanonicalRow((str(t), "100", "102", "99", "101", "10",
                         str(t + 900_000 - 1), "1000", "20", "3", "300", "0"))


def source_rows(missing=()):
    return tuple(candle(DEVELOPMENT_START_MS + i * 900_000)
                 for i in range(48) if i not in missing)


def fixture_membership():
    preflight = ready_preflight()
    symbols = [f"ASSET{i:02d}USDT" for i in range(15)]
    for i, row in enumerate(preflight["monthly_rankings"]):
        selected = [] if i < 11 else symbols if i == 11 else symbols[:2]
        row.update(selected_symbols=selected, selected_count=len(selected), eligible_count=len(selected))
    preflight["preflight_sha256"] = digest({k: v for k, v in preflight.items() if k != "preflight_sha256"})
    return preflight, build_freeze(preflight)


class RuntimeInputFreezeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.evidence = self.root / "evidence"
        self.output = self.root / "output"
        self.evidence.mkdir()
        self.output.mkdir()
        self.preflight, self.membership = fixture_membership()
        self.member_ref = "membership.json"
        self.preflight_ref = "preflight.json"
        (self.evidence / self.member_ref).write_bytes(canonical(self.membership))
        (self.evidence / self.preflight_ref).write_bytes(canonical(self.preflight))
        self.patches = ExitStack()
        self.addCleanup(self.patches.close)
        self.patches.enter_context(patch.object(runner, "MEMBERSHIP_SHA", self.membership["freeze_sha256"]))
        self.patches.enter_context(patch.object(runner, "accepted_membership", return_value=self.membership))

    def make_index(self, missing=()):
        datasets = []
        for symbol in self.membership["selected_union_symbols"]:
            datasets.extend(data.materialize_symbol(self.output, symbol, source_rows(missing),
                                                    [{"identity": symbol, "record_sha256": "a" * 64}]))
        base = {"schema": data.VERSION, "generation_id": "MCF-PROD-001",
                "state": "RUNTIME_DATA_MATERIALIZED_BEFORE_PERFORMANCE",
                "membership_freeze_sha256": self.membership["freeze_sha256"],
                "source_preflight_sha256": data.PREFLIGHT_SHA,
                "classification_map_sha256": data.CLASSIFICATION_SHA,
                "plan_sha256": data.EXPECTED_PLAN_SHA256,
                "population_reconciliation_sha256": data.EXPECTED_POPULATION_RECONCILIATION_SHA256,
                "universe_policy_sha256": self.membership["universe_policy_sha256"],
                "selected_union_symbols": self.membership["selected_union_symbols"],
                "dataset_count": len(datasets), "timeframes": data.TIMEFRAMES,
                "evidence_bounds": data.BOUNDS, "datasets": datasets, "safety": data.SAFETY}
        doc = {**base, "index_sha256": digest(base)}
        self.index = doc
        self.index_ref = f"runtime-data/index-{doc['index_sha256']}.json"
        (self.output / self.index_ref).write_bytes(canonical(doc))
        return doc

    def freeze(self):
        if not hasattr(self, "index"):
            self.make_index()
        return runner.freeze_input(evidence_root=self.evidence, runtime_root=self.output,
                                   index_relative=self.index_ref,
                                   expected_index_sha256=self.index["index_sha256"])

    def reader(self):
        result = self.freeze()
        return runner.FrozenRunnerInput(self.output, result["artifact"], result["runner_input_sha256"])

    def test_module_entrypoint_delegates_to_canonical_module(self):
        with patch.object(sys, "argv", ["production_runner_input"]):
            with patch.object(runner, "main", return_value=23) as canonical_main:
                with self.assertRaises(SystemExit) as caught:
                    runpy.run_module(
                        "research.mass_candidate_factory.production_runner_input",
                        run_name="__main__", alter_sys=True,
                    )
        self.assertEqual(caught.exception.code, 23)
        canonical_main.assert_called_once_with()

    def test_wrong_membership_hash_rejected(self):
        with self.assertRaises(MCFError):
            data.read_membership(self.evidence, self.member_ref, "f" * 64,
                                 self.preflight_ref, self.preflight["preflight_sha256"])

    def test_tampered_membership_rejected(self):
        changed = copy.deepcopy(self.membership)
        changed["monthly_memberships"][0]["selected_symbols"] = ["EXTRAUSDT"]
        (self.evidence / self.member_ref).write_bytes(canonical(changed))
        with self.assertRaises(MCFError):
            data.read_membership(self.evidence, self.member_ref, self.membership["freeze_sha256"],
                                 self.preflight_ref, self.preflight["preflight_sha256"])

    def test_membership_must_equal_preflight_even_when_rehashed(self):
        changed = copy.deepcopy(self.membership)
        changed["monthly_memberships"][0]["selected_symbols"] = ["EXTRAUSDT"]
        changed["freeze_sha256"] = digest({k: v for k, v in changed.items() if k != "freeze_sha256"})
        (self.evidence / self.member_ref).write_bytes(canonical(changed))
        with self.assertRaises(MCFError):
            data.read_membership(self.evidence, self.member_ref, changed["freeze_sha256"],
                                 self.preflight_ref, self.preflight["preflight_sha256"])

    def test_outside_symbol_rejected_before_file_read(self):
        reader = self.reader()
        with patch.object(runner, "read_dataset", side_effect=AssertionError("unexpected data read")):
            with self.assertRaises(MCFError):
                reader.load("EXTRAUSDT", "15m")

    def test_outside_timeframe_rejected_before_file_read(self):
        reader = self.reader()
        with patch.object(runner, "read_dataset", side_effect=AssertionError("unexpected data read")):
            with self.assertRaises(MCFError):
                reader.load("ASSET00USDT", "1d")

    def test_after_development_rejected(self):
        with self.assertRaises(OpportunityError):
            data.materialize_symbol(self.output, "ASSET00USDT", source_rows() + (candle(DEVELOPMENT_END_MS),), [])

    def test_before_population_rejected(self):
        with self.assertRaises(MCFError):
            data.validate_development((candle(POPULATION_START_MS - 900_000),) + source_rows(), "15m")

    def test_incomplete_buckets_are_dropped_and_visible(self):
        self.make_index(missing=(2,))
        for row in self.index["datasets"][:3]:
            derived = runner.read_dataset(self.output, row)
            self.assertNotIn(DEVELOPMENT_START_MS, [x.open_time_ms for x in derived] if row["timeframe"] != "15m" else [])
            if row["timeframe"] != "15m":
                self.assertEqual(row["incomplete_bucket_dropped_count"], 1)
                gap, _ = data.read_json(self.output, row["gap_ref"])
                self.assertTrue(any(a <= DEVELOPMENT_START_MS <= b for a, b in gap["missing_ranges"]))
        runner.reconcile_datasets(self.output, self.index)

    def test_completely_missing_buckets_and_edges_remain_gaps(self):
        row = data.materialize_symbol(self.output, "ASSET00USDT", source_rows(missing=tuple(range(16, 32))), [])[2]
        gap, _ = data.read_json(self.output, row["gap_ref"])
        self.assertEqual(row["incomplete_bucket_dropped_count"], 0)
        self.assertTrue(any(a <= DEVELOPMENT_START_MS + 16 * 900_000 <= b for a, b in gap["missing_ranges"]))
        self.assertEqual(gap["missing_ranges"][0][0], POPULATION_START_MS)
        self.assertEqual(gap["missing_ranges"][-1][1], DEVELOPMENT_END_MS - 14_400_000)

    def test_rerun_same_hash(self):
        first = self.make_index()
        second = self.make_index()
        self.assertEqual(first, second)
        self.assertEqual(self.freeze(), self.freeze())

    def test_collision_rejected(self):
        self.make_index()
        path = self.output / self.index["datasets"][0]["data_ref"]
        path.write_bytes(b"changed")
        with self.assertRaises(MCFError):
            self.make_index()

    def test_changed_data_hash_rejected(self):
        reader = self.reader()
        path = self.output / self.index["datasets"][0]["data_ref"]
        path.write_bytes(path.read_bytes() + b"changed\n")
        with self.assertRaises(OpportunityError):
            reader.load("ASSET00USDT", "15m")

    def test_changed_gap_hash_rejected(self):
        reader = self.reader()
        (self.output / self.index["datasets"][0]["gap_ref"]).write_bytes(b"{}\n")
        with self.assertRaises(MCFError):
            reader.load("ASSET00USDT", "15m")

    def test_empty_month_and_fifteen_member_month_exact(self):
        reader = self.reader()
        monthly = self.membership["monthly_memberships"]
        for row in monthly[:11]:
            self.assertEqual(reader.binding.symbols_at(row["effective_ms"]), ())
        self.assertEqual(reader.binding.symbols_at(monthly[11]["effective_ms"]),
                         tuple(monthly[11]["selected_symbols"]))
        self.assertEqual(len(reader.binding.symbols_at(monthly[11]["effective_ms"])), 15)
        self.assertFalse(reader.binding.is_member("ASSET14USDT", monthly[12]["effective_ms"]))

    def test_raw_production_constructor_blocked(self):
        with self.assertRaises(MCFError):
            ProductionRuntime(executable_freeze=freeze_artifact(), binding=binding(),
                              bars_by_timeframe={"1h": {"AAAUSDT": bars("AAAUSDT")}})

    def test_frozen_runtime_cannot_accept_replacement_data(self):
        reader = self.reader()
        with self.assertRaises(MCFError):
            ProductionRuntime(executable_freeze=freeze_artifact(), binding=reader.binding,
                              bars_by_timeframe={"1h": {"AAAUSDT": bars("AAAUSDT")}}, frozen_input=reader)

    def test_frozen_runtime_wiring_has_no_performance_side_effect(self):
        reader = self.reader()
        with patch("research.mass_candidate_factory.production_runtime.run_candidate",
                   side_effect=AssertionError("performance must remain closed")):
            runtime = ProductionRuntime.from_frozen_input(reader)
            with self.assertRaises(MCFError):
                runtime.run(next(iter(runtime._candidates)))
            admitted = runtime._timeframe_caches("4h")
            self.assertEqual(set(admitted), set(self.membership["selected_union_symbols"]))

    def test_runtime_membership_substitution_rejected(self):
        reader = self.reader()
        runtime = ProductionRuntime.from_frozen_input(reader)
        runtime.binding = binding()
        with self.assertRaises(MCFError):
            runtime.run(next(iter(runtime._candidates)), director_authorized=True)

    def test_manifest_change_after_load_rejected(self):
        reader = self.reader()
        (self.output / reader.relative).write_bytes(b"{}\n")
        with self.assertRaises(MCFError):
            reader.load("ASSET00USDT", "15m")

    def test_unsafe_paths_and_roots_are_rejected(self):
        for part in ("fresh_oos", "recent-reserve", "p10"):
            with self.subTest(part=part):
                with self.assertRaises(MCFError):
                    safe_path(self.output, f"{part}/data.csv")
                with self.assertRaises(MCFError):
                    runner.FrozenRunnerInput(self.root / part, "input.json", "a" * 64)

    def test_symlink_and_traversal_rejected(self):
        (self.output / "escape").symlink_to(self.evidence, target_is_directory=True)
        for ref in ("escape/membership.json", "../evidence/membership.json"):
            with self.assertRaises(MCFError):
                safe_path(self.output, ref)

    def test_safety_and_no_performance_reads_or_writes(self):
        self.make_index()
        with patch("research.mass_candidate_factory.production_runtime.run_candidate",
                   side_effect=AssertionError("performance read/execution forbidden")):
            result = self.freeze()
            reader = runner.FrozenRunnerInput(self.output, result["artifact"], result["runner_input_sha256"])
            ProductionRuntime.from_frozen_input(reader)
        for name in ("performance_read", "fresh_oos_read", "recent_reserve_read", "p10_read", "p10_write", "live"):
            self.assertIs(result["safety"][name], False)
        self.assertIs(result["safety"]["p11_locked"], True)
        self.assertEqual(result["safety"]["live_master_lock"], "OFF")
        self.assertFalse(result["performance_authorized"])
        self.assertEqual(set(p.name for p in self.root.iterdir()), {"evidence", "output"})

    def test_derivation_independent_of_ambient_decimal_context(self):
        ordinary, _ = data.derive_complete(source_rows(), "ASSET00USDT", "4h", "FIXTURE")
        with localcontext() as context:
            context.prec = 5
            context.rounding = ROUND_DOWN
            altered, _ = data.derive_complete(source_rows(), "ASSET00USDT", "4h", "FIXTURE")
        self.assertEqual(ordinary, altered)

    def test_index_rejects_extra_symbol_timeframe_and_sealed_partition(self):
        index = self.make_index()
        for key, value in (("symbol", "EXTRAUSDT"), ("timeframe", "1d"),
                           ("evidence_partition", "FRESH_OOS")):
            changed = copy.deepcopy(index)
            changed["datasets"][0][key] = value
            changed["index_sha256"] = digest({k: v for k, v in changed.items() if k != "index_sha256"})
            with self.subTest(key=key), self.assertRaises(MCFError):
                runner.validate_index(changed, self.membership)

    def test_rehashed_future_file_still_rejected(self):
        from research.crisis_lab.acquisition import _canonical_csv
        from research.opportunity_data.models import sha256
        self.make_index()
        row = copy.deepcopy(self.index["datasets"][0])
        raw = _canonical_csv(source_rows() + (candle(DEVELOPMENT_END_MS),))
        row["content_sha256"] = sha256(raw)
        row["data_ref"] = f"runtime-data/future-{row['content_sha256']}.csv"
        (self.output / row["data_ref"]).write_bytes(raw)
        with self.assertRaises(OpportunityError):
            runner.read_dataset(self.output, row)

    def test_semantically_rehashed_gap_cannot_hide_missing_bars(self):
        self.make_index(missing=(2,))
        row = copy.deepcopy(self.index["datasets"][1])
        gap, _ = data.read_json(self.output, row["gap_ref"])
        gap.update(missing_ranges=[], gap_count=0)
        row["gap_sha256"] = digest(gap)
        row["gap_ref"] = f"runtime-data/false-gaps-{row['gap_sha256']}.json"
        (self.output / row["gap_ref"]).write_bytes(canonical(gap))
        with self.assertRaises(MCFError):
            runner.read_dataset(self.output, row)

    def test_population_reconciliation_detects_rehashed_ledger_change(self):
        entries, documents, hashes = [], {}, []
        for i in range(9306):
            entry = {"symbol": f"META{i:05d}USDT", "month": "2020-01"}
            identity = f"{entry['symbol']}-{entry['month']}"
            base = {"identity": identity, "symbol": entry["symbol"], "period": entry["month"],
                    "interval": "15m", "plan_sha256": data.EXPECTED_PLAN_SHA256,
                    "state": "MONTHLY_SUCCESS" if i < 6443 else "MISSING_ARCHIVE"}
            doc = {**base, "record_sha256": digest(base)}
            documents[f"ledger/{identity}.json"] = doc
            hashes.append(doc["record_sha256"])
            entries.append(entry)
        plan = {"periods": entries, "plan_sha256": data.EXPECTED_PLAN_SHA256}
        adapter = {"state": "AF01C_ENGINEERING_PILOT_NO_SELECTION", "plan_sha256": data.EXPECTED_PLAN_SHA256,
                   "records": tuple(hashes), "final_count": 9306, "source_gap_count": 2863}
        reconciliation = {"adapter_reconciliation_sha256": digest(adapter),
                          "final_count": 9306, "source_gap_count": 2863}
        def read_metadata(root, relative):
            doc = documents[relative]
            return doc, canonical(doc)
        with patch.object(data, "read_json", side_effect=read_metadata):
            admitted = data.verify_population_metadata(self.root, plan, reconciliation)
            self.assertEqual(len(admitted), 9306)
            first = next(iter(documents.values()))
            first["state"] = "MISSING_ARCHIVE"
            first["record_sha256"] = digest({k: v for k, v in first.items() if k != "record_sha256"})
            with self.assertRaises(MCFError):
                data.verify_population_metadata(self.root, plan, reconciliation)

    def test_failed_source_is_preserved_without_reading_partial_data(self):
        from research.crisis_lab.acquisition import _canonical_csv
        from research.opportunity_data.models import sha256
        rows = source_rows()
        raw = _canonical_csv(rows)
        (self.evidence / "source.csv").write_bytes(raw)
        success = {"identity": "ASSET00USDT-2020-03", "state": "MONTHLY_SUCCESS",
                   "record_sha256": "a" * 64, "canonical_ref": "source.csv",
                   "canonical_sha256": sha256(raw), "row_count": len(rows), "gap_count": 0,
                   "requested_start_ms": DEVELOPMENT_START_MS,
                   "requested_end_ms": DEVELOPMENT_START_MS + 31 * 86400000}
        failure = {"identity": "ASSET00USDT-2020-04", "state": "MISSING_ARCHIVE",
                   "record_sha256": "b" * 64, "canonical_ref": "never-read.csv",
                   "canonical_sha256": "c" * 64}
        entries = [{"symbol": "ASSET00USDT", "month": "2020-03"},
                   {"symbol": "ASSET00USDT", "month": "2020-04"}]
        records = {success["identity"]: success, failure["identity"]: failure}
        with patch.object(data, "_validate_ledger", side_effect=[success, failure]):
            combined, sources = data.symbol_source(self.evidence, {}, {}, entries, records)
        self.assertEqual(combined, rows)
        self.assertEqual(sources[1]["state"], "MISSING_ARCHIVE")
        self.assertEqual(sources[1]["canonical_ref"], "never-read.csv")

    def test_discovery_prunes_sealed_directories_without_entering_them(self):
        names = [f"membership-freeze-{data.MEMBERSHIP_SHA}.json", f"preflight-{data.PREFLIGHT_SHA}.json"]
        for kind in ("normal", "fresh_oos", "recent-reserve", "p10", "results"):
            root = self.root / kind
            (root / "monthly-membership").mkdir(parents=True)
            (root / "binding-preflight").mkdir()
            (root / "monthly-membership" / names[0]).write_text("fixture")
            (root / "binding-preflight" / names[1]).write_text("fixture")
        self.assertEqual(vps.discover_evidence(self.root), self.root / "normal")
        duplicate = self.root / "duplicate"
        (duplicate / "monthly-membership").mkdir(parents=True)
        (duplicate / "binding-preflight").mkdir()
        (duplicate / "monthly-membership" / names[0]).write_text("fixture")
        (duplicate / "binding-preflight" / names[1]).write_text("fixture")
        with self.assertRaises(MCFError):
            vps.discover_evidence(self.root)


if __name__ == "__main__":
    unittest.main()
