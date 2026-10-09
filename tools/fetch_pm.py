"""Téléchargeur des marchés de prédiction Polymarket résolus (API publique Gamma et CLOB, sans clé, lecture seule) pour l'étude de calibration.

Marchés : fermés, binaires (Yes / No), résolus à 1 ou 0, volume total >= --min-volume, date de fin programmée connue, sans frais activés. Découpage par semaine de date de fin
(la pagination de Gamma est plafonnée à environ 2 000 entrées). Historique des prix du jeton Yes : `prices-history` du CLOB, 1 point par jour (interval=max, fidelity=1440).
Sorties dans data/pm/ (ignoré par git) : markets.jsonl (champs utiles) et history.jsonl (market id -> [[t, p], ...]). Reprenable. Débit : 4 requêtes par seconde au plus, attente
croissante sur 429 et erreurs réseau. Aucun accès aux comptes. L'éligibilité à NÉGOCIER ces marchés dépend du pays de l'utilisateur et n'est pas du ressort de ce script.
python tools/fetch_pm.py --from 2023-01-01 --to 2026-09-30 [--min-volume 100000] [--count-only]
stdlib uniquement.
"""
import argparse
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

GAMMA = "https://gamma-api.polymarket.com/markets"
CLOB = "https://clob.polymarket.com/prices-history"
UA = "trading-bot-perp research (personal, read-only)"
OUT = os.path.join("data", "pm")
MIN_INTERVAL = 0.25
_last = [0.0]


def get(url, opener=urllib.request.urlopen, clock=time.time, sleep=time.sleep):
    for attempt in range(8):
        w = MIN_INTERVAL - (clock() - _last[0])
        if w > 0:
            sleep(w)
        _last[0] = clock()
        try:
            with opener(urllib.request.Request(url, headers={"accept": "application/json", "user-agent": UA}), timeout=30) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 422:
                return None                      # au-delà du plafond de pagination
            sleep(30 * (attempt + 1) if e.code == 429 else 10 * (attempt + 1))
        except (urllib.error.URLError, TimeoutError, ConnectionError, ValueError):
            sleep(10 * (attempt + 1))
    raise RuntimeError("API injoignable après 8 essais : " + url[:80])


def keep(m, min_volume):
    """(garder ?, raison d'exclusion) selon les filtres pré-enregistrés."""
    try:
        outcomes = json.loads(m.get("outcomes") or "[]")
        prices = json.loads(m.get("outcomePrices") or "[]")
        tokens = json.loads(m.get("clobTokenIds") or "[]")
    except ValueError:
        return False, "champs illisibles"
    if not m.get("closed"):
        return False, "non fermé"
    if outcomes != ["Yes", "No"]:
        return False, "non binaire Yes/No"
    if m.get("umaResolutionStatus") != "resolved":
        return False, "non résolu"
    if [float(x) for x in prices] not in ([1.0, 0.0], [0.0, 1.0]):
        return False, "résolution ni 1 ni 0"
    if not m.get("endDate"):
        return False, "date de fin inconnue"
    if m.get("feesEnabled"):
        return False, "frais activés"
    if not tokens or len(tokens) != 2:
        return False, "jetons absents"
    if float(m.get("volumeNum") or 0) < min_volume:
        return False, "volume insuffisant"
    return True, ""


def compact(m):
    ev = (m.get("events") or [{}])[0]
    return {"id": m["id"], "question": m["question"], "yes_token": json.loads(m["clobTokenIds"])[0], "yes": float(json.loads(m["outcomePrices"])[0]),
            "volume": float(m["volumeNum"]), "start": m.get("startDate"), "end": m["endDate"], "closed": m.get("closedTime"), "event": ev.get("id"),
            "neg_risk": bool(m.get("negRisk"))}


def weeks(a, b):
    d = a
    while d <= b:
        yield d, min(d + dt.timedelta(days=6), b)
        d += dt.timedelta(days=7)


def list_markets(a, b, min_volume, sink=None, fetch=get):
    counts = {}
    for w0, w1 in weeks(a, b):
        for off in range(0, 2100, 100):
            q = urllib.parse.urlencode({"closed": "true", "limit": 100, "offset": off, "order": "volumeNum", "ascending": "false", "volume_num_min": int(min_volume),
                                        "end_date_min": w0.isoformat() + "T00:00:00Z", "end_date_max": w1.isoformat() + "T23:59:59Z"})
            page = fetch(GAMMA + "?" + q)
            if not page:
                break
            for m in page:
                ok, why = keep(m, min_volume)
                counts[why or "gardé"] = counts.get(why or "gardé", 0) + 1
                if ok and sink is not None:
                    sink(compact(m))
            if len(page) < 100:
                break
    return counts


def history(token, fetch=get):
    d = fetch(CLOB + "?" + urllib.parse.urlencode({"market": token, "interval": "max", "fidelity": 1440}))
    return [[int(x["t"]), float(x["p"])] for x in (d or {}).get("history", [])]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="a", default="2023-01-01")
    ap.add_argument("--to", dest="b", default="2026-09-30")
    ap.add_argument("--min-volume", type=float, default=100000)
    ap.add_argument("--count-only", action="store_true")
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    d0, d1 = dt.date.fromisoformat(a.a), dt.date.fromisoformat(a.b)
    mp = os.path.join(OUT, "markets.jsonl")
    hp = os.path.join(OUT, "history.jsonl")
    done_m = set()
    if os.path.exists(mp):
        with open(mp, encoding="utf-8") as f:
            done_m = {json.loads(x)["id"] for x in f}
    if a.count_only:
        print(list_markets(d0, d1, a.min_volume))
        return
    with open(mp, "a", encoding="utf-8") as f:
        def sink(c):
            if c["id"] not in done_m:
                done_m.add(c["id"])
                f.write(json.dumps(c) + "\n")
                f.flush()
        counts = list_markets(d0, d1, a.min_volume, sink)
    print("marchés :", counts, flush=True)
    done_h = set()
    if os.path.exists(hp):
        with open(hp, encoding="utf-8") as f:
            done_h = {json.loads(x)["id"] for x in f}
    with open(mp, encoding="utf-8") as f:
        markets = [json.loads(x) for x in f]
    n = 0
    with open(hp, "a", encoding="utf-8") as f:
        for m in markets:
            if m["id"] in done_h:
                continue
            f.write(json.dumps({"id": m["id"], "h": history(m["yes_token"])}) + "\n")
            f.flush()
            n += 1
            if n % 200 == 0:
                print("historiques :", n, "/", len(markets) - len(done_h), flush=True)
    print("terminé :", n, "historiques téléchargés")


if __name__ == "__main__":
    main()
