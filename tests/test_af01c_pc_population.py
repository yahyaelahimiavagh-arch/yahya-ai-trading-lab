"""AF-01C P-C isolated population runtime tests."""
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from research.opportunity_data.archive_adapter import plan
from research.opportunity_data.models import canonical, sha256
from research.opportunity_data.pc_population import (
    acquire_batch,
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
