"""H_VRP phase 1 et 3 : indices de stratégie Cboe (put-write) contre le marché, alpha après bêta. Hors Polymarket, sans ordres, stdlib uniquement.

Règles GELÉES dans docs/VRP_PREREG.md (2026-10-10) et « Écarts déclarés ». Données : data/vrp/ (ignoré par git, aucune série brute en sortie).
python tools/vrp_indices.py --mode power   # variance seulement, écrit results/vrp_real_power.csv (verrou : requis avant 'run')
python tools/vrp_indices.py --mode run     # toutes les estimations, lecture unique (verrou results/vrp_real.lock)
"""
import argparse
import bisect
import csv
import datetime as dt
import io
import math
import os
import random
import statistics
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

NAN = float("nan")
M_CURRENT = 11          # Bonferroni de la phase 1 (10 + 1)
M_PHASE3 = 12
X_MONTH = 0.0015
NW_LAGS = 3
CELLS = [("PUT", 0.00115), ("PUTY", 0.00115), ("WPUT", 0.055 * 52 / 12 / 100), ("CNDR", 0.00115)]   # surcoût par point de volatilité et par mois
SECONDARY = ["BXM", "BXMD", "BXY"]
SPECS = {"S1": ["mkt"], "S2": ["mkt", "smb", "hml"], "S3": ["mkt", "smb", "hml", "mom"], "S4": ["mkt", "down"]}
LOCK = os.path.join("results", "vrp_real.lock")


# ---------- chargement ----------
def load_cboe(path):
    out = {}
    with open(path, encoding="utf-8") as f:
        for r in list(csv.reader(f))[1:]:
            try:
                m, d, y = r[0].split("/")
                out[dt.date(int(y), int(m), int(d))] = float(r[1])
            except (ValueError, IndexError):
                continue
    return out


def load_ff(data):
    """Facteurs French mensuels en décimal : {aaaamm: dict(mkt, smb, hml, rf, mom)}."""
    ff = {}
    with zipfile.ZipFile(os.path.join(data, "vrp", "ff3.zip")) as z:
        txt = z.read(z.namelist()[0]).decode("latin-1")
    for line in txt.splitlines():
        p = [x.strip() for x in line.split(",")]
        if len(p) == 5 and len(p[0]) == 6 and p[0].isdigit():
            ff[int(p[0])] = {"mkt": float(p[1]) / 100, "smb": float(p[2]) / 100, "hml": float(p[3]) / 100, "rf": float(p[4]) / 100}
    with zipfile.ZipFile(os.path.join(data, "vrp", "mom.zip")) as z:
        txt = z.read(z.namelist()[0]).decode("latin-1")
    for line in txt.splitlines():
        p = [x.strip() for x in line.split(",")]
        if len(p) == 2 and len(p[0]) == 6 and p[0].isdigit() and int(p[0]) in ff:
            v = float(p[1])
            if v > -99:
                ff[int(p[0])]["mom"] = v / 100
    return {k: v for k, v in ff.items() if "mom" in v}


def prev_ym(ym):
    y, m = divmod(ym, 100)
    return y * 100 + m - 1 if m > 1 else (y - 1) * 100 + 12


def month_end_values(series):
    """{aaaamm: valeur du dernier jour observé du mois} ; mois écarté si ce jour est à plus de 7 jours de la fin du mois."""
    last = {}
    for d in sorted(series):
        last[d.year * 100 + d.month] = d
    out = {}
    for ym, d in last.items():
        nxt = dt.date(d.year + (d.month == 12), d.month % 12 + 1, 1)
        if (nxt - d).days - 1 <= 7:
            out[ym] = series[d]
    return out


def monthly_returns(series):
    me = month_end_values(series)
    return {ym: me[ym] / me[prev_ym(ym)] - 1.0 for ym in me if prev_ym(ym) in me}


# ---------- algèbre et régression ----------
def solve_inv(A):
    n = len(A)
    M = [list(A[i]) + [1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(M[r][c]))
        M[c], M[p] = M[p], M[c]
        piv = M[c][c]
        M[c] = [v / piv for v in M[c]]
        for r in range(n):
            if r != c:
                f = M[r][c]
                if f:
                    M[r] = [a - f * b for a, b in zip(M[r], M[c])]
    return [row[n:] for row in M]


def ols(y, cols):
    """MCO avec constante : (coefficients [alpha, b1...], résidus, (X'X)^-1, X)."""
    n = len(y)
    X = [[1.0] + [c[i] for c in cols] for i in range(n)]
    k = len(X[0])
    XtX = [[sum(X[t][a] * X[t][b] for t in range(n)) for b in range(k)] for a in range(k)]
    inv = solve_inv(XtX)
    Xty = [sum(X[t][a] * y[t] for t in range(n)) for a in range(k)]
    beta = [sum(inv[a][b] * Xty[b] for b in range(k)) for a in range(k)]
    res = [y[t] - sum(beta[a] * X[t][a] for a in range(k)) for t in range(n)]
    return beta, res, inv, X


def nw_se(res, inv, X, lags=NW_LAGS):
    """Erreurs-types Newey-West (Bartlett, sans correction de petit échantillon) de tous les coefficients."""
    n, k = len(X), len(X[0])
    S = [[0.0] * k for _ in range(k)]
    for t in range(n):
        for a in range(k):
            for b in range(k):
                S[a][b] += res[t] ** 2 * X[t][a] * X[t][b]
    for l in range(1, lags + 1):
        w = 1.0 - l / (lags + 1.0)
        for t in range(l, n):
            e = res[t] * res[t - l]
            for a in range(k):
                for b in range(k):
                    S[a][b] += w * e * (X[t][a] * X[t - l][b] + X[t - l][a] * X[t][b])
    V = [[sum(inv[a][c] * S[c][d] * inv[d][b] for c in range(k) for d in range(k)) for b in range(k)] for a in range(k)]
    return [math.sqrt(max(V[a][a], 0.0)) for a in range(k)]


def fit(y, cols):
    beta, res, inv, X = ols(y, cols)
    se = nw_se(res, inv, X)
    n, k = len(y), len(beta)
    sd = math.sqrt(sum(e * e for e in res) / (n - k))
    return {"beta": beta, "se": se, "t": [b / s if s > 0 else NAN for b, s in zip(beta, se)], "sd": sd,
            "se_iid": sd * math.sqrt(inv[0][0]), "n": n}


def mbb_indices(n, block, rng):
    out = []
    while len(out) < n:
        s = rng.randrange(n)
        out += [(s + j) % n for j in range(block)]
    return out[:n]


def boot_alpha_ci(y, cols, draws, rng, block=6):
    n = len(y)
    al = []
    for _ in range(draws):
        ix = mbb_indices(n, block, rng)
        al.append(ols([y[i] for i in ix], [[c[i] for i in ix] for c in cols])[0][0])
    al.sort()
    return al[int(0.025 * draws)], al[min(int(0.975 * draws), draws - 1)]


def phi(x):
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


def bh(pvals, q=0.05):
    """Benjamini-Hochberg : liste de booléens (rejet de H0)."""
    m = len(pvals)
    order = sorted(range(m), key=lambda i: pvals[i])
    kmax = -1
    for r, i in enumerate(order, 1):
        if pvals[i] <= q * r / m:
            kmax = r
    rej = [False] * m
    for r, i in enumerate(order, 1):
        if r <= kmax:
            rej[i] = True
    return rej


# ---------- séries alignées et statistiques ----------
def build_rows(idx_ret, ff, last_ym=202608):
    rows = []
    for ym in sorted(idx_ret):
        if ym in ff and ym <= last_ym:
            f = ff[ym]
            rows.append({"ym": ym, "ret": idx_ret[ym], "y": idx_ret[ym] - f["rf"], "mkt": f["mkt"], "smb": f["smb"], "hml": f["hml"],
                         "mom": f["mom"], "rf": f["rf"], "down": max(-f["mkt"], 0.0)})
    return rows


def cols_of(rows, spec):
    return [[r[c] for r in rows] for c in SPECS[spec]]


def windows(rows):
    n = len(rows)
    h, t = n // 2, n // 3
    return {"full": rows, "half1": rows[:h], "half2": rows[h:], "third1": rows[:t], "third2": rows[t:2 * t], "third3": rows[2 * t:]}


def equity_path(rets):
    e, p = 1.0, [1.0]
    for r in rets:
        e *= 1.0 + r
        p.append(e)
    return p


def dd_stats(rets):
    p = equity_path(rets)
    peak, dd, run, longest = p[0], 0.0, 0, 0
    for x in p:
        if x >= peak:
            peak, run = x, 0
        else:
            run += 1
            longest = max(longest, run)
        dd = max(dd, 1 - x / peak)
    return dd, longest


def perf(rets, rfs):
    n = len(rets)
    ex = [r - f for r, f in zip(rets, rfs)]
    sd = statistics.stdev(ex)
    cagr = equity_path(rets)[-1] ** (12.0 / n) - 1
    dd, longest = dd_stats(rets)
    return {"n": n, "ann_ret": cagr, "ann_vol": sd * math.sqrt(12), "sharpe": statistics.fmean(ex) / sd * math.sqrt(12) if sd > 0 else NAN,
            "worst": min(rets), "maxdd": dd, "dd_len": longest}


def thresholds(rows):
    """Seuils gelés : plus strict de 0,75 x le marché et de la valeur absolue."""
    mk = [r["mkt"] + r["rf"] for r in rows]
    worst_mkt = min(mk)
    dd_mkt = dd_stats(mk)[0]
    return {"worst_min": max(0.75 * worst_mkt, -0.20), "dd_max": min(0.75 * dd_mkt, 0.45), "worst_mkt": worst_mkt, "dd_mkt": dd_mkt}


def tail_stats(x):
    s = sorted(x)
    k = max(1, int(0.05 * len(s)))
    m, sd = statistics.fmean(x), statistics.pstdev(x)
    return {"p1": s[max(0, int(0.01 * len(s)))], "p5": s[int(0.05 * len(s))], "cvar5": sum(s[:k]) / k, "skew": statistics.fmean(((v - m) / sd) ** 3 for v in x),
            "mean": m, "ratio_prime_tail": m / abs(sum(s[:k]) / k)}


STRESS = [("1987-10", 198709, 198712), ("1998", 199808, 199810), ("2002", 200206, 200210), ("2008", 200809, 200811), ("2018-02", 201802, 201802),
          ("2020", 202002, 202003), ("2022", 202201, 202210)]


def stress_rows(rows):
    ret = [r["ret"] for r in rows]
    mk = [r["mkt"] + r["rf"] for r in rows]
    yms = [r["ym"] for r in rows]
    out = []
    for name, a, b in STRESS:
        ix = [i for i, y in enumerate(yms) if a <= y <= b]
        if not ix:
            out.append({"episode": name, "covered": 0})
            continue
        i0, i1 = ix[0], ix[-1]
        w3 = [(math.prod(1 + v for v in ret[i:i + 3]) - 1, math.prod(1 + v for v in mk[i:i + 3]) - 1) for i in ix if i + 3 <= len(rows)]
        eq = equity_path(ret)
        peak = max(eq[:i0 + 1])
        rec = None
        for j in range(i0 + 1, len(eq)):
            if eq[j] >= peak:
                rec = j - i0
                break
        trough = min(eq[i0 + 1:i1 + 4])
        out.append({"episode": name, "covered": 1, "worst_month": min(ret[i] for i in ix), "worst_month_mkt": min(mk[i] for i in ix),
                    "loss_3m": min(w[0] for w in w3), "loss_3m_mkt": min(w[1] for w in w3), "drop_from_peak": 1 - trough / peak,
                    "months_to_recover": rec if rec is not None else -1 if min(eq[i0 + 1:]) < peak else 0})
    return out


# ---------- coeur de l'analyse ----------
def estimate_cell(rows, spec, y_key="y"):
    y = [r[y_key] for r in rows]
    return fit(y, cols_of(rows, spec))


def random_baseline(rows, beta, draws, rng):
    b = min(max(beta, 0.0), 1.0)
    x = [r["mkt"] for r in rows]
    al = []
    for _ in range(draws):
        y = [v if rng.random() < b else 0.0 for v in x]
        al.append(ols(y, [x])[0][0])
    al.sort()
    return al[int(0.95 * draws)]


def placebo_z(rows, alpha_full, rng, n_shuffle=200):
    """z placebos (centrés : excès moins l'alpha de S1) : (a) décalages de 13 à 60 mois, (b) mélange par blocs de 12 mois."""
    y0 = [r["y"] - alpha_full for r in rows]
    x = [r["mkt"] for r in rows]
    n = len(rows)
    zs = {"shift": [], "block": [], "shift_raw": [], "block_raw": []}
    for lab, yy in (("", y0), ("_raw", [r["y"] for r in rows])):
        for k in range(13, 61):
            ys = yy[k:] + yy[:k]
            f = fit(ys, [x])
            zs["shift" + lab].append(f["t"][0])
        for _ in range(n_shuffle):
            blocks = [yy[i:i + 12] for i in range(0, n, 12)]
            rng.shuffle(blocks)
            f = fit([v for b in blocks for v in b], [x])
            zs["block" + lab].append(f["t"][0])
    return zs


def robust_sd(z):
    return statistics.median(abs(v) for v in z) / 0.6745


def read_underlying(data, kind):
    if kind == "NDX":
        d = {}
        for r in csv.DictReader(open(os.path.join(data, "under", "FRED_NASDAQ100.csv"), encoding="utf-8")):
            try:
                d[dt.date.fromisoformat(r["date"])] = float(r["value"])
            except ValueError:
                continue
        return d
    d = {}
    for r in csv.DictReader(open(os.path.join(data, "tiingo", "TLT.csv"), encoding="utf-8")):
        d[dt.date.fromisoformat(r["date"])] = float(r["adjClose"])
    return d


def phase3_rows(name, data, ff, idx_ret):
    """Lignes alignées pour RUT (Mkt-RF, SMB), TLT (excès TLT), NDX (excès NDX prix) ; régresseurs placés dans 'mkt' (et 'smb' pour RUT)."""
    rows = []
    under = {} if name == "RUT" else monthly_returns(read_underlying(data, name))
    for ym in sorted(idx_ret):
        if ym in ff and ym <= 202608 and (name == "RUT" or ym in under):
            f = ff[ym]
            mk = f["mkt"] if name == "RUT" else under[ym] - f["rf"]
            rows.append({"ym": ym, "ret": idx_ret[ym], "y": idx_ret[ym] - f["rf"], "mkt": mk, "smb": f["smb"], "rf": f["rf"]})
    return rows


def write_csv(path, rows):
    keys = []
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow({k: (round(v, 6) if isinstance(v, float) else v) for k, v in r.items()})


def load_all(data):
    ff = load_ff(data)
    ret = {n: monthly_returns(load_cboe(os.path.join(data, "vrp", n + "_History.csv"))) for n in [c[0] for c in CELLS] + SECONDARY + ["PUTR", "PTLT", "BXN"]}
    return ff, ret


def power_mode(data, out):
    ff, ret = load_all(data)
    rows = []
    for name, _ in CELLS:
        for wn, w in windows(build_rows(ret[name], ff)).items():
            f = estimate_cell(w, "S1")
            mde = 2.80 * f["se"][0]
            rows.append({"index": name, "window": wn, "n": f["n"], "sd_resid": f["sd"], "se_iid": f["se_iid"], "se_nw": f["se"][0], "mde": mde,
                         "underpowered": int(mde > 2 * X_MONTH)})
    p3 = [("RUT", "PUTR"), ("TLT", "PTLT"), ("NDX", "BXN")]
    for under, name in p3:
        w = phase3_rows(under, data, ff, ret[name])
        f = fit([r["y"] for r in w], [[r["mkt"] for r in w]] + ([[r["smb"] for r in w]] if under == "RUT" else []))
        mde = 2.80 * f["se"][0]
        rows.append({"index": name, "window": "full", "n": f["n"], "sd_resid": f["sd"], "se_iid": f["se_iid"], "se_nw": f["se"][0], "mde": mde,
                     "underpowered": int(mde > 2 * X_MONTH)})
    write_csv(os.path.join(out, "vrp_real_power.csv"), rows)
    for r in rows:
        if r["window"] == "full":
            print("%s : n=%d, résidu %.2f %%, se_NW %.3f %%, MDE %.3f %% par mois -> %s" % (r["index"], r["n"], 100 * r["sd_resid"], 100 * r["se_nw"], 100 * r["mde"],
                                                                                         "SOUS-PUISSANT (inconclusif)" if r["underpowered"] else "puissant"))


def run_mode(data, out, draws=5000, seed=20261010):
    if not os.path.exists(os.path.join(out, "vrp_real_power.csv")):
        raise SystemExit("REFUSÉ : le fichier de puissance doit être écrit d'abord (--mode power)")
    if os.path.exists(LOCK):
        raise SystemExit("REFUSÉ : lecture unique déjà faite")
    rng = random.Random(seed)
    ff, ret = load_all(data)
    power = {(r["index"], r["window"]): r for r in csv.DictReader(open(os.path.join(out, "vrp_real_power.csv")))}
    L, stats_rows, est_rows, dec_rows, stress_out, sens_rows, cell_rows, tail_rows, p3_rows, win_rows = [], [], [], [], [], [], [], [], [], []
    cells = {}
    for name, sur in CELLS:
        rows = build_rows(ret[name], ff)
        wins = windows(rows)
        for wn, w in wins.items():
            st = perf([r["ret"] for r in w], [r["rf"] for r in w])
            mk = perf([r["mkt"] + r["rf"] for r in w], [r["rf"] for r in w])
            stats_rows.append({"index": name, "window": wn, "first": w[0]["ym"], "last": w[-1]["ym"], **st, "mkt_sharpe": mk["sharpe"], "mkt_worst": mk["worst"], "mkt_maxdd": mk["maxdd"]})
            for sp in SPECS:
                f = estimate_cell(w, sp)
                row = {"index": name, "spec": sp, "window": wn, "n": f["n"], "alpha": f["beta"][0], "t_nw": f["t"][0], "beta_mkt": f["beta"][1]}
                if sp == "S4":
                    row["beta_down"] = f["beta"][2]
                est_rows.append(row)
        for dec in range(1980, 2030, 10):
            w = [r for r in rows if dec <= r["ym"] // 100 < dec + 10]
            if len(w) >= 12:
                st = perf([r["ret"] for r in w], [r["rf"] for r in w])
                dec_rows.append({"index": name, "decade": dec, "n": st["n"], "ann_ret": st["ann_ret"], "ann_vol": st["ann_vol"], "sharpe": st["sharpe"], "worst": st["worst"], "maxdd": st["maxdd"]})
        full = estimate_cell(rows, "S1")
        a0 = full["beta"][0]
        lo, hi = boot_alpha_ci([r["y"] for r in rows], cols_of(rows, "S1"), draws, rng)
        bwin = {}
        for wn, w in wins.items():
            bw = estimate_cell(w, "S1")
            blo, bhi = boot_alpha_ci([r["y"] for r in w], cols_of(w, "S1"), draws, rng) if wn != "full" else (lo, hi)
            bwin[wn] = (bw["beta"][0], blo, bhi, random_baseline(w, bw["beta"][1], 1000, rng))
        zs = placebo_z(rows, a0, rng)
        cells[name] = {"rows": rows, "full": full, "ci": (lo, hi), "bwin": bwin, "zs": zs, "sur": sur}
    pool = [z for c in cells.values() for z in c["zs"]["shift"] + c["zs"]["block"]]
    pool_raw = [z for c in cells.values() for z in c["zs"]["shift_raw"] + c["zs"]["block_raw"]]
    lam, lam_raw = max(1.0, robust_sd(pool)), max(1.0, robust_sd(pool_raw))
    share = sum(1 for z in pool if abs(z) > 1.96) / len(pool)
    L.append("placebos centrés : lambda = %.3f (part de |z| > 1,96 : %.1f %%) ; lambda littéral non centré (non décisionnel) = %.3f" % (lam, 100 * share, lam_raw))
    pv = []
    for name, _ in CELLS:
        c = cells[name]
        c["z"] = c["full"]["t"][0]
        c["p"] = 1 - phi(c["z"] / lam)
        pv.append(c["p"])
    rej = bh(pv)
    p3_pos = 0
    p3_out = []
    for under, name in (("RUT", "PUTR"), ("TLT", "PTLT"), ("NDX", "BXN")):
        w = phase3_rows(under, data, ff, ret[name])
        cl = [[r["mkt"] for r in w]] + ([[r["smb"] for r in w]] if under == "RUT" else [])
        f = fit([r["y"] for r in w], cl)
        lo, hi = boot_alpha_ci([r["y"] for r in w], cl, draws, rng)
        p3_pos += f["beta"][0] > 0
        st = perf([r["ret"] for r in w], [r["rf"] for r in w])
        p3_out.append({"index": name, "underlying": under, "n": f["n"], "first": w[0]["ym"], "alpha": f["beta"][0], "ci_lo": lo, "ci_hi": hi, "t_nw": f["t"][0],
                       "beta": f["beta"][1], "p_bonf_M12": min(1.0, (1 - phi(f["t"][0])) * M_PHASE3), "sharpe": st["sharpe"], "worst": st["worst"], "maxdd": st["maxdd"],
                       "underpowered": int(power[(name, "full")]["underpowered"] == "1")})
    p3_rows = list(p3_out)
    crit7 = p3_pos >= 2
    for i, (name, sur) in enumerate(CELLS):
        c = cells[name]
        rows, full, (lo, hi) = c["rows"], c["full"], c["ci"]
        a0 = full["beta"][0]
        under_p = power[(name, "full")]["underpowered"] == "1"
        th = thresholds(rows)
        st = perf([r["ret"] for r in rows], [r["rf"] for r in rows])
        bw = c["bwin"]
        # sensibilités : demi-spread en points de volatilité
        sens = {}
        for hs in (0, 1, 2, 3):
            ys = [r["y"] - hs * sur for r in rows]
            f = fit(ys, cols_of(rows, "S1"))
            sens[hs] = (f["beta"][0], f["t"][0])
            sens_rows.append({"index": name, "variant": "demi-spread %d pt" % hs, "alpha": f["beta"][0], "t_nw": f["t"][0]})
        be = a0 / sur
        sens_rows.append({"index": name, "variant": "surcout d'equilibre (points de vol)", "alpha": be, "t_nw": NAN})
        worst3 = set(sorted(range(len(rows)), key=lambda j: rows[j]["y"])[:3])
        for lab, keep in (("sans les 3 pires mois", [r for j, r in enumerate(rows) if j not in worst3]),
                          ("sans 2008-2010", [r for r in rows if not 2008 <= r["ym"] // 100 <= 2010]),
                          ("sans 1987", [r for r in rows if r["ym"] // 100 != 1987]),
                          ("avec momentum (S3)", rows)):
            f = estimate_cell(keep, "S3" if "momentum" in lab else "S1")
            sens_rows.append({"index": name, "variant": lab, "alpha": f["beta"][0], "t_nw": f["t"][0]})
        if name == "PUTY":
            post = [r for r in rows if r["ym"] >= 201903]
            f = estimate_cell(post, "S1")
            sens_rows.append({"index": name, "variant": "apres lancement (2019-03 ->), n=%d" % len(post), "alpha": f["beta"][0], "t_nw": f["t"][0]})
            pre = [r for r in rows if r["ym"] < 201903]
            f = estimate_cell(pre, "S1")
            sens_rows.append({"index": name, "variant": "reconstruit (avant 2019-03), n=%d" % len(pre), "alpha": f["beta"][0], "t_nw": f["t"][0]})
        al = {sp: estimate_cell(rows, sp)["beta"][0] for sp in ("S2", "S3", "S4")}
        stress_out += [{"index": name, **s} for s in stress_rows(rows)]
        tail_rows.append({"index": name, **tail_stats([r["y"] for r in rows])})
        halves_pos = bw["half1"][0] > 0 and bw["half2"][0] > 0
        thirds_pos = sum(bw[k][0] > 0 for k in ("third1", "third2", "third3"))
        c1 = a0 > 0 and lo > 0 and rej[i] and c["p"] * M_CURRENT < 0.05
        crit = {"1 alpha>0, IC95 boot exclut 0, BH et Bonferroni(M=11)": c1,
                "2 alpha>0 dans chaque moitie et >=2 des 3 tiers": halves_pos and thirds_pos >= 2,
                "3 alpha>0 avec demi-spread 2 pt": sens[2][0] > 0,
                "4 alpha S2, S3, S4 > 0": all(v > 0 for v in al.values()),
                "5 pire mois et drawdown sous les seuils": st["worst"] >= th["worst_min"] and st["maxdd"] <= th["dd_max"],
                "6 alpha > p95 baseline aleatoire": a0 > bw["full"][3],
                "7 signe positif sur >=2 des 3 hors echantillon": crit7}
        negative = (not under_p) and hi < X_MONTH
        verdict = "NEGATIVE" if negative else ("ACCEPTEE" if all(crit.values()) and not under_p else "INCONCLUSIVE")
        L.append("%s : n=%d, alpha S1 %+.3f %%/mois (IC95 boot [%+.3f ; %+.3f]), t_NW %.2f, beta %.2f, p calibre %.4f, p x 11 = %.3f, BH %s, MDE %.3f %% -> %s" % (
            name, full["n"], 100 * a0, 100 * lo, 100 * hi, c["z"], full["beta"][1], c["p"], min(1, c["p"] * M_CURRENT), "rejet" if rej[i] else "non", 100 * float(power[(name, "full")]["mde"]),
            "SOUS-PUISSANT" if under_p else "puissant"))
        L.append("    pire mois %+.1f %% (seuil %+.1f %%, marche %+.1f %%), drawdown mensuel %.0f %% (seuil %.0f %%, marche %.0f %%, plus longue periode sous l'eau %d mois), alpha d'equilibre %.2f pt de vol" % (
            100 * st["worst"], 100 * th["worst_min"], 100 * th["worst_mkt"], 100 * st["maxdd"], 100 * th["dd_max"], 100 * th["dd_mkt"], st["dd_len"], be))
        for k, v in crit.items():
            L.append("    critere %s : %s" % (k, "OUI" if v else "NON"))
        L.append("    VERDICT cellule : %s" % verdict)
        cell_rows.append({"index": name, "n": full["n"], "alpha": a0, "ci_lo": lo, "ci_hi": hi, "t_nw": c["z"], "beta": full["beta"][1], "p_cal": c["p"], "bh": int(rej[i]),
                          "mde": float(power[(name, "full")]["mde"]), "underpowered": int(under_p), "verdict": verdict, **{"crit" + k[0]: int(v) for k, v in crit.items()}})
        for wn, (a, blo, bhi, p95) in bw.items():
            win_rows.append({"index": name, "window": wn, "n": len(windows(rows)[wn]), "alpha_S1": a, "ci_lo": blo, "ci_hi": bhi, "alpha_p95_random": p95})
    for under, name, desc in ((None, "BXM", "BXM"), (None, "BXMD", "BXMD"), (None, "BXY", "BXY")):
        rows = build_rows(ret[name], ff)
        f = estimate_cell(rows, "S1")
        L.append("descriptif %s (covered call) : n=%d, alpha %+.3f %%/mois (t_NW %.2f), beta %.2f" % (name, f["n"], 100 * f["beta"][0], f["t"][0], f["beta"][1]))
        p3_rows.append({"index": name, "underlying": "SPX (descriptif)", "n": f["n"], "alpha": f["beta"][0], "t_nw": f["t"][0], "beta": f["beta"][1]})
    for r in p3_out:
        L.append("hors echantillon %s : n=%d, alpha %+.3f %%/mois (IC95 [%+.3f ; %+.3f]), t_NW %.2f, beta %.2f%s" % (
            r["index"], r["n"], 100 * r["alpha"], 100 * r["ci_lo"], 100 * r["ci_hi"], r["t_nw"], r["beta"], " SOUS-PUISSANT" if r["underpowered"] else ""))
    L.append("hors echantillon : %d signes positifs sur 3 -> critere 7 %s" % (p3_pos, "tenu" if crit7 else "echoue"))
    write_csv(os.path.join(out, "vrp_real_stats.csv"), stats_rows)
    write_csv(os.path.join(out, "vrp_real_estimates.csv"), est_rows)
    write_csv(os.path.join(out, "vrp_real_decades.csv"), dec_rows)
    write_csv(os.path.join(out, "vrp_real_windows.csv"), win_rows)
    write_csv(os.path.join(out, "vrp_real_stress.csv"), stress_out)
    write_csv(os.path.join(out, "vrp_real_sens.csv"), sens_rows)
    write_csv(os.path.join(out, "vrp_real_cells.csv"), cell_rows)
    write_csv(os.path.join(out, "vrp_real_tails.csv"), tail_rows)
    write_csv(os.path.join(out, "vrp_real_phase3.csv"), p3_rows)
    bridge = bridge_e(data, ff, ret, cells)
    write_csv(os.path.join(out, "vrp_real_bridge.csv"), bridge)
    text = "\n".join(L)
    open(os.path.join(out, "vrp_real_summary.txt"), "w", encoding="utf-8").write(text + "\n")
    open(LOCK, "w").write("lu")
    print(text)


def bridge_e(data, ff, ret, cells):
    """Comparaison avec la piste E (Black-Scholes, E1 L=1) sur la même fenêtre : écart de rendement mensuel moyen et de bêta."""
    import vrp_study as vs
    vix, spy, rf = vs.load(data)
    out = []
    for hc, lab in ((0.015, "VIX-1,5"), (0.03, "VIX-3")):
        ms = vs.months(vix, spy, rf, hc, 0.005)
        for name, _ in CELLS:
            rows = [r for r in cells[name]["rows"] if r["ym"] >= 199303]
            e = [m for m in ms if 199303 <= m["d1"].year * 100 + m["d1"].month <= 202608]
            fi = fit([r["y"] for r in rows], [[r["mkt"] for r in rows]])
            b_e, a_e, _ = vs.alpha_beta(e, "e1", 1.0)
            out.append({"index": name, "piste_E": lab, "n_index": len(rows), "n_E": len(e), "mean_index": statistics.fmean(r["y"] for r in rows),
                        "mean_E1": statistics.fmean(m["e1"] for m in e), "beta_index": fi["beta"][1], "beta_E1": b_e, "alpha_index": fi["beta"][0], "alpha_E1": a_e})
    return out


def placebo2_mode(data, out, seed=20261011):
    """Correction déclarée (Écarts, 2026-10-10 après lecture) : placebos centrés sur la MOYENNE de l'excès (et non sur l'alpha de S1, qui laissait beta x moyenne du marché)."""
    ff, ret = load_all(data)
    rng = random.Random(seed)
    zs, cells = [], {}
    for name, _ in CELLS:
        rows = build_rows(ret[name], ff)
        z = placebo_z(rows, statistics.fmean(r["y"] for r in rows), rng)
        zs += z["shift"] + z["block"]
        cells[name] = estimate_cell(rows, "S1")
    lam = max(1.0, robust_sd(zs))
    share = sum(1 for z in zs if abs(z) > 1.96) / len(zs)
    pv = [1 - phi(cells[n]["t"][0] / lam) for n, _ in CELLS]
    rej = bh(pv)
    txt = ["placebos centres sur la moyenne : lambda = %.3f, part de |z| > 1,96 = %.1f %%" % (lam, 100 * share)]
    for (n, _), p, r in zip(CELLS, pv, rej):
        txt.append("%s : p calibre %.4f, p x 11 = %.3f, BH %s" % (n, p, min(1, p * M_CURRENT), "rejet" if r else "non"))
    out_txt = chr(10).join(txt)
    open(os.path.join(out, "vrp_real_placebo2.txt"), "w", encoding="utf-8").write(out_txt + chr(10))
    print(out_txt)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["power", "run", "placebo2"], required=True)
    ap.add_argument("--data", default="data")
    ap.add_argument("--out", default="results")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    {"power": power_mode, "run": run_mode, "placebo2": placebo2_mode}[a.mode](a.data, a.out)


if __name__ == "__main__":
    main()
