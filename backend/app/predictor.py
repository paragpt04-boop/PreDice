"""Leakage-resistant empirical-analogue baseline, not a calibrated ML oracle."""
from __future__ import annotations
import math
from dataclasses import dataclass
from statistics import median
from .market import Candle

@dataclass
class Result:
    expected_pct: float
    p10_pct: float
    p50_pct: float
    p90_pct: float
    up_vote: float
    neighbors: int

def quantile(data: list[float], q: float) -> float:
    a = sorted(data)
    x = q * (len(a) - 1)
    low = int(x)
    return a[low] + (a[min(low + 1, len(a) - 1)] - a[low]) * (x - low)

def features(candles: list[Candle], i: int, closes: list[float] | None = None) -> tuple[float, ...]:
    if closes is None: closes = [x.close for x in candles]
    rets = [math.log(closes[k] / closes[k-1]) for k in range(i - 23, i + 1)]
    mean = sum(rets) / len(rets)
    sigma = math.sqrt(sum((r-mean)**2 for r in rets) / len(rets))
    current = candles[i]
    lows = min(c.low for c in candles[i - 19:i+1])
    highs = max(c.high for c in candles[i - 19:i+1])
    volumes = [c.volume for c in candles[i-19:i+1]]
    average_volume = sum(volumes)/20
    return (
        math.log(closes[i] / closes[i-3]),
        math.log(closes[i] / closes[i-12]),
        math.log(closes[i] / closes[i-24]),
        sigma,
        (current.volume / average_volume - 1) if average_volume else 0,
        (current.close-lows)/(highs-lows) if highs > lows else 0.5,
    )

def forecast(candles: list[Candle], horizon_bars: int, asof: int | None = None, neighbors: int = 35) -> Result | None:
    """Only training outcomes with index i + horizon <= asof are used."""
    t = len(candles) - 1 if asof is None else asof
    h = horizon_bars
    if t < max(240, 60 + h) or h < 1: return None
    closes = [x.close for x in candles]
    current = features(candles, t, closes)
    candidates = []
    for i in range(30, t-h+1):
        if candles[i+h].ts - candles[i].ts != h * (candles[i+1].ts - candles[i].ts):
            continue  # skip broken/missing timestamp windows
        f = features(candles, i, closes)
        target = (candles[i+h].close/candles[i].close-1)*100
        candidates.append((f, target))
    if len(candidates) < 150: return None
    scales = []
    for j in range(len(current)):
        values = [c[0][j] for c in candidates]
        center = sum(values)/len(values)
        std = math.sqrt(sum((x-center)**2 for x in values)/len(values))
        scales.append(max(std, 1e-5 if j != 4 else 0.02))
    distances = []
    for f, target in candidates:
        d = sum(((a-b)/s)**2 for a,b,s in zip(f,current,scales))
        distances.append((d,target))
    best = sorted(distances,key=lambda p:p[0])[:neighbors]
    if len(best) < 20: return None
    weights = [1/(1+math.sqrt(d)) for d,_ in best]
    total = sum(weights)
    return Result(
        expected_pct=sum(w*y for w,(_,y) in zip(weights,best))/total,
        p10_pct=quantile([y for _,y in best], .1),
        p50_pct=median([y for _,y in best]),
        p90_pct=quantile([y for _,y in best], .9),
        up_vote=sum(w for w,(_,y) in zip(weights,best) if y>0)/total,
        neighbors=len(best))

def walk_forward(candles: list[Candle], h: int, max_evaluations: int = 45) -> dict:
    """Each backtest prediction learns only from outcomes completed by its historical as-of."""
    final_index = len(candles)-h-1
    if final_index < 300: return {"evaluations":0,"accuracy_pct":None,"mae_pct":None}
    start = max(280,final_index - max_evaluations * max(1,h))
    indices = list(range(start,final_index+1,max(1,h)))[-max_evaluations:]
    good, n, error = 0, 0, 0.
    for i in indices:
        pred = forecast(candles,h,asof=i)
        if not pred: continue
        actual=(candles[i+h].close/candles[i].close-1)*100
        good += int((pred.expected_pct>0)==(actual>0))
        error += abs(pred.expected_pct-actual)
        n += 1
    return {"evaluations":n,"accuracy_pct":round(100*good/n,1) if n else None,
            "mae_pct":round(error/n,3) if n else None}
