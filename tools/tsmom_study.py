"""Famille E : momentum de séries temporelles sur les sous-jacents non crypto, modèle de coûts Polymarket.

Mesuré SUR LE SOUS-JACENT (séries de data/under/, voir MANIFEST.txt) ; ce qui reste à valider sur le perp lui-même est
listé dans CLAUDE.md (écart de prix perp / sous-jacent, hors séance, spread réel, funding réel).

Signal : à la fin du mois m, s = signe(P_m / P_{m-L} - 1). Position tenue le mois suivant. 'ls' : +1 / -1 ; 'lo' : +1 / 0.
Poids : 'equal' |w| = 1 ; 'volscaled' w = target / sigma (sigma annualisé des 12 derniers rendements mensuels, |w| <= 3).
Rendement net du mois m+1 d'un sleeve : w R_{m+1} - |w_m - w_{m-1}| x (4 + demi-spread + 2) bps - w x F_mois,
F_mois = 0.5 x 0.01 % / 8 h x 730 h = 0.45625 % (HYPOTHÈSE H_F : seule la composante d'intérêt fixe du funding non crypto ;
les longs paient, les shorts reçoivent). Liquidation : marge isolée, maintenance mmr = 0.5 / levier max, testée sur le chemin
quotidien du mois quand il existe (sinon fin de mois) ; liquidation = perte de tout le capital du sleeve pour le mois.
Portefeuille : sleeves de capital égal (moyenne des rendements nets).

Le sens du signal n'est JAMAIS retourné. stdlib uniquement. python tools/tsmom_study.py --mode search
"""
from __future__ import annotations

import argparse
import csv
import math
import os
import random
import statistics
import sys

FEE_BPS = 4.0
SLIP_BPS = 2.0
TARGET_VOL = 0.10
W_CAP = 3.0
FUND_MONTH = 0.5 * 0.0001 / 8.0 * 730.0  # 0.0045625 : 6.25e-6 par heure x 730 heures
NORM = statistics.NormalDist()


def ym(year, month):
    return year * 12 + month - 1


def ym_str(i):
    return "%04d-%02d" % (i // 12, i % 12 + 1)


class Inst:
    """prices : {mois: prix de fin de mois} ; path : {mois: [prix quotidiens positifs]} (vide pour une série mensuelle)."""

    def __init__(self, name, prices, path=None, spread_bps=2.0, max_lev=10.0, decision=True, robust=True):
        self.name, self.prices, self.path = name, prices, path or {}
        self.spread_bps, self.max_lev, self.decision, self.robust = spread_bps, max_lev, decision, robust
        self.R = {}
        for m, p in prices.items():
            q = prices.get(m - 1)
            if q is not None and q > 0 and p > 0:
                self.R[m] = p / q - 1.0

    @property
    def mmr(self):
        return 0.5 / self.max_lev

    @property
    def unit_cost(self):  # par unité de notionnel échangé
        return (FEE_BPS + self.spread_bps / 2.0 + SLIP_BPS) / 1e4

    def sigma(self, m):
        xs = [self.R.get(m - k) for k in range(12)]
        if any(x is None for x in xs):
            return None
        return statistics.stdev(xs) * math.sqrt(12.0)


def load_rows(path):
    with open(path) as f:
        return [(r["date"], float(r["value"])) for r in csv.DictReader(f)]


def build_inst(name, rows, monthly_source, **kw):
    prices, path = {}, {}
    for d, v in rows:
        m = ym(int(d[:4]), int(d[5:7]))
        prices[m] = v  # dernière observation du mois
        if not monthly_source and v > 0:
            path.setdefault(m, []).append(v)
    return Inst(name, prices, path, **kw)


def chain_dxy(old_rows, new_rows):
    """DTWEXM jusqu'à sa fin puis DTWEXBGS en enchaînant les rendements (proxys du DXY, pas le DXY d'ICE)."""
    last_old = old_rows[-1]
    base = dict(new_rows).get(last_old[0])
    if base is None:  # le jour de raccord n'existe pas dans la nouvelle série : premier jour postérieur
        nxt = [r for r in new_rows if r[0] > last_old[0]]
        base = nxt[0][1]
        new_rows = nxt
    out = list(old_rows)
    for d, v in new_rows:
        if d > last_old[0]:
            out.append((d, last_old[1] * v / base))
    return out


def load_universe(data):
    fr = lambda n: load_rows(os.path.join(data, n + ".csv"))
    u = [
        build_inst("SP500", fr("FRENCH_US_MKT_TR"), False, spread_bps=0.13, max_lev=50, decision=True, robust=True),
        build_inst("NAS100", fr("FRED_NASDAQ100"), False, spread_bps=0.32, max_lev=50, decision=True, robust=True),
        build_inst("WTI", fr("FRED_DCOILWTICO"), False, spread_bps=3.68, max_lev=20, decision=True, robust=True),
        build_inst("BRENT", fr("FRED_DCOILBRENTEU"), False, spread_bps=3.68, max_lev=20, decision=True, robust=True),
        build_inst("GOLD", fr("WB_GOLD"), True, spread_bps=0.24, max_lev=20, decision=True, robust=False),
        build_inst("SILVER", fr("WB_SILVER"), True, spread_bps=2.30, max_lev=20, decision=True, robust=False),
        build_inst("EURUSD", fr("FRED_DEXUSEU"), False, spread_bps=2.0, max_lev=10, decision=False, robust=False),
        build_inst("DXYproxy", chain_dxy(fr("FRED_DTWEXM"), fr("FRED_DTWEXBGS")), False, spread_bps=2.0, max_lev=10, decision=False, robust=False),
    ]
    return u


# ── moteur ────────────────────────────────────────────────────────────────

def raw_weight(inst, m, L, mode, weighting, target, signs=None):
    p0, p1 = inst.prices.get(m - L), inst.prices.get(m)
    if p0 is None or p1 is None or p0 <= 0 or p1 <= 0:
        return None
    sig = inst.sigma(m)
    if sig is None:
        return None
    if signs is not None:
        s = signs.get(m)
        if s is None:
            return None
    else:
        r = p1 / p0 - 1.0
        s = (1 if r > 0 else (-1 if r < 0 else 0))
        if mode == "lo" and s < 0:
            s = 0
    if weighting == "equal":
        return float(s)
    return s * min(W_CAP, target / max(sig, 1e-6))


def sleeve(inst, params, signs=None, lev=1.0, fund=True, target=TARGET_VOL):
    """Retourne {mois_du_rendement: dict(net, gross, cost, fund, w, liq)} pour chaque mois où une position est prise."""
    L, mode, weighting = params
    out = {}
    w_prev = 0.0
    months = sorted(inst.prices)
    for m in months:
        if (m + 1) not in inst.prices or (m + 1) not in inst.R:
            continue
        w0 = raw_weight(inst, m, L, mode, weighting, target, signs)
        if w0 is None:
            continue
        w = w0 * lev
        cap = 0.95 * inst.max_lev
        w = max(-cap, min(cap, w))
        R = inst.R[m + 1]
        gross = w * R
        cost = abs(w - w_prev) * inst.unit_cost
        fnd = w * FUND_MONTH if fund else 0.0
        net = gross - cost - fnd
        liq = False
        if w != 0.0:
            p0 = inst.prices[m]
            xs = [v / p0 for v in inst.path.get(m + 1, [])] + [1.0 + R]
            for x in xs:
                if 1.0 + w * (x - 1.0) <= inst.mmr * abs(w) * x:
                    liq = True
                    break
        if liq or net < -1.0:
            net, liq = -1.0, True
        out[m + 1] = {"net": net, "gross": gross, "cost": cost, "fund": fnd, "w": w, "liq": liq}
        w_prev = w
    return out


def portfolio(insts, params, signs=None, lev=1.0, fund=True, target=TARGET_VOL, subset=None):
    per = {}
    for inst in insts:
        if subset is not None and inst.name not in subset:
            continue
        per[inst.name] = sleeve(inst, params, (signs or {}).get(inst.name), lev, fund, target)
    months = sorted({m for d in per.values() for m in d})
    ret, long_c, short_c, liqs, cnt = {}, {}, {}, {}, {}
    for m in months:
        rows = [d[m] for d in per.values() if m in d]
        n = len(rows)
        ret[m] = sum(r["net"] for r in rows) / n
        long_c[m] = sum(r["net"] for r in rows if r["w"] > 0) / n
        short_c[m] = sum(r["net"] for r in rows if r["w"] < 0) / n
        liqs[m] = sum(1 for r in rows if r["liq"])
        cnt[m] = n
    return {"ret": ret, "long": long_c, "short": short_c, "liq": liqs, "n": cnt, "per": per}


def window(series, a, b):
    return [series[m] for m in sorted(series) if a <= m <= b]


def stats(rs):
    n = len(rs)
    if n < 2:
        return {"n": n, "mean": 0.0, "sd": 0.0, "sharpe": 0.0, "t": 0.0, "cagr": 0.0, "maxdd": 0.0, "worst": 0.0}
    mean = sum(rs) / n
    sd = statistics.stdev(rs)
    eq, peak, dd = 1.0, 1.0, 0.0
    for r in rs:
        eq *= 1.0 + r
        peak = max(peak, eq)
        dd = max(dd, (peak - eq) / peak)
    cagr = eq ** (12.0 / n) - 1.0 if eq > 0 else -1.0
    return {"n": n, "mean": mean, "sd": sd, "sharpe": mean / sd * math.sqrt(12.0) if sd > 0 else 0.0,
            "t": mean / (sd / math.sqrt(n)) if sd > 0 else 0.0, "cagr": cagr, "maxdd": dd, "worst": min(rs)}


def compound(rs):
    e = 1.0
    for r in rs:
        e *= 1.0 + r
    return e - 1.0


def deflated_sharpe(sr_hat_ann, sr_trials_ann, n_obs, skew, kurt):
    """Bailey, Lopez de Prado ; Sharpe mensuels par période (annualisés / racine de 12)."""
    f = 1.0 / math.sqrt(12.0)
    sr, trials = sr_hat_ann * f, [x * f for x in sr_trials_ann]
    var = statistics.pvariance(trials)
    g = 0.5772156649
    n_tr = len(trials)
    sr0 = math.sqrt(var) * ((1 - g) * NORM.inv_cdf(1 - 1.0 / n_tr) + g * NORM.inv_cdf(1 - 1.0 / (n_tr * math.e)))
    den = math.sqrt(max(1e-12, 1 - skew * sr + (kurt - 1) / 4.0 * sr * sr))
    return sr0 / f, NORM.cdf((sr - sr0) * math.sqrt(n_obs - 1) / den)


def moments(rs):
    n = len(rs)
    m = sum(rs) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in rs) / n)
    if sd == 0:
        return 0.0, 3.0
    return sum((x - m) ** 3 for x in rs) / n / sd ** 3, sum((x - m) ** 4 for x in rs) / n / sd ** 4


# ── baselines ─────────────────────────────────────────────────────────────

def sign_sequences(per, a, b):
    """Séquences de signes (+1, 0, -1) par instrument sur [a, b] (mois de rendement) et matrice de transition poolée."""
    seqs = {}
    for name, d in per.items():
        seqs[name] = [(m, (1 if r["w"] > 0 else (-1 if r["w"] < 0 else 0))) for m, r in sorted(d.items()) if a <= m <= b]
    trans = {s: {t: 0 for t in (-1, 0, 1)} for s in (-1, 0, 1)}
    marg = {-1: 0, 0: 0, 1: 0}
    for q in seqs.values():
        for (m0, s0), (m1, s1) in zip(q, q[1:]):
            if m1 == m0 + 1:
                trans[s0][s1] += 1
        for _, s in q:
            marg[s] += 1
    return seqs, trans, marg


def random_signs(insts, per, a, b, seed, subset=None):
    """Signes aléatoires d'une chaîne de Markov à 3 états (mêmes proportions et même rythme de changements que la
    stratégie sur [a, b]) ; clés : mois de SIGNAL (= mois de rendement - 1), comme `sleeve`."""
    rnd = random.Random(seed)
    seqs, trans, marg = sign_sequences(per, a, b)
    tot = sum(marg.values()) or 1
    out = {}
    for inst in insts:
        if inst.name not in seqs or not seqs[inst.name]:
            continue
        sig = {}
        prev = None
        for m, _ in seqs[inst.name]:
            if prev is None:
                s = rnd.choices((-1, 0, 1), weights=[marg[-1] + 1e-9, marg[0] + 1e-9, marg[1] + 1e-9])[0]
            else:
                w = trans[prev]
                tt = sum(w.values())
                s = rnd.choices((-1, 0, 1), weights=[w[-1] + 1e-9, w[0] + 1e-9, w[1] + 1e-9])[0] if tt else prev
            sig[m - 1] = s
            prev = s
        out[inst.name] = sig
    return out


def buy_and_hold(insts, subset=None):
    """Long 1x permanent (poids 1 chaque mois : le coût n'est payé qu'à l'entrée), funding payé."""
    class _P:
        pass
    ret = {}
    per = {}
    for inst in insts:
        if subset is not None and inst.name not in subset:
            continue
        d, w_prev = {}, 0.0
        for m in sorted(inst.prices):
            if (m + 1) not in inst.R or inst.sigma(m) is None:  # même date de départ que la stratégie (12 mois d'historique)
                continue
            R = inst.R[m + 1]
            cost = abs(1.0 - w_prev) * inst.unit_cost
            net = R - cost - FUND_MONTH
            d[m + 1] = {"net": net, "w": 1.0, "liq": False}
            w_prev = 1.0
        per[inst.name] = d
    months = sorted({m for d in per.values() for m in d})
    for m in months:
        rows = [d[m] for d in per.values() if m in d]
        ret[m] = sum(r["net"] for r in rows) / len(rows)
    return {"ret": ret, "per": per}


# ── protocole ─────────────────────────────────────────────────────────────

WINDOWS = {"train": (ym(1927, 1), ym(2004, 12)), "val": (ym(2005, 1), ym(2014, 12)), "test": (ym(2015, 1), ym(2100, 1))}
STRESS = {"2008": (ym(2008, 1), ym(2009, 3)), "2020": (ym(2020, 2), ym(2020, 12)), "2022": (ym(2022, 1), ym(2022, 12))}
GRID = [(L, mode, wt) for L in (1, 3, 6, 12) for mode in ("ls", "lo") for wt in ("equal", "volscaled")]


def label(p):
    return "L=%d %s %s" % p


def decade_table(ret):
    out = {}
    for m, r in ret.items():
        out.setdefault((m // 12) // 10 * 10, []).append(r)
    return out


def search(a, out):
    P = lambda s="": out.append(s)
    insts = load_universe(a.data)
    dec = [i for i in insts if i.decision]
    dec_names = {i.name for i in dec}
    robust = {i.name for i in dec if i.robust}
    P("FAMILLE E : momentum de séries temporelles sur sous-jacents non crypto. Mesuré SUR LE SOUS-JACENT.")
    P("Univers de décision : %s. Extras descriptifs : %s." % (", ".join(i.name for i in dec), ", ".join(i.name for i in insts if not i.decision)))
    for i in insts:
        ms = sorted(i.prices)
        P("  %-9s %s -> %s, %d mois, spread %.2f bps, levier max %gx, quotidien : %s" % (i.name, ym_str(ms[0]), ym_str(ms[-1]), len(ms), i.spread_bps, i.max_lev, "oui" if i.path else "NON (moyennes mensuelles)"))
    P("Fenêtres : train 1927-01 -> 2004-12, validation 2005-01 -> 2014-12, test 2015-01 -> fin. Funding H_F : +%.4f %% du notionnel par mois (longs paient, shorts reçoivent)." % (100 * FUND_MONTH))
    P("")
    # grille sur toute l'histoire (la stratégie n'utilise que le passé), évaluée par fenêtre
    runs = {g: portfolio(dec, g) for g in GRID}
    tr_a, tr_b = WINDOWS["train"]
    rows = [(g, stats(window(runs[g]["ret"], tr_a, tr_b))) for g in GRID]
    P("== Train : %d points testés" % len(rows))
    for g, s in sorted(rows, key=lambda x: -x[1]["sharpe"]):
        P("    %-22s Sharpe %+.2f, rendement moyen %+.3f %%/mois, CAGR %+.1f %%, maxDD %.0f %%, %d mois" % (label(g), s["sharpe"], 100 * s["mean"], 100 * s["cagr"], 100 * s["maxdd"], s["n"]))
    pos = sum(1 for _, s in rows if s["sharpe"] > 0)
    P("  points avec Sharpe net > 0 en train : %d/%d" % (pos, len(rows)))
    # Sharpe déflaté sur le train (informatif)
    best_g, best_s = max(rows, key=lambda x: x[1]["sharpe"])
    rs_best = window(runs[best_g]["ret"], tr_a, tr_b)
    sk, ku = moments(rs_best)
    sr0, dsr = deflated_sharpe(best_s["sharpe"], [s["sharpe"] for _, s in rows], len(rs_best), sk, ku)
    P("  Sharpe déflaté (16 essais) du meilleur point : SR0 attendu du meilleur d'une grille de bruit %.2f, DSR = %.3f (informatif)" % (sr0, dsr))
    top = sorted(rows, key=lambda x: -x[1]["sharpe"])[:3]
    P("")
    P("== Top 3 de train confirmés sur validation")
    va_a, va_b = WINDOWS["val"]
    best, bv = None, -1e18
    for g, s in top:
        v = stats(window(runs[g]["ret"], va_a, va_b))
        P("    %-22s train Sharpe %+.2f | validation Sharpe %+.2f (rendement moyen %+.3f %%/mois, %d mois)" % (label(g), s["sharpe"], v["sharpe"], 100 * v["mean"], v["n"]))
        if v["sharpe"] > bv:
            bv, best = v["sharpe"], g
    P("  Points évalués : %d (train) + 3 (validation) + 1 (test, une seule fois)." % len(rows))
    fin = best
    P("  Point final : %s" % label(fin))
    P("")
    te_a, te_b = WINDOWS["test"]
    R = runs[fin]
    st_tr, st_va, st_te = (stats(window(R["ret"], *WINDOWS[k])) for k in ("train", "val", "test"))
    # baselines
    bh = buy_and_hold(dec)
    ev = portfolio(dec, (1, "lo", "volscaled"), signs={i.name: {m: 1 for m in i.prices} for i in dec})  # long toujours, à volatilité égale
    P("== Résultat du point final (portefeuille équipondéré des 6, net de coûts et de funding H_F)")
    hdr = "  %-34s | %-30s | %-30s | %-30s"
    P(hdr % ("", "TRAIN 1927-2004", "VALIDATION 2005-2014", "TEST 2015-2026 (une seule fois)"))
    for nm, ser in (("Stratégie " + label(fin), R["ret"]), ("Buy and hold 1x (6 instruments)", bh["ret"]), ("Volatilité égale, long seul", ev["ret"])):
        cells = []
        for k in ("train", "val", "test"):
            s = stats(window(ser, *WINDOWS[k]))
            cells.append("Sharpe %+.2f CAGR %+5.1f%% DD %2.0f%% t %+.1f" % (s["sharpe"], 100 * s["cagr"], 100 * s["maxdd"], s["t"]))
        P(hdr % (nm, *cells))
    P("")
    # longs / shorts
    P("== Longs et shorts séparés (contribution moyenne au rendement mensuel du portefeuille, en %)")
    for k in ("train", "val", "test"):
        lg, sh = window(R["long"], *WINDOWS[k]), window(R["short"], *WINDOWS[k])
        P("    %-5s longs %+.3f %%/mois ; shorts %+.3f %%/mois ; mois avec liquidation(s) : %d" % (k, 100 * statistics.fmean(lg), 100 * statistics.fmean(sh), sum(1 for m in R["liq"] if WINDOWS[k][0] <= m <= WINDOWS[k][1] and R["liq"][m])))
    # par instrument sur le test
    P("")
    P("== Par instrument, TEST (Sharpe net mensuel du sleeve ; fraction de mois long / short / flat)")
    for name, d in R["per"].items():
        ms = [m for m in d if te_a <= m <= te_b]
        if len(ms) < 12:
            continue
        s = stats([d[m]["net"] for m in ms])
        fl = sum(1 for m in ms if d[m]["w"] > 0), sum(1 for m in ms if d[m]["w"] < 0), sum(1 for m in ms if d[m]["w"] == 0)
        P("    %-9s Sharpe %+.2f, CAGR %+.1f %%, %d mois : long %d, short %d, flat %d" % (name, s["sharpe"], 100 * s["cagr"], s["n"], *fl))
    # sous-ensemble robuste
    Rr = portfolio(dec, fin, subset=robust)
    P("")
    P("== Sous-ensemble robuste (séries quotidiennes : %s)" % ", ".join(sorted(robust)))
    for k in ("train", "val", "test"):
        s = stats(window(Rr["ret"], *WINDOWS[k]))
        P("    %-5s Sharpe %+.2f, CAGR %+.1f %%, maxDD %.0f %%" % (k, s["sharpe"], 100 * s["cagr"], 100 * s["maxdd"]))
    # sensibilité au funding
    Rf = portfolio(dec, fin, fund=False)
    P("")
    P("== Sensibilité : funding nul (H_F retirée)")
    for k in ("val", "test"):
        P("    %-5s Sharpe %+.2f (avec H_F : %+.2f)" % (k, stats(window(Rf["ret"], *WINDOWS[k]))["sharpe"], stats(window(R["ret"], *WINDOWS[k]))["sharpe"]))
    # régimes
    P("")
    P("== Régimes de stress (rendement composé, drawdown max) : stratégie / buy and hold / volatilité égale long seul")
    stress_pos = 0
    for nm, (x, y) in STRESS.items():
        a1, b1, c1 = (window(s, x, y) for s in (R["ret"], bh["ret"], ev["ret"]))
        P("    %-5s %+6.1f %% (DD %2.0f %%) / %+6.1f %% (DD %2.0f %%) / %+6.1f %% (DD %2.0f %%)" % (nm, 100 * compound(a1), 100 * stats(a1)["maxdd"], 100 * compound(b1), 100 * stats(b1)["maxdd"], 100 * compound(c1), 100 * stats(c1)["maxdd"]))
        stress_pos += 1 if compound(a1) > 0 else 0
    # décennies
    P("")
    P("== Par décennie : stratégie, buy and hold, volatilité égale long seul (Sharpe net ; >= 60 mois)")
    dt, db, de = decade_table(R["ret"]), decade_table(bh["ret"]), decade_table(ev["ret"])
    n_dec = n_dec_pos = 0
    for d in sorted(dt):
        if len(dt[d]) < 60:
            continue
        n_dec += 1
        s = stats(dt[d])
        n_dec_pos += 1 if compound(dt[d]) > 0 else 0
        P("    %ds : stratégie Sharpe %+.2f (CAGR %+.1f %%) | B&H %+.2f | vol égale %+.2f | %d mois" % (d, s["sharpe"], 100 * s["cagr"], stats(db.get(d, [0, 0]))["sharpe"], stats(de.get(d, [0, 0]))["sharpe"], s["n"]))
    # walk-forward
    P("")
    P("== Walk-forward (DESCRIPTIF : relit la fenêtre de test) : chaque janvier à partir de 2005, meilleur des 16 sur les données antérieures")
    wf = {}
    for y in range(2005, 2027):
        lo, hi = ym(y, 1), ym(y, 12)
        cand = [(stats([runs[g]["ret"][m] for m in sorted(runs[g]["ret"]) if m < lo])["sharpe"], g) for g in GRID if len([1 for m in runs[g]["ret"] if m < lo]) >= 120]
        if not cand:
            continue
        g = max(cand)[1]
        for m in range(lo, hi + 1):
            if m in runs[g]["ret"]:
                wf[m] = runs[g]["ret"][m]
    sw = stats(list(wf[m] for m in sorted(wf)))
    P("    série recousue 2005 -> fin : Sharpe %+.2f, CAGR %+.1f %%, maxDD %.0f %%, %d mois ; par régime :" % (sw["sharpe"], 100 * sw["cagr"], 100 * sw["maxdd"], sw["n"]))
    for nm, (x, y) in STRESS.items():
        P("      %-5s %+.1f %%" % (nm, 100 * compound(window(wf, x, y))))
    # aléatoire
    seqs_prob = sign_sequences(R["per"], te_a, te_b)
    draws = []
    for k in range(a.draws):
        sg = random_signs(dec, R["per"], te_a, te_b, 1000 + k)
        draws.append(stats(window(portfolio(dec, fin, signs=sg)["ret"], te_a, te_b))["sharpe"])
    beat = 100.0 * sum(1 for d in draws if st_te["sharpe"] > d) / len(draws)
    sd_ = sorted(draws)
    P("")
    P("== Signes aléatoires, même rythme et mêmes proportions (%d tirages, TEST) : Sharpe moyen %+.2f [p5 %+.2f, p95 %+.2f] ; la stratégie fait mieux que %.0f %% des tirages" % (len(draws), statistics.fmean(draws), sd_[len(sd_) // 20], sd_[len(sd_) * 19 // 20], beat))
    # levier
    P("")
    P("== Levier (point final, descriptif, non compté dans M) : validation | test : Sharpe, CAGR, drawdown max, pire mois, liquidations, coût en % de la marge par mois")
    for lab, kw in (("1x", dict(lev=1.0)), ("2x", dict(lev=2.0)), ("5x", dict(lev=5.0)), ("vol cible 5 %", dict(target=0.05)), ("vol cible 10 %", dict(target=0.10)), ("vol cible 20 %", dict(target=0.20))):
        res = portfolio(dec, fin, **kw)
        cells = []
        for k in ("val", "test"):
            rs = window(res["ret"], *WINDOWS[k])
            s = stats(rs)
            nliq = sum(v for m, v in res["liq"].items() if WINDOWS[k][0] <= m <= WINDOWS[k][1])
            ce = [r["cost"] for d in res["per"].values() for m, r in d.items() if WINDOWS[k][0] <= m <= WINDOWS[k][1]]
            cells.append("Sharpe %+.2f CAGR %+6.1f%% DD %3.0f%% pire %+6.1f%% liq %d coût %.3f%%/mois" % (s["sharpe"], 100 * s["cagr"], 100 * s["maxdd"], 100 * s["worst"], nliq, 100 * statistics.fmean(ce)))
        P("    %-14s %s | %s" % (lab, cells[0], cells[1]))
    # extras
    ex = [i for i in insts if not i.decision]
    Re = portfolio(ex, fin)
    P("")
    P("== Extras non listés chez Polymarket (EUR/USD, proxy DXY), mêmes paramètres, descriptif")
    for k in ("train", "val", "test"):
        s = stats(window(Re["ret"], *WINDOWS[k]))
        P("    %-5s Sharpe %+.2f, CAGR %+.1f %%, %d mois" % (k, s["sharpe"], 100 * s["cagr"], s["n"]))
    # verdict
    t = st_te["t"]
    p_val = 1 - NORM.cdf(t)
    r_test = stats(window(Rr["ret"], te_a, te_b))
    lg_te, sh_te = statistics.fmean(window(R["long"], te_a, te_b)), statistics.fmean(window(R["short"], te_a, te_b))
    ev_te = stats(window(ev["ret"], te_a, te_b))["sharpe"]
    crit = []
    crit.append(("1. Sharpe net > 0 en validation ET test", st_va["sharpe"] > 0 and st_te["sharpe"] > 0, "validation %+.2f, test %+.2f" % (st_va["sharpe"], st_te["sharpe"])))
    crit.append(("2. Bonferroni (M=8) significatif en test", p_val * a.m_tests < 0.05, "t = %.2f, p x 8 = %.4f" % (t, min(1, p_val * a.m_tests))))
    crit.append(("3. robustesse : >= 2/3 stress positifs ET >= 60 %% des décennies positives", stress_pos >= 2 and n_dec > 0 and n_dec_pos / n_dec >= 0.6, "stress %d/3, décennies %d/%d" % (stress_pos, n_dec_pos, n_dec)))
    crit.append(("4. bat >= 75 %% des signes aléatoires (test)", beat >= 75, "%.0f %%" % beat))
    crit.append(("5. Sharpe test > volatilité égale long seul", st_te["sharpe"] > ev_te, "%+.2f contre %+.2f" % (st_te["sharpe"], ev_te)))
    crit.append(("6. longs ET shorts >= 0 en test (variantes ls)", fin[1] == "lo" or (lg_te >= 0 and sh_te >= 0), "longs %+.3f, shorts %+.3f %%/mois" % (100 * lg_te, 100 * sh_te)))
    crit.append(("7. sous-ensemble robuste : Sharpe > 0 en test", r_test["sharpe"] > 0, "%+.2f" % r_test["sharpe"]))
    P("")
    P("== VERDICT (critères pré-enregistrés)")
    for nm, ok, det in crit:
        P("    [%s] %s : %s" % ("OUI" if ok else "NON", nm.replace("%%", "%"), det))
    allok = all(c[1] for c in crit)
    P("  RÉSULTAT : %s" % ("POSITIF selon tous les critères sur le sous-jacent : reste à valider sur le perp (écart de prix, hors séance, funding réel, spread)" if allok else "NÉGATIF ou NON CONCLUANT : aucun code d'exécution"))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", default="search")
    ap.add_argument("--data", default="data/under")
    ap.add_argument("--draws", type=int, default=300)
    ap.add_argument("--m-tests", type=int, default=8)
    ap.add_argument("--out", default="results/tsmom_report.txt")
    a = ap.parse_args(argv)
    out = []
    search(a, out)
    text = "\n".join(out) + "\n"
    print(text)
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(text)


if __name__ == "__main__":
    main()
