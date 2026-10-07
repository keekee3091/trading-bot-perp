"""Enregistreur de données de marché Polymarket Perps. Aucun ordre, aucune authentification, lecture seule.

But : calibrer le spread et le slippage réels par instrument, tester plus tard le déséquilibre du
carnet et un modèle de fill maker, et fournir un holdout vierge (rien ici n'a servi à ajuster une
stratégie). Échantillon par défaut : crypto, indices, matières premières, quelques actions.

Fichiers (JSON lines, un objet par ligne, rotation par jour UTC), sous data/live/<AAAA-MM-JJ>/ :
  tickers.jsonl   un enregistrement par instrument et par relevé (une requête /v1/info/tickers)
  books.jsonl     un enregistrement par instrument et par relevé de carnet (/v1/info/book, 10 niveaux)
  funding.jsonl   chaque taux de funding publié, dédoublonné (/v1/info/funding)
  errors.log      une ligne par erreur réseau ou de format : l'enregistreur ne plante jamais dessus
  instruments.json  instantané de /v1/info/instruments au démarrage de chaque jour

Champs communs : t (ms epoch, heure locale de réception), sym, iid, session (1 = marché sous-jacent
ouvert selon tools/sessions.py, 0 sinon), lat_ms (latence de la requête).
tickers : index, mark, last, mid, oi (open interest), funding (taux horaire courant), next_funding (ms),
  srv_ts (ms, horodatage serveur), basis_bps = (mark - index) / index x 1e4.
books : bids, asks (listes [prix, quantité] en nombres, du meilleur au pire, 10 niveaux), bid, ask, mid,
  spread_bps = (ask - bid) / mid x 1e4, depth_bid / depth_ask = notionnel (prix x quantité) cumulé dans
  [mid x (1 -/+ 5 bps)] et [mid x (1 -/+ 20 bps)] (clés "5" et "20"), slip_buy / slip_sell = coût de
  marché en bps par rapport au mid pour un ordre de 1000, 5000 et 20000 de notionnel (VWAP du
  parcours des 10 niveaux vs mid ; null si 10 niveaux ne suffisent pas), l'impact inclut donc le
  demi-spread.
funding : sym, iid, ts (ms, horodatage de la publication), rate (taux horaire).

Usage : python tools/recorder.py [--symbols A B ...] [--out data/live] [--tick-s 5] [--book-s 15]
        [--funding-s 600] [--duration SECONDES] ; arrêt propre par Ctrl+C.
Une erreur (réseau, DNS, TLS, JSON, HTTP) est journalisée, la boucle continue avec un délai croissant
(plafonné à 60 s). Rien ne contourne un blocage réseau : si l'API est injoignable, on attend.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sessions import in_session  # noqa: E402

BASE = "https://api.perpetuals.polymarket.com"
DEFAULT_SYMBOLS = ["BTC-USD", "ETH-USD", "SOL-USD", "SP500-USD", "NAS100-USD", "GOLD-USD", "SILVER-USD",
                   "WTIOIL-USD", "AAPL-USD", "MSFT-USD", "NVDA-USD", "TSLA-USD"]
NOTIONALS = (1000, 5000, 20000)


def http_get(path, params=None, timeout=15.0):
    url = BASE + path + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, headers={"accept": "application/json", "user-agent": "trading-bot-perp-recorder"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def levels(raw):
    return [(float(p), float(q)) for p, q in raw]


def depth_within(side, mid, bps, bid_side):
    """Notionnel cumulé des niveaux à moins de `bps` du mid, du bon côté."""
    lim = mid * (1 - bps / 1e4) if bid_side else mid * (1 + bps / 1e4)
    return sum(p * q for p, q in side if (p >= lim if bid_side else p <= lim))


def market_cost_bps(side, mid, notional, buy):
    """Coût en bps vs mid d'un ordre marché de `notional` : VWAP du parcours des niveaux ; None si
    la profondeur affichée ne suffit pas."""
    remaining, spent, qty = notional, 0.0, 0.0
    for p, q in side:
        take = min(remaining, p * q)
        spent += take
        qty += take / p
        remaining -= take
        if remaining <= 1e-9:
            break
    if remaining > 1e-9 or qty <= 0:
        return None
    vwap = spent / qty
    return ((vwap - mid) / mid if buy else (mid - vwap) / mid) * 1e4


def book_record(raw, sym, iid, t_ms, lat_ms, session):
    bids, asks = levels(raw["bids"]), levels(raw["asks"])
    if not bids or not asks:
        raise ValueError("carnet vide d'un côté")
    bid, ask = bids[0][0], asks[0][0]
    mid = (bid + ask) / 2
    return {
        "t": t_ms, "sym": sym, "iid": iid, "session": session, "lat_ms": lat_ms,
        "bids": [list(x) for x in bids], "asks": [list(x) for x in asks],
        "bid": bid, "ask": ask, "mid": mid, "spread_bps": (ask - bid) / mid * 1e4,
        "depth_bid": {str(b): depth_within(bids, mid, b, True) for b in (5, 20)},
        "depth_ask": {str(b): depth_within(asks, mid, b, False) for b in (5, 20)},
        "slip_buy": {str(n): market_cost_bps(asks, mid, n, True) for n in NOTIONALS},
        "slip_sell": {str(n): market_cost_bps(bids, mid, n, False) for n in NOTIONALS},
    }


def ticker_record(row, sym, iid, t_ms, lat_ms, session):
    index, mark = float(row["index_price"]), float(row["mark_price"])
    return {
        "t": t_ms, "sym": sym, "iid": iid, "session": session, "lat_ms": lat_ms,
        "index": index, "mark": mark, "last": float(row["last_price"]), "mid": float(row["mid_price"]),
        "oi": float(row["open_interest"]), "funding": float(row["funding_rate"] or 0.0),
        "next_funding": row.get("next_funding"), "srv_ts": row.get("timestamp"),
        "basis_bps": (mark - index) / index * 1e4 if index else None,
    }


class Recorder:
    def __init__(self, symbols, out_dir, fetch=http_get, clock=time.time, sleep=time.sleep):
        self.symbols, self.out_dir = list(symbols), out_dir
        self.fetch, self.clock, self.sleep = fetch, clock, sleep
        self.inst = {}          # symbole -> {iid, category}
        self.fail = 0           # échecs consécutifs, pour le délai croissant
        self.seen_funding = set()
        self.snapshot_day = None
        self.counts = {"tickers": 0, "books": 0, "funding": 0, "errors": 0}

    # ── fichiers ───────────────────────────────────────────────────────────
    def day_dir(self, t_s=None):
        d = os.path.join(self.out_dir, time.strftime("%Y-%m-%d", time.gmtime(t_s if t_s is not None else self.clock())))
        os.makedirs(d, exist_ok=True)
        return d

    def write(self, name, obj, t_s=None):
        with open(os.path.join(self.day_dir(t_s), name), "a", encoding="utf-8") as f:
            f.write(json.dumps(obj, separators=(",", ":")) + "\n")

    def log_error(self, where, exc):
        self.counts["errors"] += 1
        self.fail += 1
        try:
            with open(os.path.join(self.day_dir(), "errors.log"), "a", encoding="utf-8") as f:
                f.write("%s %s %s: %s\n" % (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.clock())), where,
                                            type(exc).__name__, str(exc)[:300].replace("\n", " ")))
        except OSError:
            pass  # même le journal d'erreurs ne doit pas faire planter l'enregistreur

    def backoff(self):
        if self.fail:
            self.sleep(min(60.0, 2.0 ** min(self.fail, 6)))

    # ── relevés ────────────────────────────────────────────────────────────
    def load_instruments(self):
        t0 = self.clock()
        rows = self.fetch("/v1/info/instruments")
        by = {r["symbol"]: r for r in rows}
        missing = [s for s in self.symbols if s not in by]
        if missing:
            raise ValueError("symboles inconnus : %s" % missing)
        self.inst = {s: {"iid": int(by[s]["instrument_id"]), "category": by[s]["category"]} for s in self.symbols}
        day = time.strftime("%Y-%m-%d", time.gmtime(t0))
        if day != self.snapshot_day:
            with open(os.path.join(self.day_dir(t0), "instruments.json"), "w", encoding="utf-8") as f:
                json.dump(rows, f)
            self.snapshot_day = day
        self.fail = 0

    def session_of(self, sym, t_s):
        return in_session(self.inst[sym]["category"], t_s)

    def poll_tickers(self):
        t0 = self.clock()
        rows = self.fetch("/v1/info/tickers")
        lat = int((self.clock() - t0) * 1000)
        by = {r["symbol"]: r for r in rows}
        for s in self.symbols:
            if s in by:
                self.write("tickers.jsonl", ticker_record(by[s], s, self.inst[s]["iid"], int(t0 * 1000), lat,
                                                           self.session_of(s, t0)), t0)
                self.counts["tickers"] += 1
        self.fail = 0

    def poll_book(self, sym):
        t0 = self.clock()
        raw = self.fetch("/v1/info/book", {"instrument_id": self.inst[sym]["iid"]})
        lat = int((self.clock() - t0) * 1000)
        raw = {"bids": raw["bids"][:10], "asks": raw["asks"][:10]}
        self.write("books.jsonl", book_record(raw, sym, self.inst[sym]["iid"], int(t0 * 1000), lat,
                                              self.session_of(sym, t0)), t0)
        self.counts["books"] += 1
        self.fail = 0

    def poll_funding(self, sym):
        d = self.fetch("/v1/info/funding", {"instrument_id": self.inst[sym]["iid"]})
        for x in d["data"]:
            key = (sym, int(x["timestamp"]))
            if key in self.seen_funding:
                continue
            self.seen_funding.add(key)
            self.write("funding.jsonl", {"sym": sym, "iid": self.inst[sym]["iid"], "ts": int(x["timestamp"]),
                                         "rate": float(x["funding_rate"])}, int(x["timestamp"]) / 1000.0)
            self.counts["funding"] += 1
        self.fail = 0

    def safe(self, where, fn, *a):
        """Exécute un relevé ; toute erreur est journalisée, jamais propagée."""
        try:
            fn(*a)
            return True
        except KeyboardInterrupt:
            raise
        except Exception as e:  # noqa: BLE001 : tolérance volontaire à toute erreur de relevé
            self.log_error(where, e)
            return False

    # ── boucle ─────────────────────────────────────────────────────────────
    def run(self, tick_s=5.0, book_s=15.0, funding_s=600.0, duration=None):
        start = self.clock()
        next_tick = next_funding = start
        next_book = {s: start + book_s * i / max(1, len(self.symbols)) for i, s in enumerate(self.symbols)}  # étalés
        try:
            while duration is None or self.clock() - start < duration:
                if not self.inst and not self.safe("instruments", self.load_instruments):
                    self.backoff()
                    continue
                now = self.clock()
                if now >= next_tick:
                    self.safe("tickers", self.poll_tickers)
                    next_tick = now + tick_s
                if now >= next_funding:
                    for s in self.symbols:
                        self.safe("funding:" + s, self.poll_funding, s)
                    next_funding = now + funding_s
                for s in self.symbols:
                    if self.clock() >= next_book[s]:
                        self.safe("book:" + s, self.poll_book, s)
                        next_book[s] = self.clock() + book_s
                self.backoff()
                self.sleep(0.5)
        except KeyboardInterrupt:
            pass
        return self.counts


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    ap.add_argument("--out", default="data/live")
    ap.add_argument("--tick-s", type=float, default=5.0)
    ap.add_argument("--book-s", type=float, default=15.0)
    ap.add_argument("--funding-s", type=float, default=600.0)
    ap.add_argument("--duration", type=float, default=None, help="secondes ; défaut : jusqu'à Ctrl+C")
    a = ap.parse_args()
    rec = Recorder(a.symbols, a.out)
    print("Enregistrement de %d instruments dans %s (Ctrl+C pour arrêter)" % (len(a.symbols), a.out), flush=True)
    counts = rec.run(a.tick_s, a.book_s, a.funding_s, a.duration)
    print("Terminé :", counts)


if __name__ == "__main__":
    main()
