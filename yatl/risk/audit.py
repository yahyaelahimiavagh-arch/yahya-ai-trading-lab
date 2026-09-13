"""Independent fail-closed acceptance audit for the complete P4 framework."""

import hashlib
import json
import re
from dataclasses import dataclass, fields
from pathlib import Path

from yatl.data import AuditError, SYMBOLS, audit_p1_manifest

from .contracts import POLICY_ID, RiskPolicy
from .scenarios import (
    SCENARIOS,
    RiskScenarioError,
    run_adversarial_scenario_matrix,
    scenario_artifact_json,
)


EXPECTED_INDEX_SHA256 = (
    "56c945c38571af294bb44bfd7e788f314d9ee3e9fc76457c6bedb018daae0783"
)
EXPECTED_POLICY_SHA256 = (
    "cb72fffad317e05638e60ad4a93b96bb78e356b52677330ecd6149095b65e2c7"
)
MAX_EVIDENCE_FILE_BYTES = 2 * 1024 * 1024
MAX_EVIDENCE_TOTAL_BYTES = 34 * 1024 * 1024
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


class P4AuditError(Exception):
    """P4 evidence, replay or safety policy is incomplete or inconsistent."""


@dataclass(frozen=True, slots=True)
class P4AuditResult:
    symbols: int
    scenarios: int
    runs: int
    files: int
    index_sha256: str
    policy_sha256: str
    exact_decisions: bool
    replay_equal: bool

    def __post_init__(self):
        if (
            (self.symbols, self.scenarios, self.runs, self.files)
            != (2, 8, 16, 17)
            or self.index_sha256 != EXPECTED_INDEX_SHA256
            or self.policy_sha256 != EXPECTED_POLICY_SHA256
            or self.exact_decisions is not True
            or self.replay_equal is not True
        ):
            raise P4AuditError("P4 audit result is inconsistent")


def _json(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ) + "\n"


def _sha256(value):
    payload = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(payload).hexdigest()


def _policy_sha256():
    policy = RiskPolicy()
    record = {item.name: getattr(policy, item.name) for item in fields(policy)}
    digest = _sha256(_json(record))
    if digest != EXPECTED_POLICY_SHA256:
        raise P4AuditError("Frozen P4 policy digest changed")
    return digest


def _filename(symbol, scenario):
    return f"{symbol.lower()}-{scenario.lower().replace('_', '-')}.json"


def _expected_files(result):
    files = {"p4-009-index.json": result.index_json}
    for item in result.runs:
        files[_filename(item.symbol, item.name)] = item.artifact_json
    if len(files) != 17:
        raise P4AuditError("P4 evidence file coverage is incomplete")
    return files


def _decode_canonical(name, payload):
    try:
        text = payload.decode("utf-8")
        record = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise P4AuditError(f"P4 evidence JSON is invalid ({name})") from None
    if not isinstance(record, dict) or _json(record) != text:
        raise P4AuditError(f"P4 evidence JSON is noncanonical ({name})")
    lowered = text.lower()
    forbidden = (
        '"api_key"', '"api_secret"', '"password"', '"credential"',
        '"database_path"', '"manifest_path"', '"broker"',
    )
    if any(value in lowered for value in forbidden):
        raise P4AuditError(f"P4 evidence contains forbidden material ({name})")
    return text, record


def _read_evidence(directory):
    target = (
        Path(directory)
        if isinstance(directory, (str, Path)) and str(directory)
        else None
    )
    if target is None or not target.is_dir() or target.is_symlink():
        raise P4AuditError("P4 evidence directory is invalid")
    expected_names = {"p4-009-index.json"} | {
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
            raise P4AuditError("P4 evidence directory contents are invalid")
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
                raise P4AuditError("P4 evidence size is invalid")
            before[path.name] = payload
        after = {path.name: path.read_bytes() for path in paths}
    except P4AuditError:
        raise
    except OSError:
        raise P4AuditError("P4 evidence cannot be read safely") from None
    if before != after:
        raise P4AuditError("P4 evidence changed during audit")
    decoded = {}
    records = {}
    for name, payload in before.items():
        decoded[name], records[name] = _decode_canonical(name, payload)
    return decoded, records


def _require_hashes(record, names):
    if any(
        not isinstance(record.get(name), str)
        or SHA256_PATTERN.fullmatch(record[name]) is None
        for name in names
    ):
        raise P4AuditError("P4 scenario digest evidence is invalid")


def _base_decision(observed, *, active, disposition, reason, outcome, fills):
    if (
        observed.get("kill_switch_active") is not active
        or observed.get("risk_disposition") != disposition
        or observed.get("risk_reason") != reason
        or observed.get("adapter_outcome") != outcome
        or observed.get("fills") != fills
        or observed.get("atomic_state_preserved") is not True
    ):
        raise P4AuditError("P4 exact scenario decision changed")


def _audit_exact_decision(record):
    required_flags = {
        "schema_version": 1,
        "policy_id": POLICY_ID,
        "source": "BINANCE_SPOT_PUBLIC_CLOSED_OHLCV",
        "passed": True,
        "paper_only": True,
        "live_master_lock": "OFF",
        "spot_only": True,
        "allow_short": False,
        "allow_leverage": False,
        "trade_permission": False,
        "exchange_order_submission": False,
    }
    if any(record.get(name) != value for name, value in required_flags.items()):
        raise P4AuditError("P4 scenario safety boundary changed")
    _require_hashes(record, ("dataset_sha256", "context_sha256", "result_sha256"))
    observed = record.get("observed")
    if not isinstance(observed, dict):
        raise P4AuditError("P4 observed scenario evidence is invalid")
    _require_hashes(observed, ("circuit_sha256", "kill_switch_state_sha256"))
    if observed.get("authorization_sha256") is not None:
        _require_hashes(observed, ("authorization_sha256",))

    scenario = record.get("scenario")
    boundaries = {
        "SESSION_LOSS_BOUNDARY": "SESSION_LOSS_LIMIT",
        "LOSS_STREAK_BOUNDARY": "CONSECUTIVE_LOSS_LIMIT",
        "DRAWDOWN_BOUNDARY": "DRAWDOWN_LIMIT",
    }
    if scenario in boundaries:
        _base_decision(
            observed, active=True, disposition="REJECT",
            reason="KILL_SWITCH_ACTIVE", outcome="ENTRY_BLOCKED", fills=[],
        )
        if observed.get("triggered_breakers") != [boundaries[scenario]]:
            raise P4AuditError("P4 boundary breaker changed")
    elif scenario == "POST_COST_REJECTION":
        _base_decision(
            observed, active=False, disposition="REJECT",
            reason="PENDING_RISK_EVALUATION", outcome="ENTRY_BLOCKED", fills=[],
        )
        if observed.get("protective_status") != "REJECT":
            raise P4AuditError("P4 post-cost rejection changed")
        _require_hashes(observed, ("protective_sha256",))
    elif scenario == "INSUFFICIENT_EVIDENCE":
        _base_decision(
            observed, active=False, disposition="REJECT",
            reason="EVIDENCE_NOT_QUALIFIED", outcome="ENTRY_BLOCKED", fills=[],
        )
    elif scenario == "GAP_FAIL_CLOSED":
        fills = observed.get("fills")
        _base_decision(
            observed, active=False, disposition="APPROVE_PAPER",
            reason="RISK_CHECKS_PASSED", outcome="ENTRY_APPROVED", fills=fills,
        )
        if (
            not isinstance(fills, list)
            or len(fills) != 1
            or fills[0].get("quantity") != observed.get("approved_quantity")
            or observed.get("gap_failure")
            != "P2_REJECTED_MISSING_EXPECTED_FILL_CANDLE"
            or observed.get("retry_succeeded") is not True
        ):
            raise P4AuditError("P4 gap fail-closed decision changed")
    elif scenario == "STALE_STATE_REJECTION":
        if (
            observed.get("stale_failure") != "LATEST_CIRCUIT_NOT_CONSUMED"
            or observed.get("atomic_state_preserved") is not True
            or observed.get("authorization_sha256") is not None
            or observed.get("risk_disposition") is not None
            or observed.get("adapter_outcome") is not None
            or observed.get("fills") != []
        ):
            raise P4AuditError("P4 stale-state rejection changed")
    elif scenario == "KILL_SWITCH_EXIT":
        fills = observed.get("fills")
        if (
            observed.get("kill_switch_active") is not True
            or observed.get("risk_disposition") != "APPROVE_PAPER"
            or observed.get("risk_reason") != "EXIT_REDUCES_RISK"
            or observed.get("adapter_outcome") != "EXIT_APPROVED"
            or not isinstance(fills, list)
            or len(fills) != 1
            or fills[0].get("quantity") != observed.get("approved_quantity")
            or observed.get("final_position_flat") is not True
            or not isinstance(observed.get("entry_fills"), list)
            or len(observed["entry_fills"]) != 1
        ):
            raise P4AuditError("P4 Kill Switch exit decision changed")
        _require_hashes(observed, ("entry_authorization_sha256",))
    else:
        raise P4AuditError("P4 scenario identity changed")


def _audit_records(records):
    index = records.get("p4-009-index.json")
    if not isinstance(index, dict):
        raise P4AuditError("P4 scenario index is invalid")
    expected_order = [
        (symbol, scenario)
        for symbol in SYMBOLS
        for scenario in SCENARIOS
    ]
    runs = index.get("runs")
    if (
        index.get("symbols") != list(SYMBOLS)
        or index.get("scenarios") != list(SCENARIOS)
        or not isinstance(runs, list)
        or [(item.get("symbol"), item.get("scenario")) for item in runs]
        != expected_order
    ):
        raise P4AuditError("P4 scenario index coverage or order changed")
    for item in runs:
        name = item.get("file")
        if (
            not isinstance(name, str)
            or item.get("passed") is not True
            or item.get("replay_equal") is not True
            or SHA256_PATTERN.fullmatch(str(item.get("sha256"))) is None
            or name not in records
        ):
            raise P4AuditError("P4 scenario index reference is invalid")
        text = _json(records[name])
        if item["sha256"] != _sha256(text):
            raise P4AuditError("P4 scenario file digest changed")
        try:
            if scenario_artifact_json(records[name]) != text:
                raise P4AuditError("P4 scenario artifact changed")
        except RiskScenarioError:
            raise P4AuditError("P4 scenario artifact failed validation") from None
        _audit_exact_decision(records[name])


def _audit_source_safety():
    forbidden = (
        ("/api/v3/" + "order"), ("f" + "api"), ("d" + "api"),
        ("with" + "draw("), ("from yatl." + "account"),
        ("import yatl." + "account"),
    )
    try:
        for path in Path(__file__).parent.glob("*.py"):
            text = path.read_text(encoding="utf-8").lower()
            if any(value in text for value in forbidden):
                raise P4AuditError("P4 source safety boundary failed")
    except OSError:
        raise P4AuditError("P4 source safety scan failed") from None


def audit_p4(
    database_path="data/p1/market.sqlite3",
    manifest_path="manifests/p1-market-data.json",
    evidence_dir="data/p4/p4-009-evidence",
):
    """Recompute P4 and compare all accepted evidence byte-for-byte."""
    try:
        audit_p1_manifest(manifest_path)
        _audit_source_safety()
        policy_sha256 = _policy_sha256()
        replay = run_adversarial_scenario_matrix(database_path, manifest_path)
        expected = _expected_files(replay)
        if _sha256(replay.index_json) != EXPECTED_INDEX_SHA256:
            raise P4AuditError("P4 accepted-data replay changed")
        evidence, records = _read_evidence(evidence_dir)
        _audit_records(records)
        if evidence != expected:
            raise P4AuditError("P4 evidence differs from deterministic replay")
        index_sha256 = _sha256(evidence["p4-009-index.json"])
        return P4AuditResult(
            symbols=len(SYMBOLS), scenarios=len(SCENARIOS),
            runs=len(replay.runs), files=len(evidence),
            index_sha256=index_sha256, policy_sha256=policy_sha256,
            exact_decisions=True, replay_equal=True,
        )
    except P4AuditError:
        raise
    except (AuditError, RiskScenarioError, TypeError, ValueError):
        raise P4AuditError("P4 final acceptance audit failed safely") from None
