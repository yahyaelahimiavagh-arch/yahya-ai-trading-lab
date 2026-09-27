"""Immutable, partition-scoped feature cache; completed bars only."""
from __future__ import annotations
import math
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from .models import MCFError, digest

VERSION="MCF_FEATURES/1.0.0"
@dataclass(frozen=True)
class Bars:
    dataset_id: str
    partition: str
    symbol: str
    timeframe: str
    times: tuple[int,...]
    opens: tuple[float,...]
    highs: tuple[float,...]
    lows: tuple[float,...]
    closes: tuple[float,...]
    base_volume: tuple[float,...]
    quote_volume: tuple[float,...]
    trade_count: tuple[float,...]

    def validate(self):
        n=len(self.times)
        if self.partition != "DEVELOPMENT" or not self.dataset_id or self.symbol not in ("BTCUSDT","ETHUSDT") or self.timeframe not in ("15m","1h","4h","1d") or n<2 or any(len(getattr(self,k)) != n for k in ("opens","highs","lows","closes","base_volume","quote_volume","trade_count")) or any(a>=b for a,b in zip(self.times,self.times[1:])):
            raise MCFError("invalid admitted bars")
        if any(not math.isfinite(v) for name in ("opens","highs","lows","closes","base_volume","quote_volume","trade_count") for v in getattr(self,name)):
            raise MCFError("nonfinite bars")

class FeatureCache:
    def __init__(self, bars: Bars, peers: dict[str,Bars]|None=None):
        bars.validate()
        self.bars=bars;self.peers=peers or {};self.values={};self.builds=0
        for peer in self.peers.values():
            peer.validate()
            if peer.dataset_id != bars.dataset_id or peer.partition != bars.partition or peer.timeframe != bars.timeframe or peer.times != bars.times:
                raise MCFError("cross-partition or unaligned peer")

    def get(self, feature: str, *, window:int=1, lag:int=1, field:str="closes", symbol:str=""):
        if not isinstance(window,int) or not 1<=window<=100000 or not isinstance(lag,int) or not 1<=lag<=100000 or field not in ("opens","highs","lows","closes","base_volume","quote_volume","trade_count"):
            raise MCFError("invalid bounded feature arguments")
        from .manifest import FEATURES
        if feature not in FEATURES:
            raise MCFError("unknown feature")
        key=digest({"dataset":self.bars.dataset_id,"partition":self.bars.partition,"symbol":self.bars.symbol,"timeframe":self.bars.timeframe,"feature":feature,"window":window,"lag":lag,"field":field,"peer":symbol,"engine":VERSION})
        if key in self.values: return self.values[key]
        b=self.bars;n=len(b.times);source=getattr(b,field)
        if feature=="BASE_VOLUME_MEAN":source=b.base_volume
        if feature=="QUOTE_VOLUME_MEAN":source=b.quote_volume
        if feature=="TRADE_COUNT_MEAN":source=b.trade_count
        if feature=="OHLC_RANGE": vals=tuple(h-l for h,l in zip(b.highs,b.lows))
        elif feature=="UTC_SESSION": vals=tuple(float(datetime.fromtimestamp(t/1000,timezone.utc).hour) for t in b.times)
        elif feature in ("LAGGED_RETURN","CROSS_ASSET_LAGGED_RETURN"):
            if feature.startswith("CROSS"):
                if b.symbol not in ("BTCUSDT","ETHUSDT") or symbol not in self.peers or symbol not in ("BTCUSDT","ETHUSDT") or symbol==b.symbol:
                    raise MCFError("unadmitted cross-asset dependency")
                source=self.peers[symbol].closes
            vals=tuple(None if i<lag or source[i-lag]==0 else source[i]/source[i-lag]-1 for i in range(n))
        elif feature in ("ROLLING_MIN","ROLLING_MAX","MOVING_AVERAGE","ROLLING_MEAN","ROLLING_STD","BASE_VOLUME_MEAN","QUOTE_VOLUME_MEAN","TRADE_COUNT_MEAN"):
            vals=[];s=0.0;ss=0.0
            for i,x in enumerate(source):
                s+=x;ss+=x*x
                if i>=window: s-=source[i-window];ss-=source[i-window]**2
                if i+1<window: vals.append(None);continue
                if feature=="ROLLING_MIN":vals.append(min(source[i-window+1:i+1]))
                elif feature=="ROLLING_MAX":vals.append(max(source[i-window+1:i+1]))
                elif feature=="ROLLING_STD":vals.append(math.sqrt(max(0.0,ss/window-(s/window)**2)))
                else: vals.append(s/window)
            vals=tuple(vals)
        else: raise MCFError("unsupported feature")
        self.values[key]=vals;self.builds+=1
        return vals
