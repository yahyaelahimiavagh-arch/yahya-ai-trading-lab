import unittest
from unittest.mock import patch

from research.crisis_lab.acquisition import CanonicalRow
from research.opportunity_data.index import UniverseIndex
from research.opportunity_data.lifecycle import Lifecycle
from research.opportunity_data.models import AdmittedDataset, digest as opportunity_digest
from research.mass_candidate_factory.production import DEVELOPMENT_START_MS
from research.mass_candidate_factory.production_universe import build

JAN1 = 1577836800000
MARCH1 = DEVELOPMENT_START_MS
CADENCE = 900_000
H = "a" * 64


def rows(multiplier=1, missing=()):
    missing = set(missing)
    result = []
    count = (MARCH1 - JAN1) // CADENCE
    for i in range(count):
        if i in missing:
            continue
        opened = JAN1 + i * CADENCE
        price = "100"
        quote = str(1000 * multiplier)
        result.append(CanonicalRow((
            str(opened), price, "101", "99", price, "10",
            str(opened + CADENCE - 1), quote, "20", "5", "500", "0",
        )))
    return tuple(result)


def dataset(symbol, multiplier=1, missing=()):
    rs = rows(multiplier, missing)
    return AdmittedDataset(
        dataset_id=f"DEV/{symbol}/15m",
        symbol=symbol,
        interval="15m",
        venue="BINANCE_SPOT",
        source="SYNTHETIC",
        requested_start_ms=JAN1,
        requested_end_ms=MARCH1,
        retrieved_at_ms=MARCH1 + 1,
        source_refs=("SYNTHETIC/v1",),
        rows=rs,
        content_sha256=("1" if symbol == "AAAUSDT" else "2" if symbol == "BBBUSDT" else "3") * 64,
        quality_sha256=("4" if symbol == "AAAUSDT" else "5" if symbol == "BBBUSDT" else "6") * 64,
        gap_sha256=("7" if symbol == "AAAUSDT" else "8" if symbol == "BBBUSDT" else "9") * 64,
        quality_verdict="PASS_WITH_GAPS" if missing else "PASS_CONTIGUOUS",
    )


def lifecycle(symbol):
    return Lifecycle(
        symbol=symbol,
        base_asset=symbol[:-4],
        quote_asset="USDT",
        venue="BINANCE_SPOT",
        instrument_type="SPOT",
        spot_allowed=True,
        leveraged_token_flag=False,
        first_admitted_data_ms=JAN1,
        last_admitted_data_ms=MARCH1 - CADENCE,
        listing_time_ms=None,
        delisting_time_ms=None,
        lifecycle_status="ACTIVE",
        lifecycle_source_refs=("SYNTHETIC/v1",),
    ).frozen()


def index_fixture():
    records = tuple(lifecycle(x) for x in ("AAAUSDT", "BBBUSDT", "CCCUSDT"))
    # 20 missing 15m bars in the trailing 30d window is below 99.5% continuity.
    trailing_start_index = (30 * 86_400_000) // CADENCE
    missing = tuple(range(trailing_start_index, trailing_start_index + 20))
    datasets = (
        dataset("AAAUSDT", 1),
        dataset("BBBUSDT", 2),
        dataset("CCCUSDT", 3, missing),
    )
    index = UniverseIndex(
        records=records,
        datasets=datasets,
        quality_refs=tuple(sorted((d.dataset_id, d.quality_sha256) for d in datasets)),
        index_sha256="",
    )
    return UniverseIndex(index.records, index.datasets, index.quality_refs, opportunity_digest(index.payload()))


class ProductionUniverseTest(unittest.TestCase):
    def test_monthly_membership_is_lagged_ranked_and_gap_aware(self):
        index = index_fixture()
        with patch(
            "research.mass_candidate_factory.production_universe._month_starts",
            return_value=(MARCH1,),
        ):
            binding, audits, audit_doc = build(index, population_manifest_sha256=H)

        self.assertEqual(len(binding.membership_snapshots), 1)
        self.assertEqual(binding.membership_snapshots[0].symbols, ("AAAUSDT", "BBBUSDT"))
        self.assertEqual(audits[0].eligible_count, 2)
        self.assertEqual(audits[0].selected_count, 2)
        ranking = audit_doc["monthly_evidence"][0]["ranking"]["selected_ranked"]
        self.assertEqual(ranking, ("BBBUSDT", "AAAUSDT"))
        rejected = {
            row["symbol"]: row["reason"]
            for row in audit_doc["monthly_evidence"][0]["rejected"]
        }
        self.assertEqual(rejected["CCCUSDT"], "CONTINUITY_LT_0_995")
        self.assertFalse(audit_doc["safety"]["performance_read"])
        self.assertFalse(audit_doc["safety"]["p10_read"])

    def test_population_manifest_identity_is_required(self):
        index = index_fixture()
        with patch(
            "research.mass_candidate_factory.production_universe._month_starts",
            return_value=(MARCH1,),
        ):
            with self.assertRaises(ValueError):
                build(index, population_manifest_sha256="bad")


if __name__ == "__main__":
    unittest.main()
