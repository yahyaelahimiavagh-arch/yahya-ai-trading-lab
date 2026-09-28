"""Bounded archive engineering fixtures; no market outcomes."""
import copy
import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from research.opportunity_data.archive_inventory import InventoryUnproven, discover, parse_key, valid_symbol, verify
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


def listing(keys=(), *, prefixes=(), truncated=False, token=None, include_count=False):
    contents = "".join(f"<Contents><Key>{key}</Key></Contents>" for key in keys)
    common = "".join(f"<CommonPrefixes><Prefix>{prefix}</Prefix></CommonPrefixes>" for prefix in prefixes)
    continuation = f"<NextContinuationToken>{token}</NextContinuationToken>" if token else ""
    count = f"<KeyCount>{len(keys) + len(prefixes)}</KeyCount>" if include_count else ""
    return (
        f"<ListBucketResult>{count}{contents}{common}"
        f"<IsTruncated>{str(truncated).lower()}</IsTruncated>{continuation}</ListBucketResult>"
    ).encode()


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
        self.monthly_root = "data/spot/monthly/klines/"
        self.daily_root = "data/spot/daily/klines/"
        self.u = lambda prefix, token=None, delimiter=None, start_after=None: (
            "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?" + urlencode({
                **{"list-type": "2", "prefix": prefix},
                **({"delimiter": delimiter} if delimiter is not None else {}),
                **{"max-keys": "1000"},
                **({"continuation-token": token} if token else {}),
                **({"start-after": start_after} if start_after is not None and token is None else {}),
            })
        )
        self.monthly_btc = self.monthly_root + "BTCUSDT/15m/"
        self.monthly_eth = self.monthly_root + "ETHUSDT/15m/"
        self.daily_eth = self.daily_root + "ETHUSDT/15m/"
        self.monthly_btc_start = self.monthly_btc + "BTCUSDT-15m-2019-99"
        self.monthly_eth_start = self.monthly_eth + "ETHUSDT-15m-2019-99"
        self.daily_eth_start = self.daily_eth + "ETHUSDT-15m-2019-99"
        self.pages = {
            self.u(self.monthly_root, delimiter="/"): listing(
                prefixes=[self.monthly_root + "BTCUSDT/"], truncated=True, token="symbols-2"),
            self.u(self.monthly_root, "symbols-2", delimiter="/"): listing(
                prefixes=[self.monthly_root + "ETHUSDT/"]),
            self.u(self.daily_root, delimiter="/"): listing(
                prefixes=[self.daily_root + "ETHUSDT/"]),
            self.u(self.monthly_btc, start_after=self.monthly_btc_start): listing([self.btc]),
            self.u(self.monthly_eth, start_after=self.monthly_eth_start): listing([self.eth]),
            self.u(self.daily_eth, start_after=self.daily_eth_start): listing(self.daily),
        }

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
        tampered_raw = copy.deepcopy(first)
        tampered_raw["raw_inventory_sha256"] = "0" * 64
        with self.assertRaises(InventoryUnproven):
            verify(tampered_raw)
        tampered_bounds = copy.deepcopy(first)
        key = sorted(tampered_bounds["object_range_bounds"])[0]
        tampered_bounds["object_range_bounds"][key]["end_exclusive"] += "-tampered"
        with self.assertRaises(InventoryUnproven):
            verify(tampered_bounds)
        tampered_urls = copy.deepcopy(first)
        tampered_urls["listing_urls"] = tampered_urls["listing_urls"][:-1]
        with self.assertRaises(InventoryUnproven):
            verify(tampered_urls)
        tampered_source = copy.deepcopy(first)
        tampered_source["source_endpoint"] = "https://example.invalid/"
        with self.assertRaises(InventoryUnproven):
            verify(tampered_source)
        with self.assertRaises(InventoryUnproven):
            discover(self.root, fetched_at="2026-09-27T20:00:00Z", fetcher=Fetcher(self.pages), max_pages=5)
        bad = dict(self.pages)
        bad[self.u(self.monthly_root, "symbols-2", delimiter="/")] = listing(
            prefixes=[self.monthly_root + "BTCUSDT/"])
        with self.assertRaises(InventoryUnproven):
            discover(self.root, fetched_at="2026-09-27T20:00:00Z", fetcher=Fetcher(bad))
        self.assertIsNone(parse_key("data/spot/monthly/klines/BTCUSDT/1h/BTCUSDT-1h-2020-01.zip"))
        with self.assertRaises(InventoryUnproven):
            discover(self.root, fetched_at="2026-09-27T20:00:00Z", fetcher=Fetcher({}))

    def test_utf8_usdt_symbol_is_registered_but_still_time_bounded(self):
        symbol = "币安人生USDT"
        self.assertTrue(valid_symbol(symbol))
        self.assertFalse(valid_symbol("USDT"))
        self.assertFalse(valid_symbol("BAD/USDT"))
        self.assertFalse(valid_symbol("BAD\\\\USDT"))
        self.assertFalse(valid_symbol("BAD\\nUSDT"))

        historical = (
            f"data/spot/monthly/klines/{symbol}/15m/"
            f"{symbol}-15m-2020-01.zip"
        )
        parsed = parse_key(historical)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["symbol"], symbol)

        symbol_prefix = self.monthly_root + symbol + "/"
        object_prefix = symbol_prefix + "15m/"
        start_after = object_prefix + symbol + "-15m-2019-99"
        future = object_prefix + symbol + "-15m-2025-10.zip"

        future_only = dict(self.pages)
        future_only[self.u(self.monthly_root, "symbols-2", delimiter="/")] = listing(
            prefixes=[self.monthly_root + "ETHUSDT/", symbol_prefix]
        )
        future_only[self.u(object_prefix, start_after=start_after)] = listing([future])

        snapshot = discover(
            self.root,
            fetched_at="2026-09-27T20:00:00Z",
            fetcher=Fetcher(future_only),
        )
        verify(snapshot)
        self.assertIn(symbol, snapshot["discovered_symbols"]["monthly"])
        self.assertNotIn(symbol, {x["symbol"] for x in snapshot["objects"]})

        historical_pages = dict(future_only)
        historical_pages[self.u(object_prefix, start_after=start_after)] = listing(
            [historical, future]
        )
        historical_snapshot = discover(
            self.root / "utf8-historical",
            fetched_at="2026-09-27T20:00:00Z",
            fetcher=Fetcher(historical_pages),
        )
        verify(historical_snapshot)
        self.assertIn(symbol, {x["symbol"] for x in historical_snapshot["objects"]})
        p = plan(historical_snapshot, (symbol,), ("2020-01",))
        self.assertEqual(p["periods"][0]["symbol"], symbol)

    def test_planner_bound_and_monthly_checksum_restart_admission(self):
        inv = self.inventory()
        p = plan(inv, ("BTCUSDT",), ("2020-01",))
        self.assertEqual(p["plan_sha256"], plan(inv, ("BTCUSDT",), ("2020-01",))["plan_sha256"])
        with self.assertRaises(OpportunityError):
            plan(inv, ("BTCUSDT",), ("2023-01",))
        url = "https://data.binance.vision/" + self.btc
        raw = zip_csv("BTCUSDT-15m-2020-01.csv", [candle(1577836800000 + i * 900000) for i in range(31 * 96)])
        f = Fetcher({url: raw, url + ".CHECKSUM": f"{sha256(raw)}  BTCUSDT-15m-2020-01.zip\n".encode()})
        rec = acquire_period(self.root, p["periods"][0], f, plan_doc=p, inventory=inv, retrieved_ms=1790539200000)
        self.assertEqual(rec["state"], "MONTHLY_SUCCESS")
        self.assertEqual(acquire_period(self.root, p["periods"][0], Fetcher({}), plan_doc=p, inventory=inv, retrieved_ms=1790539200000), rec)
        self.assertEqual(reconcile(self.root, p, inv)["source_gap_count"], 0)
        evidence = canonical(dict(symbol="BTCUSDT", classification="ORDINARY_SPOT_CONFIRMED", reviewed=True,
                                  source_type="INDEPENDENT_HISTORICAL_PRODUCT_RECORD", source_reference="fixture:product-record"))
        evidence_ref = f"classification/record-{sha256(evidence)}.json"
        from research.opportunity_data.storage import save_artifact
        save_artifact(self.root, evidence_ref, evidence)
        result = build_lifecycle(self.root, p, inv, "BTCUSDT", retrieved_ms=1790539200000,
                                 ordinary_evidence_ref=evidence_ref)
        self.assertEqual(result["gap_count"], 0)
        self.assertIsNone(result["listing_time_ms"])
        self.assertIsNone(result["delisting_time_ms"])
        self.assertEqual(result["index_sha256"], build_lifecycle(
            self.root, p, inv, "BTCUSDT", retrieved_ms=1790539200000,
            ordinary_evidence_ref=evidence_ref)["index_sha256"])
        (self.root / rec["canonical_ref"]).write_bytes(b"collision")
        with self.assertRaises(OpportunityError):
            acquire_period(self.root, p["periods"][0], Fetcher({}), plan_doc=p, inventory=inv, retrieved_ms=1790539200000)

    def test_checksum_zip_member_and_explicit_fallback(self):
        inv = self.inventory()
        p = plan(inv, ("ETHUSDT",), ("2020-01",))
        monthly = "https://data.binance.vision/" + self.eth
        raw = zip_csv("wrong.csv", [candle(1577836800000)])
        self.assertEqual(acquire_period(self.root / "bad-member", p["periods"][0], Fetcher({
            monthly: raw, monthly + ".CHECKSUM": sha256(raw).encode()}), plan_doc=p, inventory=inv, retrieved_ms=1790539200000)["state"], "INVALID_MEMBER")
        self.assertEqual(acquire_period(self.root / "bad-sum", p["periods"][0], Fetcher({
            monthly: raw, monthly + ".CHECKSUM": b"0" * 64}), plan_doc=p, inventory=inv, retrieved_ms=1790539200000)["state"], "CHECKSUM_MISMATCH")
        self.assertEqual(acquire_period(self.root / "bad-zip", p["periods"][0], Fetcher({
            monthly: b"bad", monthly + ".CHECKSUM": sha256(b"bad").encode()}), plan_doc=p, inventory=inv, retrieved_ms=1790539200000)["state"], "INVALID_ZIP")
        mapping = {}
        for day, key in enumerate(self.daily):
            url = "https://data.binance.vision/" + key
            stamp = 1577836800000 + day * 86400000
            raw = zip_csv(key.rsplit("/", 1)[-1].replace(".zip", ".csv"),
                          [candle(stamp + i * 900000) for i in range(96)])
            mapping[url] = raw
            mapping[url + ".CHECKSUM"] = sha256(raw).encode()
        rec = acquire_period(self.root / "fallback", p["periods"][0], Fetcher(mapping), plan_doc=p, inventory=inv,
                             retrieved_ms=1790539200000, allow_daily_fallback=True)
        self.assertEqual(rec["state"], "DAILY_FALLBACK_SUCCESS")
        self.assertEqual(rec["fallback_state"], "EXPLICIT")
        self.assertEqual(rec["row_count"], 31 * 96)
        self.assertEqual(rec["gap_count"], 0)
        pilot_root = self.root / "fallback"
        self.assertEqual(reconcile(pilot_root, p, inv)["source_gap_count"], 0)
        evidence = canonical(dict(symbol="ETHUSDT", classification="ORDINARY_SPOT_CONFIRMED", reviewed=True,
                                  source_type="INDEPENDENT_HISTORICAL_PRODUCT_RECORD", source_reference="fixture:product-record"))
        evidence_ref = f"classification/record-{sha256(evidence)}.json"
        from research.opportunity_data.storage import save_artifact
        save_artifact(pilot_root, evidence_ref, evidence)
        admitted = build_lifecycle(pilot_root, p, inv, "ETHUSDT", retrieved_ms=1790539200000,
                                   ordinary_evidence_ref=evidence_ref)
        self.assertEqual(admitted["classification"], "ORDINARY_SPOT_CONFIRMED")
        self.assertEqual(admitted["gap_count"], 0)
        self.assertFalse(admitted["production_eligible"])
        self.assertEqual(len(admitted["index_sha256"]), 64)

    def test_safety_unresolved_and_source_gap(self):
        inv = self.inventory()
        p = plan(inv, ("BTCUSDT",), ("2020-01",))
        rec = acquire_period(self.root, p["periods"][0], Fetcher({}), plan_doc=p, inventory=inv, retrieved_ms=1790539200000)
        self.assertEqual(rec["state"], "MISSING_CHECKSUM")
        self.assertEqual(reconcile(self.root, p, inv)["source_gap_count"], 1)
        with self.assertRaises(OpportunityError):
            build_lifecycle(self.root, p, inv, "BTCUSDT", retrieved_ms=1790539200000)
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
                acquire_period(self.root / name, p["periods"][0], Fetcher({}), plan_doc=p, inventory=inv, retrieved_ms=1790539200000)
            self.assertFalse((self.root / name).exists())

    def test_transport_and_malformed_listing_fail_closed(self):
        from research.crisis_lab.acquisition import AcquisitionError, _validate_https_url
        for url in ("http://data.binance.vision/data/spot/monthly/klines/a",
                    "https://api.binance.com/api/v3/order",
                    "https://fapi.binance.com/fapi/v1/order",
                    "https://user:secret@data.binance.vision/file"):
            with self.assertRaises(AcquisitionError):
                _validate_https_url(url, ("data.binance.vision",))
        _validate_https_url(self.u(self.monthly_root, delimiter="/"), ("s3-ap-northeast-1.amazonaws.com",))
        from research.opportunity_data.archive_inventory import _listing_page
        real_shape = (
            b'<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
            b'<Name>data.binance.vision</Name><Prefix>data/spot/monthly/klines/</Prefix>'
            b'<Delimiter>/</Delimiter><KeyCount>2</KeyCount><MaxKeys>2</MaxKeys>'
            b'<IsTruncated>true</IsTruncated>'
            b'<CommonPrefixes><Prefix>data/spot/monthly/klines/0GBNB/</Prefix></CommonPrefixes>'
            b'<CommonPrefixes><Prefix>data/spot/monthly/klines/0GUSDT/</Prefix></CommonPrefixes>'
            b'<NextContinuationToken>token-2</NextContinuationToken></ListBucketResult>'
        )
        keys, prefixes, more, token = _listing_page(real_shape)
        self.assertEqual(keys, [])
        self.assertEqual(prefixes, [
            "data/spot/monthly/klines/0GBNB/",
            "data/spot/monthly/klines/0GUSDT/",
        ])
        self.assertTrue(more)
        self.assertEqual(token, "token-2")

        outside = "data/spot/monthly/klines/BTCUSDT/15m/BTCUSDT-15m-2025-01.zip"
        permitted = dict(self.pages)
        permitted[self.u(self.monthly_btc, start_after=self.monthly_btc_start)] = listing(
            [self.btc, outside], include_count=True)
        snapshot = discover(self.root, fetched_at="2026-09-27T20:00:00Z", fetcher=Fetcher(permitted))
        self.assertEqual(
            snapshot["inventory_strategy"],
            "HIERARCHICAL_COMMON_PREFIXES_RANGE_BOUNDED/2",
        )
        self.assertEqual(snapshot["discovered_symbols"]["monthly"], ["BTCUSDT", "ETHUSDT"])
        self.assertEqual(snapshot["discovered_symbols"]["daily"], ["ETHUSDT"])
        self.assertNotIn(outside, {x["key"] for x in snapshot["objects"]})

        non_usdt = dict(self.pages)
        non_usdt[self.u(self.daily_root, delimiter="/")] = listing(
            prefixes=[self.daily_root + "ETHBTC/", self.daily_root + "ETHUSDT/"])
        fetched = Fetcher(non_usdt)
        discover(self.root, fetched_at="2026-09-27T20:00:00Z", fetcher=fetched)
        ethbtc_prefix = self.daily_root + "ETHBTC/15m/"
        self.assertNotIn(
            self.u(
                ethbtc_prefix,
                start_after=ethbtc_prefix + "ETHBTC-15m-2019-99",
            ),
            fetched.calls,
        )

        future = dict(self.pages)
        first_2023 = (
            "data/spot/monthly/klines/BTCUSDT/15m/"
            "BTCUSDT-15m-2023-01.zip"
        )
        future[self.u(self.monthly_btc, start_after=self.monthly_btc_start)] = listing(
            [self.btc, first_2023],
            truncated=True,
            token="post-development",
        )
        bounded_fetcher = Fetcher(future)
        bounded_snapshot = discover(
            self.root,
            fetched_at="2026-09-27T20:00:00Z",
            fetcher=bounded_fetcher,
        )
        self.assertIn(self.btc, {x["key"] for x in bounded_snapshot["objects"]})
        self.assertNotIn(
            self.u(self.monthly_btc, token="post-development"),
            bounded_fetcher.calls,
        )

        broken = dict(self.pages)
        broken[self.u(self.monthly_btc, start_after=self.monthly_btc_start)] = listing([
            "data/spot/monthly/klines/BTCUSDT/15m/BTCUSDT-15m-2020-13.zip"])
        with self.assertRaises(InventoryUnproven):
            discover(self.root, fetched_at="2026-09-27T20:00:00Z", fetcher=Fetcher(broken))

        cycle = dict(self.pages)
        cycle[self.u(self.monthly_root, "symbols-2", delimiter="/")] = listing(
            prefixes=[self.monthly_root + "ETHUSDT/"], truncated=True, token="symbols-2")
        with self.assertRaises(InventoryUnproven):
            discover(self.root, fetched_at="2026-09-27T20:00:00Z", fetcher=Fetcher(cycle))

    def test_gap_and_unresolved_classification(self):
        inv = self.inventory()
        p = plan(inv, ("BTCUSDT",), ("2020-01",))
        url = "https://data.binance.vision/" + self.btc
        raw = zip_csv("BTCUSDT-15m-2020-01.csv", [candle(1577836800000), candle(1577838600000)])
        rec = acquire_period(self.root, p["periods"][0], Fetcher({url: raw, url + ".CHECKSUM": sha256(raw).encode()}), plan_doc=p, inventory=inv,
                             retrieved_ms=1790539200000)
        self.assertEqual(rec["state"], "SOURCE_GAP")
        self.assertEqual(rec["admission_state"], "BLOCKED")
        self.assertEqual(reconcile(self.root, p, inv)["source_gap_count"], 1)
        with self.assertRaises(OpportunityError):
            build_lifecycle(self.root, p, inv, "BTCUSDT", retrieved_ms=1790539200000)

    def test_stale_ledger_rejected_for_new_plan_and_inventory(self):
        inv = self.inventory()
        first = plan(inv, ("BTCUSDT",), ("2020-01",))
        entry = first["periods"][0]
        rec = acquire_period(self.root, entry, Fetcher({}), plan_doc=first, inventory=inv,
                             retrieved_ms=1790539200000)
        self.assertEqual(rec["state"], "MISSING_CHECKSUM")
        expanded = plan(inv, ("BTCUSDT", "ETHUSDT"), ("2020-01",))
        self.assertEqual(expanded["periods"][0], entry)
        with self.assertRaisesRegex(OpportunityError, "different inventory/plan"):
            acquire_period(self.root, entry, Fetcher({}), plan_doc=expanded, inventory=inv,
                           retrieved_ms=1790539200000)
        with self.assertRaisesRegex(OpportunityError, "different inventory/plan"):
            reconcile(self.root, expanded, inv)
        changed = copy.deepcopy(inv)
        changed["objects"] = [*inv["objects"], dict(
            key="data/spot/monthly/klines/XRPUSDT/15m/XRPUSDT-15m-2020-01.zip",
            cadence="monthly", symbol="XRPUSDT", interval="15m", period="2020-01")]
        changed["objects"] = sorted(changed["objects"], key=lambda x: x["key"])
        changed["discovered_symbols"]["monthly"] = sorted(
            [*changed["discovered_symbols"]["monthly"], "XRPUSDT"])
        xrp_prefix = "data/spot/monthly/klines/XRPUSDT/15m/"
        changed["object_range_bounds"]["monthly:XRPUSDT"] = {
            "start_after": xrp_prefix + "XRPUSDT-15m-2019-99",
            "end_exclusive": xrp_prefix + "XRPUSDT-15m-2023-01",
        }
        from research.opportunity_data.models import digest
        changed["normalized_inventory_sha256"] = digest(
            dict(schema="AF-01C-INVENTORY/1", objects=changed["objects"]))
        new_plan = plan(changed, ("BTCUSDT",), ("2020-01",))
        with self.assertRaisesRegex(OpportunityError, "different inventory/plan"):
            acquire_period(self.root, new_plan["periods"][0], Fetcher({}), plan_doc=new_plan,
                           inventory=changed, retrieved_ms=1790539200000)
        with self.assertRaisesRegex(OpportunityError, "different inventory/plan"):
            reconcile(self.root, new_plan, changed)
        eth = plan(inv, ("ETHUSDT",), ("2020-01",))
        eth_root = self.root / "selected-objects"
        acquire_period(eth_root, eth["periods"][0], Fetcher({}), plan_doc=eth, inventory=inv,
                       retrieved_ms=1790539200000)
        altered = copy.deepcopy(eth)
        altered["periods"][0]["daily"] = altered["periods"][0]["daily"][:-1]
        altered["plan_sha256"] = digest({k: v for k, v in altered.items() if k != "plan_sha256"})
        with self.assertRaisesRegex(OpportunityError, "different inventory/plan"):
            acquire_period(eth_root, altered["periods"][0], Fetcher({}), plan_doc=altered,
                           inventory=inv, retrieved_ms=1790539200000)
        with self.assertRaisesRegex(OpportunityError, "different inventory/plan"):
            reconcile(eth_root, altered, inv)

    def test_monthly_edges_fail_closed_and_independent_history_exception(self):
        inv = self.inventory()
        p = plan(inv, ("BTCUSDT",), ("2020-01",))
        entry = p["periods"][0]
        url = "https://data.binance.vision/" + self.btc
        start = 1577836800000
        for label, rows in (("missing-start", [candle(start + i * 900000) for i in range(2, 31 * 96)]),
                            ("missing-end", [candle(start), candle(start + 900000)])):
            raw = zip_csv("BTCUSDT-15m-2020-01.csv", rows)
            mapping = {url: raw, url + ".CHECKSUM": sha256(raw).encode()}
            root = self.root / label
            rec = acquire_period(root, entry, Fetcher(mapping), plan_doc=p, inventory=inv,
                                 retrieved_ms=1790539200000)
            self.assertEqual(rec["state"], "SOURCE_GAP")
            self.assertEqual(rec["attempts"][0]["anomaly"], "archive boundary coverage incomplete")
            self.assertEqual(rec["gap_count"], 0)  # no interior gap does not rescue an edge
            source = b"Fixture independent historical listing/delisting notice\n"
            source_ref = f"boundary/source-{sha256(source)}.txt"
            event = dict(schema="AF-01C-HISTORICAL-BOUNDARY/1", object_key=self.btc,
                         symbol="BTCUSDT", reviewed=True,
                         source_type="INDEPENDENT_HISTORICAL_LISTING_EVENT",
                         source_reference="fixture:historical-event",
                         source_artifact_ref=source_ref, source_artifact_sha256=sha256(source),
                         listing_time_ms=start + 2 * 900000 if label == "missing-start" else None,
                         delisting_time_ms=None if label == "missing-start" else start + 2 * 900000)
            evidence = canonical(event)
            ref = f"boundary/evidence-{sha256(evidence)}.json"
            from research.opportunity_data.storage import save_artifact
            accepted_root = self.root / (label + "-evidenced")
            accepted_root.mkdir()
            save_artifact(accepted_root, source_ref, source)
            save_artifact(accepted_root, ref, evidence)
            accepted = acquire_period(accepted_root, entry, Fetcher(mapping), plan_doc=p, inventory=inv,
                                      boundary_evidence_ref=ref, retrieved_ms=1790539200000)
            self.assertEqual(accepted["state"], "MONTHLY_SUCCESS")
            self.assertEqual(reconcile(accepted_root, p, inv)["source_gap_count"], 0)
            (accepted_root / source_ref).write_bytes(b"tampered source")
            with self.assertRaises(OpportunityError):
                reconcile(accepted_root, p, inv)
            with self.assertRaises(OpportunityError):
                acquire_period(accepted_root, entry, Fetcher({}), plan_doc=p, inventory=inv,
                               retrieved_ms=1790539200000)

    def test_partial_month_explicit_daily_fallback(self):
        inv = self.inventory()
        p = plan(inv, ("ETHUSDT",), ("2020-01",))
        monthly_url = "https://data.binance.vision/" + self.eth
        raw = zip_csv("ETHUSDT-15m-2020-01.csv", [candle(1577836800000), candle(1577837700000)])
        mapping = {monthly_url: raw, monthly_url + ".CHECKSUM": sha256(raw).encode()}
        for day, key in enumerate(self.daily):
            url = "https://data.binance.vision/" + key
            start = 1577836800000 + day * 86400000
            daily = zip_csv(key.rsplit("/", 1)[-1].replace(".zip", ".csv"),
                            [candle(start + i * 900000) for i in range(96)])
            mapping[url] = daily
            mapping[url + ".CHECKSUM"] = sha256(daily).encode()
        rec = acquire_period(self.root, p["periods"][0], Fetcher(mapping), plan_doc=p, inventory=inv,
                             retrieved_ms=1790539200000, allow_daily_fallback=True)
        self.assertEqual(rec["attempts"][0]["state"], "SOURCE_GAP")
        self.assertEqual(rec["state"], "DAILY_FALLBACK_SUCCESS")
        self.assertEqual(rec["fallback_state"], "EXPLICIT")
        self.assertEqual(rec["row_count"], 31 * 96)


if __name__ == "__main__":
    unittest.main()
