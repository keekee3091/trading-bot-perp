"""Klines 1 s de Binance spot (données publiques, sans clé, gratuites) vers data/ext/<SYMBOLE>_1s.csv.

Sert de prix externe de référence pour la crypto (famille D, décalage avec un prix externe). Colonnes :
ts(ms, ouverture de la seconde),open,close,volume. Reprenable (relancer continue après le dernier ts écrit),
débit limité (--rate requêtes par seconde, défaut 4 : bien sous la limite publique de 1200 de poids par minute,
une requête de klines pesant 2), backoff sur 429 et erreurs réseau.

Sources externes pour les autres catégories : voir CLAUDE.md (aucune source gratuite et légale à 1 s sans clé
pour l'or, les indices et les actions : on se limite à la crypto).

python tools/fetch_binance.py --symbols BTCUSDT ETHUSDT --start 2026-09-14
"""
import argparse
import calendar
import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = "https://api.binance.com/api/v3/klines"


def get(url, retries=14):
    last = None
    for k in range(retries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"user-agent": "trading-bot-perp"}), timeout=30) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            last = "HTTP %d" % e.code
            if e.code in (418, 429) or e.code >= 500:
                try:
                    ra = float(e.headers.get("Retry-After", "0"))
                except ValueError:
                    ra = 0.0
                time.sleep(max(ra, min(60.0, 2.0 ** (k + 1))))
                continue
            raise
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last = repr(e)
            time.sleep(min(60.0, 2.0 ** (k + 1)))
    raise RuntimeError("échec après %d essais (%s) : %s" % (retries, last, url))


def fetch(symbol, start_ms, end_ms, out, rate):
    path = os.path.join(out, symbol + "_1s.csv")
    cursor, n = start_ms, 0
    if os.path.exists(path):
        with open(path) as f:
            last = None
            for last in f:
                pass
        if last and last[0].isdigit():
            cursor = int(last.split(",")[0]) + 1000
    new = not os.path.exists(path)
    with open(path, "a", newline="") as f:
        if new:
            f.write("ts,open,close,volume\n")
        while cursor < end_ms:
            t0 = time.time()
            rows = get("%s?symbol=%s&interval=1s&startTime=%d&endTime=%d&limit=1000" % (BASE, symbol, cursor, end_ms))
            if not rows:
                break
            for r in rows:
                f.write("%d,%s,%s,%s\n" % (r[0], r[1], r[4], r[5]))
            n += len(rows)
            f.flush()
            cursor = int(rows[-1][0]) + 1000
            if n % 100000 < 1000:
                print(time.strftime("%H:%M:%S"), symbol, n, time.strftime("%Y-%m-%d %H:%M", time.gmtime(cursor / 1000)), flush=True)
            time.sleep(max(0.0, 1.0 / rate - (time.time() - t0)))
    print(symbol, "terminé :", n, "lignes", flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--symbols", nargs="+", required=True)
    ap.add_argument("--start", required=True, help="AAAA-MM-JJ UTC")
    ap.add_argument("--end", default=None, help="AAAA-MM-JJ UTC (défaut : maintenant)")
    ap.add_argument("--out", default="data/ext")
    ap.add_argument("--rate", type=float, default=4.0)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    ms = lambda d: calendar.timegm(tuple(int(x) for x in d.split("-")) + (0, 0, 0)) * 1000
    end = ms(a.end) if a.end else int(time.time() * 1000)
    for s in a.symbols:
        fetch(s, ms(a.start), end, a.out, a.rate)


if __name__ == "__main__":
    main()
