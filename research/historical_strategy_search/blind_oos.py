"""HSSE-004B single-pass frozen Blind OOS replay.

Consumes only CRL-003-admitted HSSE-BLIND-OOS-001 data and the six immutable
HSSE-004A survivors. No parameter search, reranking, retuning or hidden retry.
"""
from __future__ import annotations

import argparse, bisect, hashlib, json, math, os
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Mapping, Sequence

from research.crisis_lab import acquisition as acq
from research.crisis_lab import replay
from . import blind_protocol
from . import survivor_ranking as hsse3
from . import trend_ma as hsse2
from . import survivor_freeze

IMPLEMENTATION_ID="HSSE-004B-FROZEN-BLIND-OOS/0.1.0"
SCHEMA_VERSION="0.1.0"
HOUR_MS=60*60*1000

class HSSEBlindReplayError(RuntimeError): pass

@dataclass(frozen=True,slots=True)
class BlindCorpus:
    event_id:str
    quality_manifest_relative_path:str
    quality_manifest_file_sha256:str
    datasets:dict[tuple[str,str],tuple[object,...]]

@dataclass(frozen=True,slots=True)
class ExactSeries:
    symbol:str
    times:tuple[int,...]
    opens:tuple[str,...]
    closes:tuple[str,...]

def _json(v):
    return json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False)

def _canonical_json(v):
    return (_json(v)+"\n").encode("utf-8")

def _sha256(b): return hashlib.sha256(b).hexdigest()

def _time_ms(v,label):
    if not isinstance(v,str) or not v.endswith("Z"): raise HSSEBlindReplayError(f"{label} is not UTC")
    try: dt=datetime.fromisoformat(v[:-1]+"+00:00")
    except ValueError: raise HSSEBlindReplayError(f"{label} is invalid") from None
    if dt.tzinfo!=timezone.utc: raise HSSEBlindReplayError(f"{label} is not UTC")
    return int(dt.timestamp()*1000)

def _load_blind_corpus(root:Path, rel:str, sha:str)->BlindCorpus:
    try:
        safe=replay._safe_root(root)
        qevent=replay._read_bound_json(safe,relative=rel,sha256=sha,prefix="event-quality-",label="HSSE Blind quality manifest")
    except replay.ReplayError as exc: raise HSSEBlindReplayError(str(exc)) from None
    if (qevent.get("schema")!="YATL_CRL_EVENT_QUALITY_MANIFEST" or qevent.get("schema_version")!=replay.QUALITY_SCHEMA_VERSION
        or qevent.get("event_id")!="HSSE-BLIND-OOS-001" or qevent.get("designation")!="BLIND_HOLDOUT"
        or qevent.get("overall_status")!="PASS" or qevent.get("replay_admitted") is not True
        or qevent.get("replay_eligible") is not True or qevent.get("dataset_count")!=6
        or qevent.get("pass_count")!=6 or qevent.get("fail_count")!=0
        or qevent.get("market_outcomes_exposed") is not False or qevent.get("research_only") is not True
        or qevent.get("p10_write_allowed") is not False or qevent.get("p11_locked") is not True):
        raise HSSEBlindReplayError("Blind corpus is not structurally admitted")
    refs=qevent.get("datasets")
    if not isinstance(refs,list) or len(refs)!=6: raise HSSEBlindReplayError("Blind dataset references are incomplete")
    expected={(s,i) for s in ("BTCUSDT","ETHUSDT") for i in ("15m","1h","4h")}
    loaded={}
    for item in refs:
        if not isinstance(item,dict): raise HSSEBlindReplayError("Blind quality reference is invalid")
        pair=(item.get("symbol"),item.get("interval"))
        if pair not in expected or pair in loaded: raise HSSEBlindReplayError("Blind dataset identity set is invalid")
        if item.get("quality_status")!="PASS" or item.get("replay_admitted") is not True or item.get("failure_codes")!=[]:
            raise HSSEBlindReplayError("Blind dataset failed structural quality")
        try:
            qsha=replay._require_sha(item.get("quality_manifest_file_sha256"),"Blind dataset quality SHA-256")
            q=replay._read_bound_json(safe,relative=item["quality_manifest_relative_path"],sha256=qsha,prefix="quality-",label="Blind dataset quality")
        except (KeyError,replay.ReplayError) as exc: raise HSSEBlindReplayError(str(exc)) from None
        if (q.get("event_id")!="HSSE-BLIND-OOS-001" or q.get("designation")!="BLIND_HOLDOUT"
            or q.get("symbol")!=pair[0] or q.get("interval")!=pair[1] or q.get("quality_status")!="PASS"
            or q.get("replay_admitted") is not True or q.get("market_outcomes_exposed") is not False):
            raise HSSEBlindReplayError("Blind dataset quality provenance is invalid")
        try:
            asha=replay._require_sha(q.get("input_acquisition_manifest_sha256"),"Blind acquisition SHA-256")
            a=replay._read_bound_json(safe,relative=q["input_acquisition_manifest_relative_path"],sha256=asha,prefix="acquisition-",label="Blind acquisition")
            candles=replay._load_canonical_candles(safe,symbol=str(pair[0]),interval=str(pair[1]),acquisition=a,quality=q)
        except (KeyError,replay.ReplayError) as exc: raise HSSEBlindReplayError(str(exc)) from None
        if a.get("event_id")!="HSSE-BLIND-OOS-001" or a.get("designation")!="BLIND_HOLDOUT":
            raise HSSEBlindReplayError("Blind acquisition provenance is invalid")
        loaded[(str(pair[0]),str(pair[1]))]=candles
    if set(loaded)!=expected: raise HSSEBlindReplayError("Blind corpus scope is incomplete")
    return BlindCorpus("HSSE-BLIND-OOS-001",rel,sha,loaded)

def _series(corpus:BlindCorpus,symbol:str):
    c=corpus.datasets[(symbol,"1h")]
    times=tuple(x.open_time_ms for x in c)
    if not c or times!=tuple(sorted(times)) or len(times)!=len(set(times)) or any(not x.is_closed for x in c):
        raise HSSEBlindReplayError(f"invalid 1h Blind series for {symbol}")
    signal=hsse2.SearchSeries(symbol,times,tuple(float(x.open) for x in c),tuple(float(x.close) for x in c))
    exact=ExactSeries(symbol,times,tuple(x.open for x in c),tuple(x.close for x in c))
    return signal,exact

def _quarter_key(ms:int)->str:
    dt=datetime.fromtimestamp(ms/1000,tz=timezone.utc)
    return f"{dt.year:04d}-Q{((dt.month-1)//3)+1}"

def _simulate_symbol(*,signal,exact,family,n1,n2,start_ms,end_ms,policy):
    short=hsse2._indicator_series(signal,family,n1)
    long=hsse2._indicator_series(signal,family,n2)
    start=bisect.bisect_left(exact.times,start_ms); end=bisect.bisect_left(exact.times,end_ms)
    if start>=end: raise HSSEBlindReplayError("Blind analysis has no 1h candles")
    quantity=Decimal(policy["quantity"]); initial=Decimal(policy["initial_equity_quote_per_symbol"])
    bf=Decimal(policy["base_fee_bps"]); bs=Decimal(policy["base_adverse_slippage_bps"])
    sf=Decimal(policy["stress_fee_bps"]); ss=Decimal(policy["stress_adverse_slippage_bps"])
    base=hsse3._new_account(initial); stress=hsse3._new_account(initial)
    position=False; peak=initial; maxdd=Decimal(0); missing=0; entries=0; exits=0
    quarter_start_equity=initial; current_quarter=None; last_equity=initial
    quarter_pnl={}
    for i in range(start,end):
        mark=Decimal(exact.closes[i])
        eq=hsse3._equity(base,mark=mark,quantity=quantity,fee_bps=bf,slippage_bps=bs)
        q=_quarter_key(exact.times[i])
        if current_quarter is None: current_quarter=q
        elif q!=current_quarter:
            with localcontext() as ctx:
                ctx.prec=hsse3.DECIMAL_PRECISION
                quarter_pnl[current_quarter]=last_equity-quarter_start_equity
            quarter_start_equity=last_equity; current_quarter=q
        last_equity=eq
        with localcontext() as ctx:
            ctx.prec=hsse3.DECIMAL_PRECISION
            if eq>peak: peak=eq
            dd=(peak-eq)/peak
        if dd>maxdd: maxdd=dd
        if i==0: continue
        vals=(short[i],long[i],short[i-1],long[i-1])
        if not all(math.isfinite(v) for v in vals): continue
        sn,ln,sp,lp=vals
        enter=(not position) and sn>ln and sp<=lp
        exit_=position and sn<ln and sp>=lp
        if not enter and not exit_: continue
        fi=i+1
        if fi>=end or fi>=len(exact.times) or exact.times[fi]!=exact.times[i]+HOUR_MS:
            missing+=1; continue
        ref=Decimal(exact.opens[fi])
        if enter:
            hsse3._entry(base,reference=ref,quantity=quantity,fee_bps=bf,slippage_bps=bs)
            hsse3._entry(stress,reference=ref,quantity=quantity,fee_bps=sf,slippage_bps=ss)
            position=True; entries+=1
        else:
            hsse3._exit(base,reference=ref,quantity=quantity,fee_bps=bf,slippage_bps=bs)
            hsse3._exit(stress,reference=ref,quantity=quantity,fee_bps=sf,slippage_bps=ss)
            position=False; exits+=1
    if current_quarter is not None:
        with localcontext() as ctx:
            ctx.prec=hsse3.DECIMAL_PRECISION
            quarter_pnl[current_quarter]=last_equity-quarter_start_equity
    final_mark=Decimal(exact.closes[end-1])
    base_final=hsse3._equity(base,mark=final_mark,quantity=quantity,fee_bps=bf,slippage_bps=bs)
    stress_final=hsse3._equity(stress,mark=final_mark,quantity=quantity,fee_bps=sf,slippage_bps=ss)
    with localcontext() as ctx:
        ctx.prec=hsse3.DECIMAL_PRECISION
        finaldd=(peak-base_final)/peak
        base_net=base_final-initial; stress_net=stress_final-initial
    maxdd=max(maxdd,finaldd)
    wins=[x for x in base.realized if x>0]; losses=[x for x in base.realized if x<0]
    return {
      "completed_trades":len(base.realized),"wins":len(wins),"losses":len(losses),
      "entry_fills":entries,"exit_fills":exits,"missing_fill_signals":missing,"open_position_at_end":position,
      "base_net":base_net,"stress_net":stress_net,"realized":hsse3._sum(base.realized),
      "stress_realized":hsse3._sum(stress.realized),"gross_profit":hsse3._sum(wins),
      "gross_loss":-hsse3._sum(losses),"max_drawdown":maxdd,"quarter_pnl":quarter_pnl
    }

def _candidate(*,survivor,signal_by_symbol,exact_by_symbol,start_ms,end_ms,protocol):
    p=survivor["parameters"]; family=survivor["family"]; per={}
    for symbol in ("BTCUSDT","ETHUSDT"):
        per[symbol]=_simulate_symbol(signal=signal_by_symbol[symbol],exact=exact_by_symbol[symbol],family=family,
          n1=p["n1"],n2=p["n2"],start_ms=start_ms,end_ms=end_ms,policy=protocol["execution"])
    completed=sum(x["completed_trades"] for x in per.values())
    realized=hsse3._sum([x["realized"] for x in per.values()])
    stress_realized=hsse3._sum([x["stress_realized"] for x in per.values()])
    total_net=hsse3._sum([x["base_net"] for x in per.values()])
    stress_net=hsse3._sum([x["stress_net"] for x in per.values()])
    gp=hsse3._sum([x["gross_profit"] for x in per.values()]); gl=hsse3._sum([x["gross_loss"] for x in per.values()])
    pf_text,pf_inf,pf=hsse3._profit_factor(gp,gl)
    with localcontext() as ctx:
        ctx.prec=hsse3.DECIMAL_PRECISION
        expectancy=realized/Decimal(completed) if completed else Decimal(0)
        stress_expectancy=stress_realized/Decimal(completed) if completed else Decimal(0)
    quarters=sorted(set().union(*(x["quarter_pnl"].keys() for x in per.values())))
    aggregate_quarters={}
    for q in quarters:
        aggregate_quarters[q]=hsse3._sum([per[s]["quarter_pnl"].get(q,Decimal(0)) for s in per])
    positive=sum(v>0 for v in aggregate_quarters.values())
    with localcontext() as ctx:
        ctx.prec=hsse3.DECIMAL_PRECISION
        positive_fraction=Decimal(positive)/Decimal(len(aggregate_quarters)) if aggregate_quarters else Decimal(0)
    maxdd=max(x["max_drawdown"] for x in per.values())
    gate=protocol["blind_gate"]; reasons=[]
    if completed<int(gate["minimum_completed_trades_total"]): reasons.append("MINIMUM_COMPLETED_TRADES_TOTAL")
    if any(per[s]["completed_trades"]<int(gate["minimum_completed_trades_per_symbol"]) for s in per): reasons.append("MINIMUM_COMPLETED_TRADES_PER_SYMBOL")
    if total_net<=0: reasons.append("TOTAL_NET_PNL_NOT_POSITIVE")
    if expectancy<=0: reasons.append("EXPECTANCY_NOT_POSITIVE")
    if not pf_inf and (pf is None or pf<Decimal(gate["minimum_profit_factor_after_base_costs"])): reasons.append("PROFIT_FACTOR_GATE_FAILED")
    if positive_fraction<Decimal(gate["minimum_positive_calendar_quarter_fraction"]): reasons.append("POSITIVE_QUARTER_FRACTION_GATE_FAILED")
    if maxdd>Decimal(gate["maximum_drawdown_fraction"]): reasons.append("MAXIMUM_DRAWDOWN_GATE_FAILED")
    return {
      "frozen_id":survivor["frozen_id"],"source_trial_id":survivor["source_trial_id"],"family":family,"parameters":p,
      "completed_trades":completed,"completed_trades_by_symbol":{s:per[s]["completed_trades"] for s in per},
      "base":{"total_net_pnl_after_costs_quote":hsse3._plain(total_net),"realized_closed_trade_pnl_quote":hsse3._plain(realized),
        "expectancy_quote":hsse3._plain(expectancy),"profit_factor":pf_text,"profit_factor_infinite":pf_inf,
        "maximum_drawdown_fraction":hsse3._plain(maxdd),"positive_calendar_quarter_fraction":hsse3._plain(positive_fraction)},
      "stress":{"total_net_pnl_after_costs_quote":hsse3._plain(stress_net),"realized_closed_trade_pnl_quote":hsse3._plain(stress_realized),
        "expectancy_quote":hsse3._plain(stress_expectancy)},
      "quarters":[{"quarter":q,"aggregate_net_pnl_after_costs_quote":hsse3._plain(aggregate_quarters[q])} for q in quarters],
      "gate":{"status":"PASS" if not reasons else "FAIL","failure_reasons":reasons}
    }

def _write_result(root:Path,record):
    payload=_canonical_json(record); digest=_sha256(payload)
    d=root/"historical-strategy-search"/"hsse-004b"; d.mkdir(parents=True,exist_ok=True)
    p=d/f"blind-oos-{digest[:24]}.json"
    if p.exists():
        if p.read_bytes()!=payload: raise HSSEBlindReplayError("existing Blind result differs")
    else:
        fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,"wb") as h: h.write(payload); h.flush(); os.fsync(h.fileno())
    return p.relative_to(root).as_posix(),digest

def run(*,runtime_root:Path,quality_manifest:str,quality_manifest_sha256:str,protocol_path:Path=blind_protocol.DEFAULT_PROTOCOL_PATH):
    protocol,protocol_sha,freeze_validation=blind_protocol.load_protocol(protocol_path)
    freeze_path=Path(protocol["freeze"]["relative_path"])
    freeze=json.loads(freeze_path.read_text(encoding="utf-8"))
    src=freeze["source_hsse003"]
    artifact=(runtime_root/src["artifact_relative_path"]).resolve()
    if not artifact.is_relative_to(runtime_root.resolve()): raise HSSEBlindReplayError("HSSE-003 artifact path escapes root")
    try: artifact_bytes=artifact.read_bytes()
    except OSError: raise HSSEBlindReplayError("cannot read bound HSSE-003 artifact") from None
    if _sha256(artifact_bytes)!=src["artifact_file_sha256"]: raise HSSEBlindReplayError("HSSE-003 artifact SHA mismatch before Blind")
    corpus=_load_blind_corpus(runtime_root,quality_manifest,quality_manifest_sha256)
    signal_by_symbol={}; exact_by_symbol={}
    for s in ("BTCUSDT","ETHUSDT"):
        signal_by_symbol[s],exact_by_symbol[s]=_series(corpus,s)
    start=_time_ms(protocol["data"]["analysis_start_utc"],"Blind start"); end=_time_ms(protocol["data"]["analysis_end_exclusive_utc"],"Blind end")
    results=[_candidate(survivor=x,signal_by_symbol=signal_by_symbol,exact_by_symbol=exact_by_symbol,start_ms=start,end_ms=end,protocol=protocol) for x in freeze["survivors"]]
    passed=[x["frozen_id"] for x in results if x["gate"]["status"]=="PASS"]
    result={
      "schema":"YATL_HSSE_BLIND_OOS_RESULT","schema_version":SCHEMA_VERSION,"implementation_id":IMPLEMENTATION_ID,
      "protocol_sha256":protocol_sha,"freeze_file_sha256":freeze_validation["freeze_file_sha256"],
      "source_hsse003_artifact_file_sha256":src["artifact_file_sha256"],"source_quality_manifest_relative_path":quality_manifest,
      "source_quality_manifest_file_sha256":quality_manifest_sha256,"source_event_id":corpus.event_id,
      "analysis_start_utc":protocol["data"]["analysis_start_utc"],"analysis_end_exclusive_utc":protocol["data"]["analysis_end_exclusive_utc"],
      "frozen_survivor_count":6,"evaluated_survivor_count":len(results),"pass_count":len(passed),"fail_count":len(results)-len(passed),
      "passed_frozen_ids":passed,"candidate_results":results,"reranking_performed":False,"retuning_performed":False,
      "hidden_retry_performed":False,"audit_holdout_read":False,"research_only":True,"p10_read":False,"p10_write_allowed":False,
      "p10_evidence_effect":"NONE","trade_permission":False,"order_endpoint":False,"ai_direct_execution":False,"p11_locked":True
    }
    result["result_sha256"]=_sha256(_canonical_json(result))
    rel,digest=_write_result(runtime_root,result)
    return {"implementation_id":IMPLEMENTATION_ID,"pass_count":result["pass_count"],"fail_count":result["fail_count"],
      "passed_frozen_ids":passed,"artifact_relative_path":rel,"artifact_file_sha256":digest,"result_sha256":result["result_sha256"],
      "reranking_performed":False,"retuning_performed":False,"audit_holdout_read":False,"research_only":True,"p10_write_allowed":False,"p11_locked":True}

def main(argv:Sequence[str]|None=None):
    p=argparse.ArgumentParser()
    p.add_argument("--runtime-root",type=Path,required=True); p.add_argument("--quality-manifest",required=True)
    p.add_argument("--quality-manifest-sha256",required=True); p.add_argument("--protocol",type=Path,default=blind_protocol.DEFAULT_PROTOCOL_PATH)
    a=p.parse_args(argv)
    print(_json(run(runtime_root=a.runtime_root,quality_manifest=a.quality_manifest,quality_manifest_sha256=a.quality_manifest_sha256,protocol_path=a.protocol)))
    return 0

if __name__=="__main__":
    try: raise SystemExit(main())
    except (HSSEBlindReplayError,blind_protocol.HSSEBlindError,survivor_freeze.HSSEFreezeError) as exc:
        print(_json({"code":"HSSE004B_BLIND_REPLAY_ERROR","reason":str(exc),"research_only":True,"p10_write_allowed":False,"p11_locked":True}))
        raise SystemExit(2)
