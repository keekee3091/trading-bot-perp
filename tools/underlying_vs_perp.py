"""Écart mesuré entre le perp Polymarket et son sous-jacent (période commune, quelques mois) : ce qui se vérifie déjà.

NAS100 : perp NAS100-USD contre FRED NASDAQ100 (clôture de séance 16:00 New York = 20:00 UTC pendant l'heure d'été américaine,
qui couvre toute la période commune). WTI : perp WTIOIL-USD contre FRED DCOILWTICO (prix spot EIA, règlement NYMEX 14:30 New
York = 18:30 UTC, approximatif : le prix spot EIA n'est pas exactement le règlement). Pour chaque jour où FRED publie un prix on
prend la clôture 1m du perp à l'heure correspondante.
Mesures : écart de NIVEAU (perp / sous-jacent - 1), écart des RENDEMENTS quotidiens (corrélation, écart-type de la différence,
en bps), et part de la variance du perp qui tombe HORS des heures de séance US (13:30 - 20:00 UTC, lundi - vendredi), à partir des
rendements horaires du perp (hors séance : le sous-jacent ne cote pas, c'est le comportement propre du perp).
Ne mesure PAS : le comportement du sous-jacent hors séance (pas de données), le spread réel, le funding réel à long terme.

stdlib uniquement. python tools/underlying_vs_perp.py
"""
import csv
import math
import statistics
import time
import calendar


def load_fred(name):
    with open("data/under/FRED_%s.csv" % name) as f:
        return {r["date"]: float(r["value"]) for r in csv.DictReader(f)}


def load_perp(sym):
    ts, close = [], []
    with open("data/%s_1m.csv" % sym) as f:
        for r in csv.DictReader(f):
            ts.append(int(r["ts"]) // 1000)
            close.append(float(r["close"]))
    return ts, close


def price_at(ts, close, t):
    import bisect
    i = bisect.bisect_right(ts, t) - 1
    return close[i] if i >= 0 and t - ts[i] < 3600 else None


def compare(sym, fred_name, hh, mm, out):
    fred = load_fred(fred_name)
    ts, close = load_perp(sym)
    t0, t1 = ts[0], ts[-1]
    days = sorted(d for d in fred if time.strftime("%Y-%m-%d", time.gmtime(t0)) <= d <= time.strftime("%Y-%m-%d", time.gmtime(t1)))
    lv, rp, rf = [], [], []
    prev = None
    for d in days:
        y, m, dd = (int(x) for x in d.split("-"))
        t = calendar.timegm((y, m, dd, hh, mm, 0))
        p = price_at(ts, close, t)
        if p is None or fred[d] <= 0 or p <= 0:
            prev = None
            continue
        lv.append(1e4 * (p / fred[d] - 1.0))
        if prev is not None:
            rp.append(math.log(p / prev[0]))
            rf.append(math.log(fred[d] / prev[1]))
        prev = (p, fred[d])
    diff = [1e4 * (a - b) for a, b in zip(rp, rf)]
    out.append("%s contre FRED %s (%d jours communs du %s au %s)" % (sym, fred_name, len(lv), days[0], days[-1]))
    out.append("  écart de niveau perp / sous-jacent : moyenne %+.1f bps, écart-type %.1f, min %+.1f, max %+.1f" % (statistics.fmean(lv), statistics.pstdev(lv), min(lv), max(lv)))
    out.append("  rendements quotidiens : corrélation %.4f ; écart-type du rendement du sous-jacent %.1f bps ; écart-type de la DIFFÉRENCE perp - sous-jacent %.1f bps ; |différence| moyenne %.1f bps"
               % (statistics.correlation(rp, rf), 1e4 * statistics.pstdev(rf), statistics.pstdev(diff), statistics.fmean(abs(x) for x in diff)))
    # variance hors séance, depuis les rendements horaires du perp
    h_in = h_out = 0.0
    last = None
    for t, c in zip(ts, close):
        if t % 3600 != 0:
            continue
        if last is not None and t - last[0] == 3600:
            r = math.log(c / last[1])
            g = time.gmtime(t - 1800)  # milieu de l'heure
            insess = g.tm_wday < 5 and 13 * 60 + 30 <= g.tm_hour * 60 + g.tm_min < 20 * 60
            if insess:
                h_in += r * r
            else:
                h_out += r * r
        last = (t, c)
    out.append("  variance du perp (rendements horaires) : %.0f %% pendant la séance US (13:30-20:00 UTC, lun-ven), %.0f %% HORS séance (séance = 19 %% des heures)"
               % (100 * h_in / (h_in + h_out), 100 * h_out / (h_in + h_out)))


def main():
    out = ["ÉCART PERP / SOUS-JACENT MESURÉ (période commune de quelques mois)", ""]
    compare("NAS100-USD", "NASDAQ100", 20, 0, out)
    out.append("")
    compare("WTIOIL-USD", "DCOILWTICO", 18, 30, out)
    out.append("")
    out.append("Lecture : un écart de niveau moyen de quelques bps et une corrélation quotidienne proche de 1 signifient que le perp suit "
               "bien son sous-jacent à l'échelle du jour ; l'écart-type de la différence quotidienne est le bruit de base (à comparer au coût "
               "d'un rééquilibrage mensuel de 4 à 8 bps) ; la part de variance hors séance est un comportement du perp NON mesurable sur le sous-jacent.")
    text = "\n".join(out) + "\n"
    print(text)
    with open("results/underlying_vs_perp.txt", "w", encoding="utf-8") as f:
        f.write(text)


if __name__ == "__main__":
    main()
