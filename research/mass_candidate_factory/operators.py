"""Versioned finite operator grammar; no expression interpretation."""
from __future__ import annotations
from .models import MCFError

VERSION="MCF_OPERATORS/1.0.0"

def evaluate(rule:dict, cache, params:dict):
    """Decision at completed bar i; caller fills only at i+1 open."""
    from .manifest import _template
    _template(rule)
    n=len(cache.bars.times)
    op=rule.get("operator")
    if op in ("AND","OR"):
        children=[evaluate(x,cache,params) for x in rule["children"]]
        return tuple((all if op=="AND" else any)(c[i] for c in children) for i in range(n))
    def values(x):
        if isinstance(x,dict):
            if "feature" not in x: raise MCFError("feature operand required")
            kw={k:params.get(v[1:],v) if isinstance(v,str) and v.startswith("$") else v for k,v in x.items() if k in ("window","lag","field","symbol")}
            return cache.get(x["feature"],**kw)
        v=params.get(x[1:]) if isinstance(x,str) and x.startswith("$") else x
        if not isinstance(v,(int,float)):
            raise MCFError("unbound typed operand")
        return (v,)*n
    a=values(rule["left"]);b=values(rule["right"])
    if op in ("GT","ZSCORE_GT","BREAKOUT"): cmp=lambda x,y:x>y
    elif op in ("LT","ZSCORE_LT","REENTRY"): cmp=lambda x,y:x<y
    elif op in ("CROSS_ABOVE","CROSS_BELOW"): cmp=(lambda x,y:x>y) if op=="CROSS_ABOVE" else (lambda x,y:x<y)
    else: raise MCFError("unknown rule operator")
    out=[]
    for i,(x,y) in enumerate(zip(a,b)):
        valid=x is not None and y is not None
        now=valid and cmp(x,y)
        if op.startswith("CROSS") or op in ("BREAKOUT","REENTRY"):
            now=now and i>0 and a[i-1] is not None and b[i-1] is not None and not cmp(a[i-1],b[i-1])
        out.append(bool(now))
    return tuple(out)

def long_cash(entry:tuple[bool,...], exit:tuple[bool,...], eligibility:tuple[bool,...]|None=None):
    if len(entry)!=len(exit) or (eligibility is not None and len(eligibility)!=len(entry)):
        raise MCFError("state-machine length mismatch")
    state=False;positions=[]
    for i in range(len(entry)):
        allowed=True if eligibility is None else eligibility[i]
        if state and (exit[i] or not allowed): state=False
        elif not state and entry[i] and allowed: state=True
        positions.append(state)
    return tuple(positions)
