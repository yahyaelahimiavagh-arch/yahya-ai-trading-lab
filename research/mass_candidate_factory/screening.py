"""F0-F3 engineering screening; no survivor state or data loading."""
from __future__ import annotations
from .models import MCFError, CostPolicy, EvidenceBinding
from .exact import account, compare

VERSION="MCF_SCREENING/1.0.0"

def float_account(signals, opens, closes, policy:CostPolicy, *,stress=False):
    policy.validate();fee=float(policy.stress_fee_bps if stress else policy.base_fee_bps)/10000;slip=float(policy.stress_slippage_bps if stress else policy.base_slippage_bps)/10000
    qty=float(policy.quantity);cash=float(policy.initial_equity);debit=None;peak=cash;dd=0.;fills=0;realized=0.;fees=0.;slippage=0.
    for i in range(1,len(signals)):
        price=float(opens[i]);held=debit is not None
        if signals[i-1] and not held:
            ex=price*(1+slip);gross=qty*ex;cost=gross*fee;debit=gross+cost
            cash-=debit
            if cash < -1e-10: raise MCFError("insufficient cash")
            fills+=1;fees+=cost;slippage+=qty*(ex-price)
        elif not signals[i-1] and held:
            ex=price*(1-slip);gross=qty*ex;cost=gross*fee;proceeds=gross-cost
            cash+=proceeds;realized+=proceeds-debit;debit=None;fills+=1;fees+=cost;slippage+=qty*(price-ex)
        mark=float(closes[i]);eq=cash+(qty*mark*(1-slip)*(1-fee) if debit is not None else 0.)
        peak=max(peak,eq);dd=max(dd,(peak-eq)/peak)
    return {"net":cash+(qty*float(closes[-1])*(1-slip)*(1-fee) if debit is not None else 0.)-float(policy.initial_equity),"maximum_drawdown_fraction":dd,"fills":fills,"realized":realized,"fees":fees,"slippage":slippage}

def screen(signals, opens, closes, policy, *, cost_policy_ref:str, thresholds:dict, folds:tuple[tuple[int,int],...], guard_band:str="0.000001", evidence:EvidenceBinding|None=None, fixture_id:str|None=None):
    if policy.ref != cost_policy_ref:
        raise MCFError("unbound cost policy")
    if evidence is not None and fixture_id is None:
        evidence.validate()
        data_id=evidence.dataset_id
    elif evidence is None and isinstance(fixture_id,str) and fixture_id.startswith("SYNTHETIC-"):
        data_id=fixture_id
    else:
        raise MCFError("screening requires bound Development evidence or synthetic fixture")
    if not (len(signals)==len(opens)==len(closes)) or len(signals)<3 or not folds or folds[0][0]!=0 or folds[-1][1]!=len(signals) or any(a>=b or b-a<3 or (i and a!=folds[i-1][1]) for i,(a,b) in enumerate(folds)):
        raise MCFError("noncanonical fold/series")
    if any(k not in ("minimum_signals","minimum_fills","minimum_base_net","minimum_stress_net","minimum_passing_folds") for k in thresholds):
        raise MCFError("unknown hard gate")
    opportunity={"signals":sum(bool(x) for x in signals[:-1]),"active_bars":sum(bool(x) for x in signals[:-1])}
    base=float_account(signals,opens,closes,policy);stress=float_account(signals,opens,closes,policy,stress=True)
    temporal=[float_account(signals[a:b],opens[a:b],closes[a:b],policy)["net"] for a,b in folds]
    metrics={"minimum_signals":opportunity["signals"],"minimum_fills":base["fills"],"minimum_base_net":base["net"],"minimum_stress_net":stress["net"],"minimum_passing_folds":sum(x>=0 for x in temporal)}
    failures=[];gray=[];guard=float(guard_band)
    for key,minimum in thresholds.items():
        delta=metrics[key]-float(minimum)
        if abs(delta)<=guard:gray.append(key)
        elif delta<0:failures.append(key)
    # Every hard gate remains binding; exact recompute is mandatory in the gray zone.
    exact_state="NOT_REQUIRED"
    discrepancy="0"
    if gray or not failures:
        exact_base=account(signals,opens,closes,policy);exact_stress=account(signals,opens,closes,policy,stress=True)
        exact_folds=[account(signals[a:b],opens[a:b],closes[a:b],policy)["net"] for a,b in folds]
        a=compare(base,exact_base,guard_band=guard_band);b=compare(stress,exact_stress,guard_band=guard_band)
        fold_error=max(abs(float(x)-float(y)) for x,y in zip(temporal,exact_folds))
        discrepancy=str(max(float(a["maximum_numerical_discrepancy"]),float(b["maximum_numerical_discrepancy"]),fold_error))
        if "IMPLEMENTATION_BLOCKER" in (a["exact_recompute_state"],b["exact_recompute_state"]) or fold_error>guard: raise MCFError("screening/exact discrepancy exceeds guard band")
        exact_state="EXACT_RECOMPUTED"
        exact_metrics={"minimum_signals":opportunity["signals"],"minimum_fills":exact_base["fills"],"minimum_base_net":float(exact_base["net"]),"minimum_stress_net":float(exact_stress["net"]),"minimum_passing_folds":sum(float(x)>=0 for x in exact_folds)}
        failures=[k for k,v in thresholds.items() if exact_metrics[k]<float(v)]
    return {"result_state":"DEVELOPMENT_FAIL" if failures else "DEVELOPMENT_GATE_PASS","failure_reasons":sorted(failures),"opportunity_metrics":opportunity,"base_economics":base,"stress_economics":stress,"temporal_metrics":{"fold_net":temporal},"exact_recompute_state":exact_state,"maximum_numerical_discrepancy":discrepancy,"screening_engine_version":VERSION,"dataset_id":data_id,"calibration_state":"ENGINEERING_ONLY_NO_SELECTION"}
