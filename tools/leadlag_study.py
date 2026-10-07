"""Famille D : le prix du perp suit-il avec retard un prix externe (Binance spot, crypto) ? Étude taker.

DONNÉES : perp = trades imprimés (data/hist/<SYM>_trades.csv, side=long = agresseur acheteur, mesuré) ;
externe = clôtures 1 s de Binance spot (data/ext/<SYMBOLE>_1s.csv). Les deux séries sont alignées à la fin de chaque
seconde. P = dernier prix imprimé du perp (reporté), B = dernière clôture Binance.

MESURE (descriptive) : corrélation croisée entre le rendement du perp et le rendement Binance retardé de L secondes
(L > 0 : Binance mène ; L < 0 : le perp mène), à 1 s et 5 s de résolution, pente (bps de perp par bps de Binance) et
implication pour un mouvement Binance de 10 bps, à comparer au coût aller-retour taker.

STRATÉGIE (fixée avant résultat, voir CLAUDE.md) : à la fin de la seconde i, écart
    g = (ln B_i - ln B_{i-w}) - (ln P_i - ln P_{i-w})   en bps ;
g > theta : ACHETER le perp ; g < -theta : VENDRE. Le sens n'est JAMAIS retourné. Exécution : le premier trade du
perp d'agresseur acheteur (pour acheter) ou vendeur (pour vendre) imprimé au moins `delay` s après le signal (au plus
`maxwait` s après, sinon pas de fill) ; sortie : le premier trade d'agresseur opposé imprimé H s après l'entrée. Les
prix d'exécution sont des prix IMPRIMÉS (le spread est payé implicitement) ; coût ajouté : 2 x 4 bps de frais + 2 x 2 bps
de slippage = 12 bps. Une position à la fois par instrument.

stdlib uniquement. python tools/leadlag_study.py --mode xcorr|search
"""
from __future__ import annotations

import argparse
import bisect
import calendar
import csv
import math
import operator
import os
import random
import statistics
import sys
from array import array

FEE_BPS = 4.0
SLIP_BPS = 2.0
COST_BPS = 2 * FEE_BPS + 2 * SLIP_BPS


class Series:
    """Une paire (perp, externe) sur une grille de 1 s. t0 : seconde epoch du premier échantillon."""

    def __init__(self, sym, t0, n, ext, prints, max_lev=10.0):
        # ext : array('d') de n clôtures externes (0 = pas encore de donnée) ; prints : [(ts_s, prix, dir)] triés
        self.sym, self.t0, self.n, self.max_lev = sym, t0, n, max_lev
        self.B = ext
        self.buy_t, self.buy_p, self.sell_t, self.sell_p = [], [], [], []
        P = array("d", [0.0]) * n
        k, last = 0, 0.0
        for i in range(n):
            end = t0 + i + 1
            while k < len(prints) and prints[k][0] < end:
                ts, px, d = prints[k]
                last = px
                if d > 0:
                    self.buy_t.append(ts)
                    self.buy_p.append(px)
                else:
                    self.sell_t.append(ts)
                    self.sell_p.append(px)
                k += 1
            P[i] = last
        # les prints avant t0 comptent pour l'exécution mais pas pour la grille : on les a ignorés ci-dessus
        self.P = P
        self._cache = {}

    def start_index(self):
        """Premier index où B et P existent."""
        for i in range(self.n):
            if self.B[i] > 0 and self.P[i] > 0:
                return i
        return self.n

    def gap(self, w):
        if w in self._cache:
            return self._cache[w]
        g = array("d", [0.0]) * self.n
        B, P = self.B, self.P
        for i in range(w, self.n):
            b0, p0 = B[i - w], P[i - w]
            if b0 > 0 and p0 > 0 and B[i] > 0 and P[i] > 0:
                g[i] = 1e4 * (math.log(B[i] / b0) - math.log(P[i] / p0))
        self._cache[w] = g
        return g

    def mmr(self):
        return 0.5 / self.max_lev


def synthetic_series(lag, seconds=20000, seed=5, sigma_bps=3.0, print_every=2, half_spread_bps=0.5):
    """Binance = marche aléatoire (sigma bps par seconde) ; perp = Binance retardé de `lag` secondes, avec un trade
    toutes les `print_every` secondes, alternant acheteur (au ask) et vendeur (au bid)."""
    rnd = random.Random(seed)
    B = array("d", [0.0]) * seconds
    px = 100.0
    for i in range(seconds):
        px *= 1.0 + rnd.gauss(0.0, sigma_bps) * 1e-4
        B[i] = px
    prints = []
    for i in range(seconds):
        if i % print_every == 0 and i - lag >= 0:
            mid = B[i - lag]
            d = 1 if (i // print_every) % 2 == 0 else -1
            prints.append((float(i) + 0.5, mid * (1 + d * half_spread_bps * 1e-4), d))
    return Series("SYN", 0, seconds, B, prints)


def fill(S, i_sig, side, H, delay=1.0, maxwait=60.0, leverage=1.0, cost_bps=COST_BPS):
    """Aller-retour. None si pas de fill (entrée ou sortie) ; sinon dict."""
    t_sig = S.t0 + i_sig + 1
    te_target = t_sig + delay
    et, ep = (S.buy_t, S.buy_p) if side > 0 else (S.sell_t, S.sell_p)
    k = bisect.bisect_left(et, te_target)
    if k >= len(et) or et[k] > te_target + maxwait:
        return None
    te, pe = et[k], ep[k]
    xt, xp = (S.sell_t, S.sell_p) if side > 0 else (S.buy_t, S.buy_p)
    j = bisect.bisect_left(xt, te + H)
    if j >= len(xt) or xt[j] > te + H + maxwait:
        return None
    tx, px = xt[j], xp[j]
    ret = side * (px / pe - 1.0) * 1e4 - cost_bps
    liq = False
    if leverage > 1.0:
        a, b = max(0, int(te - S.t0)), min(S.n, int(tx - S.t0) + 1)
        seg = [v for v in S.P[a:b] if v > 0]
        m = S.mmr()
        if seg:
            if side > 0:
                liq = min(seg) <= pe * (1 - (1.0 / leverage - m) / (1.0 - m))
            else:
                liq = max(seg) >= pe * (1 + (1.0 / leverage - m) / (1.0 + m))
    margin_ret = -1.0 if liq else leverage * ret / 1e4
    return {"te": te, "tx": tx, "side": side, "ret_bps": ret, "margin_ret": margin_ret, "liq": liq, "sym": S.sym}


def candidates(S, w, theta, i0, i1):
    g = S.gap(w)
    return [i for i in range(max(i0, w), i1) if abs(g[i]) > theta]


def run_strategy(S, w, theta, H, i0, i1, leverage=1.0, cost_bps=COST_BPS):
    g = S.gap(w)
    out, busy, nofill = [], 0.0, 0
    for i in candidates(S, w, theta, i0, i1):
        if S.t0 + i + 1 < busy:
            continue
        side = 1 if g[i] > 0 else -1
        t = fill(S, i, side, H, leverage=leverage, cost_bps=cost_bps)
        if t is None:
            nofill += 1
            continue
        t["g"] = g[i]
        out.append(t)
        busy = t["tx"]
    return out, nofill


def random_baseline(S, counts_n, H, i0, i1, draws, seed, w=5):
    rnd = random.Random(seed)
    res = []
    lo = max(i0, S.start_index() + w)
    for _ in range(draws):
        rets, busy, tries = [], 0.0, 0
        while len(rets) < counts_n and tries < counts_n * 40:
            tries += 1
            i = rnd.randrange(lo, max(lo + 1, i1))
            if S.t0 + i + 1 < busy:
                continue
            t = fill(S, i, rnd.choice((-1, 1)), H)
            if t is not None:
                rets.append(t["ret_bps"])
                busy = t["tx"]
        if rets:
            res.append(sum(rets) / len(rets))
    return res


def stats(trades):
    n = len(trades)
    if n == 0:
        return {"n": 0, "mean": 0.0, "t": 0.0, "win": 0.0, "best_share": 0.0}
    r = [t["ret_bps"] for t in trades]
    m = sum(r) / n
    sd = statistics.stdev(r) if n > 1 else 0.0
    pos = sum(x for x in r if x > 0)
    return {"n": n, "mean": m, "t": m / (sd / math.sqrt(n)) if sd > 0 else 0.0, "win": sum(1 for x in r if x > 0) / n,
            "best_share": (max(r) / pos) if pos > 0 else 0.0}


def corr_at(x, y, k):
    """corr(x[t], y[t-k]) pour k >= 0 ; k < 0 : corr(x[t-|k|], y[t])."""
    if k >= 0:
        a, b = x[k:], y[:len(y) - k]
    else:
        a, b = x[:len(x) + k], y[-k:]
    n = min(len(a), len(b))
    a, b = a[:n], b[:n]
    sa, sb = sum(a), sum(b)
    saa, sbb = sum(map(operator.mul, a, a)), sum(map(operator.mul, b, b))
    sab = sum(map(operator.mul, a, b))
    ma, mb = sa / n, sb / n
    va, vb, cv = saa / n - ma * ma, sbb / n - mb * mb, sab / n - ma * mb
    if va <= 0 or vb <= 0:
        return 0.0, 0.0, n
    return cv / math.sqrt(va * vb), cv / vb, n


def resampled_returns(S, i0, i1, step):
    """Rendements (bps) du perp et de Binance sur des pas de `step` secondes, séries alignées."""
    rp, rb = [], []
    prev = None
    for i in range(i0, i1 - step + 1, step):
        j = i + step - 1
        if S.B[j] <= 0 or S.P[j] <= 0:
            prev = None
            continue
        cur = (S.P[j], S.B[j])
        if prev is not None:
            rp.append(1e4 * math.log(cur[0] / prev[0]))
            rb.append(1e4 * math.log(cur[1] / prev[1]))
        prev = cur
    return rp, rb


def xcorr_table(S, i0, i1, step, lags_s):
    rp, rb = resampled_returns(S, i0, i1, step)
    out = []
    for L in lags_s:
        c, slope, n = corr_at(rp, rb, L // step)
        t = c * math.sqrt(max(n - 2, 1)) / math.sqrt(max(1 - c * c, 1e-12))
        out.append((L, c, slope, t, n))
    return out


# ── données réelles ───────────────────────────────────────────────────────

def date_s(s):
    y, m, d = (int(x) for x in s.split("-"))
    return calendar.timegm((y, m, d, 0, 0, 0))


def load_series(sym, bsym, t0, t1, hist, ext, long_is_buyer=True, max_lev=10.0):
    n = t1 - t0
    B = array("d", [0.0]) * n
    last = 0.0
    seen = set()
    with open(os.path.join(ext, bsym + "_1s.csv")) as f:
        next(f)
        for line in f:
            p = line.split(",")
            s = int(p[0]) // 1000 - t0
            if 0 <= s < n:
                B[s] = float(p[2])
                seen.add(s)
    for i in range(n):
        if B[i] > 0:
            last = B[i]
        elif last > 0:
            B[i] = last
    prints = []
    with open(os.path.join(hist, sym + "_trades.csv")) as f:
        next(f)
        for line in f:
            p = line.rstrip("\n").split(",")
            if p[5] == "1":
                continue
            ts = int(p[0]) / 1000.0
            if ts < t1 + 3600:
                d = 1 if (p[2] == "long") == long_is_buyer else -1
                prints.append((ts, float(p[3]), d))
    prints.sort(key=lambda x: x[0])
    # les prints d'avant t0 servent seulement à initialiser P : on les garde avec leur ts réel
    S = Series(sym, t0, n, B, [p for p in prints if p[0] >= t0] , max_lev)
    return S


def normal_cdf(x):
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


PAIRS = [("BTC-USD", "BTCUSDT", 50.0), ("ETH-USD", "ETHUSDT", 50.0), ("SOL-USD", "SOLUSDT", 20.0),
         ("XRP-USD", "XRPUSDT", 20.0), ("HYPE-USD", "HYPEUSDT", 20.0)]


def build_all(a):
    t0 = date_s(a.start)
    t1 = date_s(a.end) if a.end else None
    series = []
    for sym, bs, lev in PAIRS:
        # fin des données : plus petit dernier ts commun
        with open(os.path.join(a.ext, bs + "_1s.csv")) as f:
            last = None
            for last in f:
                pass
        tb = int(last.split(",")[0]) // 1000
        end = tb if t1 is None else min(t1, tb)
        series.append((sym, bs, lev, end))
    t_end = min(e for _, _, _, e in series)
    return [load_series(sym, bs, t0, t_end, a.hist, a.ext, True, lev) for sym, bs, lev, _ in series], t0, t_end


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", default="search", choices=["xcorr", "search"])
    ap.add_argument("--start", default="2026-09-14")
    ap.add_argument("--end", default=None)
    ap.add_argument("--train-end", default="2026-09-26")
    ap.add_argument("--val-end", default="2026-10-01")
    ap.add_argument("--hist", default="data/hist")
    ap.add_argument("--ext", default="data/ext")
    ap.add_argument("--draws", type=int, default=100)
    ap.add_argument("--m-tests", type=int, default=7)
    ap.add_argument("--out", default="results/leadlag_report.txt")
    a = ap.parse_args(argv)
    out = []
    P = lambda s="": out.append(s)
    series, t0, t_end = build_all(a)
    i_tr, i_va = date_s(a.train_end) - t0, date_s(a.val_end) - t0
    n = series[0].n
    P("FAMILLE D (décalage avec Binance spot), crypto : %s ; données du %s au %s UTC" % (", ".join(s.sym for s in series), a.start,
      __import__("time").strftime("%Y-%m-%d %H:%M", __import__("time").gmtime(t_end))))
    P("Fenêtres : train < %s, validation %s -> %s, test >= %s. Coût ajouté 12 bps (8 frais + 4 slippage) en plus du spread payé sur les prix imprimés."
      % (a.train_end, a.train_end, a.val_end, a.val_end))
    P("")
    if a.mode == "xcorr":
        P("== Corrélation croisée (train + validation seulement) : corr(rendement perp(t), rendement Binance(t - L)), L > 0 : Binance mène")
        P("  pente = bps de perp par bps de Binance ; implication = pente x 10 bps (mouvement Binance de 10 bps) ; coût aller-retour taker ~ 12 bps + spread")
        for step, lags in ((1, [-10, -5, -2, -1, 1, 2, 3, 5, 10]), (5, [-300, -60, -30, -10, 5, 10, 30, 60, 120, 300])):
            P("  résolution %d s :" % step)
            for S in series:
                tab = xcorr_table(S, S.start_index(), i_va, step, lags)
                P("    %-9s " % S.sym + " ".join("L=%+d:%.3f" % (L, c) for L, c, sl, t, nn in tab))
            P("    pente moyenne sur les symboles, implication pour 10 bps de Binance (bps de perp) :")
            for k, L in enumerate(lags):
                sl = statistics.fmean(xcorr_table(S, S.start_index(), i_va, step, [L])[0][2] for S in series)
                P("      L=%+4d s : pente %.3f -> %.2f bps" % (L, sl, sl * 10))
        text = "\n".join(out) + "\n"
        print(text)
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(text)
        return
    ws, thetas, hs = [5, 15, 60], [5, 10, 20], [10, 30, 120]
    win = {"train": (0, i_tr), "val": (i_tr, i_va), "test": (i_va, n)}

    def pooled(w, th, H, name, lev=1.0):
        tr, nf = [], 0
        for S in series:
            t, f = run_strategy(S, w, th, H, win[name][0], win[name][1], lev)
            tr += t
            nf += f
        return tr, nf

    rows = []
    for w in ws:
        for th in thetas:
            for H in hs:
                tr, nf = pooled(w, th, H, "train")
                rows.append((w, th, H, stats(tr), nf))
    P("== Train : %d points testés" % len(rows))
    elig = [r for r in rows if r[3]["n"] >= 30]
    P("  éligibles (>= 30 trades) : %d/%d ; net moyen > 0 : %d" % (len(elig), len(rows), sum(1 for r in elig if r[3]["mean"] > 0)))
    for w, th, H, s, nf in sorted(rows, key=lambda r: -r[3]["mean"])[:10]:
        P("    w=%d theta=%d H=%d : %d trades (sans fill %d), net moyen %+.1f bps (t %.2f, win %.0f %%)" % (w, th, H, s["n"], nf, s["mean"], s["t"], 100 * s["win"]))
    if not elig:
        P("Aucun point éligible : arrêt (validation et test non touchés).")
    else:
        top = sorted(elig, key=lambda r: -r[3]["mean"])[:3]
        P("")
        P("== Top 3 de train confirmés sur validation")
        best, bv = None, -1e18
        for w, th, H, s, nf in top:
            tr, _ = pooled(w, th, H, "val")
            v = stats(tr)
            P("    w=%d theta=%d H=%d : train %+.1f bps (%d) | validation %+.1f bps (%d trades, t %.2f)" % (w, th, H, s["mean"], s["n"], v["mean"], v["n"], v["t"]))
            if v["n"] >= 10 and v["mean"] > bv:
                bv, best = v["mean"], (w, th, H)
        P("  Points évalués : %d (train) + 3 (validation) + 1 (test, une seule fois)." % len(rows))
        if best is None:
            P("Aucun des 3 n'a >= 10 trades en validation : pas de point final, test non touché.")
        else:
            w, th, H = best
            P("  Point final : w=%d s, theta=%d bps, H=%d s" % (w, th, H))
            P("")
            res = {}
            for name in ("train", "val", "test"):
                tr, nf = pooled(w, th, H, name)
                res[name] = tr
                s = stats(tr)
                lg, sh = stats([t for t in tr if t["side"] > 0]), stats([t for t in tr if t["side"] < 0])
                counts = {S.sym: sum(1 for t in tr if t["sym"] == S.sym) for S in series}
                draws = []
                per = [random_baseline(S, counts[S.sym], H, win[name][0], win[name][1], a.draws, 1, w) for S in series if counts[S.sym]]
                for d in range(min((len(x) for x in per), default=0)):
                    tot = sum(counts[S.sym] * x[d] for S, x in zip([S for S in series if counts[S.sym]], per))
                    draws.append(tot / max(1, sum(counts.values())))
                beat = 100.0 * sum(1 for d in draws if s["mean"] > d) / len(draws) if draws else float("nan")
                P("== %s : %d trades (sans fill %d), net moyen %+.1f bps (t %.2f, win %.0f %%), meilleur trade = %.0f %% des gains" % (
                    name.upper() if name != "test" else "TEST (évalué une seule fois)", s["n"], nf, s["mean"], s["t"], 100 * s["win"], 100 * s["best_share"]))
                P("     longs : %d trades, %+.1f bps (t %.2f) | shorts : %d trades, %+.1f bps (t %.2f)" % (lg["n"], lg["mean"], lg["t"], sh["n"], sh["mean"], sh["t"]))
                if draws:
                    sd = sorted(draws)
                    P("     entrées aléatoires de même rythme (%d tirages) : net moyen %+.1f bps [p5 %+.1f, p95 %+.1f] ; la stratégie fait mieux que %.0f %% des tirages"
                      % (len(draws), statistics.fmean(draws), sd[len(sd) // 20], sd[len(sd) * 19 // 20], beat))
                if tr:
                    P("     écart moyen |g| à l'entrée %.1f bps ; durée moyenne en position %.0f s" % (statistics.fmean(abs(t["g"]) for t in tr), statistics.fmean(t["tx"] - t["te"] for t in tr)))
            P("")
            P("== Levier (point final ; descriptif, non compté dans M) : rendement moyen par trade sur la MARGE, liquidations, coût en % de la marge")
            for name in ("val", "test"):
                for L in (1, 2, 3, 5, 10):
                    tr, _ = pooled(w, th, H, name, float(L))
                    if tr:
                        mr = [t["margin_ret"] for t in tr]
                        P("    %-4s L=%-2d : %d trades, rendement moyen sur marge %+.3f %%, pire %+.1f %%, liquidations %d, coût (12 bps) x L = %.2f %% de la marge"
                          % (name, L, len(tr), 100 * statistics.fmean(mr), 100 * min(mr), sum(1 for t in tr if t["liq"]), COST_BPS * L / 100.0))
            st, sv = stats(res["test"]), stats(res["val"])
            p = 1 - normal_cdf(st["t"]) if st["n"] > 1 else 1.0
            P("")
            P("== Verdict (net moyen > 0 en validation ET test avec >= 30 trades en test ; Bonferroni M=%d ; bat >= 75 %% des tirages ; longs et shorts >= 0)" % a.m_tests)
            P("  validation %+.1f bps (%d), test %+.1f bps (%d trades), t test %.2f, p unilatérale %.4f, p x M = %.4f" % (sv["mean"], sv["n"], st["mean"], st["n"], st["t"], p, min(1.0, p * a.m_tests)))
            ok = sv["mean"] > 0 and st["mean"] > 0 and st["n"] >= 30 and p * a.m_tests < 0.05
            P("  RÉSULTAT : %s" % ("POSITIF selon les critères (à confirmer sur temps neuf)" if ok else "NÉGATIF ou NON CONCLUANT : pas de code d'exécution"))
    text = "\n".join(out) + "\n"
    print(text)
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(text)


if __name__ == "__main__":
    main()
