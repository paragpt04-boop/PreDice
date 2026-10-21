"""Append-only origin and later outcome; unique candle/horizon prevents inflated hit rates."""
from __future__ import annotations
import os
import sqlite3
from pathlib import Path
from .market import Candle

DB = os.getenv("PREDICE_DB", "predice.sqlite3")

def connect():
    Path(DB).parent.mkdir(parents=True,exist_ok=True)
    con=sqlite3.connect(DB,timeout=15)
    con.row_factory=sqlite3.Row
    con.execute("""CREATE TABLE IF NOT EXISTS forecasts (
      symbol TEXT NOT NULL, horizon TEXT NOT NULL, asof_ms INTEGER NOT NULL,
      target_ms INTEGER NOT NULL, base_price REAL NOT NULL,
      expected_pct REAL NOT NULL, vote_up REAL NOT NULL,
      p10_pct REAL NOT NULL, p90_pct REAL NOT NULL, signal TEXT NOT NULL,
      actual_pct REAL, resolved_ms INTEGER,
      PRIMARY KEY(symbol,horizon,asof_ms))""")
    return con

def remember(symbol,horizon,asof_ms,target_ms,base_price,pred,signal):
    with connect() as c:
        c.execute("""INSERT OR IGNORE INTO forecasts
            (symbol,horizon,asof_ms,target_ms,base_price,expected_pct,vote_up,p10_pct,p90_pct,signal)
            VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (symbol,horizon,asof_ms,target_ms,base_price,pred.expected_pct,pred.up_vote,
             pred.p10_pct,pred.p90_pct,signal))

def resolve(symbol: str, candles: list[Candle]):
    by_close_time = {x.ts: x.close for x in candles}
    with connect() as c:
        pending=c.execute("SELECT horizon,asof_ms,target_ms,base_price FROM forecasts WHERE symbol=? AND resolved_ms IS NULL",(symbol,)).fetchall()
        for row in pending:
            close=by_close_time.get(row["target_ms"])
            if close is not None:
                actual=(close/row["base_price"]-1)*100
                c.execute("""UPDATE forecasts SET actual_pct=?,resolved_ms=? WHERE symbol=? AND horizon=? AND asof_ms=?""",
                          (actual,row["target_ms"],symbol,row["horizon"],row["asof_ms"]))

def records(symbol: str | None = None, limit: int = 100):
    with connect() as c:
        sql="SELECT * FROM forecasts" + (" WHERE symbol=?" if symbol else "") + " ORDER BY asof_ms DESC LIMIT ?"
        return [dict(r) for r in c.execute(sql,(symbol,limit) if symbol else (limit,))]
