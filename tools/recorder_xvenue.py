"""Enregistreur inter-plateformes, lecture seule, sans clé : Polymarket Perps et Hyperliquid (dex principal et dex HIP-3 « xyz », trade.xyz).

PHASE 1 de la piste C : collecte uniquement, aucune analyse, aucune stratégie. Pour chaque paire d'instruments, à chaque cycle, les deux carnets sont
demandés EN PARALLÈLE (deux threads) et horodatés localement avant l'envoi et à la réception, avec l'horodatage serveur de chaque plateforme
(Polymarket : champ `timestamp` du carnet ; Hyperliquid : champ `time` de l'`l2Book`). 5 niveaux par côté. Toutes les minutes : contexte (Hyperliquid
`metaAndAssetCtxs` : mark, oracle, funding, intérêt ouvert, prime ; Polymarket `/v1/info/tickers` : index, mark, funding). Toutes les heures : mesure du
décalage d'horloge et de la latence. Les écarts inférieurs à la latence (quelques centaines de ms) ne sont PAS mesurables par ce sondage REST : dit ici.

Limites de débit : Hyperliquid, par IP, poids agrégé de 1 200 par minute ; `l2Book` pèse 2, `metaAndAssetCtxs` 20 (doc, lue le 2026-10-08).
Polymarket : limites non documentées (des 429 sont apparus vers 4 requêtes par seconde). Le débit prévu est calculé au démarrage et le programme refuse
de démarrer au-delà de 900 de poids Hyperliquid par minute ou de 3 requêtes par seconde pour Polymarket. 429 et erreurs réseau : attente croissante, jamais de plantage.

Appariement : les instruments sont appariés par le NOM DE L'ACTIF (`base_asset` de Polymarket contre le nom Hyperliquid, préfixe « xyz: » retiré), jamais
supposé ; deux appariements dont l'équivalence n'est pas établie (NAS100 contre XYZ100, WTIOIL contre CL) sont enregistrés avec `verified = false`.
Fichiers : data/xvenue/<AAAA-MM-JJ>/pairs.jsonl, ctx.jsonl, clock.jsonl, errors.log ; data/xvenue/pairs.json ; data/xvenue/health.json.
stdlib uniquement. python tools/recorder_xvenue.py [--pairs BTC ETH ...] [--period 6] [--duration SECONDES] | --health
"""
import argparse
import json
import os
import statistics
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

POLY = "https://api.perpetuals.polymarket.com"
HL = "https://api.hyperliquid.xyz/info"
UA = "trading-bot-perp-recorder (research, read-only)"
DEFAULT = ["BTC", "ETH", "SOL", "XRP", "HYPE", "SP500", "GOLD", "SILVER", "NAS100", "WTIOIL", "BRENTOIL", "AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "META", "GOOGL"]
UNVERIFIED = {"NAS100": "xyz:XYZ100", "WTIOIL": "xyz:CL"}      # équivalence non établie : à vérifier à la main avant toute analyse
LEVELS = 5
HL_WEIGHT_MAX = 900
POLY_RPS_MAX = 3.0


def poly_get(path, params=None, timeout=15.0):
    url = POLY + path + ("?" + urllib.parse.urlencode(params) if params else "")
    with urllib.request.urlopen(urllib.request.Request(url, headers={"accept": "application/json", "user-agent": UA}), timeout=timeout) as r:
        return json.loads(r.read().decode())


def hl_post(body, timeout=15.0):
    req = urllib.request.Request(HL, data=json.dumps(body).encode(), headers={"Content-Type": "application/json", "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def build_pairs(poly_instruments, hl_main, hl_xyz, wanted=DEFAULT):
    """Apparie par nom d'actif. poly_instruments : liste de dicts Polymarket ; hl_main / hl_xyz : noms Hyperliquid (xyz avec ou sans préfixe)."""
    xyz = {n.split(":", 1)[-1]: n for n in hl_xyz}
    main = set(hl_main)
    out = []
    for base in wanted:
        row = next((i for i in poly_instruments if i["base_asset"] == base), None)
        if row is None:
            continue
        if base in main:
            coin, verified = base, True
        elif base in xyz:
            coin, verified = xyz[base] if xyz[base].startswith("xyz:") else "xyz:" + base, True
        elif base in UNVERIFIED:
            coin, verified = UNVERIFIED[base], False
        else:
            continue
        out.append({"base": base, "poly_symbol": row["symbol"], "poly_id": row["instrument_id"], "hl_coin": coin, "verified": verified,
                    "category": row.get("category")})
    return out


def hl_weight_per_min(n_pairs, period_s, ctx_s=60.0, dexes=2):
    return n_pairs * 2 * 60.0 / period_s + dexes * 20 * 60.0 / ctx_s


def poly_rps(n_pairs, period_s, ctx_s=60.0):
    return n_pairs / period_s + 1.0 / ctx_s


def top(levels, n=LEVELS):
    """Niveaux Polymarket [prix, quantité] ou Hyperliquid {px, sz, n} -> [[prix, quantité], ...]."""
    return [[float(l["px"]), float(l["sz"])] if isinstance(l, dict) else [float(l[0]), float(l[1])] for l in levels[:n]]


class XRecorder:
    def __init__(self, pairs, out_dir, period=7.0, fetch_poly=poly_get, fetch_hl=hl_post, clock=time.time, sleep=time.sleep):
        w, r = hl_weight_per_min(len(pairs), period), poly_rps(len(pairs), period)
        if w > HL_WEIGHT_MAX or r > POLY_RPS_MAX:
            raise SystemExit("débit prévu trop élevé : poids Hyperliquid %.0f par minute (max %d), Polymarket %.2f requêtes par seconde (max %.1f)" % (w, HL_WEIGHT_MAX, r, POLY_RPS_MAX))
        self.pairs, self.out_dir, self.period = pairs, out_dir, period
        self.fetch_poly, self.fetch_hl, self.clock, self.sleep = fetch_poly, fetch_hl, clock, sleep
        self.fail = 0
        self.lock = threading.Lock()
        self.counts = {"pairs": 0, "ctx": 0, "clock": 0, "errors": 0}

    def day_dir(self, t=None):
        d = os.path.join(self.out_dir, time.strftime("%Y-%m-%d", time.gmtime(self.clock() if t is None else t)))
        os.makedirs(d, exist_ok=True)
        return d

    def write(self, name, obj):
        with self.lock, open(os.path.join(self.day_dir(), name), "a", encoding="utf-8") as f:
            f.write(json.dumps(obj, separators=(",", ":")) + "\n")

    def error(self, where, exc):
        self.counts["errors"] += 1
        self.fail += 1
        with self.lock, open(os.path.join(self.day_dir(), "errors.log"), "a", encoding="utf-8") as f:
            f.write("%s %s %s: %s\n" % (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.clock())), where, type(exc).__name__, str(exc)[:200]))
        if isinstance(exc, urllib.error.HTTPError) and exc.code == 429:
            self.sleep(min(60, 5 * self.fail))

    def timed(self, fn):
        t_send = self.clock() * 1000
        v = fn()
        return v, t_send, self.clock() * 1000

    def sample_pair(self, pr):
        try:
            with ThreadPoolExecutor(max_workers=2) as ex:
                fp = ex.submit(self.timed, lambda: self.fetch_poly("/v1/info/book", {"instrument_id": pr["poly_id"]}))
                fh = ex.submit(self.timed, lambda: self.fetch_hl({"type": "l2Book", "coin": pr["hl_coin"]}))
                bp, ps, pr_ = fp.result()
                bh, hs, hr = fh.result()
            self.write("pairs.jsonl", {
                "pair": pr["base"], "verified": pr["verified"],
                "poly": {"send": ps, "recv": pr_, "srv": bp.get("timestamp"), "seq": bp.get("sequence"), "bids": top(bp["bids"]), "asks": top(bp["asks"])},
                "hl": {"send": hs, "recv": hr, "srv": bh.get("time"), "bids": top(bh["levels"][0]), "asks": top(bh["levels"][1])}})
            self.counts["pairs"] += 1
            self.fail = 0
        except Exception as e:  # noqa: BLE001 : l'enregistreur ne plante jamais sur une erreur réseau ou de format
            self.error("pair " + pr["base"], e)

    def ctx(self):
        try:
            t0 = self.clock() * 1000
            rec = {"t": t0, "hl": {}, "poly": {}}
            for dex in ("", "xyz"):
                body = {"type": "metaAndAssetCtxs"} if not dex else {"type": "metaAndAssetCtxs", "dex": dex}
                meta, ctxs = self.fetch_hl(body)
                want = {p["hl_coin"] for p in self.pairs}
                for u, c in zip(meta["universe"], ctxs):
                    if u["name"] in want:
                        rec["hl"][u["name"]] = {k: c.get(k) for k in ("markPx", "oraclePx", "funding", "openInterest", "premium", "midPx")}
            for row in self.fetch_poly("/v1/info/tickers"):
                if row.get("symbol") in {p["poly_symbol"] for p in self.pairs}:
                    rec["poly"][row["symbol"]] = {k: row.get(k) for k in ("index_price", "mark_price", "funding_rate", "next_funding", "timestamp")}
            self.write("ctx.jsonl", rec)
            self.counts["ctx"] += 1
        except Exception as e:  # noqa: BLE001
            self.error("ctx", e)

    def clock_check(self, n=5):
        try:
            offs_hl, offs_p, rtt_hl, rtt_p = [], [], [], []
            for _ in range(n):
                b, s, r = self.timed(lambda: self.fetch_hl({"type": "l2Book", "coin": self.pairs[0]["hl_coin"]}))
                offs_hl.append(b["time"] - (s + r) / 2)
                rtt_hl.append(r - s)
                b, s, r = self.timed(lambda: self.fetch_poly("/v1/info/book", {"instrument_id": self.pairs[0]["poly_id"]}))
                offs_p.append(b["timestamp"] - (s + r) / 2)
                rtt_p.append(r - s)
                self.sleep(1.0)
            self.write("clock.jsonl", {"t": self.clock() * 1000, "hl_offset_ms": statistics.median(offs_hl), "hl_rtt_ms": statistics.median(rtt_hl),
                                       "poly_offset_ms": statistics.median(offs_p), "poly_rtt_ms": statistics.median(rtt_p)})
            self.counts["clock"] += 1
        except Exception as e:  # noqa: BLE001
            self.error("clock", e)

    def run(self, duration=None):
        t_end = None if duration is None else self.clock() + duration
        next_ctx = next_clock = 0.0
        with ThreadPoolExecutor(max_workers=6) as pool:
            while t_end is None or self.clock() < t_end:
                t0 = self.clock()
                if t0 >= next_clock:
                    self.clock_check()
                    next_clock = t0 + 3600
                if t0 >= next_ctx:
                    self.ctx()
                    next_ctx = t0 + 60
                list(pool.map(self.sample_pair, self.pairs))
                self.sleep(max(0.0, self.period - (self.clock() - t0)) + min(60.0, 2.0 * self.fail))


def health(out_dir, period=7.0, n_pairs=18):
    """Pour chaque jour UTC : échantillons par paire, couverture (échantillons / attendus), plus long trou ; jours continus ; décalage d'horloge maximal."""
    days = {}
    if not os.path.isdir(out_dir):
        return {"days": {}, "continuous_days": 0}
    for d in sorted(x for x in os.listdir(out_dir) if len(x) == 10 and x[4] == "-"):
        p = os.path.join(out_dir, d, "pairs.jsonl")
        if not os.path.exists(p):
            continue
        ts = {}
        with open(p, encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line)
                    ts.setdefault(r["pair"], []).append(r["poly"]["send"] / 1000.0)
                except (ValueError, KeyError):
                    continue
        exp = 86400.0 / period
        cov, gap = {}, {}
        for k, v in ts.items():
            v.sort()
            cov[k] = len(v) / exp
            gap[k] = max([b - a for a, b in zip(v, v[1:])] or [0.0])
        days[d] = {"pairs": len(ts), "coverage_min": min(cov.values()) if cov else 0.0, "coverage_median": statistics.median(cov.values()) if cov else 0.0,
                   "max_gap_s": max(gap.values()) if gap else 0.0, "n_samples": sum(len(v) for v in ts.values())}
    ok = [d for d, v in days.items() if v["pairs"] >= n_pairs - 1 and v["coverage_median"] >= 0.90 and v["max_gap_s"] <= 300]
    run = best = 0
    prev = None
    import datetime as dt
    for d in sorted(ok):
        cur = dt.date.fromisoformat(d)
        run = run + 1 if prev is not None and (cur - prev).days == 1 else 1
        best, prev = max(best, run), cur
    hl_o, po_o, n_err, n_smp = [], [], 0, 0
    for d in days:
        n_smp += days[d]["n_samples"]
        pe = os.path.join(out_dir, d, "errors.log")
        if os.path.exists(pe):
            with open(pe, encoding="utf-8") as f:
                n_err += sum(1 for _ in f)
        p = os.path.join(out_dir, d, "clock.jsonl")
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                for line in f:
                    try:
                        r = json.loads(line)
                        hl_o.append(r["hl_offset_ms"])
                        po_o.append(r["poly_offset_ms"])
                    except (ValueError, KeyError):
                        continue
    rng = lambda v: (max(v) - min(v)) if v else None
    return {"days": days, "continuous_days": best, "max_clock_offset_ms": max([abs(x) for x in hl_o + po_o]) if hl_o else None,
            "clock_offset_range_ms": max([rng(hl_o), rng(po_o)]) if hl_o else None, "error_rate": n_err / max(n_smp, 1)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join("data", "xvenue"))
    ap.add_argument("--pairs", nargs="+", default=DEFAULT)
    ap.add_argument("--period", type=float, default=7.0)
    ap.add_argument("--duration", type=float, default=None)
    ap.add_argument("--health", action="store_true")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    if a.health:
        h = health(a.out, a.period, len(a.pairs))
        json.dump(h, open(os.path.join(a.out, "health.json"), "w"), indent=1)
        print("jours continus (couverture médiane >= 90 %%, plus long trou <= 5 min) : %d ; décalage d'horloge maximal %s ms, variation %s ms (critère <= 300) ; taux d'erreurs %.3f %% (critère <= 1 %%)" % (
            h["continuous_days"], h["max_clock_offset_ms"], h["clock_offset_range_ms"], 100 * h["error_rate"]))
        for d, v in h["days"].items():
            print("  %s : %d paires, couverture médiane %.1f %%, minimale %.1f %%, plus long trou %.0f s" % (d, v["pairs"], 100 * v["coverage_median"], 100 * v["coverage_min"], v["max_gap_s"]))
        return
    poly = poly_get("/v1/info/instruments")
    hl_main = [u["name"] for u in hl_post({"type": "meta"})["universe"]]
    hl_xyz = [u["name"] for u in hl_post({"type": "meta", "dex": "xyz"})["universe"]]
    pairs = build_pairs(poly, hl_main, hl_xyz, a.pairs)
    json.dump(pairs, open(os.path.join(a.out, "pairs.json"), "w"), indent=1)
    print("%d paires (%d non vérifiées) ; poids Hyperliquid prévu %.0f par minute, Polymarket %.2f requêtes par seconde" % (
        len(pairs), sum(not p["verified"] for p in pairs), hl_weight_per_min(len(pairs), a.period), poly_rps(len(pairs), a.period)), flush=True)
    try:
        XRecorder(pairs, a.out, a.period).run(a.duration)
    except KeyboardInterrupt:
        print("arrêt demandé")


if __name__ == "__main__":
    main()
