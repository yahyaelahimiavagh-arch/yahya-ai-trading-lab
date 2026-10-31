"""Offline, self-contained HTML summary of a paper-only experiment."""
from __future__ import annotations

from decimal import Decimal
from html import escape
from pathlib import Path


def html_report(report: dict) -> str:
    if report.get("kind") != "YATL_SMART_MONEY_PAPER_ONLY":
        raise ValueError("not a YATL paper snapshot")

    def safe(value):
        return escape(str(value), quote=True)

    rows = []
    for p in sorted(report.get("portfolios", []), key=lambda x: x["id"]):
        equity = p.get("equity_usd")
        if equity is None:
            pnl, equity_text, cls = "Unknown — unpriced assets", "Unknown", "unknown"
        else:
            net = Decimal(str(equity)) - Decimal("1000")
            pnl = f"{net:+,.2f} USD"
            equity_text = f"{Decimal(str(equity)):,.2f} USD"
            cls = "pos" if net >= 0 else "neg"
        rows.append(
            "<tr>"
            f"<td>{safe(p['id'])}</td><td>{safe(p['cash_usd'])} USD</td>"
            f"<td>{safe(equity_text)}</td><td class='{cls}'>{safe(pnl)}</td>"
            f"<td>{len(p.get('fills', []))}</td>"
            f"<td>{len(p.get('open_positions', []))}</td>"
            f"<td>{'HALTED' if p.get('halted') else 'Paper'}</td></tr>"
        )
    hours = int(report.get("elapsed_seconds", 0)) // 3600
    unique = int(report.get("unique_signals_seen", 0))
    polls = int(report.get("polls", 0))
    quality = "DATA GAPS / INCOMPLETE" if report.get("feed_complete") is False else "Not independently audited"
    skips = safe(report.get("skips", {}))
    mode = report.get("selection_mode", "qualified")
    if mode not in ("qualified", "exploratory_unvetted"):
        raise ValueError("unknown selection mode in report")
    cohort_banner = ("""<div class="warning"><strong>UNVETTED EXPLORATORY COHORT</strong>
<p>No wallet satisfied complete smart-money qualification. The BLIND and SMART
labels are provisional activity/liquidity watchlists, NOT evidence of skill.
No historical profitability claim is supported. Treat this as an
observation/technical feasibility study only.</p></div>"""
                     if mode == "exploratory_unvetted" else "")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>YATL Smart Money Paper Dashboard</title>
<style>
body{{background:#101419;color:#e8eaf0;font:15px system-ui;margin:0;padding:30px}}
main{{max-width:1150px;margin:auto}}
h1{{font-size:32px;margin-bottom:5px}} h2{{font-size:18px;margin-top:30px}}
p,small{{color:#a7adb4;line-height:1.6}}
.flag{{color:#ead29a;border:1px solid #9e8346;padding:8px 12px;border-radius:30px}}
.top{{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px}}
.metrics{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin:30px 0}}
.metric{{padding:18px;background:#1c2229;border-radius:12px}}
.metric strong{{font-size:24px;display:block;margin-top:7px}}
.scroll{{overflow:auto;border:1px solid #313c49;border-radius:12px}}
table{{border-collapse:collapse;width:100%;min-width:700px;background:#1c2229}}
td,th{{padding:13px;text-align:left;border-bottom:1px solid #303943;white-space:nowrap}}
th{{color:#d6c391}}.pos{{color:#8ed8b6}}.neg{{color:#f4a7a7}}.unknown{{color:#f3cd8d}}
.warning{{border-left:3px solid #d2b36e;padding:9px 18px;background:#1c2229;margin-top:20px}}
</style></head><body><main>
<div class="top"><div><small>YAHYA AI TRADING LAB / EXPERIMENT</small>
<h1>Smart Money Lab</h1></div><span class="flag">PAPER ONLY / ZERO REAL FUNDS</span></div>
{cohort_banner}
<p>Three strategies, three execution-delay arms per strategy.
All USD profits are modeled, not independently executable.</p>
<div class="metrics">
<div class="metric"><small>Virtual starting capital/account</small><strong>1,000 USD</strong></div>
<div class="metric"><small>Elapsed</small><strong>{hours} hours</strong></div>
<div class="metric"><small>Unique swap signals observed</small><strong>{unique}</strong></div>
<div class="metric"><small>Provider data quality</small><strong style="font-size:17px">{safe(quality)}</strong></div>
</div>
<h2>Nine independent paper portfolios</h2>
<div class="scroll"><table><thead><tr><th>Method</th><th>Cash</th><th>Equity</th>
<th>P/L</th><th>Fills</th><th>Open lots</th><th>State</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div>
<h2>Data diagnostics</h2>
<p>Completed wallet polls: {polls}. Pending fills: {int(report.get("pending", 0))}.
Error / skip counters: {skips}.</p>
<div class="warning"><strong>Evidence boundary</strong><p>Unknown quotes are never treated
as profits. DEX indicative prices and an illustrative cost model are NOT executable
trade quotes. A 24-hour result alone cannot establish a repeatable trading edge.
If the feed has gaps, the result is incomplete.</p></div>
<small>This static report loads no scripts, trackers, remote assets or account data.</small>
</main></body></html>"""


def save_html(report: dict, output: Path):
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = output.with_suffix(output.suffix + ".tmp")
    staging.write_text(html_report(report), encoding="utf-8")
    staging.replace(output)
