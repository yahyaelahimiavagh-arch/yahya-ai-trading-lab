# YATL — Public Solana Wallet Candidate Discovery

**Implemented and run on public June 2026 data. Research only. No proof of profitable or copyable trading.**

## Source and process

The source is https://github.com/ian05012/solana-memecoin-dataset, pinned at upstream Git revision 7070d00e1e4492f8604d988549d91785cc5f43f7. The pipeline uses all four Parquet trade shards and the token snapshot file. Inputs are local; the tool makes **zero Helius/RPC, DEX, or live price requests**.

- Use the earliest snapshot of each token with liquidity of at least $20,000 and an available forward 24-hour token 2x classification.
- Match each wallet to buys of at least $10 within the 15 minutes before the snapshot. Collapse multiple buys to a single wallet/token observation.
- Freeze the first two-thirds of calendar time as training. Training labels must mature 24 hours before cutoff. The remaining period is the holdout.
- Require at least 10 separate token observations and activity on at least 3 days.
- Rank only on the training period: posterior token 2x hit rate shrunk toward the training token base rate with 20 pseudo-observations.
- Select the top 1% of training-qualified wallets, subject to a 100-address limit. Do not use later test data for rank selection.
- Group selected wallet patterns when their training-token sets have >=80% Jaccard overlap; this is a **similar behavior** indicator, not proof of shared owner.
- Present the number of independent holdout tokens, NOT only raw wallet-token observations. Explicitly label inactive wallets as insufficient evidence.
- Input file sizes and SHA-256 digests are captured in the result JSON.

## First real run (2026-11-01)

- 73,318 unique wallets linked to an earlier token buy
- 726,123 matched wallet/token observations
- 14,301 eligible distinct token snapshots
- 2,551 training-qualified wallets
- 26 top-1% training candidates (ceil(2,551 x 0.01))
- Only 3 distinct training behavior groups among the 26
- 23/26 exhibit at least 80% training-token overlap with a stronger group's anchor
- None of the 26 had five or more holdout wallet/token observations
- Training token baseline: 16.622% subsequently reached 2x
- Later holdout token baseline: 1.250% subsequently reached 2x

This is not evidence of 26 independent skilled traders. Underlying market conditions and event rates differ sharply between periods. The author notes the original live early-buy model was shelved because its live expected value was insufficient.

## Files generated

GitHub Actions workflow:
https://github.com/yahyaelahimiavagh-arch/yahya-ai-trading-lab/actions/workflows/sml-public-wallet-run.yml

Download the artifact named public-wallet-discovery-june-2026 from a successful run. It contains:

- public_wallet_candidates.json: source SHA-256 manifest, training cutoff, candidate ranks, behavior grouping, holdout metrics
- public_wallet_candidates.csv: public Solana wallet addresses and descriptive research metrics

## Optional reproduction without disturbing V2

An existing paid account or new API key is **not needed**. The workflow already produces the complete results, so another VPS run is optional. For independent reproduction:

1. Clone branch research/sml-public-wallet-discovery into a **new folder**, never reuse the live V2 checkout.
2. Create a Python environment and install free DuckDB 1.4.1 and pytz.
3. Download tokens.parquet and trades-000.parquet through trades-003.parquet from the upstream SHA above to a private local folder. Approx. 285MB, plus temporary disk space.
4. Run:

~~~bash
python -m research.smart_money_lab.public_wallet_discovery \
  --data-dir ~/yatl-public-june-data \
  --output-dir ~/yatl-public-wallet-results
~~~

The program does not restart V2, reset budgets, call Helius, or place orders.

## Methodological boundaries

The trade log records USD buy/sell amounts but lacks exact token quantities. It cannot establish FIFO cost basis or realized account PnL. The forward-2x label means a token's future price **peaked** at 2x; it is NOT an available exit quote, realized profit or copyable trade. June 2026's 20-day GMGN sample has selection and survivorship biases; past wallet IDs are not proof of current activity.

Selection/cutoff experiments already examined this historical dataset. Accordingly, the reported holdout is exploratory, not an untouched confirmatory test. Any claim of repeatable skill requires new independent dates, source-wallet inventory reconciliation, and time-stamped realizable follower quotes, without artificially relaxing safety or liquidity thresholds.
