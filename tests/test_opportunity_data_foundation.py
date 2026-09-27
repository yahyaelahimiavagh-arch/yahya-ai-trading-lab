"""Bounded synthetic AF-01B engineering validation; no market or P10 reads."""
from dataclasses import replace
from pathlib import Path

import tempfile
import unittest

from research.crisis_lab.acquisition import CanonicalRow
from research.opportunity_data import Lifecycle, UniversePolicy, admit, build_index, compute, derive
from research.opportunity_data.canonical import validate_rows
from research.opportunity_data.models import OpportunityError, canonical, development_path, sha256
from research.opportunity_data.quality import verify_quality
from research.opportunity_data.storage import read_canonical, read_quality, save_artifact

C = 900_000
START = (1_700_000_000_000 // 86_400_000) * 86_400_000  # UTC day boundary


def row(i, *, base='2', quote='20', trades='3'):
    start = START + i * C
    return CanonicalRow((str(start), '9', '11', '8', '10', base, str(start + C - 1),
                         quote, trades, '1', '10', '0'))


def dataset(symbol='BTCUSDT', indices=range(12), allow_gaps=True):
    rows = tuple(row(i) for i in indices)
    return admit(dataset_id=f'{symbol}/15m/fixture/v1', symbol=symbol, interval='15m', rows=rows,
                 source='SYNTHETIC_FIXTURE', requested_start_ms=START,
                 requested_end_ms=START + 16*C, retrieved_at_ms=START + 16*C,
                 source_refs=('fixture://bounded/v1',), allow_gaps=allow_gaps)


def lifecycle(symbol='BTCUSDT', status='INACTIVE', **kw):
    return Lifecycle(symbol=symbol, base_asset=symbol[:-4], quote_asset='USDT',
                     venue='BINANCE_SPOT', instrument_type='SPOT', spot_allowed=True,
                     leveraged_token_flag=False, first_admitted_data_ms=START,
                     last_admitted_data_ms=START+11*C, listing_time_ms=None,
                     delisting_time_ms=START+13*C if status == 'DELISTED' else None,
                     lifecycle_status=status, lifecycle_source_refs=('fixture://lifecycle/v1',),
                     **kw).frozen()


def policy(**kw):
    return UniversePolicy(ref='fixture-universe/v1', quote_asset='USDT', required_intervals=('15m',),
                          required_dependencies=('PRICE_OHLC', 'VOLUME', 'TRADE_COUNT'),
                          warmup_bars=2, **kw).frozen()


class OpportunityFoundationTests(unittest.TestCase):
    def test_lifecycle_nullable_listing_distinct_from_first_data_and_inactive_history(self):
        d = dataset(); l = lifecycle(status='DELISTED')
        ix = build_index((l,), (d,))
        assert l.listing_time_ms is None and l.first_admitted_data_ms == START
        assert ix.symbols_at(START+4*C) == ('BTCUSDT',)
        assert ix.symbol('BTCUSDT', START+4*C)['delisting_time_ms'] is None
        assert ix.symbol('BTCUSDT', START+4*C)['lifecycle_status'] == 'HISTORICALLY_ADMITTED'
        assert ix.symbols_at(START+14*C) == ()
        assert not ix.symbols_at(START-C)
        assert not ix.symbols_at(START)
        assert ix.index_sha256 == build_index((l,), (d,)).index_sha256
        assert ix.intervals_at(l.symbol, START+2*C) == ('15m',)
        assert ix.dependency_available(l.symbol, START+2*C, 'VOLUME')
        assert not ix.dependency_available(l.symbol, START+2*C, 'ORDER_BOOK')
        for changes in ({'instrument_type': 'FUTURES'}, {'leveraged_token_flag': True},
                        {'spot_allowed': False}):
            with self.assertRaises(OpportunityError):
                replace(l, **changes).frozen()
        with self.assertRaises(OpportunityError):
            replace(l, listing_time_ms=START+C).frozen()
        with self.assertRaises(OpportunityError):
            replace(l, delisting_time_ms=START+10*C).frozen()


    def test_eligibility_point_in_time_quote_warmup_dependencies_and_lagged_liquidity(self):
        d = dataset(); eth = dataset('ETHUSDT')
        ix = build_index((lifecycle(), lifecycle('ETHUSDT')), (d, eth))
        t = START+5*C
        assert ix.eligibility('BTCUSDT', t, policy()).production_research_eligible
        assert not ix.eligibility('BTCUSDT', START, policy()).data_admitted
        with self.assertRaises(OpportunityError):
            ix.eligibility('BTCUSDT', t, replace(policy(), policy_sha256='0'*64))
        assert not ix.eligibility('BTCUSDT', START+C, policy()).production_research_eligible
        assert 'QUOTE_MISMATCH' in ix.eligibility('BTCUSDT', t, replace(policy(), quote_asset='BTC').frozen()).reasons
        cross = replace(policy(), required_dependencies=('MULTI_ASSET',)).frozen()
        assert not ix.eligibility('BTCUSDT', t, cross).production_research_eligible
        assert ix.eligibility('BTCUSDT', t, cross, companions=('ETHUSDT',)).production_research_eligible
        blocked = replace(policy(), required_dependencies=('ORDER_BOOK',)).frozen()
        assert 'BLOCKED_DEPENDENCY:ORDER_BOOK' in ix.eligibility('BTCUSDT', t, blocked).reasons
        liquid = compute(d[0], ending_ms=t, window_bars=3)
        threshold = replace(policy(), minimum_trailing_quote_volume='60', liquidity_window_bars=3).frozen()
        assert ix.eligibility('BTCUSDT', t, threshold, liquidity=liquid).production_research_eligible
        assert not ix.eligibility('BTCUSDT', t, threshold, liquidity=replace(liquid, ending_ms=t+C)).production_research_eligible
        assert ix.liquidity_available(liquid, t)
        bridge = ix.mcf_data_binding('BTCUSDT', t, policy())
        assert bridge['symbol_eligible'] and bridge['evidence_partition'] == 'DEVELOPMENT'
        assert bridge == ix.mcf_data_binding('BTCUSDT', t, policy())
        assert not ix.liquidity_available(liquid, t+C)


    def test_quality_failures_gap_map_digest_and_binding(self):
        data, gap, manifest = dataset(indices=(0, 1, 2, 4, 5, 6, 7, 8, 9, 10, 11))
        assert gap.missing_ranges == ((START+3*C, START+3*C),)
        assert gap.gap_count == manifest['gap_count'] == 1
        assert data.quality_verdict == 'PASS_WITH_GAPS'
        verify_quality(data, manifest, gap)
        assert data.content_sha256 == validate_rows(data.rows, '15m', as_of_ms=START+16*C)
        with self.assertRaises(OpportunityError):
            verify_quality(data, manifest | {'row_count': 42}, gap)
        with self.assertRaises(OpportunityError):
            dataset(indices=(0, 2), allow_gaps=False)
        with self.assertRaises(OpportunityError):
            admit(dataset_id='BTCUSDT/15m/fixture/v1', symbol='BTCUSDT', interval='15m',
                  rows=(row(0),), source='fixture', requested_start_ms=START,
                  requested_end_ms=START+C, retrieved_at_ms=START+2*C,
                  source_refs=('fresh-oos/secret',), allow_gaps=True)
        for bad in ((row(0), row(0)), (row(2), row(1)),
                    (replace(row(0), values=row(0).values[:2]+('7',)+row(0).values[3:]),),
                    (replace(row(0), values=row(0).values[:5]+('-1',)+row(0).values[6:]),),
                    (replace(row(0), values=row(0).values[:7]+('-1',)+row(0).values[8:]),),
                    (replace(row(0), values=row(0).values[:8]+('-1',)+row(0).values[9:]),)):
            with self.assertRaises(OpportunityError):
                validate_rows(bad, '15m', as_of_ms=START+16*C)


    def test_views_utc_ohlc_sums_incomplete_buckets_and_gap_propagation(self):
        raw = tuple(row(i) for i in range(12))
        hourly, gap = derive(raw, 'BTCUSDT', 'view/v1', '15m', '1h', as_of_ms=START+12*C)
        assert len(hourly) == 3 and gap.gap_count == 0
        assert hourly[0].values[5] == '8' and hourly[0].values[7] == '80'
        assert hourly[0].values[8] == '12'
        assert hourly[0].open_time_ms % (4*C) == 0
        broken = tuple(r for r in raw if r.open_time_ms != START+5*C)
        derived, gaps = derive(broken, 'BTCUSDT', 'view/v1', '15m', '1h', as_of_ms=START+12*C)
        assert len(derived) == 2 and gaps.gap_count == 1
        partial, _ = derive(raw[:10], 'BTCUSDT', 'view/v1', '15m', '1h', as_of_ms=START+12*C)
        assert len(partial) == 2
        assert derive(raw[:10], 'BTCUSDT', 'view/v1', '15m', '1h', as_of_ms=START+12*C)[1].gap_count == 1
        full_day = tuple(row(i) for i in range(96))
        day, _ = derive(full_day, 'BTCUSDT', 'day/v1', '15m', '1d', as_of_ms=START+96*C)
        assert len(day) == 1 and day[0].values[8] == '288'
        for name, expected in [('4h', 1), ('1d', 0)]:
            if expected:
                complete = tuple(row(i) for i in range(16))
                assert len(derive(complete, 'BTCUSDT', 'v', '15m', name, as_of_ms=START+16*C)[0]) == expected
            else:
                with self.assertRaises(OpportunityError):
                    derive(raw, 'BTCUSDT', 'v', '15m', name, as_of_ms=START+12*C)


    def test_liquidity_lagged_and_deterministic(self):
        data = dataset()[0]
        t = START+4*C
        m = compute(data, ending_ms=t, window_bars=3)
        assert (m.trailing_quote_volume, m.trailing_base_volume, m.trailing_trade_count,
                m.active_bar_count, m.gap_rate, m.turnover_proxy) == ('60', '6', 9, 3, '0', '10')
        assert m.metric_sha256 == compute(data, ending_ms=t, window_bars=3).metric_sha256
        gap_data = dataset(indices=(0, 1, 3, 4, 5, 6, 7, 8, 9, 10, 11))[0]
        assert compute(gap_data, ending_ms=t, window_bars=3).gap_rate == str(__import__('decimal').Decimal(1)/3)
        ix = build_index((lifecycle(),), (dataset(indices=(0, 1, 2, 4, 5, 6, 7, 8, 9, 10, 11)),))
        strict = policy(maximum_gap_rate='0')
        assert 'GAP_RATE:15m' in ix.eligibility('BTCUSDT', START+5*C, strict).reasons


    def test_development_isolation_paths_partitions_symlinks_and_immutable_artifacts(self):
        tmp_path = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__('shutil').rmtree(tmp_path))
        root = tmp_path / 'opportunity-data'; root.mkdir()
        for forbidden in ('fresh-oos/secret', 'recent_reserve/secret', 'p10/state', '../other', '/var/lib/yatl/p10/state'):
            with self.assertRaises(OpportunityError):
                development_path(root, forbidden)
        for p in ('FRESH_OOS', 'RECENT_RESERVE', 'P10', 'UNKNOWN'):
            with self.assertRaises(OpportunityError):
                development_path(root, 'canonical/btc.csv', p)
        (root/'escape').symlink_to(tmp_path, target_is_directory=True)
        with self.assertRaises(OpportunityError):
            development_path(root, 'escape/file')
        with self.assertRaises(OpportunityError):
            development_path(tmp_path/'p10', 'canonical')
        payload = canonical({'version':'AF-01B/1.0.0','evidence_partition':'DEVELOPMENT','dataset_id':'fixture/v1', 'quality_verdict':'PASS_CONTIGUOUS', 'content_sha256':'a'*64})
        sha = save_artifact(root, 'quality/fixture.json', payload)
        assert read_quality(root, 'quality/fixture.json', sha)['dataset_id'] == 'fixture/v1'
        assert save_artifact(root, 'quality/fixture.json', payload) == sha
        with self.assertRaises(OpportunityError):
            save_artifact(root, 'quality/fixture.json', b'different')
        with self.assertRaises(OpportunityError):
            read_quality(root, 'quality/fixture.json', '0'*64)
        with self.assertRaises(OpportunityError):
            read_canonical(root, 'quality/fixture.json', sha)
