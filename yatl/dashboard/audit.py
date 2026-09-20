"""Independent fail-closed final acceptance audit for the complete P8 Dashboard."""

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path

from .contracts import DashboardPolicy
from .loader import MAX_P7_EXPORT_BYTES, P7ExportLoadError, load_p7_export
from .overview import OverviewProjectionError, project_overview
from .performance_views import (
    PerformanceViewProjectionError,
    project_performance_segmentation,
)
from .quality_view import (
    QualityDiagnosticProjectionError,
    project_quality_diagnostics,
)
from .renderer import (
    MAX_DASHBOARD_BYTES,
    DashboardRenderError,
    render_dashboard,
)
from .scenarios import (
    MAX_ARTIFACT_BYTES,
    SCENARIOS,
    SYMBOLS,
    DashboardAcceptedFixture,
    DashboardScenarioError,
    run_adversarial_dashboard_matrix,
    scenario_artifact_json,
)
from .trade_table import TradeTableProjectionError, project_completed_trade_table


EXPECTED_POLICY_SHA256 = (
    "b4534112975f519714592ad7468c950eb6aa112f49b9aee80b1d15bf51804c2e"
)
EXPECTED_INDEX_SHA256 = (
    "38bc0e1eafedd44b1776ecec1a65fc48352a3155341dfca323641686739a8608"
)
EXPECTED_EXPORTS = {
    "BTCUSDT": "8e11935814a57389399eea4046beed2f98b7bb448b25465740ef868f7e4dc456",
    "ETHUSDT": "1ea65455e44f8723709f504f585da965683558608909bd2da75ab561c5e9c092",
}
EXPECTED_EXPORT_SET_SHA256 = (
    "6f884ea930cd929292f000e8ada2da370b4428d7173a1f3d2423deacc6523439"
)
MAX_EVIDENCE_TOTAL_BYTES = 32 * 1024 * 1024
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


class P8AuditError(Exception):
    """P8 policy, source, projection, renderer or evidence is inconsistent."""


def _compact_json(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _json(value):
    return _compact_json(value) + "\n"


def _sha256(value):
    payload = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(payload).hexdigest()


def _valid_sha(value):
    return isinstance(value, str) and SHA256_PATTERN.fullmatch(value) is not None


def _policy_sha256():
    policy = DashboardPolicy()
    digest = policy.policy_sha256
    if digest != EXPECTED_POLICY_SHA256:
        raise P8AuditError("Frozen P8 Dashboard policy digest changed")
    if (
        policy.mode != "LOCAL_READ_ONLY_DASHBOARD"
        or policy.source_scope != "ACCEPTED_SANITIZED_P7_EXPORT_ONLY"
        or policy.display_only is not True
        or policy.paper_only is not True
        or policy.live_master_lock != "OFF"
        or policy.spot_only is not True
        or any(
            getattr(policy, name) is not False
            for name in (
                "allow_short",
                "allow_margin",
                "allow_futures",
                "allow_leverage",
                "allow_withdrawal",
                "allow_remote_assets",
                "allow_external_scripts",
                "allow_network_transport",
                "allow_provider_transport",
                "allow_credentials",
                "allow_source_write",
                "allow_direct_p5_p6_access",
                "allow_execution_import",
                "allow_account_import",
                "allow_risk_import",
                "allow_risk_authorization_mutation",
                "allow_quantity_authority",
                "allow_trade_permission",
                "allow_order_endpoint",
                "allow_ai_direct_execution",
                "allow_strategy_evidence_upgrade",
            )
        )
    ):
        raise P8AuditError("P8 Dashboard policy safety boundary changed")
    return digest


def _read_regular_file(path, max_bytes, label):
    if not isinstance(path, (str, os.PathLike)) or not str(path):
        raise P8AuditError(f"{label} path is invalid")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError:
        raise P8AuditError(f"{label} cannot be opened safely") from None
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_size <= 0
            or metadata.st_size > max_bytes
        ):
            raise P8AuditError(f"{label} size or file type is invalid")
        chunks = []
        remaining = metadata.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 64 * 1024))
            if not chunk:
                raise P8AuditError(f"{label} read is incomplete")
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        if len(data) != metadata.st_size:
            raise P8AuditError(f"{label} changed while reading")
        return data
    except P8AuditError:
        raise
    except OSError:
        raise P8AuditError(f"{label} cannot be read safely") from None
    finally:
        os.close(descriptor)


def _load_exports(export_paths):
    if not isinstance(export_paths, dict) or set(export_paths) != set(SYMBOLS):
        raise P8AuditError("P8 export path set is incomplete")

    fixtures = {}
    loaded_by_symbol = {}
    before = {}
    after = {}
    renderer_identity = {}

    for symbol in SYMBOLS:
        expected_sha = EXPECTED_EXPORTS[symbol]
        path = export_paths[symbol]
        raw_before = _read_regular_file(path, MAX_P7_EXPORT_BYTES, "P7 export")
        before[symbol] = _sha256(raw_before)
        try:
            loaded = load_p7_export(path, expected_sha)
        except P7ExportLoadError:
            raise P8AuditError("Accepted P7 export failed independent load") from None
        raw_after = _read_regular_file(path, MAX_P7_EXPORT_BYTES, "P7 export")
        after[symbol] = _sha256(raw_after)

        if (
            raw_before != raw_after
            or loaded.export_sha256 != expected_sha
            or loaded.source.symbol != symbol
            or loaded.raw_file_sha256 != before[symbol]
            or loaded.byte_length != len(raw_before)
            or loaded.canonical_json.encode("utf-8") != raw_before
        ):
            raise P8AuditError("Accepted P7 export identity or no-write boundary changed")

        try:
            quality_first = project_quality_diagnostics(loaded=loaded)
            overview_first = project_overview(loaded)
            trades_first = project_completed_trade_table(loaded)
            performance_first = project_performance_segmentation(loaded)
            artifact_first = render_dashboard(
                quality_first,
                overview=overview_first,
                trades=trades_first,
                performance=performance_first,
            )

            quality_second = project_quality_diagnostics(loaded=loaded)
            overview_second = project_overview(loaded)
            trades_second = project_completed_trade_table(loaded)
            performance_second = project_performance_segmentation(loaded)
            artifact_second = render_dashboard(
                quality_second,
                overview=overview_second,
                trades=trades_second,
                performance=performance_second,
            )
        except (
            QualityDiagnosticProjectionError,
            OverviewProjectionError,
            TradeTableProjectionError,
            PerformanceViewProjectionError,
            DashboardRenderError,
        ):
            raise P8AuditError("P8 projection or renderer replay failed") from None

        if (
            quality_first != quality_second
            or overview_first != overview_second
            or trades_first != trades_second
            or performance_first != performance_second
            or artifact_first != artifact_second
            or quality_first.quality_status != "PASS"
            or quality_first.publication_allowed is not True
            or quality_first.analytics_presentation_allowed is not True
            or quality_first.partial_analytics_visible is not False
            or artifact_first.artifact_kind != "FULL"
            or artifact_first.quality_status != "PASS"
            or artifact_first.source_export_sha256 != expected_sha
            or artifact_first.byte_length > MAX_DASHBOARD_BYTES
            or not artifact_first.self_contained
        ):
            raise P8AuditError("P8 deterministic projection or renderer identity changed")

        fixtures[symbol] = DashboardAcceptedFixture(
            symbol,
            loaded.canonical_json,
            loaded.export_sha256,
        )
        loaded_by_symbol[symbol] = loaded
        renderer_identity[symbol] = {
            "view_model_sha256": artifact_first.view_model_sha256,
            "dashboard_sha256": artifact_first.dashboard_sha256,
            "bytes": artifact_first.byte_length,
        }

    if before != after:
        raise P8AuditError("Accepted P7 exports changed during final audit")
    export_set_sha = _sha256(_compact_json(EXPECTED_EXPORTS))
    if export_set_sha != EXPECTED_EXPORT_SET_SHA256:
        raise P8AuditError("Frozen accepted P7 export set digest changed")
    return fixtures, loaded_by_symbol, renderer_identity, export_set_sha


def _filename(symbol, scenario):
    return f"{symbol.lower()}-{scenario.lower().replace('_', '-')}.json"


def _expected_evidence(replay):
    files = {"p8-009-index.json": replay.index_json}
    for item in replay.runs:
        files[_filename(item.symbol, item.name)] = item.artifact_json
    if len(files) != 19:
        raise P8AuditError("P8 adversarial replay file coverage is incomplete")
    return files


def _decode_evidence(name, payload):
    try:
        text = payload.decode("utf-8")
        record = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise P8AuditError(f"P8 evidence JSON is invalid ({name})") from None
    if not isinstance(record, dict) or _json(record) != text:
        raise P8AuditError(f"P8 evidence JSON is noncanonical ({name})")
    lowered = text.casefold()
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
    if any(value in lowered for value in forbidden):
        raise P8AuditError(f"P8 evidence contains forbidden material ({name})")
    return text, record


def _read_evidence(directory):
    target = (
        Path(directory)
        if isinstance(directory, (str, Path)) and str(directory)
        else None
    )
    if target is None or not target.is_dir() or target.is_symlink():
        raise P8AuditError("P8 evidence directory is invalid")

    expected_names = {"p8-009-index.json"} | {
        _filename(symbol, scenario)
        for symbol in SYMBOLS
        for scenario in SCENARIOS
    }
    try:
        paths = tuple(sorted(target.iterdir(), key=lambda item: item.name))
        if (
            {item.name for item in paths} != expected_names
            or any(item.is_symlink() or not item.is_file() for item in paths)
        ):
            raise P8AuditError("P8 evidence directory contents are invalid")
        before = {}
        total = 0
        for path in paths:
            payload = path.read_bytes()
            total += len(payload)
            if (
                not payload
                or len(payload) > MAX_ARTIFACT_BYTES
                or total > MAX_EVIDENCE_TOTAL_BYTES
            ):
                raise P8AuditError("P8 evidence size is invalid")
            before[path.name] = payload
        after = {path.name: path.read_bytes() for path in paths}
    except P8AuditError:
        raise
    except OSError:
        raise P8AuditError("P8 evidence cannot be read safely") from None

    if before != after:
        raise P8AuditError("P8 evidence changed during final audit")

    decoded = {}
    records = {}
    for name, payload in before.items():
        decoded[name], records[name] = _decode_evidence(name, payload)
    return decoded, records


def _audit_evidence_records(records):
    index = records.get("p8-009-index.json")
    if not isinstance(index, dict):
        raise P8AuditError("P8 adversarial index is invalid")
    if (
        index.get("artifact_kind") != "YATL_P8_ADVERSARIAL_DASHBOARD_MATRIX"
        or index.get("symbols") != list(SYMBOLS)
        or index.get("scenarios") != list(SCENARIOS)
        or index.get("strategy_evidence") != "INSUFFICIENT_EVIDENCE"
        or index.get("paper_only") is not True
        or index.get("read_only_source") is not True
        or index.get("local_dashboard_only") is not True
        or index.get("live_master_lock") != "OFF"
        or index.get("trade_permission") is not False
        or index.get("order_endpoints") is not False
        or index.get("quantity_authority") is not False
        or index.get("risk_authorization_mutation") is not False
        or index.get("ai_direct_execution") is not False
        or index.get("remote_resources") is not False
    ):
        raise P8AuditError("P8 adversarial index safety boundary changed")

    expected_order = [
        (symbol, scenario)
        for symbol in SYMBOLS
        for scenario in SCENARIOS
    ]
    runs = index.get("runs")
    if (
        not isinstance(runs, list)
        or [(item.get("symbol"), item.get("scenario")) for item in runs]
        != expected_order
    ):
        raise P8AuditError("P8 adversarial index order or coverage changed")

    identities = index.get("accepted_source_identities")
    if (
        not isinstance(identities, dict)
        or set(identities) != set(SYMBOLS)
        or any(
            identities[symbol].get("export_sha256") != EXPECTED_EXPORTS[symbol]
            for symbol in SYMBOLS
        )
    ):
        raise P8AuditError("P8 adversarial accepted source identities changed")

    for item in runs:
        name = item.get("file")
        digest = item.get("sha256")
        if (
            not isinstance(name, str)
            or name not in records
            or item.get("passed") is not True
            or item.get("replay_equal") is not True
            or not _valid_sha(digest)
            or digest != _sha256(_json(records[name]))
        ):
            raise P8AuditError("P8 adversarial index reference changed")
        try:
            if scenario_artifact_json(records[name]) != _json(records[name]):
                raise P8AuditError("P8 adversarial scenario canonicalization changed")
        except DashboardScenarioError:
            raise P8AuditError("P8 adversarial scenario failed validation") from None


def _audit_published_artifacts(published_artifacts, renderer_identity, loaded_by_symbol):
    if (
        not isinstance(published_artifacts, dict)
        or set(published_artifacts) != set(SYMBOLS)
    ):
        raise P8AuditError("Published Dashboard artifact set is incomplete")

    identities = {}
    for symbol in SYMBOLS:
        data = _read_regular_file(
            published_artifacts[symbol],
            MAX_DASHBOARD_BYTES,
            "Published Dashboard",
        )
        expected = renderer_identity[symbol]
        if (
            len(data) != expected["bytes"]
            or _sha256(data) != expected["dashboard_sha256"]
            or not data.startswith(b"<!doctype html>\n<html lang=\"en\">")
            or b"Content-Security-Policy" not in data
            or loaded_by_symbol[symbol].export_sha256 != EXPECTED_EXPORTS[symbol]
        ):
            raise P8AuditError("Published Dashboard artifact differs from renderer")
        lowered = data.lower()
        forbidden = (
            b"<script",
            b"<img",
            b"<iframe",
            b"<link",
            b" src=",
            b" href=",
            b"fetch(",
            b"websocket",
            b"localstorage",
            b"document.cookie",
        )
        if any(value in lowered for value in forbidden):
            raise P8AuditError("Published Dashboard contains remote or executable material")
        identities[symbol] = {
            "bytes": len(data),
            "dashboard_sha256": _sha256(data),
            "view_model_sha256": expected["view_model_sha256"],
        }
    return identities


def _audit_source_safety():
    production_files = (
        "contracts.py",
        "loader.py",
        "overview.py",
        "trade_table.py",
        "performance_views.py",
        "quality_view.py",
        "renderer.py",
        "cli.py",
        "scenarios.py",
        "audit.py",
    )
    forbidden = (
        ("from yatl." + "analytics"),
        ("import yatl." + "analytics"),
        ("from yatl." + "execution"),
        ("import yatl." + "execution"),
        ("from yatl." + "account"),
        ("import yatl." + "account"),
        ("from yatl." + "risk"),
        ("import yatl." + "risk"),
        ("sqlite" + "3"),
        ("local_" + "paper"),
        ("analyst_" + "journal"),
        ("url" + "lib"),
        ("http." + "client"),
        ("req" + "uests"),
        ("http" + "x"),
        ("aio" + "http"),
        ("web" + "sockets"),
        ("open" + "ai"),
        ("anth" + "ropic"),
        ("os." + "getenv"),
        ("os." + "environ"),
        ("/api/v3/" + "order"),
        ("/f" + "api"),
        ("/d" + "api"),
        ("with" + "draw("),
    )
    try:
        root = Path(__file__).parent
        for name in production_files:
            text = (root / name).read_text(encoding="utf-8").casefold()
            if any(value in text for value in forbidden):
                raise P8AuditError("P8 source safety boundary failed")
    except P8AuditError:
        raise
    except OSError:
        raise P8AuditError("P8 source safety scan failed") from None
    return True


@dataclass(frozen=True, slots=True)
class P8AuditResult:
    symbols: int
    scenarios: int
    runs: int
    files: int
    published_artifacts: int
    policy_sha256: str
    index_sha256: str
    export_set_sha256: str
    renderer_set_sha256: str
    exact_outcomes: bool
    replay_equal: bool
    projections_recomputed: bool
    renderer_recomputed: bool
    artifacts_verified: bool
    no_write: bool
    source_safe: bool

    def __post_init__(self):
        if (
            (self.symbols, self.scenarios, self.runs, self.files)
            != (2, 9, 18, 19)
            or self.published_artifacts != 2
            or self.policy_sha256 != EXPECTED_POLICY_SHA256
            or self.index_sha256 != EXPECTED_INDEX_SHA256
            or self.export_set_sha256 != EXPECTED_EXPORT_SET_SHA256
            or not _valid_sha(self.renderer_set_sha256)
            or self.exact_outcomes is not True
            or self.replay_equal is not True
            or self.projections_recomputed is not True
            or self.renderer_recomputed is not True
            or self.artifacts_verified is not True
            or self.no_write is not True
            or self.source_safe is not True
        ):
            raise P8AuditError("P8 final audit result is inconsistent")


def audit_p8(export_paths, evidence_dir, published_artifacts):
    """Independently recompute P8 and compare source, views, renderer and evidence."""

    try:
        policy_sha = _policy_sha256()
        source_safe = _audit_source_safety()
        fixtures, loaded, renderer_identity, export_set_sha = _load_exports(export_paths)

        replay = run_adversarial_dashboard_matrix(fixtures)
        replay_again = run_adversarial_dashboard_matrix(fixtures)
        if (
            replay != replay_again
            or _sha256(replay.index_json) != EXPECTED_INDEX_SHA256
        ):
            raise P8AuditError("P8 deterministic adversarial replay changed")
        expected_evidence = _expected_evidence(replay)

        evidence, records = _read_evidence(evidence_dir)
        _audit_evidence_records(records)
        if evidence != expected_evidence:
            raise P8AuditError("P8 published evidence differs from deterministic replay")

        published = _audit_published_artifacts(
            published_artifacts,
            renderer_identity,
            loaded,
        )
        renderer_set_sha = _sha256(_compact_json(published))

        return P8AuditResult(
            symbols=len(SYMBOLS),
            scenarios=len(SCENARIOS),
            runs=len(replay.runs),
            files=len(evidence),
            published_artifacts=len(published),
            policy_sha256=policy_sha,
            index_sha256=_sha256(evidence["p8-009-index.json"]),
            export_set_sha256=export_set_sha,
            renderer_set_sha256=renderer_set_sha,
            exact_outcomes=True,
            replay_equal=True,
            projections_recomputed=True,
            renderer_recomputed=True,
            artifacts_verified=True,
            no_write=True,
            source_safe=source_safe,
        )
    except P8AuditError:
        raise
    except (
        DashboardScenarioError,
        P7ExportLoadError,
        QualityDiagnosticProjectionError,
        OverviewProjectionError,
        TradeTableProjectionError,
        PerformanceViewProjectionError,
        DashboardRenderError,
        TypeError,
        ValueError,
    ):
        raise P8AuditError("P8 independent final audit failed safely") from None
