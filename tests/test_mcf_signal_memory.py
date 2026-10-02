"""Exact synthetic-only signal memory regression. No real runner or market files."""
import ast
import copy
import gc
import io
import json
import os
import subprocess
import sys
import tracemalloc
import unittest
from dataclasses import asdict, replace
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path
from unittest.mock import patch

from research.mass_candidate_factory import production_runtime as runtime_module
from research.mass_candidate_factory import production_rules as rules
from research.mass_candidate_factory.models import canonical, digest, MCFError
from research.mass_candidate_factory.production import (
    CADENCE_MS, DEVELOPMENT_START_MS, MembershipSnapshot, ProductionSeries,
)
from research.mass_candidate_factory.production_features import ProductionFeatureCache
from research.mass_candidate_factory.production_runner_input import FrozenRunnerInput
from research.mass_candidate_factory.production_memory_diagnostic import CHECKPOINT_KEYS, CheckpointSink, validate_checkpoint
from research.mass_candidate_factory.production_memory_telemetry import engineering_telemetry
from test_mcf_feature_cache_memory import FAMILIES, synthetic_bars, allocation_peak, validation_outcome
from test_mcf_production_runtime import binding, freeze_artifact
import mcf_signal_memory_baseline_rules as old_rules
import mcf_signal_memory_baseline_runtime as old_runtime
from mcf_signal_memory_baseline_validation import legacy_series_validate

APRIL = 1585699200000


def fixture(timeframe='1h', rows=320, gaps=True):
    matrix = {}
    for symbol in ('AAAUSDT', 'BBBUSDT', 'BTCUSDT', 'ETHUSDT'):
        b = synthetic_bars(symbol, rows=rows, timeframe=timeframe, gaps=gaps and symbol!='ETHUSDT')
        start = APRIL - 150 * CADENCE_MS[timeframe]
        # Shift source times without filling the two missing source bars.
        matrix[symbol] = replace(b, times=tuple(start + t - DEVELOPMENT_START_MS for t in b.times))
    bound = replace(binding(), membership_snapshots=(
        MembershipSnapshot(DEVELOPMENT_START_MS, tuple(sorted(matrix)), 'a'*64),
        MembershipSnapshot(APRIL, ('BBBUSDT', 'ETHUSDT'), 'b'*64),
    ))
    return matrix, bound


def frozen_fixture(families, timeframe='1h'):
    freeze = copy.deepcopy(freeze_artifact())
    rows = []
    for index, (family, params) in enumerate(families):
        row = copy.deepcopy(freeze['executable'][0])
        row.update(candidate_id=f'SYNTHETIC-SIGNAL-{index:06d}', family=family,
                   economic_mechanism_id=family, parameter_vector=copy.deepcopy(params),
                   timeframe=timeframe, free_parameter_dimensions=len(params))
        row['candidate_spec_sha256'] = digest(row)
        rows.append(row)
    registered = tuple((r['candidate_id'], r['candidate_spec_sha256']) for r in rows)
    graph_body = {'schema': 'MCF_PRODUCTION_NEIGHBOR_GRAPH/1.0.0',
                  'graph': {r['candidate_id']: () for r in rows}}
    graph = {**graph_body, 'neighbor_graph_sha256': digest(graph_body)}
    freeze.update(executable=tuple(rows), registered_candidates=registered, neighbor_graph=graph)
    freeze['summary'].update(candidate_ledger_sha256=digest([
        {'candidate_id': cid, 'candidate_spec_sha256': sha} for cid, sha in registered
    ]), neighbor_graph_sha256=graph['neighbor_graph_sha256'])
    return freeze


class SyntheticReader(FrozenRunnerInput):
    """Test double exercising frozen runtime reuse, without admission or filesystem I/O.

    Production admission stays unchanged. This fixture cannot load any external data.
    """
    def __init__(self, matrix):
        if any(not b.dataset_id.startswith('SYNTHETIC-') for b in matrix.values()):
            raise AssertionError('synthetic input required')
        self.matrix = matrix

    def require_runtime(self, freeze, bound, policy):
        if any(not row['candidate_id'].startswith('SYNTHETIC-') for row in freeze['executable']):
            raise AssertionError('synthetic identities required')

    def load_timeframe(self, timeframe):
        if any(b.timeframe != timeframe for b in self.matrix.values()):
            raise AssertionError('fixture timeframe mismatch')
        return self.matrix


def runtime(cls, freeze, matrix, bound):
    return cls(executable_freeze=freeze, binding=bound, bars_by_timeframe={},
               frozen_input=SyntheticReader(matrix))


def baseline_source(method, module):
    tree = ast.parse(Path(module.__file__).read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == method:
            return ast.dump(node, include_attributes=False)
    raise AssertionError(method)


class SignalMemoryTest(unittest.TestCase):
    def test_baseline_provenance_matches_accepted_main_source_hashes(self):
        # Hashes pinned to the exact accepted Git blobs, with only import routing
        # adjusted so baseline runtime invokes its own old compiler in tests.
        import hashlib
        expected = {
            'rules': '701b7d11858eed03b83474b51d501f95ff239f63fa0352c24463af2f9b68154f',
            'runtime': 'cd5f3eae41e6009b5558864330a481201489712b4f62de2ad996f8ad37b40405',
        }
        for name, sha in expected.items():
            source = Path(__file__).with_name(f'mcf_signal_memory_baseline_{name}.py').read_text().split('\n', 1)[1]
            source = source.replace('from mcf_signal_memory_baseline_rules import compile_candidate',
                                    'from research.mass_candidate_factory.production_rules import compile_candidate')
            source = source.replace('from research.mass_candidate_factory.', 'from .')
            self.assertEqual(hashlib.sha256(source.encode()).hexdigest(), sha)

        import mcf_signal_memory_baseline_validation as validator
        self.assertEqual(hashlib.sha256(baseline_source('legacy_series_validate', validator).encode()).hexdigest(),
                         'bfa284e04702fab07e7091e043418fbfdf64e722c6778928b50d8dfd4c66be41')

    def compare_sequence(self, families, timeframe):
        matrix, bound = fixture(timeframe)
        freeze = frozen_fixture(families, timeframe)
        before = runtime(old_runtime.ProductionRuntime, freeze, matrix, bound)
        after = runtime(runtime_module.ProductionRuntime, freeze, matrix, bound)
        original_bars = {s: b for s,b in matrix.items()}
        for candidate in freeze['executable']:
            captures = []
            def capture(compiler):
                def call(*args, **kwargs):
                    out = compiler(*args, **kwargs)
                    cache = args[1]
                    captures.append((cache.bars.symbol, canonical(asdict(out)), dict(cache._cache), canonical(kwargs.get("liquidity_percentile"))))
                    self.assertIs(out.times, cache.bars.times)
                    self.assertIs(out.opens, cache.bars.opens)
                    self.assertIs(out.closes, cache.bars.closes)
                    return out
                return call
            with patch.object(old_runtime, 'compile_candidate', capture(old_rules.compile_candidate)), \
                    patch.object(ProductionSeries, 'validate', legacy_series_validate):
                expected = canonical(before.run(candidate['candidate_id'], director_authorized=True))
            old_capture = list(captures); captures.clear()
            with patch.object(runtime_module, 'compile_candidate', capture(rules.compile_candidate)):
                actual = canonical(after.run(candidate['candidate_id'], director_authorized=True))
            self.assertEqual(actual, expected)
            # Old reuse has additional stale entries; every feature requested by
            # the current compiler must still be exactly equal, not just close.
            for (s,series,features,ranks), (old_s,old_series,old_features,old_ranks) in zip(captures, old_capture):
                self.assertEqual((s,series), (old_s,old_series))
                self.assertEqual(ranks, old_ranks)
                for key, values in features.items():
                    self.assertEqual(canonical(values), canonical(old_features[key]))
            for symbol, cache in after._timeframe_caches(timeframe).items():
                self.assertEqual(cache._cache, {})
                self.assertIs(cache.bars, original_bars[symbol])
            self.assertEqual(after._liquidity, {})
        return before, after

    def test_all_executable_families_exact_signals_features_and_canonical_accounting(self):
        for timeframe in ('15m','1h','4h'):
            for family,params in FAMILIES.items():
                with self.subTest(timeframe=timeframe, family=family):
                    self.compare_sequence([(family,params)], timeframe)

    def test_exact_ninth_stress_shape_parameters_on_synthetic_15m(self):
        self.compare_sequence([('SESSION_TIME_EFFECT', {'return_lookback':1,
            'return_threshold':'0','session_start_utc':0,'session_length_hours':4})], '15m')

    def test_multi_symbol_peak_and_retention_regression(self):
        root=Path(__file__).resolve().parents[1]
        env={**os.environ,'PYTHONPATH':str(root/'tests')+os.pathsep+str(root)}
        results=[]
        for mode in ('baseline','remediated'):
            raw=subprocess.check_output([sys.executable,str(root/'tests/mcf_signal_memory_probe.py'),
                mode,'--rows','5000','--symbols','4','--trace-allocation'],cwd=root,env=env)
            results.append(json.loads(raw))
        old,new=results
        self.assertEqual(old['series_owned_bytes'],new['series_owned_bytes'])
        self.assertGreater(old['feature_cache_bytes_after'],4*5000*25)
        self.assertEqual(new['feature_cache_bytes_after'],0)
        self.assertLess(new['traced_compilation_peak_bytes'],old['traced_compilation_peak_bytes']*.7)
        self.assertLess(new['traced_total_retained_bytes'],old['traced_total_retained_bytes']*.5)
        for record in new['per_symbol']:
            self.assertLess(record['traced_after_release_bytes'],record['traced_after_compile_bytes'])

    def test_sequential_different_candidates_reuse_same_runtime(self):
        families = list(FAMILIES.items())
        families += [('LEAD_LAG', {**FAMILIES['LEAD_LAG'], 'peer':'ETHUSDT','response_mode':'REVERSAL'}),
                     ('SESSION_TIME_EFFECT', {**FAMILIES['SESSION_TIME_EFFECT'], 'session_start_utc':20,'session_length_hours':4}),
                     ('TREND_CROSSOVER', {'fast_window':6,'slow_window':32}),
                     ('LIQUIDITY_CONDITIONED_ENTRY', {**FAMILIES['LIQUIDITY_CONDITIONED_ENTRY'],'liquidity_window':6})]
        self.compare_sequence(families, '1h')

    def test_release_after_last_symbol_consumer_and_before_simulation(self):
        matrix, bound = fixture()
        freeze = frozen_fixture([('LIQUIDITY_CONDITIONED_ENTRY', FAMILIES['LIQUIDITY_CONDITIONED_ENTRY'])])
        obj = runtime(runtime_module.ProductionRuntime,freeze,matrix,bound)
        original = rules.compile_candidate
        finished = []
        def compile(*args, **kwargs):
            for symbol in finished:
                self.assertFalse(obj._timeframe_caches('1h')[symbol]._cache)
            self.assertIsNotNone(kwargs['liquidity_percentile'])
            self.assertFalse(args[1]._cache) # trailing ranking sums already consumed
            result = original(*args, **kwargs)
            self.assertTrue(args[1]._cache)
            finished.append(result.symbol)
            return result
        def simulate(**kwargs):
            self.assertEqual(finished, list(matrix))
            self.assertTrue(all(not c._cache for c in obj._timeframe_caches('1h').values()))
            self.assertFalse(obj._liquidity)
            return kwargs['series_by_symbol']
        with patch.object(runtime_module,'compile_candidate',compile), patch.object(runtime_module,'run_candidate',simulate):
            result = obj.run(freeze['executable'][0]['candidate_id'],director_authorized=True)
        for out in result.values():
            out.validate()

    def test_compile_error_releases_arrays_and_runtime_can_be_reused(self):
        matrix,bound = fixture()
        freeze = frozen_fixture(list(FAMILIES.items()))
        obj = runtime(runtime_module.ProductionRuntime,freeze,matrix,bound)
        def broken(candidate,cache,**kwargs):
            cache.lagged_return(1)
            raise MCFError('synthetic failure')
        with patch.object(runtime_module,'compile_candidate',broken), self.assertRaises(MCFError):
            obj.run(freeze['executable'][0]['candidate_id'],director_authorized=True)
        self.assertTrue(all(not c._cache for c in obj._timeframe_caches('1h').values()))
        self.assertEqual(obj._liquidity,{})
        with patch.object(ProductionSeries,'validate',legacy_series_validate):
            expected = runtime(old_runtime.ProductionRuntime,freeze,matrix,bound).run(freeze['executable'][1]['candidate_id'],director_authorized=True)
        self.assertEqual(canonical(obj.run(freeze['executable'][1]['candidate_id'],director_authorized=True)),canonical(expected))

    def test_series_validation_exact_errors_and_conversion_precedence(self):
        matrix,_ = fixture()
        b = matrix['AAAUSDT']; n=len(b.times)
        series = ProductionSeries(b.symbol,b.timeframe,b.times,b.opens,b.closes,(False,)*n,(True,)*n)
        variants = [series, replace(series,symbol='BAD'),replace(series,timeframe='bad'),
                    replace(series,times=series.times[:1]),replace(series,closes=series.closes[:-1]),
                    replace(series,times=tuple(reversed(series.times))),
                    replace(series,times=tuple(t+1 for t in series.times)),
                    replace(series,desired_state=(1,)+series.desired_state[1:]),
                    replace(series,feature_available=series.feature_available[:-1]+(None,))]
        for field in ('opens','closes'):
            for first in ('0','-1','NaN','sNaN','Infinity','bad',1.0, Decimal('2')):
                for last in ('bad','NaN','sNaN','0','2'):
                    variants.append(replace(series,**{field:(first,)+getattr(series,field)[1:-1]+(last,)}))
        for trap in (True,False):
            with localcontext() as ctx:
                ctx.traps[InvalidOperation]=trap
                for item in variants:
                    self.assertEqual(validation_outcome(ProductionSeries.validate,item),
                                     validation_outcome(legacy_series_validate,item))

    def test_series_validation_memory_is_bounded(self):
        for n in (10000,20000):
            b=synthetic_bars(rows=n,gaps=False)
            series=ProductionSeries(b.symbol,b.timeframe,b.times,b.opens,b.closes,(False,)*n,(True,)*n)
            _,old_peak=allocation_peak(lambda:legacy_series_validate(series))
            _,new_peak=allocation_peak(series.validate)
            self.assertGreater(old_peak,n*100)
            self.assertLess(new_peak,12000)

    def test_removed_dead_trend_lists_reduce_compiler_peak(self):
        b=synthetic_bars(rows=20000,gaps=False)
        row=frozen_fixture([('TREND_CROSSOVER',FAMILIES['TREND_CROSSOVER'])])['executable'][0]
        cache=ProductionFeatureCache(b)
        cache.rolling('closes',4,lag=0);cache.rolling('closes',24,lag=0)
        _,old_peak=allocation_peak(lambda:old_rules.compile_candidate(row,cache))
        _,new_peak=allocation_peak(lambda:rules.compile_candidate(row,cache))
        self.assertGreater(old_peak-new_peak,20000*20)

    def test_telemetry_still_contains_no_economics(self):
        matrix,bound=fixture()
        freeze=frozen_fixture([('SESSION_TIME_EFFECT',FAMILIES['SESSION_TIME_EFFECT'])])
        obj=runtime(runtime_module.ProductionRuntime,freeze,matrix,bound)
        identity={'candidate_id':'SYNTHETIC-SIGNAL-MEMORY','candidate_spec_sha256':'a'*64,
                  'runner_input_sha256':'b'*64,'git_sha':'c'*40}
        stream=io.StringIO()
        with engineering_telemetry(CheckpointSink(stream,identity)):
            result=obj.run(freeze['executable'][0]['candidate_id'],director_authorized=True)
        for line in stream.getvalue().splitlines():
            row=json.loads(line);self.assertEqual(set(row),CHECKPOINT_KEYS);validate_checkpoint(row,identity)
        for key in ('completed_trades','net_return','result_sha256','failure_reasons'):
            self.assertNotIn(key,stream.getvalue())
        for key in ('p10_read','p10_write','fresh_oos_read','recent_reserve_read','live','futures','leverage','short','order_endpoint','ai_direct_execution'):
            self.assertIs(result['safety'][key],False)
        self.assertIs(result['safety']['p11_locked'],True)


if __name__=='__main__':
    unittest.main()
