"""Piste D : différence de funding entre plateformes (Polymarket Perps et Hyperliquid), position neutre au marché formée de deux perps du même actif.

Règles FIXÉES avant résultat dans CLAUDE.md (« Pré-enregistrement : piste D »). Pour un actif présent sur les deux plateformes (appariement par NOM d'actif), on est SHORT
sur la plateforme où le funding moyen des 14 derniers jours est le plus élevé et LONG sur l'autre : le short reçoit le funding de sa plateforme, le long paie celui de la sienne.
Décision chaque lundi 00:00 UTC à partir des seules données antérieures ; position ouverte seulement si l'écart annualisé dépasse theta ; sinon cash.
P&L horaire par unité de notionnel N sur chaque jambe = funding net + base (rendement de la jambe longue moins rendement de la jambe courte) ; coûts aux entrées et sorties ;
coût d'opportunité rf sur les deux marges N/L1 + N/L2 tant qu'une position est ouverte. Excès annualisé sur N, temps à plat compris (cash = 0 par construction).
stdlib uniquement. python tools/funding_xvenue.py
"""
import bisect
import csv
import datetime as dt
import json
import math
import os
import random
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import carry_study as cs  # noqa: E402
import grid_stage1 as gs  # noqa: E402
import stocks_study as ss  # noqa: E402

NAN = float("nan")
HOUR = 3600_000
FREEZE_MS = gs.FREEZE_MS
LOOKBACK_H = 14 * 24
THETA = 0.02                    # seuil annualisé : on n'ouvre que si l'écart de funding dépasse 2 % par an
X_PREMIUM = 0.01
L_REF = 3
POLY_ONE_WAY = 4.0 + 2.0        # frais + slippage ; le demi-spread s'y ajoute
HL_ONE_WAY = 4.5 + 2.0
REF_SPREAD = 3.5                # spread par défaut (bps)
MIN_DAYS = 40


# ---------------------------------------------------------------- séries horaires
class Pair:
    def __init__(self, name, hours, f_poly, f_hl, c_poly, c_hl, hi_poly, lo_poly, hi_hl, lo_hl, meta):
        self.name, self.hours = name, hours
        self.f_poly, self.f_hl, self.c_poly, self.c_hl = f_poly, f_hl, c_poly, c_hl
        self.hi_poly, self.lo_poly, self.hi_hl, self.lo_hl = hi_poly, lo_poly, hi_hl, lo_hl
        self.meta = meta


def hourly_funding(path, tcol=0, rcol=1):
    d = {}
    with open(path, encoding="utf-8") as f:
        r = csv.reader(f)
        next(r)
        for row in r:
            d[int(row[tcol]) // HOUR] = float(row[rcol])
    return d


def load_pair(poly_sym, hl_coin, data="data", rf=None):
    fp = hourly_funding(os.path.join(data, poly_sym + "_funding.csv"))
    fh = hourly_funding(os.path.join(data, "hl", hl_coin.replace(":", "_") + "_funding.csv"))
    gs.G = (FREEZE_MS - gs.T0_MS) // 60000
    perp = gs.load_klines(poly_sym, data)
    ch, hh, lh = {}, {}, {}
    with open(os.path.join(data, "hl", hl_coin.replace(":", "_") + "_1h.csv"), encoding="utf-8") as f:
        r = csv.reader(f)
        next(r)
        for row in r:
            k = int(row[0]) // HOUR
            hh[k], lh[k], ch[k] = float(row[2]), float(row[3]), float(row[4])
    t0 = max(min(fp), min(fh), min(ch), gs.T0_MS // HOUR + perp.start // 60)
    t1 = min(max(fp), max(fh), max(ch), FREEZE_MS // HOUR - 1)
    hours = list(range(t0, t1 + 1))

    def poly_hour(k):
        a = (k * HOUR - gs.T0_MS) // 60000
        if a < 0 or a + 60 > gs.G:
            return NAN, NAN, NAN
        return perp.C[a + 59], max(perp.H[a:a + 60]), min(perp.L[a:a + 60])
    cp, hp, lp = zip(*[poly_hour(k) for k in hours]) if hours else ((), (), ())
    return hours, fp, fh, ch, hh, lh, list(cp), list(hp), list(lp)


def build_pair(name, poly_sym, hl_coin, meta, data="data"):
    hours, fp, fh, ch, hh, lh, cp, hp, lp = load_pair(poly_sym, hl_coin, data)
    return Pair(name, hours, [fp.get(k, NAN) for k in hours], [fh.get(k, NAN) for k in hours], cp, [ch.get(k, NAN) for k in hours],
                hp, lp, [hh.get(k, NAN) for k in hours], [lh.get(k, NAN) for k in hours], meta)


# ---------------------------------------------------------------- simulation
def decide(pair, i, theta=THETA):
    """Position souhaitée à l'indice horaire i d'après les 14 jours qui PRÉCÈDENT i (+1 : short Hyperliquid, long Polymarket ; -1 : l'inverse ; 0 : cash)."""
    if i < LOOKBACK_H:
        return 0, NAN
    d = [pair.f_hl[j] - pair.f_poly[j] for j in range(i - LOOKBACK_H, i) if pair.f_hl[j] == pair.f_hl[j] and pair.f_poly[j] == pair.f_poly[j]]
    if len(d) < LOOKBACK_H * 0.8:
        return 0, NAN
    ann = sum(d) / len(d) * 8760
    return (0 if abs(ann) < theta else (1 if ann > 0 else -1)), ann


def is_monday_midnight(hour_index):
    d = dt.datetime.fromtimestamp(hour_index * 3600, dt.timezone.utc)
    return d.weekday() == 0 and d.hour == 0


def simulate(pair, rf, L_poly=L_REF, L_hl=L_REF, theta=THETA, hl_fee=4.5, hedge_cost_scale=1.0):
    """Retourne la liste des lignes horaires (indice, pos, funding, base, cost, cap) et les épisodes (entrée, sortie, côté, excursions adverses)."""
    rows, episodes = [], []
    pos, ep = 0, None
    one_poly = POLY_ONE_WAY + pair.meta.get("spread_poly", REF_SPREAD) / 2
    one_hl = hl_fee + 2.0 + pair.meta.get("spread_hl", REF_SPREAD) / 2
    for i in range(1, len(pair.hours)):
        k = pair.hours[i]
        cost = 0.0
        if is_monday_midnight(k):
            want, _ann = decide(pair, i, theta)
            if want != pos:
                if pos != 0:
                    cost += (one_poly + one_hl) * hedge_cost_scale / 1e4
                    ep["exit"] = i
                    episodes.append(ep)
                    ep = None
                if want != 0:
                    cost += (one_poly + one_hl) * hedge_cost_scale / 1e4
                    ep = {"entry": i, "side": want}
                pos = want
        fund = base = cap = 0.0
        if pos != 0:
            fp, fh = pair.f_poly[i], pair.f_hl[i]
            if fp == fp and fh == fh:
                fund = (fh - fp) if pos > 0 else (fp - fh)              # le short reçoit son taux, le long paie le sien
            p0, p1, h0, h1 = pair.c_poly[i - 1], pair.c_poly[i], pair.c_hl[i - 1], pair.c_hl[i]
            if p0 == p0 and p1 == p1 and h0 == h0 and h1 == h1 and p0 > 0 and h0 > 0:
                r_poly, r_hl = p1 / p0 - 1.0, h1 / h0 - 1.0
                base = (r_poly - r_hl) if pos > 0 else (r_hl - r_poly)   # jambe longue moins jambe courte
            cap = rf * (1.0 / L_poly + 1.0 / L_hl) / 8760.0
        rows.append((i, pos, fund, base, cost, cap))
    if pos != 0 and ep is not None:
        ep["exit"] = len(pair.hours) - 1
        episodes.append(ep)
    return rows, episodes


def adverse(pair, ep):
    """Excursion défavorable maximale de la jambe qui perd le plus, en fraction du prix d'entrée, sur la durée de l'épisode."""
    a, b = ep["entry"], ep["exit"]
    e_poly, e_hl = pair.c_poly[a], pair.c_hl[a]
    if not (e_poly > 0 and e_hl > 0):
        return NAN
    if ep["side"] > 0:                  # short Hyperliquid (monte = perte), long Polymarket (baisse = perte)
        x1 = max(pair.hi_hl[a:b + 1]) / e_hl - 1.0
        x2 = 1.0 - min(pair.lo_poly[a:b + 1]) / e_poly
    else:
        x1 = max(pair.hi_poly[a:b + 1]) / e_poly - 1.0
        x2 = 1.0 - min(pair.lo_hl[a:b + 1]) / e_hl
    return max(x1, x2)


def liquidation_share(pair, episodes, L):
    dist_p = 1.0 / L - 0.5 / pair.meta.get("maxlev_poly", 10.0)
    dist_h = 1.0 / L - 0.5 / pair.meta.get("maxlev_hl", 10.0)
    dist = min(dist_p, dist_h)
    ex = [adverse(pair, e) for e in episodes]
    ex = [x for x in ex if x == x]
    return (sum(x >= dist for x in ex) / len(ex) if ex else NAN), len(ex)


def summarize_pair(pair, rf_at, **kw):
    rf = rf_at(pair)
    rows, eps = simulate(pair, rf, **kw)
    hrs = len(rows)
    tot = lambda j: sum(r[j] for r in rows)
    funding, basis, cost, cap = tot(2), tot(3), tot(4), tot(5)
    in_pos = sum(1 for r in rows if r[1] != 0)
    ann = lambda x: x / hrs * 8760 if hrs else NAN
    return {"hours": hrs, "in_position_share": in_pos / hrs if hrs else NAN, "funding_ann": ann(funding), "basis_ann": ann(basis), "cost_ann": ann(cost), "cap_ann": ann(cap),
            "excess_ann": ann(funding + basis - cost - cap), "episodes": eps, "rows": rows}


# ---------------------------------------------------------------- bootstrap par semaines
def week_sums(pair, rows):
    t = {}
    for i, pos, fund, base, cost, cap in rows:
        d = dt.datetime.fromtimestamp(pair.hours[i] * 3600, dt.timezone.utc)
        w = d.isocalendar()[0] * 100 + d.isocalendar()[1]
        a = t.setdefault(w, [0.0, 0])
        a[0] += fund + base - cost - cap
        a[1] += 1
    return t


def bootstrap(tabs, weeks, draws=2000, seed=20261012, block=2):
    rng = random.Random(seed)
    out = []
    nb = max(1, len(weeks) - block + 1)
    for _ in range(draws):
        pick = []
        while len(pick) < len(weeks):
            j = rng.randrange(nb)
            pick += weeks[j:j + block]
        pick = pick[:len(weeks)]
        vals = []
        for t in tabs.values():
            s = h = 0.0
            for w in pick:
                a = t.get(w)
                if a:
                    s += a[0]
                    h += a[1]
            if h > 0:
                vals.append(s / h * 8760)
        out.append(sum(vals) / len(vals) if vals else NAN)
    out.sort()
    return out


# ---------------------------------------------------------------- orchestration
SENS_EXCLUDE = ("DRAM", "STRC", "SKHY", "SPCX")
CRYPTO = ("BTC", "ETH", "SOL", "XRP", "HYPE")


def hl_spreads(data="data"):
    """Spread médian (bps) de l'enregistreur inter-plateformes par actif et par plateforme ; vide s'il n'y a pas assez de données."""
    out = {}
    base = os.path.join(data, "xvenue")
    if not os.path.isdir(base):
        return out
    for d in sorted(x for x in os.listdir(base) if len(x) == 10 and x[4] == "-"):
        p = os.path.join(base, d, "pairs.jsonl")
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i % 20:
                    continue
                try:
                    r = json.loads(line)
                    for k in ("hl", "poly"):
                        b, a = r[k]["bids"][0][0], r[k]["asks"][0][0]
                        out.setdefault((r["pair"], k), []).append((a - b) / ((a + b) / 2) * 1e4)
                except (ValueError, KeyError, IndexError):
                    continue
    return {k: statistics.median(v) for k, v in out.items() if len(v) >= 30}


def persistence(pair, rows):
    """Pour chaque semaine en position : le signe de la décision est-il celui de l'écart de funding réalisé cette semaine-là ?"""
    hits = n = 0
    for i, pos, *_r in rows:
        if pos != 0 and is_monday_midnight(pair.hours[i]) and i + 168 <= len(pair.hours):
            d = [pair.f_hl[j] - pair.f_poly[j] for j in range(i, i + 168) if pair.f_hl[j] == pair.f_hl[j] and pair.f_poly[j] == pair.f_poly[j]]
            if d:
                n += 1
                hits += (sum(d) > 0) == (pos > 0)
    return hits, n


def worst_30d(pairs_rows):
    """Pire somme glissante de 30 jours de la base moyenne journalière (moyenne sur les instruments en position), fenêtres d'au moins 25 jours."""
    day = {}
    for pair, rows in pairs_rows:
        per = {}
        for i, pos, fund, base, cost, cap in rows:
            if pos != 0:
                per.setdefault(pair.hours[i] // 24, 0.0)
                per[pair.hours[i] // 24] += base
        for d, v in per.items():
            day.setdefault(d, []).append(v)
    ds = sorted(day)
    daily = {d: sum(day[d]) / len(day[d]) for d in ds}
    worst = 0.0
    for d0 in ds:
        win = [daily[d] for d in ds if d0 <= d < d0 + 30]
        if len(win) >= 25:
            worst = min(worst, sum(win))
    return worst


def run(data="data", out="results", log=print):
    import fetch_hl
    spreads = hl_spreads(data)
    costs = gs.load_costs(data)
    surv = {r["symbol"]: r for r in csv.DictReader(open(os.path.join(data, "universe_survey.csv"), encoding="utf-8"))}
    mp = {}
    for m in (fetch_hl.post({"type": "meta"})["universe"], fetch_hl.post({"type": "meta", "dex": "xyz"})["universe"]):
        for u in m:
            mp[u["name"]] = float(u.get("maxLeverage", 10))
    rf = cs.load_rf(data)
    coins = json.load(open(os.path.join(data, "hl", "pairs.json")))
    keep = set(json.load(open(os.path.join(data, "hl", "coins_keep.json"))))
    pairs = []
    for sym, coin in coins:
        if coin not in keep:
            continue
        base = sym.replace("-USD", "")
        alias = "GOOGL" if base == "GOOG" else base
        meta = {"spread_poly": spreads.get((alias, "poly"), (costs[sym] - 12.0) if sym in costs else REF_SPREAD),
                "spread_hl": spreads.get((alias, "hl"), REF_SPREAD), "maxlev_poly": float(surv[sym]["max_leverage"]),
                "maxlev_hl": mp.get(coin, 10.0), "base": base, "crypto": base in CRYPTO}
        p = build_pair(base, sym, coin, meta, data)
        if len(p.hours) >= MIN_DAYS * 24:
            pairs.append(p)
        else:
            log("ignoré (moins de %d jours communs) : %s" % (MIN_DAYS, sym))
    mid_h = int(statistics.median(h for p in pairs for h in p.hours))
    mid = dt.datetime.fromtimestamp(mid_h * 3600, dt.timezone.utc)
    rf_at = lambda p: cs.rf_at(rf, dt.datetime.fromtimestamp(p.hours[len(p.hours) // 2] * 3600, dt.timezone.utc).date())

    def evaluate(sel, **kw):
        res = {p.name: summarize_pair(p, rf_at, **kw) for p in sel}
        tabs = {p.name: week_sums(p, res[p.name]["rows"]) for p in sel}
        weeks = sorted({w for t in tabs.values() for w in t})
        boot = bootstrap(tabs, weeks, draws=1000)
        pt = sum(r["excess_ann"] for r in res.values()) / len(res)
        return res, pt, boot[int(0.025 * len(boot))], boot[int(0.975 * len(boot))]

    res, pt, lo, hi = evaluate(pairs)
    sens = []
    for label, sel, kw in (
            ("theta 0 %", pairs, {"theta": 0.0}), ("theta 5 %", pairs, {"theta": 0.05}), ("frais HL doublés", pairs, {"hl_fee": 9.0}),
            ("crypto seule", [p for p in pairs if p.meta["crypto"]], {}), ("non crypto", [p for p in pairs if not p.meta["crypto"]], {}),
            ("sans DRAM, STRC, SKHY, SPCX", [p for p in pairs if p.name not in SENS_EXCLUDE], {}),
            ("L = 1", pairs, {"L_poly": 1, "L_hl": 1}), ("L = 2", pairs, {"L_poly": 2, "L_hl": 2}),
            ("L = 5", pairs, {"L_poly": 5, "L_hl": 5}), ("L = 10", pairs, {"L_poly": 10, "L_hl": 10})):
        if sel:
            _r, p2, l2, h2 = evaluate(sel, **kw)
            sens.append((label, len(sel), p2, l2, h2))
    halves = []
    for sel in (lambda h: h < mid_h, lambda h: h >= mid_h):
        vals = []
        for p in pairs:
            idx = [x for x in res[p.name]["rows"] if sel(p.hours[x[0]])]
            if len(idx) >= 7 * 24:
                vals.append(sum(x[2] + x[3] - x[4] - x[5] for x in idx) / len(idx) * 8760)
        halves.append(sum(vals) / len(vals) if vals else NAN)
    hits = n = 0
    liq_num = liq_den = 0
    for p in pairs:
        h, m = persistence(p, res[p.name]["rows"])
        hits, n = hits + h, n + m
        share, ne = liquidation_share(p, res[p.name]["episodes"], L_REF)
        if ne:
            liq_num += share * ne
            liq_den += ne
    worst = worst_30d([(p, res[p.name]["rows"]) for p in pairs])
    return {"pairs": pairs, "res": res, "excess": pt, "ci_lo": lo, "ci_hi": hi, "sens": sens, "halves": halves, "persist": (hits, n),
            "liq": (liq_num / liq_den if liq_den else NAN, liq_den), "worst30": worst, "mid": mid}


def verdict(r):
    n = len(r["pairs"])
    pos = sum(1 for v in r["res"].values() if v["excess_ann"] > 0)
    hits, nw = r["persist"]
    crit = {
        "(1) excès net poolé > X = 1 %": r["excess"] > X_PREMIUM,
        "(2) borne basse IC95 > 0": r["ci_lo"] > 0,
        "(3) positif dans les deux moitiés": all(h == h and h > 0 for h in r["halves"]),
        "(4) >= 60 % des instruments positifs": pos >= 0.6 * n,
        "(5) signe de la décision confirmé dans >= 60 % des semaines en position": nw > 0 and hits / nw >= 0.6,
        "(6) part d'épisodes liquidés à L = 3 <= 5 %": r["liq"][0] == r["liq"][0] and r["liq"][0] <= 0.05,
        "(7) pire fenêtre de base de 30 jours >= -3 % de N": r["worst30"] >= -0.03,
    }
    return crit, (r["ci_hi"] - r["ci_lo"]) > 2 * X_PREMIUM, pos


def write(r, out):
    with open(os.path.join(out, "funding_xvenue_instruments.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["asset", "hours", "in_position_share", "funding_ann_pct", "basis_ann_pct", "cost_ann_pct", "capital_cost_ann_pct", "excess_ann_pct", "episodes"])
        for p in r["pairs"]:
            v = r["res"][p.name]
            w.writerow([p.name, v["hours"], ss.fm(v["in_position_share"])] + [ss.fm(100 * v[k]) for k in ("funding_ann", "basis_ann", "cost_ann", "cap_ann", "excess_ann")] + [len(v["episodes"])])
    with open(os.path.join(out, "funding_xvenue_sensitivity.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["setting", "n_instruments", "excess_ann_pct", "ci_lo_pct", "ci_hi_pct"])
        w.writerow(["reference (L=3, theta 2 %, frais HL 4,5 bps)", len(r["pairs"]), ss.fm(100 * r["excess"]), ss.fm(100 * r["ci_lo"]), ss.fm(100 * r["ci_hi"])])
        for label, n, p, lo, hi in r["sens"]:
            w.writerow([label, n] + [ss.fm(100 * x) for x in (p, lo, hi)])


def main():
    r = run()
    write(r, "results")
    crit, inconc, pos = verdict(r)
    L = ["PISTE D : %d instruments, moitiés séparées au %s" % (len(r["pairs"]), r["mid"].date()),
         "référence (L = 3 sur chaque plateforme, theta 2 %%, frais HL 4,5 bps) : excès net poolé %+.2f %% par an, IC95 [%+.2f ; %+.2f] (largeur %.2f %%), moitiés %s" % (
             100 * r["excess"], 100 * r["ci_lo"], 100 * r["ci_hi"], 100 * (r["ci_hi"] - r["ci_lo"]), ["%+.2f %%" % (100 * h) for h in r["halves"]]),
         "instruments positifs : %d / %d ; semaines à décision confirmée : %d / %d ; épisodes liquidés à L=3 : %.1f %% (%d épisodes) ; pire fenêtre de base de 30 jours : %+.2f %%" % (
             pos, len(r["pairs"]), r["persist"][0], r["persist"][1], 100 * r["liq"][0], r["liq"][1], 100 * r["worst30"])]
    for k, v in crit.items():
        L.append("  critère %s : %s" % (k, "OUI" if v else "NON"))
    L.append("VERDICT : %s" % ("INCONCLUSIF (intervalle trop large)" if inconc else ("TOUS LES CRITÈRES TENUS" if all(crit.values()) else "NÉGATIF")))
    L.append("composantes moyennes annualisées (par instrument, temps à plat compris) : funding %+.2f %%, base %+.2f %%, coûts %.2f %%, coût du capital %.2f %%" % tuple(
        100 * sum(v[k] for v in r["res"].values()) / len(r["res"]) for k in ("funding_ann", "basis_ann", "cost_ann", "cap_ann")))
    for label, n, p, lo, hi in r["sens"]:
        L.append("  sensibilité %-28s (%2d instr.) : %+.2f %% [%+.2f ; %+.2f]" % (label, n, 100 * p, 100 * lo, 100 * hi))
    text = "\n".join(L)
    print(text)
    open("results/funding_xvenue_summary.txt", "w", encoding="utf-8").write(text + "\n")


if __name__ == "__main__":
    main()
