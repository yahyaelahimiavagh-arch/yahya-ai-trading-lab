"""Bounded synthetic signal compilation probe; never a production capacity test.

Run each mode in a fresh process with PYTHONPATH=tests:.
RSS and tracemalloc must be measured in separate invocations.
"""
import argparse
import gc
import json
import resource
import sys
from itertools import chain
import tracemalloc
from pathlib import Path
from unittest.mock import patch

from research.mass_candidate_factory.production_features import ProductionFeatureCache
from test_mcf_feature_cache_memory import synthetic_bars
from test_mcf_signal_memory import frozen_fixture, runtime
from test_mcf_production_runtime import binding
from research.mass_candidate_factory.production import MembershipSnapshot, DEVELOPMENT_START_MS
from dataclasses import replace
import mcf_signal_memory_baseline_runtime as baseline
from research.mass_candidate_factory import production_runtime as remediated


def rss():
    return int(next(line.split()[1] for line in Path('/proc/self/status').read_text().splitlines() if line.startswith('VmRSS:')))


def cache_bytes(caches):
    # Unique candidate-derived arrays/floats only; shared source bars excluded.
    seen=set();size=0
    for cache in caches.values():
        for values in cache._cache.values():
            for value in chain((values,),values):
                if id(value) in seen or value is None:
                    continue
                seen.add(id(value));size+=sys.getsizeof(value)
    return size


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('baseline','remediated'))
    parser.add_argument('--rows',type=int,default=90000)
    parser.add_argument('--symbols',type=int,default=8)
    parser.add_argument('--trace-allocation',action='store_true')
    args=parser.parse_args()
    if not 2<=args.rows<=90000 or not 2<=args.symbols<=16:
        parser.error('bounded synthetic fixture: rows 2..90000, symbols 2..16')
    symbols=tuple(f'ASSET{i:02d}USDT' for i in range(args.symbols))
    matrix={s:synthetic_bars(s,rows=args.rows,timeframe='15m',gaps=False) for s in symbols}
    bound=replace(binding(),membership_snapshots=(MembershipSnapshot(DEVELOPMENT_START_MS,symbols,'a'*64),))
    # Same stress shape/parameter vector, deliberately distinct synthetic identity.
    freeze=frozen_fixture([('SESSION_TIME_EFFECT',{'return_lookback':1,'return_threshold':'0',
                          'session_start_utc':0,'session_length_hours':4})],'15m')
    module=baseline if args.mode=='baseline' else remediated
    obj=runtime(module.ProductionRuntime,freeze,matrix,bound)
    caches=obj._timeframe_caches('15m')
    gc.collect();before_rss=rss();before_cache=cache_bytes(caches)
    if args.trace_allocation:tracemalloc.start()
    records=[];compiler=module.compile_candidate
    def compile(*params,**kwargs):
        current_before=tracemalloc.get_traced_memory()[0] if args.trace_allocation else None
        if args.trace_allocation:tracemalloc.reset_peak()
        out=compiler(*params,**kwargs)
        current,peak=tracemalloc.get_traced_memory() if args.trace_allocation else (None,None)
        records.append({'symbol':out.symbol,'rss_after_compile_kib':rss(),
                        'traced_before_bytes':current_before,'traced_after_compile_bytes':current,
                        'traced_symbol_peak_bytes':peak})
        return out
    original_clear=ProductionFeatureCache.clear_transient
    def clear(cache):
        original_clear(cache)
        if records and records[-1]['symbol']==cache.bars.symbol and 'traced_after_release_bytes' not in records[-1]:
            records[-1]['traced_after_release_bytes']=tracemalloc.get_traced_memory()[0] if args.trace_allocation else None
            records[-1]['rss_after_release_kib']=rss()
    def no_simulation(**kwargs):
        # Exact signal outputs retained; no accounting, simulation, profitability.
        return kwargs['series_by_symbol']
    with patch.object(module,'compile_candidate',compile),patch.object(module,'run_candidate',no_simulation), \
            patch.object(ProductionFeatureCache,'clear_transient',clear):
        series=obj.run(freeze['executable'][0]['candidate_id'],director_authorized=True)
    current=tracemalloc.get_traced_memory()[0] if args.trace_allocation else None
    if args.trace_allocation:tracemalloc.stop()
    owned_series=sum(sys.getsizeof(s.desired_state)+sys.getsizeof(s.feature_available)+sys.getsizeof(s) for s in series.values())
    print(json.dumps({'evidence':'SYNTHETIC_ONLY_NOT_PRODUCTION_CAPACITY','mode':args.mode,
        'rows_per_symbol':args.rows,'symbols':args.symbols,'rss_before_kib':before_rss,'rss_after_kib':rss(),
        'process_peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        'feature_cache_bytes_before':before_cache,'feature_cache_bytes_after':cache_bytes(caches),
        'series_owned_bytes':owned_series,'traced_total_retained_bytes':current,
        'traced_compilation_peak_bytes':max((r['traced_symbol_peak_bytes'] for r in records),default=None) if args.trace_allocation else None,
        'per_symbol':records},sort_keys=True))


if __name__=='__main__':main()
