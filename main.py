from fastapi import FastAPI
from pydantic import BaseModel
from datetime import datetime
import os, sqlite3

app = FastAPI(title="HA Paper Logger")
DB_PATH = "/app/data/paper.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.on_event("startup")
async def startup():
    os.makedirs("/app/data", exist_ok=True)
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS paper_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            strategy_id TEXT, variant TEXT, symbol TEXT, direction TEXT,
            entry_price REAL, exit_price REAL, stop_ticks INTEGER,
            target_ticks INTEGER, contracts INTEGER, pnl_ticks REAL,
            pnl_dollars REAL, exit_reason TEXT, entry_time TEXT,
            exit_time TEXT, htf_aligned INTEGER, confirmation_bars INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

class TradeEntry(BaseModel):
    strategy_id: str
    variant: str = "default"
    symbol: str
    direction: str
    entry_price: float
    stop_ticks: int
    target_ticks: int
    contracts: int
    confirmation_bars: int
    htf_aligned: bool
    entry_time: datetime

class TradeExit(BaseModel):
    trade_id: int
    exit_price: float
    pnl_ticks: float
    pnl_dollars: float
    exit_reason: str
    exit_time: datetime

@app.post("/api/paper-trade/entry")
async def log_entry(trade: TradeEntry):
    conn = get_db()
    cur = conn.execute("""
        INSERT INTO paper_trades (strategy_id, variant, symbol, direction, entry_price,
        stop_ticks, target_ticks, contracts, confirmation_bars, htf_aligned, entry_time)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
    """, (trade.strategy_id, trade.variant, trade.symbol, trade.direction,
    trade.entry_price, trade.stop_ticks, trade.target_ticks, trade.contracts,
    trade.confirmation_bars, trade.htf_aligned, trade.entry_time))
    conn.commit()
    tid = cur.lastrowid
    conn.close()
    return {"trade_id": tid, "status": "logged"}

@app.post("/api/paper-trade/exit")
async def log_exit(trade: TradeExit):
    conn = get_db()
    conn.execute("""
        UPDATE paper_trades SET exit_price=?, pnl_ticks=?, pnl_dollars=?,
        exit_reason=?, exit_time=? WHERE id=?
    """, (trade.exit_price, trade.pnl_ticks, trade.pnl_dollars,
    trade.exit_reason, trade.exit_time, trade.trade_id))
    conn.commit()
    conn.close()
    return {"status": "exit_logged"}

@app.get("/api/paper-trade/stats")
async def get_stats(days: int = 30):
    conn = get_db()
    summary = conn.execute("""
        SELECT COUNT(*) as total,
            SUM(CASE WHEN pnl_dollars > 0 THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN pnl_dollars < 0 THEN 1 ELSE 0 END) as losses,
            SUM(pnl_dollars) as total_pnl,
            AVG(pnl_dollars) as avg_trade,
            MAX(pnl_dollars) as best, MIN(pnl_dollars) as worst
        FROM paper_trades
        WHERE entry_time > datetime('now', '-{} days')
        AND exit_price IS NOT NULL
    """.format(days)).fetchone()
    variants = conn.execute("""
        SELECT variant, COUNT(*) as trades, SUM(pnl_dollars) as total_pnl,
            AVG(pnl_dollars) as avg_pnl,
            ROUND(SUM(CASE WHEN pnl_dollars > 0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) as win_rate
        FROM paper_trades
        WHERE entry_time > datetime('now', '-{} days') AND exit_price IS NOT NULL
        GROUP BY variant ORDER BY total_pnl DESC
    """.format(days)).fetchall()
    conn.close()
    return {"summary": dict(summary) if summary else {}, "variants": [dict(v) for v in variants]}

@app.get("/health")
async def health():
    return {"status": "ok"}
