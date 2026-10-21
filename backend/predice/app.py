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
from . import store, market, bitunix
from .model import HORIZONS, forecast

log=logging.getLogger('predice')
status={}

def source_key(symbol, source):
    if source=='binance': return symbol
    if source=='bitunix': return bitunix.key(symbol)
    raise HTTPException(422,'Unknown market source')

def source_market(source):
    source_key('BTCUSDT',source)
    return market if source=='binance' else bitunix

async def alert_worker():
    while True:
        try:
            with store.connect() as db:
                symbols=[r[0] for r in db.execute('SELECT DISTINCT symbol FROM alerts WHERE fired IS NULL')]
            for symbol in symbols:
                if symbol.startswith('BITUNIX:'):
                    price=await bitunix.last_price(symbol.split(':',1)[1])
                else:
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
        for key in symbols:
            try:
                provider=bitunix if key.startswith('BITUNIX:') else market
                symbol=key.split(':',1)[-1]
                rows=await provider.ingest(symbol)
                if not rows or time.time()*1000-(rows[-1]['t']+300000)>120000:
                    raise ValueError('Stale candles')
                store.settle(key)
                for horizon,steps in HORIZONS.items():
                    with store.connect() as db:
                        exists=db.execute('SELECT 1 FROM predictions WHERE symbol=? AND horizon=? AND origin=?',
                                          (key,horizon,rows[-1]['t'])).fetchone()
                    if exists: continue
                    result=await asyncio.to_thread(forecast,[r['close'] for r in rows],
                                                   [r['volume'] for r in rows],horizon)
                    result['source']='Bitunix futures LAST_PRICE' if provider is bitunix else 'Binance spot'
                    store.save_prediction(key,rows[-1]['t'],horizon,result,steps)
                status[key]='ready'
            except Exception as exc:
                status[key]=type(exc).__name__+': '+str(exc)[:180]
                log.warning('Ingest/model unavailable for %s: %s',key,type(exc).__name__)
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
async def assets(q: str='',source: str='binance'):
    try:
        provider=source_market(source)
        if provider is market: return await market.search(q)
        return await bitunix.search(q)
    except httpx.HTTPError: raise HTTPException(503,'Market catalog unavailable')

@app.get('/watchlist',dependencies=[Depends(auth)])
def watchlist(source: str='binance'):
    source_market(source)
    with store.connect() as db:
        rows=[r[0] for r in db.execute('SELECT symbol FROM watch')]
    return [r.split(':',1)[-1] for r in rows if r.startswith('BITUNIX:') == (source=='bitunix')]

@app.put('/watchlist/{symbol}',dependencies=[Depends(auth)])
async def add(symbol: str,source: str='binance'):
    provider=source_market(source)
    if symbol not in {a['symbol'] for a in await provider.assets()}: raise HTTPException(404,'Unknown symbol')
    key=source_key(symbol,source)
    with store.connect() as db:
        if db.execute('SELECT count(*) FROM watch').fetchone()[0]>=20: raise HTTPException(409,'Limit: 20 assets')
        db.execute('INSERT OR IGNORE INTO watch VALUES(?)',(key,))
    return {'symbol':symbol,'source':source,'state':'collecting'}

@app.delete('/watchlist/{symbol}',dependencies=[Depends(auth)])
def remove(symbol: str,source: str='binance'):
    with store.connect() as db: db.execute('DELETE FROM watch WHERE symbol=?',(source_key(symbol,source),))
    return {'removed':symbol}

@app.get('/candles/{symbol}',dependencies=[Depends(auth)])
def candles(symbol: str,source: str='binance'): return store.candles(source_key(symbol,source))[-288:]

@app.get('/predictions/{symbol}',dependencies=[Depends(auth)])
def predictions(symbol: str,source: str='binance'):
    key=source_key(symbol,source)
    with store.connect() as db:
        rows=db.execute('SELECT * FROM predictions WHERE symbol=? AND id IN (SELECT MAX(id) FROM predictions WHERE symbol=? GROUP BY horizon)',(key,key)).fetchall()
    results=[]
    for r in rows:
        item=json.loads(r['payload'])
        now=time.time()*1000
        stale=now-(r['origin']+300000)>420000 or now>=r['target']+300000
        item.update(origin=r['origin'],target=r['target'],issued_at=r['issued_at'],stale=stale)
        if stale: item.update(signal='WAIT',entry=None,stop=None,take_profit=None,reason='Stale prediction')
        results.append(item)
    return {'state':status.get(key,'collecting'),'items':results}

@app.get('/history/{symbol}',dependencies=[Depends(auth)])
def history(symbol: str,source: str='binance'):
    with store.connect() as db:
        return [dict(r) for r in db.execute('SELECT * FROM predictions WHERE symbol=? ORDER BY id DESC LIMIT 100',(source_key(symbol,source),))]

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
    source: Literal['binance','bitunix']='binance'
    threshold: float=Field(gt=0,allow_inf_nan=False)
    above: bool=True

@app.post('/alerts',dependencies=[Depends(auth)])
async def alert(a: Alert):
    if a.symbol not in {s['symbol'] for s in await source_market(a.source).assets()}: raise HTTPException(404,'Unknown symbol')
    with store.connect() as db:
        if db.execute('SELECT count(*) FROM alerts WHERE fired IS NULL').fetchone()[0]>=100: raise HTTPException(409,'Alert limit')
        cur=db.execute('INSERT INTO alerts(symbol,threshold,above) VALUES(?,?,?)',(source_key(a.symbol,a.source),a.threshold,a.above))
        return {'id':cur.lastrowid}

@app.get('/alerts',dependencies=[Depends(auth)])
def alerts(source: str='binance'):
    source_market(source)
    with store.connect() as db:
        rows=[dict(r) for r in db.execute('SELECT * FROM alerts ORDER BY id DESC LIMIT 100')]
    return [dict(r,symbol=r['symbol'].split(':',1)[-1]) for r in rows
            if r['symbol'].startswith('BITUNIX:') == (source=='bitunix')]

@app.websocket('/ws/{symbol}')
async def prices(ws: WebSocket,symbol: str,source: str='binance'):
    token=os.getenv('PREDICE_TOKEN','')
    if not token or not secrets.compare_digest(ws.headers.get('authorization',''),'Bearer '+token):
        await ws.close(code=1008); return
    try: provider=source_market(source)
    except HTTPException:
        await ws.close(code=1008); return
    if symbol not in {a['symbol'] for a in await provider.assets()}:
        await ws.close(code=1008); return
    await ws.accept()
    import websockets
    try:
        url=(f'wss://data-stream.binance.vision/ws/{symbol.lower()}@trade' if source=='binance'
             else 'wss://fapi.bitunix.com/public/')
        async with websockets.connect(url) as upstream:
            if source=='bitunix':
                await upstream.send(json.dumps({'op':'subscribe','args':[{'symbol':symbol,'ch':'ticker'}]}))
            async for raw in upstream:
                event=json.loads(raw)
                if source=='bitunix':
                    if event.get('ch')!='ticker' or event.get('symbol')!=symbol: continue
                    price=float(event['data']['la']); timestamp=int(event['ts'])
                else:
                    price=float(event['p']); timestamp=int(event['T'])
                with store.connect() as db:
                    db.execute('UPDATE alerts SET fired=? WHERE symbol=? AND fired IS NULL AND ((above=1 AND threshold<=?) OR (above=0 AND threshold>=?))',
                               (timestamp,source_key(symbol,source),price,price))
                await ws.send_json(dict(symbol=symbol,price=price,timestamp=timestamp,
                                        source='Bitunix futures' if source=='bitunix' else 'Binance spot'))
    except (WebSocketDisconnect,Exception):
        with contextlib.suppress(Exception): await ws.close(code=1011)
