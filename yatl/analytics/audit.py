"""Independent fail-closed final acceptance audit for the complete P7 framework."""

import argparse
import hashlib
import json
import re
from dataclasses import dataclass, fields
from pathlib import Path
from tempfile import TemporaryDirectory

from .cli import ANALYTICS_EXPORT_SCHEMA_VERSION
from .contracts import AnalyticsPolicy, StrategyEvidenceState, SYMBOLS
from .ingestion import AnalyticsIngestionError, ingest_readonly_sources
from .metrics import PerformanceMetricsError, calculate_performance_metrics
from .quality import QualityStatus, run_quality_gate
from .scenarios import (
    SCENARIOS,
    AnalyticsScenarioError,
    _fixture,
    run_adversarial_analytics_matrix,
)
from .segmentation import SegmentationError, build_segmentation
from .timeline import TimelineError, build_unified_timeline
from .trades import TradeReconstructionError, reconstruct_paper_trades


EXPECTED_INDEX_SHA256 = (
    "f13a322e7071b48a8b05182fceee8024ee6d22d6b08a7b223d337e5f7850e60b"
)
EXPECTED_POLICY_SHA256 = (
    "534fb28e630a8bca4ccffd4c8ef572f4aac440d4a3d05de190cf70264ac9f4d9"
)
# Frozen after the first independent P7-010 candidate run and then required.
EXPECTED_CHAIN_SET_SHA256 = ""

EXPECTED_BTC_CHAIN = {
    "manifest_sha256":
        "aff65af16c41cb684c13b8c3504532c0975cfdd7b4c6a632076c10adcf7feab3",
    "timeline_sha256":
        "c0738c02733a76b37d47e05031ae306f98aef6d72079324688477facf4bed311",
    "reconstruction_sha256":
        "2162b742d014f9cb00dd959fae04309a7aaa6824cdd65e79037166c5c384ecab",
    "metrics_sha256":
        "d2aa2ad3cf2b29aef0eb5ce1db21fb1dfda6ebeef2dfa142d61bda815f6b3dbb",
    "segmentation_sha256":
        "be0a03a702b4b672e912c54435a37ce6c2b910f0cf0cd40e147ccfed4eefcba0",
    "quality_sha256":
        "2c62a387c8ad24535eb9c4a2bd828d05ef6a8269cdd4529d261544c991e39a07",
    "export_sha256":
        "8e11935814a57389399eea4046beed2f98b7bb448b25465740ef868f7e4dc456",
}

EXPECTED_UPSTREAM_IDENTITIES = {
    "p3_index_sha256":
        "59f0af64843baeb2ecf593142e3247be190bb24c8768de80dd971bc677d8e92a",
    "p4_index_sha256":
        "56c945c38571af294bb44bfd7e788f314d9ee3e9fc76457c6bedb018daae0783",
    "p4_policy_sha256":
        "cb72fffad317e05638e60ad4a93b96bb78e356b52677330ecd6149095b65e2c7",
    "p5_index_sha256":
        "7e90d6d39fde707b1fc1f0504ec96d3d537863c9a1042d757d3437ccc41690fa",
    "p5_policy_sha256":
        "d3a7edcad7027c215093d6cc0e11d90d194fda8f918c1e27fdbdd4bba5b98b72",
    "p6_index_sha256":
        "a5a09bdde1600c706bdc3665b46f334ae04fd5fc4fe364613cc9ed7913018524",
    "p6_policy_sha256":
        "355ad5a2ed274878db4c9a56e15b14548ee6ba0c16016c7cc3b04b02120bbe44",
    "p6_evidence_sha256":
        "93dd09b73d439ed60b781f38783f2fb716689210ad66fb7ed5a395ed7b5b5f0f",
}

MAX_EVIDENCE_FILE_BYTES = 1024 * 1024
MAX_EVIDENCE_TOTAL_BYTES = 24 * 1024 * 1024
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


class P7AuditError(Exception):
    """P7 evidence, replay, analytics chain or safety policy is inconsistent."""


@dataclass(frozen=True, slots=True)
class P7AuditResult:
    symbols: int
    scenarios: int
    runs: int
    files: int
    index_sha256: str
    policy_sha256: str
    chain_set_sha256: str
    exact_outcomes: bool
    replay_equal: bool
    chain_recomputed: bool
    no_write: bool
    source_safe: bool

    def __post_init__(self):
        if (
            (self.symbols, self.scenarios, self.runs, self.files)
            != (2, 9, 18, 19)
            or self.index_sha256 != EXPECTED_INDEX_SHA256
            or self.policy_sha256 != EXPECTED_POLICY_SHA256
            or SHA256_PATTERN.fullmatch(self.chain_set_sha256) is None
            or (
                EXPECTED_CHAIN_SET_SHA256
                and self.chain_set_sha256 != EXPECTED_CHAIN_SET_SHA256
            )
            or self.exact_outcomes is not True
            or self.replay_equal is not True
            or self.chain_recomputed is not True
            or self.no_write is not True
            or self.source_safe is not True
        ):
            raise P7AuditError("P7 audit result is inconsistent")


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


def _policy_sha256():
    policy = AnalyticsPolicy()
    record = {
        "schema_version": 1,
        "policy": {
            item.name: getattr(policy, item.name)
            for item in fields(policy)
        },
    }
    digest = _sha256(_compact_json(record))
    if digest != EXPECTED_POLICY_SHA256:
        raise P7AuditError("Frozen P7 analytics policy digest changed")
    if (
        policy.descriptive_only is not True
        or policy.paper_only is not True
        or policy.live_master_lock != "OFF"
        or policy.allow_short is not False
        or policy.allow_margin is not False
        or policy.allow_futures is not False
        or policy.allow_leverage is not False
        or policy.allow_withdrawal is not False
        or policy.allow_external_transport is not False
        or policy.allow_credentials is not False
        or policy.allow_upstream_mutation is not False
        or policy.allow_execution_import is not False
        or policy.allow_risk_authorization_mutation is not False
        or policy.allow_quantity_authority is not False
        or policy.allow_trade_permission is not False
        or policy.allow_order_endpoint is not False
        or policy.allow_ai_direct_execution is not False
        or policy.allow_strategy_evidence_upgrade is not False
    ):
        raise P7AuditError("P7 analytics policy safety boundary changed")
    return digest


def _filename(symbol, scenario):
    return f"{symbol.lower()}-{scenario.lower().replace('_', '-')}.json"


def _expected_files(result):
    files = {"p7-009-index.json": result.index_json}
    for item in result.runs:
        files[_filename(item.symbol, item.name)] = item.artifact_json
    if len(files) != 19:
        raise P7AuditError("P7 evidence file coverage is incomplete")
    return files


def _decode_canonical(name, payload):
    try:
        text = payload.decode("utf-8")
        record = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise P7AuditError(f"P7 evidence JSON is invalid ({name})") from None
    if not isinstance(record, dict) or _json(record) != text:
        raise P7AuditError(f"P7 evidence JSON is noncanonical ({name})")
    lowered = text.casefold()
    forbidden = (
        ('"api_' + 'key"'),
        ('"api_' + 'secret"'),
        '"password"',
        '"credential"',
        '"endpoint_url"',
        '"raw_response"',
        '"canonical_response_json"',
        '"database_path"',
        '"private_key"',
        '"account_id"',
        '"risk_authorization"',
        '"approved_quantity"',
        '"order_request"',
        "traceback",
        "select ",
        "update ",
        "insert ",
        "delete ",
    )
    if any(value in lowered for value in forbidden):
        raise P7AuditError(f"P7 evidence contains forbidden material ({name})")
    return text, record


def _read_evidence(directory):
    target = (
        Path(directory)
        if isinstance(directory, (str, Path)) and str(directory)
        else None
    )
    if target is None or not target.is_dir() or target.is_symlink():
        raise P7AuditError("P7 evidence directory is invalid")
    expected_names = {"p7-009-index.json"} | {
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
            raise P7AuditError("P7 evidence directory contents are invalid")
        before = {}
        total = 0
        for path in paths:
            payload = path.read_bytes()
            total += len(payload)
            if (
                not payload
                or len(payload) > MAX_EVIDENCE_FILE_BYTES
                or total > MAX_EVIDENCE_TOTAL_BYTES
            ):
                raise P7AuditError("P7 evidence size is invalid")
            before[path.name] = payload
        after = {path.name: path.read_bytes() for path in paths}
    except P7AuditError:
        raise
    except OSError:
        raise P7AuditError("P7 evidence cannot be read safely") from None
    if before != after:
        raise P7AuditError("P7 evidence changed during audit")

    decoded = {}
    records = {}
    for name, payload in before.items():
        decoded[name], records[name] = _decode_canonical(name, payload)
    return decoded, records


def _required_safety(record):
    fixed = {
        "schema_version": 1,
        "artifact_kind": "YATL_P7_ADVERSARIAL_ANALYTICS_SCENARIO",
        "passed": True,
        "accepted_upstream_identities": EXPECTED_UPSTREAM_IDENTITIES,
        "strategy_evidence": "INSUFFICIENT_EVIDENCE",
        "paper_only": True,
        "read_only_analytics": True,
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
        "partial_publication_on_failure": False,
    }
    if any(record.get(name) != value for name, value in fixed.items()):
        raise P7AuditError("P7 scenario safety boundary changed")


def _audit_quality_failure(record, code, component):
    expected = record.get("expected")
    observed = record.get("observed")
    expected_base = {
        "quality_code": code,
        "publication_allowed": False,
    }
    if record.get("scenario") == "CHANGED_COST_EQUITY_TOTALS":
        expected_base["fabricated_totals_accepted"] = False
    elif record.get("scenario") == "FABRICATED_PROFITABILITY":
        expected_base["fabricated_profitability_accepted"] = False
    elif record.get("scenario") == "SCHEMA_SMUGGLING":
        expected_base["schema_smuggling_accepted"] = False
    if expected != expected_base:
        raise P7AuditError("P7 quality scenario expectation changed")

    if observed != {
        "stage": "QUALITY",
        "status": "FAIL",
        "publication_allowed": False,
        "diagnostics": [{"code": code, "component": component}],
        "accepted_chain_present": False,
        "analytics_payload_present": False,
    }:
        raise P7AuditError("P7 quality scenario exact outcome changed")


def _audit_exact_outcome(record):
    _required_safety(record)
    symbol = record.get("symbol")
    scenario = record.get("scenario")
    if symbol not in SYMBOLS or scenario not in SCENARIOS:
        raise P7AuditError("P7 scenario identity changed")
    expected = record.get("expected")
    observed = record.get("observed")
    if not isinstance(expected, dict) or not isinstance(observed, dict):
        raise P7AuditError("P7 scenario outcome material is invalid")

    material = dict(record)
    digest = material.pop("result_sha256", None)
    if (
        not isinstance(digest, str)
        or SHA256_PATTERN.fullmatch(digest) is None
        or digest != _sha256(_json(material))
    ):
        raise P7AuditError("P7 scenario result digest changed")

    quality = {
        "UPSTREAM_TAMPERING": ("UPSTREAM_DIGEST_CHANGED", "SOURCE"),
        "DUPLICATE_ORPHAN_FILL": ("ORPHAN_RELATIONSHIP", "TIMELINE"),
        "CROSS_SYMBOL_LINKAGE": ("SOURCE_IDENTITY_INVALID", "TIMELINE"),
        "FUTURE_TIMESTAMP": ("FUTURE_TIMESTAMP", "SOURCE"),
        "CHANGED_COST_EQUITY_TOTALS": ("INCONSISTENT_TOTALS", "TRADES"),
        "FABRICATED_PROFITABILITY": ("INCONSISTENT_TOTALS", "TRADES"),
        "SCHEMA_SMUGGLING": ("ANALYTICS_CHAIN_INVALID", "SOURCE"),
    }
    if scenario in quality:
        _audit_quality_failure(record, *quality[scenario])
        return

    if scenario == "EVIDENCE_LABEL_UPGRADE":
        if expected != {
            "code": "EVIDENCE_LABEL_UPGRADE_REJECTED",
            "strategy_evidence": "INSUFFICIENT_EVIDENCE",
            "publication_allowed": False,
        } or observed != {
            "stage": "SEGMENTATION",
            "code": "EVIDENCE_LABEL_UPGRADE_REJECTED",
            "strategy_evidence": "INSUFFICIENT_EVIDENCE",
            "publication_allowed": False,
        }:
            raise P7AuditError("P7 evidence-label upgrade outcome changed")
        return

    if scenario == "JOURNAL_MUTATION":
        if expected != {
            "code": "READ_ONLY_MUTATION_REJECTED",
            "no_write": True,
            "quality_after_attempt": "PASS",
        } or observed != {
            "stage": "READ_ONLY_SOURCE",
            "code": "READ_ONLY_MUTATION_REJECTED",
            "no_write": True,
            "quality_after_attempt": "PASS",
        }:
            raise P7AuditError("P7 read-only mutation outcome changed")
        return

    raise P7AuditError("P7 scenario identity is unsupported")


def _audit_records(records):
    index = records.get("p7-009-index.json")
    if not isinstance(index, dict):
        raise P7AuditError("P7 scenario index is invalid")
    expected_order = [
        (symbol, scenario)
        for symbol in SYMBOLS
        for scenario in SCENARIOS
    ]
    fixed_index = {
        "schema_version": 1,
        "artifact_kind": "YATL_P7_ADVERSARIAL_ANALYTICS_MATRIX",
        "symbols": list(SYMBOLS),
        "scenarios": list(SCENARIOS),
        "accepted_upstream_identities": EXPECTED_UPSTREAM_IDENTITIES,
        "strategy_evidence": "INSUFFICIENT_EVIDENCE",
        "paper_only": True,
        "read_only_analytics": True,
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
        "partial_publication_on_failure": False,
    }
    if any(index.get(name) != value for name, value in fixed_index.items()):
        raise P7AuditError("P7 scenario index safety boundary changed")
    runs = index.get("runs")
    if (
        not isinstance(runs, list)
        or [(item.get("symbol"), item.get("scenario")) for item in runs]
        != expected_order
    ):
        raise P7AuditError("P7 scenario index coverage or order changed")

    for item in runs:
        name = item.get("file")
        digest = item.get("sha256")
        if (
            not isinstance(name, str)
            or item.get("passed") is not True
            or item.get("replay_equal") is not True
            or not isinstance(digest, str)
            or SHA256_PATTERN.fullmatch(digest) is None
            or name not in records
        ):
            raise P7AuditError("P7 scenario index reference is invalid")
        text = _json(records[name])
        if digest != _sha256(text):
            raise P7AuditError("P7 scenario file digest changed")
        _audit_exact_outcome(records[name])


def _source_file_sha(path):
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        raise P7AuditError("P7 audit fixture source cannot be read") from None


def _export_sha256(gate, segmentation):
    if (
        gate.report.status is not QualityStatus.PASS
        or gate.accepted_segmentation != segmentation
    ):
        raise P7AuditError("P7 accepted export source differs from quality gate")
    material = {
        "schema_version": ANALYTICS_EXPORT_SCHEMA_VERSION,
        "quality": gate.report.as_record(),
        "analytics": segmentation.as_record(),
    }
    return _sha256(_compact_json(material))


def _chain_record(symbol):
    with TemporaryDirectory() as directory:
        root = Path(directory)
        _p5, _p6, specs = _fixture(root, symbol)
        before = tuple(
            _source_file_sha(item.database_path)
            for item in specs
        )

        first_manifest = ingest_readonly_sources(1_790_001_000_100, specs)
        first_timeline = build_unified_timeline(1_790_001_000_100, specs)
        first_reconstruction = reconstruct_paper_trades(
            1_790_001_000_100,
            specs,
        )
        first_metrics = calculate_performance_metrics(first_reconstruction)
        first_segmentation = build_segmentation(
            1_790_001_000_100,
            specs,
        )
        first_quality = run_quality_gate(1_790_001_000_100, specs)

        second_manifest = ingest_readonly_sources(1_790_001_000_100, specs)
        second_timeline = build_unified_timeline(1_790_001_000_100, specs)
        second_reconstruction = reconstruct_paper_trades(
            1_790_001_000_100,
            specs,
        )
        second_metrics = calculate_performance_metrics(second_reconstruction)
        second_segmentation = build_segmentation(
            1_790_001_000_100,
            specs,
        )
        second_quality = run_quality_gate(1_790_001_000_100, specs)

        after = tuple(
            _source_file_sha(item.database_path)
            for item in specs
        )
        if (
            before != after
            or first_manifest != second_manifest
            or first_timeline != second_timeline
            or first_reconstruction != second_reconstruction
            or first_metrics != second_metrics
            or first_segmentation != second_segmentation
            or first_quality != second_quality
            or first_quality.report.status is not QualityStatus.PASS
            or first_quality.accepted_segmentation != first_segmentation
            or first_metrics.symbol != symbol
            or first_metrics.completed_trade_count != 1
            or first_segmentation.symbol != symbol
            or len(first_segmentation.analyst_traces) != 1
            or first_metrics.strategy_evidence
            is not StrategyEvidenceState.INSUFFICIENT_EVIDENCE
            or first_segmentation.strategy_evidence
            is not StrategyEvidenceState.INSUFFICIENT_EVIDENCE
        ):
            raise P7AuditError("P7 accepted analytics chain replay changed")

        sources = {
            item.identity.source_kind.value: item
            for item in first_manifest.sources
        }
        if len(sources) != 2:
            raise P7AuditError("P7 accepted source coverage changed")
        record = {
            "symbol": symbol,
            "p5_database_sha256":
                sources["P5_EXECUTION_EVIDENCE"].database_sha256,
            "p5_canonical_sha256":
                sources["P5_EXECUTION_EVIDENCE"].canonical_sha256,
            "p6_database_sha256":
                sources["P6_ANALYST_TRACE"].database_sha256,
            "p6_canonical_sha256":
                sources["P6_ANALYST_TRACE"].canonical_sha256,
            "manifest_sha256": first_manifest.manifest_sha256,
            "timeline_sha256": first_timeline.timeline_sha256,
            "reconstruction_sha256":
                first_reconstruction.reconstruction_sha256,
            "metrics_sha256": first_metrics.metrics_sha256,
            "segmentation_sha256":
                first_segmentation.segmentation_sha256,
            "quality_sha256": first_quality.report.quality_sha256,
            "export_sha256":
                _export_sha256(first_quality, first_segmentation),
            "completed_trade_count": first_metrics.completed_trade_count,
            "analyst_trace_count": len(first_segmentation.analyst_traces),
            "strategy_evidence": "INSUFFICIENT_EVIDENCE",
            "replay_equal": True,
            "no_write": True,
        }

        for name, value in record.items():
            if name.endswith("_sha256") and SHA256_PATTERN.fullmatch(value) is None:
                raise P7AuditError("P7 accepted chain digest is invalid")

        if symbol == "BTCUSDT":
            for name, expected in EXPECTED_BTC_CHAIN.items():
                if record.get(name) != expected:
                    raise P7AuditError(
                        f"Frozen P7 BTC accepted chain changed ({name})"
                    )
        return record


def _chain_set_sha256():
    chains = tuple(_chain_record(symbol) for symbol in SYMBOLS)
    if tuple(item["symbol"] for item in chains) != tuple(SYMBOLS):
        raise P7AuditError("P7 accepted chain symbol coverage changed")
    digest = _sha256(_compact_json({
        "schema_version": 1,
        "chains": list(chains),
    }))
    if EXPECTED_CHAIN_SET_SHA256 and digest != EXPECTED_CHAIN_SET_SHA256:
        raise P7AuditError("Frozen P7 accepted chain-set digest changed")
    return digest, chains


def _audit_source_safety():
    forbidden = (
        ("/api/v3/" + "order"),
        ("/f" + "api"),
        ("/d" + "api"),
        ("with" + "draw("),
        ("from yatl." + "execution"),
        ("import yatl." + "execution"),
        ("from yatl." + "account"),
        ("import yatl." + "account"),
        ("from yatl." + "risk"),
        ("import yatl." + "risk"),
        ("from yatl." + "backtest"),
        ("import yatl." + "backtest"),
        ("os." + "getenv"),
        ("os." + "environ"),
        ("import " + "re" + "quests"),
        ("import " + "ht" + "tpx"),
        ("import " + "aio" + "http"),
        ("import " + "open" + "ai"),
        ("import " + "anth" + "ropic"),
        ("import " + "sub" + "process"),
    )
    try:
        for path in Path(__file__).parent.glob("*.py"):
            text = path.read_text(encoding="utf-8").casefold()
            if any(value in text for value in forbidden):
                raise P7AuditError("P7 source safety boundary failed")
    except OSError:
        raise P7AuditError("P7 source safety scan failed") from None
    return True


def audit_p7(evidence_dir="data/p7/p7-009-evidence"):
    """Independently recompute P7 and compare every accepted artifact exactly."""

    try:
        source_safe = _audit_source_safety()
        policy_sha256 = _policy_sha256()
        chain_set_sha256, _chains = _chain_set_sha256()

        replay = run_adversarial_analytics_matrix()
        if _sha256(replay.index_json) != EXPECTED_INDEX_SHA256:
            raise P7AuditError("P7 deterministic adversarial replay digest changed")
        expected = _expected_files(replay)

        evidence, records = _read_evidence(evidence_dir)
        _audit_records(records)
        if evidence != expected:
            raise P7AuditError("P7 evidence differs from deterministic replay")

        index_sha256 = _sha256(evidence["p7-009-index.json"])
        return P7AuditResult(
            symbols=len(SYMBOLS),
            scenarios=len(SCENARIOS),
            runs=len(replay.runs),
            files=len(evidence),
            index_sha256=index_sha256,
            policy_sha256=policy_sha256,
            chain_set_sha256=chain_set_sha256,
            exact_outcomes=True,
            replay_equal=True,
            chain_recomputed=True,
            no_write=True,
            source_safe=source_safe,
        )
    except P7AuditError:
        raise
    except (
        AnalyticsScenarioError,
        AnalyticsIngestionError,
        TimelineError,
        TradeReconstructionError,
        PerformanceMetricsError,
        SegmentationError,
        TypeError,
        ValueError,
    ):
        raise P7AuditError("P7 final acceptance audit failed safely") from None


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Independent final P7 analytics acceptance audit"
    )
    parser.add_argument(
        "--evidence",
        default="data/p7/p7-009-evidence",
    )
    args = parser.parse_args(argv)
    try:
        result = audit_p7(args.evidence)
    except P7AuditError as exc:
        print(f"FAIL: {exc}")
        return 1
    print(
        "OK: P7 independent final audit; "
        f"symbols={result.symbols} scenarios={result.scenarios} "
        f"runs={result.runs} files={result.files} "
        f"index_sha256={result.index_sha256} "
        f"policy_sha256={result.policy_sha256} "
        f"chain_set_sha256={result.chain_set_sha256} "
        "exact_outcomes=true replay_equal=true chain_recomputed=true "
        "no_write=true source_safe=true"
    )
    print(
        "PAPER ONLY | READ_ONLY_ANALYTICS | LIVE_MASTER_LOCK=OFF | "
        "INSUFFICIENT_EVIDENCE preserved | Accepted P3/P4/P5/P6 identities "
        "unchanged | No credentials | No provider/network | No executor import | "
        "No RiskAuthorization mutation | No quantity authority | "
        "No trade permission | No order endpoint | No AI direct execution"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
