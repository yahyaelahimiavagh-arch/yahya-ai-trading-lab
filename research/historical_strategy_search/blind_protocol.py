"""HSSE-004B frozen Blind OOS protocol validator."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
from typing import Sequence
from research.crisis_lab import acquisition as acq
from . import survivor_freeze

SCHEMA_VERSION="0.1.0"
DEFAULT_PROTOCOL_PATH=Path("docs/research/historical-strategy-search/HSSE-004B-BLIND-OOS-PROTOCOL-v0.1.0.json")
MAX_BYTES=2*1024*1024
REPO_ROOT=Path(__file__).resolve().parents[2]

class HSSEBlindError(RuntimeError): pass

def _json(v):
    return json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False)

def _sha256(b): return hashlib.sha256(b).hexdigest()

def _git_blob_sha(b):
    return hashlib.sha1(b"blob "+str(len(b)).encode("ascii")+b"\0"+b).hexdigest()

def load_protocol(path:Path=DEFAULT_PROTOCOL_PATH):
    if path.is_symlink(): raise HSSEBlindError("symlink protocol is forbidden")
    try: payload=path.read_bytes()
    except OSError: raise HSSEBlindError("cannot read HSSE-004B protocol") from None
    if not payload or len(payload)>MAX_BYTES: raise HSSEBlindError("HSSE-004B protocol size is invalid")
    try: r=json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError,json.JSONDecodeError): raise HSSEBlindError("HSSE-004B protocol is invalid JSON") from None
    if not isinstance(r,dict): raise HSSEBlindError("HSSE-004B protocol must be an object")
    if (r.get("schema")!="YATL_HSSE_BLIND_OOS_PROTOCOL" or r.get("schema_version")!=SCHEMA_VERSION
        or r.get("protocol_id")!="HSSE-004B-FROZEN-BLIND-OOS-001"
        or r.get("status")!="REGISTERED_BEFORE_HSSE_BLIND_OOS_ACQUISITION_OR_OUTCOME_ACCESS"
        or r.get("research_only") is not True or r.get("p10_read") is not False
        or r.get("p10_write_allowed") is not False or r.get("p10_evidence_effect")!="NONE"
        or r.get("live_master_lock")!="OFF" or r.get("trade_permission") is not False
        or r.get("order_endpoint") is not False or r.get("quantity_authority") is not False
        or r.get("risk_authorization_mutation") is not False or r.get("ai_direct_execution") is not False
        or r.get("p11_locked") is not True):
        raise HSSEBlindError("HSSE-004B safety invariants are invalid")
    f=r.get("freeze"); d=r.get("data"); e=r.get("execution"); g=r.get("blind_gate"); dec=r.get("decision")
    if not all(isinstance(x,dict) for x in (f,d,e,g,dec)): raise HSSEBlindError("HSSE-004B scope is incomplete")
    if (f.get("freeze_id")!="HSSE-004A-SURVIVOR-FREEZE-001" or f.get("survivor_count")!=6
        or f.get("relative_path")!="docs/research/historical-strategy-search/HSSE-004A-SURVIVOR-FREEZE-v0.1.0.json"):
        raise HSSEBlindError("freeze binding is invalid")
    freeze_path=(REPO_ROOT/f["relative_path"]).resolve()
    if not freeze_path.is_relative_to(REPO_ROOT):
        raise HSSEBlindError("survivor freeze path escapes repository root")
    try: fp=freeze_path.read_bytes()
    except OSError: raise HSSEBlindError("cannot read bound survivor freeze") from None
    if _git_blob_sha(fp)!=f.get("git_blob_sha"): raise HSSEBlindError("survivor freeze Git blob binding mismatch")
    try: fr=survivor_freeze.validate_freeze(freeze_path)
    except survivor_freeze.HSSEFreezeError as exc: raise HSSEBlindError(str(exc)) from None
    if fr["survivor_count"]!=6 or fr["blind_oos_accessed"] is not False: raise HSSEBlindError("survivor freeze is not pristine")
    reg=d.get("acquisition_register")
    if (not isinstance(reg,dict)
        or reg.get("relative_path")!="docs/research/historical-strategy-search/HSSE-004B-DATA-ACQUISITION-REGISTER-v0.1.0.json"
        or reg.get("git_blob_sha")!="4ecb2821d06a6aa6bc5735ada36ec0ac740a1f3e"
        or reg.get("event_count")!=1):
        raise HSSEBlindError("Blind acquisition register binding is invalid")
    register_path=(REPO_ROOT/reg["relative_path"]).resolve()
    if not register_path.is_relative_to(REPO_ROOT):
        raise HSSEBlindError("Blind acquisition register path escapes repository root")
    try: register_bytes=register_path.read_bytes()
    except OSError: raise HSSEBlindError("cannot read bound Blind acquisition register") from None
    if _git_blob_sha(register_bytes)!=reg["git_blob_sha"]:
        raise HSSEBlindError("Blind acquisition register Git blob binding mismatch")
    try:
        registration=acq.load_acquisition_register(register_path)
        plan=acq.plan_event(registration,"HSSE-BLIND-OOS-001")
    except acq.AcquisitionError as exc:
        raise HSSEBlindError(str(exc)) from None
    if (len(registration.get("events",[]))!=1 or plan.get("designation")!="BLIND_HOLDOUT"
        or plan.get("replay_eligible") is not True or len(plan.get("datasets",[]))!=6):
        raise HSSEBlindError("Blind acquisition register scope is invalid")
    if (d.get("event_id")!="HSSE-BLIND-OOS-001" or d.get("designation")!="BLIND_HOLDOUT"
        or d.get("acquisition_start_utc")!="2022-11-01T00:00:00Z"
        or d.get("analysis_start_utc")!="2023-01-01T00:00:00Z"
        or d.get("analysis_end_exclusive_utc")!="2025-01-01T00:00:00Z"
        or d.get("symbols")!=["BTCUSDT","ETHUSDT"] or d.get("acquired_intervals")!=["15m","1h","4h"]
        or d.get("strategy_interval")!="1h" or d.get("warmup_only_before_analysis_start") is not True
        or d.get("structural_quality_before_replay") is not True):
        raise HSSEBlindError("Blind data contract is invalid")
    if (e.get("execution_count_per_frozen_survivor")!=1 or e.get("reset_at_calendar_quarter_boundary") is not False
        or e.get("reset_inside_analysis_period") is not False or e.get("quantity")!="0.001"
        or e.get("initial_equity_quote_per_symbol")!="10000" or e.get("base_fee_bps")!="10"
        or e.get("base_adverse_slippage_bps")!="5" or e.get("stress_fee_bps")!="20"
        or e.get("stress_adverse_slippage_bps")!="10" or e.get("economics_math")!="DECIMAL_256"
        or e.get("side")!="LONG_ONLY_SPOT" or e.get("next_open") is not True):
        raise HSSEBlindError("Blind execution contract is invalid")
    if (g.get("minimum_completed_trades_total")!=40 or g.get("minimum_completed_trades_per_symbol")!=10
        or g.get("minimum_profit_factor_after_base_costs")!="1.05"
        or g.get("minimum_positive_calendar_quarter_fraction")!="0.50"
        or g.get("maximum_drawdown_fraction")!="0.12"
        or g.get("failure_policy")!="RETAIN_FAILURE; DO_NOT_RETUNE_ON_THIS_HOLDOUT"):
        raise HSSEBlindError("Blind gate is invalid")
    if (dec.get("no_cross_candidate_reranking_on_blind") is not True or dec.get("no_parameter_change") is not True
        or dec.get("no_hidden_retry") is not True or dec.get("zero_pass_is_valid") is not True):
        raise HSSEBlindError("Blind decision policy is invalid")
    return r,_sha256(payload),fr

def main(argv:Sequence[str]|None=None):
    p=argparse.ArgumentParser()
    p.add_argument("--protocol",type=Path,default=DEFAULT_PROTOCOL_PATH)
    a=p.parse_args(argv)
    r,d,f=load_protocol(a.protocol)
    print(_json({"implementation_id":"HSSE-004B-PROTOCOL/0.1.0","protocol_id":r["protocol_id"],"protocol_sha256":d,
      "survivor_count":f["survivor_count"],"blind_event_id":r["data"]["event_id"],"blind_outcomes_accessed":False,
      "research_only":True,"p10_write_allowed":False,"p11_locked":True}))
    return 0

if __name__=="__main__":
    try: raise SystemExit(main())
    except HSSEBlindError as exc:
        print(_json({"code":"HSSE004B_PROTOCOL_ERROR","reason":str(exc),"research_only":True,"p10_write_allowed":False,"p11_locked":True}))
        raise SystemExit(2)
