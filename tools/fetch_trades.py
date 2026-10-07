"""Télécharge l'historique de trades, le mark price et le funding de Polymarket Perps vers data/hist/.

  <SYM>_trades.csv    ts(ms),trade_id,side,price,qty,settlement   (trié par temps, dédoublonné)
  <SYM>_mark_<itv>.csv ts(ms),mark                                (prix de référence ; 0 = pas encore de mark)
  <SYM>_funding.csv   ts(ms),rate                                 (taux horaire publié)
  trades_summary.txt  profondeur réelle de l'historique par instrument + contrôle de complétude

Politesse : un limiteur de débit GLOBAL (--rate requêtes par seconde, défaut 4, tous threads confondus),
backoff exponentiel sur 429, 5xx et erreurs réseau (Retry-After respecté), arrêt propre sur Ctrl+C.
Reprenable : chaque instrument a un fichier d'état ; relancer la même commande continue où l'on s'était arrêté.

Pagination de /v1/info/trades : pages de 100 du plus récent au plus ancien ; `start_timestamp` et
`end_timestamp` bornent la fenêtre ; `limit` et `page_size` sont ignorés. `end_timestamp` est EXCLUSIF
(établi par essai : la page suivante ne contient pas les trades de la milliseconde frontière, or une page
coupe parfois au milieu d'une milliseconde) : on remonte donc avec end = plus_ancien + 1 et on
dédoublonne par trade_id.
Pagination de /v1/info/mark-history : `interval` obligatoire (1s, 1m, 5m, 15m, 30m, 1h, 4h, 6h, 12h, 1d, 1w),
pages de 1000 en ordre croissant, `more` indique la suite.

python tools/fetch_trades.py --symbols AAPL-USD NVDA-USD --start 2026-08-26 [--mark-interval 1m]
"""
from __future__ import annotations

import argparse
import calendar
import csv
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

BASE = "https://api.perpetuals.polymarket.com"

STOP = threading.Event()


class Limiter:
    """Débit global : au plus `rate` requêtes par seconde, tous threads confondus."""

    def __init__(self, rate):
        self.interval = 1.0 / rate
        self.lock = threading.Lock()
        self.next = 0.0

    def wait(self):
        with self.lock:
            now = time.monotonic()
            t = max(now, self.next)
            self.next = t + self.interval
        if t > now:
            time.sleep(t - now)


class ApiError(RuntimeError):
    pass


def api_get(limiter, path, params=None, retries=14):
    url = BASE + path + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, headers={"accept": "application/json", "user-agent": "trading-bot-perp-history"})
    last = None
    for k in range(retries):
        if STOP.is_set():
            raise KeyboardInterrupt
        limiter.wait()
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            last = "HTTP %d" % e.code
            if e.code == 429 or e.code >= 500:
                try:
                    delay = float(e.headers.get("Retry-After", "0"))
                except ValueError:
                    delay = 0.0
                time.sleep(max(delay, min(60.0, 2.0 ** (k + 1))))
                continue
            raise ApiError("%s : %s %s" % (url, last, e.read()[:200]))
        except (urllib.error.URLError, TimeoutError, ConnectionError, ValueError) as e:
            last = "%s: %s" % (type(e).__name__, e)
            time.sleep(min(60.0, 2.0 ** (k + 1)))
    raise ApiError("échec après %d essais (%s) : %s" % (retries, last, url))


def to_ms(ymd):
    y, m, d = (int(x) for x in ymd.split("-"))
    return calendar.timegm((y, m, d, 0, 0, 0)) * 1000


# ── trades ─────────────────────────────────────────────────────────────────

def trades_paths(out, sym):
    return (os.path.join(out, sym + "_trades_raw.csv"), os.path.join(out, sym + "_trades.state.json"),
            os.path.join(out, sym + "_trades.csv"))


def fetch_trades(limiter, sym, iid, start_ms, out, log):
    raw, state_p, final = trades_paths(out, sym)
    st = {"start_ms": start_ms, "end_ms": None, "next_end": None, "done": False, "pages": 0, "rows": 0,
          "dup_pages": 0, "skipped_ms": 0}
    if os.path.exists(state_p):
        with open(state_p) as f:
            st.update(json.load(f))
        if st["start_ms"] != start_ms:  # fenêtre changée : on recommence proprement
            st = {"start_ms": start_ms, "end_ms": None, "next_end": None, "done": False, "pages": 0, "rows": 0,
                  "dup_pages": 0, "skipped_ms": 0}
            if os.path.exists(raw):
                os.remove(raw)
    if st["done"]:
        return st
    if st["end_ms"] is None:
        st["end_ms"] = st["next_end"] = int(time.time() * 1000)
    boundary_ts = st.get("last_oldest")
    seen_at_boundary = set()
    if os.path.exists(raw) and boundary_ts is not None:  # ids déjà écrits à la frontière de reprise
        with open(raw) as f:
            for line in f:
                p = line.rstrip("\n").split(",")
                if len(p) >= 2 and p[0].isdigit() and int(p[0]) == boundary_ts:
                    seen_at_boundary.add(p[1])
    with open(raw, "a", newline="") as f:
        while not st["done"]:
            d = api_get(limiter, "/v1/info/trades",
                        {"instrument_id": iid, "start_timestamp": st["start_ms"], "end_timestamp": st["next_end"]})
            rows = d["data"]
            if not rows:
                st["done"] = True
                break
            new = [r for r in rows if not (int(r["timestamp"]) == boundary_ts and str(r["trade_id"]) in seen_at_boundary)]
            for r in new:
                f.write("%d,%s,%s,%s,%s,%d\n" % (int(r["timestamp"]), r["trade_id"], r["side"], r["price"], r["quantity"],
                                                 1 if r.get("settlement") else 0))
            f.flush()
            st["pages"] += 1
            st["rows"] += len(new)
            oldest = min(int(r["timestamp"]) for r in rows)
            if not d.get("more"):
                st["done"] = True
            elif not new:
                # page entièrement déjà vue : plus de 100 trades à la même milliseconde ; on saute cette ms
                st["dup_pages"] += 1
                st["skipped_ms"] += 1
                st["next_end"] = oldest
                boundary_ts, seen_at_boundary = None, set()
            else:
                st["next_end"] = oldest + 1
                boundary_ts = oldest
                seen_at_boundary = {str(r["trade_id"]) for r in rows if int(r["timestamp"]) == oldest}
            st["last_oldest"] = boundary_ts
            if oldest <= st["start_ms"]:
                st["done"] = True
            if st["pages"] % 20 == 0 or st["done"]:
                with open(state_p, "w") as sf:
                    json.dump(st, sf)
                log("%s trades : %d pages, %d trades, plus ancien %s" % (
                    sym, st["pages"], st["rows"], time.strftime("%Y-%m-%d %H:%M", time.gmtime(oldest / 1000))))
            if STOP.is_set():
                break
    with open(state_p, "w") as sf:
        json.dump(st, sf)
    return st


def finalize_trades(out, sym):
    """raw -> csv trié par temps, dédoublonné par trade_id. Ordre des égalités de ms : inverse de l'arrivée
    (les pages arrivent du plus récent au plus ancien)."""
    raw, _, final = trades_paths(out, sym)
    if not os.path.exists(raw):
        return 0
    rows, seen = [], set()
    with open(raw) as f:
        for i, line in enumerate(f):
            p = line.rstrip("\n").split(",")
            if len(p) < 6 or p[1] in seen:
                continue
            seen.add(p[1])
            rows.append((int(p[0]), -i, p))
    rows.sort(key=lambda x: (x[0], x[1]))
    with open(final, "w", newline="") as f:
        f.write("ts,trade_id,side,price,qty,settlement\n")
        for _, _, p in rows:
            f.write(",".join(p[:6]) + "\n")
    return len(rows)


# ── mark et funding ────────────────────────────────────────────────────────

def fetch_mark(limiter, sym, iid, start_ms, interval, out, log):
    path = os.path.join(out, "%s_mark_%s.csv" % (sym, interval))
    cursor, n = start_ms, 0
    if os.path.exists(path):
        with open(path) as f:
            last = None
            for last in f:
                pass
        if last and last[0].isdigit():
            cursor = int(last.split(",")[0]) + 1
    new_file = not os.path.exists(path)
    with open(path, "a", newline="") as f:
        if new_file:
            f.write("ts,mark\n")
        while True:
            d = api_get(limiter, "/v1/info/mark-history",
                        {"instrument_id": iid, "interval": interval, "start_timestamp": cursor})
            rows = d["data"]
            for ts, px in rows:
                f.write("%d,%s\n" % (ts, px))
            n += len(rows)
            f.flush()
            if not rows or not d.get("more"):
                break
            cursor = int(rows[-1][0]) + 1
    log("%s mark %s : +%d points" % (sym, interval, n))
    return n


def fetch_funding(limiter, sym, iid, out, log):
    pts, end = {}, None
    while True:
        p = {"instrument_id": iid, "start_timestamp": 0}
        if end is not None:
            p["end_timestamp"] = end
        d = api_get(limiter, "/v1/info/funding", p)
        page = d["data"]
        if not page:
            break
        for x in page:
            pts[int(x["timestamp"])] = float(x["funding_rate"])
        oldest = min(int(x["timestamp"]) for x in page)
        if not d.get("more") or (end is not None and oldest - 1 >= end):
            break
        end = oldest - 1
    with open(os.path.join(out, sym + "_funding.csv"), "w", newline="") as f:
        f.write("ts,rate\n")
        for t in sorted(pts):
            f.write("%d,%.10g\n" % (t, pts[t]))
    log("%s funding : %d points" % (sym, len(pts)))


# ── rapport ────────────────────────────────────────────────────────────────

def kline_trade_count(sym, a_ms, b_ms):
    """Somme du champ `trades` des klines 1m sur [a, b) : référence indépendante du nombre de trades."""
    p = os.path.join("data", sym + "_1m.csv")
    if not os.path.exists(p):
        return None, None
    n, first = 0, None
    with open(p) as f:
        for r in csv.DictReader(f):
            t = int(r["ts"])
            first = t if first is None else first
            if a_ms <= t < b_ms:
                n += int(r["trades"])
    return n, first


def summary_line(out, sym, start_ms):
    _, _, final = trades_paths(out, sym)
    if not os.path.exists(final):
        return "%-11s aucun fichier de trades" % sym
    n, vol_base, notional, sett, longs = 0, 0.0, 0.0, 0, 0
    t0 = t1 = None
    with open(final) as f:
        for r in csv.DictReader(f):
            t = int(r["ts"])
            t0 = t if t0 is None else t0
            t1 = t
            q, px = float(r["qty"]), float(r["price"])
            vol_base += q
            notional += q * px
            sett += int(r["settlement"])
            longs += 1 if r["side"] == "long" else 0
            n += 1
    iso = lambda ms: time.strftime("%Y-%m-%d", time.gmtime(ms / 1000))
    kn, kfirst = kline_trade_count(sym, t0, t1 + 60000) if n else (None, None)
    cover = "n/a" if not kn else "%.3f" % (n / kn)
    return ("%-11s %s -> %s  %.1f j | %8d trades (%.0f/j) | notionnel %.3e | volume base %.4g | long %.1f %% | settlement %d | "
            "trades / somme des klines (même période) = %s | 1er kline %s" % (
                sym, iso(t0), iso(t1), (t1 - t0) / 86400000, n, n / max(1e-9, (t1 - t0) / 86400000), notional, vol_base,
                100.0 * longs / max(1, n), sett, cover, iso(kfirst) if kfirst else "?"))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--symbols", nargs="+", required=True)
    ap.add_argument("--start", required=True, help="AAAA-MM-JJ UTC : début de la fenêtre de trades")
    ap.add_argument("--out", default="data/hist")
    ap.add_argument("--rate", type=float, default=4.0, help="requêtes par seconde, tous threads confondus")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--mark-interval", default="1m")
    ap.add_argument("--mark-start", default=None, help="début du mark (défaut : --start)")
    ap.add_argument("--no-mark", action="store_true")
    ap.add_argument("--no-trades", action="store_true")
    ap.add_argument("--no-funding", action="store_true")
    ap.add_argument("--instruments-only", action="store_true", help="n'écrit que instruments.csv")
    ap.add_argument("--report", action="store_true", help="n'écrit que le rapport depuis les fichiers existants")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    start_ms = to_ms(a.start)
    mark_ms = to_ms(a.mark_start) if a.mark_start else start_ms
    lock = threading.Lock()

    def log(msg):
        with lock:
            print(time.strftime("%H:%M:%S"), msg, flush=True)

    limiter = Limiter(a.rate)
    if not a.report:
        rows_inst = api_get(limiter, "/v1/info/instruments")
        inst = {r["symbol"]: int(r["instrument_id"]) for r in rows_inst}
        # paramètres d'instrument pour perp_mm (tick = 10^-price_decimals, levier max, frais de liquidation)
        with open(os.path.join(a.out, "instruments.csv"), "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["symbol", "category", "price_decimals", "max_leverage", "liquidation_fee", "min_notional",
                        "quantity_decimals"])
            for r in rows_inst:
                w.writerow([r["symbol"], r["category"], r["price_decimals"], r["max_leverage"], r["liquidation_fee"],
                            r["min_notional"], r["quantity_decimals"]])
        if a.instruments_only:
            print("instruments.csv écrit (%d instruments)" % len(rows_inst))
            return

        def work(sym):
            try:
                iid = inst[sym]
                if not a.no_trades:
                    fetch_trades(limiter, sym, iid, start_ms, a.out, log)
                    finalize_trades(a.out, sym)
                if not a.no_mark:
                    fetch_mark(limiter, sym, iid, mark_ms, a.mark_interval, a.out, log)
                if not a.no_funding:
                    fetch_funding(limiter, sym, iid, a.out, log)
                log("%s terminé" % sym)
            except KeyboardInterrupt:
                pass
            except Exception as e:  # noqa: BLE001
                log("%s ÉCHEC : %s (relancer pour reprendre)" % (sym, e))

        try:
            with ThreadPoolExecutor(max_workers=a.workers) as ex:
                list(ex.map(work, a.symbols))
        except KeyboardInterrupt:
            STOP.set()
            log("arrêt demandé : l'état est sauvegardé, relancer pour reprendre")
    lines = [summary_line(a.out, s, start_ms) for s in a.symbols]
    with open(os.path.join(a.out, "trades_summary.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
