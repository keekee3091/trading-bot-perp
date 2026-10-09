"""Piste F : calibration des marchés de prédiction Polymarket résolus (biais favori / outsider), net du spread et du coût du capital.

Règles FIXÉES avant résultat dans CLAUDE.md (« Pré-enregistrement : piste F »). Pour chaque marché binaire résolu et chaque horizon h (1, 7, 30 jours) : prix de Yes à T0 = date de fin - h
(dernier point d'historique antérieur à T0, à moins de 2 jours), marché démarré et OUVERT à T0. Règles : LONGSHOT_SELL (acheter No si Yes < 10 %), FAV_BUY (acheter Yes si Yes >= 90 %).
Rendement par dollar = gain / (prix + 1 cent) - 1 - rf x jours jusqu'à la résolution / 365. Erreur-type : jackknife en supprimant un événement. Test (2026) lu une seule fois (verrou).
Aucun accès à un compte. stdlib uniquement. python tools/pm_calibration.py --mode discover | test
"""
import argparse
import bisect
import csv
import datetime as dt
import json
import math
import os
import random
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import carry_study as cs  # noqa: E402
import grid_stage1 as gs  # noqa: E402

NAN = float("nan")
HORIZONS = (1, 7, 30)
RULES = ("LONGSHOT_SELL", "FAV_BUY")
BINS = ((0.0, 0.05), (0.05, 0.10), (0.10, 0.20), (0.20, 0.80), (0.80, 0.90), (0.90, 0.95), (0.95, 1.0001))
SPREAD_HALF = 0.01
X_TRADE = 0.01
TRAIN_END, VAL_END = dt.date(2025, 6, 30), dt.date(2025, 12, 31)
LOCK = os.path.join("results", "pm_test.lock")


def parse_ts(s):
    if s is None:
        return None
    s = s.replace("Z", "+00:00").replace(" ", "T")
    if len(s) > 6 and s[-3:] in ("+00",):
        s += ":00"
    return dt.datetime.fromisoformat(s)


def period(end_date):
    return "train" if end_date <= TRAIN_END else ("validation" if end_date <= VAL_END else "test")


def load(data="data"):
    mk = {}
    with open(os.path.join(data, "pm", "markets.jsonl"), encoding="utf-8") as f:
        for line in f:
            m = json.loads(line)
            mk[m["id"]] = m
    hist = {}
    with open(os.path.join(data, "pm", "history.jsonl"), encoding="utf-8") as f:
        for line in f:
            h = json.loads(line)
            hist[h["id"]] = h["h"]
    return mk, hist


def price_at(h, t0):
    """Dernier point de l'historique [[t, p], ...] antérieur ou égal à t0 (secondes), à moins de 2 jours ; sinon None."""
    ts = [x[0] for x in h]
    j = bisect.bisect_right(ts, t0) - 1
    if j < 0 or t0 - ts[j] > 2 * 86400:
        return None
    return h[j][1]


def build_trades(mk, hist, rf, horizons=HORIZONS, spread=SPREAD_HALF):
    """Retourne (transactions, comptes d'exclusion). Chaque transaction : règle, horizon, période, événement, rendement net, prix de Yes, issue, jours, date de fin."""
    out, why = [], {}

    def ex(r):
        why[r] = why.get(r, 0) + 1
    for mid, m in mk.items():
        h = hist.get(mid)
        if not h:
            ex("historique absent")
            continue
        end = parse_ts(m["end"])
        start = parse_ts(m["start"])
        closed = parse_ts(m["closed"])
        for hz in horizons:
            T0 = end - dt.timedelta(days=hz)
            if start is None or start >= T0:
                ex("pas démarré à T0")
                continue
            if closed is not None and closed <= T0:
                ex("fermé avant T0")
                continue
            p = price_at(h, T0.timestamp())
            if p is None:
                ex("pas de prix récent à T0")
                continue
            y = 1.0 if m["yes"] == 1.0 else 0.0
            days = max(((closed or end) - T0).total_seconds() / 86400.0, 0.0)
            carry = cs.rf_at(rf, T0.date()) * days / 365.0
            for rule in RULES:
                if rule == "LONGSHOT_SELL" and p < 0.10:
                    ask, win = (1.0 - p) + spread, 1.0 - y
                elif rule == "FAV_BUY" and p >= 0.90:
                    ask, win = p + spread, y
                else:
                    continue
                if ask >= 1.0:
                    ex("prix d'achat >= 1")
                    continue
                out.append({"rule": rule, "h": hz, "period": period(end.date()), "event": m["event"] or mid, "r": win / ask - 1.0 - carry, "p": p, "y": y,
                            "days": days, "end": end.date(), "ask": ask, "win": win, "carry": carry})
    return out, why


def jack(trades):
    """Moyenne et erreur-type par jackknife en supprimant un événement à la fois."""
    n = len(trades)
    if n < 30:
        return NAN, NAN
    S = sum(t["r"] for t in trades)
    by = {}
    for t in trades:
        a = by.setdefault(t["event"], [0.0, 0])
        a[0] += t["r"]
        a[1] += 1
    J = len(by)
    if J < 5:
        return S / n, NAN
    th = [(S - a[0]) / (n - a[1]) for a in by.values() if n - a[1] > 0]
    m = sum(th) / len(th)
    return S / n, math.sqrt((len(th) - 1) / len(th) * sum((x - m) ** 2 for x in th))


def wilson(k, n, z=1.96):
    if n == 0:
        return NAN, NAN
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h


def calibration(mk, hist, rf):
    """Table descriptive : par horizon et tranche de prix de Yes, fréquence réalisée contre prix moyen (toutes périodes de découverte)."""
    rows = []
    for hz in HORIZONS:
        pts = []
        for mid, m in mk.items():
            h = hist.get(mid)
            if not h or period(parse_ts(m["end"]).date()) == "test":
                continue
            end, start, closed = parse_ts(m["end"]), parse_ts(m["start"]), parse_ts(m["closed"])
            T0 = end - dt.timedelta(days=hz)
            if start is None or start >= T0 or (closed is not None and closed <= T0):
                continue
            p = price_at(h, T0.timestamp())
            if p is not None:
                pts.append((p, 1.0 if m["yes"] == 1.0 else 0.0))
        for lo, hi in BINS:
            b = [x for x in pts if lo <= x[0] < hi]
            if b:
                k = sum(y for _p, y in b)
                w0, w1 = wilson(k, len(b))
                rows.append((hz, lo, hi, len(b), statistics.fmean(p for p, _y in b), k / len(b), k / len(b) - statistics.fmean(p for p, _y in b), w0, w1))
    return rows


def null_means(trs, draws=1000, seed=20261013):
    """Moyenne des rendements sous la calibration parfaite : issues tirées selon Bernoulli(prix de Yes) sur les mêmes transactions."""
    rng = random.Random(seed)
    out = []
    for _ in range(draws):
        tot = 0.0
        for t in trs:
            y = 1.0 if rng.random() < t["p"] else 0.0
            win = (1.0 - y) if t["rule"] == "LONGSHOT_SELL" else y
            tot += win / t["ask"] - 1.0 - t["carry"]
        out.append(tot / len(trs))
    return sorted(out)


def phi_p1(z):
    return 0.5 * math.erfc(z / math.sqrt(2.0))


def evaluate(trades, rf_unused=None, with_null=True):
    """Statistiques par règle et horizon sur train + validation et critères (1) à (8)."""
    res = {}
    for rule in RULES:
        for hz in HORIZONS:
            tr = [t for t in trades if t["rule"] == rule and t["h"] == hz and t["period"] == "train"]
            va = [t for t in trades if t["rule"] == rule and t["h"] == hz and t["period"] == "validation"]
            pooled = tr + va
            m, se = jack(pooled)
            res[(rule, hz)] = {"n_train": len(tr), "n_val": len(va), "mean": m, "se": se, "z": m / se if se == se and se > 0 else NAN, "mean_train": jack(tr)[0],
                               "mean_val": jack(va)[0], "pooled": pooled}
    cells = list(res)
    ps = [phi_p1(res[k]["z"]) if res[k]["z"] == res[k]["z"] else NAN for k in cells]
    qs = gs.bh_q(ps)
    for k, q in zip(cells, qs):
        r = res[k]
        pooled = r["pooled"]
        months = max(1.0, (max((t["end"] for t in pooled), default=dt.date(2023, 1, 1)) - min((t["end"] for t in pooled), default=dt.date(2023, 1, 1))).days / 30.4) if pooled else 1.0
        by_ev = {}
        for t in pooled:
            by_ev[t["event"]] = by_ev.get(t["event"], 0.0) + t["r"]
        top5 = set(sorted(by_ev, key=lambda e: -by_ev[e])[:5])
        ex5 = [t for t in pooled if t["event"] not in top5]
        # coût de spread de 2 cents : recalcul du rendement avec ask + 0,01
        s2 = [(t["win"] / (t["ask"] + 0.01) - 1.0 - t["carry"]) for t in pooled if t["ask"] + 0.01 < 1.0]
        nm = null_means(pooled, 1000) if (with_null and pooled) else []
        beat = sum(1 for x in nm if x < r["mean"]) / len(nm) if nm else NAN
        r.update({"q": q, "months": months, "trades_per_month": len(pooled) / months, "ex5": (sum(t["r"] for t in ex5) / len(ex5)) if ex5 else NAN,
                  "spread2": statistics.fmean(s2) if s2 else NAN, "beat_null": beat})
        r["criteria"] = {
            "(1) rendement net moyen > 1 %": r["mean"] > X_TRADE,
            "(2) IC95 bas > 0 sur train + validation, positif dans chacun": r["mean"] - 1.96 * r["se"] > 0 and r["mean_train"] > 0 and r["mean_val"] > 0,
            "(3) >= 300 transactions dans le train et dans la validation": r["n_train"] >= 300 and r["n_val"] >= 300,
            "(4) BH-FDR 5 %": q == q and q <= 0.05,
            "(5) bat 95 % des tirages de calibration parfaite": beat == beat and beat >= 0.95,
            "(6) positif sans les 5 meilleurs événements": r["ex5"] == r["ex5"] and r["ex5"] > 0,
            "(7) positif avec 2 cents de spread": r["spread2"] == r["spread2"] and r["spread2"] > 0,
            "(8) >= 20 transactions par mois": r["trades_per_month"] >= 20,
        }
    return res


def report(res):
    L = []
    for (rule, hz), r in res.items():
        ok = all(r["criteria"].values())
        L.append("%-14s h=%2d j : n train %4d, validation %4d ; rendement net moyen %+7.2f %% (se %.2f), train %+.2f %%, validation %+.2f %% ; q %.3f ; sans top 5 %+.2f %% ; 2 cents %+.2f %% ; "
                 "bat la calibration parfaite %.0f %% ; %.0f trans./mois ; %s" % (
                     rule, hz, r["n_train"], r["n_val"], 100 * r["mean"], 100 * r["se"], 100 * r["mean_train"], 100 * r["mean_val"], r["q"], 100 * r["ex5"], 100 * r["spread2"],
                     100 * r["beat_null"] if r["beat_null"] == r["beat_null"] else NAN, r["trades_per_month"], "CRITÈRES TENUS" if ok else "NÉGATIF"))
        if not ok:
            L.append("      échecs : " + " ; ".join(k for k, v in r["criteria"].items() if not v))
    return L


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["discover", "test"], required=True)
    ap.add_argument("--data", default="data")
    ap.add_argument("--out", default="results")
    a = ap.parse_args()
    mk, hist = load(a.data)
    rf = cs.load_rf(a.data)
    trades, why = build_trades(mk, hist, rf)
    if a.mode == "discover":
        disc = [t for t in trades if t["period"] != "test"]
        res = evaluate(disc)
        L = ["DÉCOUVERTE : %d marchés, %d avec historique ; exclusions (marché x horizon) : %s" % (len(mk), len(hist), why)]
        L += report(res)
        with open(os.path.join(a.out, "pm_calibration.csv"), "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["horizon_days", "price_lo", "price_hi", "n", "mean_price", "realized_freq", "gap", "wilson_lo", "wilson_hi"])
            for row in calibration(mk, hist, rf):
                w.writerow([row[0], row[1], min(row[2], 1.0)] + ["%.5g" % x for x in row[3:]])
        text = "\n".join(L)
        open(os.path.join(a.out, "pm_summary.txt"), "w", encoding="utf-8").write(text + "\n")
        print(text)
    else:
        if os.path.exists(LOCK):
            raise SystemExit("TEST REFUSÉ : déjà lu une fois")
        disc = [t for t in trades if t["period"] != "test"]
        res = evaluate(disc)
        passed = [k for k, r in res.items() if all(r["criteria"].values())]
        if not passed:
            raise SystemExit("TEST REFUSÉ : aucune règle ne passe la découverte")
        open(LOCK, "w").write("lu")
        L = ["TEST 2026 : règles passant la découverte : %s" % passed]
        for rule, hz in passed:
            te = [t for t in trades if t["period"] == "test" and t["rule"] == rule and t["h"] == hz]
            m, se = jack(te)
            nm = null_means(te, 1000) if te else []
            beat = sum(1 for x in nm if x < m) / len(nm) if nm else NAN
            z_b = 1.96 if len(passed) == 1 else 2.24
            L.append("%s h=%d : n %d, rendement net moyen %+.2f %% (se %.2f, borne basse corrigée %+.2f %%), bat la calibration parfaite %.0f %%" % (
                rule, hz, len(te), 100 * m, 100 * se, 100 * (m - z_b * se), 100 * beat))
        text = "\n".join(L)
        open(os.path.join(a.out, "pm_test.txt"), "w", encoding="utf-8").write(text + "\n")
        print(text)


if __name__ == "__main__":
    main()
