"""Deterministic adversarial matrix for P7 read-only analytics boundaries."""

import hashlib
import json
import shutil
import sqlite3
from dataclasses import dataclass, replace
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from .contracts import AnalyticsSourceKind, SYMBOLS
from .ingestion import UpstreamSourceSpec, _connect_readonly
from .quality import QualityCode, QualityStatus, run_quality_gate
from .segmentation import (
    SegmentDimension,
    SegmentationError,
    build_segmentation,
)
from .timeline_runtime import P6_OBSERVED, SNAPSHOT, START, _create_p5, _create_p6


SCHEMA_VERSION = 1
ARTIFACT_KIND = "YATL_P7_ADVERSARIAL_ANALYTICS_SCENARIO"
MATRIX_KIND = "YATL_P7_ADVERSARIAL_ANALYTICS_MATRIX"
MAX_ARTIFACT_BYTES = 1024 * 1024
MAX_EVIDENCE_FILES = 32

SCENARIOS = (
    "UPSTREAM_TAMPERING",
    "DUPLICATE_ORPHAN_FILL",
    "CROSS_SYMBOL_LINKAGE",
    "FUTURE_TIMESTAMP",
    "CHANGED_COST_EQUITY_TOTALS",
    "FABRICATED_PROFITABILITY",
    "EVIDENCE_LABEL_UPGRADE",
    "JOURNAL_MUTATION",
    "SCHEMA_SMUGGLING",
)

ACCEPTED_UPSTREAM_IDENTITIES = {
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


class AnalyticsScenarioError(Exception):
    """One P7 adversarial scenario violated its exact fail-closed outcome."""


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


def _file_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _digest(value):
    return _sha256(_compact_json(value))


def _close_fixture(path, symbol):
    connection = sqlite3.connect(str(path))
    entry = connection.execute(
        "SELECT payload_json FROM local_paper_fill_events WHERE sequence = 0"
    ).fetchone()
    if entry is None:
        connection.close()
        raise AnalyticsScenarioError("Scenario fixture is missing entry fill")
    entry_payload = json.loads(entry[0])

    authorization = "6" * 64
    decision = "7" * 64
    readiness = "8" * 64
    intent_material = {
        "schema_version": 1,
        "authorization_sha256": authorization,
        "effect_sha256": authorization,
        "decision_sha256": decision,
        "readiness_sha256": readiness,
        "action": "EXIT_LONG",
        "approved_quantity": "1",
        "policy_id": "P5_LOCAL_PAPER_V1",
    }
    intent_sha = _digest(intent_material)

    create_material = {
        "schema_version": 1,
        "authorization_sha256": authorization,
        "intent_sha256": intent_sha,
        "sequence": 0,
        "event_time_ms": START + 60,
        "event_type": "CREATE",
        "reason": "ACCEPTED_INTENT_RECORDED",
        "previous_event_sha256": None,
    }
    create_sha = _digest(create_material)
    state0_material = {
        "schema_version": 1,
        "authorization_sha256": authorization,
        "intent_sha256": intent_sha,
        "sequence": 0,
        "updated_time_ms": START + 60,
        "status": "PENDING_LOCAL",
        "reason": "ACCEPTED_INTENT_RECORDED",
        "previous_state_sha256": None,
        "event_sha256": create_sha,
    }
    state0_sha = _digest(state0_material)

    activate_material = {
        "schema_version": 1,
        "authorization_sha256": authorization,
        "intent_sha256": intent_sha,
        "sequence": 1,
        "event_time_ms": START + 70,
        "event_type": "ACTIVATE",
        "reason": "LOCAL_ACTIVATION_CONFIRMED",
        "previous_event_sha256": create_sha,
    }
    activate_sha = _digest(activate_material)
    state1_material = {
        "schema_version": 1,
        "authorization_sha256": authorization,
        "intent_sha256": intent_sha,
        "sequence": 1,
        "updated_time_ms": START + 70,
        "status": "ACTIVE_LOCAL",
        "reason": "LOCAL_ACTIVATION_CONFIRMED",
        "previous_state_sha256": state0_sha,
        "event_sha256": activate_sha,
    }
    state1_sha = _digest(state1_material)

    exit_payload = {
        "action": "EXIT_LONG",
        "symbol": symbol,
        "decision_time_ms": START + 80,
        "fill_time_ms": START + 80,
        "quantity": "1",
        "reference_price": "110",
        "reason": "SCRIPTED_EXIT",
        "fee_bps": "10",
        "slippage_bps": "5",
        "execution_price": "109.945",
        "gross_quote": "109.945",
        "fee_quote": "0.109945",
        "slippage_quote": "0.055",
        "cash_delta": "109.835055",
        "asset_delta": "-1",
    }
    fill_step_sha = "9" * 64
    fill_material = {
        "schema_version": 1,
        "sequence": 1,
        "authorization_sha256": authorization,
        "intent_sha256": intent_sha,
        "order_state_sha256": state1_sha,
        "fill_step_sha256": fill_step_sha,
        "fill_index": 0,
        "fill": exit_payload,
    }
    fill_sha = _digest(fill_material)

    realized = str(
        Decimal(entry_payload["cash_delta"])
        + Decimal(exit_payload["cash_delta"])
    )
    total_fee = str(
        Decimal(entry_payload["fee_quote"])
        + Decimal(exit_payload["fee_quote"])
    )
    total_slippage = str(
        Decimal(entry_payload["slippage_quote"])
        + Decimal(exit_payload["slippage_quote"])
    )
    current = connection.execute(
        "SELECT spec_sha256 FROM local_paper_portfolios WHERE symbol = ?",
        (symbol,),
    ).fetchone()
    if current is None:
        connection.close()
        raise AnalyticsScenarioError("Scenario fixture is missing portfolio")
    spec_sha = current[0]
    portfolio = {
        "symbol": symbol,
        "cash": "1009.685005",
        "asset_quantity": "0",
        "cost_basis_quote": "0",
        "liquidation_value_quote": "0",
        "realized_pnl_quote": realized,
        "unrealized_pnl_quote": "0",
        "equity_quote": "1009.685005",
        "total_fee_quote": total_fee,
        "total_slippage_quote": total_slippage,
        "closed_trades": 1,
    }
    projection_material = {
        "schema_version": 1,
        "spec_sha256": spec_sha,
        "fill_count": 2,
        "last_fill_event_sha256": fill_sha,
        "mark_price": "110",
        "position": "FLAT",
        "portfolio": portfolio,
    }
    projection_sha = _digest(projection_material)
    projection_payload = {
        **projection_material,
        "projection_sha256": projection_sha,
    }

    with connection:
        connection.execute(
            "INSERT INTO local_paper_intents VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                authorization,
                authorization,
                decision,
                readiness,
                "EXIT_LONG",
                "1",
                "P5_LOCAL_PAPER_V1",
                intent_sha,
            ),
        )
        connection.execute(
            "INSERT INTO local_paper_order_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                authorization,
                intent_sha,
                0,
                START + 60,
                "CREATE",
                "ACCEPTED_INTENT_RECORDED",
                None,
                create_sha,
            ),
        )
        connection.execute(
            "INSERT INTO local_paper_order_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                authorization,
                intent_sha,
                1,
                START + 70,
                "ACTIVATE",
                "LOCAL_ACTIVATION_CONFIRMED",
                create_sha,
                activate_sha,
            ),
        )
        connection.execute(
            "INSERT INTO local_paper_order_states VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                authorization,
                intent_sha,
                1,
                START + 70,
                "ACTIVE_LOCAL",
                "LOCAL_ACTIVATION_CONFIRMED",
                state0_sha,
                activate_sha,
                state1_sha,
            ),
        )
        connection.execute(
            "INSERT INTO local_paper_fill_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                fill_sha,
                symbol,
                1,
                authorization,
                intent_sha,
                state1_sha,
                fill_step_sha,
                0,
                _compact_json(exit_payload),
            ),
        )
        connection.execute(
            """
            UPDATE local_paper_portfolios
            SET fill_count = ?, last_fill_event_sha256 = ?, mark_price = ?,
                payload_json = ?, projection_sha256 = ?
            WHERE symbol = ?
            """,
            (
                2,
                fill_sha,
                "110",
                _compact_json(projection_payload),
                projection_sha,
                symbol,
            ),
        )
    connection.close()


def _fixture(root, symbol):
    p5 = root / "p5.sqlite3"
    p6 = root / "p6.sqlite3"
    _create_p5(p5, symbol, START)
    _close_fixture(p5, symbol)
    _create_p6(p6)
    specs = (
        UpstreamSourceSpec(
            "SOURCE_P5",
            AnalyticsSourceKind.P5_EXECUTION_EVIDENCE,
            symbol,
            START + 90,
            p5,
            _file_sha(p5),
        ),
        UpstreamSourceSpec(
            "SOURCE_P6",
            AnalyticsSourceKind.P6_ANALYST_TRACE,
            symbol,
            P6_OBSERVED,
            p6,
            _file_sha(p6),
        ),
    )
    return p5, p6, specs


def _quality_observed(gate):
    return {
        "stage": "QUALITY",
        "status": gate.report.status.value,
        "publication_allowed":
            gate.report.as_record()["publication_allowed"],
        "diagnostics": [
            {
                "code": item.code.value,
                "component": item.component.value,
            }
            for item in gate.report.diagnostics
        ],
        "accepted_chain_present": gate.report.accepted_chain is not None,
        "analytics_payload_present": gate.accepted_segmentation is not None,
    }


def _expect_quality_failure(symbol, expected_code, mutation):
    with TemporaryDirectory() as directory:
        root = Path(directory)
        p5, p6, specs = _fixture(root, symbol)
        specs = mutation(p5, p6, specs)
        gate = run_quality_gate(SNAPSHOT, specs)
        observed = _quality_observed(gate)
        passed = (
            gate.report.status is QualityStatus.FAIL
            and tuple(item.code for item in gate.report.diagnostics)
            == (expected_code,)
            and gate.report.accepted_chain is None
            and gate.accepted_segmentation is None
            and gate.report.as_record()["publication_allowed"] is False
        )
        return observed, passed


def _upstream_tampering(symbol):
    def mutate(p5, _p6, specs):
        with p5.open("ab") as stream:
            stream.write(b"tampered")
        return specs

    observed, passed = _expect_quality_failure(
        symbol,
        QualityCode.UPSTREAM_DIGEST_CHANGED,
        mutate,
    )
    return {
        "quality_code": "UPSTREAM_DIGEST_CHANGED",
        "publication_allowed": False,
    }, observed, passed


def _duplicate_orphan_fill(symbol):
    def mutate(p5, _p6, specs):
        connection = sqlite3.connect(str(p5))
        row = connection.execute(
            "SELECT payload_json FROM local_paper_fill_events "
            "ORDER BY sequence LIMIT 1"
        ).fetchone()
        if row is None:
            connection.close()
            raise AnalyticsScenarioError("Scenario fill fixture is missing")
        with connection:
            connection.execute(
                "INSERT INTO local_paper_fill_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "a" * 64,
                    symbol,
                    2,
                    "b" * 64,
                    "c" * 64,
                    "d" * 64,
                    "e" * 64,
                    0,
                    row[0],
                ),
            )
        connection.close()
        return (
            replace(specs[0], expected_database_sha256=_file_sha(p5)),
            specs[1],
        )

    observed, passed = _expect_quality_failure(
        symbol,
        QualityCode.ORPHAN_RELATIONSHIP,
        mutate,
    )
    return {
        "quality_code": "ORPHAN_RELATIONSHIP",
        "publication_allowed": False,
    }, observed, passed


def _cross_symbol_linkage(symbol):
    other = "ETHUSDT" if symbol == "BTCUSDT" else "BTCUSDT"

    def mutate(p5, _p6, specs):
        connection = sqlite3.connect(str(p5))
        with connection:
            connection.execute(
                "UPDATE local_paper_fill_events SET symbol=? "
                "WHERE sequence=0",
                (other,),
            )
        connection.close()
        return (
            replace(specs[0], expected_database_sha256=_file_sha(p5)),
            specs[1],
        )

    observed, passed = _expect_quality_failure(
        symbol,
        QualityCode.SOURCE_IDENTITY_INVALID,
        mutate,
    )
    return {
        "quality_code": "SOURCE_IDENTITY_INVALID",
        "publication_allowed": False,
    }, observed, passed


def _future_timestamp(symbol):
    def mutate(_p5, _p6, specs):
        return (
            specs[0],
            replace(specs[1], observed_at_ms=SNAPSHOT + 1),
        )

    observed, passed = _expect_quality_failure(
        symbol,
        QualityCode.FUTURE_TIMESTAMP,
        mutate,
    )
    return {
        "quality_code": "FUTURE_TIMESTAMP",
        "publication_allowed": False,
    }, observed, passed


def _mutate_portfolio(p5, symbol, updates):
    connection = sqlite3.connect(str(p5))
    row = connection.execute(
        "SELECT payload_json FROM local_paper_portfolios WHERE symbol=?",
        (symbol,),
    ).fetchone()
    if row is None:
        connection.close()
        raise AnalyticsScenarioError("Scenario portfolio fixture is missing")
    payload = json.loads(row[0])
    portfolio = dict(payload["portfolio"])
    portfolio.update(updates)
    material = {
        **{key: value for key, value in payload.items()
           if key != "projection_sha256"},
        "portfolio": portfolio,
    }
    projection_sha = _digest(material)
    updated = {
        **material,
        "projection_sha256": projection_sha,
    }
    with connection:
        connection.execute(
            "UPDATE local_paper_portfolios "
            "SET payload_json=?, projection_sha256=? WHERE symbol=?",
            (_compact_json(updated), projection_sha, symbol),
        )
    connection.close()


def _changed_cost_equity_totals(symbol):
    def mutate(p5, _p6, specs):
        _mutate_portfolio(
            p5,
            symbol,
            {
                "total_fee_quote": "999",
                "equity_quote": "1",
            },
        )
        return (
            replace(specs[0], expected_database_sha256=_file_sha(p5)),
            specs[1],
        )

    observed, passed = _expect_quality_failure(
        symbol,
        QualityCode.INCONSISTENT_TOTALS,
        mutate,
    )
    return {
        "quality_code": "INCONSISTENT_TOTALS",
        "publication_allowed": False,
        "fabricated_totals_accepted": False,
    }, observed, passed


def _fabricated_profitability(symbol):
    def mutate(p5, _p6, specs):
        _mutate_portfolio(
            p5,
            symbol,
            {
                "realized_pnl_quote": "999999",
                "equity_quote": "1000999",
            },
        )
        return (
            replace(specs[0], expected_database_sha256=_file_sha(p5)),
            specs[1],
        )

    observed, passed = _expect_quality_failure(
        symbol,
        QualityCode.INCONSISTENT_TOTALS,
        mutate,
    )
    return {
        "quality_code": "INCONSISTENT_TOTALS",
        "publication_allowed": False,
        "fabricated_profitability_accepted": False,
    }, observed, passed


def _evidence_label_upgrade(symbol):
    with TemporaryDirectory() as directory:
        root = Path(directory)
        _p5, _p6, specs = _fixture(root, symbol)
        report = build_segmentation(SNAPSHOT, specs)
        segments = list(report.trade_segments)
        index = next(
            index
            for index, item in enumerate(segments)
            if item.dimension is SegmentDimension.EVIDENCE_LABEL
        )
        segments[index] = replace(
            segments[index],
            value="QUALIFIED_FOR_P4_RESEARCH",
        )
        rejected = False
        try:
            replace(report, trade_segments=tuple(segments))
        except SegmentationError:
            rejected = True
        observed = {
            "stage": "SEGMENTATION",
            "code": "EVIDENCE_LABEL_UPGRADE_REJECTED"
                if rejected else "UNEXPECTED_ACCEPT",
            "strategy_evidence": "INSUFFICIENT_EVIDENCE",
            "publication_allowed": False,
        }
        expected = {
            "code": "EVIDENCE_LABEL_UPGRADE_REJECTED",
            "strategy_evidence": "INSUFFICIENT_EVIDENCE",
            "publication_allowed": False,
        }
        return expected, observed, rejected


def _journal_mutation(symbol):
    with TemporaryDirectory() as directory:
        root = Path(directory)
        p5, _p6, specs = _fixture(root, symbol)
        before = _file_sha(p5)
        rejected = False
        connection = _connect_readonly(p5)
        try:
            try:
                connection.execute(
                    "UPDATE local_paper_intents SET action='EXIT_LONG'"
                )
                connection.commit()
            except sqlite3.Error:
                rejected = True
        finally:
            connection.close()
        after = _file_sha(p5)
        gate = run_quality_gate(SNAPSHOT, specs)
        passed = (
            rejected
            and before == after
            and gate.report.status is QualityStatus.PASS
            and gate.accepted_segmentation is not None
        )
        observed = {
            "stage": "READ_ONLY_SOURCE",
            "code": "READ_ONLY_MUTATION_REJECTED"
                if rejected else "UNEXPECTED_WRITE",
            "no_write": before == after,
            "quality_after_attempt": gate.report.status.value,
        }
        expected = {
            "code": "READ_ONLY_MUTATION_REJECTED",
            "no_write": True,
            "quality_after_attempt": "PASS",
        }
        return expected, observed, passed


def _schema_smuggling(symbol):
    def mutate(p5, _p6, specs):
        connection = sqlite3.connect(str(p5))
        with connection:
            connection.execute(
                "ALTER TABLE local_paper_intents ADD COLUMN smuggled TEXT"
            )
        connection.close()
        return (
            replace(specs[0], expected_database_sha256=_file_sha(p5)),
            specs[1],
        )

    observed, passed = _expect_quality_failure(
        symbol,
        QualityCode.ANALYTICS_CHAIN_INVALID,
        mutate,
    )
    return {
        "quality_code": "ANALYTICS_CHAIN_INVALID",
        "publication_allowed": False,
        "schema_smuggling_accepted": False,
    }, observed, passed


_HANDLERS = {
    "UPSTREAM_TAMPERING": _upstream_tampering,
    "DUPLICATE_ORPHAN_FILL": _duplicate_orphan_fill,
    "CROSS_SYMBOL_LINKAGE": _cross_symbol_linkage,
    "FUTURE_TIMESTAMP": _future_timestamp,
    "CHANGED_COST_EQUITY_TOTALS": _changed_cost_equity_totals,
    "FABRICATED_PROFITABILITY": _fabricated_profitability,
    "EVIDENCE_LABEL_UPGRADE": _evidence_label_upgrade,
    "JOURNAL_MUTATION": _journal_mutation,
    "SCHEMA_SMUGGLING": _schema_smuggling,
}


def _safe_result(symbol, name, expected, observed, passed):
    if not passed:
        raise AnalyticsScenarioError(
            f"Scenario failed safe invariant: {symbol}/{name}"
        )
    record = {
        "schema_version": SCHEMA_VERSION,
        "artifact_kind": ARTIFACT_KIND,
        "symbol": symbol,
        "scenario": name,
        "expected": expected,
        "observed": observed,
        "passed": True,
        "accepted_upstream_identities": dict(ACCEPTED_UPSTREAM_IDENTITIES),
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
    record["result_sha256"] = _sha256(_json(record))
    return record


def _run_scenario(symbol, name):
    if symbol not in SYMBOLS or name not in SCENARIOS:
        raise AnalyticsScenarioError("Scenario symbol or name is invalid")
    expected, observed, passed = _HANDLERS[name](symbol)
    return _safe_result(symbol, name, expected, observed, passed)


def scenario_artifact_json(record):
    required = {
        "schema_version",
        "artifact_kind",
        "symbol",
        "scenario",
        "expected",
        "observed",
        "passed",
        "accepted_upstream_identities",
        "strategy_evidence",
        "paper_only",
        "read_only_analytics",
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
        "partial_publication_on_failure",
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
        or record.get("accepted_upstream_identities")
        != ACCEPTED_UPSTREAM_IDENTITIES
        or record.get("strategy_evidence") != "INSUFFICIENT_EVIDENCE"
        or record.get("paper_only") is not True
        or record.get("read_only_analytics") is not True
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
        or record.get("partial_publication_on_failure") is not False
    ):
        raise AnalyticsScenarioError("Scenario artifact identity is invalid")

    material = dict(record)
    digest = material.pop("result_sha256", None)
    if digest != _sha256(_json(material)):
        raise AnalyticsScenarioError("Scenario artifact digest is inconsistent")

    encoded = _json(record)
    lowered = encoded.casefold()
    forbidden = (
        '"api_key"',
        '"api_secret"',
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
    if (
        any(item in lowered for item in forbidden)
        or len(encoded.encode("utf-8")) > MAX_ARTIFACT_BYTES
    ):
        raise AnalyticsScenarioError(
            "Scenario artifact contains forbidden material"
        )
    return encoded


@dataclass(frozen=True, slots=True)
class AnalyticsScenarioResult:
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
            raise AnalyticsScenarioError("Scenario result identity is invalid")
        try:
            record = json.loads(self.artifact_json)
        except json.JSONDecodeError:
            raise AnalyticsScenarioError("Scenario result JSON is invalid") from None
        if (
            record.get("symbol") != self.symbol
            or record.get("scenario") != self.name
            or scenario_artifact_json(record) != self.artifact_json
        ):
            raise AnalyticsScenarioError("Scenario result and artifact differ")


@dataclass(frozen=True, slots=True)
class AnalyticsScenarioMatrixResult:
    runs: tuple[AnalyticsScenarioResult, ...]
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
            raise AnalyticsScenarioError(
                "Scenario matrix is incomplete or unordered"
            )
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
            "accepted_upstream_identities": dict(
                ACCEPTED_UPSTREAM_IDENTITIES
            ),
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
        try:
            actual = json.loads(self.index_json)
        except json.JSONDecodeError:
            raise AnalyticsScenarioError("Scenario matrix index is invalid") from None
        if actual != expected_index or _json(actual) != self.index_json:
            raise AnalyticsScenarioError("Scenario matrix index is noncanonical")


def _filename(symbol, name):
    return f"{symbol.lower()}-{name.lower().replace('_', '-')}.json"


def run_adversarial_analytics_matrix():
    runs = []
    for symbol in SYMBOLS:
        for name in SCENARIOS:
            first = scenario_artifact_json(_run_scenario(symbol, name))
            replay = scenario_artifact_json(_run_scenario(symbol, name))
            if first != replay:
                raise AnalyticsScenarioError(
                    f"Scenario replay diverged: {symbol}/{name}"
                )
            runs.append(
                AnalyticsScenarioResult(
                    symbol,
                    name,
                    first,
                    _sha256(first),
                )
            )

    records = [
        {
            "symbol": item.symbol,
            "scenario": item.name,
            "file": _filename(item.symbol, item.name),
            "sha256": item.result_sha256,
            "passed": True,
            "replay_equal": True,
        }
        for item in runs
    ]
    index = {
        "schema_version": SCHEMA_VERSION,
        "artifact_kind": MATRIX_KIND,
        "symbols": list(SYMBOLS),
        "scenarios": list(SCENARIOS),
        "runs": records,
        "accepted_upstream_identities": dict(ACCEPTED_UPSTREAM_IDENTITIES),
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
    return AnalyticsScenarioMatrixResult(tuple(runs), _json(index))


def write_adversarial_analytics_matrix(result, output_dir):
    if not isinstance(result, AnalyticsScenarioMatrixResult):
        raise AnalyticsScenarioError("Scenario matrix output is invalid")
    target = (
        Path(output_dir)
        if isinstance(output_dir, (str, Path)) and str(output_dir)
        else None
    )
    if target is None:
        raise AnalyticsScenarioError("Scenario output directory is invalid")
    if target.exists():
        raise AnalyticsScenarioError(
            "Existing scenario evidence will not be overwritten"
        )
    temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
    try:
        temporary.mkdir(parents=True)
        files = {"p7-009-index.json": result.index_json}
        for item in result.runs:
            files[_filename(item.symbol, item.name)] = item.artifact_json
        if not 1 <= len(files) <= MAX_EVIDENCE_FILES:
            raise AnalyticsScenarioError(
                "Scenario evidence file count is invalid"
            )
        for name, payload in files.items():
            if len(payload.encode("utf-8")) > MAX_ARTIFACT_BYTES:
                raise AnalyticsScenarioError(
                    "Scenario evidence file is too large"
                )
            (temporary / name).write_text(
                payload,
                encoding="utf-8",
                newline="\n",
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary.replace(target)
    except AnalyticsScenarioError:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    except OSError:
        shutil.rmtree(temporary, ignore_errors=True)
        raise AnalyticsScenarioError(
            "Cannot atomically publish analytics scenario evidence"
        ) from None
    return target


def analytics_matrix_sha256(result):
    if not isinstance(result, AnalyticsScenarioMatrixResult):
        raise AnalyticsScenarioError("Scenario matrix digest input is invalid")
    return _sha256(result.index_json)


def run_and_write_adversarial_analytics_matrix(output_dir):
    result = run_adversarial_analytics_matrix()
    write_adversarial_analytics_matrix(result, output_dir)
    return result


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(
        description="Deterministic P7 adversarial analytics matrix"
    )
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    result = run_and_write_adversarial_analytics_matrix(args.output)
    print(
        "OK: P7 adversarial analytics matrix; "
        f"scenarios={len(SCENARIOS)} symbols={len(SYMBOLS)} "
        f"runs={len(result.runs)} replay_equal=true "
        f"index_sha256={analytics_matrix_sha256(result)}"
    )
    print(
        "PAPER ONLY | READ_ONLY_ANALYTICS | LIVE_MASTER_LOCK=OFF | "
        "INSUFFICIENT_EVIDENCE preserved | Canonical evidence | "
        "Accepted P3/P4/P5/P6 identities unchanged | "
        "No partial publication on failure | No credentials | "
        "No network/provider | No executor import | "
        "No RiskAuthorization mutation | No quantity authority | "
        "No trade permission | No order endpoint | No AI direct execution"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
