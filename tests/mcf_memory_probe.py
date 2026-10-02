"""Manual synthetic allocation/RSS comparison. No data reader or candidate run.

Run from repository root with PYTHONPATH=tests:. using the locked Python runner.
Each invocation must be a fresh process. Optional tracemalloc numbers include
only the measured operation, excluding preconstructed immutable synthetic bars.
"""
import argparse
import gc
import json
import resource
import tracemalloc
from pathlib import Path
from unittest.mock import patch

from research.mass_candidate_factory.production_features import ProductionBars, ProductionFeatureCache
from mcf_memory_baseline import legacy_validate, LegacyProductionFeatureCache
from test_mcf_feature_cache_memory import synthetic_bars


def rss_kib():
    return int(next(line.split()[1] for line in Path('/proc/self/status').read_text().splitlines()
                    if line.startswith('VmRSS:')))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('baseline', 'remediated'))
    parser.add_argument('operation', choices=('validate', 'cache'))
    parser.add_argument('--rows', type=int, default=90000)
    parser.add_argument('--symbols', type=int, default=4)
    parser.add_argument('--trace-allocation', action='store_true')
    args = parser.parse_args()
    if not 2 <= args.rows <= 90000 or not 1 <= args.symbols <= 8:
        parser.error('bounded synthetic fixture requires 2..90000 rows and 1..8 symbols')
    bars = [synthetic_bars(f'ASSET{i}USDT', rows=args.rows, timeframe='15m', gaps=False)
            for i in range(args.symbols)]
    gc.collect()
    before_rss = rss_kib()
    before_peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if args.trace_allocation:
        tracemalloc.start()
    retained = []
    validate = legacy_validate if args.mode == 'baseline' else ProductionBars.validate
    cache = LegacyProductionFeatureCache if args.mode == 'baseline' else ProductionFeatureCache
    with patch.object(ProductionBars, 'validate', validate):
        for b in bars:
            if args.operation == 'validate':
                b.validate()
            else:
                retained.append(cache(b))
    current = peak = None
    if args.trace_allocation:
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
    print(json.dumps({'fixture': 'SYNTHETIC_ONLY', 'mode': args.mode, 'operation': args.operation,
                      'rows_per_symbol': args.rows, 'symbols': args.symbols,
                      'rss_before_kib': before_rss, 'rss_after_kib': rss_kib(),
                      'process_peak_before_kib': before_peak,
                      'process_peak_after_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                      'traced_current_bytes': current, 'traced_peak_bytes': peak}, sort_keys=True))


if __name__ == '__main__':
    main()
