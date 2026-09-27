# AF-01B Opportunity Data Foundation — Implementation Closeout v1.0

Status: **IMPLEMENTATION ACCEPTED / MERGED**

Date: 2026-09-27

Work unit:
`AF-01B-OPPORTUNITY-DATA-FOUNDATION-IMPLEMENTATION`

Merged PR:
`#147 research: implement AF-01B point-in-time opportunity data foundation`

Work Final HEAD before Director patch:
`4191ff644feb8abdd923e14021fcdb56bf3f9500`

Director-reviewed Final HEAD:
`7a34dc9a2d30d95b8d6461dc07f60bf2d32f9437`

Merged main commit:
`d6b0c2662d7c92123a099fd1e9cf79d16c0f3b5e`

Final-HEAD GitHub Actions:
- run `36341399844`
- `unit-and-safety`: SUCCESS
- `accepted-public-data`: SUCCESS

## Implemented

- point-in-time lifecycle records with nullable official listing/delisting;
- explicit distinction between first admitted data and official listing time;
- CRL-compatible canonical OHLCV/trade-count validation;
- explicit gap maps;
- deterministic UTC views for 15m / 1h / 4h / 1d;
- lagged liquidity metrics;
- deterministic historical universe index;
- read-only MCF data binding;
- Development-only evidence isolation.

## Director hardening before merge

Independent review found and fixed two edge cases before merge:

1. a stale dataset could remain eligible when `warmup_bars=0`;
2. MULTI_ASSET availability could be satisfied by a companion lacking one or
   more policy-required intervals.

The merged implementation now requires:
- the latest completed interval bar at evaluation timestamp;
- all policy-required intervals for companion assets.

Both changes are covered by regression tests and passed Final-HEAD CI.

## Bounded validation

Engineering-only validation:
- 3 synthetic symbols;
- 1,151 synthetic candles;
- explicit known gap;
- deterministic index rebuild;
- no market-performance selection.

Reported benchmark from implementation Work:
- validation about 55,263 rows/sec;
- index build about 0.020 sec;
- derived views about 5,568 rows/sec;
- liquidity about 3,500 metrics/sec;
- measured peak memory about 1.15 MB.

These are engineering fixture measurements only.

## Evidence boundary

- Fresh OOS read: false
- recent reserve read: false
- P10 read: false
- P10 write: false
- strategy selection: false
- full-universe population: false
- P11: locked
- Live: unauthorized

## Interpretation

AF-01B is a reusable data-admission foundation. It does not establish that a
historical Binance universe is complete, because official current symbol lists
must not be treated as a complete historical delisted-symbol manifest.

Bulk historical population therefore requires a separately frozen acquisition
and archive-inventory plan before a broad-universe claim is allowed.
