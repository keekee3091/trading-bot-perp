"""Tests de tools/tsmom_study.py : poids, coûts, funding, liquidation calculés à la main ; plomberie sur tendance injectée.

Plomberie : une série à régimes de tendance nets (hausse puis baisse) doit être capturée par le momentum, du bon côté ;
le long seul reste à plat en baisse ; le signal inversé perd. Comptabilité : equity finale = initiale + somme des PnL nets.
stdlib uniquement, aucun réseau. Lancé par ctest.
"""
import math
import os
import random
import statistics
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import tsmom_study as ts  # noqa: E402

START = ts.ym(2000, 1)
F = ts.FUND_MONTH  # 0.0045625


def inst_from_returns(rets, spread=2.0, max_lev=20.0, paths=None, name="X"):
    prices = {START: 100.0}
    p = 100.0
    for k, r in enumerate(rets, start=1):
        p *= 1.0 + r
        prices[START + k] = p
    return ts.Inst(name, prices, paths or {}, spread_bps=spread, max_lev=max_lev)


class Constants(unittest.TestCase):
    def test_funding_month(self):
        self.assertAlmostEqual(F, 6.25e-6 * 730, 12)
        self.assertAlmostEqual(F, 0.0045625, 12)
        self.assertAlmostEqual(F * 12 * 100, 5.475, 9)  # 5.475 % par an


class Weights(unittest.TestCase):
    def test_vol_scaling_by_hand(self):
        # 12 rendements alternés +-2 % : écart-type échantillon 0.0208893 x racine(12) = 0.0723627 ; w = 0.10 / 0.0723627
        inst = inst_from_returns([0.02, -0.02] * 8)
        m = START + 12
        self.assertAlmostEqual(inst.sigma(m), 0.07236272269866326, 12)
        w = ts.raw_weight(inst, m, 1, "ls", "volscaled", 0.10)
        self.assertAlmostEqual(w, -0.10 / 0.07236272269866326, 9)  # dernier rendement -2 % : signal vendeur
        self.assertAlmostEqual(ts.raw_weight(inst, m, 1, "lo", "volscaled", 0.10), 0.0, 12)
        self.assertEqual(ts.raw_weight(inst, m, 1, "ls", "equal", 0.10), -1.0)

    def test_weight_cap(self):
        inst = inst_from_returns([0.0001, 0.0002] * 8)  # volatilité minuscule
        self.assertAlmostEqual(ts.raw_weight(inst, START + 12, 1, "ls", "volscaled", 0.10), ts.W_CAP, 12)

    def test_needs_twelve_months(self):
        inst = inst_from_returns([0.01] * 20)
        self.assertIsNone(ts.raw_weight(inst, START + 6, 1, "ls", "equal", 0.10))
        self.assertIsNotNone(ts.raw_weight(inst, START + 12, 1, "ls", "equal", 0.10))


class OneMonth(unittest.TestCase):
    # Hausse de 5 %/mois : signal acheteur, poids 1. Spread 2 bps : coût unitaire (4 + 1 + 2) / 1e4 = 7e-4.
    def test_long_hand_computed(self):
        inst = inst_from_returns([0.05] * 16)
        d = ts.sleeve(inst, (1, "ls", "equal"))
        m1 = START + 13  # premier mois de rendement (signal au mois 12)
        self.assertEqual(min(d), m1)
        self.assertAlmostEqual(d[m1]["gross"], 0.05, 12)
        self.assertAlmostEqual(d[m1]["cost"], 7e-4, 12)
        self.assertAlmostEqual(d[m1]["fund"], F, 12)
        self.assertAlmostEqual(d[m1]["net"], 0.05 - 7e-4 - F, 12)      # 0.0447375
        self.assertAlmostEqual(d[m1 + 1]["net"], 0.05 - F, 12)         # pas de nouveau coût : poids inchangé

    def test_short_receives_funding(self):
        inst = inst_from_returns([-0.05] * 16)
        d = ts.sleeve(inst, (1, "ls", "equal"))
        m1 = START + 13
        self.assertAlmostEqual(d[m1]["w"], -1.0, 12)
        self.assertAlmostEqual(d[m1]["net"], 0.05 - 7e-4 + F, 12)      # 0.0538625 : le short encaisse le funding
        self.assertLess(ts.sleeve(inst, (1, "lo", "equal"))[m1]["net"] + 1e-12, 1e-9)  # long seul : flat, aucun flux

    def test_funding_can_be_removed(self):
        inst = inst_from_returns([0.05] * 16)
        d = ts.sleeve(inst, (1, "ls", "equal"), fund=False)
        self.assertAlmostEqual(d[START + 13]["net"], 0.05 - 7e-4, 12)

    def test_cost_scales_with_turnover(self):
        # passage de +1 à -1 : turnover 2
        rets = [0.05] * 13 + [-0.30, -0.05, -0.05]
        inst = inst_from_returns(rets)
        d = ts.sleeve(inst, (1, "ls", "equal"))
        flip = [m for m in sorted(d) if d[m]["w"] < 0][0]
        self.assertAlmostEqual(d[flip]["cost"], 2 * 7e-4, 12)


class Liquidation(unittest.TestCase):
    # max_lev 20 : mmr 2.5 %. Levier de compte 5x : w = 5. Liquidation si 1 + 5 (x - 1) <= 0.025 x 5 x.
    def test_intramonth_crash_liquidates(self):
        m = START + 13
        paths = {m: [0.81, 1.0]}  # chute de -19 % puis retour : 1 + 5 (-0.19) = 0.05 <= 0.025 x 5 x 0.81 = 0.10125
        inst = inst_from_returns([0.01] * 16, paths={m: [100 * 1.01 ** 12 * 0.81 for _ in [0]]})
        base = 100 * 1.01 ** 12
        inst.path = {m: [base * 0.81, base * 1.01]}
        d = ts.sleeve(inst, (1, "ls", "equal"), lev=5.0)
        self.assertTrue(d[m]["liq"])
        self.assertEqual(d[m]["net"], -1.0)

    def test_shallower_crash_survives(self):
        m = START + 13
        inst = inst_from_returns([0.01] * 16)
        base = 100 * 1.01 ** 12
        inst.path = {m: [base * 0.85, base * 1.01]}  # -15 % : 1 - 0.75 = 0.25 > 0.025 x 5 x 0.85 = 0.10625
        d = ts.sleeve(inst, (1, "ls", "equal"), lev=5.0)
        self.assertFalse(d[m]["liq"])

    def test_month_end_only_series(self):
        # série mensuelle (pas de chemin) : -25 % en fin de mois, 5x -> 1 - 1.25 < 0 : liquidation
        inst = inst_from_returns([0.01] * 12 + [-0.25] + [0.01] * 3)
        d = ts.sleeve(inst, (1, "ls", "equal"), lev=5.0)
        self.assertTrue(d[START + 13]["liq"] and d[START + 13]["net"] == -1.0)

    def test_leverage_cap_by_instrument(self):
        inst = inst_from_returns([0.05] * 16, max_lev=10.0)
        d = ts.sleeve(inst, (1, "ls", "equal"), lev=100.0)
        self.assertAlmostEqual(d[START + 13]["w"], 9.5, 12)  # 95 % du levier max


class Plumbing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.up = [0.02] * 120
        cls.down = [-0.02] * 120
        cls.inst = inst_from_returns(cls.up + cls.down)

    def test_momentum_captures_both_regimes_on_the_right_side(self):
        d = ts.sleeve(self.inst, (3, "ls", "equal"))
        up_months = [d[m]["net"] for m in range(START + 20, START + 110)]
        dn_months = [d[m]["net"] for m in range(START + 130, START + 230)]
        self.assertAlmostEqual(statistics.fmean(up_months), 0.02 - F, 9)      # long : gagne 2 % moins le funding
        self.assertAlmostEqual(statistics.fmean(dn_months), 0.02 + F, 9)      # short : gagne 2 % et reçoit le funding
        self.assertTrue(all(d[m]["w"] > 0 for m in range(START + 20, START + 110)))
        self.assertTrue(all(d[m]["w"] < 0 for m in range(START + 130, START + 230)))

    def test_long_only_is_flat_in_the_downtrend(self):
        d = ts.sleeve(self.inst, (3, "lo", "equal"))
        dn = [d[m]["net"] for m in range(START + 130, START + 230)]
        self.assertTrue(all(abs(x) < 1e-12 for x in dn))  # pas de position, pas de coût, pas de funding

    def test_flipped_signal_loses(self):
        signs = {m: -1 for m in range(START, START + 118)}  # sens inversé en hausse
        d = ts.sleeve(self.inst, (3, "ls", "equal"), signs=signs)
        self.assertLess(statistics.fmean(d[m]["net"] for m in range(START + 20, START + 110)), -0.015)

    def test_noise_does_not_win(self):
        rnd = random.Random(4)
        noise = [rnd.gauss(0.0, 0.04) for _ in range(600)]
        inst = inst_from_returns(noise)
        res = ts.portfolio([inst], (6, "ls", "equal"))
        s = ts.stats(list(res["ret"].values()))
        self.assertLess(s["t"], 2.5)  # pas d'edge sur du bruit

    def test_random_sign_baseline_matches_rhythm_and_loses(self):
        res = ts.portfolio([self.inst], (3, "ls", "equal"))
        a, b = START, START + 240
        sg = ts.random_signs([self.inst], res["per"], a, b, 7)
        self.assertEqual(len(sg[self.inst.name]), len(res["per"][self.inst.name]))
        # chaîne de Markov estimée sur la stratégie : états admis seulement ; sur une tendance pure la chaîne change presque
        # jamais d'état (la stratégie non plus), elle reste donc dans l'état tiré au départ
        self.assertTrue(set(sg[self.inst.name].values()) <= {-1, 0, 1})
        rnd = ts.portfolio([self.inst], (3, "ls", "equal"), signs=sg)
        self.assertLess(statistics.fmean(rnd["ret"].values()), statistics.fmean(res["ret"].values()))


class Accounting(unittest.TestCase):
    def test_equity_identity_and_decomposition(self):
        rnd = random.Random(9)
        a = inst_from_returns([rnd.gauss(0.004, 0.03) for _ in range(200)], name="A", max_lev=50)
        b = inst_from_returns([rnd.gauss(0.002, 0.05) for _ in range(200)], name="B", max_lev=20, spread=4.0)
        for params in ((3, "ls", "volscaled"), (6, "lo", "equal")):
            res = ts.portfolio([a, b], params)
            e0, e = 1000.0, 1000.0
            total = 0.0
            for m in sorted(res["ret"]):
                pnl = e * res["ret"][m]
                total += pnl
                e += pnl
            self.assertAlmostEqual(e, e0 + total, 9)   # equity finale = initiale + somme des PnL nets
            for d in res["per"].values():
                for r in d.values():
                    if not r["liq"]:
                        self.assertAlmostEqual(r["net"], r["gross"] - r["cost"] - r["fund"], 12)

    def test_buy_and_hold_by_hand(self):
        inst = inst_from_returns([0.01] * 16)
        bh = ts.buy_and_hold([inst])
        rs = [bh["ret"][m] for m in sorted(bh["ret"])]
        self.assertAlmostEqual(rs[0], 0.01 - 7e-4 - F, 12)   # coût d'entrée une fois
        self.assertAlmostEqual(rs[1], 0.01 - F, 12)


class Loader(unittest.TestCase):
    def test_month_end_and_path_exclude_non_positive(self):
        rows = [("2020-03-30", 20.0), ("2020-03-31", 18.0), ("2020-04-20", -37.0), ("2020-04-21", 10.0), ("2020-04-30", 18.38)]
        inst = ts.build_inst("WTI", rows, False)
        self.assertAlmostEqual(inst.prices[ts.ym(2020, 3)], 18.0)
        self.assertAlmostEqual(inst.prices[ts.ym(2020, 4)], 18.38)
        self.assertEqual(inst.path[ts.ym(2020, 4)], [10.0, 18.38])  # le point négatif est écarté
        self.assertAlmostEqual(inst.R[ts.ym(2020, 4)], 18.38 / 18.0 - 1.0, 12)

    def test_monthly_source_has_no_path(self):
        inst = ts.build_inst("GOLD", [("2000-01-01", 100.0), ("2000-02-01", 101.0)], True)
        self.assertEqual(inst.path, {})

    def test_dxy_chain(self):
        old = [("2019-12-30", 99.0), ("2019-12-31", 100.0)]
        new = [("2019-12-31", 120.0), ("2020-01-02", 126.0)]
        out = ts.chain_dxy(old, new)
        self.assertEqual(out[-1][0], "2020-01-02")
        self.assertAlmostEqual(out[-1][1], 105.0, 9)


class Statistics(unittest.TestCase):
    def test_stats_by_hand(self):
        s = ts.stats([0.01, 0.03, -0.02, 0.02])
        self.assertAlmostEqual(s["mean"], 0.01, 12)
        self.assertAlmostEqual(s["sharpe"], 0.01 / statistics.stdev([0.01, 0.03, -0.02, 0.02]) * math.sqrt(12), 9)
        self.assertAlmostEqual(s["worst"], -0.02, 12)
        eq = 1.01 * 1.03 * 0.98 * 1.02
        self.assertAlmostEqual(s["cagr"], eq ** 3 - 1, 9)  # 4 mois : exposant 12 / 4
        # drawdown : pic 1.0403 après 2 mois, creux 1.0403 x 0.98 : 2 %
        self.assertAlmostEqual(s["maxdd"], 0.02, 12)

    def test_deflation_penalises_noisy_grids(self):
        calm = ts.deflated_sharpe(1.0, [0.4, 0.6] * 8, 240, 0.0, 3.0)[1]
        noisy = ts.deflated_sharpe(1.0, [0.0, 1.0] * 8, 240, 0.0, 3.0)[1]
        self.assertLess(noisy, calm)


if __name__ == "__main__":
    unittest.main(verbosity=1)
