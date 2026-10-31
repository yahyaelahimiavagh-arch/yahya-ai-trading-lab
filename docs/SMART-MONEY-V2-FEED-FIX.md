# YATL Smart Money Lab — V0.2 feed/quote correction

**Development status:** isolated changes on the existing research PR.
**Operator rule:** DO NOT run `git pull`, restart, overwrite or delete any files
in the active `~/yatl-smart-money` paper pilot. Do not restart
`yatl-sml-paper` or `yatl-sml-hostinger`. The current run remains a
read-only experimental baseline, including **zero paper fills** so far.

## Evidence motivating the patch

Observed live in first 24h pilot: ~308 unique reported events, 0 fills,
2,804 unparsed/unsupported *rows counted across polling cycles*; 45
`missing_quote`, 12 `illiquid`, 12 `no_matching_position` account-level
rejections. These are not distinct economic opportunities and
`unique_signals_seen` included pre-start history in the old implementation.

- Live ingestion now refuses to ask DEX prices for trades before the
  observer's `start_at`. Parsed historical rows are not counted as new signals.
- SWAP parser labels missing swap event, ambiguous multi-asset leg, unsupported
  pair, lack of SOL/USD reference, or malformed amount/time; never invents
  wallet trades from token transfers or ambiguous multihop instructions.
- Solana native official USDT mint `Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB`
  is allowed as another nominal USD quote. Just like USDC, USD$1 per unit is
  assumed for historical paper scoring; **stablecoin depegs are not modeled**.
- Batch DEX Screener price lookup may trigger at most **three**
  single-token token-pairs lookups for missing mints. Same exact base mint
  requirements apply; a reverse/quote-side pair cannot be misrepresented as
  the requested token's USD price.
- Optional `discover --source profiles` scans currently listed token profiles
  rather than paid boosts, but before querying Helius filters their pools by
  >=$200k USD DEX liquidity, >=$30k reported 24h volume, and >=7d pool age.
  This is **not a leaderboard**, not independent discovery of smart money,
  and may return zero or poor candidates. Every wallet still needs strict
  historical vetting.
- Phone dashboard supports redacted aggregate parser-reason counters. In the
  old run these counters are absent/zero until a **new** observer is used.
- The existing ≥$20,000 DEX liquidity fill threshold, 5% portfolio halt, fees,
  slippage, and all order/exposure limits remain **unchanged**. No real order
  or wallet signing code is added.

## Safe offline smoke test now (zero Helius credits, does not change active run)

```bash
git clone --depth 1 --branch research/smart-money-lab-paper-v1 --single-branch \
  https://github.com/yahyaelahimiavagh-arch/yahya-ai-trading-lab.git \
  ~/yatl-smart-money-v2-qa
cd ~/yatl-smart-money-v2-qa
python3 -m unittest discover -s tests -p 'test_smart_money_lab.py' -v
python3 -m unittest discover -s tests -p 'test_smart_money_live_monitor.py' -v
python3 -m unittest discover -s tests -p 'test_smart_money_hostinger.py' -v
```

No CLI/API key is needed for these deterministic offline tests.

## After old 24h window completes and its full report is archived

1. Preserve `state.json`, `report.json`, and dashboard; do not overwrite
   their timestamps or compare pilot PnL with a modified parser as if identical.
2. Check the historical `helius_budget.json`. The V0.2 pilot MUST reuse the
   same cumulative cap; never reset credits by using a new worktree.
3. Only then configure a **new** paper experiment and run discovery with
   `--source profiles`, followed by strict `screen`.
4. If fewer than 2 vetted wallets remain, optionally use **explicit**
   `observe --exploratory` for an engineering test, not an alpha claim.
5. If no fills occur again, inspect reason-coded `skips`, token quote
   availability and DEX liquidity. Do NOT relax the liquidity guard in an
   attempt to force activity.

For a new isolated working directory, point the Helius quota reader to the
old existing cap file *only while no other observer is using it*:

```bash
export YATL_SML_HELIUS_BUDGET_FILE=/home/ubuntu/yatl-smart-money/data/smart_money/helius_budget.json
```

The budget file lock is **thread-only**, NOT safe for concurrent processes.
Do not run screening/discovery/observation concurrently on multiple checkouts.

**Cost:** no new subscription or hosting required. Extra price fallback HTTP
calls go to the third-party DEX Screener public API, not Helius. DEX indicative
prices still do not prove achievable execution price, price depth, or alpha.

Primary references:
- Helius Enhanced Transactions (aggregate swap input/output; possible
  multi-hop route entries) https://docs.rs/helius/latest/helius/types/enhanced_transaction_types/struct.SwapEvent.html
- DEX Screener token-pairs and batch token pricing
  https://docs.dexscreener.com/api/reference
- Official Solana stablecoin mainnet mint IDs
  https://solana.com/docs/payments/how-payments-work
