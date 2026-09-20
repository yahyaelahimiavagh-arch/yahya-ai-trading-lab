"""Immutable P8 local Dashboard contracts with no execution capability."""

import hashlib
import json
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from enum import Enum


DASHBOARD_POLICY_ID = "P8_DASHBOARD_V1"
DASHBOARD_SCHEMA_VERSION = 1
SYMBOLS = ("BTCUSDT", "ETHUSDT")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
ID_PATTERN = re.compile(r"[A-Z][A-Z0-9_-]{2,63}")
FIELD_KEY_PATTERN = re.compile(r"[a-z][a-z0-9_]{2,63}")
MAX_TEXT_CHARS = 256
MAX_OVERVIEW_CARDS = 32
MAX_TRADE_ROWS = 4096
MAX_METRIC_VALUES = 256
MAX_SEGMENT_ROWS = 1024
MAX_DIAGNOSTICS = 256

_AUTHORITY_FIELD_TOKENS = (
    "credential",
    "api_key",
    "api_secret",
    "secret",
    "account_id",
    "risk_authorization",
    "approved_quantity",
    "quantity_authority",
    "trade_permission",
    "order_endpoint",
    "execution_command",
    "withdrawal",
)


class DashboardContractError(ValueError):
    """P8 Dashboard material violates the frozen display-only boundary."""


class StrategyEvidenceState(str, Enum):
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class OverviewDisplayKind(str, Enum):
    TEXT = "TEXT"
    COUNT = "COUNT"
    STATUS = "STATUS"
    HASH = "HASH"


class MetricState(str, Enum):
    VALUE = "VALUE"
    UNAVAILABLE = "UNAVAILABLE"


class MetricUnit(str, Enum):
    USD = "USD"
    PERCENT = "PERCENT"
    COUNT = "COUNT"
    MILLISECONDS = "MILLISECONDS"
    RATIO = "RATIO"


class DiagnosticSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


def _canonical_json(payload):
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def _sha256(payload):
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _valid_sha(value):
    return isinstance(value, str) and SHA256_PATTERN.fullmatch(value) is not None


def _valid_id(value):
    return isinstance(value, str) and ID_PATTERN.fullmatch(value) is not None


def _valid_field_key(value):
    return isinstance(value, str) and FIELD_KEY_PATTERN.fullmatch(value) is not None


def _valid_text(value, *, allow_empty=False):
    if not isinstance(value, str):
        return False
    if not allow_empty and not value:
        return False
    if len(value) > MAX_TEXT_CHARS:
        return False
    return all(character >= " " and character != "\x7f" for character in value)


def _valid_decimal_text(value):
    if not isinstance(value, str) or not value or len(value) > 96:
        return False
    if value != value.strip() or "e" in value.lower():
        return False
    try:
        number = Decimal(value)
    except InvalidOperation:
        return False
    return number.is_finite()


def _nonnegative_decimal_text(value):
    return _valid_decimal_text(value) and Decimal(value) >= 0


def _positive_decimal_text(value):
    return _valid_decimal_text(value) and Decimal(value) > 0


def _reject_authority_field_name(value):
    lowered = value.lower()
    if any(token in lowered for token in _AUTHORITY_FIELD_TOKENS):
        raise DashboardContractError(
            "Dashboard display field attempts to carry authority-bearing material"
        )


def _expect_record(record, expected_keys, label):
    if not isinstance(record, dict) or set(record) != set(expected_keys):
        raise DashboardContractError(
            f"{label} schema is invalid or contains unexpected fields"
        )


def _ordered_unique(items, key, label):
    identities = tuple(key(item) for item in items)
    if len(set(identities)) != len(identities) or identities != tuple(sorted(identities)):
        raise DashboardContractError(f"{label} are duplicate or unordered")


@dataclass(frozen=True, slots=True)
class DashboardPolicy:
    """Frozen P8 boundary. Dashboard output is local, read-only and display-only."""

    policy_id: str = DASHBOARD_POLICY_ID
    mode: str = "LOCAL_READ_ONLY_DASHBOARD"
    source_scope: str = "ACCEPTED_SANITIZED_P7_EXPORT_ONLY"
    display_only: bool = True
    paper_only: bool = True
    live_master_lock: str = "OFF"
    spot_only: bool = True
    allow_short: bool = False
    allow_margin: bool = False
    allow_futures: bool = False
    allow_leverage: bool = False
    allow_withdrawal: bool = False
    allow_remote_assets: bool = False
    allow_external_scripts: bool = False
    allow_network_transport: bool = False
    allow_provider_transport: bool = False
    allow_credentials: bool = False
    allow_source_write: bool = False
    allow_direct_p5_p6_access: bool = False
    allow_execution_import: bool = False
    allow_account_import: bool = False
    allow_risk_import: bool = False
    allow_risk_authorization_mutation: bool = False
    allow_quantity_authority: bool = False
    allow_trade_permission: bool = False
    allow_order_endpoint: bool = False
    allow_ai_direct_execution: bool = False
    allow_strategy_evidence_upgrade: bool = False

    def __post_init__(self):
        expected_false = (
            self.allow_short,
            self.allow_margin,
            self.allow_futures,
            self.allow_leverage,
            self.allow_withdrawal,
            self.allow_remote_assets,
            self.allow_external_scripts,
            self.allow_network_transport,
            self.allow_provider_transport,
            self.allow_credentials,
            self.allow_source_write,
            self.allow_direct_p5_p6_access,
            self.allow_execution_import,
            self.allow_account_import,
            self.allow_risk_import,
            self.allow_risk_authorization_mutation,
            self.allow_quantity_authority,
            self.allow_trade_permission,
            self.allow_order_endpoint,
            self.allow_ai_direct_execution,
            self.allow_strategy_evidence_upgrade,
        )
        if not (
            self.policy_id == DASHBOARD_POLICY_ID
            and self.mode == "LOCAL_READ_ONLY_DASHBOARD"
            and self.source_scope == "ACCEPTED_SANITIZED_P7_EXPORT_ONLY"
            and self.display_only is True
            and self.paper_only is True
            and self.live_master_lock == "OFF"
            and self.spot_only is True
            and all(value is False for value in expected_false)
        ):
            raise DashboardContractError(
                "Dashboard policy differs from the frozen P8 display-only policy"
            )

    def as_record(self):
        return {
            name: getattr(self, name)
            for name in self.__dataclass_fields__
        }

    @property
    def policy_sha256(self):
        return _sha256(
            {
                "schema_version": DASHBOARD_SCHEMA_VERSION,
                "policy": self.as_record(),
            }
        )


@dataclass(frozen=True, slots=True)
class DashboardSourceIdentity:
    """Identity of one accepted and sanitized P7 export; no file path is carried."""

    source_id: str
    symbol: str
    export_schema_version: int
    observed_at_ms: int
    export_sha256: str
    source_kind: str = "P7_ACCEPTED_SANITIZED_EXPORT"
    quality_status: str = "PASS"
    accepted: bool = True
    sanitized: bool = True
    read_only: bool = True
    strategy_evidence: StrategyEvidenceState = (
        StrategyEvidenceState.INSUFFICIENT_EVIDENCE
    )

    def __post_init__(self):
        if not (
            _valid_id(self.source_id)
            and self.symbol in SYMBOLS
            and type(self.export_schema_version) is int
            and 1 <= self.export_schema_version <= 1_000_000
            and type(self.observed_at_ms) is int
            and self.observed_at_ms >= 0
            and _valid_sha(self.export_sha256)
            and self.source_kind == "P7_ACCEPTED_SANITIZED_EXPORT"
            and self.quality_status == "PASS"
            and self.accepted is True
            and self.sanitized is True
            and self.read_only is True
            and self.strategy_evidence
            is StrategyEvidenceState.INSUFFICIENT_EVIDENCE
        ):
            raise DashboardContractError("Dashboard source identity is invalid")

    def as_record(self):
        return {
            "source_id": self.source_id,
            "symbol": self.symbol,
            "export_schema_version": self.export_schema_version,
            "observed_at_ms": self.observed_at_ms,
            "export_sha256": self.export_sha256,
            "source_kind": self.source_kind,
            "quality_status": self.quality_status,
            "accepted": self.accepted,
            "sanitized": self.sanitized,
            "read_only": self.read_only,
            "strategy_evidence": self.strategy_evidence.value,
        }

    @property
    def identity_sha256(self):
        return _sha256(
            {
                "schema_version": DASHBOARD_SCHEMA_VERSION,
                "source": self.as_record(),
            }
        )


@dataclass(frozen=True, slots=True)
class DashboardSafetyBanner:
    """Non-overridable user-visible safety/evidence labels."""

    paper_label: str = "PAPER ONLY"
    live_lock_label: str = "LIVE_MASTER_LOCK=OFF"
    evidence_label: str = "INSUFFICIENT_EVIDENCE"
    purpose_label: str = "DESCRIPTIVE ONLY"
    readiness_label: str = "NOT A PROFITABILITY OR LIVE-READINESS CLAIM"

    def __post_init__(self):
        if (
            self.paper_label,
            self.live_lock_label,
            self.evidence_label,
            self.purpose_label,
            self.readiness_label,
        ) != (
            "PAPER ONLY",
            "LIVE_MASTER_LOCK=OFF",
            "INSUFFICIENT_EVIDENCE",
            "DESCRIPTIVE ONLY",
            "NOT A PROFITABILITY OR LIVE-READINESS CLAIM",
        ):
            raise DashboardContractError("Dashboard safety banner cannot be weakened")

    def as_record(self):
        return {
            name: getattr(self, name)
            for name in self.__dataclass_fields__
        }


@dataclass(frozen=True, slots=True)
class DashboardOverviewCard:
    """One bounded display-only overview card."""

    card_id: str
    field_key: str
    label: str
    value: str
    display_kind: OverviewDisplayKind
    source_field_sha256: str
    display_only: bool = True

    def __post_init__(self):
        if not (
            _valid_id(self.card_id)
            and _valid_field_key(self.field_key)
            and _valid_text(self.label)
            and _valid_text(self.value, allow_empty=True)
            and isinstance(self.display_kind, OverviewDisplayKind)
            and _valid_sha(self.source_field_sha256)
            and self.display_only is True
        ):
            raise DashboardContractError("Dashboard overview card is invalid")
        _reject_authority_field_name(self.field_key)

    def as_record(self):
        return {
            "card_id": self.card_id,
            "field_key": self.field_key,
            "label": self.label,
            "value": self.value,
            "display_kind": self.display_kind.value,
            "source_field_sha256": self.source_field_sha256,
            "display_only": self.display_only,
        }


@dataclass(frozen=True, slots=True)
class DashboardTradeRow:
    """Immutable completed Paper-trade display row; values are not re-authorized."""

    trade_id: str
    symbol: str
    entry_time_ms: int
    exit_time_ms: int
    quantity: str
    entry_price: str
    exit_price: str
    net_pnl: str
    fee_total: str
    slippage_total: str
    source_trade_sha256: str
    side: str = "LONG"
    status: str = "COMPLETED"
    paper: bool = True
    display_only: bool = True

    def __post_init__(self):
        if not (
            _valid_id(self.trade_id)
            and self.symbol in SYMBOLS
            and type(self.entry_time_ms) is int
            and type(self.exit_time_ms) is int
            and 0 <= self.entry_time_ms < self.exit_time_ms
            and _positive_decimal_text(self.quantity)
            and _positive_decimal_text(self.entry_price)
            and _positive_decimal_text(self.exit_price)
            and _valid_decimal_text(self.net_pnl)
            and _nonnegative_decimal_text(self.fee_total)
            and _nonnegative_decimal_text(self.slippage_total)
            and _valid_sha(self.source_trade_sha256)
            and self.side == "LONG"
            and self.status == "COMPLETED"
            and self.paper is True
            and self.display_only is True
        ):
            raise DashboardContractError("Dashboard trade row is invalid")

    def as_record(self):
        return {
            name: getattr(self, name)
            for name in self.__dataclass_fields__
        }


@dataclass(frozen=True, slots=True)
class DashboardMetricValue:
    """One descriptive metric copied from accepted P7 analytics."""

    metric_id: str
    value: str | None
    unit: MetricUnit
    state: MetricState
    source_metric_sha256: str
    display_only: bool = True

    def __post_init__(self):
        valid_value = (
            self.state is MetricState.VALUE
            and _valid_decimal_text(self.value)
        ) or (
            self.state is MetricState.UNAVAILABLE
            and self.value is None
        )
        if not (
            _valid_id(self.metric_id)
            and isinstance(self.unit, MetricUnit)
            and isinstance(self.state, MetricState)
            and valid_value
            and _valid_sha(self.source_metric_sha256)
            and self.display_only is True
        ):
            raise DashboardContractError("Dashboard metric value is invalid")

    def as_record(self):
        return {
            "metric_id": self.metric_id,
            "value": self.value,
            "unit": self.unit.value,
            "state": self.state.value,
            "source_metric_sha256": self.source_metric_sha256,
            "display_only": self.display_only,
        }


@dataclass(frozen=True, slots=True)
class DashboardSegmentRow:
    """One descriptive segment row with the frozen strategy-evidence label."""

    segment_id: str
    dimension: str
    label: str
    completed_trade_count: int
    net_pnl: str | None
    source_segment_sha256: str
    strategy_evidence: StrategyEvidenceState = (
        StrategyEvidenceState.INSUFFICIENT_EVIDENCE
    )
    display_only: bool = True

    def __post_init__(self):
        if not (
            _valid_id(self.segment_id)
            and _valid_field_key(self.dimension)
            and _valid_text(self.label)
            and type(self.completed_trade_count) is int
            and 0 <= self.completed_trade_count <= MAX_TRADE_ROWS
            and (self.net_pnl is None or _valid_decimal_text(self.net_pnl))
            and _valid_sha(self.source_segment_sha256)
            and self.strategy_evidence
            is StrategyEvidenceState.INSUFFICIENT_EVIDENCE
            and self.display_only is True
        ):
            raise DashboardContractError("Dashboard segment row is invalid")
        _reject_authority_field_name(self.dimension)

    def as_record(self):
        return {
            "segment_id": self.segment_id,
            "dimension": self.dimension,
            "label": self.label,
            "completed_trade_count": self.completed_trade_count,
            "net_pnl": self.net_pnl,
            "source_segment_sha256": self.source_segment_sha256,
            "strategy_evidence": self.strategy_evidence.value,
            "display_only": self.display_only,
        }


@dataclass(frozen=True, slots=True)
class DashboardDiagnostic:
    """One bounded sanitized diagnostic display row."""

    diagnostic_id: str
    code: str
    severity: DiagnosticSeverity
    message: str
    source_diagnostic_sha256: str
    display_only: bool = True

    def __post_init__(self):
        if not (
            _valid_id(self.diagnostic_id)
            and _valid_id(self.code)
            and isinstance(self.severity, DiagnosticSeverity)
            and _valid_text(self.message)
            and _valid_sha(self.source_diagnostic_sha256)
            and self.display_only is True
        ):
            raise DashboardContractError("Dashboard diagnostic is invalid")

    def as_record(self):
        return {
            "diagnostic_id": self.diagnostic_id,
            "code": self.code,
            "severity": self.severity.value,
            "message": self.message,
            "source_diagnostic_sha256": self.source_diagnostic_sha256,
            "display_only": self.display_only,
        }


@dataclass(frozen=True, slots=True)
class DashboardView:
    """Canonical P8 view contract; it contains display data and zero authority."""

    source: DashboardSourceIdentity
    safety_banner: DashboardSafetyBanner
    overview_cards: tuple[DashboardOverviewCard, ...]
    trade_rows: tuple[DashboardTradeRow, ...]
    metric_values: tuple[DashboardMetricValue, ...]
    segment_rows: tuple[DashboardSegmentRow, ...]
    diagnostics: tuple[DashboardDiagnostic, ...]
    policy: DashboardPolicy = field(default_factory=DashboardPolicy)

    def __post_init__(self):
        collections = (
            (self.overview_cards, DashboardOverviewCard, MAX_OVERVIEW_CARDS, "Overview cards"),
            (self.trade_rows, DashboardTradeRow, MAX_TRADE_ROWS, "Trade rows"),
            (self.metric_values, DashboardMetricValue, MAX_METRIC_VALUES, "Metric values"),
            (self.segment_rows, DashboardSegmentRow, MAX_SEGMENT_ROWS, "Segment rows"),
            (self.diagnostics, DashboardDiagnostic, MAX_DIAGNOSTICS, "Diagnostics"),
        )
        if not (
            isinstance(self.source, DashboardSourceIdentity)
            and isinstance(self.safety_banner, DashboardSafetyBanner)
            and isinstance(self.policy, DashboardPolicy)
        ):
            raise DashboardContractError("Dashboard view root identity is invalid")
        for items, expected_type, maximum, label in collections:
            if (
                type(items) is not tuple
                or len(items) > maximum
                or any(not isinstance(item, expected_type) for item in items)
            ):
                raise DashboardContractError(f"{label} collection is invalid")

        _ordered_unique(self.overview_cards, lambda item: item.card_id, "Overview cards")
        _ordered_unique(self.trade_rows, lambda item: item.trade_id, "Trade rows")
        _ordered_unique(self.metric_values, lambda item: item.metric_id, "Metric values")
        _ordered_unique(self.segment_rows, lambda item: item.segment_id, "Segment rows")
        _ordered_unique(self.diagnostics, lambda item: item.diagnostic_id, "Diagnostics")

        if any(item.symbol != self.source.symbol for item in self.trade_rows):
            raise DashboardContractError(
                "Dashboard trade rows contain cross-symbol material"
            )
        if any(
            item.strategy_evidence
            is not StrategyEvidenceState.INSUFFICIENT_EVIDENCE
            for item in self.segment_rows
        ):
            raise DashboardContractError(
                "Dashboard segment attempts to upgrade strategy evidence"
            )

    def as_record(self):
        return {
            "schema_version": DASHBOARD_SCHEMA_VERSION,
            "source": self.source.as_record(),
            "safety_banner": self.safety_banner.as_record(),
            "overview_cards": [item.as_record() for item in self.overview_cards],
            "trade_rows": [item.as_record() for item in self.trade_rows],
            "metric_values": [item.as_record() for item in self.metric_values],
            "segment_rows": [item.as_record() for item in self.segment_rows],
            "diagnostics": [item.as_record() for item in self.diagnostics],
            "strategy_evidence": self.source.strategy_evidence.value,
            "policy": self.policy.as_record(),
        }

    @property
    def view_sha256(self):
        return _sha256(self.as_record())


def build_dashboard_view(
    source,
    *,
    overview_cards=(),
    trade_rows=(),
    metric_values=(),
    segment_rows=(),
    diagnostics=(),
    safety_banner=None,
    policy=None,
):
    """Build one immutable display-only view from already accepted display material."""

    if safety_banner is None:
        safety_banner = DashboardSafetyBanner()
    if policy is None:
        policy = DashboardPolicy()
    return DashboardView(
        source,
        safety_banner,
        overview_cards,
        trade_rows,
        metric_values,
        segment_rows,
        diagnostics,
        policy,
    )


def dashboard_view_from_record(record):
    """Reconstruct only the exact P8-001 canonical schema; reject schema smuggling."""

    top_keys = (
        "schema_version",
        "source",
        "safety_banner",
        "overview_cards",
        "trade_rows",
        "metric_values",
        "segment_rows",
        "diagnostics",
        "strategy_evidence",
        "policy",
    )
    _expect_record(record, top_keys, "Dashboard view")
    if record["schema_version"] != DASHBOARD_SCHEMA_VERSION:
        raise DashboardContractError("Dashboard schema version is unsupported")

    source_keys = (
        "source_id",
        "symbol",
        "export_schema_version",
        "observed_at_ms",
        "export_sha256",
        "source_kind",
        "quality_status",
        "accepted",
        "sanitized",
        "read_only",
        "strategy_evidence",
    )
    _expect_record(record["source"], source_keys, "Dashboard source")
    source_data = dict(record["source"])
    try:
        source_data["strategy_evidence"] = StrategyEvidenceState(
            source_data["strategy_evidence"]
        )
        source = DashboardSourceIdentity(**source_data)

        banner_keys = tuple(DashboardSafetyBanner.__dataclass_fields__)
        _expect_record(record["safety_banner"], banner_keys, "Dashboard safety banner")
        banner = DashboardSafetyBanner(**record["safety_banner"])

        policy_keys = tuple(DashboardPolicy.__dataclass_fields__)
        _expect_record(record["policy"], policy_keys, "Dashboard policy")
        policy = DashboardPolicy(**record["policy"])

        overview = []
        overview_keys = tuple(DashboardOverviewCard.__dataclass_fields__)
        for item in record["overview_cards"]:
            _expect_record(item, overview_keys, "Dashboard overview card")
            data = dict(item)
            data["display_kind"] = OverviewDisplayKind(data["display_kind"])
            overview.append(DashboardOverviewCard(**data))

        trades = []
        trade_keys = tuple(DashboardTradeRow.__dataclass_fields__)
        for item in record["trade_rows"]:
            _expect_record(item, trade_keys, "Dashboard trade row")
            trades.append(DashboardTradeRow(**item))

        metrics = []
        metric_keys = tuple(DashboardMetricValue.__dataclass_fields__)
        for item in record["metric_values"]:
            _expect_record(item, metric_keys, "Dashboard metric value")
            data = dict(item)
            data["unit"] = MetricUnit(data["unit"])
            data["state"] = MetricState(data["state"])
            metrics.append(DashboardMetricValue(**data))

        segments = []
        segment_keys = tuple(DashboardSegmentRow.__dataclass_fields__)
        for item in record["segment_rows"]:
            _expect_record(item, segment_keys, "Dashboard segment row")
            data = dict(item)
            data["strategy_evidence"] = StrategyEvidenceState(
                data["strategy_evidence"]
            )
            segments.append(DashboardSegmentRow(**data))

        diagnostics = []
        diagnostic_keys = tuple(DashboardDiagnostic.__dataclass_fields__)
        for item in record["diagnostics"]:
            _expect_record(item, diagnostic_keys, "Dashboard diagnostic")
            data = dict(item)
            data["severity"] = DiagnosticSeverity(data["severity"])
            diagnostics.append(DashboardDiagnostic(**data))
    except (DashboardContractError, TypeError, ValueError) as exc:
        if isinstance(exc, DashboardContractError):
            raise
        raise DashboardContractError(
            "Dashboard canonical record reconstruction failed"
        ) from None

    if record["strategy_evidence"] != source.strategy_evidence.value:
        raise DashboardContractError("Dashboard strategy-evidence label is inconsistent")

    return DashboardView(
        source,
        banner,
        tuple(overview),
        tuple(trades),
        tuple(metrics),
        tuple(segments),
        tuple(diagnostics),
        policy,
    )
