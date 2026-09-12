"""Immutable P1 market and timeframe policy.

The research data layer is public and credential-free. Testnet account access
remains isolated in ``yatl.account`` and is not imported here.
"""

from types import MappingProxyType


BINANCE_PUBLIC_BASE_URL = "https://api.binance.com"
BINANCE_MARKET_DATA_BASE_URL = "https://data-api.binance.vision"
DATA_SOURCE = "BINANCE_SPOT_PUBLIC"
SYMBOLS = ("BTCUSDT", "ETHUSDT")
INTERVAL_MILLISECONDS = MappingProxyType({
    "15m": 15 * 60 * 1000,
    "1h": 60 * 60 * 1000,
    "4h": 4 * 60 * 60 * 1000,
})
TIMEFRAME_POLICY = MappingProxyType({
    "primary_analysis": "1h",
    "higher_timeframe_regime": "4h",
    "entry_context": "15m",
    "execution": "NOT_ENABLED",
})
