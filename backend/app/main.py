from __future__ import annotations
import os
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import httpx

from . import database, market
from .predictor import forecast, walk_forward

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.client = httpx.AsyncClient(headers={"User-Agent":"PreDice/0.1"},limits=httpx.Limits(max_connections=10))
    database.connect().close()
    yield
    await app.state.client.aclose()

app = FastAPI(title="PreDice", version="0.1.0", lifespan=lifespan)
allowed=[x.strip() for x in os.getenv("PREDICE_ALLOWED_ORIGINS","").split(",") if x.strip()]
if allowed:
    app.add_middleware(CORSMiddleware, allow_origins=allowed, allow_methods=["GET","POST"],allow_headers=["Content-Type"])

_cache: dict[str, tuple[float, object]] = {}
async def cached(key,ttl,fn):
    hit=_cache.get(key)
    if hit and time.monotonic()-hit[0]<ttl: return hit[1]
    result=await fn()
    _cache[key]=(time.monotonic(),result)
    return result

def fail(error: Exception):
    if isinstance(error,ValueError): raise HTTPException(422,str(error))
    raise HTTPException(502,"Fuente de datos de mercado no disponible")

@app.get("/health")
def health(): return {"status":"ok","version":"0.1.0","engine":"empirical-analog-baseline"}

@app.get("/api/v1/assets")
async def assets(q: str = Query("",max_length=160)):
    try:
        pairs=await cached("pairs",600,lambda:market.trading_pairs(app.state.client))
        term = q.strip().upper()
        if term.startswith(("HTTP://","HTTPS://")) or "/" in term:
            try: term = market.normalize_symbol(term)
            except ValueError: term = ""
        matches = [x for x in pairs if term in x["symbol"] or term in (x.get("base") or "")]
        return {"popular":market.POPULAR,"assets":[{"symbol":x["symbol"],"base":x.get("base",""),"quote":x.get("quote","")} for x in matches[:100]]}
    except Exception as e: fail(e)

@app.get("/api/v1/tickers")
async def tickers(symbols: str = Query("BTCUSDT,ETHUSDT,SOLUSDT,XRPUSDT",max_length=300)):
    try:
        values=list(dict.fromkeys(market.normalize_symbol(s) for s in symbols.split(",") if s.strip()))[:20]
        data=await cached("ticker:"+",".join(values),10,lambda:market.tickers(app.state.client,values))
        return {"items":data,"source":"Bitunix futures","asof_ms":int(time.time()*1000)}
    except Exception as e: fail(e)

@app.get("/api/v1/predict/{symbol}")
async def predict(symbol: str,horizon: str = "15m"):
    if horizon not in market.HORIZONS: raise HTTPException(422,"Horizonte no válido")
    try:
        sym=market.normalize_symbol(symbol)
        interval,h=market.HORIZONS[horizon]
        candles=await cached("candles:"+sym+":"+interval,45,lambda:market.history(app.state.client,sym,interval))
        database.resolve(sym,candles,market.INTERVAL_MS[interval])
        result=forecast(candles,h)
        if not result:
            return {"symbol":sym,"horizon":horizon,"status":"insufficient_data",
                    "bars_available":len(candles),"signal":"WAIT","reason":"Histórico cerrado insuficiente; no se inventa predicción"}
        last=candles[-1]
        asof=last.ts+market.INTERVAL_MS[interval]
        target=asof+h*market.INTERVAL_MS[interval]
        signal="WAIT"
        # Filters intentionally conservative; these are NOT validated trading edges.
        if result.up_vote>=0.68 and result.expected_pct>0.35: signal="LONG_CANDIDATE"
        elif result.up_vote<=0.32 and result.expected_pct< -0.35: signal="SHORT_CANDIDATE"
        database.remember(sym,horizon,asof,target,last.close,result,signal)
        quality=walk_forward(candles,h)
        return {"symbol":sym,"horizon":horizon,"status":"experimental","signal":signal,
                "base_price":last.close,"asof_ms":asof,"target_ms":target,
                "expected_change_pct":round(result.expected_pct,4),
                "scenario_p10_pct":round(result.p10_pct,4),
                "scenario_p50_pct":round(result.p50_pct,4),
                "scenario_p90_pct":round(result.p90_pct,4),
                "up_pattern_vote_pct":round(result.up_vote*100,1),
                "pattern_votes_calibrated":False,"neighbors":result.neighbors,
                "walk_forward":quality,
                "caveat":"Modelo experimental. La votación histórica no es probabilidad calibrada. No ejecuta órdenes."}
    except Exception as e: fail(e)

@app.get("/api/v1/history")
def history(symbol: str | None=None,limit: int=Query(100,ge=1,le=500)):
    try: return {"items":database.records(market.normalize_symbol(symbol) if symbol else None,limit)}
    except Exception as e: fail(e)

class Calculate(BaseModel):
    margin_usdt: float = Field(gt=0,le=1000000)
    leverage: float = Field(default=1,ge=1,le=20)
    entry: float = Field(gt=0)
    exit: float = Field(gt=0)
    side: str = Field(pattern="^(LONG|SHORT)$")
    taker_fee_pct: float = Field(default=.06,ge=0,le=1)
    slippage_pct: float = Field(default=.02,ge=0,le=2)

@app.post("/api/v1/calculate")
def calculate(x: Calculate):
    notional=x.margin_usdt*x.leverage
    change=(x.exit/x.entry-1) * (1 if x.side=="LONG" else -1)
    gross=notional*change
    fees=notional*(x.taker_fee_pct+x.slippage_pct)*2/100
    return {"notional_usdt":round(notional,4),"gross_pnl_usdt":round(gross,4),
            "estimated_cost_usdt":round(fees,4),"net_pnl_usdt":round(gross-fees,4),
            "estimated_return_on_margin_pct":round((gross-fees)/x.margin_usdt*100,3),
            "note":"Estimación sin funding, variación de comisiones ni liquidación; no orden real."}
