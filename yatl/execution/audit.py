"""Independent fail-closed final acceptance audit for the complete P5 framework."""

import hashlib
import json
import re
from dataclasses import dataclass, fields
from pathlib import Path

from yatl.data import SYMBOLS

from .contracts import EXECUTION_POLICY_ID, LocalPaperExecutionPolicy
from .scenarios import (
    SCENARIOS,
    ExecutionScenarioError,
    run_adversarial_execution_matrix,
    scenario_artifact_json,
)


EXPECTED_INDEX_SHA256 = (
    "7e90d6d39fde707b1fc1f0504ec96d3d537863c9a1042d757d3437ccc41690fa"
)
EXPECTED_POLICY_SHA256 = (
    "d3a7edcad7027c215093d6cc0e11d90d194fda8f918c1e27fdbdd4bba5b98b72"
)
MAX_EVIDENCE_FILE_BYTES = 2 * 1024 * 1024
MAX_EVIDENCE_TOTAL_BYTES = 40 * 1024 * 1024
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


class P5AuditError(Exception):
    """P5 evidence, replay or safety policy is incomplete or inconsistent."""


@dataclass(frozen=True, slots=True)
class P5AuditResult:
    symbols: int
    scenarios: int
    runs: int
    files: int
    index_sha256: str
    policy_sha256: str
    exact_outcomes: bool
    replay_equal: bool
    source_safe: bool

    def __post_init__(self):
        if (
            (self.symbols, self.scenarios, self.runs, self.files)
            != (2, 9, 18, 19)
            or self.index_sha256 != EXPECTED_INDEX_SHA256
            or self.policy_sha256 != EXPECTED_POLICY_SHA256
            or self.exact_outcomes is not True
            or self.replay_equal is not True
            or self.source_safe is not True
        ):
            raise P5AuditError("P5 audit result is inconsistent")


def _json(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ) + "\n"


def _sha256(value):
    payload = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(payload).hexdigest()


def _policy_sha256():
    policy = LocalPaperExecutionPolicy()
    record = {item.name: getattr(policy, item.name) for item in fields(policy)}
    digest = _sha256(_json(record))
    if digest != EXPECTED_POLICY_SHA256:
        raise P5AuditError("Frozen P5 execution policy digest changed")
    return digest


def _filename(symbol, scenario):
    return f"{symbol.lower()}-{scenario.lower().replace('_', '-')}.json"


def _expected_files(result):
    files = {"p5-009-index.json": result.index_json}
    for item in result.runs:
        files[_filename(item.symbol, item.name)] = item.artifact_json
    if len(files) != 19:
        raise P5AuditError("P5 evidence file coverage is incomplete")
    return files


def _decode_canonical(name, payload):
    try:
        text = payload.decode("utf-8")
        record = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise P5AuditError(f"P5 evidence JSON is invalid ({name})") from None
    if not isinstance(record, dict) or _json(record) != text:
        raise P5AuditError(f"P5 evidence JSON is noncanonical ({name})")
    lowered = text.lower()
    forbidden = (
        ('"api_' + 'key"'),
        ('"api_' + 'secret"'),
        '"password"',
        '"credential"',
        '"database_path"',
        '"endpoint_url"',
        '"broker"',
        '"private_key"',
    )
    if any(value in lowered for value in forbidden):
        raise P5AuditError(f"P5 evidence contains forbidden material ({name})")
    return text, record


def _read_evidence(directory):
    target = (
        Path(directory)
        if isinstance(directory, (str, Path)) and str(directory)
        else None
    )
    if target is None or not target.is_dir() or target.is_symlink():
        raise P5AuditError("P5 evidence directory is invalid")
    expected_names = {"p5-009-index.json"} | {
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
            raise P5AuditError("P5 evidence directory contents are invalid")
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
                raise P5AuditError("P5 evidence size is invalid")
            before[path.name] = payload
        after = {path.name: path.read_bytes() for path in paths}
    except P5AuditError:
        raise
    except OSError:
        raise P5AuditError("P5 evidence cannot be read safely") from None
    if before != after:
        raise P5AuditError("P5 evidence changed during audit")
    decoded = {}
    records = {}
    for name, payload in before.items():
        decoded[name], records[name] = _decode_canonical(name, payload)
    return decoded, records


def _required_safety(record):
    fixed = {
        "schema_version": 1,
        "artifact_kind": "YATL_P5_ADVERSARIAL_EXECUTION_SCENARIO",
        "execution_policy_id": EXECUTION_POLICY_ID,
        "passed": True,
        "atomic_state_preserved": True,
        "engineering_fixture": True,
        "real_strategy_qualification": False,
        "paper_only": True,
        "live_master_lock": "OFF",
        "spot_only": True,
        "allow_short": False,
        "allow_leverage": False,
        "trade_permission": False,
        "exchange_order_submission": False,
        "ai_direct_execution": False,
    }
    if any(record.get(name) != value for name, value in fixed.items()):
        raise P5AuditError("P5 scenario safety boundary changed")


def _audit_exact_outcome(record):
    _required_safety(record)
    symbol = record.get("symbol")
    scenario = record.get("scenario")
    if symbol not in SYMBOLS or scenario not in SCENARIOS:
        raise P5AuditError("P5 scenario identity changed")
    expected = record.get("expected")
    observed = record.get("observed")
    if not isinstance(expected, dict) or not isinstance(observed, dict):
        raise P5AuditError("P5 scenario expected/observed evidence is invalid")
    if any(observed.get(key) != value for key, value in expected.items()):
        raise P5AuditError("P5 scenario observed outcome differs from expectation")

    if scenario == "DUPLICATE_INTENT":
        if (
            observed.get("intent_count") != 1
            or observed.get("duplicate_effect") is not False
            or SHA256_PATTERN.fullmatch(str(observed.get("journal_sha256"))) is None
        ):
            raise P5AuditError("P5 duplicate-intent outcome changed")
    elif scenario == "CRASH_ROLLBACK":
        if (
            observed.get("failure_rejected") is not True
            or observed.get("intent_count") != 0
        ):
            raise P5AuditError("P5 transactional rollback outcome changed")
    elif scenario == "STALE_AUTHORIZATION":
        if (
            observed.get("stale_rejected") is not True
            or observed.get("intent_count") != 1
            or observed.get("original_preserved") is not True
        ):
            raise P5AuditError("P5 stale-authorization outcome changed")
    elif scenario == "OUT_OF_ORDER_EVENT":
        if (
            observed.get("out_of_order_rejected") is not True
            or observed.get("event_count") != 1
            or observed.get("state_sequence") != 0
        ):
            raise P5AuditError("P5 out-of-order outcome changed")
    elif scenario == "JOURNAL_CORRUPTION":
        if observed != {
            "clean": "MATCH",
            "corrupt": "INTENT_INVALID",
            "ready": False,
        }:
            raise P5AuditError("P5 journal-corruption outcome changed")
    elif scenario == "SNAPSHOT_CORRUPTION":
        if observed != {"code": "SNAPSHOT_CORRUPT", "ready": False}:
            raise P5AuditError("P5 snapshot-corruption outcome changed")
    elif scenario == "MISSING_FILL_CANDLE":
        if observed != {
            "missing_candle_rejected": True,
            "has_position": False,
        }:
            raise P5AuditError("P5 missing-fill outcome changed")
    elif scenario == "COST_POLICY_MISMATCH":
        if observed != {
            "cost_mismatch_rejected": True,
            "has_position": False,
        }:
            raise P5AuditError("P5 cost-mismatch outcome changed")
    elif scenario == "UNCERTAIN_COMMIT":
        if observed != {
            "code": "AMBIGUOUS_COMMIT",
            "ready": False,
            "pending_preserved": True,
            "confirmation_available": True,
        }:
            raise P5AuditError("P5 uncertain-commit outcome changed")
    else:
        raise P5AuditError("P5 scenario identity is unsupported")


def _audit_records(records):
    index = records.get("p5-009-index.json")
    if not isinstance(index, dict):
        raise P5AuditError("P5 scenario index is invalid")
    expected_order = [
        (symbol, scenario)
        for symbol in SYMBOLS
        for scenario in SCENARIOS
    ]
    runs = index.get("runs")
    fixed_index = {
        "schema_version": 1,
        "artifact_kind": "YATL_P5_ADVERSARIAL_EXECUTION_MATRIX",
        "execution_policy_id": EXECUTION_POLICY_ID,
        "symbols": list(SYMBOLS),
        "scenarios": list(SCENARIOS),
        "paper_only": True,
        "live_master_lock": "OFF",
        "spot_only": True,
        "allow_short": False,
        "allow_leverage": False,
        "trade_permission": False,
        "exchange_order_submission": False,
        "ai_direct_execution": False,
    }
    if any(index.get(name) != value for name, value in fixed_index.items()):
        raise P5AuditError("P5 scenario index safety boundary changed")
    if (
        not isinstance(runs, list)
        or [(item.get("symbol"), item.get("scenario")) for item in runs]
        != expected_order
    ):
        raise P5AuditError("P5 scenario index coverage or order changed")
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
            raise P5AuditError("P5 scenario index reference is invalid")
        text = _json(records[name])
        if digest != _sha256(text):
            raise P5AuditError("P5 scenario file digest changed")
        try:
            if scenario_artifact_json(records[name]) != text:
                raise P5AuditError("P5 scenario artifact changed")
        except ExecutionScenarioError:
            raise P5AuditError("P5 scenario artifact failed validation") from None
        _audit_exact_outcome(records[name])


def _audit_source_safety():
    forbidden = (
        ("/api/v3/" + "order"),
        ("f" + "api"),
        ("d" + "api"),
        ("with" + "draw("),
        ("from yatl." + "account"),
        ("import yatl." + "account"),
        ("api_" + "key"),
        ("api_" + "secret"),
        ("os." + "getenv"),
        ("os." + "environ"),
    )
    try:
        for path in Path(__file__).parent.glob("*.py"):
            text = path.read_text(encoding="utf-8").lower()
            if any(value in text for value in forbidden):
                raise P5AuditError("P5 source safety boundary failed")
    except OSError:
        raise P5AuditError("P5 source safety scan failed") from None
    return True


def audit_p5(evidence_dir="data/p5/p5-009-evidence"):
    """Independently recompute P5 and compare every scenario artifact byte-for-byte."""
    try:
        source_safe = _audit_source_safety()
        policy_sha256 = _policy_sha256()
        replay = run_adversarial_execution_matrix()
        expected = _expected_files(replay)
        if _sha256(replay.index_json) != EXPECTED_INDEX_SHA256:
            raise P5AuditError("P5 deterministic replay digest changed")
        evidence, records = _read_evidence(evidence_dir)
        _audit_records(records)
        if evidence != expected:
            raise P5AuditError("P5 evidence differs from deterministic replay")
        index_sha256 = _sha256(evidence["p5-009-index.json"])
        return P5AuditResult(
            symbols=len(SYMBOLS),
            scenarios=len(SCENARIOS),
            runs=len(replay.runs),
            files=len(evidence),
            index_sha256=index_sha256,
            policy_sha256=policy_sha256,
            exact_outcomes=True,
            replay_equal=True,
            source_safe=source_safe,
        )
    except P5AuditError:
        raise
    except (ExecutionScenarioError, TypeError, ValueError):
        raise P5AuditError("P5 final acceptance audit failed safely") from None
