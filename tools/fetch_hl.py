"""Téléchargeur Hyperliquid (API publique `info`, sans clé, lecture seule) : historique du funding et bougies 1 heure d'une liste d'actifs.

Sorties dans data/hl/ (ignoré par git) : <ACTIF>_funding.csv (time_ms, funding_rate_par_heure, premium) et <ACTIF>_1h.csv (t_ms, open, high, low, close, volume).
Le « : » des actifs HIP-3 devient « _ » dans les noms de fichiers (xyz:AAPL -> xyz_AAPL). Limites (doc, lue le 2026-10-08) : poids agrégé de 1 200 par minute et par IP,
`fundingHistory` et `candleSnapshot` pèsent 20 chacun ; ici une requête toutes les 2,5 s au plus (480 de poids par minute). `candleSnapshot` ne renvoie que les 5 000 dernières bougies.
Erreurs réseau et 429 : attente croissante, jamais de plantage. Reprenable : un fichier complet n'est pas retéléchargé (--force pour refaire).
python tools/fetch_hl.py --coins BTC xyz:AAPL ... --start 2026-05-01   |   --from-pairs (tous les actifs de Polymarket appariés par nom à Hyperliquid)
stdlib uniquement.
"""
import argparse
import calendar
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.request

HL = "https://api.hyperliquid.xyz/info"
UA = "trading-bot-perp research (personal, read-only)"
MIN_INTERVAL = 2.5
OUT = os.path.join("data", "hl")
_last = [0.0]


def post(body, opener=urllib.request.urlopen, clock=time.time, sleep=time.sleep):
    for attempt in range(8):
        w = MIN_INTERVAL - (clock() - _last[0])
        if w > 0:
            sleep(w)
        _last[0] = clock()
        req = urllib.request.Request(HL, data=json.dumps(body).encode(), headers={"Content-Type": "application/json", "User-Agent": UA})
        try:
            with opener(req, timeout=30) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            sleep(30 * (attempt + 1) if e.code == 429 else 10 * (attempt + 1))
        except (urllib.error.URLError, TimeoutError, ConnectionError, ValueError):
            sleep(10 * (attempt + 1))
    raise RuntimeError("Hyperliquid injoignable après 8 essais")


def funding_history(coin, start_ms, end_ms, fetch=post):
    """Pages de 500 au plus, ordre croissant ; la page suivante démarre une milliseconde après le dernier point."""
    rows, t = [], start_ms
    while t < end_ms:
        page = fetch({"type": "fundingHistory", "coin": coin, "startTime": t})
        if not page:
            break
        rows += [(int(x["time"]), float(x["fundingRate"]), float(x["premium"])) for x in page]
        if len(page) < 500:
            break
        t = int(page[-1]["time"]) + 1
    seen, out = set(), []
    for r in rows:
        if r[0] not in seen:
            seen.add(r[0])
            out.append(r)
    return sorted(out)


def candles(coin, start_ms, end_ms, fetch=post):
    c = fetch({"type": "candleSnapshot", "req": {"coin": coin, "interval": "1h", "startTime": start_ms, "endTime": end_ms}})
    return [(int(x["t"]), float(x["o"]), float(x["h"]), float(x["l"]), float(x["c"]), float(x["v"])) for x in c]


def fname(coin):
    return coin.replace(":", "_")


def save(coin, out=OUT, start_ms=0, end_ms=None, fetch=post, force=False):
    os.makedirs(out, exist_ok=True)
    end_ms = end_ms or int(time.time() * 1000)
    pf, pc = os.path.join(out, fname(coin) + "_funding.csv"), os.path.join(out, fname(coin) + "_1h.csv")
    if force or not os.path.exists(pf):
        fr = funding_history(coin, start_ms, end_ms, fetch)
        with open(pf, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["time_ms", "funding_rate_per_hour", "premium"])
            w.writerows(fr)
    if force or not os.path.exists(pc):
        cs = candles(coin, start_ms, end_ms, fetch)
        with open(pc, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["t_ms", "open", "high", "low", "close", "volume"])
            w.writerows(cs)
    return pf, pc


def paired_coins(data="data"):
    """Actifs de Polymarket appariés par NOM d'actif (base_asset) à Hyperliquid : dex principal, puis dex xyz."""
    ins = post({"type": "meta"})["universe"]
    main = {u["name"] for u in ins}
    xyz = {u["name"].split(":", 1)[-1]: u["name"] for u in post({"type": "meta", "dex": "xyz"})["universe"]}
    req = urllib.request.Request("https://api.perpetuals.polymarket.com/v1/info/instruments", headers={"accept": "application/json", "user-agent": UA})
    poly = json.loads(urllib.request.urlopen(req, timeout=30).read().decode())
    out = []
    for i in poly:
        b = i["base_asset"]
        if b in main:
            out.append((i["symbol"], b))
        elif b in xyz:
            out.append((i["symbol"], xyz[b]))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--coins", nargs="+")
    ap.add_argument("--from-pairs", action="store_true")
    ap.add_argument("--start", default="2026-05-01")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    y, m, d = (int(x) for x in a.start.split("-"))
    start = calendar.timegm((y, m, d, 0, 0, 0)) * 1000
    coins = list(a.coins or [])
    if a.from_pairs:
        pairs = paired_coins()
        os.makedirs(OUT, exist_ok=True)
        json.dump(pairs, open(os.path.join(OUT, "pairs.json"), "w"), indent=1)
        coins += [c for _s, c in pairs]
    for c in coins:
        pf, pc = save(c, OUT, start, force=a.force)
        print(c, "ok", flush=True)


if __name__ == "__main__":
    main()
