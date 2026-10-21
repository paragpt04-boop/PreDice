import asyncio
import contextlib
import json
import logging
import os
import secrets
import time
import httpx
from contextlib import asynccontextmanager
from typing import Literal
from fastapi import FastAPI, Depends, Header, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from . import store, market
from .model import HORIZONS, forecast

log=logging.getLogger('predice')
status={}

async def alert_worker():
    while True:
        try:
            with store.connect() as db:
                symbols=[r[0] for r in db.execute('SELECT DISTINCT symbol FROM alerts WHERE fired IS NULL')]
            for symbol in symbols:
                ticker=await market.get('/api/v3/ticker/price',symbol=symbol)
                price=float(ticker['price'])
                with store.connect() as db:
                    db.execute('UPDATE alerts SET fired=? WHERE symbol=? AND fired IS NULL AND ((above=1 AND threshold<=?) OR (above=0 AND threshold>=?))',
                               (int(time.time()*1000),symbol,price,price))
        except Exception:
            log.warning('Alert polling unavailable')
        await asyncio.sleep(15)

async def worker():
    while True:
        with store.connect() as db:
            symbols=[r[0] for r in db.execute('SELECT symbol FROM watch')]
        for symbol in symbols:
            try:
                rows=await market.ingest(symbol)
                if not rows or time.time()*1000-(rows[-1]['t']+300000)>120000:
                    raise ValueError('Stale candles')
                store.settle(symbol)
                for horizon,steps in HORIZONS.items():
                    with store.connect() as db:
                        exists=db.execute('SELECT 1 FROM predictions WHERE symbol=? AND horizon=? AND origin=?',
                                          (symbol,horizon,rows[-1]['t'])).fetchone()
                    if exists: continue
                    result=await asyncio.to_thread(forecast,[r['close'] for r in rows],
                                                   [r['volume'] for r in rows],horizon)
                    store.save_prediction(symbol,rows[-1]['t'],horizon,result,steps)
                status[symbol]='ready'
            except Exception as exc:
                status[symbol]=type(exc).__name__+': '+str(exc)[:180]
                log.warning('Ingest/model unavailable for %s: %s',symbol,type(exc).__name__)
        await asyncio.sleep(30)

@asynccontextmanager
async def lifespan(app):
    store.init()
    task=asyncio.create_task(worker())
    alerts_task=asyncio.create_task(alert_worker())
    yield
    task.cancel()
    alerts_task.cancel()
    with contextlib.suppress(asyncio.CancelledError): await task
    with contextlib.suppress(asyncio.CancelledError): await alerts_task

def auth(authorization: str = Header(default='')):
    token=os.getenv('PREDICE_TOKEN','')
    if not token or not secrets.compare_digest(authorization,'Bearer '+token):
        raise HTTPException(401,'Configure a valid access token')

app=FastAPI(title='PreDice',version='0.1.0',lifespan=lifespan)

@app.get('/health')
def health(): return {'status':'ok','market':status}

@app.get('/assets',dependencies=[Depends(auth)])
async def assets(q: str=''):
    try: return await market.search(q)
    except httpx.HTTPError: raise HTTPException(503,'Market catalog unavailable')

@app.get('/watchlist',dependencies=[Depends(auth)])
def watchlist():
    with store.connect() as db: return [r[0] for r in db.execute('SELECT symbol FROM watch')]

@app.put('/watchlist/{symbol}',dependencies=[Depends(auth)])
async def add(symbol: str):
    if symbol not in {a['symbol'] for a in await market.assets()}: raise HTTPException(404,'Unknown symbol')
    with store.connect() as db:
        if db.execute('SELECT count(*) FROM watch').fetchone()[0]>=20: raise HTTPException(409,'Limit: 20 assets')
        db.execute('INSERT OR IGNORE INTO watch VALUES(?)',(symbol,))
    return {'symbol':symbol,'state':'collecting'}

@app.delete('/watchlist/{symbol}',dependencies=[Depends(auth)])
def remove(symbol: str):
    with store.connect() as db: db.execute('DELETE FROM watch WHERE symbol=?',(symbol,))
    return {'removed':symbol}

@app.get('/candles/{symbol}',dependencies=[Depends(auth)])
def candles(symbol: str): return store.candles(symbol)[-288:]

@app.get('/predictions/{symbol}',dependencies=[Depends(auth)])
def predictions(symbol: str):
    with store.connect() as db:
        rows=db.execute('SELECT * FROM predictions WHERE symbol=? AND id IN (SELECT MAX(id) FROM predictions WHERE symbol=? GROUP BY horizon)',(symbol,symbol)).fetchall()
    results=[]
    for r in rows:
        item=json.loads(r['payload'])
        stale=time.time()*1000-(r['origin']+300000)>420000
        item.update(origin=r['origin'],target=r['target'],stale=stale)
        if stale: item.update(signal='WAIT',entry=None,stop=None,take_profit=None,reason='Stale prediction')
        results.append(item)
    return {'state':status.get(symbol,'collecting'),'items':results}

@app.get('/history/{symbol}',dependencies=[Depends(auth)])
def history(symbol: str):
    with store.connect() as db:
        return [dict(r) for r in db.execute('SELECT * FROM predictions WHERE symbol=? ORDER BY id DESC LIMIT 100',(symbol,))]

class Calculation(BaseModel):
    side: Literal['LONG','SHORT']
    amount: float=Field(gt=0,le=1e9,allow_inf_nan=False)
    entry: float=Field(gt=0,allow_inf_nan=False)
    exit: float=Field(gt=0,allow_inf_nan=False)
    fee_bps: float=Field(default=10,ge=0,le=1000,allow_inf_nan=False)
    slippage_bps: float=Field(default=5,ge=0,le=1000,allow_inf_nan=False)
    stop: float|None=Field(default=None,gt=0,allow_inf_nan=False)

def calculate(c):
    sign=1 if c.side=='LONG' else -1
    if c.stop is not None and sign*(c.stop-c.entry)>=0: raise HTTPException(422,'Stop must be on loss side')
    units=c.amount/c.entry
    cost=(c.amount+units*c.exit)*(c.fee_bps+c.slippage_bps)/10000
    gross=sign*units*(c.exit-c.entry)
    risk=None if c.stop is None else units*abs(c.entry-c.stop)+(c.amount+units*c.stop)*(c.fee_bps+c.slippage_bps)/10000
    return dict(gross=gross,costs=cost,net=gross-cost,risk=risk,leveraged=False,
                note='Scenario only; excludes funding, borrow costs and liquidation')

@app.post('/calculate',dependencies=[Depends(auth)])
def calculator(c: Calculation): return calculate(c)

class Alert(BaseModel):
    symbol: str=Field(pattern=r'^[A-Z0-9]{2,24}$')
    threshold: float=Field(gt=0,allow_inf_nan=False)
    above: bool=True

@app.post('/alerts',dependencies=[Depends(auth)])
async def alert(a: Alert):
    if a.symbol not in {s['symbol'] for s in await market.assets()}: raise HTTPException(404,'Unknown symbol')
    with store.connect() as db:
        if db.execute('SELECT count(*) FROM alerts WHERE fired IS NULL').fetchone()[0]>=100: raise HTTPException(409,'Alert limit')
        cur=db.execute('INSERT INTO alerts(symbol,threshold,above) VALUES(?,?,?)',(a.symbol,a.threshold,a.above))
        return {'id':cur.lastrowid}

@app.get('/alerts',dependencies=[Depends(auth)])
def alerts():
    with store.connect() as db: return [dict(r) for r in db.execute('SELECT * FROM alerts ORDER BY id DESC LIMIT 100')]

@app.websocket('/ws/{symbol}')
async def prices(ws: WebSocket,symbol: str):
    token=os.getenv('PREDICE_TOKEN','')
    if not token or not secrets.compare_digest(ws.headers.get('authorization',''),'Bearer '+token):
        await ws.close(code=1008); return
    if symbol not in {a['symbol'] for a in await market.assets()}:
        await ws.close(code=1008); return
    await ws.accept()
    import websockets
    try:
        async with websockets.connect(f'wss://data-stream.binance.vision/ws/{symbol.lower()}@trade') as upstream:
            async for raw in upstream:
                event=json.loads(raw); price=float(event['p']); timestamp=int(event['T'])
                with store.connect() as db:
                    db.execute('UPDATE alerts SET fired=? WHERE symbol=? AND fired IS NULL AND ((above=1 AND threshold<=?) OR (above=0 AND threshold>=?))',
                               (timestamp,symbol,price,price))
                await ws.send_json(dict(symbol=symbol,price=price,timestamp=timestamp,source='Binance spot'))
    except (WebSocketDisconnect,Exception):
        with contextlib.suppress(Exception): await ws.close(code=1011)
