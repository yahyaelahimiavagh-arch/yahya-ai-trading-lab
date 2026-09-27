"""Synthetic MCF fixtures; no market data or strategy selection."""
from copy import deepcopy
from research.mass_candidate_factory.manifest import SCHEMA
from research.mass_candidate_factory.models import CostPolicy
from research.mass_candidate_factory.feature_cache import Bars

def family():
    return {"manifest_schema":SCHEMA["schema"],"manifest_schema_version":"1.0","family_manifest_id":"MCF-FAM-TEST","family_manifest_version":"1.0","alpha_family_id":"SYNTHETIC","economic_mechanism_id":"ENGINEERING_ONLY","common_factor_cluster_hint":"ENGINEERING","origin_type":"CONTROL_BASELINE","source_refs":["SYNTHETIC/v1"],"tested_object_type":"ENGINEERING_FIXTURE","market_scope":{"assets":["BTCUSDT"],"quote_assets":["USDT"],"venues":["BINANCE_SPOT"],"timeframes":["1h"],"spot_only":True,"directionality":"LONG_CASH","universe_policy_ref":"AF-01A/v1"},"data_dependencies":["PRICE_OHLC"],"signal_template":{"operator":"GT","left":{"feature":"MOVING_AVERAGE","window":2},"right":1},"entry_template":{"operator":"GT","left":1,"right":0},"exit_template":{"operator":"LT","left":0,"right":1},"sizing_template":{"quantity":1},"eligibility_template":None,"parameter_domains":[{"name":"fast","type":"INTEGER_RANGE","start":1,"stop":3,"step":1,"ordering":"ASCENDING","semantic_role":"WINDOW","mechanism_distinct":False},{"name":"slow","type":"ENUM","values":[2,4],"ordering":"ASCENDING","semantic_role":"WINDOW","mechanism_distinct":False}],"structural_constraints":[{"left":"fast","operator":"LT","right":"slow"}],"cost_policy_ref":"COST/v1","evidence_policy_ref":"DEV/v1","generation_budget":{"batch_generation_id":"2026-01","maximum_raw_candidates":6,"maximum_valid_economic_trials":6,"parameter_neighbor_accounting":"ALL","hidden_trials_forbidden":True,"post_outcome_expansion_forbidden":True,"child_generation_requires_new_batch":True},"screening_policy":{"policy_ref":"SCREEN/v1","thresholds":{}},"exact_recompute_policy":{"policy_ref":"EXACT/v1","thresholds":{}},"prohibited_adaptations":[],"research_only":True,"safety":deepcopy(SCHEMA["defaults"])}

def policy():return CostPolicy("COST/v1","1","1000","10","5","20","10")

def bars():
    return Bars("SYNTHETIC-001","DEVELOPMENT","BTCUSDT","1h",tuple(i*3600000 for i in range(8)),(10,11,12,13,14,15,16,17),(11,12,13,14,15,16,17,18),(9,10,11,12,13,14,15,16),(10,11,12,13,14,15,16,17),(1,)*8,(10,)*8,(3,)*8)
