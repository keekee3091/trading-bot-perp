"""Journal SQLite des trades (WAL), meme esprit que data/recorder.py du bot Up/Down."""

import sqlite3
from pathlib import Path

from .models import ClosedTrade

_SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  symbol TEXT, side TEXT, entry_price REAL, exit_price REAL, qty REAL, leverage REAL,
  margin REAL, pnl REAL, pnl_pct REAL, fees REAL, funding REAL, reason TEXT,
  held_s REAL, opened_ts REAL, closed_ts REAL, mode TEXT
)"""


class Recorder:
    def __init__(self, path: str = "logs/perp_trades.db", mode: str = "paper"):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute(_SCHEMA)
        self.mode = mode

    def record(self, t: ClosedTrade) -> None:
        self.db.execute(
            "INSERT INTO trades (symbol,side,entry_price,exit_price,qty,leverage,margin,pnl,pnl_pct,fees,funding,reason,held_s,opened_ts,closed_ts,mode)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (t.symbol, t.side, t.entry_price, t.exit_price, t.qty, t.leverage, t.margin, t.pnl,
             t.pnl_pct, t.fees, t.funding, t.reason, t.held_s, t.opened_ts, t.closed_ts, self.mode),
        )
        self.db.commit()
