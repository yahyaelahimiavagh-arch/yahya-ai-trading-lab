# YATL — Forward Paper Copy of Six Current-Market Wallets

**Status: code and offline tests READY; NOT started on the user's VPS. All funds fictitious. No live broker, transaction signing or blockchain order submission interface exists.**

The user decided to stop the losing V2 *paper* experiment and use selected wallets from November 1, 2026 for actual **forward paper signal following**, not more historical screening.

## New six-wallet cohort

The frozen, explicitly non-verified list is at:

`research/smart_money_lab/data/selected_forward_paper_wallets_20261101.json`

The six public Solana candidates are:

- `AgmLJBMDCqWynYnQiPCuj9ewsNNsBJXyzoUhD9LJzN51`
- `FHpcNSe6tb2n15bAdq4BkeYWGyZKFD7yLYrH92ng7wCT`
- `BXEHNbKPGeUHaqpaiHR6hc9mQkTZ2WFCXh6kkHkhFnCY`
- `7KyEvScKGoBPdroVYAy6v47XWjuuQFtPLjpWgZgMWEi`
- `SHARKdrwEJCe5hLNNLMNkkxn7aV8sTnURUV4TWtNUZS`
- `Jd97uyw9wb6PxV2jawAjS7aU6XUMHbcfn4En8xRP7Mg`

These six were selected for a mix of observable activity, partial historic entry/exit matching and hold times, NOT for proven profit. The two most active candidates had negative sampled gross spread. All samples remain severely incomplete. Selection is frozen and must not be tuned after new results are observed.

## What runs

`research/smart_money_lab/paper_copy_next.py` implements ONE fixed-notional, paper-only portfolio:

- Starting virtual cash $1000, max $30 per paper buy;
- Max six concurrently open paper positions; up to $180 initial modeled exposure;
- Poll each of six selected wallets every 300 seconds, for up to six hours;
- Read *new on-chain observations* via existing Helius Enhanced transaction API;
- Never backfill pre-start transactions into the follower;
- No paper-buy when a newer source sell has already occurred in the observed batch;
- No source signal older than 300 seconds; skip malformed/ambiguous source swaps;
- Quotes come from DexScreener's public **indicative** token prices; liquidity at least $20k and quote age under 30 seconds required by the paper engine;
- BUY $30 or less in the virtual portfolio; **first source SELL closes its entire matching virtual position**, not proportional execution;
- Model fixed 20bps fee and 50bps base slippage plus a notional/liquidity term (assumptions, not observed execution costs);
- Unknown paper position valuation locks **future paper BUYs**. The prior V2 problem allowing buys on `equity=None` is guarded;
- 5% modeled peak drawdown triggers a risk halt and attempts modeled liquidations where quote evidence is present. It is NOT an actual maximum loss guarantee;
- Status, fills, paper cash, paper equity, modeled realized PnL by source wallet and rejection reasons saved after every cycle.

**The program deliberately has no sendTransaction or real order API.**
Observation may still cost Helius quota, but uses the same existing persisted limit.

## API budget and cost

The six-hour, five-minute polling setup expects **432 Helius Enhanced request attempts** and requires **531** remaining out of the previous cumulative 5,000-call software cap as a conservative buffer. The exact provider billing credits may differ from call count; no purchase is suggested. For an optional three-hour trial, set `YATL_PAPER_HOURS=3` and the preflight will recompute the minimum.

**NEVER delete or reset `helius_budget.json`, start two observers with the same file, or bypass the guard by cloning a new quota file.**

## VPS — safe cutover

We cannot access the user's VPS directly; they run these commands **on the VPS**.

```bash
cd ~
git clone --depth 1 --branch research/sml-paper-copy-selected-wallets --single-branch \
  https://github.com/yahyaelahimiavagh-arch/yahya-ai-trading-lab.git \
  ~/yatl-paper-copy-selected

cd ~/yatl-paper-copy-selected
bash scripts/sml_paper_copy_cutover.sh preflight
```

The PRE-FLIGHT step does NOT change the V2 process and does not use API credits; it reads the EXISTING cumulative budget and verifies the cohort.

Once the preflight passes and **the existing `HELIUS_API_KEY` is already exported in the current VPS shell**, run:

```bash
bash scripts/sml_paper_copy_cutover.sh switch
```

The script:
1. Archives V2 report/state/budget in a new timestamped local folder.
2. Attempts a Ctrl+C on the known `yatl-sml-v2` tmux session, **without stopping the separate Hostinger publisher**.
3. Refuses to start the new paper process if any V2 observe process is still active.
4. Launches the new paper observer using `nohup`, inheriting the already present VPS Helius secret only as an environment variable, without printing or writing it to script/CLI.
5. Saves private state and reports under `~/yatl-paper-copy-forward-20261101`.

If the key is not already loaded in the shell, the script exits **before stopping V2**. Use the SAME secured environment-loading method previously used for V2, not a secret copied into ChatGPT. Never email/chat your token.

Status and controls:

```bash
tail -f ~/yatl-paper-copy-forward-20261101/console.log
python3 -m json.tool ~/yatl-paper-copy-forward-20261101/paper_copy_report.json | head -n 85
# Only when you want to stop the new paper process:
kill -TERM "$(cat ~/yatl-paper-copy-forward-20261101/paper_copy.pid)"
```

The old Hostinger dashboard may continue showing *archived V2*, not this new paper follower. Do not misrepresent it as a live V3 dashboard.

## Known limitations

- This is a forward LIVE-OBSERVED *PAPER* follower, not real-copy trading.
- Simulated fills at indicative last-price and simplified fees are NOT actual executable route quotes, and no latency-to-inclusion or MEV is measured.
- One Helius failure, missing quote, budget shortage or history gap can halt the run. Do not override these safety gates merely to get more fills.
- Some candidate wallets might no longer actively trade in the six-hour window; a zero-signal report is real information, not a reason to invent trades.
- User has NOT authorized real-money transaction submission and the project has no secure execution path for that.
- This code is a separate research branch; do not merge into V2 or replace its original data.
