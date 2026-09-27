"""HSSE-005 crisis/regime certification for the six frozen survivors.

No search, retuning, reranking, live execution, P10 mutation, Audit Holdout
access, or recent-reserve access. Uses only the pre-2023 Development corpus and
the already-opened HSSE-004B 2023-2024 Blind corpus.
"""
from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import math
import os
from dataclasses import dataclass
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Mapping, Sequence

from research.crisis_lab import controls
from . import blind_oos
from . import survivor_ranking as hsse3
from . import trend_ma as hsse2

IMPLEMENTATION_ID="HSSE-005-CRISIS-REGIME-CERTIFICATION/0.1.0"
SCHEMA_VERSION="0.1.0"
DEFAULT_PROTOCOL_PATH=Path("docs/research/historical-strategy-search/HSSE-005-CRISIS-REGIME-CERTIFICATION-PROTOCOL-v0.1.0.json")
REPO_ROOT=Path(__file__).resolve().parents[2]
HOUR_MS=60*60*1000
MAX_PROTOCOL_BYTES=2*1024*1024

class HSSE005Error(RuntimeError): pass

@dataclass(frozen=True,slots=True)
class Series:
    symbol:str
    times:tuple[int,...]
    opens:tuple[str,...]
    closes:tuple[str,...]
    signal:hsse2.SearchSeries

def _json(v):
    return json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False)

def _canonical_json(v):
    return (_json(v)+"\n").encode("utf-8")

def _sha256(b): return hashlib.sha256(b).hexdigest()

def _git_blob_sha(b):
    return hashlib.sha1(b"blob "+str(len(b)).encode("ascii")+b"\0"+b).hexdigest()

def _time_ms(v,label):
    if not isinstance(v,str) or not v.endswith("Z"): raise HSSE005Error(f"{label} is not UTC")
    try:
        from datetime import datetime
        return int(datetime.fromisoformat(v[:-1]+"+00:00").timestamp()*1000)
    except ValueError:
        raise HSSE005Error(f"{label} is invalid") from None

def _read_bound_repo_json(relative,blob_sha,label):
    if not isinstance(relative,str) or not relative or not isinstance(blob_sha,str) or len(blob_sha)!=40:
        raise HSSE005Error(f"{label} binding is invalid")
    p=(REPO_ROOT/relative).resolve()
    if not p.is_relative_to(REPO_ROOT) or p.is_symlink(): raise HSSE005Error(f"{label} path is invalid")
    try: b=p.read_bytes()
    except OSError: raise HSSE005Error(f"cannot read {label}") from None
    if _git_blob_sha(b)!=blob_sha: raise HSSE005Error(f"{label} Git blob binding mismatch")
    try: r=json.loads(b.decode("utf-8"))
    except (UnicodeDecodeError,json.JSONDecodeError): raise HSSE005Error(f"{label} is invalid JSON") from None
    if not isinstance(r,dict): raise HSSE005Error(f"{label} must be an object")
    return r

def load_protocol(path:Path=DEFAULT_PROTOCOL_PATH):
    if path.is_symlink(): raise HSSE005Error("symlink protocol is forbidden")
    try: payload=path.read_bytes()
    except OSError: raise HSSE005Error("cannot read HSSE-005 protocol") from None
    if not payload or len(payload)>MAX_PROTOCOL_BYTES: raise HSSE005Error("HSSE-005 protocol size is invalid")
    try: p=json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError,json.JSONDecodeError): raise HSSE005Error("HSSE-005 protocol is invalid JSON") from None
    if (not isinstance(p,dict) or p.get("schema")!="YATL_HSSE_CRISIS_REGIME_CERTIFICATION_PROTOCOL"
        or p.get("schema_version")!=SCHEMA_VERSION or p.get("protocol_id")!="HSSE-005-CRISIS-REGIME-CERTIFICATION-001"
        or p.get("status")!="REGISTERED_AFTER_HSSE004B_CANONICAL_BEFORE_HSSE005_OUTCOME_ACCESS"
        or p.get("research_only") is not True or p.get("p10_read") is not False
        or p.get("p10_write_allowed") is not False or p.get("p10_evidence_effect")!="NONE"
        or p.get("live_master_lock")!="OFF" or p.get("trade_permission") is not False
        or p.get("order_endpoint") is not False or p.get("ai_direct_execution") is not False
        or p.get("p11_locked") is not True):
        raise HSSE005Error("HSSE-005 safety invariants are invalid")
    inputs=p.get("inputs"); ex=p.get("exclusions"); units=p.get("certification_units"); execution=p.get("execution"); gate=p.get("certification_gate"); decision=p.get("decision")
    if not isinstance(inputs,dict) or not isinstance(ex,dict) or not isinstance(units,list) or not isinstance(execution,dict) or not isinstance(gate,dict) or not isinstance(decision,dict):
        raise HSSE005Error("HSSE-005 protocol scope is incomplete")
    if len(units)!=8 or gate.get("unit_count")!=8: raise HSSE005Error("HSSE-005 unit count is invalid")
    if (ex.get("audit_holdout_event_ids")!=["CRL-E012","CRL-E013","CRL-E014"]
        or ex.get("audit_holdout_read") is not False or ex.get("recent_reserve_read") is not False
        or ex.get("latest_allowed_scored_time_exclusive_utc")!="2025-01-01T00:00:00Z"):
        raise HSSE005Error("HSSE-005 holdout exclusions are invalid")
    if (decision.get("no_reranking") is not True or decision.get("no_parameter_change") is not True
        or decision.get("no_family_change") is not True or decision.get("no_hidden_retry") is not True
        or decision.get("no_automatic_forward_promotion") is not True):
        raise HSSE005Error("HSSE-005 decision invariants are invalid")

    acc_b=inputs["hsse004b_acceptance"]; fr_b=inputs["survivor_freeze"]; cat_b=inputs["event_catalog"]
    acceptance=_read_bound_repo_json(acc_b["relative_path"],acc_b["git_blob_sha"],"HSSE-004B acceptance")
    freeze=_read_bound_repo_json(fr_b["relative_path"],fr_b["git_blob_sha"],"HSSE-004A freeze")
    catalog=_read_bound_repo_json(cat_b["relative_path"],cat_b["git_blob_sha"],"CRL event catalog")
    if (acceptance.get("status")!="CANONICAL_COMPLETE" or acceptance.get("result",{}).get("pass_count")!=6
        or acceptance.get("result",{}).get("fail_count")!=0 or acceptance.get("result",{}).get("audit_holdout_read") is not False):
        raise HSSE005Error("HSSE-004B acceptance is not canonical")
    if freeze.get("freeze_id")!="HSSE-004A-SURVIVOR-FREEZE-001" or len(freeze.get("survivors",[]))!=6:
        raise HSSE005Error("survivor freeze identity is invalid")
    if catalog.get("schema")!="YATL_CRL_EVENT_CATALOG" or catalog.get("catalog_version")!="0.1.0":
        raise HSSE005Error("event catalog identity is invalid")
    events={x["event_id"]:x for x in catalog.get("events",[]) if isinstance(x,dict) and isinstance(x.get("event_id"),str)}
    seen=set()
    previous_end=None
    cutoff=_time_ms(ex["latest_allowed_scored_time_exclusive_utc"],"scored cutoff")
    for u in units:
        ids=u.get("event_ids")
        if not isinstance(ids,list) or not ids or any(x in seen for x in ids): raise HSSE005Error("certification event assignment is invalid")
        rows=[]
        for eid in ids:
            row=events.get(eid)
            if row is None or row.get("replay_eligible") is not True: raise HSSE005Error("certification event is not replay eligible")
            if eid in set(ex["audit_holdout_event_ids"]) or eid in set(ex["quarantined_or_replay_ineligible_event_ids"]):
                raise HSSE005Error("excluded event entered HSSE-005")
            rows.append(row); seen.add(eid)
        starts=[_time_ms(x["windows"]["pre_event"]["start_utc"],"event start") for x in rows]
        ends=[_time_ms(x["windows"]["aftermath_recovery"]["end_utc"],"event end") for x in rows]
        us=_time_ms(u["semantic_start_utc"],"unit start"); ue=_time_ms(u["semantic_end_exclusive_utc"],"unit end")
        if us!=min(starts) or ue!=max(ends) or ue>cutoff or us>=ue:
            raise HSSE005Error("certification unit does not equal registered event union")
        if previous_end is not None and us<previous_end: raise HSSE005Error("certification units overlap")
        previous_end=ue
    expected={"CRL-E001","CRL-E002","CRL-E003","CRL-E004","CRL-E005","CRL-E006","CRL-E007","CRL-E008","CRL-E009","CRL-E011","CRL-E016"}
    if seen!=expected: raise HSSE005Error("HSSE-005 event set differs from registration")
    if (execution.get("lead_in_hours")!=720 or execution.get("quantity")!="0.001"
        or execution.get("base_fee_bps")!="10" or execution.get("base_adverse_slippage_bps")!="5"
        or execution.get("stress_fee_bps")!="20" or execution.get("stress_adverse_slippage_bps")!="10"
        or execution.get("event_labels_visible_to_strategy") is not False or execution.get("side")!="LONG_ONLY_SPOT"):
        raise HSSE005Error("HSSE-005 execution semantics are invalid")
    return p,_sha256(payload),acceptance,freeze

def _series(corpus,symbol):
    candles=corpus.datasets.get((symbol,"1h"))
    if not candles: raise HSSE005Error(f"missing 1h corpus for {symbol}")
    times=tuple(x.open_time_ms for x in candles)
    if times!=tuple(sorted(times)) or len(times)!=len(set(times)) or any(not x.is_closed for x in candles):
        raise HSSE005Error(f"invalid 1h series for {symbol}")
    opens=tuple(x.open for x in candles); closes=tuple(x.close for x in candles)
    signal=hsse2.SearchSeries(symbol,times,tuple(float(x) for x in opens),tuple(float(x) for x in closes))
    return Series(symbol,times,opens,closes,signal)

def _simulate_unit_symbol(*,series,short_values,long_values,start_ms,end_ms,lead_hours,policy):
    score=bisect.bisect_left(series.times,start_ms); end=bisect.bisect_left(series.times,end_ms)
    lead=bisect.bisect_left(series.times,start_ms-lead_hours*HOUR_MS)
    if lead>=score or score>=end: raise HSSE005Error("crisis unit has invalid aligned range")
    q=Decimal(policy["quantity"]); initial=Decimal(policy["initial_equity_quote_per_symbol"])
    bf=Decimal(policy["base_fee_bps"]); bs=Decimal(policy["base_adverse_slippage_bps"])
    sf=Decimal(policy["stress_fee_bps"]); ss=Decimal(policy["stress_adverse_slippage_bps"])
    base=hsse3._new_account(initial); stress=hsse3._new_account(initial)
    position=False; pending=None; baseline=None; stress_baseline=None
    peak=None; maxdd=Decimal(0); scored_entries=scored_exits=missing=0
    position_at_start=False
    for i in range(lead,end):
        if i==score:
            mark=Decimal(series.opens[i])
            baseline=hsse3._equity(base,mark=mark,quantity=q,fee_bps=bf,slippage_bps=bs)
            stress_baseline=hsse3._equity(stress,mark=mark,quantity=q,fee_bps=sf,slippage_bps=ss)
            peak=baseline; position_at_start=position
        if pending is not None:
            action,target=pending
            if target!=i: raise HSSE005Error("pending fill target drifted")
            ref=Decimal(series.opens[i])
            if action=="ENTER":
                hsse3._entry(base,reference=ref,quantity=q,fee_bps=bf,slippage_bps=bs)
                hsse3._entry(stress,reference=ref,quantity=q,fee_bps=sf,slippage_bps=ss)
                position=True
                if i>=score: scored_entries+=1
            else:
                hsse3._exit(base,reference=ref,quantity=q,fee_bps=bf,slippage_bps=bs)
                hsse3._exit(stress,reference=ref,quantity=q,fee_bps=sf,slippage_bps=ss)
                position=False
                if i>=score: scored_exits+=1
            pending=None
        close=Decimal(series.closes[i])
        if i>=score:
            eq=hsse3._equity(base,mark=close,quantity=q,fee_bps=bf,slippage_bps=bs)
            if peak is None: raise HSSE005Error("score baseline was not set")
            if eq>peak: peak=eq
            with localcontext() as ctx:
                ctx.prec=hsse3.DECIMAL_PRECISION
                dd=(peak-eq)/peak
            if dd>maxdd: maxdd=dd
        if i<=lead: continue
        vals=(short_values[i],long_values[i],short_values[i-1],long_values[i-1])
        if not all(math.isfinite(x) for x in vals): continue
        sn,ln,sp,lp=vals
        action=None
        if (not position) and sn>ln and sp<=lp: action="ENTER"
        elif position and sn<ln and sp>=lp: action="EXIT"
        if action is not None:
            nxt=i+1
            if nxt>=end or nxt>=len(series.times) or series.times[nxt]!=series.times[i]+HOUR_MS:
                missing+=1
            else:
                pending=(action,nxt)
    if baseline is None or stress_baseline is None: raise HSSE005Error("unit baseline missing")
    final_mark=Decimal(series.closes[end-1])
    final=hsse3._equity(base,mark=final_mark,quantity=q,fee_bps=bf,slippage_bps=bs)
    stress_final=hsse3._equity(stress,mark=final_mark,quantity=q,fee_bps=sf,slippage_bps=ss)
    with localcontext() as ctx:
        ctx.prec=hsse3.DECIMAL_PRECISION
        net=final-baseline; stress_net=stress_final-stress_baseline
    return {
      "base_net":net,"stress_net":stress_net,"maximum_drawdown":maxdd,
      "scored_entry_fills":scored_entries,"scored_exit_fills":scored_exits,
      "completed_trades":scored_exits,"missing_fill_signals":missing,
      "position_at_score_start":position_at_start,"position_at_score_end":position
    }

def _pearson(a,b):
    if len(a)!=len(b) or not a: return None
    af=[float(x) for x in a]; bf=[float(x) for x in b]
    ma=sum(af)/len(af); mb=sum(bf)/len(bf)
    da=[x-ma for x in af]; db=[x-mb for x in bf]
    va=sum(x*x for x in da); vb=sum(x*x for x in db)
    if va<=0 or vb<=0: return None
    return sum(x*y for x,y in zip(da,db))/math.sqrt(va*vb)

def _sign(v):
    return 1 if v>0 else (-1 if v<0 else 0)

def _write_result(root,record):
    payload=_canonical_json(record); digest=_sha256(payload)
    d=root/"historical-strategy-search"/"hsse-005"; d.mkdir(parents=True,exist_ok=True)
    p=d/f"crisis-regime-{digest[:24]}.json"
    if p.exists():
        if p.read_bytes()!=payload: raise HSSE005Error("existing HSSE-005 artifact differs")
    else:
        fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,"wb") as h: h.write(payload); h.flush(); os.fsync(h.fileno())
    return p.relative_to(root).as_posix(),digest

def run(*,runtime_root:Path,protocol_path:Path=DEFAULT_PROTOCOL_PATH):
    protocol,protocol_sha,acceptance,freeze=load_protocol(protocol_path)
    corpora_cfg={x["corpus_id"]:x for x in protocol["inputs"]["corpora"]}
    try:
        dev=controls._load_control_corpus(
          runtime_root=runtime_root,
          quality_manifest_relative_path=corpora_cfg["CRL-CONTROL-DEV-POOL-001"]["quality_manifest_relative_path"],
          quality_manifest_file_sha256=corpora_cfg["CRL-CONTROL-DEV-POOL-001"]["quality_manifest_file_sha256"])
        blind=blind_oos._load_blind_corpus(
          runtime_root,
          corpora_cfg["HSSE-BLIND-OOS-001"]["quality_manifest_relative_path"],
          corpora_cfg["HSSE-BLIND-OOS-001"]["quality_manifest_file_sha256"])
    except Exception as exc:
        raise HSSE005Error(str(exc)) from None
    corpora={"CRL-CONTROL-DEV-POOL-001":dev,"HSSE-BLIND-OOS-001":blind}
    series={cid:{s:_series(c,s) for s in ("BTCUSDT","ETHUSDT")} for cid,c in corpora.items()}
    policy=protocol["execution"]; gate=protocol["certification_gate"]
    blind_metrics={x["frozen_id"]:x for x in acceptance["survivors"]}
    cache={}
    candidates=[]
    for survivor in freeze["survivors"]:
        fid=survivor["frozen_id"]; family=survivor["family"]; n1=survivor["parameters"]["n1"]; n2=survivor["parameters"]["n2"]
        units=[]
        symbol_completed={"BTCUSDT":0,"ETHUSDT":0}
        for u in protocol["certification_units"]:
            cid=u["source_corpus_id"]; per={}
            start=_time_ms(u["semantic_start_utc"],"unit start"); end=_time_ms(u["semantic_end_exclusive_utc"],"unit end")
            for symbol in ("BTCUSDT","ETHUSDT"):
                ser=series[cid][symbol]
                for w in (n1,n2):
                    key=(cid,symbol,family,w)
                    if key not in cache: cache[key]=hsse2._indicator_series(ser.signal,family,w)
                r=_simulate_unit_symbol(series=ser,short_values=cache[(cid,symbol,family,n1)],long_values=cache[(cid,symbol,family,n2)],
                    start_ms=start,end_ms=end,lead_hours=int(policy["lead_in_hours"]),policy=policy)
                per[symbol]=r; symbol_completed[symbol]+=r["completed_trades"]
            base_net=hsse3._sum([per[s]["base_net"] for s in per]); stress_net=hsse3._sum([per[s]["stress_net"] for s in per])
            maxdd=max(per[s]["maximum_drawdown"] for s in per)
            active=any(per[s]["scored_entry_fills"]+per[s]["scored_exit_fills"]>0 for s in per)
            units.append({
              "unit_id":u["unit_id"],"label":u["label"],"event_ids":u["event_ids"],"source_corpus_id":cid,
              "base_net_pnl_after_costs_quote":hsse3._plain(base_net),"stress_net_pnl_after_costs_quote":hsse3._plain(stress_net),
              "maximum_drawdown_fraction":hsse3._plain(maxdd),"active":active,
              "completed_trades":sum(per[s]["completed_trades"] for s in per),
              "per_symbol":{s:{
                "base_net_pnl_after_costs_quote":hsse3._plain(per[s]["base_net"]),
                "stress_net_pnl_after_costs_quote":hsse3._plain(per[s]["stress_net"]),
                "maximum_drawdown_fraction":hsse3._plain(per[s]["maximum_drawdown"]),
                "completed_trades":per[s]["completed_trades"],
                "scored_entry_fills":per[s]["scored_entry_fills"],
                "scored_exit_fills":per[s]["scored_exit_fills"],
                "position_at_score_start":per[s]["position_at_score_start"],
                "position_at_score_end":per[s]["position_at_score_end"]
              } for s in per}
            })
        base_vals=[Decimal(x["base_net_pnl_after_costs_quote"]) for x in units]
        stress_vals=[Decimal(x["stress_net_pnl_after_costs_quote"]) for x in units]
        pos_base=sum(x>0 for x in base_vals); pos_stress=sum(x>0 for x in stress_vals); active=sum(x["active"] for x in units)
        with localcontext() as ctx:
            ctx.prec=hsse3.DECIMAL_PRECISION
            fbase=Decimal(pos_base)/Decimal(len(units)); fstress=Decimal(pos_stress)/Decimal(len(units)); factive=Decimal(active)/Decimal(len(units))
        med_base=hsse3._median_decimal(base_vals); med_stress=hsse3._median_decimal(stress_vals)
        worstdd=max(Decimal(x["maximum_drawdown_fraction"]) for x in units)
        blinddd=Decimal(blind_metrics[fid]["max_drawdown_fraction"])
        with localcontext() as ctx:
            ctx.prec=hsse3.DECIMAL_PRECISION
            ddl=max(Decimal("0.005"),Decimal(5)*blinddd)
            ddl=min(ddl,Decimal(gate["maximum_absolute_drawdown_ceiling"]))
        total_completed=sum(x["completed_trades"] for x in units)
        reasons=[]
        if fbase<Decimal(gate["minimum_positive_unit_fraction_base"]): reasons.append("BASE_POSITIVE_UNIT_FRACTION")
        if fstress<Decimal(gate["minimum_positive_unit_fraction_stress"]): reasons.append("STRESS_POSITIVE_UNIT_FRACTION")
        if med_base<=0: reasons.append("BASE_MEDIAN_NOT_POSITIVE")
        if med_stress<=0: reasons.append("STRESS_MEDIAN_NOT_POSITIVE")
        if total_completed<int(gate["minimum_total_completed_trades_in_scored_units"]): reasons.append("TOTAL_COMPLETED_TRADES")
        if any(symbol_completed[s]<int(gate["minimum_completed_trades_per_symbol_in_scored_units"]) for s in symbol_completed): reasons.append("PER_SYMBOL_COMPLETED_TRADES")
        if factive<Decimal(gate["minimum_active_unit_fraction"]): reasons.append("ACTIVE_UNIT_FRACTION")
        if worstdd>ddl: reasons.append("CRISIS_DRAWDOWN_LIMIT")
        candidates.append({
          "frozen_id":fid,"family":family,"parameters":{"n1":n1,"n2":n2},
          "units":units,
          "summary":{
            "positive_unit_fraction_base":hsse3._plain(fbase),"positive_unit_fraction_stress":hsse3._plain(fstress),
            "median_unit_net_base_quote":hsse3._plain(med_base),"median_unit_net_stress_quote":hsse3._plain(med_stress),
            "active_unit_fraction":hsse3._plain(factive),"total_completed_trades":total_completed,
            "completed_trades_by_symbol":symbol_completed,"worst_unit_drawdown_fraction":hsse3._plain(worstdd),
            "drawdown_limit_fraction":hsse3._plain(ddl)
          },
          "gate":{"status":"PASS" if not reasons else "FAIL","failure_reasons":reasons}
        })
    correlations=[]
    for i,a in enumerate(candidates):
        av=[Decimal(x["base_net_pnl_after_costs_quote"]) for x in a["units"]]
        for b in candidates[i+1:]:
            bv=[Decimal(x["base_net_pnl_after_costs_quote"]) for x in b["units"]]
            corr=_pearson(av,bv)
            agreement=sum(_sign(x)==_sign(y) for x,y in zip(av,bv))/len(av)
            correlations.append({"a":a["frozen_id"],"b":b["frozen_id"],"pearson_base_unit_pnl":None if corr is None else format(corr,".17g"),"sign_agreement_fraction":format(agreement,".17g")})
    passed=[x["frozen_id"] for x in candidates if x["gate"]["status"]=="PASS"]
    result={
      "schema":"YATL_HSSE_CRISIS_REGIME_CERTIFICATION_RESULT","schema_version":SCHEMA_VERSION,"implementation_id":IMPLEMENTATION_ID,
      "protocol_sha256":protocol_sha,"source_hsse004b_result_sha256":acceptance["result"]["result_sha256"],
      "candidate_count":6,"pass_count":len(passed),"fail_count":6-len(passed),"passed_frozen_ids":passed,
      "candidate_results":candidates,"correlation_diagnostics":correlations,
      "reranking_performed":False,"retuning_performed":False,"hidden_retry_performed":False,
      "audit_holdout_read":False,"recent_reserve_read":False,"research_only":True,"p10_read":False,"p10_write_allowed":False,
      "p10_evidence_effect":"NONE","trade_permission":False,"order_endpoint":False,"ai_direct_execution":False,"p11_locked":True
    }
    result["result_sha256"]=_sha256(_canonical_json(result))
    rel,digest=_write_result(runtime_root,result)
    return {"implementation_id":IMPLEMENTATION_ID,"pass_count":result["pass_count"],"fail_count":result["fail_count"],"passed_frozen_ids":passed,
      "artifact_relative_path":rel,"artifact_file_sha256":digest,"result_sha256":result["result_sha256"],
      "reranking_performed":False,"retuning_performed":False,"audit_holdout_read":False,"recent_reserve_read":False,
      "research_only":True,"p10_write_allowed":False,"p11_locked":True}

def main(argv:Sequence[str]|None=None):
    p=argparse.ArgumentParser()
    p.add_argument("--runtime-root",type=Path,required=True)
    p.add_argument("--protocol",type=Path,default=DEFAULT_PROTOCOL_PATH)
    p.add_argument("--validate-protocol-only",action="store_true")
    a=p.parse_args(argv)
    if a.validate_protocol_only:
        protocol,digest,_,freeze=load_protocol(a.protocol)
        print(_json({"implementation_id":IMPLEMENTATION_ID,"protocol_id":protocol["protocol_id"],"protocol_sha256":digest,
          "unit_count":len(protocol["certification_units"]),"survivor_count":len(freeze["survivors"]),"audit_holdout_read":False,
          "research_only":True,"p10_write_allowed":False,"p11_locked":True}))
        return 0
    print(_json(run(runtime_root=a.runtime_root,protocol_path=a.protocol)))
    return 0

if __name__=="__main__":
    try: raise SystemExit(main())
    except HSSE005Error as exc:
        print(_json({"code":"HSSE005_CERTIFICATION_ERROR","reason":str(exc),"research_only":True,"p10_write_allowed":False,"p11_locked":True}))
        raise SystemExit(2)
