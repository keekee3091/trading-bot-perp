"""Économie théorique du market making, depuis les données de tools/recorder.py (data/live/).

Lecture seule, aucun ordre, aucune authentification. Chaque chiffre est étiqueté :
  [MESURÉ]  calculé directement sur les données enregistrées
  [SUPPOSÉ] hypothèse du modèle, non mesurée (listée en tête du rapport)
  [DÉRIVÉ]  calcul à partir de mesures et d'hypothèses ; hérite de la fragilité des deux

Par instrument, séparément en séance et hors séance (colonne `session` de l'enregistreur) :
  [MESURÉ]  spread moyen, médian, p90 ; profondeur au touch (notionnel au meilleur bid et au meilleur ask,
            et dans 5 bps du mid) ; volatilité à court terme du mid (variance réalisée par seconde,
            ramenée à 1 s, 10 s et 60 s) ;
  [DÉRIVÉ]  P&L théorique d'un aller-retour maker = spread capturé - 2 x frais maker, AVANT sélection
            adverse ; seuil de sélection adverse par exécution qui annule ce gain =
            (spread - 2 x frais maker) / 2 ; horizon tau* tel qu'un mouvement de 1 sigma du mid
            (sigma x racine de tau*) égale ce seuil.

HYPOTHÈSES du modèle (non mesurées, à ne pas oublier en lisant les chiffres) :
  H1 les deux jambes s'exécutent au meilleur prix du côté maker (bid pour acheter, ask pour vendre), sans
     amélioration de prix, sans file d'attente ni fill partiel, avec probabilité d'exécution 1 ;
  H2 frais maker de 1.25 bps par jambe (tier 0 de la page des frais ; paramètre --maker-fee-bps) ;
  H3 aucun coût d'inventaire, de funding, ni de latence ; aucune récompense de liquidité (le programme
     documenté ne peut pas être estimé sans la part de volume maker de l'exchange, non disponible) ;
  H4 le mid est une marche aléatoire à variance constante sur l'échantillon (la volatilité n'est pas
     stationnaire en réalité) ; la sélection adverse réelle n'est PAS mesurable ici : il faudrait les
     exécutions réelles du carnet (trades) et leur mouvement du mid après coup.

Règle de lecture : aucune conclusion avant plusieurs jours de données (--min-days, défaut 3) ; en
dessous, le rapport l'affiche en tête et chaque ligne reste indicative. Un seul relevé en séance ne dit
rien des heures creuses ni du week-end.

stdlib uniquement : python tools/mm_economics.py [--data data/live] [--maker-fee-bps 1.25] [--min-days 3]
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
import statistics
import sys

MAX_GAP_S = 30.0  # intervalles plus longs que 30 s (panne, trou) exclus du calcul de volatilité


def read_jsonl(pattern):
    out = []
    for path in sorted(glob.glob(pattern)):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue  # ligne tronquée (arrêt brutal) : ignorée
    return out


def quantile(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * (len(xs) - 1) + 0.5))] if xs else float("nan")


def mean(xs):
    return statistics.fmean(xs) if xs else float("nan")


def realized_vol_per_sqrt_s(points):
    """points : [(t_s, mid)] trié. sigma^2 = somme(r^2) / somme(dt) sur les intervalles <= MAX_GAP_S.
    Retourne (sigma par racine de seconde, nombre d'intervalles) ; sigma est un rendement relatif."""
    s2, sdt, n = 0.0, 0.0, 0
    for (t0, m0), (t1, m1) in zip(points, points[1:]):
        dt = t1 - t0
        if dt <= 0 or dt > MAX_GAP_S or m0 <= 0 or m1 <= 0:
            continue
        r = math.log(m1 / m0)
        s2 += r * r
        sdt += dt
        n += 1
    return (math.sqrt(s2 / sdt) if sdt > 0 else float("nan")), n


def analyse(data_dir, maker_fee_bps):
    books = read_jsonl(os.path.join(data_dir, "*", "books.jsonl"))
    ticks = read_jsonl(os.path.join(data_dir, "*", "tickers.jsonl"))
    ts = [b["t"] for b in books] + [t["t"] for t in ticks]
    span_days = (max(ts) - min(ts)) / 86_400_000 if ts else 0.0
    syms = sorted({b["sym"] for b in books} | {t["sym"] for t in ticks})
    rows = []
    for sym in syms:
        for sess in (1, 0):
            bk = [b for b in books if b["sym"] == sym and b["session"] == sess]
            tk = sorted((t["t"] / 1000.0, t["mid"]) for t in ticks if t["sym"] == sym and t["session"] == sess)
            if not bk and not tk:
                continue
            spreads = [b["spread_bps"] for b in bk]
            bid_n = [b["bids"][0][0] * b["bids"][0][1] for b in bk]
            ask_n = [b["asks"][0][0] * b["asks"][0][1] for b in bk]
            d5 = [b["depth_bid"]["5"] + b["depth_ask"]["5"] for b in bk]
            sig, nint = realized_vol_per_sqrt_s(tk)
            sp = mean(spreads)
            rt = sp - 2 * maker_fee_bps                      # DÉRIVÉ, avant sélection adverse
            as_be = rt / 2                                   # DÉRIVÉ, par exécution
            sig_bps = sig * 1e4                              # MESURÉ, bps par racine de seconde
            tau = (as_be / sig_bps) ** 2 if (as_be > 0 and sig_bps > 0) else float("nan")
            rows.append({
                "sym": sym, "session": sess, "n_book": len(bk), "n_tick_int": nint,
                "spread_mean": sp, "spread_med": statistics.median(spreads) if spreads else float("nan"),
                "spread_p90": quantile(spreads, 0.9),
                "touch_bid": mean(bid_n), "touch_ask": mean(ask_n), "depth5": mean(d5),
                "sig_bps_sqrt_s": sig_bps,
                "vol_1s": sig_bps, "vol_10s": sig_bps * math.sqrt(10), "vol_60s": sig_bps * math.sqrt(60),
                "rt_bps": rt, "rt_per_1000": rt * 0.1, "as_breakeven": as_be, "tau_star": tau,
            })
    return {"span_days": span_days, "n_books": len(books), "n_ticks": len(ticks), "rows": rows}


def fmt(x, w=8, p=2):
    return ("%*.*f" % (w, p, x)) if x == x and abs(x) != float("inf") else "%*s" % (w, "n/a")


def report(res, maker_fee_bps, min_days):
    out = []
    out.append("ÉCONOMIE THÉORIQUE DU MARKET MAKING (maker, frais %.2f bps par jambe)" % maker_fee_bps)
    out.append("Données : %.2f jour(s) d'enregistrement, %d relevés de carnet, %d relevés de ticker" %
               (res["span_days"], res["n_books"], res["n_ticks"]))
    if res["span_days"] < min_days:
        out.append("*** DONNÉES INSUFFISANTES : %.2f jour(s) < %.1f. Chiffres INDICATIFS, AUCUNE conclusion à tirer. ***" %
                   (res["span_days"], min_days))
    out.append("")
    out.append("[SUPPOSÉ] H1 exécution au touch des deux jambes, probabilité 1, sans file d'attente ; H2 frais maker %.2f bps par jambe ;"
               % maker_fee_bps)
    out.append("[SUPPOSÉ] H3 ni inventaire, ni funding, ni latence, ni récompenses de liquidité ; H4 mid en marche aléatoire à variance constante.")
    out.append("[NON MESURABLE ICI] la sélection adverse réelle (exige les exécutions du carnet et le mouvement du mid après chacune).")
    out.append("")
    hdr = ("%-11s %-6s %6s | %8s %8s %8s | %10s %10s %10s | %9s %9s %9s | %9s %9s | %9s %8s")
    out.append(hdr % ("instrument", "sess.", "n_book", "spr.moy", "spr.méd", "spr.p90", "touch bid", "touch ask", "depth 5bp",
                      "vol 1s", "vol 10s", "vol 60s", "A/R net", "net/1000", "AS seuil", "tau*"))
    out.append(hdr % ("", "", "", "[M] bps", "[M] bps", "[M] bps", "[M] $", "[M] $", "[M] $", "[M] bps", "[M] bps", "[M] bps",
                      "[D] bps", "[D] $", "[D] bps", "[D] s"))
    for r in res["rows"]:
        out.append(hdr % (r["sym"], "séance" if r["session"] else "hors", r["n_book"], fmt(r["spread_mean"]), fmt(r["spread_med"]),
                          fmt(r["spread_p90"]), fmt(r["touch_bid"], 10, 0), fmt(r["touch_ask"], 10, 0), fmt(r["depth5"], 10, 0),
                          fmt(r["vol_1s"], 9), fmt(r["vol_10s"], 9), fmt(r["vol_60s"], 9), fmt(r["rt_bps"], 9),
                          fmt(r["rt_per_1000"], 9, 3), fmt(r["as_breakeven"], 9), fmt(r["tau_star"], 8, 1)))
    out.append("")
    out.append("Colonnes : [M] mesuré, [D] dérivé. A/R net = spread moyen - 2 x frais maker (avant sélection adverse), en bps du notionnel ;")
    out.append("net/1000 = gain en $ par aller-retour de 1000 de notionnel ; AS seuil = sélection adverse par exécution (bps) qui annule le gain ;")
    out.append("tau* = horizon (s) tel qu'un mouvement de 1 sigma du mid égale AS seuil (n/a si le gain est déjà <= 0 ou sigma inconnu).")
    neg = [r for r in res["rows"] if r["rt_bps"] <= 0 and r["n_book"]]
    if neg:
        out.append("")
        out.append("[DÉRIVÉ] Spread moyen <= 2 x frais maker (aller-retour négatif AVANT toute sélection adverse) pour : " +
                   ", ".join("%s (%s)" % (r["sym"], "séance" if r["session"] else "hors") for r in neg))
    thin = [r for r in res["rows"] if r["n_book"] < 100]
    if thin:
        out.append("")
        out.append("Échantillons de carnet < 100 (trop petits pour p90 et médiane) : " +
                   ", ".join("%s/%s (n=%d)" % (r["sym"], "séance" if r["session"] else "hors", r["n_book"]) for r in thin))
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="data/live")
    ap.add_argument("--maker-fee-bps", type=float, default=1.25)
    ap.add_argument("--min-days", type=float, default=3.0)
    a = ap.parse_args(argv)
    res = analyse(a.data, a.maker_fee_bps)
    if not res["rows"]:
        print("Aucune donnée dans %s : lancer tools/recorder.py d'abord." % a.data)
        return 1
    print(report(res, a.maker_fee_bps, a.min_days))
    return 0


if __name__ == "__main__":
    sys.exit(main())
