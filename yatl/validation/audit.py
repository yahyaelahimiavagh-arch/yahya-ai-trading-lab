"""Independent P10 final economic audit over accepted forward evidence.

This module recomputes the frozen candidate/gates/window identities, point-in-time
Paper run, economics, gate disposition and P10-009 adversarial matrix from the
accepted store/snapshot. It never promotes a Paper candidate into Live authority.
"""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from .cli import ValidationEvidenceBundle
from .economics import ForwardEconomicsError, calculate_forward_economics
from .forward_store import ForwardCandleStore, ForwardStoreError
from .gate import ForwardGateError, GateDisposition, evaluate_forward_gate
from .ingestion import ForwardIngestionSnapshot
from .paper_runner import ForwardPaperRunnerError, run_forward_paper
from .registration import CandidateFreeze, EconomicGateRegistry
from .scenarios import (
    MAX_ARTIFACT_BYTES,
    MAX_EVIDENCE_TOTAL_BYTES,
    SCENARIOS,
    ValidationScenarioError,
    accepted_validation_fixture,
    run_adversarial_validation_matrix,
    scenario_artifact_json,
    validation_matrix_sha256,
)
from .window import ForwardWindowSeal


EXPECTED_CANDIDATE_SHA256 = (
    "64f2e116616f84e09fbf70a19977395eac99b16fe7e24a283dd53a8b0b84ac86"
)
EXPECTED_GATE_REGISTRY_SHA256 = (
    "f8d706df050bb095219ae4b76e400eff73e1a7a6755c4a197d489b03117a3e95"
)
EXPECTED_WINDOW_SHA256 = (
    "115f72be7941f682ccd28a70058677eba2ea24ee8ed44b5380510fe685022867"
)
EXPECTED_CRITERIA = (
    "NET_PNL_AFTER_COSTS",
    "MAX_DRAWDOWN",
    "SAMPLE_SIZE",
    "CONSISTENCY",
    "REGIME_STABILITY",
    "FAILURE_RECOVERY",
    "RISK_CONTROLS",
)
FINAL_DISPOSITIONS = (
    GateDisposition.INSUFFICIENT_DATA.value,
    GateDisposition.FAIL.value,
    GateDisposition.PASS_CANDIDATE.value,
)
EXPECTED_EVIDENCE_FILES = 1 + len(SCENARIOS)
_HEX = frozenset("0123456789abcdef")


class P10AuditError(RuntimeError):
    """The final P10 chain or published adversarial evidence is inconsistent."""


def _compact(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _json(value):
    return _compact(value) + "\n"


def _sha256(value):
    if isinstance(value, str):
        payload = value.encode("utf-8")
    elif isinstance(value, bytes):
        payload = value
    else:
        payload = _compact(value).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _valid_sha(value):
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in _HEX for character in value)
    )


def _candidate_gate_window():
    candidate = CandidateFreeze()
    gates = EconomicGateRegistry()
    window = ForwardWindowSeal()
    if (
        candidate.candidate_sha256 != EXPECTED_CANDIDATE_SHA256
        or gates.registry_sha256 != EXPECTED_GATE_REGISTRY_SHA256
        or window.window_sha256 != EXPECTED_WINDOW_SHA256
        or window.candidate_sha256 != candidate.candidate_sha256
        or window.gate_registry_sha256 != gates.registry_sha256
        or tuple(item.value for item in gates.criteria) != EXPECTED_CRITERIA
        or gates.thresholds_mutable_after_window_open is not False
        or window.candidate_mutation_allowed is not False
        or window.gate_mutation_allowed is not False
        or window.lookahead_allowed is not False
        or window.future_only is not True
        or window.paper_only is not True
        or window.live_master_lock != "OFF"
        or window.p11_locked is not True
        or window.trade_permission is not False
        or window.order_endpoint is not False
        or window.ai_direct_execution is not False
    ):
        raise P10AuditError("Frozen P10 candidate/gate/window identity changed")
    return candidate, gates, window


def _dataset_digest(candles):
    return _sha256([item.as_record() for item in candles])


def _store_identity(store, snapshot):
    if (
        not isinstance(store, ForwardCandleStore)
        or type(snapshot) is not ForwardIngestionSnapshot
        or snapshot.quality_pass is not True
    ):
        raise P10AuditError("P10 audit source is not accepted forward evidence")

    records = []
    total = 0
    per_dataset = {}
    for evidence in snapshot.datasets:
        try:
            candles = store.candles_between(
                evidence.symbol,
                evidence.interval,
                evidence.requested_start_time_ms,
                evidence.requested_end_time_ms,
            )
        except ForwardStoreError:
            raise P10AuditError("P10 audit cannot reproduce forward dataset") from None
        digest = _dataset_digest(candles)
        if (
            len(candles) != evidence.total_rows
            or digest != evidence.dataset_sha256
        ):
            raise P10AuditError("P10 audit dataset differs from ingestion evidence")
        key = f"{evidence.symbol}:{evidence.interval}"
        per_dataset[key] = {
            "rows": len(candles),
            "dataset_sha256": digest,
        }
        total += len(candles)
        records.extend(
            {
                "symbol": evidence.symbol,
                "interval": evidence.interval,
                "candle": item.as_record(),
            }
            for item in candles
        )

    if total != store.count():
        raise P10AuditError("P10 store contains material outside accepted snapshot scope")
    return {
        "count": total,
        "content_sha256": _sha256(records),
        "datasets": per_dataset,
    }


def _paper_summary(run):
    return {
        "runner_id": run.runner_id,
        "run_sha256": run.run_sha256,
        "ingestion_snapshot_sha256": run.ingestion_snapshot_sha256,
        "window_sha256": run.window_sha256,
        "candidate_sha256": run.candidate_sha256,
        "gate_registry_sha256": run.gate_registry_sha256,
        "execution_policy_id": run.execution_policy_id,
        "fixed_research_quantity": run.fixed_research_quantity,
        "p3_adapter_git_blob_sha1": run.p3_adapter_git_blob_sha1,
        "symbols": [
            {
                "symbol": item.symbol,
                "result_sha256": item.result_sha256,
                "first_decision_time_ms": item.first_decision_time_ms,
                "end_time_ms": item.end_time_ms,
                "event_count": item.event_count,
                "entry_signals": item.entry_signals,
                "entries_allowed": item.entries_allowed,
                "entries_blocked": item.entries_blocked,
                "exit_signals": item.exit_signals,
                "no_trade_signals": item.no_trade_signals,
                "kill_switch_latched": item.kill_switch_latched,
                "fill_count": len(item.fills),
                "final_portfolio": item.final_portfolio,
                "point_in_time_verified": item.point_in_time_verified,
                "replay_from_start": item.replay_from_start,
            }
            for item in run.symbols
        ],
        "safety": run.as_record()["safety"],
    }


def _independent_audit_record(
    candidate,
    gates,
    window,
    snapshot,
    database_snapshot_sha256,
    run,
    economics,
    gate,
):
    material = {
        "schema_version": 1,
        "candidate": candidate.as_record(),
        "gate_registry": gates.as_record(),
        "window": window.as_record(),
        "provenance": {
            "database_snapshot_sha256": database_snapshot_sha256,
            "ingestion": snapshot.as_record(),
        },
        "forward_paper": _paper_summary(run),
        "economics": economics.as_record(),
        "gate": gate.as_record(),
    }
    return {
        **material,
        "audit_sha256": _sha256(_compact(material)),
    }


def _scenario_filename(name):
    return f"{name.lower().replace('_', '-')}.json"


def _expected_evidence(matrix):
    payloads = {"p10-009-index.json": matrix.index_json}
    for item in matrix.runs:
        payloads[_scenario_filename(item.name)] = item.artifact_json
    if len(payloads) != EXPECTED_EVIDENCE_FILES:
        raise P10AuditError("P10-009 recomputed evidence coverage is incomplete")
    return payloads


def _read_evidence(directory):
    target = (
        Path(directory)
        if isinstance(directory, (str, Path)) and str(directory)
        else None
    )
    if target is None or not target.is_dir() or target.is_symlink():
        raise P10AuditError("P10-009 evidence directory is invalid")

    expected_names = {"p10-009-index.json"} | {
        _scenario_filename(name) for name in SCENARIOS
    }
    try:
        paths = tuple(sorted(target.iterdir(), key=lambda item: item.name))
    except OSError:
        raise P10AuditError("P10-009 evidence directory cannot be read") from None

    if (
        len(paths) != EXPECTED_EVIDENCE_FILES
        or {item.name for item in paths} != expected_names
        or any(item.is_symlink() or not item.is_file() for item in paths)
    ):
        raise P10AuditError("P10-009 evidence directory contents are invalid")

    payloads = {}
    total = 0
    for path in paths:
        try:
            raw = path.read_bytes()
            text = raw.decode("utf-8")
            record = json.loads(text)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            raise P10AuditError("P10-009 evidence JSON is invalid") from None
        total += len(raw)
        if (
            not raw
            or len(raw) > MAX_ARTIFACT_BYTES
            or total > MAX_EVIDENCE_TOTAL_BYTES
            or _json(record) != text
        ):
            raise P10AuditError("P10-009 evidence is noncanonical or oversized")
        payloads[path.name] = text
    return payloads


def _audit_evidence(matrix, evidence_directory):
    expected = _expected_evidence(matrix)
    before = _read_evidence(evidence_directory)
    if before != expected:
        raise P10AuditError("Published P10-009 evidence differs from recomputation")

    index = json.loads(before["p10-009-index.json"])
    if (
        index.get("scenarios") != list(SCENARIOS)
        or len(index.get("runs", ())) != len(SCENARIOS)
        or index.get("strategy_evidence") != "INSUFFICIENT_EVIDENCE"
        or index.get("paper_only") is not True
        or index.get("live_master_lock") != "OFF"
        or index.get("p11_unlocked") is not False
        or index.get("trade_permission") is not False
        or index.get("order_endpoint") is not False
        or index.get("ai_direct_execution") is not False
        or index.get("threshold_mutation_allowed") is not False
        or index.get("candidate_mutation_allowed") is not False
        or index.get("accepted_evidence_mutated") is not False
        or index.get("real_network_called") is not False
    ):
        raise P10AuditError("P10-009 index safety boundary changed")

    for item in matrix.runs:
        record = json.loads(before[_scenario_filename(item.name)])
        if scenario_artifact_json(record) != item.artifact_json:
            raise P10AuditError("P10-009 scenario artifact failed independent validation")

    after = _read_evidence(evidence_directory)
    if before != after:
        raise P10AuditError("P10 final audit mutated adversarial evidence")
    return before


def _audit_source_safety():
    forbidden = (
        "Binance" + "PublicRestClient",
        "collect_" + "forward_snapshot",
        "write_" + "many(",
        "from yatl." + "execution",
        "import yatl." + "execution",
        "from yatl." + "account",
        "import yatl." + "account",
        "from yatl." + "risk",
        "import yatl." + "risk",
        "url" + "lib",
        "http." + "client",
        "req" + "uests",
        "http" + "x",
        "aio" + "http",
        "web" + "sock" + "ets",
        "os." + "getenv",
        "os." + "environ",
        "open" + "ai",
        "anth" + "ropic",
        "/api/v3/" + "order",
        "/f" + "api",
        "/d" + "api",
        "with" + "draw(",
        "sub" + "process",
    )
    try:
        text = Path(__file__).read_text(encoding="utf-8").casefold()
    except OSError:
        raise P10AuditError("P10 final audit source safety scan failed") from None
    if any(value.casefold() in text for value in forbidden):
        raise P10AuditError("P10 final audit source safety boundary failed")
    return True


def _disposition_flags(disposition):
    if disposition == GateDisposition.INSUFFICIENT_DATA.value:
        return {
            "continue_forward_observation": True,
            "research_restart_required": False,
            "economic_candidate_accepted": False,
            "p11_consideration_allowed": False,
        }
    if disposition == GateDisposition.FAIL.value:
        return {
            "continue_forward_observation": False,
            "research_restart_required": True,
            "economic_candidate_accepted": False,
            "p11_consideration_allowed": False,
        }
    if disposition == GateDisposition.PASS_CANDIDATE.value:
        return {
            "continue_forward_observation": False,
            "research_restart_required": False,
            "economic_candidate_accepted": True,
            "p11_consideration_allowed": True,
        }
    raise P10AuditError("P10 final disposition is invalid")


@dataclass(frozen=True, slots=True)
class P10AuditResult:
    disposition: str
    candidate_sha256: str
    gate_registry_sha256: str
    window_sha256: str
    ingestion_snapshot_sha256: str
    store_content_sha256: str
    paper_run_sha256: str
    economics_sha256: str
    gate_sha256: str
    audit_sha256: str
    adversarial_matrix_sha256: str
    scenarios: int
    evidence_files: int
    criteria: int
    exact_outcomes: bool
    replay_equal: bool
    chain_recomputed: bool
    adversarial_recomputed: bool
    evidence_verified: bool
    candidate_unchanged: bool
    thresholds_unchanged: bool
    no_write: bool
    source_safe: bool
    continue_forward_observation: bool
    research_restart_required: bool
    economic_candidate_accepted: bool
    p11_consideration_allowed: bool
    p11_unlocked: bool
    live_authorized: bool
    strategy_evidence: str

    def __post_init__(self):
        flags = _disposition_flags(self.disposition)
        if (
            self.disposition not in FINAL_DISPOSITIONS
            or self.candidate_sha256 != EXPECTED_CANDIDATE_SHA256
            or self.gate_registry_sha256 != EXPECTED_GATE_REGISTRY_SHA256
            or self.window_sha256 != EXPECTED_WINDOW_SHA256
            or any(
                not _valid_sha(value)
                for value in (
                    self.ingestion_snapshot_sha256,
                    self.store_content_sha256,
                    self.paper_run_sha256,
                    self.economics_sha256,
                    self.gate_sha256,
                    self.audit_sha256,
                    self.adversarial_matrix_sha256,
                )
            )
            or self.scenarios != len(SCENARIOS)
            or self.evidence_files != EXPECTED_EVIDENCE_FILES
            or self.criteria != len(EXPECTED_CRITERIA)
            or any(
                value is not True
                for value in (
                    self.exact_outcomes,
                    self.replay_equal,
                    self.chain_recomputed,
                    self.adversarial_recomputed,
                    self.evidence_verified,
                    self.candidate_unchanged,
                    self.thresholds_unchanged,
                    self.no_write,
                    self.source_safe,
                )
            )
            or self.continue_forward_observation
            is not flags["continue_forward_observation"]
            or self.research_restart_required
            is not flags["research_restart_required"]
            or self.economic_candidate_accepted
            is not flags["economic_candidate_accepted"]
            or self.p11_consideration_allowed
            is not flags["p11_consideration_allowed"]
            or self.p11_unlocked is not False
            or self.live_authorized is not False
            or self.strategy_evidence != "INSUFFICIENT_EVIDENCE"
        ):
            raise P10AuditError("P10 final audit result is inconsistent")


def audit_p10(store, snapshot, database_snapshot_sha256, evidence_directory):
    """Recompute the complete P10 chain and verify published P10-009 evidence."""
    try:
        if not _valid_sha(database_snapshot_sha256):
            raise P10AuditError("P10 database snapshot identity is invalid")
        candidate, gates, window = _candidate_gate_window()
        if (
            type(snapshot) is not ForwardIngestionSnapshot
            or snapshot.window_sha256 != window.window_sha256
            or snapshot.candidate_sha256 != candidate.candidate_sha256
            or snapshot.gate_registry_sha256 != gates.registry_sha256
            or snapshot.quality_pass is not True
        ):
            raise P10AuditError("P10 ingestion provenance differs from frozen chain")

        store_before = _store_identity(store, snapshot)

        run = run_forward_paper(store, snapshot)
        economics = calculate_forward_economics(store, snapshot, run)
        gate = evaluate_forward_gate(store, snapshot, run, economics)

        criteria = gate.as_record().get("criteria")
        disposition = gate.as_record().get("disposition")
        if (
            not isinstance(criteria, list)
            or tuple(item.get("criterion") for item in criteria) != EXPECTED_CRITERIA
            or disposition not in FINAL_DISPOSITIONS
        ):
            raise P10AuditError("P10 gate result differs from registered criteria")

        independent_record = _independent_audit_record(
            candidate,
            gates,
            window,
            snapshot,
            database_snapshot_sha256,
            run,
            economics,
            gate,
        )
        bundle = ValidationEvidenceBundle(
            snapshot=snapshot,
            database_snapshot_sha256=database_snapshot_sha256,
            ready=True,
            run=run,
            economics=economics,
            gate=gate,
        )
        fixture = accepted_validation_fixture(bundle)
        if (
            json.loads(fixture.canonical_audit_json) != independent_record
            or fixture.audit_sha256 != independent_record["audit_sha256"]
        ):
            raise P10AuditError("P10-008 canonical audit differs from independent recomputation")

        matrix = run_adversarial_validation_matrix(fixture)
        evidence = _audit_evidence(matrix, evidence_directory)

        store_after = _store_identity(store, snapshot)
        if store_before != store_after:
            raise P10AuditError("P10 final audit mutated accepted forward store")

        flags = _disposition_flags(disposition)
        return P10AuditResult(
            disposition=disposition,
            candidate_sha256=candidate.candidate_sha256,
            gate_registry_sha256=gates.registry_sha256,
            window_sha256=window.window_sha256,
            ingestion_snapshot_sha256=snapshot.snapshot_sha256,
            store_content_sha256=store_before["content_sha256"],
            paper_run_sha256=run.run_sha256,
            economics_sha256=economics.report_sha256,
            gate_sha256=gate.report_sha256,
            audit_sha256=independent_record["audit_sha256"],
            adversarial_matrix_sha256=validation_matrix_sha256(matrix),
            scenarios=len(matrix.runs),
            evidence_files=len(evidence),
            criteria=len(criteria),
            exact_outcomes=True,
            replay_equal=True,
            chain_recomputed=True,
            adversarial_recomputed=True,
            evidence_verified=True,
            candidate_unchanged=True,
            thresholds_unchanged=True,
            no_write=True,
            source_safe=_audit_source_safety(),
            continue_forward_observation=flags["continue_forward_observation"],
            research_restart_required=flags["research_restart_required"],
            economic_candidate_accepted=flags["economic_candidate_accepted"],
            p11_consideration_allowed=flags["p11_consideration_allowed"],
            p11_unlocked=False,
            live_authorized=False,
            strategy_evidence="INSUFFICIENT_EVIDENCE",
        )
    except P10AuditError:
        raise
    except (
        ForwardStoreError,
        ForwardPaperRunnerError,
        ForwardEconomicsError,
        ForwardGateError,
        ValidationScenarioError,
        TypeError,
        ValueError,
        KeyError,
        IndexError,
    ) as exc:
        raise P10AuditError("P10 independent final audit failed closed") from exc
