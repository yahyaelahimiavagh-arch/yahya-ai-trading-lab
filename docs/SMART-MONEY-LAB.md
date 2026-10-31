# YATL Smart Money Lab — paper-only research track (V0.1)

**Isolation:** independent research package at \`research/smart_money_lab/\`. Existing P10 forward collector and P11 lock remain unchanged. This is not a live trade bot. There are no order, custody, signing, withdrawal, wallet private key, Jupiter swap, or brokerage endpoints in this module.

## What is implemented

1. **Candidate discovery:** a bounded, explicitly biased sample of recently promoted Solana token pools, using DEX Screener and Helius on-chain swap fee payers. These are *unverified candidates*, never assumed professional or profitable. If pools cannot be parsed, discovery may return zero. Supplement/replace the candidates file with known public Solana addresses.
2. **Historical qualification:** fetch 30–90 days of parsed swap records with an auditable pagination completeness flag. Approximate realized PnL by FIFO cost basis on simple USDC/SOL quotes; SOL-to-USD values use the **previous closed hour** SOL/USDT reference candle to avoid future data leakage. Incomplete history, unknown cost basis, low sample size, poor parse coverage, low *current* liquidity, and unavailable market data block eligibility. Scores are research heuristics, not audited professional classifications.
3. **Forward paper portfolios:** BLIND (historical profit ordering), SMART (liquidity/copyability proxy and performance ordering), and CONSENSUS (two independent eligible wallets trading the same mint/direction within 120 seconds). Every strategy is evaluated with 1, 3, and 10 seconds **additional time after observation**: 9 isolated USD 1,000 ledgers, not $9,000 of real money.
4. **Friction and guards:** up to $30 per paper buy, 6 open lots, at most $180 deployed per account, 20bps fee per side, 50bps base adverse slippage plus illustrative notional/liquidity impact, no leverage. Mark-to-market risk stop on 5% observed drawdown; paper liquidation uses another adverse execution penalty, so the realized loss may exceed 5% on gaps/stale quotes.
5. **Evidence:** unique on-chain signature, separate chain/observation/fill timing, missing-price blocking, 15-second crash snapshots, no pre-start trades, and null equity when open positions are unpriced. No claim of actual exchange execution or attainable PnL.

## Prerequisites

- Python 3.12 / existing YATL \`uv\` environment. No extra pip dependencies.
- A **Helius API key** in an environment variable, never in source, \`.env\`, PRs or chat logs. Helius has a free tier at time of writing; check limits before running.
- Network access to Helius, DEX Screener and Binance public market data APIs. Providers may fail, throttle or change schema. No credentials or payment is needed for DEX Screener public pricing.
- A Linux/Windows host that remains online for 24 hours. **No host deployment is performed by this PR.**

## Steps

Run from repo root:

\`\`\`sh
uv sync --locked
export HELIUS_API_KEY="YOUR_KEY_SET_LOCALLY"  # Linux; use $env:HELIUS_API_KEY=... on PowerShell

uv run --locked python -m research.smart_money_lab discover \
  --output data/smart_money/candidates.json --max-pools 5

# Edit candidates.json to add/remove public wallet addresses, if desired.
uv run --locked python -m research.smart_money_lab screen \
  --candidates data/smart_money/candidates.json \
  --output data/smart_money/screened.json --days 30 --max-pages 20

# Observe ONLY when 2+ wallets have passed the automated gates.
uv run --locked python -m research.smart_money_lab observe \
  --screened data/smart_money/screened.json --hours 24 \
  --state data/smart_money/state.json --report data/smart_money/report.json
\`\`\`

The 24-hour observer writes `data/smart_money/report.json`, `state.json` and a static `data/smart_money/dashboard.html` every ~15 seconds. Open the HTML dashboard locally; it uses no external scripts or trackers.

To resume an interrupted window **using the saved snapshot**:

\`\`\`sh
uv run --locked python -m research.smart_money_lab observe --resume \
  --screened data/smart_money/screened.json \
  --state data/smart_money/state.json --report data/smart_money/report.json
\`\`\`

Report the persisted snapshot at any time:

\`\`\`sh
uv run --locked python -m research.smart_money_lab report --state data/smart_money/state.json \
  --html data/smart_money/dashboard.html
\`\`\`

Focused offline deterministic suite:

\`\`\`sh
uv run --locked python -m unittest discover -s tests -p 'test_smart_money_lab.py' -v
\`\`\`

## Interpretation and limitations — essential

- **24h is a plumbing and exploratory smoke test, not proof of edge.** Advance only after multiple market regimes, at least 200 independent observations, out-of-sample forward validation, and stable positive net PnL. These thresholds are hypotheses, not guarantees.
- **DEX Screener market prices are indicative** and its liquidity is not a live executable swap route. This MVP cannot reproduce actual fills, network prioritization fees, token transfer restrictions, MEV, priority tips, rug-pulls, or price impact curves exactly. A later version needs observed executable Jupiter quotes and more conservative missing-fill handling.
- The 1/3/10-second variations are **delays after our first observation**, not assured latency from the trader's blockchain execution. Polling and API request time are additional and shown in \`signal_to_fill_seconds\`. A synchronous polling loop can make observed delays converge when requests are slow. Do not use latency-arm comparisons to infer real execution superiority before an asynchronous feed is implemented.
- Swaps outside simple one-input/one-output USDC/SOL patterns are skipped. Historical scores can be biased by skipped complex swaps, wallet transfers, multiple token accounts, pump trades, missing older cost basis and survivorship bias. Price conversions for SOL history use the previous hour reference candle and are estimates, not transaction-exact accounting.
- Recent promoted tokens are a **sampling mechanism**, not neutral market discovery; paid visibility biases the wallet universe. No statistically representative universal trader discovery is claimed.
- A SELL by a selected trader **fully exits** our associated paper lot, even if that trader sells partially. This is an explicit experimental exit policy, not exact proportional mirroring.
- 5% drawdown stop is only detected on fresh indicative marks. Lack of prices means no reliable mark or enforcement. Capital is never deposited; this is **not** a capital-protection guarantee.
- \`data/\` is gitignored. Snapshot recovery is best effort and may lose up to 15 seconds of updates on an abrupt failure. Resume may not be suitable if the data feed has a multi-minute outage; flag and start a new evidence window rather than pretending continuous monitoring.
- Never set broker private keys. No live-order code is installed; keep \`LIVE_MASTER_LOCK=OFF\` in the parent YATL system.
- If screening returns fewer than two eligible wallets, the observer refuses to start rather than fabricate a winner. More expensive data providers should not be purchased merely to bypass qualification.

## Deployment / next improvements

This PR **does not deploy to the VPS**, because authenticated host access and a user-provisioned Helius key are needed. Before a credible 24h experiment:
1. Verify API health and credit use with a small read-only sampling run.
2. Improve the observer into independent asynchronous transaction acquisition and scheduled quote sampling, plus monitor missing-transaction gaps (current synchronous implementation is exploratory).
3. Capture actual executable route quotes and quote failure rates for each delay.
4. Freeze wallet selection before the start; don't tune thresholds based on the forward results.
5. Only then run a continuously supervised 24h trial with periodic retained snapshots and independent data-quality alerts.

Sources: [Helius enhanced transaction history](https://github.com/helius-labs/core-ai/blob/main/helius-plugin/skills/build/references/enhanced-transactions.md), [DEX Screener official API reference](https://docs.dexscreener.com/api/reference), [Helius pricing](https://www.helius.dev/pricing).


## Free-tier 24h pilot settings — 2026-10-31

This first run deliberately prioritizes a completed observation over low latency:

- **One existing free Helius key; no subscription.** Enhanced-history calls cost about 110 credits/call per published Helius reference. Our code reserves one persistent request in `data/smart_money/helius_budget.json` before each Helius history request, and refuses requests after **5,000 calls**. This is a **conservative approximate** ~550,000 credits, *not* provider-reported actual credit usage; verify remaining credits on the dashboard. It does not automatically reset. Do not delete the budget file to evade the stop.
- **At most 4 blind + 4 smart wallets**, i.e. 8 different wallets maximum. The observer uses 180 seconds between polling cycles, rather than 30. Theoretical regular polls: at most `8 × (24 × 3600 / 180) = 3,840` calls, before screening, discovery, network retries, or any unrelated Helius usage. Actual credits can differ. Stop and audit if the free account approaches its quota.
- **Up to 5,000 requests across every phase and restart** on one host. Do not run discovery/screen/observe simultaneously; this budget file is a **single-process** lock and is not multi-process safe.
- **300-second maximum signal age** and 300-second consensus window are exploratory concessions to coarse polling. Because the leader's trade may precede detection by minutes, this test cannot verify the effectiveness of 1s/3s/10s live copy trading. All simulated delays are counted after signal observation; the report also preserves chain-to-fill seconds.
- If the screening criteria select fewer than 2 eligible wallets, the experiment will **refuse to trade in paper mode**. This is a valid screening outcome, not a reason to invent traders, override filters or consume paid API credits.
- If requests exhaust the cap, monitoring stops with partial snapshots and marks data coverage as incomplete. No manual deposit, real wallet or trading API is used.

The basic chronological procedure is `discover` → `screen` → confirm `eligible >= 2` → `observe` for 24h. All data is paper-only, and VPS deployment needs separate authorized host access and a securely stored API key. If `data/smart_money/state.json` already exists from a previous run, use `--resume` only to continue the **same** window, otherwise archive old output and start a new window.
