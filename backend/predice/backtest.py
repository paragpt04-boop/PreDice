"""Rolling chronological backtest. Run: python -m predice.backtest BTCUSDT."""
import argparse
import asyncio
import json
from pathlib import Path
from . import store, market
from .model import forecast, HORIZONS

def walk_forward(rows, window=6000, step=1500):
    if step < window//4: raise ValueError('Test windows must not overlap')
    if len(rows)<window: raise ValueError('Insufficient data')
    folds=[]
    for end in range(window,len(rows)+1,step):
        sample=rows[end-window:end]
        results={h:forecast([r['close'] for r in sample],[r['volume'] for r in sample],h) for h in HORIZONS}
        folds.append(dict(start=sample[0]['t'],end=sample[-1]['t'],results=results))
    return dict(protocol='rolling-purged-55-20-25',window=window,step=step,
                execution_backtest=False,source='Binance spot closed 5m candles',folds=folds)

async def main():
    parser=argparse.ArgumentParser(); parser.add_argument('symbol'); parser.add_argument('--output',default='backtest.json')
    args=parser.parse_args(); store.init()
    if args.symbol not in {x['symbol'] for x in await market.assets()}: raise ValueError('Unknown symbol')
    rows=await market.ingest(args.symbol)
    report=await asyncio.to_thread(walk_forward,rows)
    Path(args.output).write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(f"Saved {len(report['folds'])} real-data folds to {args.output}")

if __name__=='__main__': asyncio.run(main())
