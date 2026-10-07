"""Actions : H1 (écart de réouverture), H2 (coupe transversale quotidienne), H3 (nuit contre séance). Étage 1, sans coûts.

Grille, règles et critères FIXÉS avant résultat dans CLAUDE.md (« Pré-enregistrement : actions »). Modes :
plan (compte les cellules), power (puissance, n'utilise QUE les rendements), run (étage 1 complet, placebos, FDR).
Données : prix journaliers AJUSTÉS Tiingo (data/tiingo/, licence interne : aucune donnée brute n'est écrite dans results/,
seulement des statistiques agrégées) et klines 1 minute du perp (data/<SYM>_1m.csv). BIAIS DE SURVIE : l'univers est celui des
actions listées AUJOURD'HUI par Polymarket (grandes capitalisations liquides, gagnantes récentes).
Réutilise tools/grid_stage1.py (rangs, jackknife par blocs, BH, plis). stdlib uniquement.
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
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import grid_stage1 as gs  # noqa: E402

NAN = float("nan")
DISC_END = dt.date(2019, 1, 1)           # long histoire : découverte strictement avant (train <= 2012, validation 2013-2018)
FREEZE_DATE = dt.date(2026, 9, 28)       # perp : découverte strictement avant, holdout ensuite
Z_MDE = gs.Z_MDE
KAPPA = gs.KAPPA
COST_RT = 8.0 + 4.0 + 3.5                # frais x2 + slippage x2 + spread 3.5 bps (relevé actions en séance)
ONE_WAY = 4.0 + 2.0 + 1.75               # frais + slippage + demi-spread
FUND_BPS_H = 0.0625                      # intérêt fixe : 6.25e-6 par heure = 0.0625 bps par heure, payé par les longs
H2_VARS = ["mom_1", "mom_5", "mom_20", "mom_60", "mom_120", "mom_60s", "mom_120s"]
H2_HOR = (1, 5, 21)
H1_VARS = ("res", "gap")
H1_HOR = ("f30", "f2h", "fc")
SUBSETS = ("all", "wd", "wk")
ROLE = {"all": "toutes les nuits", "wd": "nuits de semaine (veille = la veille)", "wk": "week-end (vendredi -> lundi)"}


# ---------------------------------------------------------------- calendrier et données
def us_dst(d):
    m1 = dt.date(d.year, 3, 1)
    start = m1 + dt.timedelta((6 - m1.weekday()) % 7) + dt.timedelta(7)
    n1 = dt.date(d.year, 11, 1)
    end = n1 + dt.timedelta((6 - n1.weekday()) % 7)
    return start <= d < end


def session_minutes(d):
    """(ouverture, clôture) des actions US en minutes UTC depuis minuit : 13:30-20:00 en heure d'été, 14:30-21:00 sinon."""
    return (810, 1200) if us_dst(d) else (870, 1260)


def load_map(data="data"):
    """symbole perp -> ticker Tiingo, seulement les actions présentes chez Tiingo."""
    with open(os.path.join(data, "instruments_equity.json"), encoding="utf-8") as f:
        ins = json.load(f)
    st = {}
    p = os.path.join(data, "tiingo", "_state.json")
    if os.path.exists(p):
        st = json.load(open(p, encoding="utf-8"))["tickers"]
    return {i["symbol"]: i["base_asset"].upper() for i in ins if st.get(i["base_asset"].upper(), {}).get("status") == "ok"}


def load_tiingo(ticker, data="data"):
    d = {"date": [], "O": [], "C": []}
    with open(os.path.join(data, "tiingo", ticker + ".csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            o, c = float(r["adjOpen"]), float(r["adjClose"])
            if o > 0 and c > 0:
                d["date"].append(dt.date.fromisoformat(r["date"]))
                d["O"].append(o)
                d["C"].append(c)
    return d


def lg(a, b):
    return 1e4 * math.log(a / b)


# ---------------------------------------------------------------- jackknife sur un tableau de valeurs
def jk_mean(vals, blen):
    """Moyenne et erreur-type jackknife (suppression d'un bloc de blen valeurs consécutives)."""
    n = len(vals)
    if n < 20:
        return NAN, NAN
    s = sum(vals)
    blocks = [(i, min(i + blen, n)) for i in range(0, n, blen)]
    B = len(blocks)
    th = [(s - sum(vals[a:b])) / (n - (b - a)) for a, b in blocks]
    m = sum(th) / B
    se = math.sqrt((B - 1) / B * sum((t - m) ** 2 for t in th))
    return s / n, se


def terciles(vals):
    n = len(vals)
    return [vals[: n // 3], vals[n // 3: 2 * n // 3], vals[2 * n // 3:]]


def bh_cal(zs, lam):
    ps = [gs.phi_p(z / lam) if z == z else NAN for z in zs]
    return ps, gs.bh_q(ps)


# ---------------------------------------------------------------- H1 : observations (action, jour)
def h1_obs(sym, tick, perp, tg, until=FREEZE_DATE):
    """Une ligne par jour de séance : mouvement du perp hors séance, écart d'ouverture réel, résidu, rendements ultérieurs.
    Prix du perp P(m) = clôture de la barre d'une minute qui DÉBUTE à la minute m (connue à m+1)."""
    rows = []
    D = tg["date"]
    ms = lambda d: (gs.calendar.timegm(d.timetuple()) * 1000 - gs.T0_MS) // 60000
    for k in range(1, len(D)):
        d, p = D[k], D[k - 1]
        if d >= until or p < dt.date(2026, 5, 1):
            continue
        om, cm = session_minutes(d)
        _, pcm = session_minutes(p)
        i_c, i_o = ms(p) + pcm - 1, ms(d) + om - 1
        i0, i30, i2, ic = ms(d) + om, ms(d) + om + 30, ms(d) + om + 120, ms(d) + cm - 1
        if i_c < perp.start or ic >= gs.G:
            continue
        v = [perp.C[i] for i in (i_c, i_o, i0, i30, i2, ic)]
        if any(not (x > 0) for x in v):
            continue
        gap = lg(tg["O"][k], tg["C"][k - 1])
        move = lg(v[1], v[0])
        gdays = (d - p).days
        rows.append({"sym": sym, "date": d, "gap": gap, "move": move, "res": move - gap, "f30": lg(v[3], v[2]),
                     "f2h": lg(v[4], v[2]), "fc": lg(v[5], v[2]), "wd": gdays == 1, "wk": gdays == 3, "dow": d.weekday()})
    return rows


def in_subset(r, sub):
    return sub == "all" or (sub == "wd" and r["wd"]) or (sub == "wk" and r["wk"])


def build_h1(data="data", until=FREEZE_DATE, min_days=40):
    mp = load_map(data)
    cost = gs.load_costs(data)
    gs.G = (gs.FREEZE_MS - gs.T0_MS) // 60000
    obs, costs, used = {}, {}, []
    for sym, tick in mp.items():
        if not os.path.exists(os.path.join(data, sym + "_1m.csv")):
            continue
        perp = gs.load_klines(sym, data)
        rows = h1_obs(sym, tick, perp, load_tiingo(tick, data), until)
        if len(rows) >= min_days:
            obs[sym], costs[sym] = rows, cost.get(sym, COST_RT)
            used.append(sym)
    return obs, costs


# ---------------------------------------------------------------- H1b : IC pooled, jackknife par jour
def pooled_inst(rows_by_sym, var, hor, sub, cost):
    """Pseudo-instrument poolé : x normalisé par action (écart-type propre), y brut en bps, blocs = jours."""
    xs, ys, bl = [], [], []
    items = []
    for sym, rows in rows_by_sym.items():
        rr = [r for r in rows if in_subset(r, sub)]
        if len(rr) < 15:
            continue
        sd = statistics.pstdev([r[var] for r in rr])
        if sd <= 0:
            continue
        for r in rr:
            items.append((r["date"].toordinal(), r[var] / sd, r[hor], sym))
    items.sort(key=lambda a: (a[0], a[3]))
    inst = gs.Inst("pool")
    inst.cost = cost
    x = [a[1] for a in items]
    y = [a[2] for a in items]
    b = [a[0] for a in items]
    inst.pops[(1, 0)] = (list(range(len(x))), y, b, gs.rank_avg(y) if y else [])
    return inst, x, sorted(set(b)), items


def fold_by_block(blocks):
    n = len(blocks)
    pos = {b: i for i, b in enumerate(blocks)}
    return lambda b: min(2, 3 * pos[b] // max(n, 1))


def h1b_cell(rows_by_sym, var, hor, sub, cost, rng=None, placebo=None):
    rbs = rows_by_sym
    if placebo:   # remplace la variable, action par action : retard aléatoire (en jours) ou mélange par blocs de 5 jours
        rbs = {}
        for sym, rows in rows_by_sym.items():
            rows = sorted(rows, key=lambda r: r["date"])
            xv = [r[var] for r in rows]
            if placebo == "lag":
                L = rng.randint(3, 20)
                xv = [NAN] * L + xv[:-L]
            else:
                bl = [xv[i:i + 5] for i in range(0, len(xv), 5)]
                rng.shuffle(bl)
                xv = [v for b in bl for v in b]
            rbs[sym] = [dict(r, **{var: v}) for r, v in zip(rows, xv) if v == v]
    inst, x, blocks, _ = pooled_inst(rbs, var, hor, sub, cost)
    if len(x) < 150:
        return None
    gs.MIN_OBS = 100
    c = gs.inst_cell(x, inst, 1, False, fold_by_block(blocks), 0)
    if c is None:
        return None
    a = gs.Acc()
    a.add("pool", c)
    return a.result()


# ---------------------------------------------------------------- H1a : régression descriptive
def h1a(rows_by_sym, sub):
    rr = [r for rows in rows_by_sym.values() for r in rows if in_subset(r, sub)]
    n = len(rr)
    mx = sum(r["move"] for r in rr) / n
    my = sum(r["gap"] for r in rr) / n
    sxx = sum((r["move"] - mx) ** 2 for r in rr)
    sxy = sum((r["move"] - mx) * (r["gap"] - my) for r in rr)
    syy = sum((r["gap"] - my) ** 2 for r in rr)
    b = sxy / sxx
    a = my - b * mx
    res = {id(r): r["gap"] - a - b * r["move"] for r in rr}

    def cluster_se(key):
        sc = {}
        for r in rr:
            sc[key(r)] = sc.get(key(r), 0.0) + (r["move"] - mx) * res[id(r)]
        G_ = len(sc)
        return math.sqrt(G_ / max(G_ - 1, 1) * sum(v * v for v in sc.values())) / sxx

    return {"n": n, "beta": b, "se_date": cluster_se(lambda r: r["date"]), "se_stock": cluster_se(lambda r: r["sym"]),
            "r2": sxy * sxy / (sxx * syy), "sd_gap": math.sqrt(syy / n), "sd_move": math.sqrt(sxx / n),
            "mean_abs_gap": sum(abs(r["gap"]) for r in rr) / n}


# ---------------------------------------------------------------- H2 : panneau quotidien
class Panel:
    def __init__(self, tickers, data="data", until=DISC_END):
        self.tickers = tickers
        raw = {t: load_tiingo(t, data) for t in tickers}
        dates = sorted({d for r in raw.values() for d in r["date"] if d < until})
        self.dates = dates
        pos = {d: i for i, d in enumerate(dates)}
        n = len(dates)
        self.lr = {}
        for t, r in raw.items():
            a = [NAN] * n
            for d, c in zip(r["date"], r["C"]):
                if d in pos:
                    a[pos[d]] = math.log(c)
            self.lr[t] = a
        self.n = n
        self.sig = {t: self._vol(self.lr[t]) for t in tickers}

    @staticmethod
    def _vol(lr, w=60):
        n = len(lr)
        out = [NAN] * n
        r = [lr[i] - lr[i - 1] if (i and lr[i] == lr[i] and lr[i - 1] == lr[i - 1]) else NAN for i in range(n)]
        for i in range(w, n):
            v = [x for x in r[i - w + 1:i + 1] if x == x]
            if len(v) >= 40:
                m = sum(v) / len(v)
                out[i] = math.sqrt(sum((x - m) ** 2 for x in v) / (len(v) - 1))
        return out

    def signal(self, var, t, i):
        """Valeur de la variable pour la action i (indice de ticker) à la date d'indice t (clôture)."""
        lr = self.lr[self.tickers[i]]
        if var.endswith("s"):
            L = int(var[4:-1])
            a, b = t - 21, t - 21 - L
        else:
            L = int(var[4:])
            a, b = t, t - L
        if b < 0:
            return NAN
        x, y = lr[a], lr[b]
        return 1e4 * (x - y) if (x == x and y == y) else NAN

    def fwd(self, i, t, h):
        lr = self.lr[self.tickers[i]]
        if t + h >= self.n:
            return NAN
        x, y = lr[t + h], lr[t]
        return 1e4 * (x - y) if (x == x and y == y) else NAN


def h2_series(P, var, h, src=None, min_names=10):
    """Série par date échantillonnée (non chevauchante) : (indice, IC de rang, écart ew, écart vol, rotation)."""
    out = []
    prev_top = prev_bot = None
    k = len(P.tickers)
    for t in range(0, P.n - h, h):
        s = t if src is None else src[t]
        if s is None:
            continue
        rows = []
        for i in range(k):
            x = P.signal(var, s, i)
            if x != x:
                continue
            f = P.fwd(i, t, h)
            if f != f:
                continue
            sg = P.sig[P.tickers[i]][s]
            rows.append((x, f, sg, i))
        m = len(rows)
        if m < min_names:
            continue
        xr = gs.rank_avg([r[0] for r in rows])
        fr = gs.rank_avg([r[1] for r in rows])
        mx, my = (m + 1) / 2, (m + 1) / 2
        sxy = sum((a - mx) * (b - my) for a, b in zip(xr, fr))
        sxx = sum((a - mx) ** 2 for a in xr)
        syy = sum((b - my) ** 2 for b in fr)
        ic = sxy / math.sqrt(sxx * syy) if sxx > 0 and syy > 0 else NAN
        q = max(1, m // 5)
        order = sorted(range(m), key=lambda j: rows[j][0])
        bot, top = order[:q], order[-q:]
        ew = sum(rows[j][1] for j in top) / q - sum(rows[j][1] for j in bot) / q

        def vw(sel):
            w = [1.0 / rows[j][2] if rows[j][2] == rows[j][2] and rows[j][2] > 0 else NAN for j in sel]
            if any(x != x for x in w):
                return NAN
            return sum(a * rows[j][1] for a, j in zip(w, sel)) / sum(w)
        spv = vw(top) - vw(bot)
        topS, botS = {rows[j][3] for j in top}, {rows[j][3] for j in bot}
        turn = NAN if prev_top is None else (len(topS - prev_top) / q + len(botS - prev_bot) / q) / 2
        prev_top, prev_bot = topS, botS
        out.append((t, ic, ew, spv, turn, m))
    return out


def h2_stats(series, h):
    ic = [r[1] for r in series if r[1] == r[1]]
    ew = [r[2] for r in series if r[1] == r[1]]
    blen = max(1, round(21 / h))
    m, se = jk_mean(ic, blen)
    sp, sps = jk_mean(ew, blen)
    vws = [r[3] for r in series if r[3] == r[3]]
    tn = [r[4] for r in series if r[4] == r[4]]
    folds_ic = [sum(f) / len(f) if f else NAN for f in terciles(ic)]
    folds_sp = [sum(f) / len(f) if f else NAN for f in terciles(ew)]
    tau = sum(tn) / len(tn) if tn else NAN
    cost = 4 * tau * ONE_WAY if tau == tau else NAN
    z = m / se if se == se and se > 0 else NAN
    return {"n": len(ic), "ic": m, "se": se, "z": z, "spread": sp, "spread_se": sps,
            "spread_vw": sum(vws) / len(vws) if vws else NAN, "turn": tau, "cost": cost,
            "tradab": abs(sp) / cost if cost == cost and cost > 0 else NAN, "fold_ic": folds_ic, "fold_sp": folds_sp,
            "names": sum(r[5] for r in series) / len(series)}


def stable(ic, fic, fsp):
    s = 1 if ic > 0 else -1
    return all(f == f and f * s > 0 for f in fic) and all(f == f and f * s > 0 for f in fsp)


def placebo_src(P, mode, rng, h):
    n = P.n
    if mode == "lag":
        L = rng.randint(30, 250)
        return [t - L if t - L >= 0 else None for t in range(n)]
    blk = 20
    ids = list(range((n + blk - 1) // blk))
    rng.shuffle(ids)
    src = [None] * n
    for bi, b in enumerate(ids):
        for j in range(blk):
            t = bi * blk + j
            if t < n and b * blk + j < n:
                src[t] = b * blk + j
    return src


def h2_loso(P, var, h):
    """Retire une action à la fois : IC moyen minimal et maximal. Robustesse au titre (cellules FDR seulement)."""
    ics = []
    full = list(P.tickers)
    for drop in full:
        sub = Panel.__new__(Panel)
        sub.__dict__.update(P.__dict__)
        sub.tickers = [t for t in full if t != drop]
        ic = [r[1] for r in h2_series(sub, var, h) if r[1] == r[1]]
        ics.append(sum(ic) / len(ic) if ic else NAN)
    return min(ics), max(ics)


# ---------------------------------------------------------------- H3 : nuit contre séance
def h3_tiingo(P_raw, sub, leg):
    """Série par date : moyenne sur les actions du rendement nuit (clôture -> ouverture) ou séance (ouverture -> clôture)."""
    by_date = {}
    for t, r in P_raw.items():
        D, O, C = r["date"], r["O"], r["C"]
        for k in range(1, len(D)):
            if D[k] >= DISC_END:
                break
            gdays = (D[k] - D[k - 1]).days
            ok = sub == "all" or (sub == "wd" and D[k].weekday() >= 1 and gdays == 1) or (sub == "wk" and D[k].weekday() == 0
                                                                                           and gdays == 3)
            if not ok:
                continue
            v = lg(O[k], C[k - 1]) if leg == "ON" else lg(C[k], O[k])
            by_date.setdefault(D[k], []).append(v)
    ds = sorted(d for d, v in by_date.items() if len(v) >= 5)
    return [sum(by_date[d]) / len(by_date[d]) for d in ds], ds


def h3_perp(rows_by_sym, leg):
    by_date = {}
    for rows in rows_by_sym.values():
        for r in rows:
            by_date.setdefault(r["date"], []).append(r["move"] if leg == "ON" else r["fc"])
    ds = sorted(d for d, v in by_date.items() if len(v) >= 5)
    return [sum(by_date[d]) / len(by_date[d]) for d in ds], ds


def hours(leg, sub):
    return {"ON": {"all": 20.0, "wd": 17.5, "wk": 65.5}, "ID": {"all": 6.5, "wd": 6.5, "wk": 6.5}}[leg][sub]


def h3_stats(vals, blen, leg, sub):
    m, se = jk_mean(vals, blen)
    if m != m:
        return None
    f = [sum(x) / len(x) if x else NAN for x in terciles(vals)]
    F = FUND_BPS_H * hours(leg, sub)
    cost = COST_RT + (F if m > 0 else -F)
    return {"n": len(vals), "mean": m, "se": se, "z": m / se if se > 0 else NAN, "fold": f, "cost": cost,
            "tradab": abs(m) / cost, "sd": statistics.pstdev(vals)}


def sign_flip(vals, blk, rng):
    out, i = [], 0
    while i < len(vals):
        s = rng.choice((-1.0, 1.0))
        out += [s * v for v in vals[i:i + blk]]
        i += blk
    return out


# ---------------------------------------------------------------- puissance (rendements seulement)
def power_h2(P, h):
    cs, ms = [], []
    for t in range(0, P.n - h, h):
        f = [P.fwd(i, t, h) for i in range(len(P.tickers))]
        f = [x for x in f if x == x]
        if len(f) >= 10:
            cs.append(statistics.pstdev(f))
            ms.append(len(f))
    N, sig, m = len(cs), sum(cs) / len(cs), sum(ms) / len(ms)
    q = m / 5
    mde = Z_MDE * math.sqrt(2 / q) * sig / math.sqrt(N)
    return {"n_dates": N, "sigma_cs": sig, "names": m, "mde": mde, "limit": KAPPA * 4 * 0.5 * ONE_WAY}


def power_h1(rows_by_sym, hor, sub):
    rr = [r for rows in rows_by_sym.values() for r in rows if in_subset(r, sub)]
    n = len(rr)
    if n < 150:
        return {"n": n, "mde": NAN, "limit": KAPPA * COST_RT}
    sig = statistics.pstdev([r[hor] for r in rr])
    by = {}
    for r in rr:
        by.setdefault(r["date"], []).append(r[hor])
    kbar = n / len(by)
    dm = [sum(v) / len(v) for v in by.values() if len(v) >= 3]
    rho = max(0.0, (kbar * statistics.pvariance(dm) - sig ** 2) / (sig ** 2 * (kbar - 1))) if kbar > 1 else 0.0
    n_eff = n / (1 + (kbar - 1) * rho)
    return {"n": n, "n_dates": len(by), "rho": rho, "sigma": sig, "n_eff": n_eff,
            "mde": Z_MDE * sig * math.sqrt(2 / (0.1 * n_eff)), "limit": KAPPA * COST_RT}


def power_h3(vals, leg, sub, blen=1):
    sd = statistics.pstdev(vals)
    return {"n": len(vals), "sigma": sd, "mde": Z_MDE * sd / math.sqrt(len(vals)), "limit": KAPPA * (COST_RT + FUND_BPS_H * hours(leg, sub))}


# ---------------------------------------------------------------- cellules planifiées
def planned():
    cells = []
    for v in H1_VARS:
        for h in H1_HOR:
            for s in ("all", "wd"):
                cells.append(("H1b", v, h, s))
    for v in H2_VARS:
        for h in H2_HOR:
            cells.append(("H2", v, str(h), "xs"))
    for leg in ("ON", "ID"):
        for s in SUBSETS:
            cells.append(("H3", leg, "tiingo", s))
        cells.append(("H3", leg, "perp", "all"))
    return cells


# ---------------------------------------------------------------- modes
def setup(data="data"):
    mp = load_map(data)
    tick_long = sorted(set(mp.values()))
    P_raw = {t: load_tiingo(t, data) for t in tick_long}
    obs, costs = build_h1(data)
    return mp, tick_long, P_raw, obs, costs


def run_power(data="data", out="results"):
    mp, tick_long, P_raw, obs, costs = setup(data)
    P = Panel(tick_long, data)
    res = {"universe_h1": sorted(obs), "n_h1": {s: len(r) for s, r in obs.items()}, "cells": {}}
    for v in H1_VARS:
        for h in H1_HOR:
            for s in ("all", "wd"):
                res["cells"]["H1b|%s|%s|%s" % (v, h, s)] = power_h1(obs, h, s)
    for h in H2_HOR:
        for v in H2_VARS:
            res["cells"]["H2|%s|%d|xs" % (v, h)] = power_h2(P, h)
    for leg in ("ON", "ID"):
        for s in SUBSETS:
            vals, _ = h3_tiingo(P_raw, s, leg)
            res["cells"]["H3|%s|tiingo|%s" % (leg, s)] = power_h3(vals, leg, s)
        vals, _ = h3_perp(obs, leg)
        res["cells"]["H3|%s|perp|all" % leg] = power_h3(vals, leg, "all")
    for c in res["cells"].values():
        c["ok"] = bool(c["mde"] == c["mde"] and c["mde"] <= c["limit"])
    json.dump(res, open(os.path.join(out, "stocks_power.json"), "w"), indent=1, default=lambda x: None)
    return res


def run_all(data="data", out="results", seed=20261008, log=print):
    power = json.load(open(os.path.join(out, "stocks_power.json")))
    mp, tick_long, P_raw, obs, costs = setup(data)
    P = Panel(tick_long, data)
    rng = random.Random(seed)
    cells = {}    # clé -> dict
    plc = []      # z placebo
    for cell in planned():
        fam, a, b, c = cell
        key = "|".join(str(x) for x in cell)
        pw = power["cells"].get(key.replace("|".join(["H2", a, b, c]), "H2|%s|%s|xs" % (a, b)), power["cells"].get(key))
        rec = {"hyp": fam, "var": a, "horizon": b, "subset": c, "mde": pw.get("mde") if pw else None,
               "limit": pw.get("limit") if pw else None}
        if not pw or not pw["ok"]:
            rec["status"] = "sous-puissant"
            cells[cell] = rec
            continue
        z_pl = []
        if fam == "H1b":
            cost = sum(costs.values()) / len(costs)
            r = h1b_cell(obs, a, b, c, cost)
            if r is None:
                rec["status"] = "indisponible"
                cells[cell] = rec
                continue
            rec.update({"status": "included", "n": r["n_obs"], "stat": r["ic"], "se": r["se_jack"], "z": r["z"],
                        "spread_bps": r["spread_bps"], "cost_bps": r["cost_bps"], "tradab": r["tradab"],
                        "fold_a": r["fold_ic"], "fold_b": r["fold_spread"], "stable": int(r["stable"])})
            for mode in ("lag", "shuffle"):
                rp = h1b_cell(obs, a, b, c, cost, random.Random(rng.random()), mode)
                if rp is not None:
                    z_pl.append(rp["z"])
        elif fam == "H2":
            h = int(b)
            s = h2_series(P, a, h)
            st = h2_stats(s, h)
            rec.update({"status": "included", "n": st["n"], "stat": st["ic"], "se": st["se"], "z": st["z"],
                        "spread_bps": st["spread"], "cost_bps": st["cost"], "tradab": st["tradab"], "turn": st["turn"],
                        "spread_vw": st["spread_vw"], "fold_a": st["fold_ic"], "fold_b": st["fold_sp"],
                        "stable": int(stable(st["ic"], st["fold_ic"], st["fold_sp"]))})
            for mode in ("lag", "shuffle"):
                src = placebo_src(P, mode, random.Random(rng.random()), h)
                sp = h2_stats(h2_series(P, a, h, src), h)
                z_pl.append(sp["z"])
        else:
            vals, _ds = h3_perp(obs, a) if b == "perp" else h3_tiingo(P_raw, c, a)
            blen = 5 if b == "perp" else 20
            st = h3_stats(vals, blen, a, c)
            if st is None:
                rec["status"] = "indisponible"
                cells[cell] = rec
                continue
            sgn = 1 if st["mean"] > 0 else -1
            rec.update({"status": "included", "n": st["n"], "stat": st["mean"], "se": st["se"], "z": st["z"],
                        "spread_bps": st["mean"], "cost_bps": st["cost"], "tradab": st["tradab"],
                        "fold_a": st["fold"], "fold_b": st["fold"],
                        "stable": int(all(f == f and f * sgn > 0 for f in st["fold"]))})
            for blk in (20, 60):
                sf = h3_stats(sign_flip(vals, blk, random.Random(rng.random())), blen, a, c)
                z_pl.append(sf["z"] if sf else NAN)
        rec["z_placebo"] = z_pl
        plc += [z for z in z_pl if z == z]
        cells[cell] = rec
    lam = max(1.0, statistics.median(abs(z) for z in plc) / 0.6745) if plc else 1.0
    inc = [k for k, v in cells.items() if v["status"] == "included"]
    ps, qs = bh_cal([cells[k]["z"] for k in inc], lam)
    _, qraw = bh_cal([cells[k]["z"] for k in inc], 1.0)
    for k, p, q, qr in zip(inc, ps, qs, qraw):
        cells[k].update({"p_cal": p, "q_cal": q, "q_raw": qr})
        v = cells[k]
        v["fdr"] = int(q == q and q <= 0.05)
        v["passes_stage1"] = 0
    # robustesse au titre (H2 et H1b) pour les cellules FDR, puis porte
    for k in inc:
        v = cells[k]
        v["loso_min"] = v["loso_max"] = None
        if v["fdr"] and k[0] == "H2":
            lo, hi = h2_loso(P, k[1], int(k[2]))
            v["loso_min"], v["loso_max"] = lo, hi
            robust = lo * hi > 0 and (lo > 0) == (v["stat"] > 0)
        else:
            robust = True
        v["passes_stage1"] = int(v["fdr"] and v["stable"] and v["tradab"] > 1.0 and robust)
    # H1a, descriptif
    h1a_res = {s: h1a(obs, s) for s in SUBSETS}
    write_outputs(cells, lam, plc, h1a_res, power, out)
    return cells, lam, plc, h1a_res


FIELDS = ["hyp", "var", "horizon", "subset", "status", "n", "stat", "se", "z", "p_cal", "q_cal", "q_raw", "fdr",
          "fold_a1", "fold_a2", "fold_a3", "fold_b1", "fold_b2", "fold_b3", "stable", "spread_bps", "cost_bps", "tradab",
          "turn", "spread_vw", "loso_min", "loso_max", "mde", "limit", "z_placebo_1", "z_placebo_2", "passes_stage1"]


def fm(x):
    if x is None or (isinstance(x, float) and x != x):
        return ""
    return "%.5g" % x if isinstance(x, float) else str(x)


def write_outputs(cells, lam, plc, h1a_res, power, out):
    with open(os.path.join(out, "stocks_stage1.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(FIELDS)
        for k, v in cells.items():
            row = dict(v)
            for i in range(3):
                row["fold_a%d" % (i + 1)] = v.get("fold_a", [None] * 3)[i] if v.get("fold_a") else None
                row["fold_b%d" % (i + 1)] = v.get("fold_b", [None] * 3)[i] if v.get("fold_b") else None
            zp = v.get("z_placebo") or [None, None]
            row["z_placebo_1"], row["z_placebo_2"] = (zp + [None, None])[:2]
            w.writerow([fm(row.get(c)) for c in FIELDS])
    with open(os.path.join(out, "stocks_h1a.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["subset", "n", "beta", "se_date", "se_stock", "r2", "sd_gap_bps", "sd_move_bps", "mean_abs_gap_bps"])
        for s, r in h1a_res.items():
            w.writerow([s, r["n"]] + [fm(r[c]) for c in ("beta", "se_date", "se_stock", "r2", "sd_gap", "sd_move",
                                                          "mean_abs_gap")])
    write_heatmap(cells, os.path.join(out, "stocks_heatmap.svg"))


def write_heatmap(cells, path):
    rows = []
    for k, v in cells.items():
        label = "%s %s %s %s" % k
        if v["status"] == "included":
            rows.append((label, v["z"], v["fdr"], v["tradab"]))
        else:
            rows.append((label, None, 0, None))
    h = 16 * len(rows) + 40
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="620" height="%d" font-family="monospace" font-size="10">' % h,
             '<rect width="100%" height="100%" fill="white"/>',
             '<text x="4" y="14">z robuste par cellule (rouge z>0, bleu z&lt;0, saturé à 4) ; gris = exclu ; cadre = FDR 5 %% ; '
             'dernière colonne : ratio effet / coût</text>']
    for i, (label, z, fdr, tr) in enumerate(rows):
        y = 24 + 16 * i
        parts.append('<text x="4" y="%d">%s</text>' % (y + 11, label))
        if z is None or z != z:
            fill = "#d9d9d9"
        else:
            t = max(-1.0, min(1.0, z / 4))
            fill = ("rgb(255,%d,%d)" % (255 - int(200 * t),) * 1) % () if False else (
                "rgb(255,%d,%d)" % ((255 - int(200 * t),) * 2) if t >= 0 else "rgb(%d,%d,255)" % ((255 + int(200 * t),) * 2))
        parts.append('<rect x="300" y="%d" width="180" height="14" fill="%s" stroke="%s"/>' % (y, fill, "#000" if fdr else "#fff"))
        parts.append('<text x="490" y="%d">%s</text>' % (y + 11, "" if tr is None or tr != tr else "%.2f" % tr))
        if z is not None and z == z:
            parts.append('<text x="304" y="%d">z=%+.2f</text>' % (y + 11, z))
    parts.append("</svg>")
    open(path, "w", encoding="utf-8").write("\n".join(parts))


def summarize(cells, lam, plc, h1a_res, power):
    inc = [v for v in cells.values() if v["status"] == "included"]
    lines = ["cellules planifiées %d (+3 descriptives H1a) ; sous-puissantes %d ; indisponibles %d ; testées %d" % (
        len(cells), sum(v["status"] == "sous-puissant" for v in cells.values()),
        sum(v["status"] == "indisponible" for v in cells.values()), len(inc))]
    lines.append("faux positifs attendus à p<0.05 non corrigé : %.1f" % (0.05 * len(inc)))
    if plc:
        lines.append("placebos (%d z) : p<0.05 %.1f %%, |z| max %.2f, écart-type robuste de z %.2f ; lambda = %.3f" % (
            len(plc), 100 * sum(gs.phi_p(z) < 0.05 for z in plc) / len(plc), max(abs(z) for z in plc),
            statistics.median(abs(z) for z in plc) / 0.6745, lam))
    lines.append("réel : p<0.05 non corrigé %d ; FDR BH 5 %% : %d ; stables : %d ; passent l'étage 1 : %d" % (
        sum(gs.phi_p(v["z"]) < 0.05 for v in inc), sum(v["fdr"] for v in inc), sum(v["fdr"] and v["stable"] for v in inc),
        sum(v["passes_stage1"] for v in inc)))
    lines.append("")
    lines.append("%-5s %-9s %-7s %-6s %-6s %7s %8s %7s %7s %8s %7s %5s %5s %5s" % (
        "hyp", "var", "horiz", "subset", "n", "stat", "z", "q_cal", "spread", "coût", "ratio", "stab", "FDR", "pass"))
    for v in sorted(inc, key=lambda v: -abs(v["z"]) if v["z"] == v["z"] else 0):
        lines.append("%-5s %-9s %-7s %-6s %-6d %+7.4f %8.2f %7.3f %7.2f %8.1f %7.2f %5d %5d %5d" % (
            v["hyp"], v["var"], v["horizon"], v["subset"], v["n"], v["stat"], v["z"], v["q_cal"], v["spread_bps"], v["cost_bps"],
            v["tradab"], v["stable"], v["fdr"], v["passes_stage1"]))
    lines.append("")
    lines.append("H1a (descriptif) : écart d'ouverture réel regressé sur le mouvement hors séance du perp")
    for s, r in h1a_res.items():
        lines.append("  %-4s n=%d beta=%.3f (se date %.3f, se action %.3f) R2=%.3f ; écart-type du gap %.0f bps, du mouvement %.0f bps" % (
            s, r["n"], r["beta"], r["se_date"], r["se_stock"], r["r2"], r["sd_gap"], r["sd_move"]))
    lines.append("")
    lines.append("sous-puissantes : " + ", ".join("%s %s %s %s" % k for k, v in cells.items() if v["status"] == "sous-puissant"))
    return "\n".join(lines)


def write_universe(data="data", out="results"):
    """Univers : action Polymarket -> ticker Tiingo, jours de perp, profondeur Tiingo (métadonnées agrégées seulement)."""
    ins = json.load(open(os.path.join(data, "instruments_equity.json"), encoding="utf-8"))
    st = json.load(open(os.path.join(data, "tiingo", "_state.json"), encoding="utf-8"))["tickers"]
    surv = {r["symbol"]: r for r in csv.DictReader(open(os.path.join(data, "universe_survey.csv"), encoding="utf-8"))}
    with open(os.path.join(out, "stocks_universe.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["perp_symbol", "tiingo_ticker", "perp_days", "perp_first_kline", "tiingo_status", "tiingo_first_date",
                    "tiingo_rows", "note"])
        for i in ins:
            t, r = i["base_asset"].upper(), surv.get(i["symbol"], {})
            s = st.get(t, {})
            note = "" if s.get("status") == "ok" else "absent chez Tiingo (non américain ou pré-IPO) : exclu"
            w.writerow([i["symbol"], t, r.get("days", ""), r.get("first_kline", ""), s.get("status", ""),
                        s.get("first", ""), s.get("rows", ""), note])


def describe_h1b(data="data", out="results"):
    """DESCRIPTIF, non décisionnel : H1b est sous-puissante (écartée du FDR) ; on rapporte seulement les estimations ponctuelles."""
    obs, costs = build_h1(data)
    cost = sum(costs.values()) / len(costs)
    with open(os.path.join(out, "stocks_h1b_descriptive.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["var", "horizon", "subset", "n", "ic", "z_robust", "decile_spread_bps", "cost_bps", "note"])
        for v in H1_VARS:
            for h in H1_HOR:
                for sub in ("all", "wd"):
                    r = h1b_cell(obs, v, h, sub, cost)
                    if r is not None:
                        w.writerow([v, h, sub, r["n_obs"], fm(r["ic"]), fm(r["z"]), fm(r["spread_bps"]), fm(r["cost_bps"]),
                                    "sous-puissant : descriptif seulement, hors FDR"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["plan", "power", "run", "universe", "describe"], required=True)
    ap.add_argument("--data", default="data")
    ap.add_argument("--out", default="results")
    a = ap.parse_args()
    if a.mode == "plan":
        c = planned()
        print("cellules planifiées (FDR) : %d ; H1b %d, H2 %d, H3 %d ; plus 3 descriptives H1a" % (
            len(c), sum(x[0] == "H1b" for x in c), sum(x[0] == "H2" for x in c), sum(x[0] == "H3" for x in c)))
    elif a.mode == "describe":
        describe_h1b(a.data, a.out)
    elif a.mode == "universe":
        write_universe(a.data, a.out)
    elif a.mode == "power":
        r = run_power(a.data, a.out)
        print("univers H1 (%d actions, >= 40 jours de perp avant le gel) : %s" % (len(r["universe_h1"]), " ".join(r["universe_h1"])))
        print("jours (action, jour) par action : %s" % r["n_h1"])
        for k, v in r["cells"].items():
            print("%-26s n=%s MDE=%s limite=%s ok=%s" % (k, v.get("n", v.get("n_dates")), fm(v["mde"]), fm(v["limit"]), v["ok"]))
        print("retenues : %d sur %d" % (sum(v["ok"] for v in r["cells"].values()), len(r["cells"])))
    else:
        t0 = time.time()
        cells, lam, plc, h1a_res = run_all(a.data, a.out)
        power = json.load(open(os.path.join(a.out, "stocks_power.json")))
        text = summarize(cells, lam, plc, h1a_res, power)
        print(text)
        open(os.path.join(a.out, "stocks_summary.txt"), "w", encoding="utf-8").write(text + "\n")
        print("durée %.0f s" % (time.time() - t0))


if __name__ == "__main__":
    main()
