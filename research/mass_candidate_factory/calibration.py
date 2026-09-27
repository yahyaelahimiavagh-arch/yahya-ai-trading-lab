"""Synthetic engineering throughput check; zero market performance selection."""
from __future__ import annotations
import json
import tempfile
import time
import tracemalloc
from pathlib import Path
from .generator import generate
from .feature_cache import Bars,FeatureCache
from .screening import screen
from .exact import account
from .models import CostPolicy
from .shards import finalize
from .ledger import make_result,reconcile
from .manifest import SCHEMA

def run():
    # Explicitly synthetic, no file/network data loading and no survivor path.
    import copy
    m={"manifest_schema":SCHEMA["schema"],"manifest_schema_version":"1.0","family_manifest_id":"MCF-CAL-001","family_manifest_version":"1.0","alpha_family_id":"ENGINEERING","economic_mechanism_id":"ENGINEERING_ONLY","common_factor_cluster_hint":"FIXTURE","origin_type":"CONTROL_BASELINE","source_refs":["SYNTHETIC/v1"],"tested_object_type":"ENGINEERING_FIXTURE","market_scope":{"assets":["BTCUSDT"],"quote_assets":["USDT"],"venues":["BINANCE_SPOT"],"timeframes":["1h"],"spot_only":True,"directionality":"LONG_CASH","universe_policy_ref":"AF-01A/v1"},"data_dependencies":["PRICE_OHLC"],"signal_template":{"operator":"GT","left":1,"right":0},"entry_template":None,"exit_template":None,"sizing_template":{"quantity":1},"eligibility_template":None,"parameter_domains":[{"name":"a","type":"INTEGER_RANGE","start":1,"stop":50,"step":1,"ordering":"ASCENDING","semantic_role":"FIXTURE","mechanism_distinct":False},{"name":"b","type":"INTEGER_RANGE","start":51,"stop":70,"step":1,"ordering":"ASCENDING","semantic_role":"FIXTURE","mechanism_distinct":False}],"structural_constraints":[],"cost_policy_ref":"COST/v1","evidence_policy_ref":"SYNTHETIC/v1","generation_budget":{"batch_generation_id":"2026-01","maximum_raw_candidates":1000,"maximum_valid_economic_trials":1000,"parameter_neighbor_accounting":"ALL","hidden_trials_forbidden":True,"post_outcome_expansion_forbidden":True,"child_generation_requires_new_batch":True},"screening_policy":{"policy_ref":"SCREEN/v1","thresholds":{}},"exact_recompute_policy":{"policy_ref":"EXACT/v1","thresholds":{}},"prohibited_adaptations":[],"research_only":True,"safety":copy.deepcopy(SCHEMA["defaults"])}
    tracemalloc.start();t=time.perf_counter()
    batch,valid,invalid=generate([m],batch_id="MCF-ENGINE-CALIBRATION-001",shard_size=100)
    generation=time.perf_counter()-t
    t=time.perf_counter();n=256
    close=tuple(100+i*.01 for i in range(n));vol=(1.,)*n
    bars=Bars("SYNTHETIC-CAL-001","DEVELOPMENT","BTCUSDT","1h",tuple(i*3600000 for i in range(n)),close,tuple(x+1 for x in close),tuple(x-1 for x in close),close,vol,vol,vol)
    cache=FeatureCache(bars);cache.get("MOVING_AVERAGE",window=12);cache.get("MOVING_AVERAGE",window=12)
    cache_time=time.perf_counter()-t
    policy=CostPolicy("COST/v1","1","1000","10","5","20","10")
    signals=tuple(i%10<5 for i in range(n));t=time.perf_counter()
    for _ in range(100):last_screen=screen(signals,bars.opens,bars.closes,policy,cost_policy_ref="COST/v1",thresholds={"minimum_signals":1},folds=((0,128),(128,256)),fixture_id="SYNTHETIC-CAL-001")
    screening=time.perf_counter()-t
    t=time.perf_counter();account(signals,bars.opens,bars.closes,policy);exact=time.perf_counter()-t
    with tempfile.TemporaryDirectory() as d:
        artifacts=[];raw=valid+invalid
        for sh in batch["shard_layout"]:
            rows=[make_result(c,batch,sh,dataset_id="SYNTHETIC-CAL-001",state="DEVELOPMENT_FAIL",failure_reasons=["ENGINEERING_ONLY_NO_SELECTION"]) for c in raw[sh["start"]:sh["end"]]]
            p,sha=finalize(Path(d),sh,rows);artifacts.append((sh,p,sha))
        first=sum(p.stat().st_size for _,p,_ in artifacts)
        rerun=[finalize(Path(d),sh,[make_result(c,batch,sh,dataset_id="SYNTHETIC-CAL-001",state="DEVELOPMENT_FAIL",failure_reasons=["ENGINEERING_ONLY_NO_SELECTION"]) for c in raw[sh["start"]:sh["end"]]])[1]==sha for sh,_,sha in artifacts]
        status=reconcile(batch,raw,artifacts,dataset_id="SYNTHETIC-CAL-001")["status"]
    _,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
    return {"calibration_id":"MCF-ENGINE-CALIBRATION-001","state":"ENGINEERING_ONLY_NO_SELECTION","candidate_specs":len(valid),"generation_seconds":generation,"generation_candidates_per_second":len(valid)/generation,"screening_candidates_per_second":100/screening,"candidate_bars_per_second":100*n/screening,"feature_cache_build_seconds":cache_time,"feature_cache_builds":cache.builds,"peak_memory_bytes":peak,"shard_artifact_bytes":first,"exact_recompute_seconds":exact,"maximum_numerical_discrepancy":last_screen["maximum_numerical_discrepancy"],"deterministic_rerun":all(rerun) and generate([m],batch_id="MCF-ENGINE-CALIBRATION-001",shard_size=100)[0]==batch,"ledger_status":status,"performance_selection_run":False,"fresh_oos_read":False,"recent_reserve_read":False,"p10_read":False,"p10_write":False}
if __name__=="__main__":print(json.dumps(run(),sort_keys=True))
