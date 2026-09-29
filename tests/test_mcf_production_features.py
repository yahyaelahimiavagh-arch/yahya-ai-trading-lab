import unittest

from research.mass_candidate_factory.models import MCFError
from research.mass_candidate_factory.production_features import (
    ProductionBars,
    ProductionFeatureCache,
    liquidity_percentiles,
)

START = 1577836800000
HOUR = 3_600_000


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
        out = liquidity_percentiles({"AAAUSDT": a, "BBBUSDT": b}, 2)
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
