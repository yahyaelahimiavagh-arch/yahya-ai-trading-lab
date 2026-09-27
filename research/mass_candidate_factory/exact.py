"""Decimal recompute using the existing HSSE-003 fill/equity primitives."""
from __future__ import annotations
from decimal import Decimal, localcontext
from research.historical_strategy_search import survivor_ranking as trusted
from yatl.backtest.costs import DECIMAL_PRECISION
from .models import MCFError, CostPolicy

VERSION="MCF_EXACT/1.0.0"

def account(signals, opens, closes, policy:CostPolicy, *, stress=False):
    policy.validate()
    if len(signals)!=len(opens) or len(opens)!=len(closes) or len(opens)<2:
        raise MCFError("series lengths")
    with localcontext() as ctx:
        ctx.prec=DECIMAL_PRECISION
        fee=Decimal(policy.stress_fee_bps if stress else policy.base_fee_bps)
        slip=Decimal(policy.stress_slippage_bps if stress else policy.base_slippage_bps)
        qty=Decimal(policy.quantity);initial=Decimal(policy.initial_equity)
        a=trusted._new_account(initial); equity_peak=initial; dd=Decimal(0);fills=0
        # Signal at close(i-1) is filled at open(i). No same-bar lookahead.
        for i in range(1,len(signals)):
            p=Decimal(str(opens[i])); held=a.entry_debit is not None
            if bool(signals[i-1]) and not held:
                trusted._entry(a,reference=p,quantity=qty,fee_bps=fee,slippage_bps=slip);fills+=1
            elif not bool(signals[i-1]) and held:
                trusted._exit(a,reference=p,quantity=qty,fee_bps=fee,slippage_bps=slip);fills+=1
            eq=trusted._equity(a,mark=Decimal(str(closes[i])),quantity=qty,fee_bps=fee,slippage_bps=slip)
            equity_peak=max(equity_peak,eq);dd=max(dd,(equity_peak-eq)/equity_peak)
        final=trusted._equity(a,mark=Decimal(str(closes[-1])),quantity=qty,fee_bps=fee,slippage_bps=slip)
        return {"net":str(final-initial),"maximum_drawdown_fraction":str(dd),"fills":fills,"realized":str(sum(a.realized,Decimal(0))),"fees":str(a.total_fee),"slippage":str(a.total_slippage)}

def compare(screening:dict, exact:dict, *, guard_band:str):
    margin=Decimal(guard_band);error=abs(Decimal(str(screening["net"]))-Decimal(exact["net"]))
    return {"exact_recompute_state":"EXACT_AGREES" if error<=margin else "IMPLEMENTATION_BLOCKER", "maximum_numerical_discrepancy":str(error),"guard_band":str(margin),"identity":VERSION}
