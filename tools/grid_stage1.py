"""Étage 1 : prédictibilité brute (sans stratégie, sans coûts) d'une grille large de variables, 3 groupes, 6 horizons.

Grille, règles et critères FIXÉS avant résultat dans CLAUDE.md (section « Pré-enregistrement : grille d'hypothèses »).
Modes : plan (énumère les cellules, aucune donnée), power (puissance, n'utilise QUE les rendements futurs, jamais une
variable), run (calcule tout, plus les placebos), test unitaires dans tests/test_grid_stage1.py.

Grille temporelle : minutes UTC depuis T0, fenêtre de découverte = avant FREEZE (holdout après, jamais lu ici).
Observation : fin de la minute i, seulement si la minute i a au moins un trade et (hors crypto) si la session est ouverte
en i et en i+h. Rendement futur = ln(C[i+h]/C[i]) en bps (C = dernier prix imprimé, reporté). Instants de décision
espacés de STRIDE[h] minutes (observations quasi non chevauchantes).
Statistique : corrélation de Pearson entre le rang de x et le rang de y dans l'échantillon d'une cellule (= Spearman,
rangs moyens pour les ex aequo), calculée par instrument puis moyennée (instruments à poids égaux) dans le groupe.
Erreur-type : jackknife par blocs de jours (suppression d'un bloc, même bloc pour tous les instruments du groupe), et
dispersion entre instruments si >= 4 instruments ; on retient la plus grande.

stdlib uniquement.
"""
import argparse
import array
import bisect
import calendar
import csv
import glob
import json
import math
import operator
import os
import random
import statistics
import sys
import time
from collections import deque
from itertools import accumulate, groupby

NAN = float("nan")
T0_MS = calendar.timegm((2026, 5, 1, 0, 0, 0)) * 1000
FREEZE_MS = calendar.timegm((2026, 9, 28, 0, 0, 0)) * 1000
G = (FREEZE_MS - T0_MS) // 60000
HORIZONS = (1, 5, 15, 60, 240, 1440)
STRIDE = {1: 1, 5: 5, 15: 15, 60: 15, 240: 30, 1440: 60}
KAPPA = 3.0            # exclusion de puissance : MDE > KAPPA x coût aller-retour
Z_MDE = 3.29 + 0.84    # p = 0.001 bilatéral, puissance 80 %
FEE, SLIP, FALLBACK_SPREAD = 4.0, 2.0, 2.5
MIN_OBS = 300          # observations minimales (échantillon espacé) par instrument et horizon
RHO_FALLBACK = 0.3
BN_START_MS = calendar.timegm((2026, 9, 14, 0, 0, 0)) * 1000
WIN_LO = {("F1", "crypto"): 136 * 1440, ("F1", "equity"): 117 * 1440, ("F7", "crypto"): 136 * 1440}   # jours depuis T0
SHUFFLE_BLOCK = 120    # minutes, placebo « mélange par blocs »
GROUPS = {
    "crypto": ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "HYPE-USD"],
    "idx_cmd": ["SP500-USD", "NAS100-USD", "GOLD-USD", "SILVER-USD", "WTIOIL-USD"],
    "equity": ["AAPL-USD", "MSFT-USD", "GOOG-USD", "AMZN-USD", "NVDA-USD", "META-USD", "TSLA-USD"],
}
BN = {"BTC-USD": "BTCUSDT", "ETH-USD": "ETHUSDT", "SOL-USD": "SOLUSDT", "XRP-USD": "XRPUSDT", "HYPE-USD": "HYPEUSDT"}

# (famille, variable, groupes, source requise, binaire)
SPEC = []


def _add(fam, names, groups, need="klines", binary=False):
    for n in names:
        SPEC.append((fam, n, tuple(groups), need, binary))


ALL3 = ("crypto", "idx_cmd", "equity")
_add("F1", ["imb_10s", "imb_1m", "imb_5m", "imb_15m", "ntr_1m", "ntr_15m", "vs_1m", "vs_5m", "big_15m", "big_60m",
            "run_len"], ("crypto", "equity"), "trades")
_add("F2", ["rn_5", "rn_15", "rn_60", "rn_240", "rn_1440", "range_15", "range_60", "range_240", "rpos_60",
            "rpos_240"], ALL3)
_add("F2", ["gap_open"], ("idx_cmd", "equity"))
_add("F3", ["vr_60_1440", "vr_15_240", "vov_24h", "idle_before", "zf_60", "zf_1440"], ALL3)
_add("F4", ["fund_lvl", "fund_d1h", "fund_d8h", "xs_fund"], ALL3, "funding")
_add("F4", ["ph_pre", "ph_post"], ALL3, "funding", True)
_add("F4", ["basis_ml"], ("equity",), "mark")
_add("F5", ["tod_sin", "tod_cos", "dow_sin", "dow_cos", "prox_open", "prox_close"], ALL3)
_add("F5", ["weekend"], ALL3, "klines", True)
_add("F6", ["lead_btc_1", "lead_btc_5", "lead_btc_15", "lead_btc_60", "lead_eth_1", "lead_eth_5", "lead_eth_15",
            "lead_eth_60"], ("crypto",))
_add("F6", ["lead_nas_5", "lead_nas_15", "lead_nas_60"], ("equity",))
_add("F6", ["xs_ret_5", "xs_ret_60", "xs_ret_1440", "resid_15", "resid_60", "resid_240"], ALL3)
_add("F7", ["bn_ret_1", "bn_ret_5", "bn_ret_15", "bn_gap_1", "bn_gap_5", "bn_sv_1", "bn_sv_5", "bn_vsurp_1"],
     ("crypto",), "bn")
FAMILIES = ["F1", "F2", "F3", "F4", "F5", "F6", "F7"]


# ---------------------------------------------------------------- utilitaires séries
def narr(v=NAN):
    return array.array("d", [v]) * G


def logret(a, k):
    out = narr()
    for i in range(k, G):
        x, y = a[i], a[i - k]
        if x > 0 and y > 0:
            out[i] = 1e4 * math.log(x / y)
    return out


def roll_sum(a, w):
    """Somme glissante sur les w dernières valeurs (i inclus) ; NaN si une valeur de la fenêtre est NaN."""
    z = [0.0 if x != x else x for x in a]
    ps = list(accumulate(z, initial=0.0))
    pc = list(accumulate([1 if x != x else 0 for x in a], initial=0))
    return array.array("d", [NAN] * (w - 1) + [(ps[j] - ps[j - w]) if pc[j] == pc[j - w] else NAN
                                                for j in range(w, len(a) + 1)])


def roll_ext(a, w, ismax):
    out = narr()
    dq = deque()
    first = None
    for i in range(len(a)):
        x = a[i]
        if x != x:
            continue
        if first is None:
            first = i
        while dq and (a[dq[-1]] <= x if ismax else a[dq[-1]] >= x):
            dq.pop()
        dq.append(i)
        if dq[0] <= i - w:
            dq.popleft()
        if i >= first + w - 1:
            out[i] = a[dq[0]]
    return out


def rank_avg(v):
    n = len(v)
    order = sorted(range(n), key=v.__getitem__)
    r = [0.0] * n
    i = 0
    while i < n:
        j = i
        vi = v[order[i]]
        while j + 1 < n and v[order[j + 1]] == vi:
            j += 1
        if j == i:
            r[order[i]] = i + 1.0
        else:
            a = (i + j) / 2 + 1.0
            for k in range(i, j + 1):
                r[order[k]] = a
        i = j + 1
    return r


def phi_p(z):
    return math.erfc(abs(z) / math.sqrt(2.0))


def rho_f(n, sx, sy, sxx, syy, sxy):
    if n < 30:
        return NAN
    vx, vy = n * sxx - sx * sx, n * syy - sy * sy
    if vx <= 0 or vy <= 0:
        return NAN
    return (n * sxy - sx * sy) / math.sqrt(vx * vy)


# ---------------------------------------------------------------- données
class Inst:
    def __init__(self, name):
        self.name = name
        self.C = self.H = self.L = self.V = self.NT = self.S = None
        self.start = G
        self.tr = None       # agrégats de trades par minute
        self.FR = None       # funding (bps/h) en escalier
        self.MK = None       # mark du bucket
        self.bn = None       # (close, signed volume, volume) par minute
        self.c = {}          # cache
        self.cost = 2 * FEE + 2 * SLIP + FALLBACK_SPREAD
        self.pops = {}


def ffill_inst(inst):
    for a in (inst.C, inst.H, inst.L, inst.S):
        last = NAN
        for i in range(inst.start, G):
            if a[i] != a[i]:
                a[i] = last
            else:
                last = a[i]


def load_klines(name, data="data"):
    inst = Inst(name)
    inst.C, inst.H, inst.L, inst.S = narr(), narr(), narr(), narr()
    inst.V, inst.NT = narr(0.0), narr(0.0)
    with open(os.path.join(data, name + "_1m.csv")) as f:
        r = csv.reader(f)
        next(r)
        for row in r:
            ts = int(row[0])
            i = (ts - T0_MS) // 60000
            if i < 0 or i >= G:
                continue
            inst.C[i], inst.H[i], inst.L[i] = float(row[4]), float(row[2]), float(row[3])
            inst.V[i], inst.NT[i] = float(row[5]), float(row[6])
            inst.S[i] = float(row[7]) if len(row) > 7 else 1.0   # HYPE (crypto) n'a pas de colonne session
            if i < inst.start:
                inst.start = i
    ffill_inst(inst)
    return inst


def read_trades(name, data="data"):
    rows = []
    with open(os.path.join(data, "hist", name + "_trades.csv")) as f:
        r = csv.reader(f)
        next(r)
        for row in r:
            ts = int(row[0])
            if ts >= FREEZE_MS or row[5] == "1" or ts < T0_MS:
                continue
            rows.append((ts, 1 if row[2] == "long" else -1, float(row[3]) * float(row[4]), float(row[3]),
                         float(row[4])))
    rows.sort(key=operator.itemgetter(0))
    return rows


def bars_from_trades(name, rows):
    inst = Inst(name)
    inst.C, inst.H, inst.L, inst.S = narr(), narr(), narr(), narr()
    inst.V, inst.NT = narr(0.0), narr(0.0)
    for ts, _s, _n, p, q in rows:
        i = (ts - T0_MS) // 60000
        inst.C[i] = p
        inst.H[i] = p if inst.H[i] != inst.H[i] else max(inst.H[i], p)
        inst.L[i] = p if inst.L[i] != inst.L[i] else min(inst.L[i], p)
        inst.V[i] += q
        inst.NT[i] += 1
        inst.S[i] = 1.0
        inst.start = min(inst.start, i)
    ffill_inst(inst)
    return inst


def attach_trades(inst, rows):
    """Agrégats par minute : notionnel acheteur/vendeur, 10 dernières secondes, gros trades, séquences."""
    n0 = (rows[0][0] - T0_MS) // 60000 if rows else G
    day_n = {}
    for ts, _s, nt, _p, _q in rows:
        day_n.setdefault((ts - T0_MS) // 86400000, []).append(nt)
    thr = {d + 1: sorted(v)[int(0.9 * (len(v) - 1))] for d, v in day_n.items()}
    keys = ("BUY", "SELL", "B10", "S10", "NTR", "BIGB", "BIGS")
    tr = {k: narr(0.0) for k in keys}
    tr["RUN"] = narr()
    prev, run = 0, 0
    for ts, s, nt, _p, _q in rows:
        i = (ts - T0_MS) // 60000
        d = (ts - T0_MS) // 86400000
        tr["BUY" if s > 0 else "SELL"][i] += nt
        if (ts - T0_MS) % 60000 >= 50000:
            tr["B10" if s > 0 else "S10"][i] += nt
        tr["NTR"][i] += 1
        if d in thr and nt >= thr[d]:
            tr["BIGB" if s > 0 else "BIGS"][i] += nt
        run = run + 1 if s == prev else 1
        prev = s
        tr["RUN"][i] = s * min(run, 50)
    for k in keys:   # NaN avant le premier trade (les fenêtres qui le contiennent sont invalides)
        a = tr[k]
        for i in range(min(n0, G)):
            a[i] = NAN
    for i in range(min(n0 + 1440, G)):   # seuil des gros trades : jour précédent
        tr["BIGB"][i] = tr["BIGS"][i] = NAN
    inst.tr = tr
    return inst


def attach_funding(inst, data="data"):
    p = os.path.join(data, inst.name + "_funding.csv")
    if not os.path.exists(p):
        return
    pts = []
    with open(p) as f:
        r = csv.reader(f)
        next(r)
        for row in r:
            pts.append((int(row[0]), float(row[1]) * 1e4))
    pts.sort()
    fr = narr()
    j = -1
    for i in range(G):
        end = T0_MS + (i + 1) * 60000
        while j + 1 < len(pts) and pts[j + 1][0] <= end:
            j += 1
        if j >= 0:
            fr[i] = pts[j][1]
    inst.FR = fr


def attach_mark(inst, data="data"):
    p = os.path.join(data, "hist", inst.name + "_mark_1m.csv")
    if not os.path.exists(p):
        return
    mk = narr()
    with open(p) as f:
        r = csv.reader(f)
        next(r)
        for row in r:
            ts, v = int(row[0]), float(row[1])
            i = (ts - T0_MS) // 60000
            if 0 <= i < G and v > 0:
                mk[i] = v
    inst.MK = mk


def attach_binance(inst, data="data"):
    p = os.path.join(data, "ext", BN[inst.name] + "_1s.csv")
    if not os.path.exists(p):
        return
    bc, sv, vv = narr(), narr(0.0), narr(0.0)
    with open(p) as f:
        r = csv.reader(f)
        next(r)
        for row in r:
            ts = int(row[0])
            if ts >= FREEZE_MS or ts < BN_START_MS:
                continue
            i = (ts - T0_MS) // 60000
            o, c, v = float(row[1]), float(row[2]), float(row[3])
            bc[i] = c
            vv[i] += v
            sv[i] += v if c > o else (-v if c < o else 0.0)
    last = NAN
    first = next((i for i in range(G) if bc[i] == bc[i]), G)
    for i in range(first, G):
        if bc[i] != bc[i]:
            bc[i] = last
        else:
            last = bc[i]
    inst.bn = (bc, sv, vv, first)


def load_costs(data="data"):
    vals = {}
    for p in glob.glob(os.path.join(data, "live_probe", "*", "books.jsonl")):
        with open(p, encoding="utf-8") as f:
            for line in f:
                try:
                    b = json.loads(line)
                    vals.setdefault(b["sym"], []).append(b["spread_bps"])
                except (ValueError, KeyError):
                    continue
    return {s: 2 * FEE + 2 * SLIP + statistics.median(v) for s, v in vals.items()}


def has_source(name, need, data="data"):
    if need == "klines":
        return os.path.exists(os.path.join(data, name + "_1m.csv")) or os.path.exists(
            os.path.join(data, "hist", name + "_trades.csv"))
    if need == "trades":
        return os.path.exists(os.path.join(data, "hist", name + "_trades.csv"))
    if need == "funding":
        return os.path.exists(os.path.join(data, name + "_funding.csv"))
    if need == "mark":
        return os.path.exists(os.path.join(data, "hist", name + "_mark_1m.csv")) and os.path.exists(
            os.path.join(data, name + "_1m.csv"))
    if need == "bn":
        return name in BN and os.path.exists(os.path.join(data, "ext", BN[name] + "_1s.csv"))
    return False


def available(group, need, data="data"):
    return [n for n in GROUPS[group] if has_source(n, need, data)]


def planned_cells(data="data"):
    out = []
    for fam, var, groups, need, _b in SPEC:
        for g in groups:
            if len(available(g, need, data)) < 3:
                continue
            for h in HORIZONS:
                out.append((fam, var, g, h))
    return out


def load_group(group, data="data", light=False):
    insts = {}
    for n in GROUPS[group]:
        if os.path.exists(os.path.join(data, n + "_1m.csv")):
            inst = load_klines(n, data)
            if not light and has_source(n, "trades", data):
                inst.rows = read_trades(n, data)
        elif has_source(n, "trades", data):
            rows = read_trades(n, data)
            inst = bars_from_trades(n, rows)
            inst.rows = rows
        else:
            continue
        if light:
            insts[n] = inst
            continue
        if getattr(inst, "rows", None):
            attach_trades(inst, inst.rows)
        attach_funding(inst, data)
        attach_mark(inst, data)
        if group == "crypto":
            attach_binance(inst, data)
        insts[n] = inst
    cost = load_costs(data)
    for n, inst in insts.items():
        if n in cost:
            inst.cost = cost[n]
    return insts


# ---------------------------------------------------------------- populations de rendements futurs
def cget(inst, key, fn):
    if key not in inst.c:
        inst.c[key] = fn()
    return inst.c[key]


def win_of(fam):
    return fam if fam in ("F1", "F7") else "long"


def win_lo(fam, group):
    return WIN_LO.get((fam, group), 0) if fam in ("F1", "F7") else 0


def bsize(h):
    return 1 if h <= 240 else 3


def build_pop(inst, h, lo=0):
    if (h, lo) in inst.pops:
        return inst.pops[(h, lo)]
    st = STRIDE[h]
    C, S, NT = inst.C, inst.S, inst.NT
    bs = bsize(h)
    idx, y, blk = [], [], []
    for i in range((max(inst.start, lo) + st - 1) // st * st, G - h, st):
        if NT[i] > 0 and S[i] == 1.0 and S[i + h] == 1.0 and C[i] > 0 and C[i + h] > 0:
            idx.append(i)
            y.append(1e4 * math.log(C[i + h] / C[i]))
            blk.append((i // 1440) // bs)
    inst.pops[(h, lo)] = (idx, y, blk, rank_avg(y) if y else [])
    return inst.pops[(h, lo)]


# ---------------------------------------------------------------- variables
def _rv(inst, w):
    def f():
        R = cget(inst, "R1", lambda: logret(inst.C, 1))
        sq = array.array("d", [x * x if x == x else NAN for x in R])
        nz = array.array("d", [1.0 if (x == x and x != 0.0) else (0.0 if x == x else NAN) for x in R])
        s, n = roll_sum(sq, w), roll_sum(nz, w)
        return array.array("d", [(math.sqrt(max(a, 0.0) / w) if b > 0 else 0.0) if a == a else NAN
                                 for a, b in zip(s, n)])
    return cget(inst, "rv%d" % w, f)


def _tr(inst, k):
    return cget(inst, "TR%d" % k, lambda: logret(inst.C, k))


def _ratio(a, b, fn=lambda x: x):
    return array.array("d", [fn(x / y) if (x == x and y == y and y > 0) else NAN for x, y in zip(a, b)])


def _imb(buy, sell):
    return array.array("d", [(b - s) / (b + s) if (b == b and s == s and b + s > 0) else NAN
                             for b, s in zip(buy, sell)])


def _shift(a, k):
    return array.array("d", [NAN] * k) + a[:len(a) - k]


def _cal(fn):
    out = narr()
    for i in range(G):
        out[i] = fn(i)
    return out


def _cal_cached(key, fn):
    return fn


def _clip(x, a, b):
    return max(a, min(b, x))


def _wd(i):
    return ((i // 1440) + 4) % 7   # 2026-05-01 est un vendredi (lundi = 0)


CAL = {}


def calendar_var(name):
    if name in CAL and len(CAL[name]) == G:
        return CAL[name]
    if name == "tod_sin":
        a = _cal(lambda i: math.sin(2 * math.pi * ((i % 1440) + 1) / 1440))
    elif name == "tod_cos":
        a = _cal(lambda i: math.cos(2 * math.pi * ((i % 1440) + 1) / 1440))
    elif name == "dow_sin":
        a = _cal(lambda i: math.sin(2 * math.pi * ((_wd(i) * 1440 + (i % 1440) + 1) / 10080)))
    elif name == "dow_cos":
        a = _cal(lambda i: math.cos(2 * math.pi * ((_wd(i) * 1440 + (i % 1440) + 1) / 10080)))
    elif name == "weekend":
        a = _cal(lambda i: 1.0 if _wd(i) >= 5 else 0.0)
    elif name == "prox_open":
        a = _cal(lambda i: _clip((i % 1440) + 1 - 810, -240, 240) if _wd(i) < 5 else NAN)
    elif name == "prox_close":
        a = _cal(lambda i: _clip((i % 1440) + 1 - 1200, -240, 240) if _wd(i) < 5 else NAN)
    CAL[name] = a
    return a


def group_xs(insts, k, mode):
    """Rang en coupe transversale (mode 'rank') ou résiduel (mode 'resid') du rendement k minutes, pour tous."""
    key = "xs_%s_%d" % (mode, k)
    first = next(iter(insts.values()))
    if key in first.c:
        return
    names = list(insts)
    trs = [_tr(insts[n], k) for n in names]
    outs = [narr() for _ in names]
    for i in range(G):
        vals = [(t[i], j) for j, t in enumerate(trs) if t[i] == t[i]]
        m = len(vals)
        if m < 3:
            continue
        if mode == "rank":
            vals.sort()
            for rk, (_v, j) in enumerate(vals):
                outs[j][i] = (rk + 1 - (m + 1) / 2) / m
        else:
            tot = sum(v for v, _ in vals)
            for v, j in vals:
                outs[j][i] = v - (tot - v) / (m - 1)
    for n, o in zip(names, outs):
        insts[n].c[key] = o


def group_xs_fund(insts):
    first = next(iter(insts.values()))
    if "xs_fund" in first.c:
        return
    names = [n for n in insts if insts[n].FR is not None]
    outs = {n: narr() for n in names}
    for i in range(G):
        vals = sorted((insts[n].FR[i], n) for n in names if insts[n].FR[i] == insts[n].FR[i])
        m = len(vals)
        if m < 3:
            continue
        for rk, (_v, n) in enumerate(vals):
            outs[n][i] = (rk + 1 - (m + 1) / 2) / m
    for n in names:
        insts[n].c["xs_fund"] = outs[n]


def make_var(var, inst, insts, aux=None):
    aux = aux or {}
    """Retourne le tableau (longueur G) de la variable pour un instrument, ou None si non définissable."""
    C, S = inst.C, inst.S
    tr = inst.tr
    if var in ("imb_10s", "imb_1m", "imb_5m", "imb_15m"):
        if var == "imb_10s":
            return _imb(tr["B10"], tr["S10"])
        w = int(var[4:-1])
        return _imb(roll_sum(tr["BUY"], w), roll_sum(tr["SELL"], w)) if w > 1 else _imb(tr["BUY"], tr["SELL"])
    if var == "ntr_1m":
        return array.array("d", [math.log1p(x) if x == x else NAN for x in tr["NTR"]])
    if var == "ntr_15m":
        return array.array("d", [math.log1p(x) if x == x else NAN for x in roll_sum(tr["NTR"], 15)])
    if var in ("vs_1m", "vs_5m"):
        notional = array.array("d", [b + s for b, s in zip(tr["BUY"], tr["SELL"])])
        if var == "vs_1m":
            num, base, lag, scale = notional, roll_sum(notional, 60), 1, 60.0
        else:
            num, base, lag, scale = roll_sum(notional, 5), roll_sum(notional, 1440), 5, 1440.0 / 5
        bs = _shift(base, lag)
        return array.array("d", [math.log(a / (b / scale)) if (a == a and b == b and a > 0 and b > 0) else NAN
                                 for a, b in zip(num, bs)])
    if var in ("big_15m", "big_60m"):
        w = int(var[4:-1])
        return _imb(roll_sum(tr["BIGB"], w), roll_sum(tr["BIGS"], w))
    if var == "run_len":
        return tr["RUN"]
    if var.startswith("rn_"):
        k = int(var[3:])
        return _ratio(_tr(inst, k), array.array("d", [x * math.sqrt(k) for x in _rv(inst, 240)]))
    if var.startswith("range_"):
        w = int(var[6:])
        hi, lo = roll_ext(inst.H, w, True), roll_ext(inst.L, w, False)
        return array.array("d", [1e4 * math.log(a / b) if (a == a and b == b and b > 0) else NAN
                                 for a, b in zip(hi, lo)])
    if var.startswith("rpos_"):
        w = int(var[5:])
        hi, lo = roll_ext(inst.H, w, True), roll_ext(inst.L, w, False)
        return array.array("d", [(c - b) / (a - b) if (a == a and b == b and a > b) else NAN
                                 for a, b, c in zip(hi, lo, C)])
    if var == "gap_open":
        out = narr()
        for o in range(inst.start + 1, G):
            if S[o] == 1.0 and S[o - 1] == 0.0 and C[o - 1] > 0 and o + 5 < G and C[o + 5] > 0:
                g = 1e4 * math.log(C[o + 5] / C[o - 1])
                for j in range(o + 5, min(o + 61, G)):
                    if S[j] != 1.0:
                        break
                    out[j] = g
        return out
    if var == "vr_60_1440":
        return _ratio(_rv(inst, 60), _rv(inst, 1440), lambda x: math.log(x) if x > 0 else NAN)
    if var == "vr_15_240":
        return _ratio(_rv(inst, 15), _rv(inst, 240), lambda x: math.log(x) if x > 0 else NAN)
    if var == "vov_24h":
        R = cget(inst, "R1", lambda: logret(C, 1))
        sq = array.array("d", [x * x if x == x else NAN for x in R])
        rs = roll_sum(sq, 60)
        nh = G // 60
        rvh = [math.sqrt(max(rs[60 * j + 59], 0.0) / 60) if rs[60 * j + 59] == rs[60 * j + 59] else NAN
               for j in range(nh)]
        cv = [NAN] * (nh + 1)
        for j in range(24, nh + 1):
            w = rvh[j - 24:j]
            if all(x == x for x in w):
                m = sum(w) / 24
                if m > 0:
                    cv[j] = statistics.pstdev(w) / m
        out = narr()
        for i in range(G):
            out[i] = cv[i // 60]
        return out
    if var == "idle_before":
        out = narr()
        last = None
        for i in range(inst.start, G):
            if inst.NT[i] > 0:
                if last is not None:
                    out[i] = math.log1p(i - last - 1)
                last = i
        return out
    if var in ("zf_60", "zf_1440"):
        w = int(var[3:])
        z = array.array("d", [(1.0 if inst.NT[i] == 0 else 0.0) if i >= inst.start else NAN for i in range(G)])
        return array.array("d", [x / w if x == x else NAN for x in roll_sum(z, w)])
    if var == "fund_lvl":
        return inst.FR
    if var == "fund_d1h":
        return array.array("d", [a - b for a, b in zip(inst.FR, _shift(inst.FR, 60))])
    if var == "fund_d8h":
        return array.array("d", [a - b for a, b in zip(inst.FR, _shift(inst.FR, 480))])
    if var == "xs_fund":
        group_xs_fund(insts)
        return inst.c.get("xs_fund")
    if var == "ph_pre":
        return array.array("d", [(1.0 if (i % 60) >= 55 else 0.0) if x == x else NAN for i, x in enumerate(inst.FR)])
    if var == "ph_post":
        return array.array("d", [(1.0 if (i % 60) < 5 else 0.0) if x == x else NAN for i, x in enumerate(inst.FR)])
    if var == "basis_ml":
        return array.array("d", [1e4 * math.log(m / c) if (m == m and c > 0) else NAN for m, c in zip(inst.MK, C)])
    if var in ("tod_sin", "tod_cos", "dow_sin", "dow_cos", "weekend", "prox_open", "prox_close"):
        return calendar_var(var)
    if var.startswith("lead_"):
        _, lead, k = var.split("_")
        name = {"btc": "BTC-USD", "eth": "ETH-USD", "nas": "NAS100-USD"}[lead]
        pool = dict(insts, **aux)
        if name == inst.name or name not in pool:
            return None
        return _tr(pool[name], int(k))
    if var.startswith("xs_ret_"):
        k = int(var[7:])
        group_xs(insts, k, "rank")
        return inst.c.get("xs_rank_%d" % k)
    if var.startswith("resid_"):
        k = int(var[6:])
        group_xs(insts, k, "resid")
        return inst.c.get("xs_resid_%d" % k)
    if var.startswith("bn_"):
        if inst.bn is None:
            return None
        bc, sv, vv, first = inst.bn
        if var.startswith("bn_ret_"):
            return logret(bc, int(var[7:]))
        if var.startswith("bn_gap_"):
            k = int(var[7:])
            return array.array("d", [a - b for a, b in zip(logret(bc, k), _tr(inst, k))])
        if var.startswith("bn_sv_"):
            k = int(var[6:])
            return _ratio(roll_sum(sv, k), roll_sum(vv, k))
        if var == "bn_vsurp_1":
            base = _shift(roll_sum(vv, 60), 1)
            return array.array("d", [math.log(a / (b / 60)) if (a > 0 and b == b and b > 0) else NAN
                                     for a, b in zip(vv, base)])
    return None


def start_day_for(inst, fam, var):
    """Premier jour où la variable peut exister, pour ancrer les plis."""
    d = inst.start // 1440
    if fam == "F1" and inst.tr is not None:
        d = max(d, next((i for i, x in enumerate(inst.tr["NTR"]) if x == x), G) // 1440)
    if fam == "F7" and inst.bn is not None:
        d = max(d, inst.bn[3] // 1440)
    return d


# ---------------------------------------------------------------- statistiques par cellule
def placebo_lag(x, rng):
    L = 1440 * rng.randint(2, 9) + rng.randint(120, 1320)
    return array.array("d", [NAN] * L) + x[:len(x) - L]


def placebo_shuffle(x, rng):
    blocks = [x[j:j + SHUFFLE_BLOCK] for j in range(0, len(x), SHUFFLE_BLOCK)]
    last = blocks.pop() if len(blocks[-1]) < SHUFFLE_BLOCK else None
    rng.shuffle(blocks)
    if last is not None:
        blocks.append(last)
    out = array.array("d")
    for b in blocks:
        out.extend(b)
    return out


def inst_cell(x, inst, h, binary, fold_of_blk, lo=0):
    """Statistiques d'un instrument pour une variable et un horizon. None si l'échantillon est trop petit."""
    idx, y, blk, yrank_full = build_pop(inst, h, lo)
    sel = [j for j in range(len(idx)) if x[idx[j]] == x[idx[j]]]
    if len(sel) < MIN_OBS:
        return None
    xv = [x[idx[j]] for j in sel]
    if len(sel) == len(idx):
        yv, yr, bl = y, yrank_full, blk
    else:
        yv = [y[j] for j in sel]
        yr = rank_avg(yv)
        bl = [blk[j] for j in sel]
    xr = rank_avg(xv)
    n = len(xr)
    if binary:
        f1 = [1.0 if v == 0.0 else 0.0 for v in xv]
        f10 = [1.0 if v == 1.0 else 0.0 for v in xv]
    else:
        sx_ = sorted(xv)   # groupes extrêmes par valeur seuil (ex aequo inclus) : v <= 10e centile, v >= 90e centile
        lo, hi = sx_[max(int(0.1 * n) - 1, 0)], sx_[min(int(0.9 * n), n - 1)]
        if lo >= hi:
            return None
        f1 = [1.0 if v <= lo else 0.0 for v in xv]
        f10 = [1.0 if v >= hi else 0.0 for v in xv]
    sums = []
    pos = 0
    mul = operator.mul
    for b, grp in groupby(bl):
        e = pos + sum(1 for _ in grp)
        x_, y_, r_ = xr[pos:pos + (e - pos)], yr[pos:e], yv[pos:e]
        a1, a10 = f1[pos:e], f10[pos:e]
        sums.append((b, e - pos, sum(x_), sum(y_), sum(map(mul, x_, x_)), sum(map(mul, y_, y_)),
                     sum(map(mul, x_, y_)), sum(a1), sum(map(mul, a1, r_)), sum(a10), sum(map(mul, a10, r_))))
        pos = e
    tot = [sum(c) for c in zip(*[s[1:] for s in sums])]
    rho = rho_f(*tot[:6])
    if rho != rho or tot[6] < 20 or tot[8] < 20:
        return None
    m1, m10 = tot[7] / tot[6], tot[9] / tot[8]

    def sp(t):
        return (t[9] / t[8] - t[7] / t[6]) if (t[6] >= 5 and t[8] >= 5) else NAN

    jr, jsp = {}, {}
    for s in sums:
        t = [a - b for a, b in zip(tot, s[1:])]
        r2 = rho_f(*t[:6])
        jr[s[0]] = (r2 - rho) if r2 == r2 else 0.0
        v = sp(t)
        jsp[s[0]] = (v - (m10 - m1)) if v == v else 0.0
    folds_r, folds_s = [NAN] * 3, [NAN] * 3
    for f in range(3):
        t = [sum(c) for c in zip(*[s[1:] for s in sums if fold_of_blk(s[0]) == f])] or None
        if t:
            folds_r[f], folds_s[f] = rho_f(*t[:6]), sp(t)
    return {"rho": rho, "n": tot[0], "m1": m1, "m10": m10, "spread": m10 - m1, "jr": jr, "jsp": jsp,
            "fr": folds_r, "fs": folds_s, "cost": inst.cost, "sig": statistics.pstdev(yv)}


class Acc:
    def __init__(self):
        self.k = 0
        self.rho = []
        self.sp = []
        self.m1 = []
        self.m10 = []
        self.n = 0
        self.cost = []
        self.jr = {}
        self.jsp = {}
        self.fr = [[], [], []]
        self.fs = [[], [], []]
        self.per = {}

    def add(self, name, c):
        self.k += 1
        self.per[name] = c["rho"]
        self.rho.append(c["rho"])
        self.sp.append(c["spread"])
        self.m1.append(c["m1"])
        self.m10.append(c["m10"])
        self.n += c["n"]
        self.cost.append(c["cost"])
        for b, v in c["jr"].items():
            self.jr[b] = self.jr.get(b, 0.0) + v
        for b, v in c["jsp"].items():
            self.jsp[b] = self.jsp.get(b, 0.0) + v
        for f in range(3):
            if c["fr"][f] == c["fr"][f]:
                self.fr[f].append(c["fr"][f])
            if c["fs"][f] == c["fs"][f]:
                self.fs[f].append(c["fs"][f])

    def result(self):
        k = self.k
        ic = sum(self.rho) / k
        spread = sum(self.sp) / k
        blocks = sorted(self.jr)
        B = len(blocks)
        se_j = se_js = NAN
        if B >= 5:
            th = [ic + self.jr[b] / k for b in blocks]
            mth = sum(th) / B
            se_j = math.sqrt((B - 1) / B * sum((t - mth) ** 2 for t in th))
            ts = [spread + self.jsp[b] / k for b in blocks]
            mts = sum(ts) / B
            se_js = math.sqrt((B - 1) / B * sum((t - mts) ** 2 for t in ts))
        se_c = statistics.stdev(self.rho) / math.sqrt(k) if k >= 4 else 0.0
        se = max(se_j, se_c) if se_j == se_j else NAN
        z = ic / se if se == se and se > 0 else NAN
        cost = sum(self.cost) / k
        m1, m10 = sum(self.m1) / k, sum(self.m10) / k
        fic = [sum(v) / len(v) if v else NAN for v in self.fr]
        fsp = [sum(v) / len(v) if v else NAN for v in self.fs]
        sgn = 1 if ic > 0 else -1
        stable = all(f == f and f * sgn > 0 for f in fic) and all(f == f and f * sgn > 0 for f in fsp)
        return {"k": k, "n_obs": self.n, "ic": ic, "se_jack": se_j, "se_inst": se_c, "z": z,
                "p": phi_p(z) if z == z else NAN, "fold_ic": fic, "fold_spread": fsp, "stable": stable,
                "spread_bps": spread, "spread_se": se_js, "d1_bps": m1, "d10_bps": m10, "cost_bps": cost,
                "tradab": abs(spread) / cost, "leg_ratio": max(abs(m1), abs(m10)) / cost, "per_inst": self.per}


# ---------------------------------------------------------------- puissance (rendements futurs seulement)
def fold_fn(ws_day, h):
    bs = bsize(h)
    days = G // 1440

    def f(b):
        d = max(b * bs, ws_day)
        return min(2, int(3 * (d - ws_day) / max(1, days - ws_day)))
    return f


def power_inst(inst, h, lo=0):
    idx, y, _b, _r = build_pop(inst, h, lo)
    n = len(idx)
    if n < MIN_OBS:
        return {"n": n, "n_eff": 0.0, "sigma": NAN, "mde": NAN, "ok": False}
    sig = statistics.pstdev(y)
    n_eff = n * min(1.0, STRIDE[h] / h)
    se = sig * math.sqrt(2.0 / (0.1 * n_eff))
    mde = Z_MDE * se
    return {"n": n, "n_eff": n_eff, "sigma": sig, "se": se, "mde": mde, "ok": mde <= KAPPA * inst.cost}


def mean_pair_corr(insts_ok, h, lo=0):
    cols = {}
    for n, inst in insts_ok.items():
        idx, y, _b, _r = build_pop(inst, h, lo)
        cols[n] = dict(zip(idx, y))
    cs = []
    names = list(cols)
    for a in range(len(names)):
        for b in range(a + 1, len(names)):
            ca, cb = cols[names[a]], cols[names[b]]
            common = [i for i in ca if i in cb]
            if len(common) >= 50:
                xa, xb = [ca[i] for i in common], [cb[i] for i in common]
                if statistics.pstdev(xa) > 0 and statistics.pstdev(xb) > 0:
                    cs.append(statistics.correlation(xa, xb))
    return sum(cs) / len(cs) if cs else RHO_FALLBACK


def power_group(insts, h, lo=0):
    per = {n: power_inst(i, h, lo) for n, i in insts.items()}
    ok = {n: insts[n] for n, p in per.items() if p["ok"]}
    if len(ok) < 3:
        return per, {"ok": False, "k_ok": len(ok), "mde": NAN, "rho": NAN, "cost": NAN}
    rho = mean_pair_corr(ok, h, lo)
    k = len(ok)
    k_eff = k / (1 + (k - 1) * max(rho, 0.0))
    se = sum(per[n]["se"] for n in ok) / k / math.sqrt(k_eff)
    cost = sum(i.cost for i in ok.values()) / k
    mde = Z_MDE * se
    return per, {"ok": mde <= KAPPA * cost, "k_ok": k, "mde": mde, "rho": rho, "cost": cost, "ok_names": sorted(ok)}


# ---------------------------------------------------------------- exécution
def compute(group, insts, variants, seed, only=None, log=None, aux=None):
    """Retourne {(fam, var, h, variant): résultat}. variants : sous-ensemble de ('real','lag','shuffle')."""
    rng = random.Random("%s-%d" % (group, seed))
    pw = {(w, h): power_group(insts, h, win_lo(w, group)) for w in ("long", "F1", "F7") for h in HORIZONS}
    out = {}
    for fam, var, groups, need, binary in SPEC:
        if group not in groups or (only and var not in only):
            continue
        have = [n for n in insts if has_inst_source(insts[n], need)]
        if len(have) < 3:
            continue
        accs = {}
        t0 = time.time()
        wsd = max(min(start_day_for(insts[m], fam, var) for m in have), win_lo(fam, group) // 1440)
        for n in have:
            inst = insts[n]
            x = make_var(var, inst, insts, aux)
            if x is None:
                continue
            ws = start_day_for(inst, fam, var)
            xs = {"real": x}
            if "lag" in variants:
                xs["lag"] = placebo_lag(x, rng)
            if "shuffle" in variants:
                xs["shuffle"] = placebo_shuffle(x, rng)
            for v in variants:
                for h in HORIZONS:
                    info = pw[(win_of(fam), h)][1]
                    if not info["ok"] or n not in info["ok_names"]:
                        continue
                    c = inst_cell(xs[v], inst, h, binary, fold_fn(wsd, h), win_lo(fam, group))
                    if c is not None:
                        accs.setdefault((v, h), Acc()).add(n, c)
        for (v, h), a in accs.items():
            if a.k >= 3:
                out[(fam, var, h, v)] = a.result()
        if log:
            log("%s %s/%s %.0fs" % (group, fam, var, time.time() - t0))
    return out, pw


def has_inst_source(inst, need):
    if need == "klines":
        return True
    return {"trades": inst.tr is not None, "funding": inst.FR is not None, "mark": inst.MK is not None,
            "bn": inst.bn is not None}[need]


def bh_q(ps):
    """Valeurs q de Benjamini-Hochberg ; ps : liste de p-valeurs (NaN = non testé -> NaN)."""
    idx = sorted((i for i, p in enumerate(ps) if p == p), key=lambda i: ps[i])
    m = len(idx)
    q = [NAN] * len(ps)
    prev = 1.0
    for r in range(m, 0, -1):
        i = idx[r - 1]
        prev = min(prev, ps[i] * m / r)
        q[i] = prev
    return q


# ---------------------------------------------------------------- sorties
GRID_COLS = ["family", "variable", "group", "horizon_min", "status", "k_inst", "n_obs", "ic", "se_jack", "se_inst",
             "z", "p_raw", "z_cal", "p_cal", "q_cal", "q_raw", "fold1_ic", "fold2_ic", "fold3_ic", "fold1_sp",
             "fold2_sp", "fold3_sp", "stable", "d1_bps", "d10_bps", "spread_bps", "spread_se", "cost_bps",
             "tradability", "leg_ratio", "mde_group_bps", "mde_over_cost", "z_lag", "z_shuffle", "passes_stage1"]


def nn(v):
    return None if isinstance(v, float) and v != v else v


def power_tables(data="data", log=print):
    """Puissance par groupe et horizon, à partir des seuls rendements futurs. Retourne (json, lignes csv)."""
    out, rows = {}, []
    for g in GROUPS:
        insts = load_group(g, data, light=True)
        out[g] = {}
        for w in ("long", "F1", "F7"):
          if w != "long" and (w, g) not in WIN_LO:
              continue
          out[g][w] = {}
          for h in HORIZONS:
            per, info = power_group(insts, h, win_lo(w, g))
            d = {k: nn(v) for k, v in info.items()}
            d["per"] = {n: {k: nn(v) for k, v in p.items()} for n, p in per.items()}
            out[g][w][str(h)] = d
            for n, p in per.items():
                rows.append([g, w, h, n, p["n"], "%.0f" % p["n_eff"], "%.1f" % p["sigma"] if p["sigma"] == p["sigma"]
                             else "", "%.1f" % p["mde"] if p["mde"] == p["mde"] else "", "%.1f" % insts[n].cost,
                             "ok" if p["ok"] else "sous-puissant"])
            log("%-8s %-4s h=%-5d groupe ok=%s k=%d MDE=%s cout=%s rho=%s" % (
                g, w, h, info["ok"], info["k_ok"], "%.1f" % info["mde"] if info["mde"] == info["mde"] else "-",
                "%.1f" % info["cost"] if info["cost"] == info["cost"] else "-",
                "%.2f" % info["rho"] if info["rho"] == info["rho"] else "-"))
    return out, rows


def retained_cells(power, data="data"):
    keep = []
    need_of = {v: n for f, v, gs, n, b in SPEC}
    for fam, var, g, h in planned_cells(data):
        info = power[g][win_of(fam)][str(h)] if win_of(fam) in power[g] else power[g]["long"][str(h)]
        if not info["ok"]:
            continue
        names = [n for n in info["ok_names"] if has_source(n, need_of[var], data)]
        if len(names) >= 3:
            keep.append((fam, var, g, h))
    return keep


def write_heatmaps(rows, outdir):
    colw, rowh, lab = 34, 18, 120
    cols = [(g, h) for g in GROUPS for h in HORIZONS]
    for fam in FAMILIES:
        vars_ = [v for f, v, gs, n, b in SPEC if f == fam]
        W, Hh = lab + colw * len(cols) + 10, 70 + rowh * len(vars_) + 30
        parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" font-family="monospace" '
                 'font-size="10">' % (W, Hh), '<rect width="100%" height="100%" fill="white"/>',
                 '<text x="4" y="14" font-size="12">%s : IC de rang moyen par (variable, groupe, horizon) ; rouge = IC>0, '
                 'bleu = IC&lt;0 (saturé à +-0.04) ; gris = exclu ; cadre noir = FDR 5 %%</text>' % fam]
        for j, (g, h) in enumerate(cols):
            parts.append('<text x="%d" y="62" transform="rotate(-60 %d 62)">%s %s</text>' % (
                lab + j * colw + 8, lab + j * colw + 8, g[:5], "%dm" % h if h < 60 else "%dh" % (h // 60)))
        for r, v in enumerate(vars_):
            y = 70 + r * rowh
            parts.append('<text x="4" y="%d">%s</text>' % (y + 13, v))
            for j, (g, h) in enumerate(cols):
                c = rows.get((fam, v, g, h))
                x = lab + j * colw
                if c is None:
                    fill, stroke, txt = "#ffffff", "#eeeeee", ""
                elif c["status"] != "included":
                    fill, stroke, txt = "#d9d9d9", "#ffffff", ""
                else:
                    t = max(-1.0, min(1.0, c["ic"] / 0.04))
                    if t >= 0:
                        fill = "rgb(255,%d,%d)" % (255 - int(200 * t), 255 - int(200 * t))
                    else:
                        fill = "rgb(%d,%d,255)" % (255 + int(200 * t), 255 + int(200 * t))
                    stroke = "#000000" if c["q_cal"] == c["q_cal"] and c["q_cal"] <= 0.05 else "#ffffff"
                    txt = "%+.0f" % (1000 * c["ic"])
                parts.append('<rect x="%d" y="%d" width="%d" height="%d" fill="%s" stroke="%s"/>' % (
                    x, y, colw - 1, rowh - 1, fill, stroke))
                if txt:
                    parts.append('<text x="%d" y="%d" fill="#333">%s</text>' % (x + 3, y + 12, txt))
        parts.append('<text x="4" y="%d">valeurs dans les cellules : IC x 1000</text></svg>' % (Hh - 6))
        with open(os.path.join(outdir, "heatmap_%s.svg" % fam), "w", encoding="utf-8") as f:
            f.write("\n".join(parts))


def fmt(x):
    if x is None or (isinstance(x, float) and x != x):
        return ""
    return ("%.5g" % x) if isinstance(x, float) else str(x)


def run_all(data="data", outdir="results", seed=20261005, log=print):
    with open(os.path.join(outdir, "etage1_power.json"), encoding="utf-8") as f:
        power = json.load(f)
    real, lag, shuf = {}, {}, {}
    mde = {}
    for g in GROUPS:
        insts = load_group(g, data)
        aux = {"NAS100-USD": load_klines("NAS100-USD", data)} if g == "equity" else {}
        res, pw = compute(g, insts, ("real", "lag", "shuffle"), seed, log=log, aux=aux)
        for (fam, var, h, v), r in res.items():
            {"real": real, "lag": lag, "shuffle": shuf}[v][(fam, var, g, h)] = r
        for (w, h), v in pw.items():
            mde[(g, w, h)] = (v[1]["mde"], v[1]["cost"])
    zpl = [r["z"] for d in (lag, shuf) for r in d.values() if r["z"] == r["z"]]
    lam = max(1.0, statistics.median(abs(z) for z in zpl) / 0.6745) if zpl else 1.0
    cells = {}
    planned = planned_cells(data)
    keys_inc = [k for k in planned if k in real]
    pcal = [phi_p(real[k]["z"] / lam) if real[k]["z"] == real[k]["z"] else NAN for k in keys_inc]
    qcal = bh_q(pcal)
    qraw = bh_q([real[k]["p"] for k in keys_inc])
    qmap = {k: (qcal[i], qraw[i], pcal[i]) for i, k in enumerate(keys_inc)}
    inst_rows = []
    for k in planned:
        fam, var, g, h = k
        m = mde.get((g, win_of(fam), h), (NAN, NAN))
        base = {"family": fam, "variable": var, "group": g, "horizon_min": h, "mde_group_bps": m[0],
                "mde_over_cost": m[0] / m[1] if m[1] == m[1] and m[1] else NAN}
        if k not in real:
            base["status"] = "sous-puissant" if not (power[g].get(win_of(fam)) or power[g]["long"])[str(h)]["ok"] else "indisponible"
        else:
            r = real[k]
            qc, qr, pc = qmap[k]
            base.update({"status": "included", "k_inst": r["k"], "n_obs": r["n_obs"], "ic": r["ic"],
                         "se_jack": r["se_jack"], "se_inst": r["se_inst"], "z": r["z"], "p_raw": r["p"],
                         "z_cal": r["z"] / lam if r["z"] == r["z"] else NAN, "p_cal": pc, "q_cal": qc, "q_raw": qr,
                         "fold1_ic": r["fold_ic"][0], "fold2_ic": r["fold_ic"][1], "fold3_ic": r["fold_ic"][2],
                         "fold1_sp": r["fold_spread"][0], "fold2_sp": r["fold_spread"][1],
                         "fold3_sp": r["fold_spread"][2], "stable": int(r["stable"]), "d1_bps": r["d1_bps"],
                         "d10_bps": r["d10_bps"], "spread_bps": r["spread_bps"], "spread_se": r["spread_se"],
                         "cost_bps": r["cost_bps"], "tradability": r["tradab"], "leg_ratio": r["leg_ratio"],
                         "z_lag": lag[k]["z"] if k in lag else NAN, "z_shuffle": shuf[k]["z"] if k in shuf else NAN})
            base["passes_stage1"] = int(qc == qc and qc <= 0.05 and r["stable"] and r["tradab"] > 1.0)
            for n, rho in r["per_inst"].items():
                inst_rows.append([fam, var, g, h, n, "%.5f" % rho])
        cells[k] = base
    with open(os.path.join(outdir, "grille_etage1.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(GRID_COLS)
        for k in planned:
            w.writerow([fmt(cells[k].get(col)) for col in GRID_COLS])
    with open(os.path.join(outdir, "grille_etage1_instruments.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["family", "variable", "group", "horizon_min", "instrument", "ic"])
        w.writerows(inst_rows)
    write_heatmaps(cells, outdir)
    return cells, lam, lag, shuf


def summarize(cells, lam, lag, shuf):
    inc = [c for c in cells.values() if c["status"] == "included"]
    out = ["cellules planifiées %d ; testées (incluses) %d ; sous-puissantes %d ; indisponibles %d" % (
        len(cells), len(inc), sum(c["status"] == "sous-puissant" for c in cells.values()),
        sum(c["status"] == "indisponible" for c in cells.values())),
        "faux positifs attendus à p<0.05 non corrigé : %.1f ; sous BH q<=5 %% : au plus 5 %% des découvertes"
        % (0.05 * len(inc))]
    for name, d in (("placebo décalé", lag), ("placebo mélangé", shuf)):
        zs = [r["z"] for r in d.values() if r["z"] == r["z"]]
        ps = [r["p"] for r in d.values() if r["p"] == r["p"]]
        q = bh_q(ps)
        out.append("%s : %d cellules, p<0.05 : %.1f %% (nominal 5 %%), p<0.01 : %.1f %%, découvertes BH 5 %% : %d, "
                   "|z| max %.2f, écart-type robuste de z %.2f" % (
                       name, len(zs), 100 * sum(p < 0.05 for p in ps) / max(1, len(ps)),
                       100 * sum(p < 0.01 for p in ps) / max(1, len(ps)), sum(x <= 0.05 for x in q if x == x),
                       max(abs(z) for z in zs), statistics.median(abs(z) for z in zs) / 0.6745))
    out.append("facteur d'étalonnage lambda (écart-type robuste des z placebos, borné à >= 1) : %.3f" % lam)
    real_ps = [c["p_raw"] for c in inc if c["p_raw"] == c["p_raw"]]
    out.append("réel : p<0.05 non corrigé %d (%.1f %%), BH q<=5 %% sans étalonnage %d, avec étalonnage %d" % (
        sum(p < 0.05 for p in real_ps), 100 * sum(p < 0.05 for p in real_ps) / max(1, len(real_ps)),
        sum(c["q_raw"] <= 0.05 for c in inc if c["q_raw"] == c["q_raw"]),
        sum(c["q_cal"] <= 0.05 for c in inc if c["q_cal"] == c["q_cal"])))
    fdr = [c for c in inc if c["q_cal"] == c["q_cal"] and c["q_cal"] <= 0.05]
    stab = [c for c in fdr if c["stable"]]
    trad = [c for c in stab if c["tradability"] > 1.0]
    out.append("portes : FDR %d -> stable sur 3 plis %d -> ratio de tradabilité > 1 : %d" % (
        len(fdr), len(stab), len(trad)))
    top = sorted((c for c in inc if c["z"] == c["z"]), key=lambda c: -abs(c["z"]))[:25]
    out += ["", "25 cellules au |z| le plus grand (réel), PAS une sélection de décision :",
            "%-4s %-12s %-8s %6s %3s %8s %7s %7s %8s %8s %6s %5s %5s" % (
                "fam", "variable", "groupe", "h_min", "k", "IC", "z", "q_cal", "spread", "coût", "ratio", "stab",
                "pass")]
    for c in top:
        out.append("%-4s %-12s %-8s %6d %3d %+8.4f %7.2f %7.3f %8.2f %8.1f %6.2f %5d %5d" % (
            c["family"], c["variable"], c["group"], c["horizon_min"], c["k_inst"], c["ic"], c["z"], c["q_cal"],
            c["spread_bps"], c["cost_bps"], c["tradability"], c["stable"], c["passes_stage1"]))
    top2 = sorted(inc, key=lambda c: -c["tradability"])[:15]
    out += ["", "15 cellules au ratio de tradabilité le plus grand (descriptif) :"]
    for c in top2:
        out.append("%-4s %-12s %-8s %6d %3d IC %+8.4f z %6.2f q %6.3f spread %8.2f coût %5.1f ratio %5.2f" % (
            c["family"], c["variable"], c["group"], c["horizon_min"], c["k_inst"], c["ic"], c["z"], c["q_cal"],
            c["spread_bps"], c["cost_bps"], c["tradability"]))
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["plan", "power", "run"], required=True)
    ap.add_argument("--data", default="data")
    ap.add_argument("--out", default="results")
    a = ap.parse_args()
    if a.mode == "plan":
        cells = planned_cells(a.data)
        lines = ["CELLULES PLANIFIÉES (avant exclusion de puissance) : %d" % len(cells)]
        for g in GROUPS:
            n = sum(1 for c in cells if c[2] == g)
            lines.append("  %-8s %4d cellules, %d variables" % (g, n, n // len(HORIZONS)))
        for fam in FAMILIES:
            lines.append("  %s : %d cellules" % (fam, sum(1 for c in cells if c[0] == fam)))
        lines.append("  variables distinctes : %d ; (variable, groupe) : %d" % (len(SPEC), len(cells) // len(HORIZONS)))
        text = "\n".join(lines)
        print(text)
        open(os.path.join(a.out, "etage1_plan.txt"), "w", encoding="utf-8").write(text + "\n")
    elif a.mode == "power":
        power, rows = power_tables(a.data)
        with open(os.path.join(a.out, "etage1_power.json"), "w", encoding="utf-8") as f:
            json.dump(power, f)
        with open(os.path.join(a.out, "etage1_power.csv"), "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["group", "window", "horizon_min", "instrument", "n_obs", "n_eff", "sigma_bps", "mde_spread_bps",
                        "cost_bps", "status"])
            w.writerows(rows)
        keep = retained_cells(power, a.data)
        planned = planned_cells(a.data)
        text = "cellules planifiées %d ; retenues après exclusion de puissance %d ; exclues %d" % (
            len(planned), len(keep), len(planned) - len(keep))
        print(text)
        with open(os.path.join(a.out, "etage1_plan.txt"), "a", encoding="utf-8") as f:
            f.write(text + "\n")
    else:
        t0 = time.time()
        cells, lam, lag, shuf = run_all(a.data, a.out, log=lambda s: print(s, flush=True))
        text = summarize(cells, lam, lag, shuf)
        print(text)
        open(os.path.join(a.out, "etage1_summary.txt"), "w", encoding="utf-8").write(text + "\n")
        print("durée %.0f s" % (time.time() - t0))


if __name__ == "__main__":
    main()
