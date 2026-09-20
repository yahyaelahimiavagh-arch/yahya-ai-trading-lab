import inspect
import tempfile
import unittest
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

from yatl.analytics.cli import _export_payload
from yatl.analytics.quality import run_quality_gate
from yatl.analytics.quality_runtime import SNAPSHOT, _fixture
from yatl.dashboard.loader import load_p7_export
from yatl.dashboard.overview import project_overview
from yatl.dashboard.performance_views import project_performance_segmentation
from yatl.dashboard.quality_view import project_quality_diagnostics
from yatl.dashboard.renderer import (
    MAX_DASHBOARD_BYTES,
    DashboardRenderError,
    RenderedDashboardArtifact,
    render_dashboard,
)
from yatl.dashboard.trade_table import project_completed_trade_table


class DashboardRendererTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

        healthy_root = self.root / "healthy"
        healthy_root.mkdir()
        _, _, specs = _fixture(healthy_root)
        gate = run_quality_gate(SNAPSHOT, specs)
        self.record, encoded = _export_payload(gate)
        export_path = self.root / "accepted.json"
        export_path.write_text(encoded, encoding="utf-8")
        self.loaded = load_p7_export(export_path, self.record["export_sha256"])

        self.quality = project_quality_diagnostics(loaded=self.loaded)
        self.overview = project_overview(self.loaded)
        self.trades = project_completed_trade_table(self.loaded)
        self.performance = project_performance_segmentation(self.loaded)

        failed_root = self.root / "failed"
        failed_root.mkdir()
        _, p6, failed_specs = _fixture(failed_root)
        p6.unlink()
        failed_gate = run_quality_gate(SNAPSHOT, failed_specs)
        self.fail_quality = project_quality_diagnostics(
            quality_record=failed_gate.report.as_record()
        )
        self.absent_quality = project_quality_diagnostics()

    def tearDown(self):
        self.temp.cleanup()

    def render_full(self, **overrides):
        values = {
            "quality": self.quality,
            "overview": self.overview,
            "trades": self.trades,
            "performance": self.performance,
        }
        values.update(overrides)
        return render_dashboard(
            values["quality"],
            overview=values["overview"],
            trades=values["trades"],
            performance=values["performance"],
        )

    def test_full_render_is_byte_identical(self):
        first = self.render_full()
        second = self.render_full()
        self.assertEqual(first, second)
        self.assertEqual(first.html.encode("utf-8"), second.html.encode("utf-8"))
        self.assertEqual(first.dashboard_sha256, second.dashboard_sha256)

    def test_full_render_has_stable_hash_and_exact_byte_length(self):
        artifact = self.render_full()
        self.assertEqual(len(artifact.dashboard_sha256), 64)
        self.assertEqual(len(artifact.view_model_sha256), 64)
        self.assertEqual(artifact.byte_length, len(artifact.html.encode("utf-8")))
        self.assertLessEqual(artifact.byte_length, MAX_DASHBOARD_BYTES)

    def test_full_render_is_frozen(self):
        artifact = self.render_full()
        with self.assertRaises(FrozenInstanceError):
            artifact.byte_length = 0

    def test_full_render_is_browser_openable_static_document(self):
        artifact = self.render_full()
        self.assertTrue(artifact.html.startswith("<!doctype html>\n<html lang=\"en\">"))
        self.assertTrue(artifact.html.endswith("</html>\n"))
        self.assertIn("<head>", artifact.html)
        self.assertIn("<body>", artifact.html)
        self.assertIn("<main>", artifact.html)
        self.assertIn("<style>", artifact.html)

    def test_content_security_policy_blocks_script_and_network(self):
        artifact = self.render_full()
        self.assertIn("Content-Security-Policy", artifact.html)
        self.assertIn("default-src 'none'", artifact.html)
        self.assertIn("connect-src 'none'", artifact.html)
        self.assertIn("script-src 'none'", artifact.html)
        self.assertIn("font-src 'none'", artifact.html)
        self.assertIn("img-src 'none'", artifact.html)

    def test_no_remote_capable_tags_or_attributes(self):
        artifact = self.render_full()
        lowered = artifact.html.lower()
        for forbidden in (
            "<script",
            "<img",
            "<iframe",
            "<link",
            "<object",
            "<embed",
            "<audio",
            "<video",
            "<source",
            " src=",
            " href=",
            " srcset=",
            " action=",
            " formaction=",
            " poster=",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, lowered)

    def test_no_remote_or_persistent_client_capability(self):
        artifact = self.render_full()
        lowered = artifact.html.lower()
        for forbidden in (
            "fetch(",
            "xmlhttprequest",
            "websocket",
            "localstorage",
            "sessionstorage",
            "document.cookie",
            "@import",
            "url(",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, lowered)

    def test_full_render_contains_non_overridable_safety_banner(self):
        artifact = self.render_full()
        for required in (
            "PAPER ONLY",
            "LIVE_MASTER_LOCK=OFF",
            "INSUFFICIENT_EVIDENCE",
            "DESCRIPTIVE ONLY",
            "NOT A PROFITABILITY OR LIVE-READINESS CLAIM",
        ):
            with self.subTest(required=required):
                self.assertIn(required, artifact.html)

    def test_full_render_contains_all_primary_sections(self):
        artifact = self.render_full()
        for heading in (
            "Quality Gate",
            "System / Safety / Quality Overview",
            "Performance Metrics",
            "Completed Trades",
            "Trade Segments",
            "Analyst Segments",
            "Provenance",
        ):
            with self.subTest(heading=heading):
                self.assertIn(f"<h2>{heading}</h2>", artifact.html)

    def test_full_render_preserves_exact_high_precision_metric_text(self):
        artifact = self.render_full()
        for metric in self.performance.metrics:
            if metric.value is not None and len(metric.value) > 96:
                self.assertIn(metric.value, artifact.html)
                return
        self.fail("Fixture did not expose a >96-character exact metric value")

    def test_full_render_preserves_exact_trade_numeric_strings(self):
        artifact = self.render_full()
        for row in self.trades.rows:
            self.assertIn(row.net_pnl, artifact.html)
            self.assertIn(row.gross_return, artifact.html)
            self.assertIn(row.net_return, artifact.html)

    def test_overview_label_xss_is_escaped(self):
        cards = list(self.overview.cards)
        cards[0] = replace(cards[0], label="<script>alert('x')</script>")
        poisoned = replace(self.overview, cards=tuple(cards))
        artifact = self.render_full(overview=poisoned)
        self.assertNotIn("<script>alert", artifact.html)
        self.assertIn("&lt;script&gt;alert(&#x27;x&#x27;)&lt;/script&gt;", artifact.html)

    def test_overview_value_html_is_escaped(self):
        cards = list(self.overview.cards)
        target = next(
            index
            for index, item in enumerate(cards)
            if item.field_key == "snapshot_time_ms"
        )
        cards[target] = replace(cards[target], value="<b>evil</b>")
        poisoned = replace(self.overview, cards=tuple(cards))
        artifact = self.render_full(overview=poisoned)
        self.assertNotIn("<b>evil</b>", artifact.html)
        self.assertIn("&lt;b&gt;evil&lt;/b&gt;", artifact.html)

    def test_trade_segment_label_xss_is_escaped(self):
        segments = list(self.performance.trade_segments)
        segments[0] = replace(
            segments[0],
            label="<img src=x onerror=alert(1)>",
        )
        poisoned = replace(self.performance, trade_segments=tuple(segments))
        artifact = self.render_full(performance=poisoned)
        self.assertNotIn("<img", artifact.html.lower())
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;", artifact.html)

    def test_analyst_segment_label_html_is_escaped(self):
        segments = list(self.performance.analyst_segments)
        segments[0] = replace(segments[0], label="<svg onload=alert(1)>")
        poisoned = replace(self.performance, analyst_segments=tuple(segments))
        artifact = self.render_full(performance=poisoned)
        self.assertNotIn("<svg", artifact.html.lower())
        self.assertIn("&lt;svg onload=alert(1)&gt;", artifact.html)

    def test_blocked_diagnostic_message_xss_is_escaped(self):
        diagnostics = list(self.fail_quality.diagnostics)
        diagnostics[0] = replace(
            diagnostics[0],
            message="<iframe src=https://evil.invalid></iframe>",
        )
        poisoned = replace(self.fail_quality, diagnostics=tuple(diagnostics))
        artifact = render_dashboard(poisoned)
        self.assertNotIn("<iframe", artifact.html.lower())
        self.assertIn("&lt;iframe src=https://evil.invalid&gt;", artifact.html)

    def test_pass_requires_all_three_analytics_projections(self):
        with self.assertRaises(DashboardRenderError):
            render_dashboard(
                self.quality,
                overview=self.overview,
                trades=self.trades,
            )

    def test_pass_rejects_cross_source_overview_identity(self):
        forged_source = replace(
            self.overview.source,
            export_sha256="a" * 64,
        )
        forged = replace(self.overview, source=forged_source)
        with self.assertRaises(DashboardRenderError):
            self.render_full(overview=forged)

    def test_pass_rejects_cross_source_trade_identity(self):
        forged_source = replace(
            self.trades.source,
            export_sha256="a" * 64,
        )
        forged = replace(self.trades, source=forged_source)
        with self.assertRaises(DashboardRenderError):
            self.render_full(trades=forged)

    def test_pass_rejects_cross_source_performance_identity(self):
        forged_source = replace(
            self.performance.source,
            export_sha256="a" * 64,
        )
        forged = replace(self.performance, source=forged_source)
        with self.assertRaises(DashboardRenderError):
            self.render_full(performance=forged)

    def test_pass_rejects_metrics_sha_mismatch(self):
        forged = replace(self.trades, source_metrics_sha256="a" * 64)
        with self.assertRaises(DashboardRenderError):
            self.render_full(trades=forged)

    def test_pass_rejects_quality_export_sha_mismatch(self):
        forged = replace(self.quality, source_export_sha256="a" * 64)
        with self.assertRaises(DashboardRenderError):
            self.render_full(quality=forged)

    def test_fail_renders_quality_only_blocked_artifact(self):
        artifact = render_dashboard(self.fail_quality)
        self.assertEqual(artifact.quality_status, "FAIL")
        self.assertEqual(artifact.artifact_kind, "QUALITY_BLOCKED")
        self.assertIsNone(artifact.source_export_sha256)
        self.assertIn("Analytics presentation is blocked", artifact.html)
        self.assertNotIn("<h2>Performance Metrics</h2>", artifact.html)
        self.assertNotIn("<h2>Completed Trades</h2>", artifact.html)

    def test_absent_renders_quality_only_blocked_artifact(self):
        artifact = render_dashboard(self.absent_quality)
        self.assertEqual(artifact.quality_status, "ABSENT")
        self.assertEqual(artifact.artifact_kind, "QUALITY_BLOCKED")
        self.assertIsNone(artifact.source_export_sha256)
        self.assertNotIn("<h2>Performance Metrics</h2>", artifact.html)

    def test_fail_rejects_injected_overview(self):
        with self.assertRaises(DashboardRenderError):
            render_dashboard(self.fail_quality, overview=self.overview)

    def test_fail_rejects_injected_trade_table(self):
        with self.assertRaises(DashboardRenderError):
            render_dashboard(self.fail_quality, trades=self.trades)

    def test_fail_rejects_injected_performance(self):
        with self.assertRaises(DashboardRenderError):
            render_dashboard(self.fail_quality, performance=self.performance)

    def test_absent_rejects_any_analytics_projection(self):
        with self.assertRaises(DashboardRenderError):
            render_dashboard(
                self.absent_quality,
                overview=self.overview,
                trades=self.trades,
                performance=self.performance,
            )

    def test_renderer_rejects_non_quality_input(self):
        with self.assertRaises(DashboardRenderError):
            render_dashboard(object())

    def test_artifact_rejects_html_digest_mismatch(self):
        artifact = self.render_full()
        with self.assertRaises(DashboardRenderError):
            replace(artifact, dashboard_sha256="a" * 64)

    def test_artifact_rejects_byte_length_mismatch(self):
        artifact = self.render_full()
        with self.assertRaises(DashboardRenderError):
            replace(artifact, byte_length=artifact.byte_length + 1)

    def test_artifact_rejects_remote_tag_even_with_recomputed_hash(self):
        artifact = self.render_full()
        poisoned_html = artifact.html.replace(
            "</body>",
            "<img src=\"https://evil.invalid/x.png\"></body>",
        )
        import hashlib
        encoded = poisoned_html.encode("utf-8")
        with self.assertRaises(DashboardRenderError):
            RenderedDashboardArtifact(
                html=poisoned_html,
                byte_length=len(encoded),
                dashboard_sha256=hashlib.sha256(encoded).hexdigest(),
                view_model_sha256=artifact.view_model_sha256,
                source_export_sha256=artifact.source_export_sha256,
                quality_status=artifact.quality_status,
                artifact_kind=artifact.artifact_kind,
            )

    def test_artifact_is_in_memory_only_contract(self):
        artifact = self.render_full()
        record = artifact.as_record()
        for forbidden in (
            "path",
            "file",
            "output",
            "overwrite",
            "temp",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertFalse(any(forbidden in key for key in record))

    def test_renderer_source_has_no_file_write_or_transport_capability(self):
        import yatl.dashboard.renderer as renderer

        source_text = inspect.getsource(renderer)
        for forbidden in (
            "from pathlib",
            "import pathlib",
            "open(",
            ".write_text",
            ".write_bytes",
            "os.replace",
            "tempfile",
            "from yatl.analytics",
            "import yatl.analytics",
            "sqlite3",
            "database_path",
            "from yatl.execution",
            "import yatl.execution",
            "from yatl.account",
            "import yatl.account",
            "from yatl.risk",
            "import yatl.risk",
            "urllib",
            "http.client",
            "requests",
            "httpx",
            "aiohttp",
            "websockets",
            "socket",
            "openai",
            "anthropic",
            "os.getenv",
            "os.environ",
            "/api/v3/order",
            "/fapi",
            "/dapi",
            "withdraw(",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source_text)


if __name__ == "__main__":
    unittest.main()
