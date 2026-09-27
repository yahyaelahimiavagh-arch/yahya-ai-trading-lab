"""Bounded archive engineering fixtures; no market outcomes."""
import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from research.opportunity_data.archive_inventory import InventoryUnproven, discover, parse_key, verify
from research.opportunity_data.archive_adapter import acquire_period, build_lifecycle, plan, reconcile
from research.opportunity_data.models import OpportunityError, sha256, canonical


def zip_csv(name, rows):
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w") as bundle:
        info = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        bundle.writestr(info, "\n".join(rows) + "\n")
    return target.getvalue()


def candle(t):
    return f"{t},1,2,1,2,10,{t+899999},20,2,5,10,0"


def listing(keys, *, truncated=False, token=None):
    contents = "".join(f"<Contents><Key>{key}</Key></Contents>" for key in keys)
    continuation = f"<NextContinuationToken>{token}</NextContinuationToken>" if token else ""
    return f"<ListBucketResult>{contents}<IsTruncated>{str(truncated).lower()}</IsTruncated>{continuation}</ListBucketResult>".encode()


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
            raise ValueError("oversized response")
        return value


class AF01C(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.btc = "data/spot/monthly/klines/BTCUSDT/15m/BTCUSDT-15m-2020-01.zip"
        self.eth = "data/spot/monthly/klines/ETHUSDT/15m/ETHUSDT-15m-2020-01.zip"
        self.daily = [f"data/spot/daily/klines/ETHUSDT/15m/ETHUSDT-15m-2020-01-{n:02}.zip" for n in range(1, 32)]
        from urllib.parse import urlencode
        self.u = lambda prefix, token=None: "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?" + urlencode({
            **{"list-type": "2", "prefix": prefix, "max-keys": "1000"},
            **({"continuation-token": token} if token else {})})
        self.pages = {self.u("data/spot/monthly/klines/"): listing([self.btc], truncated=True, token="continue"),
                      self.u("data/spot/monthly/klines/", "continue"): listing([self.eth]),
                      self.u("data/spot/daily/klines/"): listing(self.daily)}

    def tearDown(self):
        self.temp.cleanup()

    def inventory(self):
        return discover(self.root, fetched_at="2026-09-27T20:00:00Z", fetcher=Fetcher(self.pages))

    def test_inventory_pagination_determinism_and_unproven(self):
        first = self.inventory()
        second = self.inventory()
        self.assertEqual(first["normalized_inventory_sha256"], second["normalized_inventory_sha256"])
        self.assertEqual(len(first["objects"]), 33)
        verify(first)
        with self.assertRaises(InventoryUnproven):
            discover(self.root, fetched_at="2026-09-27T20:00:00Z", fetcher=Fetcher(self.pages), max_pages=2)
        bad = dict(self.pages)
        bad[self.u("data/spot/monthly/klines/", "continue")] = listing([self.btc])
        with self.assertRaises(InventoryUnproven):
            discover(self.root, fetched_at="2026-09-27T20:00:00Z", fetcher=Fetcher(bad))
        self.assertIsNone(parse_key("data/spot/monthly/klines/BTCUSDT/1h/BTCUSDT-1h-2020-01.zip"))
        with self.assertRaises(InventoryUnproven):
            discover(self.root, fetched_at="2026-09-27T20:00:00Z", fetcher=Fetcher({}))

    def test_planner_bound_and_monthly_checksum_restart_admission(self):
        inv = self.inventory()
        p = plan(inv, ("BTCUSDT",), ("2020-01",))
        self.assertEqual(p["plan_sha256"], plan(inv, ("BTCUSDT",), ("2020-01",))["plan_sha256"])
        with self.assertRaises(OpportunityError):
            plan(inv, ("BTCUSDT",), ("2023-01",))
        url = "https://data.binance.vision/" + self.btc
        raw = zip_csv("BTCUSDT-15m-2020-01.csv", [candle(1577836800000), candle(1577837700000)])
        f = Fetcher({url: raw, url + ".CHECKSUM": f"{sha256(raw)}  BTCUSDT-15m-2020-01.zip\n".encode()})
        rec = acquire_period(self.root, p["periods"][0], f, retrieved_ms=1790539200000)
        self.assertEqual(rec["state"], "MONTHLY_SUCCESS")
        self.assertEqual(acquire_period(self.root, p["periods"][0], Fetcher({}), retrieved_ms=1790539200000), rec)
        self.assertEqual(reconcile(self.root, p)["source_gap_count"], 0)
        evidence = canonical(dict(symbol="BTCUSDT", classification="ORDINARY_SPOT_CONFIRMED", reviewed=True,
                                  source_type="INDEPENDENT_HISTORICAL_PRODUCT_RECORD", source_reference="fixture:product-record"))
        evidence_ref = f"classification/record-{sha256(evidence)}.json"
        from research.opportunity_data.storage import save_artifact
        save_artifact(self.root, evidence_ref, evidence)
        result = build_lifecycle(self.root, p, "BTCUSDT", retrieved_ms=1790539200000,
                                 ordinary_evidence_ref=evidence_ref)
        self.assertEqual(result["gap_count"], 0)
        self.assertIsNone(result["listing_time_ms"])
        self.assertIsNone(result["delisting_time_ms"])
        self.assertEqual(result["index_sha256"], build_lifecycle(
            self.root, p, "BTCUSDT", retrieved_ms=1790539200000,
            ordinary_evidence_ref=evidence_ref)["index_sha256"])
        (self.root / rec["canonical_ref"]).write_bytes(b"collision")
        with self.assertRaises(OpportunityError):
            acquire_period(self.root, p["periods"][0], Fetcher({}), retrieved_ms=1790539200000)

    def test_checksum_zip_member_and_explicit_fallback(self):
        inv = self.inventory()
        p = plan(inv, ("ETHUSDT",), ("2020-01",))
        monthly = "https://data.binance.vision/" + self.eth
        raw = zip_csv("wrong.csv", [candle(1577836800000)])
        self.assertEqual(acquire_period(self.root / "bad-member", p["periods"][0], Fetcher({
            monthly: raw, monthly + ".CHECKSUM": sha256(raw).encode()}), retrieved_ms=1790539200000)["state"], "INVALID_MEMBER")
        self.assertEqual(acquire_period(self.root / "bad-sum", p["periods"][0], Fetcher({
            monthly: raw, monthly + ".CHECKSUM": b"0" * 64}), retrieved_ms=1790539200000)["state"], "CHECKSUM_MISMATCH")
        self.assertEqual(acquire_period(self.root / "bad-zip", p["periods"][0], Fetcher({
            monthly: b"bad", monthly + ".CHECKSUM": sha256(b"bad").encode()}), retrieved_ms=1790539200000)["state"], "INVALID_ZIP")
        mapping = {}
        for day, key in enumerate(self.daily):
            url = "https://data.binance.vision/" + key
            stamp = 1577836800000 + day * 86400000
            raw = zip_csv(key.rsplit("/", 1)[-1].replace(".zip", ".csv"),
                          [candle(stamp + i * 900000) for i in range(96)])
            mapping[url] = raw
            mapping[url + ".CHECKSUM"] = sha256(raw).encode()
        rec = acquire_period(self.root / "fallback", p["periods"][0], Fetcher(mapping),
                             retrieved_ms=1790539200000, allow_daily_fallback=True)
        self.assertEqual(rec["state"], "DAILY_FALLBACK_SUCCESS")
        self.assertEqual(rec["fallback_state"], "EXPLICIT")
        self.assertEqual(rec["row_count"], 31 * 96)
        self.assertEqual(rec["gap_count"], 0)

    def test_safety_unresolved_and_source_gap(self):
        inv = self.inventory()
        p = plan(inv, ("BTCUSDT",), ("2020-01",))
        rec = acquire_period(self.root, p["periods"][0], Fetcher({}), retrieved_ms=1790539200000)
        self.assertEqual(rec["state"], "MISSING_CHECKSUM")
        self.assertEqual(reconcile(self.root, p)["source_gap_count"], 1)
        with self.assertRaises(OpportunityError):
            build_lifecycle(self.root, p, "BTCUSDT", retrieved_ms=1790539200000)
        with self.assertRaises(OpportunityError):
            plan(inv, ("BTCUSDT",) * 11, ("2020-01",))
        from research.opportunity_data.archive_adapter import classify
        self.assertEqual(classify("BTCUPUSDT"), "NONORDINARY_CONFIRMED")
        self.assertEqual(classify("BTCUSDT"), "PRODUCT_CLASSIFICATION_UNRESOLVED")
        from research.opportunity_data.models import development_path
        for name in ("p10", "fresh_oos", "recent_reserve"):
            with self.assertRaises(OpportunityError):
                development_path(self.root, name)
            with self.assertRaises(OpportunityError):
                acquire_period(self.root / name, p["periods"][0], Fetcher({}), retrieved_ms=1790539200000)
            self.assertFalse((self.root / name).exists())

    def test_transport_and_malformed_listing_fail_closed(self):
        from research.crisis_lab.acquisition import AcquisitionError, _validate_https_url
        for url in ("http://data.binance.vision/data/spot/monthly/klines/a",
                    "https://api.binance.com/api/v3/order",
                    "https://fapi.binance.com/fapi/v1/order",
                    "https://user:secret@data.binance.vision/file"):
            with self.assertRaises(AcquisitionError):
                _validate_https_url(url, ("data.binance.vision",))
        _validate_https_url(self.u("data/spot/monthly/klines/"), ("s3-ap-northeast-1.amazonaws.com",))
        broken = dict(self.pages)
        broken[self.u("data/spot/monthly/klines/", "continue")] = listing([
            "data/spot/monthly/klines/BTCUSDT/15m/BTCUSDT-15m-2020-13.zip"])
        with self.assertRaises(InventoryUnproven):
            discover(self.root, fetched_at="2026-09-27T20:00:00Z", fetcher=Fetcher(broken))
        cycle = dict(self.pages)
        cycle[self.u("data/spot/monthly/klines/", "continue")] = listing([self.eth], truncated=True, token="continue")
        with self.assertRaises(InventoryUnproven):
            discover(self.root, fetched_at="2026-09-27T20:00:00Z", fetcher=Fetcher(cycle))

    def test_gap_and_unresolved_classification(self):
        inv = self.inventory()
        p = plan(inv, ("BTCUSDT",), ("2020-01",))
        url = "https://data.binance.vision/" + self.btc
        raw = zip_csv("BTCUSDT-15m-2020-01.csv", [candle(1577836800000), candle(1577838600000)])
        rec = acquire_period(self.root, p["periods"][0], Fetcher({url: raw, url + ".CHECKSUM": sha256(raw).encode()}),
                             retrieved_ms=1790539200000)
        self.assertEqual(rec["state"], "SOURCE_GAP")
        self.assertEqual(rec["admission_state"], "BLOCKED")
        self.assertEqual(reconcile(self.root, p)["source_gap_count"], 1)
        with self.assertRaises(OpportunityError):
            build_lifecycle(self.root, p, "BTCUSDT", retrieved_ms=1790539200000)


if __name__ == "__main__":
    unittest.main()
