"""Bounded synthetic engineering benchmark. No acquisition or selection."""
from __future__ import annotations

import json
import time
import tracemalloc

from research.crisis_lab.acquisition import CanonicalRow, _canonical_csv

from .index import build_index
from .lifecycle import Lifecycle
from .liquidity import compute
from .quality import admit
from .views import derive


def run() -> dict:
    start = 1_700_000_000_000 // 86_400_000 * 86_400_000
    cadence = 900_000
    n = 384
    symbols = ('BTCUSDT', 'ETHUSDT', 'TESTUSDT')
    tracemalloc.start()
    beginning = time.perf_counter()
    records, bindings = [], []
    validation_seconds = 0.0
    for symbol in symbols:
        rows = tuple(CanonicalRow((str(start+i*cadence), '9', '11', '8', '10', '2',
                                   str(start+(i+1)*cadence-1), '20', '3', '1', '10', '0'))
                     for i in range(n) if not (symbol == 'TESTUSDT' and i == 100))
        t = time.perf_counter()
        bound = admit(dataset_id=f'{symbol}/15m/engineering-v1', symbol=symbol, interval='15m',
                      rows=rows, source='SYNTHETIC_FIXTURE', requested_start_ms=start,
                      requested_end_ms=start+n*cadence, retrieved_at_ms=start+(n+1)*cadence,
                      source_refs=('fixture://AF-01B-CALIBRATION-001',), allow_gaps=True)
        validation_seconds += time.perf_counter()-t
        bindings.append(bound)
        records.append(Lifecycle(symbol, symbol[:-4], 'USDT', 'BINANCE_SPOT', 'SPOT',
                                 True, False, start, rows[-1].open_time_ms, None, None,
                                 'INACTIVE', ('fixture://lifecycle',)).frozen())
    t = time.perf_counter()
    index = build_index(tuple(records), tuple(bindings))
    index_seconds = time.perf_counter()-t
    t = time.perf_counter()
    views = tuple(derive(b[0].rows, b[0].symbol, b[0].dataset_id+'/1h', '15m', '1h',
                         as_of_ms=start+(n+1)*cadence) for b in bindings)
    view_seconds = time.perf_counter()-t
    t = time.perf_counter()
    metrics = [compute(b[0], ending_ms=start+i*cadence, window_bars=8)
               for b in bindings for i in range(8, n)]
    liquidity_seconds = time.perf_counter()-t
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    rebuild = build_index(tuple(reversed(records)), tuple(reversed(bindings)))
    total_rows = sum(len(b[0].rows) for b in bindings)
    result = dict(calibration_id='AF-01B-ENGINEERING-CALIBRATION-001',
                  state='ENGINEERING_ONLY_NO_SELECTION', symbols=len(symbols), rows=total_rows,
                  validation_rows_per_second=round(total_rows/validation_seconds, 2),
                  validation_seconds=round(validation_seconds, 6),
                  index_build_seconds=round(index_seconds, 6),
                  derived_view_rows=sum(len(v[0]) for v in views),
                  derived_view_rows_per_second=round(sum(len(v[0]) for v in views)/view_seconds, 2),
                  derived_view_seconds=round(view_seconds, 6),
                  liquidity_metrics=len(metrics),
                  liquidity_metrics_per_second=round(len(metrics)/liquidity_seconds, 2),
                  liquidity_seconds=round(liquidity_seconds, 6),
                  peak_tracemalloc_bytes=peak,
                  canonical_fixture_bytes=sum(len(_canonical_csv(b[0].rows)) for b in bindings),
                  deterministic_rebuild=index.index_sha256 == rebuild.index_sha256,
                  known_gap_count=bindings[2][1].gap_count,
                  elapsed_seconds=round(time.perf_counter()-beginning, 6))
    assert result['deterministic_rebuild'] and result['known_gap_count'] == 1
    return result


if __name__ == '__main__':
    print(json.dumps(run(), sort_keys=True))
