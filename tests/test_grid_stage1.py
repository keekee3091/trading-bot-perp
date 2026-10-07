"""Tests de tools/grid_stage1.py : rangs, BH, déciles à la main ; contrôle positif ; nul ; absence d'anticipation.

Contrôle positif : une relation injectée de signe connu (saisonnalité intrajournalière, autocorrélation des rendements)
doit être retrouvée avec le bon signe et passer le FDR ; sur du bruit pur rien ne passe le FDR ; aucune variable à
l'instant t ne change quand on supprime le futur de la série. stdlib uniquement, aucun réseau. Lancé par ctest.
"""
import array
import math
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import grid_stage1 as gs  # noqa: E402

NAN = float("nan")


def same(a, b):
    return (a != a and b != b) or a == b


def synth_inst(name, rng, n, phi=0.0, tod=0.0, sd=5.0):
    """Rendements par minute : AR(1) (phi) + saisonnalité tod*sin(2 pi minute/1440) bps + bruit sd."""
    inst = gs.Inst(name)
    inst.C, inst.H, inst.L = gs.narr(), gs.narr(), gs.narr()
    inst.V, inst.NT, inst.S = gs.narr(1.0), gs.narr(1.0), gs.narr(1.0)
    p, r = 100.0, 0.0
    for i in range(n):
        r = phi * r + tod * math.sin(2 * math.pi * ((i % 1440) + 1) / 1440) + rng.gauss(0, sd)
        p *= math.exp(r / 1e4)
        inst.C[i] = inst.H[i] = inst.L[i] = p
    inst.start = 0
    inst.cost = 14.0
    return inst


def run_synth(rng, n, only, **kw):
    gs.G = n
    gs.CAL.clear()
    insts = {nm: synth_inst(nm, rng, n, **kw) for nm in ("BTC-USD", "ETH-USD", "SOL-USD", "HYPE-USD")}
    res, _pw = gs.compute("crypto", insts, ("real",), 1, only=only)
    return res


class Basics(unittest.TestCase):
    def test_rank_avg_ties_by_hand(self):
        # valeurs 3, 1, 3, 2 : rangs 3.5, 1, 3.5, 2 (les deux 3 occupent les rangs 3 et 4)
        self.assertEqual(gs.rank_avg([3.0, 1.0, 3.0, 2.0]), [3.5, 1.0, 3.5, 2.0])

    def test_rho_perfect_and_inverse(self):
        x = [float(i) for i in range(1, 101)]
        for y, want in ((x, 1.0), (x[::-1], -1.0)):
            s = (len(x), sum(x), sum(y), sum(a * a for a in x), sum(a * a for a in y), sum(a * b for a, b in zip(x, y)))
            self.assertAlmostEqual(gs.rho_f(*s), want, places=12)

    def test_bh_by_hand(self):
        # p = 0.01, 0.04, 0.03, 0.20 (m = 4) : triés 0.01, 0.03, 0.04, 0.20 ; p x m / rang = 0.04, 0.06, 0.0533, 0.20
        # monotonie descendante : q(0.20) = 0.20, q(0.04) = min(0.20, 0.0533) = 0.0533, q(0.03) = min(0.0533, 0.06) = 0.0533,
        # q(0.01) = min(0.0533, 0.04) = 0.04
        q = gs.bh_q([0.01, 0.04, 0.03, 0.20])
        for got, want in zip(q, [0.04, 0.16 / 3, 0.16 / 3, 0.20]):
            self.assertAlmostEqual(got, want, places=12)

    def test_roll_sum_and_ext(self):
        gs.G = 6
        a = array.array("d", [NAN, 1.0, 2.0, 3.0, 4.0, 5.0])
        s = gs.roll_sum(a, 2)
        self.assertTrue(math.isnan(s[0]) and math.isnan(s[1]))
        self.assertEqual(list(s[2:]), [3.0, 5.0, 7.0, 9.0])
        self.assertEqual(list(gs.roll_ext(a, 3, True)[3:]), [3.0, 4.0, 5.0])
        self.assertEqual(list(gs.roll_ext(a, 3, False)[3:]), [1.0, 2.0, 3.0])

    def test_inst_cell_decile_by_hand(self):
        # 400 observations, x = y = rang croissant : IC = 1 ; D10 = 40 dernières valeurs de y, D1 = 40 premières
        gs.G = 3 * 1440
        inst = synth_inst("A", random.Random(1), gs.G)
        inst.pops[(1, 0)] = (list(range(400)), [float(i) for i in range(400)], [i // 100 for i in range(400)],
                             gs.rank_avg([float(i) for i in range(400)]))
        x = array.array("d", [float(i) for i in range(gs.G)])
        c = gs.inst_cell(x, inst, 1, False, lambda b: min(2, b), 0)
        self.assertAlmostEqual(c["rho"], 1.0, places=12)
        # D1 : y = 0..39 (moyenne 19.5) ; D10 : y = 360..399 (moyenne 379.5) ; écart 360
        self.assertAlmostEqual(c["m1"], 19.5, places=9)
        self.assertAlmostEqual(c["m10"], 379.5, places=9)
        self.assertAlmostEqual(c["spread"], 360.0, places=9)


class Plumbing(unittest.TestCase):
    def test_injected_seasonality_found_with_right_sign(self):
        for tod in (0.8, -0.8):
            res = run_synth(random.Random(11), 30 * 1440, {"tod_sin"}, tod=tod)
            r = res[("F5", "tod_sin", 15, "real")]
            self.assertGreater(abs(r["z"]), 4.0)
            self.assertEqual(r["ic"] > 0, tod > 0)
            self.assertEqual(r["spread_bps"] > 0, tod > 0)

    def test_injected_autocorrelation_found(self):
        res = run_synth(random.Random(12), 20 * 1440, {"rn_15"}, phi=0.2, sd=5.0)
        r = res[("F2", "rn_15", 1, "real")]
        self.assertGreater(r["ic"], 0.02)
        self.assertGreater(r["z"], 4.0)

    def test_null_nothing_survives_fdr(self):
        names = {"rn_5", "rn_15", "rn_60", "range_15", "range_60", "tod_sin", "tod_cos", "dow_sin", "dow_cos",
                 "prox_open", "zf_60", "vr_15_240", "xs_ret_5", "resid_15"}
        res = {}
        for seed in (21, 22):
            res.update({(k, seed): v for k, v in run_synth(random.Random(seed), 12 * 1440, names).items()})
        ps = [v["p"] for v in res.values()]
        self.assertGreater(len(ps), 40)
        q = [x for x in gs.bh_q(ps) if x == x]
        self.assertTrue(min(q) > 0.05, min(q))
        self.assertLess(sum(p < 0.05 for p in ps) / len(ps), 0.2)


class NoLookahead(unittest.TestCase):
    def test_truncation_does_not_change_the_past(self):
        N, CUT = 3 * 1440, 2 * 1440 + 500
        rng = random.Random(5)
        gs.G = N
        gs.CAL.clear()
        names = ["BTC-USD", "ETH-USD", "SOL-USD", "HYPE-USD"]
        full = {n: synth_inst(n, rng, N, phi=0.1) for n in names}
        trades = {}
        for n, inst in full.items():
            rows = []
            for i in range(N):
                for _ in range(rng.randint(0, 3)):
                    ts = gs.T0_MS + i * 60000 + rng.randint(0, 59999)
                    rows.append((ts, rng.choice((1, -1)), rng.uniform(10, 1000), 100.0, 1.0))
            rows.sort()
            trades[n] = rows
            gs.attach_trades(inst, rows)
            inst.FR = gs.narr()
            for i in range(N):
                inst.FR[i] = (i // 60) * 0.1 if i >= 60 else NAN
        names_ok = ["imb_10s", "imb_5m", "ntr_15m", "vs_1m", "vs_5m", "big_15m", "run_len", "rn_60", "rn_1440",
                    "range_60", "rpos_240", "vr_60_1440", "vov_24h", "idle_before", "zf_60", "fund_lvl", "fund_d1h",
                    "xs_fund", "ph_pre", "tod_sin", "prox_open", "lead_btc_5", "xs_ret_5", "resid_15", "resid_60"]
        want = {}
        for v in names_ok:
            want[v] = {n: gs.make_var(v, full[n], full) for n in names}
        # série tronquée : on reconstruit tout à partir de CUT minutes seulement
        gs.G = CUT
        gs.CAL.clear()
        cut = {}
        for n, inst in full.items():
            c = gs.Inst(n)
            for a in ("C", "H", "L", "V", "NT", "S"):
                setattr(c, a, getattr(inst, a)[:CUT])
            c.start, c.cost = inst.start, inst.cost
            gs.attach_trades(c, [t for t in trades[n] if t[0] < gs.T0_MS + CUT * 60000])
            c.FR = inst.FR[:CUT]
            cut[n] = c
        for v in names_ok:
            for n in names:
                a = want[v][n]
                b = gs.make_var(v, cut[n], cut)
                if a is None:   # le meneur n'est pas sa propre cible
                    self.assertIsNone(b)
                    continue
                bad = [i for i in range(CUT) if not same(a[i], b[i])]
                self.assertEqual(bad[:3], [], "%s %s utilise le futur aux indices %s" % (v, n, bad[:3]))


if __name__ == "__main__":
    unittest.main()
