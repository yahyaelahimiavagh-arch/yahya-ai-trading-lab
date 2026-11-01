# YATL — 117s Follower Hold & Trade-Print Coverage Audit

Status: Implemented, offline-tested and actually executed against frozen public Solana observations from 2026-11-01.

**No Helius, DexScreener, GeckoTerminal, Solana RPC or paid API request is made by this audit. No VPS or V2 observer was modified.**

## Reproducible frozen input

Original historical GeckoTerminal public DEX source artifact from PR #193 and GitHub Actions run 41294005096:
https://github.com/yahyaelahimiavagh-arch/yahya-ai-trading-lab/actions/runs/41294005096

It contains 1,173 normalized trade rows, 547 public maker addresses, four sampled liquid pools. The source was stopped on public provider HTTP 429. Every selected pool returned at most the newest 300 trades, so this is NOT a complete day or representative Solana-wide sample.

The input ZIP contains wallet_candidates.json, normalized_trades.jsonl, and sha256_manifest.json; the script verifies SHA-256 before reading trade records.

Implementation: research/smart_money_lab/trade_hold_latency_audit.py
Tests: tests/test_sml_trade_hold_latency_audit.py
CI: .github/workflows/sml-offline-hold-latency.yml

To repeat with the original ZIP saved on disk:

    python -m research.smart_money_lab.trade_hold_latency_audit --source-zip public_data_20261101.zip --output report.json

CI uses actions/download-artifact from the already stored 2026-11-01 GitHub run rather than querying any market endpoint. Its external Actions artifact may expire after 14 days; preserve the original ZIP for future repeatability.

## Actual 2026-11-01 offline numerical results

For the whole sampled data:

| Observation | Number |
| --- | ---: |
| FIFO buy/sell matching FRAGMENTS (not unique independent trades) | 177 |
| Distinct buy signatures contributing to matches | 134 |
| Distinct sell signatures contributing to matches | 127 |
| Wallets with any sampled buy/sell match | 75 |
| Distinct matched tokens | 4 |
| SELL events lacking fully observed opening cost basis | 335 |
| Median holding among fragments | 376 seconds |
| Leader exited before modeled copy-entry at +117s | 61 of 177 |
| Both delayed decisions had past trade prints no older than 30s | 61 of 177 |
| Both delayed decisions had prints no older than 120s | 116 of 177 |
| +180s copy delay with 30s-fresh prints at both decisions | 33 of 177 |

For the ten selected research wallets from the source screen:

| Observation | Number |
| --- | ---: |
| FIFO fragments | 29 |
| Held longer than 117 seconds | 28 |
| Held longer than 900 seconds | 20 |
| With BOTH 30-second-fresh past prints at entry/exit +117 seconds | 8 |

Example wallet AgmLJBMDCqWynYnQiPCuj9ewsNNsBJXyzoUhD9LJzN51 had 11 matching fragments, median holding 3796s, 3 with both delayed print observations, and partial gross spread -13.3265 USD.

Example wallet FHpcNSe6tb2n15bAdq4BkeYWGyZKFD7yLYrH92ng7wCT had 7 matching fragments, median holding 12161s, **zero** with both delayed print observations and partial gross spread -37.8929 USD.

## Conditional exploratory delay-price proxy, NOT an execution backtest

For the 61 matched fragments with entry and exit as-of trade prints no older than 30 seconds, using a modeled 117-second delay after leader buys and sells:

- Median gross historical **trade-print proxy** return = +0.0872%.
- After ASSUMING a hypothetical 150bps TOTAL round-trip friction, median cost-adjusted print proxy = -1.4029%.
- After ASSUMING 300bps friction, median = -2.8710%.

These assumed bps are NOT verified Solana execution costs and the exact outputs are NOT return estimates for a live strategy. Results are conditional on the select 61 with observed indexer prints; missing observations cause selection bias.

The code strictly does NOT use a later-chain-timestamp print to establish the price at an earlier decision. HOWEVER, the time when a third-party indexer actually exposed any earlier-chain-time print to a follower is unknown, and the print is NOT a route quote or fill price.

One economic position may yield multiple matched FIFO fragments; even 177 fragments are not independent. Missing inventory, other pools, transfers, DEX fees, route failure, priority fees and MEV also prevent realized PnL.

## Practical implementation guidance

Keep the ranked list as PROVISIONAL. Do not trade on these results. Select a slower-position, higher-data-coverage observational cohort and then prospectively record the entire position with timestamps and independently verified executable buy/sell route prices before making profitable-copying claims.

No new subscription or API purchase is required for this offline evidence audit.
