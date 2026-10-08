"""Piste A : carry de funding avec couverture (short perp, long sous-jacent) hors crypto, net de tous les coûts.

Règles FIXÉES avant résultat dans CLAUDE.md (« Pré-enregistrement : piste A »). Par unité de notionnel N de la jambe longue :
P&L journalier de clôture à clôture = base + funding, base = rendement total du sous-jacent - rendement du prix du perp (les dividendes que le perp
ne verse pas y apparaissent), funding = somme des taux horaires publiés entre deux clôtures (reçu par le short quand positif). Excès net annualisé =
365 x P&L moyen par jour calendaire - coûts aller-retour x 365 / H - rf x (1 + 1/L) (marge non rémunérée) ou - rf (marge rémunérée).
Estimateur poolé : poids égaux entre instruments ; intervalle par bootstrap de blocs de semaines tirés pour tous les instruments à la fois.
Aucune donnée brute Tiingo en sortie (statistiques agrégées seulement). stdlib uniquement.
python tools/carry_study.py
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
import grid_stage1 as gs  # noqa: E402
import stocks_study as ss  # noqa: E402

NAN = float("nan")
FREEZE = dt.date(2026, 9, 28)
LAST_DAY = dt.date(2026, 9, 25)
ETF = {"SP500-USD": "SPY", "NAS100-USD": "QQQ", "GOLD-USD": "GLD", "SILVER-USD": "SLV", "WTIOIL-USD": "USO"}
EQUITIES = ["SPCX", "MU", "SKHY", "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AMD", "INTC", "AVGO", "QCOM", "ARM", "TSM", "ASML",
            "SNDK", "HOOD", "MSTR", "CRCL", "COIN", "RKLB", "LITE", "NBIS", "ORCL", "PLTR"]
EXCLUDED = ["STRC (actions de préférence)", "BABA, ZM (38 jours)", "DRAM, EWY, NCLD, SOXL (sous-jacent non établi)", "BRENTOIL (pas de funding)",
            "SKHYNIX, CXMT, SAMSUNG, UNITREE (absents chez Tiingo)", "DELL, CRWV, CBRS, MRVL (pas de funding)", "toute la crypto"]
REF = {"H": 30, "L": 2, "h": 3.0, "margin": "i"}
X_PREMIUM = 0.01           # prime X fixée d'avance : 1 % par an
GRID_L, GRID_H, GRID_h = (1, 2, 5, 10), (7, 30, 90), (0.0, 1.0, 3.0, 5.0)


# ---------------------------------------------------------------- données
def load_tiingo_full(ticker, data="data"):
    d = {"date": [], "adj": [], "raw": [], "div": []}
    with open(os.path.join(data, "tiingo", ticker + ".csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if float(r["adjClose"]) > 0 and float(r["close"]) > 0:
                d["date"].append(dt.date.fromisoformat(r["date"]))
                d["adj"].append(float(r["adjClose"]))
                d["raw"].append(float(r["close"]))
                d["div"].append(float(r["divCash"]))
    return d


def load_rf(data="data"):
    ds, vs = [], []
    with open(os.path.join(data, "under", "FRED_DTB3.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                v = float(r["value"]) / 100.0
            except ValueError:
                continue
            ds.append(dt.date.fromisoformat(r["date"]))
            vs.append(v)
    return ds, vs


def rf_at(rf, d):
    ds, vs = rf
    j = bisect.bisect_right(ds, d) - 1
    return vs[max(j, 0)]


def load_funding(sym, data="data"):
    p = os.path.join(data, sym + "_funding.csv")
    pts = sorted((int(r[0]), float(r[1])) for r in list(csv.reader(open(p)))[1:])
    return [t for t, _ in pts], [v for _, v in pts]


def funding_between(fund, t0, t1):
    ts, rate = fund
    return sum(rate[bisect.bisect_right(ts, t0):bisect.bisect_right(ts, t1)])


def instrument_list(data="data"):
    mp = ss.load_map(data)
    out = [(sym, tk, "action") for sym, tk in sorted(mp.items()) if tk in EQUITIES]
    for sym, tk in ETF.items():
        out.append((sym, tk, "wti" if sym == "WTIOIL-USD" else "indice_matiere"))
    return out


def build_rows(sym, ticker, perp, tg, fund, rf):
    """Lignes journalières de clôture à clôture. perp : Inst de grid_stage1 (C, H, L par minute) ; tg : série Tiingo complète."""
    rows = []
    D = tg["date"]
    ms = lambda d: (gs.calendar.timegm(d.timetuple()) * 1000 - gs.T0_MS) // 60000
    prev = None
    for k, d in enumerate(D):
        if d >= FREEZE or d > LAST_DAY or d < dt.date(2026, 5, 1):
            continue
        _, cm = ss.session_minutes(d)
        ic = ms(d) + cm - 1
        if ic >= gs.G or ic < perp.start:
            prev = None
            continue
        p = perp.C[ic]
        if not (p > 0):
            prev = None
            continue
        if prev is not None and k > 0 and D[k - 1] == prev["date"]:
            hi = max(perp.H[prev["ic"] + 1:ic + 1])
            lo = min(perp.L[prev["ic"] + 1:ic + 1])
            t0 = gs.T0_MS + (prev["ic"] + 1) * 60000
            t1 = gs.T0_MS + (ic + 1) * 60000
            under = tg["adj"][k] / tg["adj"][k - 1] - 1.0
            rows.append({"date": d, "cal": (d - prev["date"]).days, "p": p, "p_prev": prev["p"], "hi": hi, "lo": lo,
                         "perp_ret": p / prev["p"] - 1.0, "under_ret": under,
                         "raw_ret": tg["raw"][k] / tg["raw"][k - 1] - 1.0, "div": tg["div"][k], "raw_prev": tg["raw"][k - 1],
                         "basis": under - (p / prev["p"] - 1.0), "fund": funding_between(fund, t0, t1),
                         "rf": rf_at(rf, prev["date"])})
        prev = {"ic": ic, "p": p, "date": d}
    return rows


# ---------------------------------------------------------------- comptabilité
def deducts(rows, perp_rt_bps, H, L, h_bps, margin):
    """Coûts annualisés (fraction de N) : frais aller-retour amortis sur H jours + coût d'opportunité du capital."""
    cost = (perp_rt_bps + 2.0 * h_bps) / 1e4 * 365.0 / H
    cal = sum(r["cal"] for r in rows)
    rf = sum(r["rf"] * r["cal"] for r in rows) / cal
    cap = rf * (1.0 + 1.0 / L) if margin == "i" else rf
    return cost, cap, rf


def gross_ann(rows):
    cal = sum(r["cal"] for r in rows)
    return 365.0 * sum(r["basis"] + r["fund"] for r in rows) / cal if cal else NAN


def excess_ann(rows, perp_rt_bps, H, L, h_bps, margin):
    cost, cap, _rf = deducts(rows, perp_rt_bps, H, L, h_bps, margin)
    return gross_ann(rows) - cost - cap


def mmr_of(maxlev):
    return 0.5 / maxlev


def liquidation_share(rows, H, L, maxlev):
    """Part des fenêtres de H jours calendaires (départ chaque jour) où le plus haut du perp dépasse l'entrée de 1/L - mmr (aucun transfert de marge)."""
    dist = 1.0 / L - mmr_of(maxlev)
    n = liq = 0
    for s in range(len(rows)):
        d0 = rows[s]["date"] - dt.timedelta(days=rows[s]["cal"])      # date d'entrée = clôture précédant la ligne s
        p0 = rows[s]["p_prev"]
        hi, e = 0.0, None
        for k in range(s, len(rows)):
            hi = max(hi, rows[k]["hi"])
            if (rows[k]["date"] - d0).days >= H:
                e = k
                break
        if e is None:
            break
        n += 1
        liq += hi / p0 - 1.0 >= dist
    return (liq / n if n else NAN), n


def worst_window_basis(series, H):
    """Pire somme glissante de la base (en fraction de N) sur H jours calendaires."""
    worst = 0.0
    for s in range(len(series)):
        tot = 0.0
        d0 = series[s][0]
        for k in range(s + 1, len(series)):           # position ouverte à la clôture de la ligne s : les P&L comptés sont ceux des lignes suivantes
            tot += series[k][1]
            if (series[k][0] - d0).days >= H:
                worst = min(worst, tot)
                break
    return worst


# ---------------------------------------------------------------- bootstrap par semaines, tous instruments à la fois
def week_of(d):
    y, w, _ = d.isocalendar()
    return y * 100 + w


def prepare_weeks(rows_by):
    tab = {}
    weeks = sorted({week_of(r["date"]) for rows in rows_by.values() for r in rows})
    for s, rows in rows_by.items():
        t = {}
        for r in rows:
            a = t.setdefault(week_of(r["date"]), [0.0, 0])
            a[0] += r["basis"] + r["fund"]
            a[1] += r["cal"]
        tab[s] = t
    return tab, weeks


def pooled_gross(tab, weeks_pick):
    """Moyenne sur les instruments du carry brut annualisé, pour un tirage de semaines (avec répétition)."""
    vals = []
    for s, t in tab.items():
        pn = cal = 0.0
        for w in weeks_pick:
            a = t.get(w)
            if a:
                pn += a[0]
                cal += a[1]
        if cal > 0:
            vals.append(365.0 * pn / cal)
    return sum(vals) / len(vals) if vals else NAN


def bootstrap_gross(tab, weeks, draws=2000, seed=20261008, block=2):
    rng = random.Random(seed)
    out = []
    nb = max(1, len(weeks) - block + 1)
    for _ in range(draws):
        pick = []
        while len(pick) < len(weeks):
            j = rng.randrange(nb)
            pick += weeks[j:j + block]
        out.append(pooled_gross(tab, pick[:len(weeks)]))
    out.sort()
    return out


def run(data="data", out="results", log=print):
    rf = load_rf(data)
    costs = gs.load_costs(data)
    gs.G = (gs.FREEZE_MS - gs.T0_MS) // 60000
    surv = {r["symbol"]: r for r in csv.DictReader(open(os.path.join(data, "universe_survey.csv"), encoding="utf-8"))}
    rows_by, meta = {}, {}
    for sym, tk, cat in instrument_list(data):
        perp = gs.load_klines(sym, data)
        rows = build_rows(sym, tk, perp, load_tiingo_full(tk, data), load_funding(sym, data), rf)
        if len(rows) < 25:
            log("ignoré (moins de 25 jours communs) : %s" % sym)
            continue
        rows_by[sym] = rows
        meta[sym] = {"ticker": tk, "cat": cat, "rt": costs.get(sym, ss.COST_RT), "maxlev": float(surv[sym]["max_leverage"])}
    tab, weeks = prepare_weeks(rows_by)
    boot = bootstrap_gross(tab, weeks)
    ci = lambda off: (boot[int(0.025 * len(boot))] - off, boot[int(0.975 * len(boot))] - off)
    syms = sorted(rows_by)
    n_inst = len(syms)

    def pooled_off(H, L, h, margin):
        offs = [sum(deducts(rows_by[s], meta[s]["rt"], H, L, h, margin)[:2]) for s in syms]
        return sum(offs) / len(offs)

    def pooled_point_exact(H, L, h, margin):
        return sum(gross_ann(rows_by[s]) for s in syms) / n_inst - pooled_off(H, L, h, margin)

    # sensibilité complète (point + intervalle)
    sens = []
    for margin in ("i", "ii"):
        for H in GRID_H:
            for L in GRID_L:
                for h in GRID_h:
                    off = pooled_off(H, L, h, margin)
                    lo, hi = ci(off)
                    sens.append({"margin": margin, "H": H, "L": L, "h_bps": h, "excess": pooled_point_exact(H, L, h, margin), "ci_lo": lo, "ci_hi": hi,
                                 "width": hi - lo})
    ref = next(s for s in sens if (s["margin"], s["H"], s["L"], s["h_bps"]) == (REF["margin"], REF["H"], REF["L"], REF["h"]))
    # moitiés du temps
    alld = sorted({r["date"] for rows in rows_by.values() for r in rows})
    mid = alld[len(alld) // 2]
    halves = []
    for sel in (lambda r: r["date"] < mid, lambda r: r["date"] >= mid):
        sub = {s: [r for r in rows if sel(r)] for s, rows in rows_by.items()}
        sub = {s: r for s, r in sub.items() if len(r) >= 10}
        if not sub:
            halves.append(NAN)
            continue
        vals = [excess_ann(r, meta[s]["rt"], REF["H"], REF["L"], REF["h"], REF["margin"]) for s, r in sub.items()]
        halves.append(sum(vals) / len(vals))
    per_inst = {}
    for s in syms:
        rows = rows_by[s]
        cal = sum(r["cal"] for r in rows)
        fund_ann = 365.0 * sum(r["fund"] for r in rows) / cal
        basis_ann = 365.0 * sum(r["basis"] for r in rows) / cal
        und_ann = 365.0 * sum(r["under_ret"] for r in rows) / cal
        pos = [r["fund"] > 0 for r in rows]
        half = len(rows) // 2
        fr = {"fund_pos_h1": sum(pos[:half]) / max(half, 1), "fund_pos_h2": sum(pos[half:]) / max(len(rows) - half, 1)}
        fh = [(r["fund"], r["cal"]) for r in rows]
        liq, nwin = liquidation_share(rows, REF["H"], REF["L"], meta[s]["maxlev"])
        bstd = statistics.pstdev([r["basis"] for r in rows]) * 1e4
        wk = [r["basis"] for r in rows if r["cal"] > 1]
        wd = [r["basis"] for r in rows if r["cal"] == 1]
        per_inst[s] = {"cat": meta[s]["cat"], "days": len(rows), "cal_days": cal, "fund_ann": fund_ann, "basis_ann": basis_ann, "under_ann": und_ann,
                       "excess_ref": excess_ann(rows, meta[s]["rt"], REF["H"], REF["L"], REF["h"], REF["margin"]),
                       "basis_sd_bps": bstd, "basis_sd_weekend_bps": statistics.pstdev(wk) * 1e4 if len(wk) > 2 else NAN,
                       "basis_sd_weekday_bps": statistics.pstdev(wd) * 1e4 if len(wd) > 2 else NAN, "liq_share_30d_L2": liq, "n_windows": nwin, **fr}
    # base : pire fenêtre de 30 jours de la moyenne poolée par date
    by_date = {}
    for rows in rows_by.values():
        for r in rows:
            by_date.setdefault(r["date"], []).append(r["basis"])
    pooled_basis = [(d, sum(v) / len(v)) for d, v in sorted(by_date.items())]
    worst30 = worst_window_basis(pooled_basis, 30)
    # ex-dividende
    exd = []
    for s in syms:
        for r in rows_by[s]:
            if r["div"] > 0:
                exd.append((r["div"] / r["raw_prev"] * 1e4, (r["perp_ret"] - r["raw_ret"]) * 1e4))
    # catégories (cas de référence)
    cats = {}
    for c in ("action", "indice_matiere", "wti"):
        ks = [s for s in syms if meta[s]["cat"] == c]
        if ks:
            cats[c] = (len(ks), sum(per_inst[s]["excess_ref"] for s in ks) / len(ks))
    vol5 = sorted(syms, key=lambda s: -per_inst[s]["basis_sd_bps"])[:5]
    ex5 = [s for s in syms if s not in vol5]
    ref_ex5 = sum(per_inst[s]["excess_ref"] for s in ex5) / len(ex5)
    tab_x = {k: v for k, v in tab.items() if k != "SPCX-USD"}
    boot_x = bootstrap_gross(tab_x, weeks)
    syms_x = [x for x in syms if x != "SPCX-USD"]
    off_x = sum(sum(deducts(rows_by[x], meta[x]["rt"], REF["H"], REF["L"], REF["h"], REF["margin"])[:2]) for x in syms_x) / len(syms_x)
    ex_spcx = {"excess": sum(gross_ann(rows_by[x]) for x in syms_x) / len(syms_x) - off_x,
               "ci_lo": boot_x[int(0.025 * len(boot_x))] - off_x, "ci_hi": boot_x[int(0.975 * len(boot_x))] - off_x}
    gross_pool = sum(gross_ann(rows_by[x]) for x in syms) / n_inst
    rt_pool = sum(meta[x]["rt"] for x in syms) / n_inst
    rf_pool = sum(deducts(rows_by[x], meta[x]["rt"], 30, 2, 3.0, "i")[2] for x in syms) / n_inst
    return {"ex_spcx": ex_spcx, "gross_pool": gross_pool, "rt_pool": rt_pool, "rf_pool": rf_pool, "syms": syms, "meta": meta, "per_inst": per_inst, "sens": sens, "ref": ref, "halves": halves, "mid": mid, "worst30": worst30,
            "exdiv": exd, "cats": cats, "ref_ex5": ref_ex5, "vol5": vol5, "n_inst": n_inst, "weeks": len(weeks), "rows_by": rows_by}


def write(res, out):
    with open(os.path.join(out, "carry_instruments.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["instrument", "category", "days", "cal_days", "funding_ann_pct", "basis_ann_pct", "underlying_ann_pct", "excess_ref_pct", "basis_sd_bps",
                    "basis_sd_weekend_bps", "basis_sd_weekday_bps", "funding_positive_h1", "funding_positive_h2", "liq_share_30d_L2"])
        for s in res["syms"]:
            p = res["per_inst"][s]
            w.writerow([s, p["cat"], p["days"], p["cal_days"]] + [ss.fm(100 * p[k]) for k in ("fund_ann", "basis_ann", "under_ann", "excess_ref")] +
                       [ss.fm(p[k]) for k in ("basis_sd_bps", "basis_sd_weekend_bps", "basis_sd_weekday_bps", "fund_pos_h1", "fund_pos_h2", "liq_share_30d_L2")])
    with open(os.path.join(out, "carry_pooled.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["margin_case", "H_days", "L_perp", "hedge_bps_per_side", "excess_ann_pct", "ci_lo_pct", "ci_hi_pct", "ci_width_pct"])
        for s in res["sens"]:
            w.writerow([s["margin"], s["H"], s["L"], s["h_bps"]] + [ss.fm(100 * s[k]) for k in ("excess", "ci_lo", "ci_hi", "width")])


def verdict(res):
    ref = res["ref"]
    pi = res["per_inst"]
    pos = sum(1 for s in res["syms"] if pi[s]["excess_ref"] > 0)
    stable = sum(1 for s in res["syms"] if pi[s]["fund_pos_h1"] >= 0.7 and pi[s]["fund_pos_h2"] >= 0.7)
    liq = [pi[s]["liq_share_30d_L2"] for s in res["syms"] if pi[s]["liq_share_30d_L2"] == pi[s]["liq_share_30d_L2"]]
    liq_pool = sum(liq) / len(liq) if liq else NAN
    crit = {
        "(1) excès net poolé > X = 1 %": ref["excess"] > X_PREMIUM,
        "(2) borne basse IC95 > 0": ref["ci_lo"] > 0,
        "(3) positif dans les deux moitiés": all(h == h and h > 0 for h in res["halves"]),
        "(4) >= 60 % des instruments positifs": pos >= 0.6 * res["n_inst"],
        "(5) funding positif >= 70 % des heures dans les deux moitiés pour >= 60 % des instruments": stable >= 0.6 * res["n_inst"],
        "(6) part de fenêtres liquidées à L = 2 <= 5 %": liq_pool == liq_pool and liq_pool <= 0.05,
        "(7) pire fenêtre de base de 30 jours poolée <= 3 % de N": res["worst30"] >= -0.03,
    }
    inconclusive = ref["width"] > 2 * X_PREMIUM
    return crit, inconclusive, pos, stable, liq_pool


def main():
    res = run()
    write(res, "results")
    crit, inconc, pos, stable, liq_pool = verdict(res)
    ref = res["ref"]
    L = ["CARRY (piste A), %d instruments, %d semaines, moitiés séparées au %s" % (res["n_inst"], res["weeks"], res["mid"]),
         "cas de référence (H=30 j, L=2, couverture 3 bps par côté, marge non rémunérée) : excès net poolé %+.2f %% par an, IC95 [%+.2f ; %+.2f] (largeur %.2f %%), moitiés %s" % (
             100 * ref["excess"], 100 * ref["ci_lo"], 100 * ref["ci_hi"], 100 * ref["width"], ["%+.2f %%" % (100 * h) for h in res["halves"]]),
         "instruments positifs : %d / %d ; funding stable : %d / %d ; part de fenêtres liquidées (L=2, 30 j) : %.1f %% ; pire fenêtre de base de 30 jours poolée : %+.2f %%" % (
             pos, res["n_inst"], stable, res["n_inst"], 100 * liq_pool, 100 * res["worst30"]),
         "par catégorie (n, excès net) : %s ; hors les 5 instruments à la base la plus volatile : %+.2f %%" % (
             {c: (n, "%+.2f %%" % (100 * v)) for c, (n, v) in res["cats"].items()}, 100 * res["ref_ex5"])]
    for k, v in crit.items():
        L.append("  critère %s : %s" % (k, "OUI" if v else "NON"))
    L.append("VERDICT : %s" % ("INCONCLUSIF (intervalle trop large)" if inconc else ("TOUS LES CRITÈRES TENUS" if all(crit.values()) else "NÉGATIF")))
    pi = res["per_inst"]
    L.append("funding annuel moyen par catégorie : " + str({c: "%.2f %%" % (100 * statistics.fmean(pi[s]["fund_ann"] for s in res["syms"] if pi[s]["cat"] == c))
                                                          for c in {pi[s]["cat"] for s in res["syms"]}}))
    L.append("base moyenne annuelle par catégorie : " + str({c: "%.2f %%" % (100 * statistics.fmean(pi[s]["basis_ann"] for s in res["syms"] if pi[s]["cat"] == c))
                                                            for c in {pi[s]["cat"] for s in res["syms"]}}))
    if res["exdiv"]:
        L.append("dates ex-dividende dans l'échantillon : %d ; dividende moyen %.1f bps ; (rendement perp - rendement du prix brut du sous-jacent) moyen %.1f bps (si le perp baisse du dividende : ~ 0 ; sinon ~ +dividende)" % (
            len(res["exdiv"]), statistics.fmean(a for a, _ in res["exdiv"]), statistics.fmean(b for _, b in res["exdiv"])))
    L.append("sensibilités (excès poolé %, IC95) pour L=2 marge non rémunérée : " + "; ".join(
        "H=%d h=%g : %+.2f [%+.2f ; %+.2f]" % (s["H"], s["h_bps"], 100 * s["excess"], 100 * s["ci_lo"], 100 * s["ci_hi"]) for s in res["sens"]
        if s["margin"] == "i" and s["L"] == 2 and s["h_bps"] in (0.0, 3.0)))
    L.append("L variable (H=30, h=3, marge non rémunérée) : " + "; ".join("L=%d : %+.2f %%" % (s["L"], 100 * s["excess"]) for s in res["sens"]
                                                                          if s["margin"] == "i" and s["H"] == 30 and s["h_bps"] == 3.0))
    L.append("marge rémunérée (H=30, L=2, h=3) : %+.2f %%" % (100 * next(s["excess"] for s in res["sens"] if s["margin"] == "ii" and s["H"] == 30 and s["L"] == 2 and s["h_bps"] == 3.0)))
    gp, rf_ = res["gross_pool"], res["rf_pool"]
    L.append("carry brut poolé (base + funding) %.2f %% par an ; taux sans risque moyen %.2f %% ; coût aller-retour moyen perp %.1f bps + 2 x 3 bps de couverture" % (
        100 * gp, 100 * rf_, res["rt_pool"]))
    for Lv in (1, 2, 5, 10):
        edge = gp - rf_ * (1 + 1.0 / Lv)
        rt = (res["rt_pool"] + 6.0) / 1e4
        L.append("  L=%d : carry brut moins coût d'opportunité = %+.2f %% par an ; jours de détention pour amortir l'aller-retour : %s" % (
            Lv, 100 * edge, "%.0f" % (rt * 365 / edge) if edge > 0 else "jamais"))
    ex = res["ex_spcx"]
    L.append("sans SPCX (prix du perp plafonné à 300 les 17 et 18 juin 2026, anomalie de démarrage de l'IPO ; sensibilité POST HOC de qualité de données) : excès net %+.2f %% [%+.2f ; %+.2f]" % (
        100 * ex["excess"], 100 * ex["ci_lo"], 100 * ex["ci_hi"]))
    text = "\n".join(L)
    print(text)
    open("results/carry_summary.txt", "w", encoding="utf-8").write(text + "\n")


if __name__ == "__main__":
    main()
