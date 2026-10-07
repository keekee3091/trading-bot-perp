"""Étage 2 : tradabilité d'une cellule qui a passé l'étage 1 (règle simple, sans stop, coûts réels, holdout touché une fois).

Règle pré-enregistrée (CLAUDE.md, « Étage 2 ») : seuil de décile de la variable (estimé sur la fenêtre de découverte,
par instrument, figé) du côté extrême où |rendement moyen de l'étage 1| est le plus grand ; sens = signe de ce
rendement moyen ; sortie à l'horizon h ; une position à la fois par instrument ; pas de stop.
EXÉCUTION (précisée avant tout résultat de l'étage 2, voir CLAUDE.md) : prix imprimés, comme la famille D : entrée au
premier trade d'agresseur du bon côté (acheteur pour acheter) imprimé au moins 1 s après la fin de la minute i (au plus
60 s, sinon pas de fill), sortie au premier trade d'agresseur opposé imprimé au moins 1 s après t_i + h minutes (au plus
300 s, sinon trade abandonné et compté). Le spread est donc payé implicitement ; coûts ajoutés : 2 x 4 bps de frais +
2 x 2 bps de slippage ; funding réel payé ou reçu aux heures pleines traversées. Sensibilité (non décisionnelle) :
exécution à la clôture de la minute (C[i] à C[i+h]) avec le coût aller-retour de l'étage 1.

stdlib uniquement. python tools/grid_stage2.py --cell F7,bn_ret_1,crypto,5 [--m 9]
"""
import argparse
import bisect
import csv
import math
import os
import random
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import grid_stage1 as gs  # noqa: E402

FEE_RT, SLIP_RT = 8.0, 4.0
ENTRY_WAIT_MS, EXIT_WAIT_MS, DELAY_MS = 60000, 300000, 1000


def last_ts(path):
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        f.seek(max(0, f.tell() - 4096))
        line = f.read().decode("utf-8", "ignore").strip().splitlines()[-1]
    return int(line.split(",")[0])


def data_end_ms(group, fam, data):
    ends = []
    for n in gs.GROUPS[group]:
        p = os.path.join(data, "hist", n + "_trades.csv")
        if os.path.exists(p):
            ends.append(last_ts(p))
        if fam == "F7" and n in gs.BN:
            ends.append(last_ts(os.path.join(data, "ext", gs.BN[n] + "_1s.csv")))
        k = os.path.join(data, n + "_1m.csv")
        if os.path.exists(k):
            ends.append(last_ts(k) + 60000)
    return min(ends) // 60000 * 60000


class Book:
    """Trades imprimés d'un instrument, indexés par sens d'agresseur pour l'exécution."""

    def __init__(self, rows):
        self.ts = {1: [], -1: []}
        self.px = {1: [], -1: []}
        for ts, s, _n, p, _q in rows:
            self.ts[s].append(ts)
            self.px[s].append(p)

    def first(self, side, t_min, wait):
        j = bisect.bisect_left(self.ts[side], t_min)
        if j < len(self.ts[side]) and self.ts[side][j] <= t_min + wait:
            return self.ts[side][j], self.px[side][j]
        return None


def fund_cost(inst_fund, t0, t1, side):
    """Funding payé en bps du notionnel entre t0 et t1 (les longs paient si le taux est positif)."""
    if not inst_fund:
        return 0.0
    ts, rate = inst_fund
    lo, hi = bisect.bisect_right(ts, t0), bisect.bisect_right(ts, t1)
    return side * sum(rate[lo:hi])


def trade(inst, book, fund, i, h, side):
    """Un aller-retour exécuté sur prix imprimés. Retourne (t_entrée, bps nets, bps bruts, i_sortie) ou un code d'échec."""
    t_sig = gs.T0_MS + (i + 1) * 60000
    e = book.first(side, t_sig + DELAY_MS, ENTRY_WAIT_MS)
    if e is None:
        return "no_entry"
    x = book.first(-side, t_sig + 60000 * h + DELAY_MS, EXIT_WAIT_MS)
    if x is None:
        return "no_exit"
    gross = side * 1e4 * (x[1] - e[1]) / e[1]
    net = gross - FEE_RT - SLIP_RT - fund_cost(fund, e[0], x[0], side)
    return e[0], net, gross, x[0], e[1]


def run_rule(inst, book, fund, x, h, side, lo, hi, direction, t_from, t_to, fam, group, pick=None):
    """Applique la règle sur [t_from, t_to). pick : liste d'indices imposés (baseline aléatoire)."""
    out, fails = [], {"no_entry": 0, "no_exit": 0}
    busy = -1
    cand = pick if pick is not None else range(max(inst.start, gs.win_lo(fam, group), (t_from - gs.T0_MS) // 60000),
                                              min(gs.G - h - 1, (t_to - gs.T0_MS) // 60000))
    for i in cand:
        if i < busy or not (inst.NT[i] > 0 and inst.S[i] == 1.0 and inst.S[i + h] == 1.0):
            continue
        if pick is None:
            v = x[i]
            if v != v or not ((v >= hi) if direction > 0 else (v <= lo)):
                continue
        r = trade(inst, book, fund, i, h, side)
        if isinstance(r, str):
            fails[r] += 1
            continue
        jx = (r[3] - gs.T0_MS) // 60000
        ext = min(inst.L[i:jx + 1]) if side > 0 else max(inst.H[i:jx + 1])
        out.append((r[0], r[1], r[2], i, max(0.0, side * (r[4] - ext)) / r[4] * 1e4))
        busy = jx + 1
    return out, fails


def stats(tr):
    if not tr:
        return None
    v = [t[1] for t in tr]
    n = len(v)
    m = sum(v) / n
    sd = statistics.pstdev(v) if n > 1 else float("nan")
    t = m / (sd / math.sqrt(n)) if sd == sd and sd > 0 else float("nan")
    top5 = sorted(v, reverse=True)[:5]
    return {"n": n, "mean": m, "sd": sd, "t": t, "gross": sum(t_[2] for t_ in tr) / n, "win": sum(a > 0 for a in v) / n,
            "total": sum(v), "ex5": sum(v) - sum(top5), "p1": 0.5 * math.erfc(t / math.sqrt(2)) if t == t else float("nan")}


def fmt_stats(name, s):
    if s is None:
        return "%-22s aucun trade" % name
    return ("%-22s n=%5d net moyen %+7.2f bps (brut %+7.2f) sd %6.1f t %+6.2f gagnants %4.1f %% total %+9.0f bps "
            "sans les 5 meilleurs %+9.0f" % (name, s["n"], s["mean"], s["gross"], s["sd"], s["t"], 100 * s["win"],
                                              s["total"], s["ex5"]))


def leverage_table(trades, insts, levmax, label):
    """Étude du levier sur une liste de trades (t, net, gross, i, nom). Descriptif."""
    lines = []
    for lev, name in ((1.0, "fixe 1x"), (2.0, "fixe 2x"), (5.0, "fixe 5x"), ("vt10", "vol cible 10 %"),
                      ("vt20", "vol cible 20 %")):
        eq, peak, dd, liq, ret = 1.0, 1.0, 0.0, 0, []
        cost_m = []
        for t, net, gross, i, nm, adverse in sorted(trades, key=lambda a: a[0]):
            inst = insts[nm]
            if isinstance(lev, float):
                m = lev
            else:
                rv = gs._rv(inst, 1440)[i]
                sig = rv / 1e4 * math.sqrt(525600) if rv == rv else float("nan")
                m = min(5.0, (0.10 if lev == "vt10" else 0.20) / sig) if sig == sig and sig > 0 else 1.0
            pl = max(1.0, m)
            mmr = 0.5 / levmax.get(nm, 10.0)
            liq_dist = 1e4 * (1.0 / pl - mmr)
            if adverse >= liq_dist:
                r, liq = -1.0, liq + 1
            else:
                r = m * net / 1e4
            ret.append(r)
            cost_m.append(m * (FEE_RT + SLIP_RT) / 1e4)
            eq *= (1.0 + r)
            peak = max(peak, eq)
            dd = max(dd, 1 - eq / peak)
        n = len(ret)
        lines.append("  %-16s n=%4d rendement moyen par trade sur la marge %+7.3f %% ; coût frais+slippage %6.3f %% de la marge ; "
                     "equity finale %6.3f ; drawdown max %5.1f %% ; liquidations %d" % (
                         name, n, 100 * sum(ret) / max(n, 1), 100 * sum(cost_m) / max(n, 1), eq, 100 * dd, liq))
    return ["Levier (%s, trades chronologiques mis bout à bout, equity de départ 1, sizing sur toute l'equity) :" % label] + lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cell", required=True, help="famille,variable,groupe,horizon")
    ap.add_argument("--m", type=int, default=9, help="nombre total d'évaluations de test pour Bonferroni")
    ap.add_argument("--data", default="data")
    ap.add_argument("--out", default="results")
    ap.add_argument("--draws", type=int, default=200)
    a = ap.parse_args()
    fam, var, group, h = a.cell.split(",")
    h = int(h)
    row = next(r for r in csv.DictReader(open(os.path.join(a.out, "grille_etage1.csv"), encoding="utf-8"))
               if (r["family"], r["variable"], r["group"], r["horizon_min"]) == (fam, var, group, str(h)))
    d1, d10 = float(row["d1_bps"]), float(row["d10_bps"])
    direction = 1 if abs(d10) >= abs(d1) else -1          # côté extrême retenu : haut (1) ou bas (-1)
    mean_ext = d10 if direction > 0 else d1
    side = 1 if mean_ext > 0 else -1                       # sens figé : signe du rendement moyen mesuré à l'étage 1
    freeze_orig = gs.FREEZE_MS
    f_idx = (freeze_orig - gs.T0_MS) // 60000
    end_ms = data_end_ms(group, fam, a.data)
    gs.FREEZE_MS = end_ms
    gs.G = (end_ms - gs.T0_MS) // 60000
    gs.CAL.clear()
    insts = gs.load_group(group, a.data)
    aux = {"NAS100-USD": gs.load_klines("NAS100-USD", a.data)} if group == "equity" else {}
    levmax = {}
    for r in csv.DictReader(open(os.path.join(a.data, "universe_survey.csv"), encoding="utf-8")):
        levmax[r["symbol"]] = float(r["max_leverage"])
    names = [r["instrument"] for r in csv.DictReader(open(os.path.join(a.out, "grille_etage1_instruments.csv"),
                                                          encoding="utf-8"))
             if (r["family"], r["variable"], r["group"], r["horizon_min"]) == (fam, var, group, str(h))]
    res = ["ÉTAGE 2 : cellule %s ; données jusqu'à %s UTC ; holdout à partir de %s UTC" % (
        a.cell, gs.time.strftime("%Y-%m-%d %H:%M", gs.time.gmtime(end_ms / 1000)),
        gs.time.strftime("%Y-%m-%d", gs.time.gmtime(freeze_orig / 1000))),
        "étage 1 : D1 = %+.2f bps, D10 = %+.2f bps, IC %+.4f, z %.1f, coût %.1f bps -> côté %s, sens %s (figé)" % (
            d1, d10, float(row["ic"]), float(row["z"]), float(row["cost_bps"]),
            "haut (x >= décile 9)" if direction > 0 else "bas (x <= décile 1)", "ACHAT" if side > 0 else "VENTE")]
    w0 = gs.T0_MS + gs.win_lo(fam, group) * 60000
    start_day = min(gs.start_day_for(insts[n], fam, var) for n in insts if gs.has_inst_source(
        insts[n], next(nd for f, v, g_, nd, b in gs.SPEC if v == var)))
    w0 = max(w0, gs.T0_MS + start_day * 86400000)
    t_tr_end = w0 + 2 * (freeze_orig - w0) // 3
    windows = [("train", w0, t_tr_end), ("validation", t_tr_end, freeze_orig), ("TEST (holdout)", freeze_orig, end_ms)]
    res.append("fenêtres : train %s -> %s, validation -> %s, test -> %s" % tuple(
        gs.time.strftime("%Y-%m-%d", gs.time.gmtime(t / 1000)) for t in (w0, t_tr_end, freeze_orig, end_ms)))
    per_window = {w: [] for w, _a, _b in windows}
    per_inst_test = {}
    adverse_all = []
    sens = {w: [] for w, _a, _b in windows}
    rng = random.Random(20261007)
    base_draws = {w: [[] for _ in range(a.draws)] for w, _a, _b in windows}
    for n in names:
        inst = insts[n]
        x = gs.make_var(var, inst, insts, aux)
        if x is None:
            continue
        idx, y, _b, _r = gs.build_pop(inst, h, gs.win_lo(fam, group))
        xs_ = sorted(x[i] for i in idx if i < f_idx and x[i] == x[i])
        k = len(xs_)
        if k < gs.MIN_OBS:
            res.append("  %s ignoré (échantillon de découverte trop petit : %d)" % (n, k))
            continue
        lo, hi = xs_[max(int(0.1 * k) - 1, 0)], xs_[min(int(0.9 * k), k - 1)]
        book = Book(inst.rows)
        fts = fr = None
        p = os.path.join(a.data, n + "_funding.csv")
        if os.path.exists(p):
            pts = sorted((int(r[0]), float(r[1]) * 1e4) for r in list(csv.reader(open(p)))[1:])
            fts, fr = [t for t, _ in pts], [v for _, v in pts]
        fund = (fts, fr) if fts else None
        res.append("  %-9s seuils découverte : x <= %.4g (décile bas), x >= %.4g (décile haut) ; n découverte %d" % (n, lo, hi, k))
        for w, t_from, t_to in windows:
            tr, fails = run_rule(inst, book, fund, x, h, side, lo, hi, direction, t_from, t_to, fam, group)
            if fails["no_entry"] or fails["no_exit"]:
                res.append("    %s %s : signaux sans entrée %d, sans sortie %d" % (n, w, fails["no_entry"], fails["no_exit"]))
            per_window[w] += [(t, net, g_, i, n, adv) for t, net, g_, i, adv in tr]
            # sensibilité : exécution à la clôture
            for t, net, g_, i, _adv in tr:
                C = inst.C
                sens[w].append(side * 1e4 * (C[i + h] / C[i] - 1.0) - inst.cost)
            # baseline : mêmes nombres d'entrées, minutes éligibles au hasard dans la fenêtre
            lo_i, hi_i = max(inst.start, (t_from - gs.T0_MS) // 60000), min(gs.G - h - 1, (t_to - gs.T0_MS) // 60000)
            elig = [i for i in range(lo_i, hi_i) if inst.NT[i] > 0 and inst.S[i] == 1.0 and inst.S[i + h] == 1.0]
            if tr and elig:
                for dr in range(a.draws):
                    pk = sorted(rng.sample(elig, min(len(tr), len(elig))))
                    rr, _f = run_rule(inst, book, fund, x, h, side, lo, hi, direction, t_from, t_to, fam, group, pick=pk)
                    base_draws[w][dr] += [t_[1] for t_ in rr]
            if w.startswith("TEST"):
                per_inst_test[n] = [net for _t, net, _g, _i, _adv in tr]
    res.append("")
    res.append("RÉSULTATS (net de frais, slippage et funding réel, prix imprimés) :")
    out = {}
    for w, _a, _b in windows:
        s = stats(per_window[w])
        out[w] = s
        res.append(fmt_stats(w, s))
        sc = sens[w]
        if sc:
            res.append("%-22s sensibilité exécution à la clôture (non décisionnelle) : net moyen %+7.2f bps sur %d trades" % (
                "", sum(sc) / len(sc), len(sc)))
    test = out["TEST (holdout)"]
    res.append("")
    res.append("par instrument (test) : " + " ; ".join("%s n=%d moy %+.1f" % (n, len(v), sum(v) / len(v)) for n, v in
                                                      per_inst_test.items() if v))
    # baseline aléatoire
    bl = [sum(d) / len(d) for d in base_draws["TEST (holdout)"] if d]
    beat = sum(b < test["mean"] for b in bl) / len(bl) if (bl and test) else float("nan")
    if bl:
        res.append("baseline aléatoire (test, %d tirages) : net moyen par trade %+.2f bps [p5 %+.2f, p95 %+.2f] ; la stratégie en bat %.1f %%" % (
            len(bl), sum(bl) / len(bl), sorted(bl)[int(0.05 * len(bl))], sorted(bl)[int(0.95 * len(bl))], 100 * beat))
    for w in ("validation", "TEST (holdout)"):
        res.append("")
        res += leverage_table(per_window[w], insts, levmax, w)
    # critères
    res.append("")
    ok = []
    v_, t_ = out["validation"], test
    c1 = bool(v_ and t_ and v_["mean"] > 0 and t_["mean"] > 0 and t_["n"] >= 30)
    p_bonf = t_["p1"] * a.m if t_ else float("nan")
    c2 = bool(t_ and p_bonf < 0.05)
    c3 = bool(beat == beat and beat >= 0.75)
    c4 = bool(t_ and t_["mean"] >= 0)
    c5 = bool(t_ and t_["ex5"] > 0)
    for lab, c in (("(1) net moyen > 0 en validation ET test, >= 30 trades en test", c1),
                   ("(2) Bonferroni M=%d : p unilatérale x M = %.4g < 0.05" % (a.m, p_bonf), c2),
                   ("(3) bat >= 75 %% des tirages aléatoires (%.0f %%)" % (100 * beat if beat == beat else float('nan')), c3),
                   ("(4) le côté tradé a un net moyen >= 0 en test", c4),
                   ("(5) total sans les 5 meilleurs trades > 0", c5)):
        res.append("critère %s : %s" % (lab, "OUI" if c else "NON"))
        ok.append(c)
    res.append("CONCLUSION : %s" % ("TOUS LES CRITÈRES TENUS" if all(ok) else "NÉGATIVE (règle d'arrêt : aucun code d'exécution)"))
    text = "\n".join(res)
    print(text)
    with open(os.path.join(a.out, "etage2_report.txt"), "w", encoding="utf-8") as f:
        f.write(text + "\n")


if __name__ == "__main__":
    main()
