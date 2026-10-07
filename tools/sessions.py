"""Session de marché par bougie : colonne `session` (1 = marché sous-jacent ouvert, 0 = hors session).

La doc (perps/learn-about-trading/market-sessions) dit que les perps tournent 24/7 et que la session
ne change que les flux de prix externes qui calculent index et mark. Hors session, le prix vient de
flux de repli minces ou absents : on ne le traite pas comme de la liquidité (pas d'entrée, pas
d'historique de signal). Le calendrier exact n'est pas exposé par l'API : règles par catégorie,
validées par le profil d'activité des klines (voir `python tools/sessions.py --check`).

  crypto            toujours ouvert
  index, commodity  type futures : fermé du vendredi 21:00 UTC au dimanche 22:00 UTC
                    (la pause quotidienne d'une heure est ignorée)
  equity            heures régulières US lun-ven 13:30-20:00 UTC (heure d'été US, jusqu'au 1er
                    novembre 2026, fin des données comprise) ; pré-marché, après-marché, nuit
                    et week-end sont hors session
Les jours fériés ne sont pas gérés (Labor Day 2026-09-07 compte comme ouvert).

python tools/sessions.py --apply   réécrit data/*_1m.csv avec la colonne session
python tools/sessions.py --check   profil : part des minutes avec trades dans et hors session
"""
import csv
import glob
import os
import sys
import time


def in_session(category: str, ts_s: float) -> int:
    if category == "crypto":
        return 1
    g = time.gmtime(ts_s)
    dow, hm = g.tm_wday, g.tm_hour * 60 + g.tm_min  # lundi = 0
    if category in ("index", "commodity"):
        if dow == 5 or (dow == 4 and hm >= 21 * 60) or (dow == 6 and hm < 22 * 60):
            return 0
        return 1
    if category == "equity":
        return 1 if dow < 5 and 13 * 60 + 30 <= hm < 20 * 60 else 0
    return 1


def categories():
    with open("data/universe_survey.csv") as f:
        return {r["symbol"]: r["category"] for r in csv.DictReader(f)}


def rewrite(path, category):
    with open(path) as f:
        rows = list(csv.DictReader(f))
    cols = [c for c in rows[0].keys() if c != "session"] + ["session"]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            r["session"] = in_session(category, int(r["ts"]) / 1000)
            w.writerow(r)
    return len(rows)


def check():
    cats = categories()
    print("%-12s %-9s %8s %10s %10s %12s" % ("symbole", "catégorie", "% min.", "% avec tr.", "% avec tr.", "ratio actif."))
    print("%-12s %-9s %8s %10s %10s %12s" % ("", "", "en sess.", "en session", "hors sess.", "in/out"))
    for p in sorted(glob.glob("data/*_1m.csv")):
        sym = os.path.basename(p)[:-7]
        cat = cats.get(sym, "crypto")
        n = [0, 0]
        act = [0, 0]
        with open(p) as f:
            for r in csv.DictReader(f):
                s = in_session(cat, int(r["ts"]) / 1000)
                n[s] += 1
                act[s] += 1 if int(r["trades"]) > 0 else 0
        a_in = 100 * act[1] / n[1] if n[1] else 0
        a_out = 100 * act[0] / n[0] if n[0] else 0
        print("%-12s %-9s %8.1f %10.1f %10.1f %12s" % (sym, cat, 100 * n[1] / max(1, sum(n)), a_in, a_out,
                                                          "%.1f" % (a_in / a_out) if a_out else "-"))


if __name__ == "__main__":
    if "--apply" in sys.argv:
        cats = categories()
        for p in sorted(glob.glob("data/*_1m.csv")):
            sym = os.path.basename(p)[:-7]
            print(sym, cats.get(sym, "crypto"), rewrite(p, cats.get(sym, "crypto")), "lignes")
    elif "--check" in sys.argv:
        check()
    else:
        print(__doc__)
