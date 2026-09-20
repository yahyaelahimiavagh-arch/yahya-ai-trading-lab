"""Deterministic P8-004 completed-trade table projection from accepted P7 metrics."""

import hashlib
import json
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from enum import Enum

from .contracts import DashboardSourceIdentity, MAX_TRADE_ROWS
from .loader import LoadedP7Export


TRADE_TABLE_SCHEMA_VERSION = 1
MAX_PAGE_SIZE = 100
_HEX = frozenset("0123456789abcdef")
_TRADE_METRIC_KEYS = frozenset((
    "trade_index",
    "trade_sha256",
    "realized_pnl_quote",
    "entry_gross_quote",
    "exit_gross_quote",
    "entry_cash_out_quote",
    "gross_return",
    "net_return",
    "total_fee_quote",
    "total_slippage_quote",
    "holding_time_ms",
))


class TradeOutcomeFilter(str, Enum):
    ALL = "ALL"
    WIN = "WIN"
    LOSS = "LOSS"
    BREAKEVEN = "BREAKEVEN"


class TradeSortKey(str, Enum):
    TRADE_INDEX = "TRADE_INDEX"
    NET_PNL = "NET_PNL"
    HOLDING_TIME = "HOLDING_TIME"


class TradeSortDirection(str, Enum):
    ASC = "ASC"
    DESC = "DESC"


class TradeTableProjectionError(ValueError):
    """Accepted completed-trade table material is invalid or ambiguous."""


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


def _decimal(value):
    if not isinstance(value, str) or not value or value != value.strip():
        raise TradeTableProjectionError("Trade metric decimal is invalid")
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        raise TradeTableProjectionError("Trade metric decimal is invalid") from None
    if not parsed.is_finite():
        raise TradeTableProjectionError("Trade metric decimal is invalid")
    return parsed


def _outcome(net_pnl):
    number = _decimal(net_pnl)
    if number > 0:
        return "WIN"
    if number < 0:
        return "LOSS"
    return "BREAKEVEN"


@dataclass(frozen=True, slots=True)
class TradeTableQuery:
    """Bounded deterministic filter/sort/page request with no execution authority."""

    outcome: TradeOutcomeFilter = TradeOutcomeFilter.ALL
    sort_key: TradeSortKey = TradeSortKey.TRADE_INDEX
    direction: TradeSortDirection = TradeSortDirection.ASC
    offset: int = 0
    page_size: int = 50

    def __post_init__(self):
        if (
            not isinstance(self.outcome, TradeOutcomeFilter)
            or not isinstance(self.sort_key, TradeSortKey)
            or not isinstance(self.direction, TradeSortDirection)
            or type(self.offset) is not int
            or not 0 <= self.offset <= MAX_TRADE_ROWS
            or type(self.page_size) is not int
            or not 1 <= self.page_size <= MAX_PAGE_SIZE
        ):
            raise TradeTableProjectionError("Trade table query is invalid")

    def as_record(self):
        return {
            "outcome": self.outcome.value,
            "sort_key": self.sort_key.value,
            "direction": self.direction.value,
            "offset": self.offset,
            "page_size": self.page_size,
        }


@dataclass(frozen=True, slots=True)
class DashboardCompletedTradeMetricRow:
    """Exact accepted P7 completed-trade metric row; no missing execution fields invented."""

    row_id: str
    trade_index: int
    symbol: str
    net_pnl: str
    entry_gross_quote: str
    exit_gross_quote: str
    entry_cash_out_quote: str
    gross_return: str
    net_return: str
    fee_total: str
    slippage_total: str
    holding_time_ms: int
    outcome: str
    source_trade_sha256: str
    source_metric_sha256: str
    side: str = "LONG"
    status: str = "COMPLETED"
    paper: bool = True
    display_only: bool = True
    strategy_evidence: str = "INSUFFICIENT_EVIDENCE"

    def __post_init__(self):
        if (
            not isinstance(self.row_id, str)
            or not self.row_id.startswith("TRADE_")
            or len(self.row_id) != 14
            or not self.row_id[6:].isdigit()
            or type(self.trade_index) is not int
            or self.trade_index < 0
            or self.symbol not in ("BTCUSDT", "ETHUSDT")
            or self.outcome not in ("WIN", "LOSS", "BREAKEVEN")
            or not _valid_sha(self.source_trade_sha256)
            or not _valid_sha(self.source_metric_sha256)
            or type(self.holding_time_ms) is not int
            or self.holding_time_ms < 0
            or self.side != "LONG"
            or self.status != "COMPLETED"
            or self.paper is not True
            or self.display_only is not True
            or self.strategy_evidence != "INSUFFICIENT_EVIDENCE"
        ):
            raise TradeTableProjectionError("Completed trade row identity is invalid")
        for value in (
            self.net_pnl,
            self.entry_gross_quote,
            self.exit_gross_quote,
            self.entry_cash_out_quote,
            self.gross_return,
            self.net_return,
            self.fee_total,
            self.slippage_total,
        ):
            _decimal(value)
        if (
            _decimal(self.entry_gross_quote) <= 0
            or _decimal(self.exit_gross_quote) <= 0
            or _decimal(self.entry_cash_out_quote) <= 0
            or _decimal(self.fee_total) < 0
            or _decimal(self.slippage_total) < 0
            or self.outcome != _outcome(self.net_pnl)
        ):
            raise TradeTableProjectionError("Completed trade row economics are invalid")

    def as_record(self):
        return {
            "row_id": self.row_id,
            "trade_index": self.trade_index,
            "symbol": self.symbol,
            "net_pnl": self.net_pnl,
            "entry_gross_quote": self.entry_gross_quote,
            "exit_gross_quote": self.exit_gross_quote,
            "entry_cash_out_quote": self.entry_cash_out_quote,
            "gross_return": self.gross_return,
            "net_return": self.net_return,
            "fee_total": self.fee_total,
            "slippage_total": self.slippage_total,
            "holding_time_ms": self.holding_time_ms,
            "outcome": self.outcome,
            "source_trade_sha256": self.source_trade_sha256,
            "source_metric_sha256": self.source_metric_sha256,
            "side": self.side,
            "status": self.status,
            "paper": self.paper,
            "display_only": self.display_only,
            "strategy_evidence": self.strategy_evidence,
        }


@dataclass(frozen=True, slots=True)
class CompletedTradeTableProjection:
    """One bounded deterministic page of completed accepted P7 trades."""

    source: DashboardSourceIdentity
    query: TradeTableQuery
    rows: tuple[DashboardCompletedTradeMetricRow, ...]
    total_completed: int
    total_filtered: int
    returned_count: int
    has_more: bool
    source_metrics_sha256: str
    noncompleted_policy: str = "SEPARATE_NOT_PROJECTED_FROM_P7_TRADE_METRICS"
    schema_version: int = TRADE_TABLE_SCHEMA_VERSION

    def __post_init__(self):
        if (
            not isinstance(self.source, DashboardSourceIdentity)
            or not isinstance(self.query, TradeTableQuery)
            or type(self.rows) is not tuple
            or len(self.rows) > self.query.page_size
            or len(self.rows) > MAX_PAGE_SIZE
            or any(
                not isinstance(item, DashboardCompletedTradeMetricRow)
                for item in self.rows
            )
            or any(item.symbol != self.source.symbol for item in self.rows)
            or type(self.total_completed) is not int
            or not 0 <= self.total_completed <= MAX_TRADE_ROWS
            or type(self.total_filtered) is not int
            or not 0 <= self.total_filtered <= self.total_completed
            or type(self.returned_count) is not int
            or self.returned_count != len(self.rows)
            or type(self.has_more) is not bool
            or self.has_more
            != (self.query.offset + self.returned_count < self.total_filtered)
            or not _valid_sha(self.source_metrics_sha256)
            or self.noncompleted_policy
            != "SEPARATE_NOT_PROJECTED_FROM_P7_TRADE_METRICS"
            or self.schema_version != TRADE_TABLE_SCHEMA_VERSION
        ):
            raise TradeTableProjectionError("Completed trade table projection is invalid")
        row_ids = tuple(item.row_id for item in self.rows)
        trade_ids = tuple(item.source_trade_sha256 for item in self.rows)
        if len(set(row_ids)) != len(row_ids) or len(set(trade_ids)) != len(trade_ids):
            raise TradeTableProjectionError("Completed trade page contains duplicate identity")

    def as_record(self):
        return {
            "schema_version": self.schema_version,
            "source": self.source.as_record(),
            "query": self.query.as_record(),
            "rows": [item.as_record() for item in self.rows],
            "total_completed": self.total_completed,
            "total_filtered": self.total_filtered,
            "returned_count": self.returned_count,
            "has_more": self.has_more,
            "source_metrics_sha256": self.source_metrics_sha256,
            "noncompleted_policy": self.noncompleted_policy,
        }

    @property
    def table_sha256(self):
        return _digest(self.as_record())


def _verify_loaded_export(loaded):
    if not isinstance(loaded, LoadedP7Export):
        raise TradeTableProjectionError("Trade table requires one validated P7 export")
    try:
        record = loaded.record()
        material = {
            "schema_version": record["schema_version"],
            "quality": record["quality"],
            "analytics": record["analytics"],
        }
        quality = record["quality"]
        analytics = record["analytics"]
        chain = quality["accepted_chain"]
        metrics = analytics["trade_metrics"]
    except (KeyError, TypeError, ValueError):
        raise TradeTableProjectionError("Loaded P7 export binding is invalid") from None

    if (
        record.get("export_sha256") != loaded.export_sha256
        or _digest(material) != loaded.export_sha256
        or _digest(quality) != loaded.quality_sha256
        or _digest(analytics) != loaded.segmentation_sha256
        or loaded.source.export_sha256 != loaded.export_sha256
        or loaded.source.symbol != analytics.get("symbol")
        or loaded.source.observed_at_ms != quality.get("snapshot_time_ms")
        or quality.get("status") != "PASS"
        or quality.get("publication_allowed") is not True
        or quality.get("strategy_evidence") != "INSUFFICIENT_EVIDENCE"
        or analytics.get("strategy_evidence") != "INSUFFICIENT_EVIDENCE"
        or not isinstance(chain, dict)
        or chain.get("symbol") != loaded.source.symbol
        or chain.get("segmentation_sha256") != loaded.segmentation_sha256
        or chain.get("metrics_sha256") != analytics.get("metrics_sha256")
        or type(metrics) is not list
        or len(metrics) > MAX_TRADE_ROWS
        or chain.get("completed_trade_count") != len(metrics)
    ):
        raise TradeTableProjectionError("Loaded P7 trade provenance changed")

    identities = []
    indexes = []
    for metric in metrics:
        if (
            not isinstance(metric, dict)
            or frozenset(metric) != _TRADE_METRIC_KEYS
            or type(metric["trade_index"]) is not int
            or metric["trade_index"] < 0
            or not _valid_sha(metric["trade_sha256"])
            or type(metric["holding_time_ms"]) is not int
            or metric["holding_time_ms"] < 0
        ):
            raise TradeTableProjectionError("Accepted P7 trade metric is invalid")
        for field_name in (
            "realized_pnl_quote",
            "entry_gross_quote",
            "exit_gross_quote",
            "entry_cash_out_quote",
            "gross_return",
            "net_return",
            "total_fee_quote",
            "total_slippage_quote",
        ):
            _decimal(metric[field_name])
        identities.append(metric["trade_sha256"])
        indexes.append(metric["trade_index"])
    if (
        len(set(identities)) != len(identities)
        or len(set(indexes)) != len(indexes)
        or indexes != sorted(indexes)
    ):
        raise TradeTableProjectionError("Accepted P7 trade identities are invalid")
    return analytics, tuple(metrics)


def _row(symbol, metric):
    metric_sha256 = _digest({
        "schema_version": TRADE_TABLE_SCHEMA_VERSION,
        "trade_metric": metric,
    })
    return DashboardCompletedTradeMetricRow(
        row_id=f"TRADE_{metric['trade_index']:08d}",
        trade_index=metric["trade_index"],
        symbol=symbol,
        net_pnl=metric["realized_pnl_quote"],
        entry_gross_quote=metric["entry_gross_quote"],
        exit_gross_quote=metric["exit_gross_quote"],
        entry_cash_out_quote=metric["entry_cash_out_quote"],
        gross_return=metric["gross_return"],
        net_return=metric["net_return"],
        fee_total=metric["total_fee_quote"],
        slippage_total=metric["total_slippage_quote"],
        holding_time_ms=metric["holding_time_ms"],
        outcome=_outcome(metric["realized_pnl_quote"]),
        source_trade_sha256=metric["trade_sha256"],
        source_metric_sha256=metric_sha256,
    )


def apply_trade_table_query(rows, query):
    """Filter, sort and page immutable completed rows deterministically."""

    if type(rows) is not tuple or len(rows) > MAX_TRADE_ROWS:
        raise TradeTableProjectionError("Completed trade row collection is invalid")
    if any(not isinstance(item, DashboardCompletedTradeMetricRow) for item in rows):
        raise TradeTableProjectionError("Completed trade row collection is invalid")
    if not isinstance(query, TradeTableQuery):
        raise TradeTableProjectionError("Trade table query is invalid")
    row_ids = tuple(item.row_id for item in rows)
    trade_ids = tuple(item.source_trade_sha256 for item in rows)
    if len(set(row_ids)) != len(row_ids) or len(set(trade_ids)) != len(trade_ids):
        raise TradeTableProjectionError("Completed trade collection contains duplicate identity")

    if query.outcome is TradeOutcomeFilter.ALL:
        filtered = list(rows)
    else:
        filtered = [
            item for item in rows
            if item.outcome == query.outcome.value
        ]

    filtered.sort(key=lambda item: (item.trade_index, item.source_trade_sha256))
    if query.sort_key is TradeSortKey.NET_PNL:
        filtered.sort(
            key=lambda item: _decimal(item.net_pnl),
            reverse=query.direction is TradeSortDirection.DESC,
        )
    elif query.sort_key is TradeSortKey.HOLDING_TIME:
        filtered.sort(
            key=lambda item: item.holding_time_ms,
            reverse=query.direction is TradeSortDirection.DESC,
        )
    elif query.direction is TradeSortDirection.DESC:
        filtered.reverse()

    start = query.offset
    end = min(start + query.page_size, len(filtered))
    return tuple(filtered[start:end]), len(filtered)


def project_completed_trade_table(loaded, query=None):
    """Project bounded completed-trade rows without inventing absent execution fields."""

    if query is None:
        query = TradeTableQuery()
    if not isinstance(query, TradeTableQuery):
        raise TradeTableProjectionError("Trade table query is invalid")

    analytics, metrics = _verify_loaded_export(loaded)
    all_rows = tuple(_row(analytics["symbol"], metric) for metric in metrics)
    page, total_filtered = apply_trade_table_query(all_rows, query)
    return CompletedTradeTableProjection(
        source=loaded.source,
        query=query,
        rows=page,
        total_completed=len(all_rows),
        total_filtered=total_filtered,
        returned_count=len(page),
        has_more=query.offset + len(page) < total_filtered,
        source_metrics_sha256=analytics["metrics_sha256"],
    )
