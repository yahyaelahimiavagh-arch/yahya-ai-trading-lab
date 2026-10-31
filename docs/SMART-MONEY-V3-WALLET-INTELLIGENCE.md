# YATL V3 — Wallet Intelligence / Independent Research Foundation

**Status:** V3 offline evidence-audit foundation, NOT an automated trading system,
NOT a proven wallet-scoring system, and NOT a live replacement for V2.

Branch: `research/smart-money-wallet-intelligence-v3`

## Why

The V2 paper pilot has 6 **unvetted** observed wallets, BLIND/SMART overlap,
three nearly identical 1s/3s/10s portfolios, and a measured median
chain-to-paper-fill latency of approximately **134 seconds**. Six BLIND/SMART
portfolios stopped after a modeled 5% peak drawdown. Those are important
technical findings but **not evidence that profitable copy trading exists**.

The remaining hypothesis is that *historically profitable wallets with
point-in-time verified, actually copyable opportunities* may perform differently.

V2's `screened.json` provides aggregate closed trade counts, current liquidity
proxies, and historical realized PnL approximations. It does **not** store a
frozen training cutoff per wallet or complete timestamped historical executable
quote/position history. No new intelligence layer should fill these gaps
with a backfilled present-day DexScreener quote.

## What V3 has today

`research.smart_money_lab.wallet_intelligence` (stdlib-only, offline):

1. **Strict training candidate gate**: complete history, >=50 closed historical
   trades, >=15 days activity, no unmatched cost-basis sells, >=80% parsed swaps,
   >=$20k token liquidity proxy, positive realized training PnL and explicit
   selection time. It requires BOTH `screened_at` and `history_end_at` no
   later than the frozen `--cutoff`. Existing V2 snapshots missing these
   fields are rejected. A candidate is *not* certified profitable.

2. **Nonoverlapping prototype research arms**: if >=4 eligible training candidates
   exist, create deterministic disjoint SMART and baseline candidate arms in
   memory. SMART is training-PnL-ranked; baseline is deterministic hash order
   from remaining candidates. The design **does not claim randomization, balance
   or causal validity**, and does not export raw wallet addresses.

3. **Read-only V2 baseline audit**: counts overlap between V2 BLIND and SMART;
   distinguishes 9 repeated account fills from unique underlying signals;
   reports median observed fill delay, redundant 1/3/10-second outcomes, and
   risk exits, never publishing wallet IDs or full transaction IDs.

4. **Held-out as-of quote evidence check**: optional user-supplied, genuinely
   recorded `live_observed` events and `live_recorded` quote snapshots.
   With a frozen cutoff, decision time is
   `max(event.observed_at, event.chain_time + 134s)`. Quotes captured **after**
   the decision are NEVER used; only an earlier quote <=30s old, token liquidity
   >=$20,000, and event age <=300s count as *indicative quote coverage*.
   Still **no executable order quote, no simulated PnL and no alpha claim**.
   Provenance labels are data assertions, not cryptographic proof.

5. **No Helius/DEX/market-data requests**. Neither branch checkout nor the
   CLI imports the provider or starts a polling thread.

## Run offline without disrupting V2

The V2 process (`yatl-sml-v2`), Hostinger publisher
(`yatl-sml-hostinger`), and V1 snapshot/Helius budget must remain unchanged.

```bash
cd ~
git clone --depth 1 --branch research/smart-money-wallet-intelligence-v3 \
  --single-branch \
  https://github.com/yahyaelahimiavagh-arch/yahya-ai-trading-lab.git \
  ~/yatl-wallet-intelligence-v3

cd ~/yatl-wallet-intelligence-v3
python3 -m unittest discover -s tests \
  -p 'test_smart_money_wallet_intelligence.py' -v

python3 -m research.smart_money_lab.wallet_intelligence \
  --screened /home/ubuntu/yatl-smart-money-v2/data/smart_money/screened.json \
  --report /home/ubuntu/yatl-smart-money-v2/data/smart_money/report.json \
  --output /home/ubuntu/yatl-wallet-intelligence-v3/v3_read_only_audit.json

python3 - <<'PY'
import json
from pathlib import Path
report = json.loads(Path("v3_read_only_audit.json").read_text())
print(json.dumps(report, indent=2, ensure_ascii=False))
PY
```

The results only contain aggregate counts. If `screened_at` and
`history_end_at` are unavailable, zero fully qualified V3 training candidates
is an **honest data-quality gate**, not a bug.

**No extra purchase, service, subscription, or hosting required.**

## Optional timestamped forward evidence format

Events JSON array (never export the raw event file to Hostinger):

```json
[
  {
    "source":"live_observed",
    "wallet":"<solana-wallet>",
    "mint":"<token-mint>",
    "signature":"<transaction-signature>",
    "side":"BUY",
    "chain_time":1800000000,
    "observed_at":1800000134
  }
]
```

Quotes JSON array, captured live at the time rather than backfilled:

```json
[
  {
    "source":"live_recorded",
    "mint":"<token-mint>",
    "captured_at":1800000134,
    "price_usd":"0.0421",
    "liquidity_usd":"85000"
  }
]
```

Example only; addresses and values above are placeholders, not discovered
wallets or actual market prices. A separate future collector must record the
data prospectively. No collector has been enabled by this V3 PR.

Then add `--cutoff <unix-timestamp> --events path --quotes path` to
the CLI invocation. Without a fixed cutoff and genuine historical as-of
snapshots the tool deliberately refuses any profitability inference.

## V3.1 prospective evidence journal (implemented in DRAFT; not deployed)

The **opt-in** `--evidence-journal /absolute/private/evidence.jsonl` switch
has been added to the experimental `observe` command on **this isolated V3
branch only**. Its default is OFF; it does not change active V2.

When eventually enabled in an independent, explicitly approved **future paper**
observer, this switch records:

- Forward parsed Helius SWAP receipts already delivered by that observer:
  wallet, token, transaction signature, on-chain timestamp, receipt timestamp
  and BUY/SELL. Historical and previously seen signatures are not re-recorded.
- Indicative DexScreener quotes **already fetched** by that observer: token,
  observed USD price, liquidity, and local receipt timestamp.
- The stream as a bounded, 0600-permission, append-only JSONL journal with an
  ordinal SHA-256 hash chain. Incomplete records, changed hashes, weak file
  permissions, or symlinks are rejected on re-open.

This feature never initiates an **additional** Helius or DexScreener request.
**However, launching an observer itself WOULD make the same API requests as V2.
Do not start it while V2 is active or share/reset its Helius budget.**

Do not put the raw journal under `public_html`, in the Git repository, or in
Hostinger exports. It contains actual wallet and transaction identifiers.
The audit command returns only redacted aggregate statistics.

Once a separately authorized future paper run has generated prospective
records, the entirely **offline** audit command will be:

```bash
python3 -m research.smart_money_lab.prospective_evidence \
  --journal /absolute/private/evidence.jsonl --cutoff YOUR_FROZEN_UNIX_CUTOFF
```

Do not execute this command unless the journal exists. It never backfills
missing quotes or pretends the V2 existing state/report is a valid journal.

**Provenance limitations:** a local hash chain is tamper-evident but not a
trusted external timestamp or independent source attestation; DexScreener
snapshots do not guarantee executable DEX quotes or MEV/slippage behavior;
reference latency 134 seconds is a V2 indicative historical benchmark, not
a verified network reaction time. The auditor computes quote coverage, NOT
realized PnL or proof of alpha.

## V3.2 and beyond (not implemented)

- Freeze training cutoff and wallet-selection evidence **before** any held-out
  data are inspected; never retrospectively fill missing V2 fields.
- Establish matched or randomized disjoint control cohorts; publish selection
  strata, wallet exclusivity, and bias/coverage attrition.
- Validate chain-to-observation latency against all incoming eligible signals,
  not only those with paper fills; current V2 unique-fill median is 117 seconds,
  while the older all-ledger-fill median was 134 seconds.
- Replay held-out buy/sell pairs with full cost basis, asymmetric latency,
  observed liquidity/price age, route-specific costs and pessimistic missing data.
  Mid-market values must never be called executable fills.
- Require independently reviewed forward paper performance and sustainable free
  request budget before considering any later trial. Never enable live orders.

## Operational/financial guardrails

- Do not `git pull` in the running V2 process checkout while it is active.
- Do not read/save/print the Helius key; do not reset its 5,000-request cap.
- No new API polls, no wallets to be signed, no third-party uploads.
- V3 output JSON is intentionally aggregate only; keep raw input files private.
- A result that says **blocked** is the correct outcome when evidence is absent.
