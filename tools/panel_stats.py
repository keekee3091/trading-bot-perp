"""Statistiques de décision du panel : Bonferroni, Sharpe déflaté, levier de Kelly hors échantillon.

Entrées (écrites par perp_panel) : results/panel_train_sweep.csv, results/panel_returns_{train,val,test}.csv
(mode search), results/panel_lev1_{val,test}.csv (mode leverage, levier fixe 1x).
stdlib uniquement : python tools/panel_stats.py [--trials-m 4]

1. Test hors échantillon : t = moyenne / (écart-type / racine n) des rendements horaires du portefeuille,
   p unilatérale (normale), puis Bonferroni : p x M, M = nombre total d'évaluations de test d'une
   hypothèse d'edge (voir CLAUDE.md). Les rendements horaires sont supposés indépendants (optimiste
   s'ils sont autocorrélés).
2. Sharpe déflaté (Bailey, Lopez de Prado) sur le train : probabilité que le Sharpe du meilleur point
   dépasse ce que donnerait la meilleure de N grilles de bruit. Critère informatif, pas de décision.
3. Kelly : f* = mu / sigma^2 (gaussien) et levier empirique qui maximise la moyenne de log(1 + L r)
   sur les rendements réalisés (capte les queues épaisses et la ruine), avec bootstrap par blocs de
   24 h. mu <= 0 => f* <= 0 : pas de levier.
"""
import csv
import math
import random
import statistics
import sys

N = statistics.NormalDist()
HOURS = 8760.0


def read_returns(path, col="port_ret"):
    with open(path) as f:
        return [float(r[col]) for r in csv.DictReader(f)]


def moments(r):
    n = len(r)
    m = sum(r) / n
    v = sum((x - m) ** 2 for x in r) / (n - 1)
    sd = math.sqrt(v)
    skew = sum((x - m) ** 3 for x in r) / n / (sd ** 3) if sd > 0 else 0.0
    kurt = sum((x - m) ** 4 for x in r) / n / (sd ** 4) if sd > 0 else 3.0
    return n, m, sd, skew, kurt


def tstat(r):
    n, m, sd, _, _ = moments(r)
    return m / (sd / math.sqrt(n)) if sd > 0 else 0.0


def sharpe_ann(r):
    n, m, sd, _, _ = moments(r)
    return m / sd * math.sqrt(HOURS) if sd > 0 else 0.0


def deflated_sharpe(sr_hat, sr_trials, n_obs, skew, kurt):
    """Tous les Sharpe en unités par période (horaire). sr_trials : Sharpe des N essais."""
    n_tr = len(sr_trials)
    var = statistics.pvariance(sr_trials)
    g = 0.5772156649
    sr0 = math.sqrt(var) * ((1 - g) * N.inv_cdf(1 - 1.0 / n_tr) + g * N.inv_cdf(1 - 1.0 / (n_tr * math.e)))
    denom = math.sqrt(max(1e-12, 1 - skew * sr_hat + (kurt - 1) / 4.0 * sr_hat ** 2))
    return sr0, N.cdf((sr_hat - sr0) * math.sqrt(n_obs - 1) / denom)


def kelly_gauss(r):
    n, m, sd, _, _ = moments(r)
    return m / (sd * sd) if sd > 0 else 0.0


def kelly_empirical(r, lmax=30.0, step=0.1):
    """Levier L dans [0, lmax] maximisant la moyenne de log(1 + L r) ; -inf si 1 + L r <= 0 (ruine)."""
    best_l, best_g, g0 = 0.0, 0.0, 0.0
    L = step
    while L <= lmax + 1e-9:
        s = 0.0
        ok = True
        for x in r:
            y = 1 + L * x
            if y <= 0:
                ok = False
                break
            s += math.log(y)
        if not ok:
            break  # au-delà, la ruine est certaine sur cet échantillon
        g = s / len(r)
        if g > best_g:
            best_l, best_g = L, g
        L += step
    return best_l, best_g


def block_bootstrap(r, fn, reps=300, block=24, seed=7):
    rnd = random.Random(seed)
    n = len(r)
    out = []
    for _ in range(reps):
        s = []
        while len(s) < n:
            i = rnd.randrange(0, max(1, n - block))
            s.extend(r[i:i + block])
        out.append(fn(s[:n]))
    out.sort()
    return out[int(0.05 * reps)], out[int(0.5 * reps)], out[int(0.95 * reps)]


def section_test(m_tests):
    print("== 1. Test hors échantillon, Bonferroni (M = %d)" % m_tests)
    for name, path in (("validation", "results/panel_returns_val.csv"), ("test", "results/panel_returns_test.csv")):
        r = read_returns(path)
        n, mean, sd, sk, ku = moments(r)
        t = tstat(r)
        p = 1 - N.cdf(t)
        print("  %-10s n=%d h, Sharpe annualisé %+.2f, t = %+.2f, p unilatérale = %.4f, p x M = %.4f -> %s" % (
            name, n, sharpe_ann(r), t, p, min(1.0, p * m_tests),
            "significatif" if p * m_tests < 0.05 else "NON significatif"))
    r = read_returns("results/panel_returns_test.csv")
    mk = read_returns("results/panel_returns_test.csv", "mkt_ret")
    print("  test : rendement cumulé stratégie %+.2f %%, marché équipondéré %+.2f %%" % (
        100 * (math.prod(1 + x for x in r) - 1), 100 * (math.prod(1 + x for x in mk) - 1)))


def section_dsr():
    print("\n== 2. Sharpe déflaté sur le train (64 essais, informatif)")
    with open("results/panel_train_sweep.csv") as f:
        rows = list(csv.DictReader(f))
    srs = [float(r["sharpe"]) / math.sqrt(HOURS) for r in rows]
    hours = int(float(rows[0]["hours"]))
    best = max(srs)
    pos = sum(1 for x in srs if x > 0)
    r = read_returns("results/panel_returns_train.csv")
    _, _, _, sk, ku = moments(r)  # asymétrie et kurtosis du point final, proxy pour le meilleur point
    sr0, dsr = deflated_sharpe(best, srs, hours, sk, ku)
    print("  %d essais, %d avec Sharpe > 0 ; meilleur Sharpe annualisé %.2f ; Sharpe annualisé attendu du meilleur"
          " d'une grille de bruit (SR0) %.2f ; DSR = %.3f" % (len(srs), pos, best * math.sqrt(HOURS), sr0 * math.sqrt(HOURS), dsr))
    print("  lecture : DSR < 0.95 => le meilleur point n'est pas distinguable de la chance de la sélection.")


def section_kelly():
    print("\n== 3. Levier de Kelly hors échantillon (rendements horaires du portefeuille à levier fixe 1x)")
    sets = {"validation": read_returns("results/panel_lev1_val.csv"), "test": read_returns("results/panel_lev1_test.csv")}
    sets["val+test"] = sets["validation"] + sets["test"]
    for name, r in sets.items():
        n, mean, sd, sk, ku = moments(r)
        fg = kelly_gauss(r)
        fe, ge = kelly_empirical(r)
        lo, med, hi = block_bootstrap(r, kelly_gauss)
        se = 1.0 / (sd * math.sqrt(n)) if sd > 0 else float("nan")
        print("  %-10s n=%d h | mu/h %+.2e, sigma/h %.2e, Sharpe ann. %+.2f | asymétrie %+.2f, kurtosis %.1f, pire heure %+.2f %%"
              % (name, n, mean, sd, sharpe_ann(r), sk, ku, 100 * min(r)))
        print("             f* gaussien = mu/sigma^2 = %+.1f (erreur type ~ %.1f, bootstrap 90 %% : [%+.1f, %+.1f]) ; "
              "levier empirique optimal = %.1f (croissance %.2e par heure) ; ruine si L > %.0f"
              % (fg, se, lo, hi, fe, ge, 1.0 / abs(min(r)) if min(r) < 0 else float("inf")))
        if mean <= 0:
            print("             mu <= 0 : edge hors échantillon NÉGATIF, f* <= 0 => le levier n'est pas une solution.")
        elif lo <= 0:
            print("             mu > 0 mais l'intervalle de f* inclut 0 : edge non distinguable de zéro, aucun levier justifiable.")
        else:
            print("             f* strictement positif sur 90 %% des rééchantillonnages : un levier fractionnaire de Kelly (<= 1/2 f*) serait défendable.")


if __name__ == "__main__":
    m = 4
    if "--trials-m" in sys.argv:
        m = int(sys.argv[sys.argv.index("--trials-m") + 1])
    section_test(m)
    section_dsr()
    section_kelly()
