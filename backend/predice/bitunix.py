"""Public Bitunix USDT futures LAST_PRICE market data only."""
import asyncio
import time
from urllib.parse import urlparse
import httpx
from . import store

BASE = 'https://fapi.bitunix.com'
PAUSE = .12  # documented 10 requests/second/IP ceiling
catalog = []

def key(symbol):
    return 'BITUNIX:'+symbol

async def get(path, **params):
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(BASE+path, params=params)
        response.raise_for_status()
        payload = response.json()
    if payload.get('code') != 0:
        raise ValueError('Bitunix market API rejected request')
    return payload['data']

async def assets():
    global catalog
    if not catalog:
        pairs = await get('/api/v1/futures/market/trading_pairs')
        catalog = [dict(symbol=p['symbol'], name=p['base'], base=p['base'],
                        source='Bitunix futures') for p in pairs
                   if p.get('quote')=='USDT' and p.get('symbolStatus')=='OPEN']
    return catalog

async def search(query):
    query=query.strip()
    if '://' in query:
        parsed=urlparse(query)
        if parsed.hostname not in ('bitunix.com','www.bitunix.com'):
            return []
        query=parsed.path.rstrip('/').split('/')[-1].replace('_','').replace('-','')
    q=query.lower()
    return [a for a in await assets() if q in a['symbol'].lower() or q in a['name'].lower()][:50]

async def ingest(symbol):
    existing = store.candles(key(symbol))
    cutoff = existing[-1]['t'] if existing else 0
    cursor = int(time.time()*1000)
    now = cursor
    downloaded = 0
    while True:
        batch = await get('/api/v1/futures/market/kline',symbol=symbol,
                          interval='5m',type='LAST_PRICE',endTime=cursor,limit=200)
        normalized = sorted((int(r['time']),float(r['close']),float(r['baseVol']))
                            for r in batch if int(r['time'])+300000 <= now)
        new = [(key(symbol),t,c,v) for t,c,v in normalized if t > cutoff]
        if new:
            with store.connect() as db:
                db.executemany('INSERT OR IGNORE INTO candles VALUES(?,?,?,?)',new)
            downloaded += len(new)
        if not normalized or normalized[0][0] <= cutoff or len(batch)<200:
            break
        cursor = normalized[0][0]
        if not existing and downloaded>=16000:
            break
        await asyncio.sleep(PAUSE)
    rows = store.candles(key(symbol))
    if any(b['t']-a['t'] != 300000 for a,b in zip(rows,rows[1:])):
        raise ValueError('Gaps in Bitunix history: prediction disabled')
    return rows

async def last_price(symbol):
    data = await get('/api/v1/futures/market/tickers',symbols=symbol)
    for item in data:
        if item['symbol']==symbol:
            return float(item['lastPrice'])
    raise ValueError('Bitunix ticker unavailable')
