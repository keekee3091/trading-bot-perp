"""Inventaire de l'univers : catégorie, levier max, premier kline, jours d'historique, densité.

Un seul appel /v1/info/klines (start_timestamp=0) par instrument : donne le début réel de
l'historique (ui_live_time est la date d'affichage dans l'UI, pas le début des données) et la
densité de la première page (1000 minutes), indicative seulement.
Sortie : data/universe_survey.csv
"""
import csv
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(__file__))
from fetch_klines import get  # noqa: E402

now_ms = time.time() * 1000
rows = get("/v1/info/instruments")
out = []
for inst in rows:
    d = get("/v1/info/klines", {"instrument_id": inst["instrument_id"], "interval": "1m", "start_timestamp": 0})
    page = d["data"]
    first = int(page[0][0]) if page else None
    span_min = (int(page[-1][0]) - first) / 60000 + 1 if page else 0
    density = len(page) / span_min if span_min else 0
    out.append({
        "iid": inst["instrument_id"], "symbol": inst["symbol"], "category": inst["category"],
        "max_leverage": inst["max_leverage"], "close_only": inst["close_only"],
        "liq_fee": inst["liquidation_fee"], "min_notional": inst["min_notional"],
        "first_kline": time.strftime("%Y-%m-%d", time.gmtime(first / 1000)) if first else "",
        "days": round((now_ms - first) / 86400000, 1) if first else 0,
        "first_page_density": round(density, 3),
    })
    print(out[-1]["symbol"], out[-1]["category"], out[-1]["days"], out[-1]["first_page_density"], flush=True)
os.makedirs("data", exist_ok=True)
with open("data/universe_survey.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(out[0]))
    w.writeheader()
    w.writerows(out)
