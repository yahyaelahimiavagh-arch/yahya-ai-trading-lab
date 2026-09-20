"""Deterministic P8-009 adversarial dashboard matrix over accepted P7 exports."""

import contextlib
import hashlib
import io
import json
import os
import shutil
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from uuid import uuid4

from .cli import DashboardCliCode, DashboardCliError, dashboard_validate, main as cli_main
from .contracts import DashboardOverviewCard
from .loader import MAX_P7_EXPORT_BYTES, LoadedP7Export, load_p7_export
from .overview import DashboardOverviewProjection, project_overview
from .performance_views import project_performance_segmentation
from .quality_view import project_quality_diagnostics
from .renderer import (
    MAX_DASHBOARD_BYTES,
    DashboardRenderError,
    RenderedDashboardArtifact,
    render_dashboard,
)
from .trade_table import (
    CompletedTradeTableProjection,
    TradeTableProjectionError,
    project_completed_trade_table,
)


SCHEMA_VERSION = 1
ARTIFACT_KIND = "YATL_P8_ADVERSARIAL_DASHBOARD_SCENARIO"
MATRIX_KIND = "YATL_P8_ADVERSARIAL_DASHBOARD_MATRIX"
MAX_ARTIFACT_BYTES = 1024 * 1024
MAX_EVIDENCE_FILES = 32
MAX_EVIDENCE_TOTAL_BYTES = 32 * 1024 * 1024
SYMBOLS = ("BTCUSDT", "ETHUSDT")
SCENARIOS = (
    "P7_EXPORT_TAMPERING",
    "FABRICATED_QUALITY_PASS",
    "EVIDENCE_LABEL_UPGRADE",
    "CROSS_SYMBOL_ROW_INJECTION",
    "DUPLICATE_TRADE_IDENTITY",
    "OVERSIZED_INPUT_OUTPUT",
    "HTML_SCRIPT_INJECTION",
    "PATH_PRIVATE_MATERIAL_SMUGGLING",
    "DASHBOARD_ARTIFACT_MUTATION",
)
_HEX = frozenset("0123456789abcdef")


class DashboardScenarioError(Exception):
    """One fixed P8 adversarial scenario violated its exact fail-closed outcome."""


def _json(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ) + "\n"


def _compact_json(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _sha256(value):
    payload = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(payload).hexdigest()


def _valid_sha(value):
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in _HEX for character in value)
    )


def _digest(value):
    return _sha256(_compact_json(value))


@dataclass(frozen=True, slots=True)
class DashboardAcceptedFixture:
    symbol: str
    canonical_export_json: str
    export_sha256: str

    def __post_init__(self):
        if (
            self.symbol not in SYMBOLS
            or not isinstance(self.canonical_export_json, str)
            or not self.canonical_export_json.endswith("\n")
            or not _valid_sha(self.export_sha256)
            or len(self.canonical_export_json.encode("utf-8")) > MAX_P7_EXPORT_BYTES
        ):
            raise DashboardScenarioError("Accepted dashboard fixture identity is invalid")
        try:
            record = json.loads(self.canonical_export_json)
        except json.JSONDecodeError:
            raise DashboardScenarioError("Accepted dashboard fixture JSON is invalid") from None
        material = {
            "schema_version": record.get("schema_version"),
            "quality": record.get("quality"),
            "analytics": record.get("analytics"),
        }
        if (
            record.get("export_sha256") != self.export_sha256
            or _digest(material) != self.export_sha256
            or _json(record) != self.canonical_export_json
            or record.get("analytics", {}).get("symbol") != self.symbol
            or record.get("quality", {}).get("accepted_chain", {}).get("symbol")
            != self.symbol
        ):
            raise DashboardScenarioError("Accepted dashboard fixture binding is invalid")


def _fixture_identity(loaded):
    if not isinstance(loaded, LoadedP7Export):
        raise DashboardScenarioError("Accepted fixture loader identity is invalid")
    record = loaded.record()
    analytics = record["analytics"]
    return {
        "symbol": loaded.source.symbol,
        "export_sha256": loaded.export_sha256,
        "quality_sha256": loaded.quality_sha256,
        "metrics_sha256": analytics["metrics_sha256"],
        "segmentation_sha256": loaded.segmentation_sha256,
    }


def _baseline(path, expected_sha):
    loaded = load_p7_export(path, expected_sha)
    quality = project_quality_diagnostics(loaded=loaded)
    overview = project_overview(loaded)
    trades = project_completed_trade_table(loaded)
    performance = project_performance_segmentation(loaded)
    artifact = render_dashboard(
        quality,
        overview=overview,
        trades=trades,
        performance=performance,
    )
    return loaded, quality, overview, trades, performance, artifact


def _resign_export(record):
    record = json.loads(_json(record))
    material = {
        "schema_version": record["schema_version"],
        "quality": record["quality"],
        "analytics": record["analytics"],
    }
    export_sha = _digest(material)
    record["export_sha256"] = export_sha
    return record, export_sha, _json(record)


def _reject_validate(path, expected_sha):
    try:
        dashboard_validate(path, expected_sha)
    except DashboardCliError as exc:
        return exc.code
    raise DashboardScenarioError("Adversarial source unexpectedly validated")


def _scenario_export_tampering(ctx):
    attack = ctx["root"] / "attack.json"
    attack.write_bytes(ctx["fixture"].canonical_export_json.encode("utf-8") + b" ")
    code = _reject_validate(attack, ctx["fixture"].export_sha256)
    expected = {"source_code": "SOURCE_REJECTED", "accepted_source_unchanged": True}
    observed = {
        "source_code": code.value,
        "accepted_source_unchanged": ctx["accepted"].read_bytes() == ctx["accepted_before"],
    }
    return expected, observed


def _scenario_fabricated_quality_pass(ctx):
    record = json.loads(ctx["fixture"].canonical_export_json)
    record["quality"]["diagnostics"] = [
        {"code": "MISSING_SOURCE", "component": "SOURCE"}
    ]
    record, forged_sha, encoded = _resign_export(record)
    attack = ctx["root"] / "fabricated-pass.json"
    attack.write_text(encoded, encoding="utf-8")
    code = _reject_validate(attack, forged_sha)
    expected = {
        "source_code": "SOURCE_REJECTED",
        "fabricated_pass_blocked": True,
        "accepted_source_unchanged": True,
    }
    observed = {
        "source_code": code.value,
        "fabricated_pass_blocked": True,
        "accepted_source_unchanged": ctx["accepted"].read_bytes() == ctx["accepted_before"],
    }
    return expected, observed


def _scenario_evidence_upgrade(ctx):
    record = json.loads(ctx["fixture"].canonical_export_json)
    record["analytics"]["strategy_evidence"] = "PROVEN"
    analytics_sha = _digest(record["analytics"])
    record["quality"]["accepted_chain"]["segmentation_sha256"] = analytics_sha
    record, forged_sha, encoded = _resign_export(record)
    attack = ctx["root"] / "evidence-upgrade.json"
    attack.write_text(encoded, encoding="utf-8")
    code = _reject_validate(attack, forged_sha)
    expected = {
        "source_code": "SOURCE_REJECTED",
        "evidence_upgrade_blocked": True,
        "accepted_source_unchanged": True,
    }
    observed = {
        "source_code": code.value,
        "evidence_upgrade_blocked": True,
        "accepted_source_unchanged": ctx["accepted"].read_bytes() == ctx["accepted_before"],
    }
    return expected, observed


def _scenario_cross_symbol_row(ctx):
    trades = ctx["trades"]
    if not trades.rows:
        raise DashboardScenarioError("Cross-symbol scenario requires a completed trade")
    other = "ETHUSDT" if ctx["fixture"].symbol == "BTCUSDT" else "BTCUSDT"
    injected = replace(trades.rows[0], symbol=other)
    rejected = False
    try:
        replace(trades, rows=(injected, *trades.rows[1:]))
    except TradeTableProjectionError:
        rejected = True
    expected = {
        "cross_symbol_row_rejected": True,
        "table_identity_preserved": True,
        "accepted_source_unchanged": True,
    }
    observed = {
        "cross_symbol_row_rejected": rejected,
        "table_identity_preserved":
            ctx["trades"].table_sha256 == project_completed_trade_table(ctx["loaded"]).table_sha256,
        "accepted_source_unchanged": ctx["accepted"].read_bytes() == ctx["accepted_before"],
    }
    return expected, observed


def _scenario_duplicate_trade(ctx):
    trades = ctx["trades"]
    if not trades.rows:
        raise DashboardScenarioError("Duplicate-trade scenario requires a completed trade")
    row = trades.rows[0]
    rejected = False
    try:
        replace(
            trades,
            rows=(row, row),
            total_completed=max(2, trades.total_completed),
            total_filtered=2,
            returned_count=2,
            has_more=False,
        )
    except TradeTableProjectionError:
        rejected = True
    expected = {
        "duplicate_trade_rejected": True,
        "accepted_source_unchanged": True,
    }
    observed = {
        "duplicate_trade_rejected": rejected,
        "accepted_source_unchanged": ctx["accepted"].read_bytes() == ctx["accepted_before"],
    }
    return expected, observed


def _scenario_oversized(ctx):
    attack = ctx["root"] / "oversized.json"
    oversized = b"x" * (MAX_P7_EXPORT_BYTES + 1)
    attack.write_bytes(oversized)
    code = _reject_validate(attack, _sha256(oversized))

    base = ctx["artifact"]
    huge_html = base.html[:-1] + ("x" * MAX_DASHBOARD_BYTES) + "\n"
    encoded = huge_html.encode("utf-8")
    output_rejected = False
    try:
        RenderedDashboardArtifact(
            html=huge_html,
            byte_length=len(encoded),
            dashboard_sha256=_sha256(encoded),
            view_model_sha256=base.view_model_sha256,
            source_export_sha256=base.source_export_sha256,
            quality_status=base.quality_status,
            artifact_kind=base.artifact_kind,
        )
    except DashboardRenderError:
        output_rejected = True

    expected = {
        "input_code": "SOURCE_REJECTED",
        "oversized_input_rejected": True,
        "oversized_output_rejected": True,
        "accepted_source_unchanged": True,
    }
    observed = {
        "input_code": code.value,
        "oversized_input_rejected": True,
        "oversized_output_rejected": output_rejected,
        "accepted_source_unchanged": ctx["accepted"].read_bytes() == ctx["accepted_before"],
    }
    return expected, observed


def _scenario_html_injection(ctx):
    overview = ctx["overview"]
    cards = list(overview.cards)
    cards[0] = replace(
        cards[0],
        label="<script>alert(1)</script><img src=x onerror=alert(2)>",
    )
    poisoned = replace(overview, cards=tuple(cards))
    artifact = render_dashboard(
        ctx["quality"],
        overview=poisoned,
        trades=ctx["trades"],
        performance=ctx["performance"],
    )
    lowered = artifact.html.lower()
    expected = {
        "rendered": True,
        "script_tag_absent": True,
        "image_tag_absent": True,
        "escaped_payload_present": True,
        "accepted_source_unchanged": True,
    }
    observed = {
        "rendered": True,
        "script_tag_absent": "<script" not in lowered,
        "image_tag_absent": "<img" not in lowered,
        "escaped_payload_present":
            "&lt;script&gt;alert(1)&lt;/script&gt;" in artifact.html
            and "&lt;img src=x onerror=alert(2)&gt;" in artifact.html,
        "accepted_source_unchanged": ctx["accepted"].read_bytes() == ctx["accepted_before"],
    }
    return expected, observed


def _scenario_private_smuggling(ctx):
    record = json.loads(ctx["fixture"].canonical_export_json)
    record["analytics"]["private_key"] = "SENSITIVE_VALUE"
    record, forged_sha, encoded = _resign_export(record)
    attack = ctx["root"] / "private-material.json"
    attack.write_text(encoded, encoding="utf-8")
    code = _reject_validate(attack, forged_sha)

    private_path = ctx["root"] / "SENSITIVE_LOCAL_PATH.json"
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        exit_code = cli_main([
            "validate",
            "--input",
            str(private_path),
            "--expected-export-sha256",
            ctx["fixture"].export_sha256,
        ])
    cli_output = stream.getvalue()
    expected = {
        "source_code": "SOURCE_REJECTED",
        "private_material_blocked": True,
        "cli_error_redacted": True,
        "accepted_source_unchanged": True,
    }
    observed = {
        "source_code": code.value,
        "private_material_blocked": True,
        "cli_error_redacted":
            "SENSITIVE_LOCAL_PATH" not in cli_output
            and str(private_path) not in cli_output
            and exit_code != 0,
        "accepted_source_unchanged": ctx["accepted"].read_bytes() == ctx["accepted_before"],
    }
    return expected, observed


def _scenario_artifact_mutation(ctx):
    artifact = ctx["artifact"]
    mutated = artifact.html.replace("YATL Local Dashboard", "XATL Local Dashboard", 1)
    if len(mutated.encode("utf-8")) != artifact.byte_length:
        raise DashboardScenarioError("Artifact mutation fixture changed byte length")
    rejected = False
    try:
        replace(artifact, html=mutated)
    except DashboardRenderError:
        rejected = True
    expected = {
        "artifact_mutation_rejected": True,
        "accepted_source_unchanged": True,
    }
    observed = {
        "artifact_mutation_rejected": rejected,
        "accepted_source_unchanged": ctx["accepted"].read_bytes() == ctx["accepted_before"],
    }
    return expected, observed


_HANDLERS = {
    "P7_EXPORT_TAMPERING": _scenario_export_tampering,
    "FABRICATED_QUALITY_PASS": _scenario_fabricated_quality_pass,
    "EVIDENCE_LABEL_UPGRADE": _scenario_evidence_upgrade,
    "CROSS_SYMBOL_ROW_INJECTION": _scenario_cross_symbol_row,
    "DUPLICATE_TRADE_IDENTITY": _scenario_duplicate_trade,
    "OVERSIZED_INPUT_OUTPUT": _scenario_oversized,
    "HTML_SCRIPT_INJECTION": _scenario_html_injection,
    "PATH_PRIVATE_MATERIAL_SMUGGLING": _scenario_private_smuggling,
    "DASHBOARD_ARTIFACT_MUTATION": _scenario_artifact_mutation,
}


def _run_scenario(fixture, name):
    if not isinstance(fixture, DashboardAcceptedFixture) or name not in SCENARIOS:
        raise DashboardScenarioError("Scenario fixture or name is invalid")

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        accepted = root / "accepted.json"
        accepted.write_text(fixture.canonical_export_json, encoding="utf-8")
        accepted_before = accepted.read_bytes()

        loaded, quality, overview, trades, performance, artifact = _baseline(
            accepted,
            fixture.export_sha256,
        )
        identity = _fixture_identity(loaded)
        if identity["symbol"] != fixture.symbol:
            raise DashboardScenarioError("Scenario accepted symbol changed")

        context = {
            "root": root,
            "fixture": fixture,
            "accepted": accepted,
            "accepted_before": accepted_before,
            "loaded": loaded,
            "quality": quality,
            "overview": overview,
            "trades": trades,
            "performance": performance,
            "artifact": artifact,
        }
        expected, observed = _HANDLERS[name](context)
        passed = expected == observed and accepted.read_bytes() == accepted_before

    if not passed:
        raise DashboardScenarioError(f"Scenario failed closed invariant: {name}")

    record = {
        "schema_version": SCHEMA_VERSION,
        "artifact_kind": ARTIFACT_KIND,
        "symbol": fixture.symbol,
        "scenario": name,
        "accepted_source_identity": identity,
        "expected": expected,
        "observed": observed,
        "passed": True,
        "replay_equal": True,
        "strategy_evidence": "INSUFFICIENT_EVIDENCE",
        "paper_only": True,
        "read_only_source": True,
        "local_dashboard_only": True,
        "live_master_lock": "OFF",
        "spot_only": True,
        "allow_short": False,
        "allow_margin": False,
        "allow_futures": False,
        "allow_leverage": False,
        "allow_withdrawal": False,
        "trade_permission": False,
        "order_endpoints": False,
        "quantity_authority": False,
        "risk_authorization_mutation": False,
        "ai_direct_execution": False,
        "remote_resources": False,
    }
    record["result_sha256"] = _sha256(_json(record))
    return record


def scenario_artifact_json(record):
    required = {
        "schema_version",
        "artifact_kind",
        "symbol",
        "scenario",
        "accepted_source_identity",
        "expected",
        "observed",
        "passed",
        "replay_equal",
        "strategy_evidence",
        "paper_only",
        "read_only_source",
        "local_dashboard_only",
        "live_master_lock",
        "spot_only",
        "allow_short",
        "allow_margin",
        "allow_futures",
        "allow_leverage",
        "allow_withdrawal",
        "trade_permission",
        "order_endpoints",
        "quantity_authority",
        "risk_authorization_mutation",
        "ai_direct_execution",
        "remote_resources",
        "result_sha256",
    }
    if (
        not isinstance(record, dict)
        or set(record) != required
        or record.get("schema_version") != SCHEMA_VERSION
        or record.get("artifact_kind") != ARTIFACT_KIND
        or record.get("symbol") not in SYMBOLS
        or record.get("scenario") not in SCENARIOS
        or record.get("passed") is not True
        or record.get("replay_equal") is not True
        or record.get("expected") != record.get("observed")
        or record.get("strategy_evidence") != "INSUFFICIENT_EVIDENCE"
        or record.get("paper_only") is not True
        or record.get("read_only_source") is not True
        or record.get("local_dashboard_only") is not True
        or record.get("live_master_lock") != "OFF"
        or record.get("spot_only") is not True
        or record.get("allow_short") is not False
        or record.get("allow_margin") is not False
        or record.get("allow_futures") is not False
        or record.get("allow_leverage") is not False
        or record.get("allow_withdrawal") is not False
        or record.get("trade_permission") is not False
        or record.get("order_endpoints") is not False
        or record.get("quantity_authority") is not False
        or record.get("risk_authorization_mutation") is not False
        or record.get("ai_direct_execution") is not False
        or record.get("remote_resources") is not False
    ):
        raise DashboardScenarioError("Scenario artifact identity is invalid")

    identity = record.get("accepted_source_identity")
    if (
        not isinstance(identity, dict)
        or set(identity)
        != {
            "symbol",
            "export_sha256",
            "quality_sha256",
            "metrics_sha256",
            "segmentation_sha256",
        }
        or identity.get("symbol") != record["symbol"]
        or any(
            not _valid_sha(identity.get(name))
            for name in (
                "export_sha256",
                "quality_sha256",
                "metrics_sha256",
                "segmentation_sha256",
            )
        )
    ):
        raise DashboardScenarioError("Scenario accepted source identity is invalid")

    material = dict(record)
    result_sha = material.pop("result_sha256", None)
    if result_sha != _sha256(_json(material)):
        raise DashboardScenarioError("Scenario artifact digest is inconsistent")

    encoded = _json(record)
    lowered = encoded.lower()
    forbidden = (
        '"api_key"',
        '"api_secret"',
        '"password"',
        '"credential"',
        '"credentials"',
        '"private_key"',
        '"database_path"',
        '"endpoint_url"',
        '"raw_response"',
        "traceback",
        "select ",
        "update ",
        "insert ",
        "delete ",
        "<script",
        "<img",
        " src=",
        " href=",
    )
    if (
        any(item in lowered for item in forbidden)
        or len(encoded.encode("utf-8")) > MAX_ARTIFACT_BYTES
    ):
        raise DashboardScenarioError("Scenario artifact contains forbidden material")
    return encoded


@dataclass(frozen=True, slots=True)
class DashboardScenarioResult:
    symbol: str
    name: str
    artifact_json: str
    result_sha256: str

    def __post_init__(self):
        if (
            self.symbol not in SYMBOLS
            or self.name not in SCENARIOS
            or not isinstance(self.artifact_json, str)
            or not self.artifact_json.endswith("\n")
            or self.result_sha256 != _sha256(self.artifact_json)
        ):
            raise DashboardScenarioError("Scenario result identity is invalid")
        try:
            record = json.loads(self.artifact_json)
        except json.JSONDecodeError:
            raise DashboardScenarioError("Scenario result JSON is invalid") from None
        if (
            record.get("symbol") != self.symbol
            or record.get("scenario") != self.name
            or scenario_artifact_json(record) != self.artifact_json
        ):
            raise DashboardScenarioError("Scenario result and artifact differ")


@dataclass(frozen=True, slots=True)
class DashboardScenarioMatrixResult:
    runs: tuple[DashboardScenarioResult, ...]
    index_json: str

    def __post_init__(self):
        expected_order = tuple(
            (symbol, name)
            for symbol in SYMBOLS
            for name in SCENARIOS
        )
        actual_order = tuple((item.symbol, item.name) for item in self.runs)
        if (
            type(self.runs) is not tuple
            or actual_order != expected_order
            or not isinstance(self.index_json, str)
            or not self.index_json.endswith("\n")
            or len(self.index_json.encode("utf-8")) > MAX_ARTIFACT_BYTES
        ):
            raise DashboardScenarioError("Scenario matrix is incomplete or unordered")
        identities = {}
        for item in self.runs:
            record = json.loads(item.artifact_json)
            identity = record["accepted_source_identity"]
            prior = identities.setdefault(item.symbol, identity)
            if prior != identity:
                raise DashboardScenarioError("Accepted P7 identity drifted across scenarios")

        expected_records = [
            {
                "symbol": item.symbol,
                "scenario": item.name,
                "file": _filename(item.symbol, item.name),
                "sha256": item.result_sha256,
                "passed": True,
                "replay_equal": True,
            }
            for item in self.runs
        ]
        expected_index = {
            "schema_version": SCHEMA_VERSION,
            "artifact_kind": MATRIX_KIND,
            "symbols": list(SYMBOLS),
            "scenarios": list(SCENARIOS),
            "runs": expected_records,
            "accepted_source_identities": {
                symbol: identities[symbol]
                for symbol in SYMBOLS
            },
            "strategy_evidence": "INSUFFICIENT_EVIDENCE",
            "paper_only": True,
            "read_only_source": True,
            "local_dashboard_only": True,
            "live_master_lock": "OFF",
            "spot_only": True,
            "allow_short": False,
            "allow_margin": False,
            "allow_futures": False,
            "allow_leverage": False,
            "allow_withdrawal": False,
            "trade_permission": False,
            "order_endpoints": False,
            "quantity_authority": False,
            "risk_authorization_mutation": False,
            "ai_direct_execution": False,
            "remote_resources": False,
        }
        try:
            actual = json.loads(self.index_json)
        except json.JSONDecodeError:
            raise DashboardScenarioError("Scenario matrix index JSON is invalid") from None
        if actual != expected_index or _json(actual) != self.index_json:
            raise DashboardScenarioError("Scenario matrix index is noncanonical")


def _filename(symbol, name):
    return f"{symbol.lower()}-{name.lower().replace('_', '-')}.json"


def run_adversarial_dashboard_matrix(fixtures):
    if (
        not isinstance(fixtures, dict)
        or set(fixtures) != set(SYMBOLS)
        or any(not isinstance(fixtures[symbol], DashboardAcceptedFixture) for symbol in SYMBOLS)
    ):
        raise DashboardScenarioError("Dashboard scenario fixture set is invalid")

    runs = []
    for symbol in SYMBOLS:
        fixture = fixtures[symbol]
        for name in SCENARIOS:
            first = scenario_artifact_json(_run_scenario(fixture, name))
            replay = scenario_artifact_json(_run_scenario(fixture, name))
            if first != replay:
                raise DashboardScenarioError(
                    f"Scenario replay diverged: {symbol}/{name}"
                )
            runs.append(
                DashboardScenarioResult(
                    symbol,
                    name,
                    first,
                    _sha256(first),
                )
            )

    identities = {}
    records = []
    for item in runs:
        record = json.loads(item.artifact_json)
        identities.setdefault(item.symbol, record["accepted_source_identity"])
        records.append({
            "symbol": item.symbol,
            "scenario": item.name,
            "file": _filename(item.symbol, item.name),
            "sha256": item.result_sha256,
            "passed": True,
            "replay_equal": True,
        })

    index = {
        "schema_version": SCHEMA_VERSION,
        "artifact_kind": MATRIX_KIND,
        "symbols": list(SYMBOLS),
        "scenarios": list(SCENARIOS),
        "runs": records,
        "accepted_source_identities": {
            symbol: identities[symbol]
            for symbol in SYMBOLS
        },
        "strategy_evidence": "INSUFFICIENT_EVIDENCE",
        "paper_only": True,
        "read_only_source": True,
        "local_dashboard_only": True,
        "live_master_lock": "OFF",
        "spot_only": True,
        "allow_short": False,
        "allow_margin": False,
        "allow_futures": False,
        "allow_leverage": False,
        "allow_withdrawal": False,
        "trade_permission": False,
        "order_endpoints": False,
        "quantity_authority": False,
        "risk_authorization_mutation": False,
        "ai_direct_execution": False,
        "remote_resources": False,
    }
    return DashboardScenarioMatrixResult(tuple(runs), _json(index))


def write_adversarial_dashboard_matrix(result, output_dir):
    if not isinstance(result, DashboardScenarioMatrixResult):
        raise DashboardScenarioError("Scenario matrix output is invalid")
    target = (
        Path(output_dir)
        if isinstance(output_dir, (str, Path)) and str(output_dir)
        else None
    )
    if target is None:
        raise DashboardScenarioError("Scenario evidence output directory is invalid")
    if target.exists():
        raise DashboardScenarioError("Existing scenario evidence will not be overwritten")
    parent = target.parent
    if not parent.exists() or not parent.is_dir() or parent.is_symlink():
        raise DashboardScenarioError("Scenario evidence parent is invalid")

    temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
    try:
        temporary.mkdir()
        payloads = {"p8-009-index.json": result.index_json}
        for item in result.runs:
            payloads[_filename(item.symbol, item.name)] = item.artifact_json
        if len(payloads) != 1 + len(SYMBOLS) * len(SCENARIOS):
            raise DashboardScenarioError("Scenario evidence file count is invalid")

        total = 0
        for name in sorted(payloads):
            payload = payloads[name]
            encoded = payload.encode("utf-8")
            total += len(encoded)
            if (
                not encoded
                or len(encoded) > MAX_ARTIFACT_BYTES
                or total > MAX_EVIDENCE_TOTAL_BYTES
            ):
                raise DashboardScenarioError("Scenario evidence size is invalid")
            path = temporary / name
            path.write_bytes(encoded)

        written = tuple(sorted(temporary.iterdir(), key=lambda item: item.name))
        if (
            len(written) > MAX_EVIDENCE_FILES
            or any(item.is_symlink() or not item.is_file() for item in written)
        ):
            raise DashboardScenarioError("Scenario evidence contents are invalid")
        os.replace(temporary, target)
        temporary = None
    except DashboardScenarioError:
        raise
    except OSError:
        raise DashboardScenarioError("Scenario evidence publication failed") from None
    finally:
        if temporary is not None and temporary.exists():
            shutil.rmtree(temporary, ignore_errors=True)
    return target


def dashboard_matrix_sha256(result):
    if not isinstance(result, DashboardScenarioMatrixResult):
        raise DashboardScenarioError("Scenario matrix digest input is invalid")
    return _sha256(result.index_json)
