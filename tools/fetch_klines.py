"""Télécharge klines 1m, historique de funding et paramètres d'instrument de Polymarket Perps.

Sorties dans data/ (stdlib uniquement) :
  <SYMBOLE>_1m.csv          ts(ms),open,high,low,close,volume,trades  (minutes sans trade remplies, volume=0)
  <SYMBOLE>_funding.csv     ts(ms),rate                               (taux horaire, ordre croissant)
  <SYMBOLE>.instrument.yaml overlay instrument.* pour perp_backtest (--config config.yaml --config ...)
  history_summary.txt       jours d'historique et densité par instrument

Les instrument_id ne sont pas stables entre doc et prod : on résout toujours par symbole.
Les klines ne contiennent que les minutes avec au moins un trade (marché fin) : on remplit les
trous par une bougie plate au dernier close, sinon le temps saute et la vol est mal mesurée.
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

BASE = "https://api.perpetuals.polymarket.com"


def get(path: str, params: dict | None = None, retries: int = 4):
    url = BASE + path + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, headers={"accept": "application/json", "user-agent": "trading-bot-perp"})
    for k in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code < 500 and e.code != 429:
                raise
        except (urllib.error.URLError, TimeoutError):
            pass
        time.sleep(1.5 * (k + 1))
    raise RuntimeError("echec apres %d essais : %s" % (retries, url))


def resolve(symbol: str, instruments: list) -> dict:
    for d in instruments:
        if d.get("symbol") == symbol:
            return d
    raise SystemExit("instrument introuvable : %s" % symbol)


def fetch_klines(iid: int, interval: str = "1m") -> list:
    """Pages de 1000 en ordre croissant, `more` indique la suite."""
    rows, cursor = [], 0
    while True:
        d = get("/v1/info/klines", {"instrument_id": iid, "interval": interval, "start_timestamp": cursor})
        page = d["data"]
        if not page:
            break
        rows.extend(page)
        last = int(page[-1][0])
        if not d.get("more") or last < cursor:
            break
        cursor = last + 1
    return rows


def fetch_funding(iid: int) -> list:
    """Pages de 100 en ordre décroissant : start_timestamp=0 puis end_timestamp qui recule."""
    out, end = [], None
    while True:
        p = {"instrument_id": iid, "start_timestamp": 0}
        if end is not None:
            p["end_timestamp"] = end
        d = get("/v1/info/funding", p)
        page = d["data"]
        if not page:
            break
        out.extend(page)
        oldest = min(int(x["timestamp"]) for x in page)
        if not d.get("more") or (end is not None and oldest - 1 >= end):
            break
        end = oldest - 1
    seen, res = set(), []
    for x in sorted(out, key=lambda x: int(x["timestamp"])):
        t = int(x["timestamp"])
        if t not in seen:
            seen.add(t)
            res.append((t, float(x["funding_rate"])))
    return res


def fill_gaps(rows: list, step_ms: int = 60_000):
    """Retourne (lignes complètes, nb de minutes réelles). Minute vide = bougie plate au dernier close."""
    out, prev_close, n_real = [], None, 0
    by_ts = {int(r[0]): r for r in rows}
    t0, t1 = min(by_ts), max(by_ts)
    for ts in range(t0, t1 + 1, step_ms):
        r = by_ts.get(ts)
        if r:
            o, h, l, c = (float(r[i]) for i in (1, 2, 3, 4))
            out.append((ts, o, h, l, c, float(r[5]), int(r[6])))
            prev_close = c
            n_real += 1
        elif prev_close is not None:
            out.append((ts, prev_close, prev_close, prev_close, prev_close, 0.0, 0))
    return out, n_real


def overlay_yaml(inst: dict) -> str:
    tiers = inst.get("risk_tiers") or [{"lower_bound": "0", "max_leverage": inst.get("max_leverage", 10)}]
    t0 = tiers[0]
    lines = [
        "# Genere par tools/fetch_klines.py depuis /v1/info/instruments (%s)" % inst["symbol"],
        "# risk_tiers (notionnel de depart -> levier max) : " + ", ".join(
            "%s:%sx" % (t["lower_bound"], t["max_leverage"]) for t in tiers),
        "# Les tiers donnent un levier max par notionnel, pas un taux de maintenance : mmr reste",
        "# mmr_factor / levier max (hypothese) tant que le taux reel n'est pas documente.",
        "instrument:",
        "  max_leverage: %s" % t0["max_leverage"],
        "  min_notional: %s" % inst.get("min_notional", 10),
        "  liquidation_fee: %s" % inst.get("liquidation_fee", 0.005),
        "  qty_decimals: %s" % inst.get("quantity_decimals", 4),
    ]
    if len(tiers) > 1:
        lines.append("# Au-dela de %s de notionnel le levier max tombe a %sx : garder max_notional_per_trade en dessous."
                     % (tiers[1]["lower_bound"], tiers[1]["max_leverage"]))
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--symbols", nargs="+", default=["BTC-USD", "ETH-USD", "SOL-USD"])
    ap.add_argument("--interval", default="1m")
    ap.add_argument("--out", default="data")
    a = ap.parse_args()
    if a.interval != "1m":
        sys.exit("seul 1m est gere (le backtester suppose des bougies de 60 s)")
    os.makedirs(a.out, exist_ok=True)
    instruments = get("/v1/info/instruments")
    summary = []
    for sym in a.symbols:
        inst = resolve(sym, instruments)
        iid = int(inst["instrument_id"])
        raw = fetch_klines(iid, a.interval)
        rows, n_real = fill_gaps(raw)
        fund = fetch_funding(iid)
        with open(os.path.join(a.out, "%s_1m.csv" % sym), "w", newline="") as f:
            f.write("ts,open,high,low,close,volume,trades\n")
            for r in rows:
                f.write("%d,%s,%s,%s,%s,%s,%d\n" % r)
        with open(os.path.join(a.out, "%s_funding.csv" % sym), "w", newline="") as f:
            f.write("ts,rate\n")
            for t, r in fund:
                f.write("%d,%.10g\n" % (t, r))
        with open(os.path.join(a.out, "%s.instrument.yaml" % sym), "w") as f:
            f.write(overlay_yaml(inst))
        days = (rows[-1][0] - rows[0][0]) / 86_400_000
        fdays = (fund[-1][0] - fund[0][0]) / 86_400_000 if fund else 0
        iso = lambda ms: time.strftime("%Y-%m-%d", time.gmtime(ms / 1000))
        summary.append(
            "%-8s iid=%-3d klines %s -> %s = %.1f jours, %d minutes dont %d avec trades (%.1f %%), "
            "funding %d points / %.1f jours, levier max %s, frais liq %s"
            % (sym, iid, iso(rows[0][0]), iso(rows[-1][0]), days, len(rows), n_real,
               100.0 * n_real / len(rows), len(fund), fdays, inst.get("max_leverage"), inst.get("liquidation_fee")))
        print(summary[-1])
    with open(os.path.join(a.out, "history_summary.txt"), "w") as f:
        f.write("\n".join(summary) + "\n")


if __name__ == "__main__":
    main()
