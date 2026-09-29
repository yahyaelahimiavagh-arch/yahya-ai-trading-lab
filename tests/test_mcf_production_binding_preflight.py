import json
import tempfile
import unittest
from pathlib import Path

from research.crisis_lab.acquisition import CanonicalRow
from research.mass_candidate_factory.models import MCFError, canonical
from research.mass_candidate_factory.production import DEVELOPMENT_START_MS
from research.mass_candidate_factory.production_binding_preflight import (
    CADENCE_MS,
    DAY_MS,
    EXPECTED_WINDOW_BARS,
    _classification_evidence,
    _classification_frontier,
    _month_starts,
    _month_stat,
    _monthly_membership,
    _rank_data_eligible,
)
from research.opportunity_data.models import sha256


def _row(t: int, quote_volume: str = "1") -> CanonicalRow:
    return CanonicalRow((
        str(t), "1", "1", "1", "1", "1",
        str(t + CADENCE_MS - 1), quote_volume, "1", "1", "1", "0",
    ))


class ProductionBindingPreflightTest(unittest.TestCase):
    def test_month_grid_matches_frozen_development(self):
        months = _month_starts()
        self.assertEqual(len(months), 34)
        self.assertEqual(months[0], DEVELOPMENT_START_MS)
        self.assertLess(months[-1], months[0] + 3 * 365 * DAY_MS)

    def test_continuity_threshold_and_history_are_fail_closed(self):
        effective = DEVELOPMENT_START_MS
        history_anchor = effective - 60 * DAY_MS
        lower = effective - 30 * DAY_MS

        full = [_row(history_anchor)]
        full.extend(_row(lower + i * CADENCE_MS) for i in range(EXPECTED_WINDOW_BARS))
        full = tuple(sorted(full, key=lambda x: x.open_time_ms))
        times = tuple(x.open_time_ms for x in full)

        stat = _month_stat(full, times, effective)
        self.assertIsNotNone(stat)
        self.assertEqual(stat["observed_bars"], EXPECTED_WINDOW_BARS)
        self.assertEqual(stat["continuity_fraction"], "1")
        self.assertEqual(stat["trailing_30d_quote_volume"], str(EXPECTED_WINDOW_BARS))

        # 14 missing bars => 2866 / 2880 >= 0.995
        pass_rows = tuple(
            row for row in full
            if row.open_time_ms == history_anchor
            or row.open_time_ms >= lower + 14 * CADENCE_MS
        )
        pass_times = tuple(x.open_time_ms for x in pass_rows)
        self.assertIsNotNone(_month_stat(pass_rows, pass_times, effective))

        # 15 missing bars => 2865 / 2880 < 0.995
        fail_rows = tuple(
            row for row in full
            if row.open_time_ms == history_anchor
            or row.open_time_ms >= lower + 15 * CADENCE_MS
        )
        fail_times = tuple(x.open_time_ms for x in fail_rows)
        self.assertIsNone(_month_stat(fail_rows, fail_times, effective))

        short_history = tuple(
            _row(history_anchor + CADENCE_MS) if row.open_time_ms == history_anchor else row
            for row in full
        )
        short_history = tuple(sorted(short_history, key=lambda x: x.open_time_ms))
        short_times = tuple(x.open_time_ms for x in short_history)
        self.assertIsNone(_month_stat(short_history, short_times, effective))


    def test_classification_neutral_liquidity_ranking_is_deterministic(self):
        rows = (
            {"symbol": "BBBUSD T".replace(" ", ""), "trailing_30d_quote_volume": "100"},
            {"symbol": "AAAUSDT", "trailing_30d_quote_volume": "100"},
            {"symbol": "CCCUSDT", "trailing_30d_quote_volume": "250"},
        )
        ranked = _rank_data_eligible(rows)
        self.assertEqual(
            tuple(row["symbol"] for row in ranked),
            ("CCCUSDT", "AAAUSDT", "BBBUSDT"),
        )


    def test_frontier_skips_confirmed_nonordinary_and_expands_below_raw_top50(self):
        rows = []
        rows.append({
            "symbol": "LEVERAGED",
            "trailing_30d_quote_volume": "1000",
            "classification": "NONORDINARY_CONFIRMED",
        })
        for i in range(49):
            rows.append({
                "symbol": f"ORD{i:02d}",
                "trailing_30d_quote_volume": str(900 - i),
                "classification": "ORDINARY_SPOT_CONFIRMED",
            })
        rows.append({
            "symbol": "UNRESOLVED51",
            "trailing_30d_quote_volume": "100",
            "classification": "PRODUCT_CLASSIFICATION_UNRESOLVED",
        })
        ranked = _rank_data_eligible(rows)
        self.assertNotIn("UNRESOLVED51", tuple(row["symbol"] for row in ranked[:50]))
        self.assertEqual(_classification_frontier(ranked), ("UNRESOLVED51",))

    def test_frontier_empty_after_fifty_confirmed_ordinary(self):
        rows = tuple({
            "symbol": f"ORD{i:02d}",
            "trailing_30d_quote_volume": str(1000 - i),
            "classification": "ORDINARY_SPOT_CONFIRMED",
        } for i in range(50)) + ({
            "symbol": "LOWER_UNRESOLVED",
            "trailing_30d_quote_volume": "1",
            "classification": "PRODUCT_CLASSIFICATION_UNRESOLVED",
        },)
        self.assertEqual(_classification_frontier(_rank_data_eligible(rows)), ())

    def test_frontier_keeps_unresolved_when_fewer_than_fifty_potential_members(self):
        rows = (
            {
                "symbol": "ORD",
                "trailing_30d_quote_volume": "10",
                "classification": "ORDINARY_SPOT_CONFIRMED",
            },
            {
                "symbol": "UNRESOLVED",
                "trailing_30d_quote_volume": "9",
                "classification": "PRODUCT_CLASSIFICATION_UNRESOLVED",
            },
        )
        self.assertEqual(_classification_frontier(_rank_data_eligible(rows)), ("UNRESOLVED",))

    def test_zero_eligible_month_is_valid_empty_membership(self):
        month = _monthly_membership((), DEVELOPMENT_START_MS)
        self.assertEqual(month["eligible_count"], 0)
        self.assertEqual(month["selected_count"], 0)
        self.assertEqual(month["selected_symbols"], ())
        self.assertEqual(len(month["ranking_sha256"]), 64)

    def test_independent_classification_evidence_and_exchangeinfo_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            good = {
                "schema": "MCF_HISTORICAL_PRODUCT_CLASSIFICATION/1.0.0",
                "symbol": "BTCUSDT",
                "classification": "ORDINARY_SPOT_CONFIRMED",
                "reviewed": True,
                "source_type": "INDEPENDENT_HISTORICAL_PRODUCT_RECORD",
                "source_reference": "https://example.invalid/historical-binance-spot-record",
            }
            raw = canonical(good)
            ident = sha256(raw)
            path = root / f"BTCUSDT-{ident}.json"
            path.write_bytes(raw)
            classification, evidence_sha = _classification_evidence(root, "BTCUSDT", path.name)
            self.assertEqual(classification, "ORDINARY_SPOT_CONFIRMED")
            self.assertEqual(evidence_sha, ident)

            bad = dict(good)
            bad["source_reference"] = "https://api.binance.com/api/v3/exchangeInfo"
            bad_raw = canonical(bad)
            bad_id = sha256(bad_raw)
            bad_path = root / f"BTCUSDT-{bad_id}.json"
            bad_path.write_bytes(bad_raw)
            with self.assertRaises(MCFError):
                _classification_evidence(root, "BTCUSDT", bad_path.name)


if __name__ == "__main__":
    unittest.main()
