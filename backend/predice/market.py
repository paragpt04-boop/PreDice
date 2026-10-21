import asyncio
import time
from urllib.parse import urlparse
import httpx
from . import store

BASE = "https://data-api.binance.vision"
NAMES = {"BTC":"Bitcoin", "ETH":"Ethereum", "SOL":"Solana", "BNB":"BNB",
         "XRP":"XRP", "DOGE":"Dogecoin", "ADA":"Cardano", "AVAX":"Avalanche"}
catalog = []

async def get(path, **params):
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(BASE+path, params=params)
        response.raise_for_status()
        return response.json()

async def assets():
    global catalog
    if not catalog:
        data = await get('/api/v3/exchangeInfo')
        catalog = [dict(symbol=s['symbol'], name=NAMES.get(s['baseAsset'],s['baseAsset']),
                        base=s['baseAsset']) for s in data['symbols']
                   if s['status']=='TRADING' and s['quoteAsset']=='USDT']
    return catalog

async def search(query):
    query=query.strip()
    if '://' in query:
        parsed=urlparse(query)
        # Parse only, never fetch a user-controlled URL (SSRF).
        if parsed.hostname not in ('www.binance.com','binance.com','www.coingecko.com','coingecko.com','coinmarketcap.com','www.coinmarketcap.com'):
            return []
        query=parsed.path.rstrip('/').split('/')[-1].replace('_','').replace('-','')
    q=query.lower()
    return [a for a in await assets() if q in a['symbol'].lower() or q in a['name'].lower()][:50]

async def ingest(symbol):
    rows=store.candles(symbol)
    now=int(time.time()*1000)
    start=rows[-1]['t']+300000 if rows else (now//300000-16000)*300000
    while start < now-300000:
        batch=await get('/api/v3/klines',symbol=symbol,interval='5m',startTime=start,limit=1000)
        closed=[r for r in batch if int(r[6])<now]
        if not closed: break
        with store.connect() as db:
            db.executemany("INSERT OR IGNORE INTO candles VALUES(?,?,?,?)",
                           [(symbol,int(r[0]),float(r[4]),float(r[5])) for r in closed])
        start=int(closed[-1][0])+300000
        await asyncio.sleep(.2)
    rows=store.candles(symbol)
    if any(b['t']-a['t'] != 300000 for a,b in zip(rows,rows[1:])):
        raise ValueError("Gaps in candle history: prediction disabled")
    return rows
