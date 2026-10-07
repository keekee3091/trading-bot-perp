"""Diagnostic du funding réel par instrument et par catégorie, sans stratégie : le carry couvert vaut-il une étude ?

Lit data/<SYM>_funding.csv (taux horaire, positif : les longs paient les shorts) et la catégorie dans
data/universe_survey.csv. Doc (perps/learn-about-trading/funding) :
  F_8h = scale x (mean_P + clamp(0.0001 - mean_P, +/- 0.0005)),  scale = 1.0 crypto, 0.5 sinon
  => avec une prime nulle le taux vaut scale x 0.0001 / 8 par heure : 1.25e-5 (crypto) ou 6.25e-6
     (non-crypto), soit 11.0 % ou 5.5 % par an payés par les longs. Les taux publiés incluent déjà le
     scale : on ne le réapplique pas.

Carry couvert : perp d'un côté, jambe de couverture ailleurs (spot crypto, future, ETF ou action),
delta neutre. Si le funding moyen est positif on est short perp (reçoit) + long jambe de couverture.
Coût d'un aller-retour (ouvrir puis fermer les deux jambes), en bps du notionnel. HYPOTHÈSES, à
remplacer par des chiffres réels ; modifiables ici :
  jambe perp : taker 4 bps + demi-spread 1 + slippage 2, par côté, soit 14 bps l'aller-retour
  jambe de couverture, aller-retour, par catégorie :
    crypto 23 bps (spot ailleurs, taker 10 bps + demi-spread 0.5 + slippage 1, par côté)
    index 6 bps (future sur indice : commission et spread faibles)
    commodity 10 bps (future matières premières)
    equity 8 bps (action : pas de commission, spread + slippage)
Non chiffré : coût d'emprunt si le funding est négatif (short de la jambe de couverture), roll des
futures, base perp/jambe, risque de liquidation de la jambe perp, transfert de collatéral entre deux
plateformes, coût du capital immobilisé sur deux plateformes. Tous ces éléments rendent le carry réel
PIRE que le chiffre affiché.

stdlib uniquement : python tools/funding_diagnostic.py [SYM ...]   (défaut : le panel)
"""
import csv
import statistics
import sys

PERP_RT_BPS = 2 * (4.0 + 1.0 + 2.0)
HEDGE_RT_BPS = {"crypto": 23.0, "index": 6.0, "commodity": 10.0, "equity": 8.0}
HOURS_YEAR = 24 * 365
RISK_FREE_PCT = 4.0  # repère de rendement sans risque du capital immobilisé, hypothèse


def categories():
    with open("data/universe_survey.csv") as f:
        return {r["symbol"]: r["category"] for r in csv.DictReader(f)}


def load(sym):
    with open("data/%s_funding.csv" % sym) as f:
        return [float(r["rate"]) for r in csv.DictReader(f)]


def analyse(sym, cat):
    r = load(sym)
    n = len(r)
    mean, med, sd = statistics.fmean(r), statistics.median(r), statistics.pstdev(r)
    pos = 100.0 * sum(1 for x in r if x > 0) / n
    sgn = 1 if mean > 0 else -1
    cost = PERP_RT_BPS + HEDGE_RT_BPS.get(cat, 23.0)
    per_day = abs(mean) * 24 * 1e4
    daily = [sum(r[i:i + 24]) for i in range(0, n - 23, 24)]
    losing = 100.0 * sum(1 for x in daily if sgn * x < 0) / len(daily)
    net_90 = (abs(mean) * 24 * 90 * 1e4 - cost) / 90 * 365 / 100
    net_365 = (abs(mean) * 24 * 365 * 1e4 - cost) / 365 * 365 / 100
    return {
        "sym": sym, "cat": cat, "hours": n, "mean": mean, "median": med, "sd": sd, "pos": pos,
        "ann": mean * HOURS_YEAR * 100, "side": "short perp" if mean > 0 else "long perp",
        "cost": cost, "days_cover": cost / per_day if per_day else float("inf"), "losing": losing,
        "net90": net_90, "net365": net_365,
    }


def main(syms):
    cats = categories()
    rows = [analyse(s, cats.get(s, "crypto")) for s in syms]
    print("Hypothèses de coût aller-retour : jambe perp %.0f bps + couverture par catégorie %s" % (PERP_RT_BPS, HEDGE_RT_BPS))
    print("Repère sans risque du capital : %.1f %% par an (hypothèse)\n" % RISK_FREE_PCT)
    hdr = "%-11s %-9s %6s %10s %10s %10s %6s %9s %7s %8s %9s %9s"
    print(hdr % ("instrument", "catégorie", "heures", "moy./h", "médiane/h", "écart-type", "%h>0", "annualisé", "coût", "jours", "net 90 j", "net 365 j"))
    print(hdr % ("", "", "", "", "", "", "", "% notion.", "bps", "amortir", "% annuel", "% annuel"))
    for x in rows:
        print("%-11s %-9s %6d %10.2e %10.2e %10.2e %6.1f %+9.2f %7.0f %8.0f %+9.2f %+9.2f" % (
            x["sym"], x["cat"], x["hours"], x["mean"], x["median"], x["sd"], x["pos"], x["ann"], x["cost"],
            x["days_cover"], x["net90"], x["net365"]))
    print("\nPar catégorie (moyenne des instruments) :")
    print("%-10s %4s %10s %7s %9s %9s %12s" % ("catégorie", "n", "annualisé%", "%h>0", "net 90 j", "net 365 j", "côté"))
    for cat in ("crypto", "index", "commodity", "equity"):
        g = [x for x in rows if x["cat"] == cat]
        if not g:
            continue
        mean_ann = statistics.fmean(x["ann"] for x in g)
        print("%-10s %4d %+10.2f %7.1f %+9.2f %+9.2f %12s" % (
            cat, len(g), mean_ann, statistics.fmean(x["pos"] for x in g), statistics.fmean(x["net90"] for x in g),
            statistics.fmean(x["net365"] for x in g), "short perp" if mean_ann > 0 else "long perp"))
    print("\nLecture : 'net' = rendement annualisé du notionnel après 1 aller-retour, détention de 90 ou 365 jours,"
          " AVANT les risques non chiffrés (voir l'en-tête) et avant le coût du capital (repère %.1f %%)." % RISK_FREE_PCT)
    print("Rendement sur capital : un carry couvert immobilise du capital sur DEUX plateformes (marge du perp + valeur de la jambe),"
          " donc le rendement par unité de capital est inférieur d'un facteur ~ 1 / (1 + marge/notionnel).")


if __name__ == "__main__":
    default = open("results/panel_symbols.txt").read().strip().split(",")
    main(sys.argv[1:] or default)
