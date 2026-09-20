"""Deterministic self-contained P8-007 local dashboard renderer."""

import hashlib
import html as html_lib
import json
from dataclasses import dataclass
from html.parser import HTMLParser

from .contracts import DashboardSafetyBanner
from .overview import DashboardOverviewProjection
from .performance_views import PerformanceSegmentationProjection
from .quality_view import QualityDiagnosticProjection
from .trade_table import CompletedTradeTableProjection


RENDERER_SCHEMA_VERSION = 1
MAX_DASHBOARD_BYTES = 4 * 1024 * 1024
_HEX = frozenset("0123456789abcdef")

_CSS = """:root{color-scheme:dark;--bg:#09111f;--panel:#111b2e;--line:#26354f;--text:#eef3fb;--muted:#aebbd0;--accent:#d4af37;--good:#9ad6b3;--bad:#ffb1b1}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;line-height:1.45}
main{max-width:1240px;margin:0 auto;padding:24px}
h1,h2{margin:0 0 12px}
h1{font-size:28px}
h2{font-size:18px;color:var(--accent)}
p{margin:6px 0}
.banner{display:flex;flex-wrap:wrap;gap:8px;margin:16px 0}
.badge{border:1px solid var(--line);border-radius:999px;padding:6px 10px;background:var(--panel);font-size:12px;font-weight:700}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px;margin:16px 0;overflow:auto}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:10px}
.card{border:1px solid var(--line);border-radius:10px;padding:12px;min-width:0}
.label{color:var(--muted);font-size:12px}
.value{overflow-wrap:anywhere;font-variant-numeric:tabular-nums}
table{width:100%;border-collapse:collapse;min-width:720px}
th,td{text-align:left;border-bottom:1px solid var(--line);padding:8px;vertical-align:top;overflow-wrap:anywhere}
th{color:var(--muted);font-size:12px}
.status-pass{color:var(--good);font-weight:800}
.status-blocked{color:var(--bad);font-weight:800}
code{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:12px;overflow-wrap:anywhere}
ul{margin:8px 0;padding-left:22px}
footer{color:var(--muted);font-size:12px;margin-top:20px}
"""

_FORBIDDEN_TAGS = frozenset(
    ("script", "img", "link", "iframe", "object", "embed", "audio", "video", "source")
)
_FORBIDDEN_ATTRS = frozenset(
    ("src", "href", "action", "formaction", "poster", "data", "srcset")
)


class DashboardRenderError(ValueError):
    """P8 renderer input or generated artifact violates the local-only boundary."""


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value):
    material = value if isinstance(value, str) else _json(value)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _valid_sha(value):
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in _HEX for character in value)
    )


def _e(value):
    if value is None:
        value = "UNAVAILABLE"
    elif isinstance(value, bool):
        value = "true" if value else "false"
    else:
        value = str(value)
    return html_lib.escape(value, quote=True)


class _SelfContainedParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.violation = None

    def handle_starttag(self, tag, attrs):
        lowered = tag.lower()
        if lowered in _FORBIDDEN_TAGS:
            self.violation = f"forbidden-tag:{lowered}"
            return
        for name, _ in attrs:
            if name.lower() in _FORBIDDEN_ATTRS:
                self.violation = f"forbidden-attr:{name.lower()}"
                return

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)


def _assert_self_contained(html):
    parser = _SelfContainedParser()
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        raise DashboardRenderError("Rendered dashboard HTML is invalid") from None
    if parser.violation is not None:
        raise DashboardRenderError("Rendered dashboard is not self-contained")
    css_lower = _CSS.lower()
    if "url(" in css_lower or "@import" in css_lower:
        raise DashboardRenderError("Renderer CSS contains remote-capable references")


def _row(cells):
    return "<tr>" + "".join(f"<td>{_e(value)}</td>" for value in cells) + "</tr>"


def _header(cells):
    return "<tr>" + "".join(f"<th>{_e(value)}</th>" for value in cells) + "</tr>"


def _table(headers, rows, empty_message):
    parts = ["<div class=\"panel\"><table><thead>", _header(headers), "</thead><tbody>"]
    if rows:
        parts.extend(_row(row) for row in rows)
    else:
        parts.append(
            f"<tr><td colspan=\"{len(headers)}\">{_e(empty_message)}</td></tr>"
        )
    parts.extend(("</tbody></table></div>",))
    return "".join(parts)


def _render_banner():
    banner = DashboardSafetyBanner()
    return (
        "<div class=\"banner\">"
        + "".join(
            f"<span class=\"badge\">{_e(value)}</span>"
            for value in (
                banner.paper_label,
                banner.live_lock_label,
                banner.evidence_label,
                banner.purpose_label,
                banner.readiness_label,
            )
        )
        + "</div>"
    )


def _render_quality(quality):
    blocked = quality.quality_status != "PASS"
    status_class = "status-blocked" if blocked else "status-pass"
    parts = [
        "<section>",
        "<h2>Quality Gate</h2>",
        "<div class=\"panel\">",
        f"<p class=\"{status_class}\">{_e(quality.quality_status)}</p>",
        f"<p>{_e(quality.status_message)}</p>",
        f"<p><span class=\"label\">Analytics presentation allowed:</span> {_e(quality.analytics_presentation_allowed)}</p>",
        f"<p><span class=\"label\">Source mode:</span> {_e(quality.source_mode)}</p>",
    ]
    if quality.source_quality_sha256 is not None:
        parts.append(
            f"<p><span class=\"label\">Quality SHA-256:</span> <code>{_e(quality.source_quality_sha256)}</code></p>"
        )
    if quality.passed_checks:
        parts.append("<p class=\"label\">Passed checks</p><ul>")
        parts.extend(f"<li>{_e(item)}</li>" for item in quality.passed_checks)
        parts.append("</ul>")
    if quality.diagnostics:
        parts.append("<p class=\"label\">Diagnostics</p><ul>")
        for item in quality.diagnostics:
            parts.append(
                "<li>"
                f"<strong>{_e(item.severity.value)}</strong> "
                f"<code>{_e(item.code)}</code> — {_e(item.message)}"
                "</li>"
            )
        parts.append("</ul>")
    parts.extend(("</div>", "</section>"))
    return "".join(parts)


def _render_overview(overview):
    cards = []
    for item in overview.cards:
        cards.append(
            "<div class=\"card\">"
            f"<div class=\"label\">{_e(item.label)}</div>"
            f"<div class=\"value\">{_e(item.value)}</div>"
            "</div>"
        )
    return (
        "<section><h2>System / Safety / Quality Overview</h2>"
        "<div class=\"panel\"><div class=\"grid\">"
        + "".join(cards)
        + "</div></div></section>"
    )


def _render_metrics(performance):
    rows = tuple(
        (
            item.metric_id,
            item.value,
            item.unit.value,
            item.state.value,
        )
        for item in performance.metrics
    )
    return (
        "<section><h2>Performance Metrics</h2>"
        + _table(
            ("Metric", "Value", "Unit", "State"),
            rows,
            "No performance metrics.",
        )
        + "</section>"
    )


def _render_trades(trades):
    rows = tuple(
        (
            item.row_id,
            item.trade_index,
            item.symbol,
            item.outcome,
            item.net_pnl,
            item.gross_return,
            item.net_return,
            item.fee_total,
            item.slippage_total,
            item.holding_time_ms,
            item.status,
        )
        for item in trades.rows
    )
    return (
        "<section><h2>Completed Trades</h2>"
        f"<p class=\"label\">Showing {_e(trades.returned_count)} of {_e(trades.total_filtered)} filtered completed trades.</p>"
        + _table(
            (
                "Row",
                "Index",
                "Symbol",
                "Outcome",
                "Net PnL",
                "Gross Return",
                "Net Return",
                "Fees",
                "Slippage",
                "Holding ms",
                "Status",
            ),
            rows,
            "No completed trades in this bounded page.",
        )
        + "</section>"
    )


def _render_trade_segments(performance):
    rows = tuple(
        (
            item.display_id,
            item.dimension,
            item.label,
            item.member_count,
            item.realized_pnl,
            item.total_cost,
            item.winning_trades,
            item.losing_trades,
            item.breakeven_trades,
        )
        for item in performance.trade_segments
    )
    return (
        "<section><h2>Trade Segments</h2>"
        + _table(
            (
                "Segment",
                "Dimension",
                "Label",
                "Members",
                "Realized PnL",
                "Total Cost",
                "Wins",
                "Losses",
                "Breakeven",
            ),
            rows,
            "No trade segments.",
        )
        + "</section>"
    )


def _render_analyst_segments(performance):
    rows = tuple(
        (
            item.display_id,
            item.dimension,
            item.label,
            item.trace_count,
        )
        for item in performance.analyst_segments
    )
    return (
        "<section><h2>Analyst Segments</h2>"
        + _table(
            ("Segment", "Dimension", "Label", "Trace Count"),
            rows,
            "No analyst segments.",
        )
        + "</section>"
    )


def _overview_values(overview):
    return {item.field_key: item.value for item in overview.cards}


def _validate_pass_bundle(quality, overview, trades, performance):
    if (
        not isinstance(quality, QualityDiagnosticProjection)
        or quality.quality_status != "PASS"
        or quality.analytics_presentation_allowed is not True
        or quality.publication_allowed is not True
        or not isinstance(overview, DashboardOverviewProjection)
        or not isinstance(trades, CompletedTradeTableProjection)
        or not isinstance(performance, PerformanceSegmentationProjection)
    ):
        raise DashboardRenderError("PASS dashboard bundle is incomplete")

    source = overview.source
    if (
        trades.source != source
        or performance.source != source
        or quality.source_export_sha256 != source.export_sha256
        or quality.snapshot_time_ms != source.observed_at_ms
        or trades.source_metrics_sha256 != performance.source_metrics_sha256
    ):
        raise DashboardRenderError("PASS dashboard source identities do not match")

    cards = _overview_values(overview)
    if (
        cards.get("export_sha256") != source.export_sha256
        or cards.get("metrics_sha256") != trades.source_metrics_sha256
        or cards.get("segmentation_sha256")
        != performance.source_segmentation_sha256
        or cards.get("quality_status") != "PASS"
        or cards.get("paper_state") != "PAPER ONLY"
        or cards.get("live_master_lock") != "OFF"
        or cards.get("strategy_evidence") != "INSUFFICIENT_EVIDENCE"
        or performance.strategy_evidence != "INSUFFICIENT_EVIDENCE"
    ):
        raise DashboardRenderError("PASS dashboard provenance or safety binding changed")
    return source


def _view_model_sha(quality, overview, trades, performance):
    return _digest({
        "schema_version": RENDERER_SCHEMA_VERSION,
        "quality": quality.as_record(),
        "overview": None if overview is None else overview.as_record(),
        "trades": None if trades is None else trades.as_record(),
        "performance": None if performance is None else performance.as_record(),
    })


@dataclass(frozen=True, slots=True)
class RenderedDashboardArtifact:
    """One bounded deterministic in-memory HTML artifact; publication is P8-008."""

    html: str
    byte_length: int
    dashboard_sha256: str
    view_model_sha256: str
    source_export_sha256: str | None
    quality_status: str
    artifact_kind: str
    content_type: str = "text/html"
    encoding: str = "utf-8"
    self_contained: bool = True
    schema_version: int = RENDERER_SCHEMA_VERSION

    def __post_init__(self):
        encoded = self.html.encode("utf-8") if isinstance(self.html, str) else b""
        if (
            not isinstance(self.html, str)
            or not self.html.startswith("<!doctype html>\n<html lang=\"en\">")
            or not self.html.endswith("\n")
            or type(self.byte_length) is not int
            or self.byte_length != len(encoded)
            or not 1 <= self.byte_length <= MAX_DASHBOARD_BYTES
            or not _valid_sha(self.dashboard_sha256)
            or self.dashboard_sha256 != hashlib.sha256(encoded).hexdigest()
            or not _valid_sha(self.view_model_sha256)
            or self.quality_status not in ("PASS", "FAIL", "ABSENT")
            or self.artifact_kind not in ("FULL", "QUALITY_BLOCKED")
            or self.content_type != "text/html"
            or self.encoding != "utf-8"
            or self.self_contained is not True
            or self.schema_version != RENDERER_SCHEMA_VERSION
        ):
            raise DashboardRenderError("Rendered dashboard artifact identity is invalid")
        if self.quality_status == "PASS":
            if self.artifact_kind != "FULL" or not _valid_sha(self.source_export_sha256):
                raise DashboardRenderError("PASS dashboard artifact is incomplete")
        elif self.artifact_kind != "QUALITY_BLOCKED" or self.source_export_sha256 is not None:
            raise DashboardRenderError("Blocked dashboard artifact exposed source analytics")
        _assert_self_contained(self.html)

    def as_record(self):
        return {
            "schema_version": self.schema_version,
            "byte_length": self.byte_length,
            "dashboard_sha256": self.dashboard_sha256,
            "view_model_sha256": self.view_model_sha256,
            "source_export_sha256": self.source_export_sha256,
            "quality_status": self.quality_status,
            "artifact_kind": self.artifact_kind,
            "content_type": self.content_type,
            "encoding": self.encoding,
            "self_contained": self.self_contained,
        }


def render_dashboard(quality, *, overview=None, trades=None, performance=None):
    """Render one deterministic static dashboard without writing or network access."""

    if not isinstance(quality, QualityDiagnosticProjection):
        raise DashboardRenderError("Renderer requires P8 quality projection")

    if quality.quality_status == "PASS":
        source = _validate_pass_bundle(quality, overview, trades, performance)
        artifact_kind = "FULL"
        source_export_sha256 = source.export_sha256
    else:
        if (
            quality.analytics_presentation_allowed is not False
            or quality.publication_allowed is not False
            or overview is not None
            or trades is not None
            or performance is not None
        ):
            raise DashboardRenderError(
                "Blocked quality state cannot render partial analytics"
            )
        source = None
        artifact_kind = "QUALITY_BLOCKED"
        source_export_sha256 = None

    parts = [
        "<!doctype html>",
        "<html lang=\"en\">",
        "<head>",
        "<meta charset=\"utf-8\">",
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">",
        "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'unsafe-inline'; img-src 'none'; font-src 'none'; connect-src 'none'; script-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'\">",
        "<title>YATL Local Dashboard</title>",
        f"<style>{_CSS}</style>",
        "</head>",
        "<body>",
        "<main>",
        "<header>",
        "<h1>YATL Local Dashboard</h1>",
        "<p class=\"label\">Deterministic local read-only research presentation.</p>",
        _render_banner(),
        "</header>",
        _render_quality(quality),
    ]

    if quality.quality_status == "PASS":
        parts.extend(
            (
                _render_overview(overview),
                _render_metrics(performance),
                _render_trades(trades),
                _render_trade_segments(performance),
                _render_analyst_segments(performance),
                "<section><h2>Provenance</h2><div class=\"panel\">"
                f"<p><span class=\"label\">Source:</span> <code>{_e(source.source_id)}</code></p>"
                f"<p><span class=\"label\">Export SHA-256:</span> <code>{_e(source.export_sha256)}</code></p>"
                f"<p><span class=\"label\">Overview SHA-256:</span> <code>{_e(overview.overview_sha256)}</code></p>"
                f"<p><span class=\"label\">Trade table SHA-256:</span> <code>{_e(trades.table_sha256)}</code></p>"
                f"<p><span class=\"label\">Performance SHA-256:</span> <code>{_e(performance.projection_sha256)}</code></p>"
                f"<p><span class=\"label\">Quality projection SHA-256:</span> <code>{_e(quality.projection_sha256)}</code></p>"
                "</div></section>",
            )
        )
    else:
        parts.append(
            "<section><h2>Analytics Presentation</h2>"
            "<div class=\"panel\"><p class=\"status-blocked\">"
            "Analytics presentation is blocked by the P7 quality boundary."
            "</p></div></section>"
        )

    view_sha = _view_model_sha(quality, overview, trades, performance)
    parts.extend(
        (
            "<footer>",
            f"<p>View-model SHA-256: <code>{_e(view_sha)}</code></p>",
            "<p>Static artifact only. No network, provider, execution, account or risk capability.</p>",
            "</footer>",
            "</main>",
            "</body>",
            "</html>",
        )
    )
    html = "\n".join(parts) + "\n"
    encoded = html.encode("utf-8")
    if len(encoded) > MAX_DASHBOARD_BYTES:
        raise DashboardRenderError("Rendered dashboard exceeds bounded artifact size")
    _assert_self_contained(html)

    return RenderedDashboardArtifact(
        html=html,
        byte_length=len(encoded),
        dashboard_sha256=hashlib.sha256(encoded).hexdigest(),
        view_model_sha256=view_sha,
        source_export_sha256=source_export_sha256,
        quality_status=quality.quality_status,
        artifact_kind=artifact_kind,
    )
