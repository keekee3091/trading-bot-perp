"""Famille C : la prime mark/index converge-t-elle ? Étude d'événements, preneur de liquidité (taker).

DONNÉES : l'API ne fournit AUCUN historique du prix index (voir CLAUDE.md). La seule trace historique de la
prime est le funding publié. Par la formule de la doc (perps/learn-about-trading/funding) :
    F_8h = scale x (P + clamp(0.0001 - P, +/-0.0005)),   FR_heure = F_8h / 8,   scale = 1 crypto, 0.5 sinon
où P est la prime moyenne de l'heure (impact-prices vs index, nulle tant que l'index reste entre l'impact bid et
l'impact ask). Inversion de u = F_8h / scale :
    u == 0.0001            -> P dans [-4, +6] bps : NON OBSERVABLE (censuré)
    u >  0.0001            -> P = u + 0.0005  (> +6 bps)
    u <  0.0001            -> P = u - 0.0005  (< -4 bps)
Le taux publié à l'heure H couvre la fenêtre [H-1, H) ; on le connaît à H. P est donc une prime HORAIRE MOYENNE
observable seulement quand elle sort de la bande : c'est précisément la zone qui intéresse (dislocation).

STRATÉGIE (fixée avant résultat, voir CLAUDE.md) : à la publication, si P > theta (perp cher) on VEND le perp, si
P < -theta (perp bon marché) on ACHÈTE ; sortie H heures plus tard ; ordres au marché (taker) ; une position à la
fois par instrument. Le sens n'est JAMAIS retourné pour améliorer un résultat.
Coût aller-retour = 2 x frais taker 4 bps + 2 x demi-spread + 2 x slippage 2 bps, plus le funding réellement
payé ou reçu pendant la détention. Prix : ouverture des bougies 1m (entrée à la minute de publication, sortie
H heures plus tard) ; bougies sans trade remplies (prix périmé : limite connue).

stdlib uniquement. python tools/premium_study.py --mode search
"""
from __future__ import annotations

import argparse
import bisect
import calendar
import csv
import glob
import math
import os
import random
import statistics
import sys
import time

BASE_U = 0.0001
EPS = 1e-9
FEE_BPS = 4.0
SLIP_BPS = 2.0
HOUR_MS = 3_600_000
MIN_MS = 60_000


def implied_premium(rate, scale):
    """Prime horaire moyenne déduite du taux de funding publié ; None si censurée (dans la bande de l'intérêt fixe)."""
    u = 8.0 * rate / scale
    if u > BASE_U + EPS:
        return u + 0.0005
    if u < BASE_U - EPS:
        return u - 0.0005
    return None


class Inst:
    """Série 1m d'un instrument + funding. t0 : ts (ms) de la première bougie ; les listes sont indexées par minute."""

    def __init__(self, sym, scale, t0, opens, highs, lows, funding, spread_bps=2.0, max_lev=10.0, category="equity"):
        self.sym, self.scale, self.t0 = sym, scale, t0
        self.open, self.high, self.low = opens, highs, lows
        self.funding = funding  # [(ts_ms, rate)] trié
        self.fts = [ts for ts, _ in funding]
        self.fcum = [0.0]
        for _, r in funding:
            self.fcum.append(self.fcum[-1] + r)
        self.spread_bps = spread_bps
        self.max_lev = max_lev
        self.category = category
        self.n = len(opens)

    def idx(self, ts_ms):
        return int((ts_ms - self.t0) // MIN_MS)

    @property
    def cost_bps(self):
        return 2 * FEE_BPS + self.spread_bps + 2 * SLIP_BPS  # 2 x demi-spread = spread

    @property
    def mmr(self):
        return 0.5 / self.max_lev


def load_inst(sym, data_dir="data", spread_map=None, cat_map=None, maxlev_map=None):
    cat = (cat_map or {}).get(sym, "equity")
    with open(os.path.join(data_dir, sym + "_1m.csv")) as f:
        rows = list(csv.DictReader(f))
    t0 = int(rows[0]["ts"])
    opens = [float(r["open"]) for r in rows]
    highs = [float(r["high"]) for r in rows]
    lows = [float(r["low"]) for r in rows]
    with open(os.path.join(data_dir, sym + "_funding.csv")) as f:
        fund = [(int(r["ts"]), float(r["rate"])) for r in csv.DictReader(f)]
    return Inst(sym, 1.0 if cat == "crypto" else 0.5, t0, opens, highs, lows, fund,
                (spread_map or {}).get(sym, 2.0), (maxlev_map or {}).get(sym, 10.0), cat)


def events(inst, theta_bps, w0_ms, w1_ms):
    """Dislocations observables dans [w0, w1) : [(ts_ms, P, side)] ; side = -1 vend (P > theta), +1 achète."""
    th = theta_bps / 1e4
    out = []
    for ts, rate in inst.funding:
        if not (w0_ms <= ts < w1_ms):
            continue
        p = implied_premium(rate, inst.scale)
        if p is None:
            continue
        if p > th:
            out.append((ts, p, -1))
        elif p < -th:
            out.append((ts, p, +1))
    return out


def funding_between(inst, a_ms, b_ms):
    """Somme des taux publiés dans ]a, b] (sommes cumulées : O(log n))."""
    return inst.fcum[bisect.bisect_right(inst.fts, b_ms)] - inst.fcum[bisect.bisect_right(inst.fts, a_ms)]


def trade(inst, ts_ms, side, hold_h, leverage=1.0):
    """Un aller-retour. Retourne None si hors données, sinon dict(ret_bps notionnel net, margin_ret, liq, ...)."""
    i0 = inst.idx(ts_ms)
    i1 = i0 + int(hold_h * 60)
    if i0 < 0 or i1 >= inst.n:
        return None
    half = inst.spread_bps / 2 / 1e4
    slip = SLIP_BPS / 1e4
    fee = FEE_BPS / 1e4
    p_in = inst.open[i0] * (1 + side * (half + slip))   # on achète plus cher, on vend moins cher
    p_out = inst.open[i1] * (1 - side * (half + slip))
    gross = side * (p_out / p_in - 1)
    fund = -side * funding_between(inst, ts_ms, ts_ms + int(hold_h * HOUR_MS))  # un long paie un taux positif
    ret = gross - 2 * fee + fund
    # liquidation (marge isolée) : distance exacte selon le côté
    m = inst.mmr
    liq = False
    if leverage > 1.0:
        if side > 0:
            d = (1.0 / leverage - m) / (1.0 - m)
            liq = min(inst.low[i0:i1 + 1]) <= p_in * (1 - d)
        else:
            d = (1.0 / leverage - m) / (1.0 + m)
            liq = max(inst.high[i0:i1 + 1]) >= p_in * (1 + d)
    margin_ret = -1.0 if liq else leverage * ret
    return {"ts": ts_ms, "side": side, "ret_bps": ret * 1e4, "margin_ret": margin_ret, "liq": liq, "sym": inst.sym}


def run_strategy(insts, theta_bps, hold_h, w0_ms, w1_ms, leverage=1.0):
    trades = []
    for inst in insts:
        busy_until = 0
        for ts, p, side in events(inst, theta_bps, w0_ms, w1_ms):
            if ts < busy_until:
                continue
            t = trade(inst, ts, side, hold_h, leverage)
            if t is None:
                continue
            t["premium_bps"] = p * 1e4
            trades.append(t)
            busy_until = ts + int(hold_h * HOUR_MS)
    return trades


def random_baseline(insts, counts, hold_h, w0_ms, w1_ms, draws, seed):
    """Même nombre d'entrées par instrument, à des heures pleines tirées au hasard, côté au hasard, mêmes coûts et
    même détention. Retourne la liste des rendements moyens (bps) par tirage et ceux des longs / des shorts."""
    rnd = random.Random(seed)
    out = []
    for _ in range(draws):
        rets = []
        for inst in insts:
            n = counts.get(inst.sym, 0)
            if n == 0:
                continue
            first = (max(w0_ms, inst.t0) // HOUR_MS + 1) * HOUR_MS
            last = min(w1_ms, inst.t0 + inst.n * MIN_MS) - int(hold_h * HOUR_MS)  # fin des données
            slots = list(range(first, last, HOUR_MS))
            rnd.shuffle(slots)
            taken = []
            for s in slots:
                if len(taken) >= n:
                    break
                if all(abs(s - x) >= hold_h * HOUR_MS for x in taken):
                    t = trade(inst, s, rnd.choice((-1, 1)), hold_h)
                    if t is not None:
                        taken.append(s)
                        rets.append(t["ret_bps"])
        if rets:
            out.append(sum(rets) / len(rets))
    return out


def stats(trades):
    n = len(trades)
    if n == 0:
        return {"n": 0, "mean": 0.0, "t": 0.0, "win": 0.0}
    r = [t["ret_bps"] for t in trades]
    m = sum(r) / n
    sd = statistics.pstdev(r) * math.sqrt(n / (n - 1)) if n > 1 else 0.0
    return {"n": n, "mean": m, "t": m / (sd / math.sqrt(n)) if sd > 0 else 0.0, "win": sum(1 for x in r if x > 0) / n}


def by_side(trades):
    return stats([t for t in trades if t["side"] > 0]), stats([t for t in trades if t["side"] < 0])


def date_ms(s):
    y, m, d = (int(x) for x in s.split("-"))
    return calendar.timegm((y, m, d, 0, 0, 0)) * 1000


def normal_cdf(x):
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


def load_context(data_dir):
    cats, lev = {}, {}
    sp = {}
    with open(os.path.join(data_dir, "universe_survey.csv")) as f:
        for r in csv.DictReader(f):
            cats[r["symbol"]] = r["category"]
            lev[r["symbol"]] = float(r["max_leverage"])
    probe = os.path.join(data_dir, "live_probe")
    vals = {}
    import json
    for p in glob.glob(os.path.join(probe, "*", "books.jsonl")):
        with open(p, encoding="utf-8") as f:
            for line in f:
                try:
                    b = json.loads(line)
                except ValueError:
                    continue
                vals.setdefault(b["sym"], []).append(b["spread_bps"])
    for s, v in vals.items():
        sp[s] = statistics.median(v)
    return cats, lev, sp


def convergence_profile(insts, theta_bps, until_ms):
    """Pour chaque dislocation |P| > theta (avant until_ms) : la prime des heures suivantes. Retourne les temps de
    retour dans la bande (heures, plafonnés à 48), la part retournée en bande après k heures, |P| moyen observable."""
    th = theta_bps / 1e4
    back, n_ev = [], 0
    still = {1: 0, 4: 0, 12: 0, 24: 0}
    flipped = 0
    absp = {1: [], 4: [], 12: []}
    for inst in insts:
        pr = [(ts, implied_premium(r, inst.scale)) for ts, r in inst.funding]
        for j, (ts, p) in enumerate(pr):
            if ts >= until_ms or p is None or abs(p) <= th:
                continue
            n_ev += 1
            t_back = 48
            for k in range(1, 49):
                if j + k >= len(pr):
                    t_back = None
                    break
                q = pr[j + k][1]
                if k in absp and q is not None:
                    absp[k].append(abs(q))
                if q is None and t_back == 48:
                    t_back = k
                    break
                if q is not None and q * p < 0 and abs(q) > th:
                    flipped += 1
                    break
            if t_back is not None:
                back.append(t_back)
            for k in still:
                if j + k < len(pr) and pr[j + k][1] is not None:
                    still[k] += 1
    return n_ev, back, still, absp, flipped


def search(a, out):
    cats, lev, sp = load_context(a.data)
    syms = sorted(os.path.basename(p)[:-7] for p in glob.glob(os.path.join(a.data, "*_1m.csv")))
    syms = [s for s in syms if os.path.exists(os.path.join(a.data, s + "_funding.csv"))]
    insts = [load_inst(s, a.data, sp, cats, lev) for s in syms]
    t_tr, t_va = date_ms(a.train_end), date_ms(a.val_end)
    w = {"train": (0, t_tr), "val": (t_tr, t_va), "test": (t_va, 10 ** 15)}
    thetas, holds = [10, 20, 40], [1, 4, 12]
    P = lambda s="": out.append(s)
    P("FAMILLE C (proxy funding) : la prime horaire déduite du funding converge-t-elle ? Stratégie taker.")
    P("Instruments (%d) : %s" % (len(insts), ", ".join(i.sym for i in insts)))
    P("Fenêtres UTC : train < %s, validation %s -> %s, test >= %s. Grille : theta %s bps x H %s h = %d points ; un seul jeu pour tous."
      % (a.train_end, a.train_end, a.val_end, a.val_end, thetas, holds, len(thetas) * len(holds)))
    P("Coût aller-retour par instrument = 8 bps de frais + spread médian du relevé + 4 bps de slippage ; funding réel inclus.")
    P("")
    # prime observable : combien d'heures, quelle ampleur
    P("== Fréquence et ampleur des dislocations observables (heures hors bande de l'intérêt fixe), toutes fenêtres")
    tot_h = tot_obs = tot_big = 0
    for inst in insts:
        ps = [implied_premium(r, inst.scale) for ts, r in inst.funding]
        obs = [p for p in ps if p is not None]
        big = [p for p in obs if abs(p) > 0.0010]
        tot_h += len(ps)
        tot_obs += len(obs)
        tot_big += len(big)
    P("  %d heures, %d observables (%.1f %%), %d avec |P| > 10 bps (%.2f %%)" % (tot_h, tot_obs, 100 * tot_obs / tot_h, tot_big, 100 * tot_big / tot_h))
    # persistance de la prime horaire observable : lag 1 h
    pairs = []
    for inst in insts:
        prev = None
        for ts, r in inst.funding:
            p = implied_premium(r, inst.scale)
            if prev is not None and p is not None and prev[1] is not None and ts - prev[0] <= HOUR_MS * 1.5:
                pairs.append((prev[1], p))
            prev = (ts, p)
    if len(pairs) > 30:
        xs, ys = [x for x, _ in pairs], [y for _, y in pairs]
        P("  persistance : corrélation de la prime d'une heure observable avec la suivante (n=%d) : %.3f" % (len(pairs), statistics.correlation(xs, ys)))
    P("")
    # convergence de la prime (fenêtres train + validation seulement : le test n'est pas regardé ici)
    ev, back, still, absp, flipped = convergence_profile(insts, 20, t_va)
    P("== Convergence de la prime horaire après une dislocation |P| > 20 bps (train + validation seulement)")
    P("  %d dislocations ; la prime est encore hors bande (observable) après 1 h : %.0f %%, 4 h : %.0f %%, 12 h : %.0f %%, 24 h : %.0f %%"
      % (ev, 100 * still[1] / ev, 100 * still[4] / ev, 100 * still[12] / ev, 100 * still[24] / ev))
    if back:
        sb = sorted(back)
        P("  temps médian avant retour dans la bande [-4, +6] bps : %d h (plafonné à 48 h ; p25 %d h, p75 %d h)" % (sb[len(sb) // 2], sb[len(sb) // 4], sb[3 * len(sb) // 4]))
    for k in (1, 4, 12):
        if absp[k]:
            P("  |P| moyen %d h plus tard quand elle est encore observable : %.1f bps (n=%d)" % (k, 1e4 * statistics.fmean(absp[k]), len(absp[k])))
    P("  (la prime étant l'écart entre le prix du perp et l'index, une prime encore observable à +k heures signifie que le perp n'a PAS convergé)")
    P("")
    # sweep train
    rows = []
    for th in thetas:
        for h in holds:
            tr = run_strategy(insts, th, h, *w["train"])
            rows.append((th, h, stats(tr)))
    P("== Train : %d points testés" % len(rows))
    elig = [r for r in rows if r[2]["n"] >= 30]
    P("  éligibles (>= 30 trades) : %d/%d ; moyenne nette > 0 : %d" % (len(elig), len(rows), sum(1 for r in elig if r[2]["mean"] > 0)))
    for th, h, s in sorted(rows, key=lambda r: -r[2]["mean"]):
        P("    theta=%d h=%d : %d trades, net moyen %+.1f bps (t %.2f, win %.0f %%)" % (th, h, s["n"], s["mean"], s["t"], 100 * s["win"]))
    if not elig:
        P("Aucun point éligible : arrêt (validation et test non touchés).")
        return
    top = sorted(elig, key=lambda r: -r[2]["mean"])[:3]
    P("")
    P("== Top 3 de train confirmés sur validation")
    best, best_v = None, -1e18
    for th, h, s in top:
        v = stats(run_strategy(insts, th, h, *w["val"]))
        P("    theta=%d h=%d : train %+.1f bps (%d) | validation %+.1f bps (%d trades, t %.2f)" % (th, h, s["mean"], s["n"], v["mean"], v["n"], v["t"]))
        if v["n"] >= 10 and v["mean"] > best_v:
            best_v, best = v["mean"], (th, h)
    P("  Points évalués : %d (train) + 3 (validation) + 1 (test, une seule fois)." % len(rows))
    if best is None:
        P("Aucun des 3 n'a >= 10 trades en validation : pas de point final, test non touché.")
        return
    th, h = best
    P("  Point final : theta=%d bps, H=%d h" % (th, h))
    P("")
    res = {}
    for name in ("train", "val", "test"):
        tr = run_strategy(insts, th, h, *w[name])
        res[name] = tr
        s = stats(tr)
        lg, sh = by_side(tr)
        counts = {}
        for t in tr:
            counts[t["sym"]] = counts.get(t["sym"], 0) + 1
        draws = random_baseline(insts, counts, h, *w[name], draws=a.draws, seed=1)
        beat = (100.0 * sum(1 for d in draws if s["mean"] > d) / len(draws)) if draws else float("nan")
        P("== %s : %d trades, net moyen %+.1f bps du notionnel (t %.2f, win %.0f %%) ; coût aller-retour moyen %.1f bps" % (
            name.upper() if name != "test" else "TEST (évalué une seule fois)", s["n"], s["mean"], s["t"], 100 * s["win"],
            statistics.fmean(i.cost_bps for i in insts)))
        P("     longs : %d trades, %+.1f bps (t %.2f) | shorts : %d trades, %+.1f bps (t %.2f)" % (lg["n"], lg["mean"], lg["t"], sh["n"], sh["mean"], sh["t"]))
        if draws:
            P("     entrées aléatoires de même rythme (%d tirages) : net moyen %+.1f bps [p5 %+.1f, p95 %+.1f] ; la stratégie fait mieux que %.0f %% des tirages"
              % (len(draws), statistics.fmean(draws), sorted(draws)[len(draws) // 20], sorted(draws)[len(draws) * 19 // 20], beat))
        if tr:
            prem = statistics.fmean(abs(t["premium_bps"]) for t in tr)
            P("     prime moyenne à l'entrée %.1f bps (en valeur absolue)" % prem)
    # levier
    P("")
    P("== Levier (point final ; descriptif, non compté dans M) : rendement moyen par trade sur la MARGE, liquidations, coût en % de la marge")
    for name in ("val", "test"):
        for L in (1, 2, 3, 5, 10):
            tr = run_strategy(insts, th, h, *w[name], leverage=float(L))
            if not tr:
                continue
            mr = [t["margin_ret"] for t in tr]
            cost = statistics.fmean(next(i for i in insts if i.sym == t["sym"]).cost_bps for t in tr) * L / 100.0
            P("    %-4s L=%-2d : %d trades, rendement moyen sur marge %+.2f %%, pire %+.0f %%, liquidations %d, coût aller-retour %.2f %% de la marge"
              % (name, L, len(tr), 100 * statistics.fmean(mr), 100 * min(mr), sum(1 for t in tr if t["liq"]), cost))
    # verdict
    st, sv = stats(res["test"]), stats(res["val"])
    p = 1 - normal_cdf(st["t"]) if st["n"] > 1 else 1.0
    M = a.m_tests
    P("")
    P("== Verdict (critères pré-enregistrés : net moyen > 0 en validation ET test avec >= 30 trades en test ; Bonferroni M=%d ; bat >= 75 %% des tirages ; longs et shorts >= 0)" % M)
    P("  validation %+.1f bps (%d), test %+.1f bps (%d trades), t test %.2f, p unilatérale %.4f, p x M = %.4f" % (sv["mean"], sv["n"], st["mean"], st["n"], st["t"], p, min(1.0, p * M)))
    ok = sv["mean"] > 0 and st["mean"] > 0 and st["n"] >= 30 and p * M < 0.05
    P("  RÉSULTAT : %s" % ("POSITIF selon les critères (à confirmer sur temps neuf)" if ok else "NÉGATIF ou NON CONCLUANT : pas de code d'exécution"))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", default="search")
    ap.add_argument("--data", default="data")
    ap.add_argument("--train-end", default="2026-08-20")
    ap.add_argument("--val-end", default="2026-09-12")
    ap.add_argument("--draws", type=int, default=200)
    ap.add_argument("--m-tests", type=int, default=7)
    ap.add_argument("--out", default="results/premium_funding_report.txt")
    a = ap.parse_args(argv)
    out = []
    search(a, out)
    text = "\n".join(out) + "\n"
    print(text)
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(text)


if __name__ == "__main__":
    main()
