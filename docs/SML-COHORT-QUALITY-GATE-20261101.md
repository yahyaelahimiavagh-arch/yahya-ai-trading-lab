# YATL — Offline Six-Wallet Selection Gate (2026-11-01)

**Decision: NO-GO for new six-hour paper pilot and all real-money copy trading.**

This is a reproducible, **ZERO-provider-request** review of the frozen exploratory
six-wallet sample. It does not modify the observer, Helius counter, Hostinger,
SSH keys, or wallets. It cannot recover missed transactions or infer realized PnL.

## Reproduction on existing VPS

```bash
cd ~/yatl-paper-copy-selected
git pull --ff-only origin research/sml-paper-copy-selected-wallets
python3 -m unittest discover -s tests -p 'test_sml_cohort_quality_gate.py' -v
python3 -m research.smart_money_lab.cohort_quality_gate
```

The script fails if the archived watchlist's Git blob SHA-1 changes. Wallet
indexes therefore refer only to the original ordered watchlist, never a new
cohort. Output contains no addresses, signatures, trading keys or executable
orders. No API key is required.

## Actual evidence

- Data from PR #193: a nonrandom **four-pool** GeckoTerminal newest-300 trade
  sample; **1,173** deduplicated trades, **547** maker addresses, ten provisional
  two-sided multi-token candidates. Source API hit HTTP 429 and stopped early.
- Data from PR #194: **177 FIFO matching fragments**, not 177 independent
  closed trades; incomplete starting inventory, incomplete costs and sparse
  as-of prices. Of 177, only **61** had both delayed 117-second print-proxy
  observations no more than 30 seconds old. Conditional historical median gross
  print proxy +0.0872%; after *hypothetical*, not measured, 150bps round-trip
  friction median -1.4029%. Not a live return estimate.
- Original one-shot paper run and 3-page run both failed closed with
  `halted_history_gap` after one complete cycle. No simulated fills.
- The later 11-request probe found: Wallet 1 `page_cap`; Wallet 2
  `repeated_signature`; Wallet 3 overlap on three pages; Wallets 4–6 overlap
  in one page. These results describe the **later probe**, not the precise
  historical mechanism of the original failure.
- Frozen fragment counts for Wallets 1–6: 11, 7, 3, 2, 1, 1. They are *not*
  independent closed, profitable trades. Wallet 1/2 had negative partial
  sampled gross spread and 3/0 117s-delayed as-of print pairs, respectively.

## Qualification gate

Every wallet is NO-GO for trading or a six-hour profitability pilot because:

1. Full wallet buy/sell history, opening balances and known cost basis are not
   verified, so source realized **net** PnL cannot be measured.
2. There are no independent, fee-inclusive, prospectively recorded follower
   executable entry/exit quotes.
3. The selection is biased to four recently trending pools, and the current
   samples are too small to estimate repeatable skill.
4. The source's high-volume history feasibility is unproven over multiple
   forward periods; one point-in-time successful overlap does not prove a
   complete long-running observer.

For future research, *prospectively* demand complete histories, many
independent closed position outcomes across several weeks and markets,
point-in-time source eligibility, independently executable route quotes,
realistic all-in costs, and OOS results. A preliminary 30-fragment threshold
used by the offline script is solely an **insufficiency warning**, never a
statistical significance test or a path to automatic promotion.

## Data acquisition alternatives — no purchase now

| Choice | Merits | Limitations / decision |
| --- | --- | --- |
| Repeated Enhanced transaction-history polling | Already implemented | Heavy wallets hit pagination cap; failed twice; do not extend this experiment |
| Standard Solana `getSignaturesForAddress` plus targeted `getTransaction` | Can checkpoint signature sequence, benchmark missed signatures and per-wallet volume; standard RPC is available through existing Helius access | Additional transaction-decoding calls may cost more; signature histories alone do not say BUY/SELL; prove continuity and compare capped request/credit usage before adopting |
| WebSocket subscription + signature checkpoint/backfill | Event-driven capture may reduce polling latency | Reconnect, dropped connections, log filters, and full state recovery complicate completeness; can still require RPC. Research-only later |
| Helius Parsed Events/Parsed Streams or `getTransactionsForAddress` | May simplify future parsing/backfill | At research date new parsed products require paid tier / beta; `getTransactionsForAddress` had been advertised as paid-plan, 100-credit method. NOT justified until measurable signal economics |

Official references:
- https://solana.com/docs/rpc/http/getsignaturesforaddress
- https://solana.com/docs/rpc/http/gettransaction
- https://www.helius.dev/pricing
- https://www.helius.dev/blog/introducing-gettransactionsforaddress
- https://www.helius.dev/blog/parsed-events-and-streams

## Next actual experiment

First run the **offline quality gate**; do not restart paper trading.
Then, if warranted, write a small isolated **read-only signature-continuity**
prototype that performs a *pre-approved* capped comparison of baseline calls
versus signatures, never order execution. Avoid mixing method or selection
changes into a historical paper run. Keep rejected experiments immutable.

## Data preservation

PR #193 original GitHub Actions artifact (run `41294005096`) exists as
`sml-current-solana-dex-wallets`, artifact ID `13078742064`,
and is set to expire on **2026-11-15 09:39:16 UTC**. Its ZIP digest on the
2026-11-01 source retrieval was
`sha256:3db02ffeb5fcae8e2fc34c03f5092e03aaeb9b0328cd51bd86b9fdb9da8feeeb`.
Preserve the exact ZIP without altering it; checksum before reuse.
