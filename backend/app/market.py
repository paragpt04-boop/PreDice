"""Public-only Bitunix adapter: fixed hostname; never fetch arbitrary user URLs."""
from __future__ import annotations
import asyncio
import re
import time
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse
import httpx

BASE = "https://fapi.bitunix.com"
INTERVAL_MS = {"1m": 60000, "5m": 300000, "15m": 900000, "1h": 3600000}
HORIZONS = {"5m": ("1m", 5), "15m": ("1m", 15), "1h": ("5m", 12), "4h": ("15m", 16), "24h": ("1h", 24)}
POPULAR = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT", "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT", "TONUSDT"]
_SYMBOL = re.compile(r"^[A-Z0-9]{2,25}USDT$")

@dataclass(frozen=True)
class Candle:
    ts: int
    open: float
    high: float
    low: float
    close: float
    volume: float

def normalize_symbol(raw: str) -> str:
    """Accept name, symbol or trading URL; *parse only*, never call URL."""
    text = raw.strip()
    parsed = urlparse(text)
    if parsed.scheme or parsed.netloc:
        parts = [v for x in parse_qs(parsed.query).values() for v in x]
        parts += [x for x in parsed.path.split("/") if x]
        parts.append(parsed.fragment)
        text = next((x for x in reversed(parts) if "USDT" in x.upper()), "")
    text = text.upper().replace("/", "").replace("-", "").replace("_", "").replace(":", "")
    text = re.sub(r"[^A-Z0-9]", "", text)
    if not text.endswith("USDT"):
        text += "USDT"
    if not _SYMBOL.fullmatch(text):
        raise ValueError("Par de mercado no válido")
    return text

async def request(client: httpx.AsyncClient, path: str, params: dict | None = None):
    response = await client.get(BASE + path, params=params, timeout=12)
    response.raise_for_status()
    body = response.json()
    if body.get("code") not in (0, "0"):
        raise ValueError("Bitunix rechazó la consulta de mercado")
    return body.get("data")

async def trading_pairs(client: httpx.AsyncClient):
    data = await request(client, "/api/v1/futures/market/trading_pairs")
    return [x for x in data if x.get("symbolStatus") == "OPEN" and x.get("symbol")]

async def tickers(client: httpx.AsyncClient, symbols: list[str]):
    params = {"symbols": ",".join(symbols)} if symbols else None
    data = await request(client, "/api/v1/futures/market/tickers", params)
    return [{"symbol": t["symbol"], "price": float(t.get("lastPrice") or t.get("last")),
             "mark": float(t.get("markPrice") or 0), "change24h_pct":
             ((float(t.get("lastPrice") or t.get("last")) / float(t["open"]) - 1) * 100)
             if float(t.get("open") or 0) > 0 else None,
             "volume24h": float(t.get("quoteVol") or 0)} for t in data if t.get("lastPrice") or t.get("last")]

async def history(client: httpx.AsyncClient, symbol: str, interval: str, batches: int = 8):
    """Paginate backward and discard all unfinished candles."""
    step = INTERVAL_MS[interval]
    end = int(time.time() * 1000)
    points: dict[int, Candle] = {}
    for _ in range(batches):
        data = await request(client, "/api/v1/futures/market/kline",
                             {"symbol": symbol, "interval": interval, "endTime": end,
                              "limit": 200, "type": "LAST_PRICE"})
        if not data:
            break
        oldest = end
        for x in data:
            t = int(x["time"])
            if t < 10**11: t *= 1000
            oldest = min(oldest, t)
            if t + step > int(time.time() * 1000): continue
            try:
                c = Candle(t, float(x["open"]), float(x["high"]), float(x["low"]),
                           float(x["close"]), float(x.get("baseVol") or 0))
                if min(c.open, c.high, c.low, c.close) <= 0: continue
                points[t] = c
            except (TypeError, ValueError): continue
        if oldest >= end: break
        end = oldest - 1
        if len(data) < 200: break
        await asyncio.sleep(0.12)
    return sorted(points.values(), key=lambda c: c.ts)
