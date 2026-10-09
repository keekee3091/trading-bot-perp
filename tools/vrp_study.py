"""Piste E : prime de variance (VIX contre volatilité réalisée du S&P 500) par vente mensuelle d'options, proxys Black-Scholes. Hors Polymarket, sans ordres.

Règles FIXÉES avant résultat dans CLAUDE.md (« Pré-enregistrement : piste E »). Mois non chevauchants de 21 jours de cotation ; entrée à la clôture t avec le VIX de t,
règlement à la clôture t+21 sur le cours brut du SPY. Prix Black-Scholes à la monnaie avec volatilité = VIX - 1,5 point, moins un demi-spread de 0,5 point à la vente ;
E1 = put vendu garanti en espèces, E2 = straddle vendu non couvert. Rendement excédentaire du mois = L x (prime - perte à l'échéance) / S0 (le capital non engagé rapporte rf).
Découverte avant 2019 ; le test 2019 -> 2026 n'est lu qu'une fois (verrou) et seulement si la découverte passe. Aucune série brute en sortie. stdlib uniquement.
python tools/vrp_study.py --mode discover | test
"""
import argparse
import csv
import datetime as dt
import math
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import carry_study as cs  # noqa: E402
import stocks_study as ss  # noqa: E402

NAN = float("nan")
T_M = 21 / 252
HAIRCUT, HALF_SPREAD = 0.015, 0.005
DISC_END = dt.date(2019, 1, 1)
X_MONTH = 0.0015
LOCK = os.path.join("results", "vrp_test.lock")


def phi(x):
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


def bs(S, K, sigma, T, r):
    """Prix Black-Scholes (sans dividende) d'un call et d'un put européens."""
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    call = S * phi(d1) - K * math.exp(-r * T) * phi(d2)
    put = K * math.exp(-r * T) * phi(-d2) - S * phi(-d1)
    return call, put


def load(data="data"):
    vix = {}
    with open(os.path.join(data, "under", "FRED_VIXCLS.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                vix[dt.date.fromisoformat(r["observation_date"])] = float(r["VIXCLS"]) / 100.0
            except ValueError:
                continue
    spy = {}
    with open(os.path.join(data, "tiingo", "SPY.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            spy[dt.date.fromisoformat(r["date"])] = float(r["close"])
    return vix, spy, cs.load_rf(data)


def months(vix, spy, rf, haircut=HAIRCUT, half_spread=HALF_SPREAD):
    """Liste de mois : date d'entrée, rendement du sous-jacent, P&L par S0 de E1 et E2, VIX, volatilité réalisée, taux sans risque. Dates SPY triées, pas de 21 jours."""
    ds = sorted(spy)
    out = []
    for j in range(0, len(ds) - 21, 21):
        d0, d1 = ds[j], ds[j + 21]
        v = vix.get(d0)
        if v is None or v != v:
            continue
        S0, S1 = spy[d0], spy[d1]
        r = cs.rf_at(rf, d0)
        sigma = max(v - haircut - half_spread, 0.03)
        call, put = bs(1.0, 1.0, sigma, T_M, r)
        ret = S1 / S0 - 1.0
        lr = [math.log(spy[ds[k]] / spy[ds[k - 1]]) for k in range(j + 1, j + 22)]
        rv = math.sqrt(252 * sum(x * x for x in lr) / len(lr))
        out.append({"d0": d0, "d1": d1, "ret": ret, "e1": put - max(-ret, 0.0), "e2": put + call - abs(ret), "vix": v, "rv": rv, "rf": r})
    return out


def equity(ms, key, L):
    e, path = 1.0, [1.0]
    for m in ms:
        e *= max(1.0 + m["rf"] * T_M + L * m[key], 0.0)
        path.append(e)
        if e <= 0:
            break
    return path


def maxdd(path):
    peak, dd = path[0], 0.0
    for x in path:
        peak = max(peak, x)
        dd = max(dd, 1 - x / peak)
    return dd


def cvar5(v):
    s = sorted(v)
    k = max(1, int(0.05 * len(s)))
    return sum(s[:k]) / k


def stats(ms, key, L):
    x = [L * m[key] for m in ms]
    mean, se = ss.jk_mean(x, 3)
    sd = statistics.pstdev(x)
    path = equity(ms, key, L)
    return {"n": len(x), "mean": mean, "se": se, "z": mean / se if se == se and se > 0 else NAN, "ci_lo": mean - 1.96 * se, "ci_hi": mean + 1.96 * se,
            "sharpe": mean / sd * math.sqrt(12) if sd > 0 else NAN, "worst": min(x), "cvar5": cvar5(x), "maxdd": maxdd(path), "ruin": path[-1] <= 0,
            "final": path[-1], "years": len(x) * T_M}


def criteria(ms, key, L):
    tr = [m for m in ms if m["d0"].year <= 2012]
    va = [m for m in ms if 2013 <= m["d0"].year <= 2018]
    ex = [m for m in ms if not 2008 <= m["d0"].year <= 2010]
    s = stats(ms, key, L)
    c = {
        "(1) rendement excédentaire moyen > 0,15 % par mois": s["mean"] > X_MONTH,
        "(2) borne basse IC95 > 0": s["ci_lo"] > 0,
        "(3) positif dans le train ET la validation": stats(tr, key, L)["mean"] > 0 and stats(va, key, L)["mean"] > 0,
        "(4) drawdown <= 45 % et pire mois >= -20 %": s["maxdd"] <= 0.45 and s["worst"] >= -0.20,
        "(5) Sharpe > 0,3": s["sharpe"] > 0.3,
        "(6) positif sans 2008-2010": stats(ex, key, L)["mean"] > 0,
    }
    return c, s


def vrp_descriptive(ms):
    d = [(m["vix"] - m["rv"]) * 100 for m in ms]
    sk = statistics.fmean(((x - statistics.fmean(d)) / statistics.pstdev(d)) ** 3 for x in d)
    return {"n": len(d), "mean_pts": statistics.fmean(d), "median_pts": statistics.median(d), "skew": sk, "worst_pts": min(d),
            "share_rv_above_vix": sum(1 for m in ms if m["rv"] > m["vix"]) / len(ms)}


def report(ms, label):
    L = ["%s : %d mois (%s -> %s)" % (label, len(ms), ms[0]["d0"], ms[-1]["d0"])]
    v = vrp_descriptive(ms)
    L.append("prime de variance brute (VIX - volatilité réalisée à 21 jours) : moyenne %+.2f points, médiane %+.2f, asymétrie %.2f, pire mois %+.1f points, volatilité réalisée > VIX dans %.0f %% des mois" % (
        v["mean_pts"], v["median_pts"], v["skew"], v["worst_pts"], 100 * v["share_rv_above_vix"]))
    spy = {"mean": statistics.fmean(m["ret"] - m["rf"] * T_M for m in ms)}
    L.append("SPY (comparaison) : excès moyen %+.2f %% par mois" % (100 * spy["mean"]))
    res = {}
    for key, name, Lref in (("e1", "E1 put garanti", 1.0), ("e2", "E2 straddle", 0.5)):
        c, s = criteria(ms, key, Lref)
        res[key] = (c, s)
        L.append("%s (L = %g) : excès moyen %+.3f %% par mois (IC95 [%+.3f ; %+.3f]), Sharpe %.2f, pire mois %+.1f %%, CVaR 5 %% %+.1f %%, drawdown maximal %.0f %%" % (
            name, Lref, 100 * s["mean"], 100 * s["ci_lo"], 100 * s["ci_hi"], s["sharpe"], 100 * s["worst"], 100 * s["cvar5"], 100 * s["maxdd"]))
        for k, ok in c.items():
            L.append("    critère %s : %s" % (k, "OUI" if ok else "NON"))
        L.append("    VERDICT %s : %s" % (name, "CRITÈRES TENUS" if all(c.values()) else "NÉGATIF"))
        L.append("    levier (excès moyen, Sharpe, drawdown, pire mois, ruine) : " + " ; ".join(
            "L=%g : %+.2f %% / %.2f / %.0f %% / %+.0f %% / %s" % (lv, 100 * stats(ms, key, lv)["mean"], stats(ms, key, lv)["sharpe"], 100 * stats(ms, key, lv)["maxdd"],
                                                                   100 * stats(ms, key, lv)["worst"], "oui" if stats(ms, key, lv)["ruin"] else "non") for lv in (0.5, 1.0, 2.0)))
    return L, res


def sensitivities(vix, spy, rf, upto):
    L = ["sensibilités (E1, L = 1, excès moyen par mois, IC95) :"]
    for h in (0.0, 0.015, 0.03):
        for sp in (0.0, 0.005, 0.01, 0.02):
            ms = [m for m in months(vix, spy, rf, h, sp) if m["d1"] < upto]
            s = stats(ms, "e1", 1.0)
            L.append("  VIX - %.1f pt, demi-spread %.1f pt : %+.3f %% [%+.3f ; %+.3f]" % (100 * h, 100 * sp, 100 * s["mean"], 100 * s["ci_lo"], 100 * s["ci_hi"]))
    return L


def test_report(ms, passed):
    """Lecture UNIQUE du test : mêmes critères sur le rendement, la borne basse de l'intervalle corrigée de Bonferroni (2 stratégies : z = 2,24), les deux moitiés du test, le drawdown, le Sharpe."""
    L = ["TEST 2019 -> 2026 : %d mois (%s -> %s)" % (len(ms), ms[0]["d0"], ms[-1]["d0"])]
    v = vrp_descriptive(ms)
    L.append("prime de variance brute : moyenne %+.2f points, médiane %+.2f, pire mois %+.1f points, volatilité réalisée > VIX dans %.0f %% des mois" % (
        v["mean_pts"], v["median_pts"], v["worst_pts"], 100 * v["share_rv_above_vix"]))
    L.append("SPY (comparaison) : excès moyen %+.2f %% par mois" % (100 * statistics.fmean(m["ret"] - m["rf"] * T_M for m in ms)))
    half = len(ms) // 2
    for key, name, Lref in (("e1", "E1 put garanti", 1.0), ("e2", "E2 straddle", 0.5)):
        s = stats(ms, key, Lref)
        lo_b = s["mean"] - 2.24 * s["se"]
        halves = [stats(ms[:half], key, Lref)["mean"], stats(ms[half:], key, Lref)["mean"]]
        c = {"(1) excès moyen > 0,15 % par mois": s["mean"] > X_MONTH, "(2) borne basse Bonferroni > 0": lo_b > 0,
             "(3) positif dans les deux moitiés": all(h > 0 for h in halves), "(4) drawdown <= 45 % et pire mois >= -20 %": s["maxdd"] <= 0.45 and s["worst"] >= -0.20,
             "(5) Sharpe > 0,3": s["sharpe"] > 0.3}
        L.append("%s (L = %g, passait la découverte : %s) : excès moyen %+.3f %% par mois (IC95 [%+.3f ; %+.3f], borne Bonferroni %+.3f), Sharpe %.2f, pire mois %+.1f %%, drawdown %.0f %%, moitiés %+.3f %% et %+.3f %%" % (
            name, Lref, "oui" if key in passed else "non", 100 * s["mean"], 100 * s["ci_lo"], 100 * s["ci_hi"], 100 * lo_b, s["sharpe"], 100 * s["worst"], 100 * s["maxdd"],
            100 * halves[0], 100 * halves[1]))
        for k, ok in c.items():
            L.append("    critère %s : %s" % (k, "OUI" if ok else "NON"))
        L.append("    VERDICT %s : %s" % (name, "CRITÈRES TENUS" if all(c.values()) else "NÉGATIF"))
        L.append("    levier (excès moyen, Sharpe, drawdown, pire mois, ruine) : " + " ; ".join(
            "L=%g : %+.2f %% / %.2f / %.0f %% / %+.0f %% / %s" % (lv, 100 * stats(ms, key, lv)["mean"], stats(ms, key, lv)["sharpe"], 100 * stats(ms, key, lv)["maxdd"],
                                                                   100 * stats(ms, key, lv)["worst"], "oui" if stats(ms, key, lv)["ruin"] else "non") for lv in (0.5, 1.0, 2.0)))
    return L


def alpha_beta(ms, key, L):
    """DESCRIPTIF (non pré-enregistré) : régression du rendement excédentaire de la stratégie sur celui du SPY ; beta, alpha mensuel et son t."""
    y = [L * m[key] for m in ms]
    x = [m["ret"] - m["rf"] * T_M for m in ms]
    mx, my = statistics.fmean(x), statistics.fmean(y)
    sxx = sum((a - mx) ** 2 for a in x)
    b = sum((a - mx) * (c - my) for a, c in zip(x, y)) / sxx
    a0 = my - b * mx
    se = math.sqrt(sum((yy - a0 - b * xx) ** 2 for xx, yy in zip(x, y)) / (len(x) - 2) * (1 / len(x) + mx * mx / sxx))
    return b, a0, a0 / se


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["discover", "test", "alpha"], required=True)
    ap.add_argument("--data", default="data")
    ap.add_argument("--out", default="results")
    a = ap.parse_args()
    vix, spy, rf = load(a.data)
    if a.mode == "alpha":
        allm = months(vix, spy, rf)
        for lab, ms in (("découverte", [m for m in allm if m["d1"] < DISC_END]), ("test (descriptif, après la lecture unique)", [m for m in allm if m["d0"] >= DISC_END])):
            for key, Lr in (("e1", 1.0), ("e2", 0.5)):
                b, a0, t = alpha_beta(ms, key, Lr)
                print("%s %s : beta %.2f, alpha %+.3f %% par mois (t = %.2f)" % (lab, key, b, 100 * a0, t))
        return
    if a.mode == "discover":
        ms = [m for m in months(vix, spy, rf) if m["d1"] < DISC_END]
        L, res = report(ms, "DÉCOUVERTE")
        L += sensitivities(vix, spy, rf, DISC_END)
        text = "\n".join(L)
        open(os.path.join(a.out, "vrp_summary.txt"), "w", encoding="utf-8").write(text + "\n")
        print(text)
    else:
        if os.path.exists(LOCK):
            raise SystemExit("TEST REFUSÉ : déjà lu une fois")
        ms0 = [m for m in months(vix, spy, rf) if m["d1"] < DISC_END]
        passed = [k for k, (c, s) in report(ms0, "x")[1].items() if all(c.values())]
        if not passed:
            raise SystemExit("TEST REFUSÉ : aucune stratégie ne passe la découverte")
        open(LOCK, "w").write("lu")
        ms = [m for m in months(vix, spy, rf) if m["d0"] >= DISC_END]
        L = test_report(ms, passed)
        text = "\n".join(L)
        open(os.path.join(a.out, "vrp_test.txt"), "w", encoding="utf-8").write(text + "\n")
        print(text)


if __name__ == "__main__":
    main()
