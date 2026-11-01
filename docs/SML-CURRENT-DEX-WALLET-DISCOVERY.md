# YATL — Current Solana Public DEX Wallet Discovery

**Status:** Independent one-shot market-data collection and research screening; no proven profitable traders or authorized live trading.

## Why this exists

The June 2026 dataset produced historical "2x token" candidates that were largely inactive, with heavy cross-wallet overlap and common fee payers. It is NOT a current trader ranking.

This module instead samples **recent trades on actively traded Solana pools** using the documented no-key GeckoTerminal API:

- Public API: https://api.geckoterminal.com/docs/index.html
- Code: `research/smart_money_lab/current_dex_discovery.py`
- Tests: `tests/test_sml_current_dex_discovery.py`
- One-shot CI: `.github/workflows/sml-current-dex-discovery.yml`

## Actual bounded workflow

1. Read one page of Solana trending pools and one page of top pools.
2. Select up to 16 **different token pools**, with reported reserve of at least USD 100,000, 24h volume of at least USD 25,000, and pool age of at least 3 days.
3. Prefer moderate rather than extreme transaction count to maximize historical coverage of the public **newest-300-trades** endpoint.
4. Fetch at most 300 recent indexed trades per pool (no Helius RPC, no wallet secrets, no trading).
5. Require valid Solana maker/signer address, transaction signature, direction matching actual pool base/quote tokens, non-anomalous row, timestamp within last 24 hours and positive quantity/volume. Preserve exact strings as Decimal.
6. Deduplicate observations by maker, transaction, base mint, side, quantity and gross USD amount. This is approximate cross-route dedup; it may discard genuinely separate same-size swaps.
7. Match only previously **observed** buy quantities to later observed sells via FIFO, using quoted USD turnover. Output **indicative sampled gross spread**; do not call it realized trader PnL.
8. Highlight wallets with more than one distinct token and at least one within-sample known-basis sell. Flag short bursts and extremely high frequency. Rank for **further inspection only**, not automated copying.
9. Upload summary JSON, addresses CSV, normalized trade evidence JSONL and SHA-256 manifest as a temporary GitHub Actions artifact.

The API docs disagree on rate limits, approximately 10/minute vs 30/minute. The implementation deliberately uses **at least 7 seconds between calls**, with a hard limit of 21 calls and immediate cessation on HTTP/provider failure. This is one-shot research, not recurring monitoring.

## Scientific and security limitations

- Selected trending and top pools are **biased**, not a random sample of Solana DEX markets.
- The newest 300 recent trades in an active pool may cover just minutes, not the full day; no longer-history claim can be made.
- Third-party reported "tx_from_address" is NOT proof of wallet beneficial ownership; it could represent a router, bot, delegated signer or aggregator.
- Observed buys/sells only within the selected pools cannot establish opening inventory, external transfers, cross-pool swaps, exact token-unit cost basis or realized wallet profits.
- Gross spread excludes DEX routing, gas, priority fees, quote expiry, failed orders, MEV and follower execution impact.
- No full fee-payer cluster audit is performed in this stage.
- The source's reported price and USD turnover should not be interpreted as available follower quotes 117s later.
- Observations are historical cached snapshots obtained on the run date, NOT prospectively recorded signals before the trades.
- CSV addresses are public research candidates; do not use them for any automatic trade or paid follow signals.
- V2 Ubuntu observer, publisher, PR #189, and Helius request budget remain untouched.

## Decision criterion

The immediate evidence sought is **a list of CURRENTLY ACTIVE candidate wallet addresses with actual buy/sell transaction evidence**. Whether they have repeatable trader skill and whether following their future trades is profitable remain distinct unproven hypotheses. Validating a small shortlist requires independent source transaction receipts, observed opening balances and a forward selection cutoff.

No new subscription, RPC purchase or VPS instance is justified by this proof of concept.
