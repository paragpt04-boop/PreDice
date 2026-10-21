import json
import os
import sqlite3
import time
from pathlib import Path

DB = os.getenv("PREDICE_DB", "data/predice.db")

def connect():
    Path(DB).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    return db

def init():
    with connect() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS candles(symbol TEXT, t INTEGER, close REAL, volume REAL,
          PRIMARY KEY(symbol,t));
        CREATE TABLE IF NOT EXISTS watch(symbol TEXT PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS predictions(id INTEGER PRIMARY KEY, symbol TEXT, horizon TEXT,
          origin INTEGER, target INTEGER, payload TEXT, outcome REAL, settled INTEGER,
          issued_at INTEGER,
          UNIQUE(symbol,horizon,origin));
        CREATE TABLE IF NOT EXISTS alerts(id INTEGER PRIMARY KEY, symbol TEXT, threshold REAL,
          above INTEGER, fired INTEGER);
        ''')
        if 'issued_at' not in {r[1] for r in db.execute('PRAGMA table_info(predictions)')}:
            db.execute('ALTER TABLE predictions ADD COLUMN issued_at INTEGER')
        for symbol in ("BTCUSDT","ETHUSDT","SOLUSDT"):
            db.execute("INSERT OR IGNORE INTO watch VALUES (?)", (symbol,))

def candles(symbol):
    with connect() as db:
        return [dict(x) for x in db.execute("SELECT * FROM candles WHERE symbol=? ORDER BY t", (symbol,))]

def save_prediction(symbol, origin, horizon, payload, steps):
    with connect() as db:
        db.execute("INSERT OR IGNORE INTO predictions(symbol,horizon,origin,target,payload,issued_at) VALUES(?,?,?,?,?,?)",
                   (symbol,horizon,origin,origin+steps*300000,json.dumps(payload),int(time.time()*1000)))

def settle(symbol):
    with connect() as db:
        pending = db.execute("SELECT * FROM predictions WHERE symbol=? AND outcome IS NULL",(symbol,)).fetchall()
        for row in pending:
            candle = db.execute("SELECT close FROM candles WHERE symbol=? AND t=?",(symbol,row['target'])).fetchone()
            if candle:
                base = json.loads(row['payload'])['reference_price']
                db.execute("UPDATE predictions SET outcome=?,settled=? WHERE id=?",
                           ((candle['close']/base-1)*100,row['target'],row['id']))
