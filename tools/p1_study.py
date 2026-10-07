"""P1 : signaux lents (inversion en coupe transversale des actions S1, prime de nuit S2) exécutés en ordres passifs (post-only).

Règles FIXÉES avant résultat dans CLAUDE.md (« Pré-enregistrement : P1 »). Partie A : effet EXÉCUTABLE sur la longue histoire Tiingo (entrée à
l'ouverture J, sortie à la clôture J+h-1, à côté de l'effet clôture-clôture), net du coût maker, FDR, placebos. Partie B : exécution simulée
sur les trades du perp (tools/passive_fills.py), politiques (a) taker, (b) post-only sans repli, (c) post-only avec repli taker, bornes
optimiste et conservatrice, par signal émis (non-exécutés à zéro), intervalles par bootstrap par jour, baseline aléatoire, levier, point mort.
Biais de survie : univers actuel de Polymarket. Licence Tiingo : seulement des statistiques agrégées en sortie. stdlib uniquement.
python tools/p1_study.py --mode a|b
"""
import argparse
import bisect
import calendar
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
import passive_fills as pf  # noqa: E402
import stocks_study as ss  # noqa: E402

NAN = float("nan")
MAKER, TAKER_RT = pf.MAKER_BPS, 2 * (pf.TAKER_BPS + pf.SLIP_BPS)
S1 = {"S1a": ("mom_1", 1), "S1b": ("mom_5", 1), "S1c": ("mom_5", 5)}
S2 = {"S2a": "all", "S2b": "wd"}
PERP_START, PERP_END = dt.date(2026, 8, 26), dt.date(2026, 9, 25)     # sorties avant le gel du 2026-09-28
HOURS_S2 = {"all": 27.1, "wd": 17.5}
S1_POLICIES = [("taker", None)] + [(p, T) for p in ("post", "post_fb") for T in ("30m", "2h", "eos")]
S2_POLICIES = [("taker", None)] + [(p, T) for p in ("post", "post_fb") for T in ("30m", "2h")]
BOUNDS = [("opt", "opt", 0.0), ("cons0", "cons", 0.0), ("cons1000", "cons", 1000.0), ("cons5000", "cons", 5000.0)]
NOTIONAL = 1000.0


# ---------------------------------------------------------------- horaires
def utc_ms(d, hh, mm):
    """Instant UTC (ms) de l'heure de l'Est hh:mm du jour d (heure d'été exacte : décalage 4 h, sinon 5 h)."""
    return calendar.timegm(d.timetuple()) * 1000 + (hh * 60 + mm + (240 if ss.us_dst(d) else 300)) * 60000


# ---------------------------------------------------------------- partie A
class ExecPanel(ss.Panel):
    """Panneau dont le rendement ultérieur est EXÉCUTABLE : de l'ouverture du jour J = t+1 à la clôture du jour t+h (J+h-1)."""

    def __init__(self, tickers, data="data", until=ss.DISC_END):
        super().__init__(tickers, data, until)
        pos = {d: i for i, d in enumerate(self.dates)}
        self.lro = {}
        for t in tickers:
            raw = ss.load_tiingo(t, data)
            a = [NAN] * self.n
            for d, o in zip(raw["date"], raw["O"]):
                if d in pos:
                    a[pos[d]] = math.log(o)
            self.lro[t] = a

    def fwd(self, i, t, h):
        if t + h >= self.n or t + 1 >= self.n:
            return NAN
        tk = self.tickers[i]
        x, y = self.lr[tk][t + h], self.lro[tk][t + 1]
        return 1e4 * (x - y) if (x == x and y == y) else NAN


def s1_series(P, var, h, src=None):
    """(gross par date en bps d'un portefeuille long du quintile bas / short du haut, IC) ; inversion : on achète les perdants."""
    out = ss.h2_series(P, var, h, src)
    return [-r[2] for r in out if r[2] == r[2]], [r[1] for r in out if r[1] == r[1]]


def cell_stats(gross, cost, blen):
    net = [g - c for g, c in zip(gross, cost)]
    m, se = ss.jk_mean(net, blen)
    g, gse = ss.jk_mean(gross, blen)
    folds = [sum(f) / len(f) if f else NAN for f in ss.terciles(net)]
    z = m / se if se == se and se > 0 else NAN
    return {"n": len(net), "gross": g, "gross_se": gse, "gross_z": g / gse if gse == gse and gse > 0 else NAN, "cost": sum(cost) / len(cost),
            "net": m, "net_se": se, "z": z, "folds": folds, "stable": int(all(f == f and f > 0 for f in folds)),
            "mde": ss.Z_MDE * se if se == se else NAN}


def part_a(data="data", seed=20261010, log=print):
    mp = ss.load_map(data)
    tick = sorted(set(mp.values()))
    P = ss.Panel(tick, data)
    EP = ExecPanel(tick, data)
    raw = {t: ss.load_tiingo(t, data) for t in tick}
    rng = random.Random(seed)
    cells = {}
    plz = []
    for name, (var, h) in S1.items():
        cc, ic_cc = s1_series(P, var, h)
        ex, ic_ex = s1_series(EP, var, h)
        blen = max(1, round(21 / h))
        cost = [4 * MAKER] * len(ex)            # position fermée puis rouverte à chaque période : 2 jambes x (entrée + sortie) maker
        st = cell_stats(ex, cost, blen)
        st.update({"cc_gross": sum(cc) / len(cc), "ic_exec": sum(ic_ex) / len(ic_ex), "taker_cost": 4 * (pf.TAKER_BPS + pf.SLIP_BPS + 1.75)})
        st["ratio_maker"] = st["gross"] / st["cost"]
        st["ratio_taker"] = st["gross"] / st["taker_cost"]
        pz = []
        for mode in ("lag", "shuffle"):
            src = ss.placebo_src(EP, mode, random.Random(rng.random()), h)
            g, _ = s1_series(EP, var, h, src)
            m, se = ss.jk_mean(g, blen)
            pz.append(m / se if se == se and se > 0 else NAN)
        st["placebo_z"] = pz
        plz += [z for z in pz if z == z]
        cells[name] = st
    for name, sub in S2.items():
        vals, _ = ss.h3_tiingo(raw, sub, "ON")
        cost = [2 * MAKER + ss.FUND_BPS_H * HOURS_S2[sub]] * len(vals)
        st = cell_stats(vals, cost, 20)
        st.update({"cc_gross": st["gross"], "ic_exec": NAN, "taker_cost": ss.COST_RT + ss.FUND_BPS_H * HOURS_S2[sub]})
        st["ratio_maker"] = st["gross"] / st["cost"]
        st["ratio_taker"] = st["gross"] / st["taker_cost"]
        pz = []
        for blk in (20, 60):
            sf = ss.sign_flip(vals, blk, random.Random(rng.random()))
            m, se = ss.jk_mean(sf, 20)
            pz.append(m / se if se > 0 else NAN)
        st["placebo_z"] = pz
        plz += [z for z in pz if z == z]
        cells[name] = st
    lam = max(1.0, statistics.median(abs(z) for z in plz) / 0.6745) if plz else 1.0
    names = list(cells)
    ps = [0.5 * math.erfc((cells[n]["z"] / lam) / math.sqrt(2)) if cells[n]["z"] == cells[n]["z"] else NAN for n in names]
    qs = gs.bh_q(ps)
    for n, p, q in zip(names, ps, qs):
        cells[n].update({"p_one_sided": p, "q": q})
        cells[n]["passes_a"] = int(q == q and q <= 0.05 and cells[n]["stable"])
    return cells, lam, P, EP


# ---------------------------------------------------------------- partie B
def load_books(data="data"):
    mp = ss.load_map(data)
    books, funds, klines = {}, {}, {}
    for sym, tk in mp.items():
        p = os.path.join(data, "hist", sym + "_trades.csv")
        if not os.path.exists(p):
            continue
        rows = gs.read_trades(sym, data)
        if len(rows) < 200:
            continue
        books[sym] = pf.Book(rows)
        fp = os.path.join(data, sym + "_funding.csv")
        if os.path.exists(fp):
            pts = sorted((int(r[0]), float(r[1]) * 1e4) for r in list(csv.reader(open(fp)))[1:])
            funds[sym] = ([t for t, _ in pts], [v for _, v in pts])
    return mp, books, funds


def entry_times(sig, policy, T, J):
    """(décision, échéance) d'entrée et de sortie selon le signal, la politique et T. J : jour d'entrée (S1) ou de la clôture (S2)."""
    d_in, d_out = sig["d_in"], sig["d_out"]
    if sig["kind"] == "S1":
        t0 = utc_ms(d_in, 9, 35)
        exp = {"30m": t0 + 30 * 60000, "2h": t0 + 120 * 60000, "eos": utc_ms(d_in, 15, 55)}.get(T, t0)
        if policy == "taker":
            return (t0, t0), (utc_ms(d_out, 15, 55), utc_ms(d_out, 15, 55))
        return (t0, exp), (utc_ms(d_out, 15, 25), utc_ms(d_out, 15, 55))
    close = utc_ms(d_in, 15, 55)
    dec = {"30m": close - 30 * 60000, "2h": close - 120 * 60000}.get(T, close)
    if policy == "taker":
        return (close, close), (utc_ms(d_out, 9, 35), utc_ms(d_out, 9, 35))
    return (dec, close), (utc_ms(d_out, 9, 35), utc_ms(d_out, 10, 5))


def s1_signals(P, tradable, mp_inv):
    """Signaux S1 sur la période perp : quintile bas long, haut short parmi les titres de la coupe transversale, négociables seulement."""
    out = []
    dates = P.dates
    for name, (var, h) in S1.items():
        for jt in range(1, len(dates)):
            J = dates[jt]
            if J < PERP_START or J > PERP_END or jt + h - 1 >= len(dates) or dates[jt + h - 1] > PERP_END:
                continue
            t = jt - 1
            rows = []
            for i, tk in enumerate(P.tickers):
                x = P.signal(var, t, i)
                if x == x:
                    rows.append((x, tk))
            if len(rows) < 10:
                continue
            rows.sort()
            q = max(1, len(rows) // 5)
            for side, grp in ((1, rows[:q]), (-1, rows[-q:])):
                for _x, tk in grp:
                    sym = mp_inv.get(tk)
                    if sym in tradable:
                        out.append({"signal": name, "kind": "S1", "sym": sym, "side": side, "d_in": J, "d_out": dates[jt + h - 1],
                                    "day": J, "tk": tk, "t": t})
    return out


def s2_signals(P, tradable, mp_inv):
    out = []
    dates = P.dates
    for name, sub in S2.items():
        for jt in range(len(dates) - 1):
            D, X = dates[jt], dates[jt + 1]
            if D < PERP_START or X > PERP_END:
                continue
            if sub == "wd" and (X - D).days != 1:
                continue
            for tk in P.tickers:
                sym = mp_inv.get(tk)
                if sym in tradable:
                    out.append({"signal": name, "kind": "S2", "sym": sym, "side": 1, "d_in": D, "d_out": X, "day": D, "tk": tk, "t": jt})
    return out


def simulate(sigs, books, funds, policy, T, bound, queue):
    res = []
    for s in sigs:
        e, x = entry_times(s, policy, T, s["day"])
        r = pf.run_trade(books[s["sym"]], funds.get(s["sym"]), s["side"], e, x, policy, bound, queue)
        r.update({"day": s["day"], "side": s["side"], "sym": s["sym"], "tk": s.get("tk"), "t": s.get("t"), "t_in": e[0], "t_out": x[1]})
        res.append(r)
    return res


def bootstrap_ci(res, draws=5000, seed=1, n_cells=31):
    by = {}
    for r in res:
        by.setdefault(r["day"], []).append(r["net"])
    days = sorted(by)
    if not days:
        return NAN, NAN, NAN, NAN
    rng = random.Random(seed)
    tot = sum(sum(v) for v in by.values())
    n = sum(len(v) for v in by.values())
    means = []
    for _ in range(draws):
        picks = [by[days[rng.randrange(len(days))]] for _ in days]
        nn = sum(len(p) for p in picks)
        means.append(sum(sum(p) for p in picks) / nn if nn else 0.0)
    means.sort()
    return tot / n, means[int(0.025 * draws)], means[int(0.975 * draws)], means[int(0.05 / n_cells / 2 * draws)]


def summarize_cell(res):
    n = len(res)
    f = [r for r in res if r["filled"]]
    m, lo, hi, lo_b = bootstrap_ci(res)
    mk = {h: [r["markouts"][h] for r in f if r.get("maker_entry") and r["markouts"].get(h) is not None] for h in (60, 600, 3600)}
    days = sorted({r["day"] for r in res})
    half = len(days) // 2
    h1 = [r["net"] for r in res if r["day"] in set(days[:half])]
    h2 = [r["net"] for r in res if r["day"] in set(days[half:])]
    lo_ = [r["net"] for r in res if r["side"] > 0]
    sh_ = [r["net"] for r in res if r["side"] < 0]
    mean = lambda v: sum(v) / len(v) if v else NAN
    return {"n_signals": n, "fill_rate": len(f) / n if n else NAN, "maker_share": mean([1.0 if r.get("maker_entry") else 0.0 for r in f]),
            "delay_min": mean([r["delay"] / 60000 for r in f]), "net_per_signal": m, "ci_lo": lo, "ci_hi": hi, "ci_lo_bonf": lo_b,
            "net_per_fill": mean([r["net"] for r in f]), "gross_per_fill": mean([r["gross"] for r in f]),
            "markout_1m": mean(mk[60]), "markout_10m": mean(mk[600]), "markout_1h": mean(mk[3600]),
            "half1": mean(h1), "half2": mean(h2), "long": mean(lo_), "short": mean(sh_), "sd": statistics.pstdev([r["net"] for r in res]) if n > 1 else NAN}


def random_baseline(sigs, books, funds, policy, T, bound, queue, draws, rng):
    """Mêmes nombres de signaux par jour et par côté, titres tirés au hasard parmi les négociables, même politique."""
    by = {}
    for s in sigs:
        by.setdefault((s["d_in"], s["d_out"], s["side"], s["kind"], s["signal"]), []).append(s)
    pool = sorted(books)
    means = []
    for _ in range(draws):
        pick = []
        for (di, do, side, kind, name), lst in by.items():
            for s in rng.sample(pool, min(len(lst), len(pool))):
                pick.append({"signal": name, "kind": kind, "sym": s, "side": side, "d_in": di, "d_out": do, "day": di})
        r = simulate(pick, books, funds, policy, T, bound, queue)
        means.append(sum(x["net"] for x in r) / len(r) if r else NAN)
    return means


def breakeven(cell_a, name, summ):
    """Qualité de fill minimale : sélection adverse maximale tolérée et taux de fill minimal pour 1 bps par signal."""
    if name in S1:
        h = S1[name][1]
        g_trade = cell_a["gross"] / 2
        c_m = 2 * MAKER            # entrée + sortie maker d'une jambe ; le funding long / short se compense (net nul)
    else:
        g_trade = cell_a["gross"]
        c_m = cell_a["cost"]       # inclut le funding de la durée (long payeur)
    a_star = g_trade - c_m
    a_obs = -summ["markout_10m"] if summ["markout_10m"] == summ["markout_10m"] else NAN
    denom = a_star - a_obs if a_obs == a_obs else NAN
    return {"g_trade": g_trade, "cost_maker": c_m, "a_star": a_star, "a_obs_10m": a_obs,
            "f_min_1bps": (1.0 / denom) if denom == denom and denom > 0 else NAN}


def part_b(cellsA, P, data="data", draws=200, seed=20261011, log=print):
    mp, books, funds = load_books(data)
    mp_inv = {tk: sym for sym, tk in mp.items()}
    tradable = set(books)
    sigs = s1_signals(P, tradable, mp_inv) + s2_signals(P, tradable, mp_inv)
    log("signaux : %s ; instruments négociables : %d" % ({n: sum(1 for s in sigs if s["signal"] == n) for n in list(S1) + list(S2)}, len(tradable)))
    rng = random.Random(seed)
    out = {}
    for name in list(S1) + list(S2):
        sg = [s for s in sigs if s["signal"] == name]
        pols = S1_POLICIES if name in S1 else S2_POLICIES
        for policy, T in pols:
            for bname, bound, queue in BOUNDS:
                if policy == "taker" and bname != "opt":
                    continue
                res = simulate(sg, books, funds, policy, T, bound, queue)
                st = summarize_cell(res)
                if (bname == "cons1000" or policy == "taker") and name in S1:   # S2 achete tout chaque nuit : pas de sélection, baseline dégénérée
                    st["baseline"] = random_baseline(sg, books, funds, policy, T, bound, queue, draws, rng)
                st["results"] = res
                out[(name, policy, T, bname)] = st
    return out, sigs, books, funds, mp_inv


def leverage_table(res, EP, klines, levmax=10.0):
    """Politique de référence : le PnL de chaque signal est multiplié par le levier de compte m (1x, 2x, 5x ou volatilité cible), rendement
    d'une journée = moyenne des signaux émis ce jour (non exécutés à zéro). Liquidation si l'excursion défavorable (mèches 1 minute) dépasse
    1/levier de position - mmr (mmr = 0.5 / levier max), perte de toute la marge de la transaction. Descriptif."""
    days = sorted({r["day"] for r in res})
    lines = []
    for lev, label in ((1.0, "fixe 1x"), (2.0, "fixe 2x"), (5.0, "fixe 5x"), ("vt10", "vol cible 10 %"), ("vt20", "vol cible 20 %")):
        eq, peak, dd, liq, cost_m, k = 1.0, 1.0, 0.0, 0, 0.0, 0
        for d in days:
            rs = [r for r in res if r["day"] == d]
            tot = 0.0
            for r in rs:
                if not r["filled"]:
                    continue
                if isinstance(lev, float):
                    m = lev
                else:
                    sg = EP.sig[r["tk"]][r["t"]]
                    ann = sg * math.sqrt(252) if sg == sg and sg > 0 else NAN
                    m = min(5.0, (0.10 if lev == "vt10" else 0.20) / ann) if ann == ann else 1.0
                kl = klines[r["sym"]]
                i0 = (r["e_t"] - gs.T0_MS) // 60000
                i1 = (r["x_t"] - gs.T0_MS) // 60000
                ext = min(kl.L[i0:i1 + 1]) if r["side"] > 0 else max(kl.H[i0:i1 + 1])
                adverse = max(0.0, r["side"] * (r["e_px"] - ext)) / r["e_px"] * 1e4
                if adverse >= 1e4 * (1.0 / max(1.0, m) - 0.5 / levmax):
                    tot += -1.0
                    liq += 1
                else:
                    tot += m * r["net"] / 1e4
                cost_m += m * 2 * pf.MAKER_BPS / 1e4
                k += 1
            ret = tot / len(rs) if rs else 0.0
            eq *= (1 + ret)
            peak = max(peak, eq)
            dd = max(dd, 1 - eq / peak)
        lines.append("    %-15s equity finale %6.3f drawdown max %5.1f %% liquidations %d ; frais maker %.3f %% de la marge par transaction" % (
            label, eq, 100 * dd, liq, 100 * cost_m / max(k, 1)))
    return lines


FIELDS_A = ["signal", "n_periods", "cc_gross_bps", "exec_gross_bps", "exec_gross_se", "ic_exec", "cost_maker_bps", "cost_taker_bps", "ratio_maker", "ratio_taker",
            "net_maker_bps", "net_se", "z", "p_one_sided", "q", "fold1", "fold2", "fold3", "stable", "mde_bps", "placebo_z1", "placebo_z2", "passes_a"]


def write_a(cells, lam, out):
    with open(os.path.join(out, "p1_partA.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(FIELDS_A)
        for n, c in cells.items():
            w.writerow([n, c["n"], ss.fm(c["cc_gross"]), ss.fm(c["gross"]), ss.fm(c["gross_se"]), ss.fm(c["ic_exec"]), ss.fm(c["cost"]),
                        ss.fm(c["taker_cost"]), ss.fm(c["ratio_maker"]), ss.fm(c["ratio_taker"]), ss.fm(c["net"]), ss.fm(c["net_se"]),
                        ss.fm(c["z"]), ss.fm(c["p_one_sided"]), ss.fm(c["q"])] + [ss.fm(x) for x in c["folds"]] +
                       [c["stable"], ss.fm(c["mde"]), ss.fm(c["placebo_z"][0]), ss.fm(c["placebo_z"][1]), c["passes_a"]])


def write_b(cells, out):
    with open(os.path.join(out, "p1_partB.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["signal", "policy", "T", "bound", "n_signals", "fill_rate", "maker_share", "delay_min", "net_per_signal", "ci_lo", "ci_hi", "ci_lo_bonf",
                    "net_per_fill", "gross_per_fill", "markout_1m", "markout_10m", "markout_1h", "half1", "half2", "long", "short",
                    "random_mean", "random_p5", "random_p95", "beats_random"])
        for (n, pol, T, b), s in cells.items():
            bl = [x for x in s.get("baseline", []) if x == x]
            bl.sort()
            beat = sum(x < s["net_per_signal"] for x in bl) / len(bl) if bl else NAN
            w.writerow([n, pol, T or "", b, s["n_signals"]] + [ss.fm(s[k]) for k in ("fill_rate", "maker_share", "delay_min", "net_per_signal", "ci_lo",
                       "ci_hi", "ci_lo_bonf", "net_per_fill", "gross_per_fill", "markout_1m", "markout_10m", "markout_1h", "half1", "half2", "long", "short")] +
                       [ss.fm(sum(bl) / len(bl)) if bl else "", ss.fm(bl[int(0.05 * len(bl))]) if bl else "", ss.fm(bl[int(0.95 * len(bl))]) if bl else "", ss.fm(beat)])


def verdict(cellsB, cellsA):
    """Classe chaque signal : POSITIF ROBUSTE / NON CONCLUANT / NÉGATIF (règle pré-enregistrée)."""
    out = {}
    for name in list(S1) + list(S2):
        best = None
        for (n, pol, T, b), s in cellsB.items():
            if n != name or b != "cons1000" or pol == "taker":
                continue
            bl = sorted(x for x in s.get("baseline", []) if x == x)
            beat = sum(x < s["net_per_signal"] for x in bl) / len(bl) if bl else 1.0     # S2 : sans objet (aucune sélection)
            robust = (s["ci_lo"] == s["ci_lo"] and s["ci_lo"] > 0 and s["ci_lo_bonf"] > 0 and s["half1"] > 0 and s["half2"] > 0 and
                      (s["long"] != s["long"] or s["long"] >= 0) and (s["short"] != s["short"] or s["short"] >= 0) and beat >= 0.75)
            if best is None or s["net_per_signal"] > best[1]:
                best = ((pol, T), s["net_per_signal"], robust)
        opt_pos = any(s["net_per_signal"] > 0 for (n, pol, T, b), s in cellsB.items() if n == name and b == "opt" and pol != "taker")
        if best is None:
            out[name] = "NON CALCULÉ"
        elif best[2] and cellsA[name]["passes_a"]:
            out[name] = "POSITIF ROBUSTE (à confirmer sur le holdout)"
        elif best[1] > 0 or opt_pos:
            out[name] = "NON CONCLUANT"
        else:
            out[name] = "NÉGATIF"
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["a", "b"], required=True)
    ap.add_argument("--data", default="data")
    ap.add_argument("--out", default="results")
    a = ap.parse_args()
    t0 = time.time()
    cellsA, lam, P, EP = part_a(a.data)
    write_a(cellsA, lam, a.out)
    lines = ["PARTIE A : effet exécutable (entrée ouverture J, sortie clôture J+h-1), longue histoire avant 2019, lambda = %.3f" % lam]
    for n, c in cellsA.items():
        lines.append("  %s : brut clôture-clôture %+.2f bps, EXÉCUTABLE %+.2f bps (se %.2f), coût maker %.2f, coût taker %.2f, rapport %.2f (maker) / %.2f (taker), net maker %+.2f (se %.2f, z %.2f, q %.3f), plis %s, stable %d, passe A %d" % (
            n, c["cc_gross"], c["gross"], c["gross_se"], c["cost"], c["taker_cost"], c["ratio_maker"], c["ratio_taker"], c["net"], c["net_se"], c["z"], c["q"],
            ["%.2f" % x for x in c["folds"]], c["stable"], c["passes_a"]))
    if a.mode == "b":
        Pb = ExecPanel(sorted(set(ss.load_map(a.data).values())), a.data, until=ss.FREEZE_DATE)   # signaux jusqu'au 2026-09-27
        cellsB, sigs, books, funds, mp_inv = part_b(cellsA, Pb)
        write_b(cellsB, a.out)
        v = verdict(cellsB, cellsA)
        lines.append("")
        lines.append("PARTIE B : exécution passive sur le perp (22 jours de cotation) ; verdict pré-enregistré par signal : %s" % v)
        for (n, pol, T, b), s in cellsB.items():
            if b in ("opt", "cons1000"):
                lines.append("  %s %-8s %-4s %-8s n=%4d fill %5.1f %% délai %5.1f min net/signal %+7.2f [%+7.1f, %+7.1f] (Bonferroni bas %+7.1f) net/fill %+7.2f markouts 1m %+6.1f 10m %+6.1f 1h %+6.1f" % (
                    n, pol, T or "-", b, s["n_signals"], 100 * s["fill_rate"], s["delay_min"], s["net_per_signal"], s["ci_lo"], s["ci_hi"], s["ci_lo_bonf"], s["net_per_fill"],
                    s["markout_1m"], s["markout_10m"], s["markout_1h"]))
        lines.append("")
        lines.append("POINT MORT (qualité de fill minimale) :")
        for name in list(S1) + list(S2):
            ref = cellsB.get((name, "post_fb", "2h", "cons1000"))
            if ref:
                be = breakeven(cellsA[name], name, ref)
                lines.append("  %s : effet par transaction %+.2f bps - coût maker %.2f = sélection adverse maximale tolérée A* = %+.2f bps ; sélection adverse observée (moins le markout à 10 min, politique c 2 h) %+.2f ; taux de fill minimal pour 1 bps par signal : %s" % (
                    name, be["g_trade"], be["cost_maker"], be["a_star"], be["a_obs_10m"], "%.2f" % be["f_min_1bps"] if be["f_min_1bps"] == be["f_min_1bps"] else "impossible"))
        klines = {sym: gs.load_klines(sym, a.data) for sym in books}
        lines.append("")
        lines.append("LEVIER (politique de référence c, T = 2 h, borne conservatrice Q = 1 000, période perp de 22 jours, descriptif) :")
        for name in list(S1) + list(S2):
            ref = cellsB.get((name, "post_fb", "2h", "cons1000"))
            if ref:
                lines.append("  %s" % name)
                lines += leverage_table(ref["results"], Pb, klines)
    text = "\n".join(lines)
    print(text)
    open(os.path.join(a.out, "p1_summary.txt"), "w", encoding="utf-8").write(text + "\n")
    print("durée %.0f s" % (time.time() - t0))


if __name__ == "__main__":
    main()
