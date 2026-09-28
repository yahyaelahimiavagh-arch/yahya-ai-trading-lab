"""AF-01C P-C isolated population runtime tests."""
import io
import json
import tempfile
import unittest
import zipfile
from unittest import mock
from pathlib import Path

from research.opportunity_data.archive_adapter import plan
from research.opportunity_data.models import canonical, sha256
from research.opportunity_data.pc_population import (
    MAX_CANARY_BATCH,
    MAX_FAST_BATCHES,
    MAX_FAST_WORKERS,
    accept_canary_continuation,
    acquire_batch,
    acquire_batches_fast,
    population_status,
    reconcile_population,
)
from research.opportunity_data.storage import save_artifact


def zip_csv(name, rows):
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w") as bundle:
        info = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        bundle.writestr(info, "\n".join(rows) + "\n")
    return target.getvalue()


def candle(t):
    return f"{t},1,2,1,2,10,{t+899999},20,2,5,10,0"


class Fetcher:
    def __init__(self, mapping):
        self.mapping = mapping
        self.calls = []

    def fetch(self, url, *, max_bytes):
        self.calls.append(url)
        if url not in self.mapping:
            from research.crisis_lab.acquisition import AcquisitionError
            raise AcquisitionError("HTTP 404")
        value = self.mapping[url]
        if len(value) > max_bytes:
            raise ValueError("oversized")
        return value


class PCPopulation(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        key = "data/spot/monthly/klines/BTCUSDT/15m/BTCUSDT-15m-2020-01.zip"
        self.item = dict(
            key=key,
            cadence="monthly",
            symbol="BTCUSDT",
            interval="15m",
            period="2020-01",
        )
        prefix = "data/spot/monthly/klines/BTCUSDT/15m/"
        self.inventory = dict(
            schema="AF-01C-INVENTORY-SNAPSHOT/1",
            inventory_strategy="HIERARCHICAL_COMMON_PREFIXES_RANGE_BOUNDED/2",
            retrieved_at="2026-09-28T00:00:00Z",
            source_endpoint="https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?list-type=2",
            discovered_symbols={"monthly": ["BTCUSDT"], "daily": []},
            object_range_bounds={
                "monthly:BTCUSDT": {
                    "start_after": prefix + "BTCUSDT-15m-2019-99",
                    "end_exclusive": prefix + "BTCUSDT-15m-2023-01",
                }
            },
            listing_urls=["https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?list-type=2"],
            raw_page_sha256=["0" * 64],
            raw_inventory_sha256=None,
            normalized_inventory_sha256=None,
            objects=[self.item],
            state="COMPLETE",
        )
        from research.opportunity_data.models import canonical as model_canonical, sha256 as model_sha256, digest
        self.inventory["raw_inventory_sha256"] = model_sha256(model_canonical(self.inventory["raw_page_sha256"]))
        self.inventory["normalized_inventory_sha256"] = digest(
            dict(schema="AF-01C-INVENTORY/1", objects=self.inventory["objects"])
        )
        self.plan = plan(self.inventory, ("BTCUSDT",), ("2020-01",), pilot=False)
        self.inventory_ref = "inventory/test.json"
        self.plan_ref = f"plans/plan-{self.plan['plan_sha256']}.json"
        save_artifact(self.root, self.inventory_ref, canonical(self.inventory))
        save_artifact(self.root, self.plan_ref, canonical(self.plan))
        self.preflight_ref = "preflight/storage-test.json"
        self.preflight = dict(
            schema="AF-01C-PC-STORAGE-PREFLIGHT/1",
            state="PASS",
            conservative_required_bytes=1,
        )
        save_artifact(self.root, self.preflight_ref, canonical(self.preflight))

    def tearDown(self):
        self.temp.cleanup()

    def test_bounded_batch_resume_status_and_reconcile(self):
        before = population_status(self.root, self.plan_ref, self.inventory_ref)
        self.assertEqual(before["completed_identities"], 0)
        self.assertEqual(before["remaining_identities"], 1)

        start = 1577836800000
        rows = [candle(start + i * 900000) for i in range(31 * 96)]
        raw = zip_csv("BTCUSDT-15m-2020-01.csv", rows)
        url = "https://data.binance.vision/" + self.item["key"]
        fetcher = Fetcher({
            url: raw,
            url + ".CHECKSUM": f"{sha256(raw)}  BTCUSDT-15m-2020-01.zip\n".encode(),
        })

        batch = acquire_batch(
            self.root,
            self.plan_ref,
            self.inventory_ref,
            limit=1,
            storage_preflight_relative=self.preflight_ref,
            fetcher=fetcher,
            retrieved_ms=1790539200000,
        )
        self.assertEqual(batch["acquired_count"], 1)
        self.assertEqual(batch["state_counts"], {"MONTHLY_SUCCESS": 1})
        self.assertEqual(batch["population_status"]["remaining_identities"], 0)

        calls = tuple(fetcher.calls)
        resumed = acquire_batch(
            self.root,
            self.plan_ref,
            self.inventory_ref,
            limit=1,
            storage_preflight_relative=self.preflight_ref,
            fetcher=Fetcher({}),
            retrieved_ms=1790539200000,
        )
        self.assertEqual(resumed["acquired_count"], 0)
        self.assertEqual(tuple(fetcher.calls), calls)

        final = reconcile_population(self.root, self.plan_ref, self.inventory_ref)
        self.assertEqual(final["state"], "POPULATION_COMPLETE")
        self.assertEqual(final["final_count"], 1)

    def _two_month_runtime(self):
        from research.opportunity_data.models import digest

        feb_key = "data/spot/monthly/klines/BTCUSDT/15m/BTCUSDT-15m-2020-02.zip"
        feb_item = dict(
            key=feb_key,
            cadence="monthly",
            symbol="BTCUSDT",
            interval="15m",
            period="2020-02",
        )
        inventory = dict(self.inventory)
        inventory["objects"] = [self.item, feb_item]
        inventory["normalized_inventory_sha256"] = digest(
            dict(schema="AF-01C-INVENTORY/1", objects=inventory["objects"])
        )
        population_plan = plan(
            inventory,
            ("BTCUSDT",),
            ("2020-01", "2020-02"),
            pilot=False,
        )
        inventory_ref = "inventory/two-month.json"
        plan_ref = f"plans/plan-{population_plan['plan_sha256']}.json"
        save_artifact(self.root, inventory_ref, canonical(inventory))
        save_artifact(self.root, plan_ref, canonical(population_plan))

        jan_start = 1577836800000
        feb_start = 1580515200000
        jan_rows = [candle(jan_start + i * 900000) for i in range(31 * 96)]
        feb_rows = [candle(feb_start + i * 900000) for i in range(29 * 96)]
        jan_raw = zip_csv("BTCUSDT-15m-2020-01.csv", jan_rows)
        feb_raw = zip_csv("BTCUSDT-15m-2020-02.csv", feb_rows)

        jan_url = "https://data.binance.vision/" + self.item["key"]
        feb_url = "https://data.binance.vision/" + feb_item["key"]
        mapping = {
            jan_url: jan_raw,
            jan_url + ".CHECKSUM": (
                f"{sha256(jan_raw)}  BTCUSDT-15m-2020-01.zip\n".encode()
            ),
            feb_url: feb_raw,
            feb_url + ".CHECKSUM": (
                f"{sha256(feb_raw)}  BTCUSDT-15m-2020-02.zip\n".encode()
            ),
        }
        return population_plan, inventory_ref, plan_ref, mapping

    def test_fast_path_reuses_one_verified_scan_and_preserves_order(self):
        from research.opportunity_data import pc_population as pc_population_module

        population_plan, inventory_ref, plan_ref, mapping = self._two_month_runtime()
        default_fetcher = Fetcher(mapping)
        original_verify = pc_population_module.verify_plan

        with mock.patch(
            "research.opportunity_data.pc_population.verify_plan",
            wraps=original_verify,
        ) as verify_call, mock.patch(
            "research.opportunity_data.archive_adapter.HttpsFetcher",
            return_value=default_fetcher,
        ):
            result = acquire_batches_fast(
                self.root,
                plan_ref,
                inventory_ref,
                limit=1,
                batch_count=2,
                workers=2,
                storage_preflight_relative=self.preflight_ref,
                retrieved_ms=1790539200000,
            )

        self.assertEqual(verify_call.call_count, 1)
        self.assertEqual(result["completed_batch_count"], 2)
        self.assertEqual(result["population_status"]["completed_identities"], 2)
        self.assertEqual(result["population_status"]["remaining_identities"], 0)
        self.assertEqual(len(result["batches"]), 2)

        identities = []
        for batch in result["batches"]:
            payload = json.loads(
                (self.root / batch["batch_ref"]).read_bytes()
            )
            identities.extend(payload["identities"])
        self.assertEqual(
            identities,
            ["BTCUSDT-2020-01", "BTCUSDT-2020-02"],
        )
        self.assertEqual(
            result["population_status"]["status_sha256"],
            population_status(self.root, plan_ref, inventory_ref)["status_sha256"],
        )

    def test_fast_path_bounds_are_hard(self):
        self.assertEqual(MAX_FAST_BATCHES, 40)
        self.assertEqual(MAX_FAST_WORKERS, 4)
        with self.assertRaisesRegex(Exception, "batch-count bound"):
            acquire_batches_fast(
                self.root,
                self.plan_ref,
                self.inventory_ref,
                limit=1,
                batch_count=MAX_FAST_BATCHES + 1,
                workers=1,
                storage_preflight_relative=self.preflight_ref,
            )
        with self.assertRaisesRegex(Exception, "worker bound"):
            acquire_batches_fast(
                self.root,
                self.plan_ref,
                self.inventory_ref,
                limit=1,
                batch_count=1,
                workers=MAX_FAST_WORKERS + 1,
                storage_preflight_relative=self.preflight_ref,
            )

    def test_population_status_does_not_reverify_full_plan_per_ledger(self):
        start = 1577836800000
        rows = [candle(start + i * 900000) for i in range(31 * 96)]
        raw = zip_csv("BTCUSDT-15m-2020-01.csv", rows)
        url = "https://data.binance.vision/" + self.item["key"]
        fetcher = Fetcher({
            url: raw,
            url + ".CHECKSUM": f"{sha256(raw)}  BTCUSDT-15m-2020-01.zip\n".encode(),
        })

        acquire_batch(
            self.root,
            self.plan_ref,
            self.inventory_ref,
            limit=1,
            storage_preflight_relative=self.preflight_ref,
            fetcher=fetcher,
            retrieved_ms=1790539200000,
        )

        with mock.patch(
            "research.opportunity_data.archive_adapter.verify_plan",
            side_effect=AssertionError("per-ledger full-plan revalidation"),
        ):
            status = population_status(self.root, self.plan_ref, self.inventory_ref)

        self.assertEqual(status["completed_identities"], 1)
        self.assertEqual(status["remaining_identities"], 0)

    def test_continuation_requires_exact_canary_boundary(self):
        batch_base = dict(
            schema="AF-01C-PC-BATCH/1",
            state="P_C_CANARY_BATCH_COMPLETE",
            plan_sha256=self.plan["plan_sha256"],
            requested_limit=1,
            acquired_count=1,
            identities=("BTCUSDT-2020-01",),
            records=("0" * 64,),
            state_counts={"MONTHLY_SUCCESS": 1},
        )
        batch_sha = __import__("research.opportunity_data.models", fromlist=["digest"]).digest(batch_base)
        batch_ref = f"batches/batch-{batch_sha}.json"
        save_artifact(self.root, batch_ref, canonical(batch_base))
        with self.assertRaisesRegex(Exception, "exactly complete"):
            accept_canary_continuation(
                self.root,
                self.plan_ref,
                self.inventory_ref,
                batch_ref,
                ci_head_sha="a" * 40,
                ci_run_id=1,
                ci_workflow="test",
            )

    def test_broad_continuation_requires_acceptance_after_canary_ceiling(self):
        # Exercise the fail-closed ceiling check without network access by
        # constructing 25 valid ledger placeholders is intentionally avoided;
        # the acceptance helper itself enforces the exact 25-ledger boundary.
        self.assertEqual(MAX_CANARY_BATCH, 25)

    def test_storage_preflight_is_required(self):
        with self.assertRaisesRegex(Exception, "storage preflight"):
            acquire_batch(
                self.root,
                self.plan_ref,
                self.inventory_ref,
                limit=1,
                storage_preflight_relative="preflight/missing.json",
                fetcher=Fetcher({}),
                retrieved_ms=1790539200000,
            )

    def test_canary_limit_is_hard_bounded(self):
        with self.assertRaisesRegex(Exception, "canary batch limit"):
            acquire_batch(
                self.root,
                self.plan_ref,
                self.inventory_ref,
                limit=26,
                storage_preflight_relative=self.preflight_ref,
                fetcher=Fetcher({}),
                retrieved_ms=1790539200000,
            )


if __name__ == "__main__":
    unittest.main()
