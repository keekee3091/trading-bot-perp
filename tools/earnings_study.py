"""H4 : résultats trimestriels (8-K Item 2.02 de la SEC) et prix ajustés Tiingo. Étage 1, sans coûts.

Grille, règles et critères FIXÉS avant résultat dans CLAUDE.md (« Pré-enregistrement : H4 »). Modes : plan, power (n'utilise QUE les
rendements, jamais une relation), run (étage 1 complet avec placebos et FDR), events (comptes d'événements et exclusions).
Événement : heure d'acceptation EDGAR (UTC) convertie en heure de l'Est (avec heure d'été). Avant l'ouverture (< 9:30) : jour de réaction E = premier
jour de cotation >= date de dépôt ; après la clôture (>= 16:00) : E = premier jour de cotation > date de dépôt ; dépôt un jour sans cotation : E = premier
jour de cotation suivant ; PENDANT la séance (9:30-16:00 un jour de cotation) : exclu. Fenêtre de réaction = clôture(E-1) -> clôture(E). Ambigu et exclu :
date de l'événement déclarée (reportDate) différente de la date de dépôt (communiqué probablement antérieur). Biais de survie : univers actuel de Polymarket.
Licence Tiingo « Internal Use Only » : seulement des statistiques agrégées en sortie. stdlib uniquement.
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
import stocks_study as ss  # noqa: E402

NAN = float("nan")
DISC_END = ss.DISC_END
GROUPS = ("BMO", "AMC", "ALL")
H4A_Y = ("d5", "d10", "d20")
H4B_Y = ("react", "d5")
HOLD = {"d5": 5, "d10": 10, "d20": 20, "react": 1}
CAL_HOURS_PER_DAY = 24.0 * 7 / 5                 # un jour de cotation = 33.6 heures de funding en moyenne
SKIP_TICKERS = {"STRC"}                          # même CIK que MSTR (actions de préférence de Strategy) : doublon


# ---------------------------------------------------------------- dates et classification
def parse_utc(s):
    return dt.datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S")


def et_local(u):
    """Heure de l'Est (naïve) d'un instant UTC (naïf). Heure d'été : du 2e dimanche de mars 2:00 EST (07:00 UTC) au 1er dimanche de novembre 2:00 EDT (06:00 UTC)."""
    y = u.year
    m1 = dt.date(y, 3, 1)
    start = dt.datetime.combine(m1 + dt.timedelta((6 - m1.weekday()) % 7) + dt.timedelta(7), dt.time(7, 0))
    n1 = dt.date(y, 11, 1)
    end = dt.datetime.combine(n1 + dt.timedelta((6 - n1.weekday()) % 7), dt.time(6, 0))
    return u - dt.timedelta(hours=4 if start <= u < end else 5)


def reaction_day(local, dates):
    """(groupe, indice du jour de réaction ou None, raison d'exclusion). dates : jours de cotation triés du ticker."""
    pos = bisect.bisect_left(dates, local.date())
    trading = pos < len(dates) and dates[pos] == local.date()
    t = local.time()
    if trading and dt.time(9, 30) <= t < dt.time(16, 0):
        return None, None, "pendant la séance"
    if t < dt.time(9, 30):
        return "BMO", pos, ""
    return "AMC", (pos + 1 if trading else pos), ""


class Stock:
    def __init__(self, ticker, data="data"):
        t = ss.load_tiingo(ticker, data)
        self.ticker, self.dates = ticker, t["date"]
        self.lc = [math.log(c) for c in t["C"]]


def feats(stk, E, until=DISC_END):
    lc = stk.lc
    if E < 62 or E + 20 >= len(lc) or stk.dates[E + 20] >= until:
        return None
    rets = [lc[i] - lc[i - 1] for i in range(E - 61, E - 1)]          # 60 rendements finissant en E-2
    sig = statistics.pstdev(rets) * 1e4
    if sig <= 0:
        return None
    ann = 1e4 * (lc[E] - lc[E - 1])
    pre = 1e4 * (lc[E - 1] - lc[E - 6])
    f = {"sig": sig, "z_ann": ann / sig, "pre_z": pre / (sig * math.sqrt(5)), "react": ann, "react_n": ann / sig,
         "date": stk.dates[E], "E": E}
    for h in (5, 10, 20):
        d = 1e4 * (lc[E + h] - lc[E])
        f["d%d" % h], f["d%d_n" % h] = d, d / (sig * math.sqrt(h))
    return f


def load_events(data="data"):
    ev = []
    with open(os.path.join(data, "sec", "events.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            ev.append(r)
    return ev


def build(data="data", until=DISC_END):
    """Événements classés. Retourne (événements retenus, comptes d'exclusion par raison, comptes par ticker)."""
    ev = load_events(data)
    st = json.load(open(os.path.join(data, "tiingo", "_state.json"), encoding="utf-8"))["tickers"]
    stocks = {t: Stock(t, data) for t, v in st.items() if v.get("status") == "ok" and t not in SKIP_TICKERS}
    kept, excl, per = [], {}, {}
    for r in ev:
        t = r["ticker"]
        if t in SKIP_TICKERS or t not in stocks:
            excl["doublon (même CIK)"] = excl.get("doublon (même CIK)", 0) + 1
            continue
        loc = et_local(parse_utc(r["acceptance_utc"]))
        grp, E, why = reaction_day(loc, stocks[t].dates)
        d = per.setdefault(t, {"n": 0, "kept": 0, "first": r["filing_date"], "last": r["filing_date"]})
        d["n"] += 1
        d["last"] = max(d["last"], r["filing_date"])
        if grp is None:
            excl[why] = excl.get(why, 0) + 1
            continue
        if r["report_date"] and r["report_date"] != loc.date().isoformat():
            excl["ambigu : date de l'événement différente du dépôt"] = excl.get("ambigu : date de l'événement différente du dépôt", 0) + 1
            continue
        if E >= len(stocks[t].dates):
            excl["jour de réaction hors historique"] = excl.get("jour de réaction hors historique", 0) + 1
            continue
        kept.append({"ticker": t, "grp": grp, "E": E, "local": loc, "filing_date": r["filing_date"]})
        d["kept"] += 1
    return kept, excl, per, stocks


def event_feats(kept, stocks, until=DISC_END, shift=None, rng=None):
    out, why = [], {"trop tôt / trop tard pour les fenêtres": 0}
    real = {}
    for e in kept:
        real.setdefault(e["ticker"], []).append(e["E"])
    for e in kept:
        E = e["E"]
        if shift:
            L = rng.randint(*shift) * rng.choice((-1, 1))
            E = E + L
            if any(abs(E - x) <= 3 for x in real[e["ticker"]]) or E < 0 or E >= len(stocks[e["ticker"]].dates):
                continue
        f = feats(stocks[e["ticker"]], E, until)
        if f is None:
            why["trop tôt / trop tard pour les fenêtres"] += 1
            continue
        f.update({"ticker": e["ticker"], "grp": e["grp"]})
        out.append(f)
    return out, why


# ---------------------------------------------------------------- cellules
def planned():
    c = []
    for y in H4A_Y:
        for g in GROUPS:
            c.append(("H4a", "z_ann", y, g))
    for y in H4B_Y:
        for g in GROUPS:
            c.append(("H4b", "pre_z", y, g))
    return c


def select(evs, grp, drop=None):
    return [e for e in evs if (grp == "ALL" or e["grp"] == grp) and e["ticker"] != drop]


def block_id(d):
    return d.year * 12 + d.month


def cell_stats(evs, xk, yk):
    if len(evs) < 100:
        return None
    items = sorted(evs, key=lambda e: (e["date"], e["ticker"]))
    x = [e[xk] for e in items]
    y = [e[yk] for e in items]
    yn = [e[yk + "_n"] if yk + "_n" in e else e[yk] / (e["sig"] * math.sqrt(HOLD[yk])) for e in items]
    blk = [block_id(e["date"]) for e in items]
    inst = gs.Inst("pool")
    inst.cost = ss.COST_RT
    inst.pops[(1, 0)] = (list(range(len(x))), y, blk, gs.rank_avg(yn))
    gs.MIN_OBS = 80
    c = gs.inst_cell(x, inst, 1, False, ss.fold_by_block(sorted(set(blk))), 0)
    if c is None:
        return None
    a = gs.Acc()
    a.add("pool", c)
    return a.result()


def hold_funding(yk):
    return ss.FUND_BPS_H * HOLD[yk] * CAL_HOURS_PER_DAY


def power_cell(evs, yk):
    n = len(evs)
    if n < 100:
        return {"n": n, "mde": NAN, "limit": ss.KAPPA * ss.COST_RT, "ok": False}
    y = [e[yk] for e in evs]
    sig = statistics.pstdev(y)
    by = {}
    for e in evs:
        by.setdefault(block_id(e["date"]), []).append(e[yk])
    kbar = n / len(by)
    dm = [sum(v) / len(v) for v in by.values() if len(v) >= 2]
    rho = max(0.0, (kbar * statistics.pvariance(dm) - sig ** 2) / (sig ** 2 * (kbar - 1))) if kbar > 1 and len(dm) > 2 else 0.0
    n_eff = n / (1 + (kbar - 1) * rho)
    mde = ss.Z_MDE * sig * math.sqrt(2 / (0.1 * n_eff))
    limit = ss.KAPPA * (ss.COST_RT + hold_funding(yk))
    return {"n": n, "n_blocks": len(by), "sigma": sig, "rho": rho, "n_eff": n_eff, "mde": mde, "limit": limit,
            "ok": bool(mde <= limit)}


def run_power(data="data", out="results"):
    kept, excl, per, stocks = build(data)
    evs, why = event_feats(kept, stocks)
    res = {"n_kept": len(kept), "n_with_features": len(evs), "excluded": excl, "cells": {}}
    for hyp, xk, yk, g in planned():
        res["cells"]["|".join((hyp, xk, yk, g))] = power_cell(select(evs, g), yk)
    json.dump(res, open(os.path.join(out, "earnings_power.json"), "w"), indent=1, default=lambda x: None)
    return res


def loso(evs, xk, yk, grp):
    ics = []
    for t in sorted({e["ticker"] for e in evs}):
        r = cell_stats(select(evs, grp, drop=t), xk, yk)
        ics.append(r["ic"] if r else NAN)
    ics = [i for i in ics if i == i]
    return (min(ics), max(ics)) if ics else (NAN, NAN)


def run_all(data="data", out="results", seed=20261009, log=print):
    power = json.load(open(os.path.join(out, "earnings_power.json")))
    kept, excl, per, stocks = build(data)
    evs, _ = event_feats(kept, stocks)
    rng = random.Random(seed)
    plac = []
    for lo_hi in ((10, 40), (41, 120)):
        pe, _ = event_feats(kept, stocks, shift=lo_hi, rng=rng)
        plac.append(pe)
    cells, zpl = {}, []
    for cell in planned():
        hyp, xk, yk, g = cell
        pw = power["cells"]["|".join(cell)]
        rec = {"hyp": hyp, "var": xk, "horizon": yk, "subset": g, "mde": pw.get("mde"), "limit": pw.get("limit")}
        if not pw["ok"]:
            rec["status"] = "sous-puissant"
            cells[cell] = rec
            continue
        r = cell_stats(select(evs, g), xk, yk)
        if r is None:
            rec["status"] = "indisponible"
            cells[cell] = rec
            continue
        rec.update({"status": "included", "n": r["n_obs"], "stat": r["ic"], "se": r["se_jack"], "z": r["z"],
                    "spread_bps": r["spread_bps"], "cost_bps": ss.COST_RT, "tradab": abs(r["spread_bps"]) / ss.COST_RT,
                    "d1": r["d1_bps"], "d10": r["d10_bps"], "fold_a": r["fold_ic"], "fold_b": r["fold_spread"],
                    "stable": int(r["stable"])})
        F = hold_funding(yk)
        rec["leg_ratio"] = max(abs(r["d1_bps"]), abs(r["d10_bps"])) / (ss.COST_RT + F)
        zp = []
        for pe in plac:
            rp = cell_stats(select(pe, g), xk, yk)
            if rp is not None:
                zp.append(rp["z"])
        rec["z_placebo"] = zp
        zpl += [z for z in zp if z == z]
        cells[cell] = rec
    lam = max(1.0, statistics.median(abs(z) for z in zpl) / 0.6745) if zpl else 1.0
    inc = [k for k, v in cells.items() if v["status"] == "included"]
    ps, qs = ss.bh_cal([cells[k]["z"] for k in inc], lam)
    _, qr = ss.bh_cal([cells[k]["z"] for k in inc], 1.0)
    for k, p, q, q0 in zip(inc, ps, qs, qr):
        v = cells[k]
        v.update({"p_cal": p, "q_cal": q, "q_raw": q0, "fdr": int(q == q and q <= 0.05)})
        v["loso_min"] = v["loso_max"] = None
        robust = True
        if v["fdr"]:
            lo, hi = loso(select(evs, "ALL"), k[1], k[2], k[3])
            v["loso_min"], v["loso_max"] = lo, hi
            robust = lo == lo and lo * hi > 0 and (lo > 0) == (v["stat"] > 0)
        v["passes_stage1"] = int(v["fdr"] and v["stable"] and v["tradab"] > 1.0 and robust)
    h4c = run_h4c(kept, data)
    write_outputs(cells, lam, zpl, excl, per, evs, h4c, out)
    return cells, lam, zpl, excl, per, evs, h4c


def run_h4c(kept, data="data"):
    """Perp, nuits d'annonce : bêta et R² de l'écart d'ouverture réel sur le mouvement hors séance, contre les autres nuits."""
    obs, _ = ss.build_h1(data)
    tick = ss.load_map(data)
    ev_days = {}
    for e in kept:
        ev_days.setdefault(e["ticker"], {})
        # jour de réaction réel = date du jour E dans le calendrier du ticker
    stocks = {t: Stock(t, data) for t in set(tick.values())}
    for e in kept:
        ev_days[e["ticker"]][stocks[e["ticker"]].dates[e["E"]]] = e["grp"]
    res = {}
    for g in ("AMC", "BMO", "ALL"):
        ev_rows, other = {}, {}
        for sym, rows in obs.items():
            t = tick[sym]
            for r in rows:
                grp = ev_days.get(t, {}).get(r["date"])
                if grp is not None and (g == "ALL" or grp == g):
                    ev_rows.setdefault(sym, []).append(r)
                elif grp is None:
                    other.setdefault(sym, []).append(r)
        n = sum(len(v) for v in ev_rows.values())
        res[g] = {"n_event": n, "event": ss.h1a(ev_rows, "all") if n >= 10 else None,
                  "other": ss.h1a(other, "all")}
    return res


FIELDS = ["hyp", "var", "horizon", "subset", "status", "n", "stat", "se", "z", "p_cal", "q_cal", "q_raw", "fdr", "fold_a1",
          "fold_a2", "fold_a3", "fold_b1", "fold_b2", "fold_b3", "stable", "spread_bps", "d1", "d10", "cost_bps", "tradab",
          "leg_ratio", "loso_min", "loso_max", "mde", "limit", "z_placebo_1", "z_placebo_2", "passes_stage1"]


def write_outputs(cells, lam, zpl, excl, per, evs, h4c, out):
    with open(os.path.join(out, "earnings_stage1.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(FIELDS)
        for k, v in cells.items():
            row = dict(v)
            for i in range(3):
                row["fold_a%d" % (i + 1)] = v["fold_a"][i] if v.get("fold_a") else None
                row["fold_b%d" % (i + 1)] = v["fold_b"][i] if v.get("fold_b") else None
            zp = (v.get("z_placebo") or []) + [None, None]
            row["z_placebo_1"], row["z_placebo_2"] = zp[0], zp[1]
            w.writerow([ss.fm(row.get(c)) for c in FIELDS])
    with open(os.path.join(out, "earnings_events.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ticker", "events_8k_202", "first_filing", "last_filing", "kept_after_classification", "in_discovery_windows"])
        n_disc = {}
        for e in evs:
            n_disc[e["ticker"]] = n_disc.get(e["ticker"], 0) + 1
        for t, d in sorted(per.items()):
            w.writerow([t, d["n"], d["first"], d["last"], d["kept"], n_disc.get(t, 0)])
    with open(os.path.join(out, "earnings_h4c.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["nights", "n", "beta", "se_date", "se_stock", "r2", "sd_gap_bps", "sd_move_bps"])
        for g, r in h4c.items():
            for lab, k in (("%s annonce" % g, "event"), ("%s autres nuits" % g, "other")):
                x = r[k]
                if x:
                    w.writerow([lab, x["n"]] + [ss.fm(x[c]) for c in ("beta", "se_date", "se_stock", "r2", "sd_gap", "sd_move")])
    ss.write_heatmap(cells, os.path.join(out, "earnings_heatmap.svg"))


def summarize(cells, lam, zpl, excl, per, evs, h4c):
    inc = [v for v in cells.values() if v["status"] == "included"]
    L = ["événements 8-K 2.02 : %d (28 actions avec au moins un) ; retenus après classification : %d ; avec fenêtres complètes avant 2019 : %d" % (
        sum(d["n"] for d in per.values()), sum(d["kept"] for d in per.values()), len(evs))]
    L.append("exclusions : " + " ; ".join("%s : %d" % (k, v) for k, v in excl.items()))
    for g in ("BMO", "AMC"):
        L.append("  groupe %s : %d événements de découverte" % (g, sum(1 for e in evs if e["grp"] == g)))
    L.append("cellules planifiées %d ; sous-puissantes %d ; indisponibles %d ; testées %d" % (
        len(cells), sum(v["status"] == "sous-puissant" for v in cells.values()),
        sum(v["status"] == "indisponible" for v in cells.values()), len(inc)))
    L.append("faux positifs attendus à p<0.05 non corrigé : %.2f" % (0.05 * len(inc)))
    if zpl:
        L.append("placebos (%d z) : p<0.05 %.1f %%, |z| max %.2f, écart-type robuste de z %.2f ; lambda = %.3f" % (
            len(zpl), 100 * sum(gs.phi_p(z) < 0.05 for z in zpl) / len(zpl), max(abs(z) for z in zpl),
            statistics.median(abs(z) for z in zpl) / 0.6745, lam))
    L.append("réel : p<0.05 non corrigé %d ; FDR 5 %% : %d ; stables : %d ; passent l'étage 1 : %d" % (
        sum(gs.phi_p(v["z"]) < 0.05 for v in inc), sum(v["fdr"] for v in inc), sum(v["fdr"] and v["stable"] for v in inc),
        sum(v["passes_stage1"] for v in inc)))
    L += ["", "%-4s %-7s %-6s %-5s %5s %8s %7s %7s %9s %7s %6s %5s %5s %5s" % (
        "hyp", "var", "Y", "grp", "n", "IC", "z", "q_cal", "spread", "d1/d10", "ratio", "stab", "FDR", "pass")]
    for v in sorted(inc, key=lambda v: -abs(v["z"]) if v["z"] == v["z"] else 0):
        L.append("%-4s %-7s %-6s %-5s %5d %+8.4f %7.2f %7.3f %9.1f %3.0f/%-4.0f %6.2f %5d %5d %5d" % (
            v["hyp"], v["var"], v["horizon"], v["subset"], v["n"], v["stat"], v["z"], v["q_cal"], v["spread_bps"], v["d1"],
            v["d10"], v["tradab"], v["stable"], v["fdr"], v["passes_stage1"]))
    L.append("sous-puissantes : " + ", ".join("%s %s %s" % (k[2], k[3], k[0]) for k, v in cells.items() if v["status"] == "sous-puissant"))
    L += ["", "H4c (perp, exploratoire) : écart d'ouverture réel sur mouvement hors séance"]
    for g, r in h4c.items():
        for lab, k in (("annonce", "event"), ("autres", "other")):
            x = r[k]
            if x:
                L.append("  %-3s %-8s n=%4d beta=%.2f (se date %.2f) R2=%.2f ; écart-type du gap %.0f bps, du mouvement %.0f" % (
                    g, lab, x["n"], x["beta"], x["se_date"], x["r2"], x["sd_gap"], x["sd_move"]))
            else:
                L.append("  %-3s %-8s n=%d (trop peu)" % (g, lab, r["n_event"]))
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["plan", "power", "run"], required=True)
    ap.add_argument("--data", default="data")
    ap.add_argument("--out", default="results")
    a = ap.parse_args()
    if a.mode == "plan":
        c = planned()
        print("cellules planifiées (FDR) : %d (H4a %d, H4b %d) ; plus 3 descriptives H4c" % (
            len(c), sum(x[0] == "H4a" for x in c), sum(x[0] == "H4b" for x in c)))
    elif a.mode == "power":
        r = run_power(a.data, a.out)
        print("événements retenus %d, avec fenêtres complètes avant 2019 : %d ; exclusions %s" % (r["n_kept"], r["n_with_features"], r["excluded"]))
        for k, v in r["cells"].items():
            print("%-22s n=%4d MDE=%s limite=%s ok=%s" % (k, v["n"], ss.fm(v["mde"]), ss.fm(v["limit"]), v["ok"]))
        print("retenues : %d sur %d" % (sum(v["ok"] for v in r["cells"].values()), len(r["cells"])))
    else:
        t0 = time.time()
        res = run_all(a.data, a.out)
        text = summarize(*res)
        print(text)
        open(os.path.join(a.out, "earnings_summary.txt"), "w", encoding="utf-8").write(text + "\n")
        print("durée %.0f s" % (time.time() - t0))


if __name__ == "__main__":
    main()
