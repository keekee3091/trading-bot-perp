"""Piste B : horizons longs (détention d'au moins 1 jour). Sélection sur l'historique long des sous-jacents, validation de l'exécution sur le perp plus tard.

Règles FIXÉES avant résultat dans CLAUDE.md et docs/LONG_HORIZON_PREREG.md. Modes :
  power     puissance par cellule (variance des rendements seulement, aucune relation)
  discover  estimation sur l'historique long AVANT 2019 (train <= 2012, validation 2013-2018) : FDR, plis, placebos, rapport effet / coût
  test      LECTURE UNIQUE, refusée avant TEST_DATE et avant MIN_HOLDOUT_DAYS jours de cotation de perp postérieurs au gel (2026-09-28) : test Tiingo
            2019 -> 2026-09-27 des finalistes, puis validation de l'exécution sur le perp (base et funding réalisés contre hypothèses)
Signaux (fermés) : TSM momentum de séries temporelles (signe du rendement des 60 derniers jours, long ou short, par instrument), XSM momentum en coupe
transversale (quintiles, rendement de 120 jours en sautant le dernier mois), XSR inversion en coupe transversale (rendement de 20 jours). Détentions : 1, 5, 20, 60 jours
de cotation, entrée à l'ouverture J, sortie à la clôture J+h-1 (cohérence signal / exécution de P1). La prime de nuit est reprise de P1 (S2a, S2b), non ré-estimée.
Coûts : taker 4 bps x2 + slippage 2 bps x2 + spread 3.5 = 15.5 bps par aller-retour d'une jambe ; funding réel (intérêt payé par les longs, reçu par les shorts) sur la durée.
Biais de survie (univers actuel de Polymarket). Aucune donnée brute Tiingo en sortie. stdlib uniquement.
"""
import argparse
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
import p1_study as p1  # noqa: E402
import stocks_study as ss  # noqa: E402

NAN = float("nan")
TEST_DATE = dt.date(2026, 12, 15)
HOLDOUT_START = dt.date(2026, 9, 28)
MIN_HOLDOUT_DAYS = 40
HORIZONS = (1, 5, 20, 60)
DISC_END = dt.date(2019, 1, 1)
TEST_END = dt.date(2026, 9, 28)
RT_COST = 15.5                       # aller-retour d'une jambe
XS_COST = 4 * 7.75                   # deux jambes fermées puis rouvertes à chaque période
ETFS = ["SPY", "QQQ", "GLD", "SLV", "USO"]
SIGNALS = ("TSM", "XSM", "XSR")
LOCK = os.path.join("results", "long_horizon_test.lock")


def cells():
    return [(s, h) for s in SIGNALS for h in HORIZONS]


def hold_hours(h):
    return h * 24.0 * 7 / 5 - 17.5 if h > 1 else 6.3         # de 9h35 le jour J à 15h55 le jour J+h-1 : jours ouvrés convertis en heures calendaires


# ---------------------------------------------------------------- séries de gains par date
def tsm_series(EP, h, lookback=60, src=None):
    """Par date d'échantillonnage : (gross moyen, coût moyen) sur les instruments avec un signal ; position = signe du rendement des 60 derniers jours."""
    gross, cost = [], []
    n = EP.n
    for t in range(lookback, n - h, h):
        g = []
        c = []
        for i, tk in enumerate(EP.tickers):
            s = t if src is None else src[t]
            if s is None or s < lookback:
                continue
            lr = EP.lr[tk]
            a, b = lr[s], lr[s - lookback]
            f = EP.fwd(i, t, h)
            if not (a == a and b == b and f == f) or a == b:
                continue
            sign = 1.0 if a > b else -1.0
            g.append(sign * f)
            c.append(RT_COST + sign * ss.FUND_BPS_H * hold_hours(h))      # le long paie le funding, le short le reçoit
        if len(g) >= 10:
            gross.append(sum(g) / len(g))
            cost.append(sum(c) / len(c))
    return gross, cost


def xs_series(EP, var, h, sign, src=None):
    out = ss.h2_series(EP, var, h, src)
    g = [sign * r[2] for r in out if r[2] == r[2]]
    return g, [XS_COST] * len(g)


def cell_series(name, h, EP, src=None):
    if name == "TSM":
        return tsm_series(EP, h, src=src)
    if name == "XSM":
        return xs_series(EP, "mom_120s", h, +1.0, src)
    return xs_series(EP, "mom_20", h, -1.0, src)          # XSR : on achète les perdants de 20 jours


def stats(name, h, EP, src=None):
    g, c = cell_series(name, h, EP, src)
    blen = max(1, round(21 / h))
    if len(g) < 20:
        return None
    st = p1.cell_stats(g, c, blen)
    st["ratio"] = st["gross"] / st["cost"] if st["cost"] > 0 else NAN
    return st


def build_panel(data="data", until=DISC_END):
    mp = ss.load_map(data)
    tick = sorted(set(mp.values()) | set(ETFS))
    return p1.ExecPanel(tick, data, until)


# ---------------------------------------------------------------- modes
def run_power(data="data", out="results"):
    EP = build_panel(data)
    res = {}
    for name, h in cells():
        st = stats(name, h, EP)
        if st is None:
            res["%s|%d" % (name, h)] = {"ok": False, "n": 0}
            continue
        limit = 3 * st["cost"]
        res["%s|%d" % (name, h)] = {"n": st["n"], "se_net": st["net_se"], "mde": ss.Z_MDE * st["net_se"], "limit": limit, "cost": st["cost"],
                                    "ok": bool(ss.Z_MDE * st["net_se"] <= limit)}
    json.dump(res, open(os.path.join(out, "long_horizon_power.json"), "w"), indent=1)
    return res


def run_discover(data="data", out="results", seed=20261012):
    power = json.load(open(os.path.join(out, "long_horizon_power.json")))
    EP = build_panel(data)
    rng = random.Random(seed)
    rows, zpl = {}, []
    for name, h in cells():
        key = "%s|%d" % (name, h)
        if not power[key]["ok"]:
            rows[(name, h)] = {"status": "sous-puissant"}
            continue
        st = stats(name, h, EP)
        pz = []
        for mode in ("lag", "shuffle"):
            if name == "TSM":
                g, _ = cell_series(name, h, EP)
                sf = ss.sign_flip(g, 20 if mode == "lag" else 60, random.Random(rng.random()))
                m, se = ss.jk_mean(sf, max(1, round(21 / h)))
            else:
                src = ss.placebo_src(EP, mode, random.Random(rng.random()), h)
                g, _ = cell_series(name, h, EP, src)
                m, se = ss.jk_mean(g, max(1, round(21 / h)))
            pz.append(m / se if se == se and se > 0 else NAN)
        st["placebo_z"] = pz
        zpl += [z for z in pz if z == z]
        st["status"] = "included"
        rows[(name, h)] = st
    lam = max(1.0, statistics.median(abs(z) for z in zpl) / 0.6745) if zpl else 1.0
    inc = [k for k, v in rows.items() if v["status"] == "included"]
    ps = [0.5 * math.erfc((rows[k]["z"] / lam) / math.sqrt(2)) if rows[k]["z"] == rows[k]["z"] else NAN for k in inc]
    qs = gs.bh_q(ps)
    for k, p, q in zip(inc, ps, qs):
        v = rows[k]
        v.update({"p": p, "q": q, "passes": int(q == q and q <= 0.05 and v["stable"] and v["ratio"] > 1.0)})
    # au plus un finaliste par signal : le plus grand rapport effet / coût
    finals = {}
    for s in SIGNALS:
        cand = [(rows[k]["ratio"], k) for k in inc if k[0] == s and rows[k]["passes"]]
        if cand:
            finals[s] = max(cand)[1][1]
    return rows, lam, finals


def write_discover(rows, lam, finals, out):
    with open(os.path.join(out, "long_horizon_discovery.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["signal", "hold_days", "status", "n_periods", "gross_bps", "cost_bps", "net_bps", "net_se", "z", "p", "q", "fold1", "fold2", "fold3",
                    "stable", "ratio", "mde_bps", "placebo_z1", "placebo_z2", "passes", "finalist"])
        for (s, h), v in rows.items():
            if v["status"] != "included":
                w.writerow([s, h, v["status"]])
                continue
            w.writerow([s, h, "included", v["n"]] + [ss.fm(v[k]) for k in ("gross", "cost", "net", "net_se", "z", "p", "q")] + [ss.fm(x) for x in v["folds"]] +
                       [v["stable"], ss.fm(v["ratio"]), ss.fm(v["mde"]), ss.fm(v["placebo_z"][0]), ss.fm(v["placebo_z"][1]), v["passes"], int(finals.get(s) == h)])
    json.dump(finals, open(os.path.join(out, "long_horizon_finalists.json"), "w"))


# ---------------------------------------------------------------- test : lecture unique et gardée
def holdout_days(data="data", symbols=("AAPL-USD", "MSFT-USD", "NVDA-USD")):
    """Jours de cotation postérieurs au gel avec des klines de perp (compte le minimum sur quelques instruments liquides) : critère de données minimal."""
    best = []
    for s in symbols:
        p = os.path.join(data, s + "_1m.csv")
        if not os.path.exists(p):
            return 0
        days = set()
        with open(p, encoding="utf-8") as f:
            next(f)
            for line in f:
                ts = int(line.split(",", 1)[0])
                d = dt.datetime.fromtimestamp(ts / 1000, dt.timezone.utc).date()
                if d >= HOLDOUT_START and d.weekday() < 5:
                    days.add(d)
        best.append(len(days))
    return min(best) if best else 0


def guard(today, n_days, lock_exists):
    """Retourne None si le test est autorisé, sinon la raison du refus."""
    if lock_exists:
        return "le test a déjà été lu une fois (verrou %s) : jamais deux fois" % LOCK
    if today < TEST_DATE:
        return "date de test fixée au %s, aujourd'hui %s" % (TEST_DATE, today)
    if n_days < MIN_HOLDOUT_DAYS:
        return "seulement %d jours de cotation de perp après le gel, %d requis" % (n_days, MIN_HOLDOUT_DAYS)
    return None


def run_test(data="data", out="results", today=None):
    today = today or dt.date.today()
    why = guard(today, holdout_days(data), os.path.exists(LOCK))
    if why:
        raise SystemExit("TEST REFUSÉ : " + why)
    finals = json.load(open(os.path.join(out, "long_horizon_finalists.json")))
    if not finals:
        raise SystemExit("aucun finaliste à la découverte : rien à tester (conclusion négative)")
    open(LOCK, "w").write(str(today))                       # verrou écrit AVANT toute lecture : le test ne se lit qu'une fois
    mp = ss.load_map(data)
    tick = sorted(set(mp.values()) | set(ETFS))
    EP = p1.ExecPanel(tick, data, TEST_END)
    start = next(i for i, d in enumerate(EP.dates) if d >= DISC_END)
    lines = []
    for s, h in finals.items():
        g, c = cell_series(s, h, EP)
        # on ne garde que les dates d'échantillonnage du test (>= 2019-01-01) ; ce sont les dernières valeurs de la série
        n_test = sum(1 for t in range(start, EP.n - h, h))
        g, c = g[-n_test:], c[-n_test:]
        st = p1.cell_stats(g, c, max(1, round(21 / h)))
        lines.append("%s h=%d : brut %+.2f bps, coût %.2f, net %+.2f (se %.2f, z %.2f), plis %s" % (s, h, st["gross"], st["cost"], st["net"], st["net_se"], st["z"],
                                                                                              ["%.2f" % x for x in st["folds"]]))
    text = "\n".join(lines)
    open(os.path.join(out, "long_horizon_test.txt"), "w", encoding="utf-8").write(text + "\n")
    return text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["power", "discover", "test"], required=True)
    ap.add_argument("--data", default="data")
    ap.add_argument("--out", default="results")
    a = ap.parse_args()
    if a.mode == "power":
        r = run_power(a.data, a.out)
        for k, v in r.items():
            print("%-8s n=%4s MDE=%s limite=%s ok=%s" % (k, v.get("n"), ss.fm(v.get("mde")), ss.fm(v.get("limit")), v.get("ok")))
        print("retenues : %d sur %d" % (sum(v["ok"] for v in r.values()), len(r)))
    elif a.mode == "discover":
        rows, lam, finals = run_discover(a.data, a.out)
        write_discover(rows, lam, finals, a.out)
        print("lambda %.3f ; finalistes : %s" % (lam, finals))
        for (s, h), v in rows.items():
            if v["status"] != "included":
                print("  %s %3d : %s" % (s, h, v["status"]))
            else:
                print("  %s %3d : brut %+8.2f coût %6.2f net %+8.2f (se %6.2f, z %6.2f, q %.3f) plis %s stable %d ratio %.2f passe %d" % (
                    s, h, v["gross"], v["cost"], v["net"], v["net_se"], v["z"], v["q"], ["%.1f" % x for x in v["folds"]], v["stable"], v["ratio"], v["passes"]))
    else:
        print(run_test(a.data, a.out))


if __name__ == "__main__":
    main()
