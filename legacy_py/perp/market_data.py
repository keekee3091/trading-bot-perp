"""
Donnees publiques Polymarket Perps (REST). Verifie contre la doc le 2026-10-05 :
  GET /v1/info/instruments, /tickers, /book, /klines, /funding  (base https://api.perpetuals.polymarket.com)
Attention : les instrument_id ne sont PAS stables entre doc et prod (id 1 = SP500-USD en prod),
toujours resoudre par symbole. Le format exact du carnet (/book) n'a pas ete verifie : parser tolerant.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import List, Optional

from .models import Instrument, Tick

BASE = "https://api.perpetuals.polymarket.com"


def _get(path: str, params: dict | None = None, timeout: float = 10.0):
    url = BASE + path + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, headers={"accept": "application/json", "user-agent": "trading-bot-perp"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def fetch_instruments() -> List[dict]:
    d = _get("/v1/info/instruments")
    return d if isinstance(d, list) else d.get("data", d)


def resolve_instrument(symbol: str) -> Instrument:
    for d in fetch_instruments():
        if d.get("symbol") == symbol:
            return Instrument.from_api(d)
    raise ValueError(f"instrument introuvable : {symbol}")


def fetch_klines(iid: int, interval: str = "1m", start_ms: int = 0, end_ms: Optional[int] = None,
                 max_pages: int = 200):
    """Pagine /klines. Chaque bougie : [ts_ms, o, h, l, c, volume, trades] (prix en chaines)."""
    out, cursor, pages = [], start_ms, 0
    while pages < max_pages:
        p = {"instrument_id": iid, "interval": interval, "start_timestamp": cursor}
        if end_ms:
            p["end_timestamp"] = end_ms
        d = _get("/v1/info/klines", p)
        rows = d.get("data", d) if isinstance(d, dict) else d
        if not rows:
            break
        out.extend(rows)
        more = d.get("more", False) if isinstance(d, dict) else False
        last = int(rows[-1][0])
        if not more or last <= cursor:
            break
        cursor = last + 1
        pages += 1
    return [(r[0] / 1000.0, float(r[1]), float(r[2]), float(r[3]), float(r[4])) for r in out]


def _best(levels, bid: bool) -> float:
    if not levels:
        return 0.0
    vals = []
    for lv in levels:
        p = lv[0] if isinstance(lv, (list, tuple)) else lv.get("p", lv.get("price"))
        vals.append(float(p))
    return max(vals) if bid else min(vals)


def fetch_tick(iid: int, with_book: bool = True) -> Tick:
    import time
    d = _get("/v1/info/tickers", {"instrument_id": iid})
    row = d[0] if isinstance(d, list) else d.get("data", d)
    row = row[0] if isinstance(row, list) else row
    bid = ask = 0.0
    if with_book:
        try:
            b = _get("/v1/info/book", {"instrument_id": iid, "depth": 10})
            bid, ask = _best(b.get("bids"), True), _best(b.get("asks"), False)
        except Exception:
            pass
    return Tick(
        ts=time.time(), mark=float(row["mark_price"]), index=float(row["index_price"]),
        bid=bid, ask=ask, funding_rate=float(row.get("funding_rate") or 0.0),
    )


def fetch_binance_ref(symbol: str) -> float:
    url = "https://api.binance.com/api/v3/ticker/price?symbol=" + symbol
    with urllib.request.urlopen(url, timeout=5) as r:
        return float(json.loads(r.read().decode())["price"])
