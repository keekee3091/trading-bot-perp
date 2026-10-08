"""Téléchargeur Tiingo (plan gratuit) : prix journaliers ajustés des actions listées par Polymarket Perps.

Limites du plan : 50 requêtes par heure, 1 000 par jour, 500 symboles par mois ; licence « Internal Use Only » : usage
personnel, aucune donnée brute dans docs/, results/ ni aucun fichier partagé (data/tiingo/ est ignoré par git).
La clé est lue dans .env (TIINGO_API_KEY) et n'est ni affichée, ni journalisée, ni mise dans une URL (en-tête Authorization).
Reprenable : l'état (horodatages des requêtes, symboles du mois, statut par ticker) est dans data/tiingo/_state.json.
Une requête par ticker (historique complet). Un 404 compte comme une requête.

python tools/fetch_tiingo.py --test AAPL          # un symbole, diagnostic des champs ajustés
python tools/fetch_tiingo.py --all                # tous les tickers de data/instruments_equity.json
stdlib uniquement.
"""
import argparse
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.request

OUT = os.path.join("data", "tiingo")
STATE = os.path.join(OUT, "_state.json")
PER_HOUR, PER_DAY, PER_MONTH_SYMBOLS = 48, 950, 450     # marges sous 50, 1000, 500
UA = "trading-bot-perp research (personal, internal use)"
FIELDS = ["date", "open", "high", "low", "close", "volume", "adjOpen", "adjHigh", "adjLow", "adjClose", "adjVolume",
          "divCash", "splitFactor"]


def load_key(path=".env"):
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.startswith("TIINGO_API_KEY="):
                return line.split("=", 1)[1].strip()
    return None


def load_state():
    if os.path.exists(STATE):
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    return {"requests": [], "months": {}, "tickers": {}}


def save_state(st):
    os.makedirs(OUT, exist_ok=True)
    tmp = STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f)
    os.replace(tmp, STATE)


def wait_slot(st, now=time.time, sleep=time.sleep):
    """Bloque jusqu'à ce qu'une requête soit permise (50 par heure glissante, 1 000 par 24 h)."""
    while True:
        t = now()
        st["requests"] = [x for x in st["requests"] if t - x < 86400]
        hour = sorted(x for x in st["requests"] if t - x < 3600)
        if len(st["requests"]) >= PER_DAY:
            sleep(min(600, 86400 - (t - min(st["requests"])) + 1))
        elif len(hour) >= PER_HOUR:
            sleep(min(600, 3600 - (t - hour[0]) + 1))
        else:
            return


def get(key, ticker, st):
    url = "https://api.tiingo.com/tiingo/daily/%s/prices?startDate=1900-01-01&format=json" % ticker.lower()
    for attempt in range(8):
        wait_slot(st)
        st["requests"].append(time.time())
        save_state(st)
        req = urllib.request.Request(url, headers={"Authorization": "Token " + key, "User-Agent": UA,
                                                   "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.status, json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return 404, None
            if e.code in (401, 403):
                sys.exit("Tiingo refuse la clé (HTTP %d)" % e.code)
            time.sleep(300 if e.code == 429 else 20 * (attempt + 1))
        except (urllib.error.URLError, TimeoutError, ValueError):
            time.sleep(20 * (attempt + 1))
    return 0, None


def fetch_one(key, ticker, st):
    month = time.strftime("%Y-%m")
    if ticker not in st["months"].setdefault(month, []) and len(st["months"][month]) >= PER_MONTH_SYMBOLS:
        sys.exit("limite mensuelle de symboles atteinte")
    code, rows = get(key, ticker, st)
    if ticker not in st["months"][month]:
        st["months"][month].append(ticker)
    if code == 404:
        st["tickers"][ticker] = {"status": "absent"}
    elif code == 200 and rows:
        os.makedirs(OUT, exist_ok=True)
        with open(os.path.join(OUT, ticker + ".csv"), "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(FIELDS)
            for r in rows:
                w.writerow([r["date"][:10]] + [r.get(k) for k in FIELDS[1:]])
        st["tickers"][ticker] = {"status": "ok", "rows": len(rows), "first": rows[0]["date"][:10],
                                 "last": rows[-1]["date"][:10]}
    else:
        st["tickers"][ticker] = {"status": "erreur", "code": code}
    save_state(st)
    return st["tickers"][ticker]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--tickers", nargs="+", help="tickers supplementaires (ETF de couverture), hors instruments Polymarket")
    a = ap.parse_args()
    key = load_key()
    if not key:
        sys.exit("TIINGO_API_KEY absente de .env")
    st = load_state()
    if a.test:
        print(a.test, fetch_one(key, a.test.upper(), st))
    for t in (a.tickers or []):
        if st["tickers"].get(t.upper(), {}).get("status") not in ("ok", "absent"):
            print(t.upper(), fetch_one(key, t.upper(), st), flush=True)
    if a.all:
        with open(os.path.join("data", "instruments_equity.json"), encoding="utf-8") as f:
            tickers = [i["base_asset"].upper() for i in json.load(f)]
        for t in tickers:
            if st["tickers"].get(t, {}).get("status") in ("ok", "absent"):
                continue
            print(t, fetch_one(key, t, st), flush=True)


if __name__ == "__main__":
    main()
