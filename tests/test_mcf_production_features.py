import unittest

from research.mass_candidate_factory.models import MCFError
from research.mass_candidate_factory.production import MembershipSnapshot, ProductionUniverseBinding
from research.mass_candidate_factory.production_features import (
    ProductionBars,
    ProductionFeatureCache,
    liquidity_percentiles,
)

START = 1577836800000
HOUR = 3_600_000
H = "a" * 64


def binding(symbols):
    return ProductionUniverseBinding(
        universe_evidence_id="MCF-PROD-001-UNIVERSE-EVIDENCE",
        population_manifest_sha256=H,
        quality_index_sha256=H,
        universe_policy_sha256=H,
        membership_snapshots=(MembershipSnapshot(START, tuple(sorted(symbols)), H),),
    )


def bars(symbol="AAAUSDT", times=None, quote=None):
    times = times or tuple(START + i * HOUR for i in range(8))
    n = len(times)
    closes = tuple(100.0 + i for i in range(n))
    return ProductionBars(
        dataset_id="SYNTHETIC-" + symbol,
        symbol=symbol,
        timeframe="1h",
        times=times,
        opens=closes,
        highs=tuple(x + 1 for x in closes),
        lows=tuple(x - 1 for x in closes),
        closes=closes,
        base_volume=tuple(10.0 + i for i in range(n)),
        quote_volume=quote or tuple(1000.0 + 10 * i for i in range(n)),
        trade_count=tuple(20.0 + i for i in range(n)),
    )


class ProductionFeaturesTest(unittest.TestCase):
    def test_gap_breaks_exact_rolling_window(self):
        times = (
            START,
            START + HOUR,
            START + 3 * HOUR,
            START + 4 * HOUR,
            START + 5 * HOUR,
        )
        cache = ProductionFeatureCache(bars(times=times))
        rolling = cache.rolling("closes", 2, lag=0, statistic="mean")
        self.assertIsNotNone(rolling[1])
        self.assertIsNone(rolling[2])
        self.assertIsNotNone(rolling[3])

        ret = cache.lagged_return(1)
        self.assertIsNone(ret[2])
        self.assertIsNotNone(ret[3])

    def test_rolling_fastpath_exact_legacy_parity_all_statistics_and_gaps(self):
        from array import array
        from dataclasses import replace
        from math import sqrt
        from random import Random
        from statistics import median

        def reference(cache, field, window, lag, statistic, q):
            source = getattr(cache.bars, field)
            result = []
            for i in range(len(source)):
                indexes = cache._complete_indexes(i - lag, window)
                if indexes is None:
                    result.append(None)
                    continue
                values = [float(source[j]) for j in indexes]
                if statistic == "mean":
                    value = sum(values) / len(values)
                elif statistic == "sum":
                    value = sum(values)
                elif statistic == "std":
                    mu = sum(values) / len(values)
                    value = sqrt(max(0.0, sum((x - mu) ** 2 for x in values) / len(values)))
                elif statistic == "min":
                    value = min(values)
                elif statistic == "max":
                    value = max(values)
                elif statistic == "median":
                    value = float(median(values))
                else:
                    ordered = sorted(values)
                    value = ordered[int(float(q) * (len(ordered) - 1))]
                result.append(value)
            return tuple(result)

        for timeframe, cadence in (("15m", 900_000), ("1h", HOUR), ("4h", 4 * HOUR)):
            rng = Random(20261020)
            n = 630
            times = tuple(
                START + i * cadence
                + (2 * cadence if i >= 55 else 0)
                + (4 * cadence if i >= 305 else 0)
                for i in range(n)
            )
            prices = tuple(100.0 + rng.uniform(-12.0, 12.0) for _ in range(n))
            volume = tuple(1000.0 + rng.uniform(-150.0, 150.0) for _ in range(n))
            source = replace(
                bars(times=times),
                timeframe=timeframe,
                opens=prices,
                highs=tuple(p + 1.0 for p in prices),
                lows=tuple(p - 1.0 for p in prices),
                closes=prices,
                quote_volume=volume,
            )
            packed = replace(
                source,
                times=array("q", source.times),
                **{
                    field: array("d", getattr(source, field))
                    for field in (
                        "opens", "highs", "lows", "closes",
                        "base_volume", "quote_volume", "trade_count"
                    )
                },
            )

            for label, payload in (("tuple", source), ("array", packed)):
                cache = ProductionFeatureCache(payload)
                for statistic in ("mean", "sum", "std", "min", "max", "median", "quantile"):
                    for window, lag in (
                        (1, 0), (5, 1), (20, 0), (200, 2),
                        (500, 3), (700, 0), (0, 1), (20, 800),
                    ):
                        with self.subTest(
                            timeframe=timeframe, representation=label,
                            statistic=statistic, window=window, lag=lag,
                        ):
                            kwargs = {"quantile": 0.75} if statistic == "quantile" else {}
                            actual = cache.rolling(
                                "closes", window, lag=lag,
                                statistic=statistic, **kwargs,
                            )
                            expected = reference(
                                cache, "closes", window, lag, statistic,
                                kwargs.get("quantile"),
                            )
                            self.assertEqual(actual, expected)
                            self.assertIs(actual, cache.rolling(
                                "closes", window, lag=lag,
                                statistic=statistic, **kwargs,
                            ))
                cache.clear_transient()
                self.assertEqual(cache._cache, {})

    def test_peer_return_does_not_bridge_gap(self):
        target = bars("AAAUSDT")
        peer_times = tuple(t for i, t in enumerate(target.times) if i != 4)
        peer = bars("BTCUSDT", times=peer_times)
        cache = ProductionFeatureCache(target, {"BTCUSDT": peer})
        values = cache.peer_return("BTCUSDT", 1)
        self.assertIsNone(values[4])
        self.assertIsNone(values[5])
        self.assertIsNotNone(values[6])

    def test_liquidity_percentile_is_point_in_time(self):
        a = ProductionFeatureCache(bars("AAAUSDT", quote=(100, 100, 100, 100, 100, 100, 100, 100)))
        b = ProductionFeatureCache(bars("BBBUSDT", quote=(200, 200, 200, 200, 200, 200, 200, 200)))
        out = liquidity_percentiles(
            {"AAAUSDT": a, "BBBUSDT": b},
            2,
            binding(("AAAUSDT", "BBBUSDT")),
        )
        self.assertIsNone(out["AAAUSDT"][0])
        self.assertIsNone(out["AAAUSDT"][1])
        self.assertEqual(out["AAAUSDT"][2], 0.0)
        self.assertEqual(out["BBBUSDT"][2], 1.0)

    def test_rejects_non_development_or_invalid_ohlc(self):
        b = bars()
        with self.assertRaises(MCFError):
            ProductionBars(
                b.dataset_id, b.symbol, b.timeframe, b.times,
                b.opens, tuple(1.0 for _ in b.highs), b.lows, b.closes,
                b.base_volume, b.quote_volume, b.trade_count,
            ).validate()


if __name__ == "__main__":
    unittest.main()
