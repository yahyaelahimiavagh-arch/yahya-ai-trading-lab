# External open-source design references

Snapshot date: **2026-09-13 UTC**

Purpose: preserve auditable design provenance for future YATL phases. These
repositories are references only. YATL does not copy their code, vendor their files,
or add them as dependencies. Their phase order does not replace the authoritative
`MASTER-PLAN.md` sequence.

| Project | Official repository | Reference commit | License | Recorded design input |
|---|---|---|---|---|
| NautilusTrader | `nautechsystems/nautilus_trader` | `99eb14bf836ae6d83a8f4198002d37afa910d7ab` | LGPL-3.0 | Execution reconciliation, startup recovery, authoritative-state comparison, deduplication and refusal to start on unresolved reconciliation. Adapt concepts only to YATL's local Paper journal; no venue execution is introduced. |
| Jesse | `jesse-ai/jesse` | `60f882e88c2d28e0f8cbc7f916758434e6ab7ce6` | MIT | Seeded trade-order/candle Monte Carlo and stationary-bootstrap Rule Significance Testing. Candidate input for later P3/P10 validation, not P5 execution. |
| Freqtrade | `freqtrade/freqtrade` | `c064be5325ad6941a2789add795434e6a13dffe9` | GPL-3.0 | Baseline-versus-sliced lookahead analysis and multiple-warm-up recursive indicator analysis, including coverage and false-result caveats. Candidate P3/P10 gates only. |
| Hummingbot | `hummingbot/hummingbot` | `2bfaccc48dd49e71a5b6d9b3011808e127dd00cd` | Apache-2.0 | Explicit Paper connector separation, scriptable CLI, stable exit codes, stale-state health checks and keystore boundaries. P5 may use Paper/CLI concepts; no credential store is needed or permitted in local P5. |
| CCXT | `ccxt/ccxt` | `cefce5bc9e5c6b3d69d2645d8f992b9ae99ab311` | MIT | Possible future exchange-abstraction reference only. It is not approved as a dependency or adapter and creates no exception to YATL's order-endpoint prohibition. |

## Source files reviewed

- NautilusTrader: `LICENSE` and
  `docs/concepts/execution/reconciliation.md` at the recorded commit.
- Jesse: `LICENSE`, `jesse/research/monte_carlo/__init__.py`,
  `jesse/research/rule_significance_testing/__init__.py` and
  `jesse/research/rule_significance_testing/bootstrap.py`.
- Freqtrade: `LICENSE`, `docs/lookahead-analysis.md` and
  `docs/recursive-analysis.md`.
- Hummingbot: `LICENSE`, `README.md`, `hummingbot/cli/README.md`,
  `hummingbot/client/config/security.py` and
  `hummingbot/cli/commands/connect.py`.
- CCXT: `LICENSE.txt`, `README.md` and `package.json`.

## Non-adoption rule

- A recorded reference is not an approval to install, import, port or translate it.
- Any future dependency proposal requires a separate need, license and security
  review, pinned version, lockfile change and explicit checkpoint acceptance.
- GPL/LGPL material must not be copied into YATL merely because its behavior is a
  useful design reference.
- No reference may weaken: PAPER ONLY; `LIVE_MASTER_LOCK=OFF`; NO FUTURES; NO
  LEVERAGE; NO WITHDRAWAL API; NO TRADE PERMISSION; NO ORDER ENDPOINTS; NO AI
  DIRECT EXECUTION.
