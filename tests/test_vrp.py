"""Tests de tools/vrp_study.py : Black-Scholes et P&L calculés à la main, levier et drawdown, échantillonnage, absence d'anticipation, contrôles positif et nul.
stdlib uniquement, aucun réseau. Lancé par ctest.
"""
import datetime as dt
import math
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import vrp_study as vs  # noqa: E402

RF = ([dt.date(1990, 1, 1)], [0.0])


def synth(n, true_vol, vix_level, seed):
    """SPY synthétique à volatilité vraie constante, VIX constant : prix bruts quotidiens."""
    rng = random.Random(seed)
    d, p = dt.date(2000, 1, 3), 100.0
    spy, vix = {}, {}
    for _ in range(n):
        while d.weekday() >= 5:
            d += dt.timedelta(1)
        spy[d] = p
        vix[d] = vix_level
        p *= math.exp(rng.gauss(0, true_vol / math.sqrt(252)))
        d += dt.timedelta(1)
    return vix, spy


class BlackScholes(unittest.TestCase):
    def test_atm_one_year_by_hand(self):
        # S = K = 100, sigma = 0,2, T = 1, r = 0 : call = put = 100 x (2 Phi(0,1) - 1) = 7,9656
        c, p = vs.bs(100.0, 100.0, 0.2, 1.0, 0.0)
        self.assertAlmostEqual(c, 7.9656, places=3)
        self.assertAlmostEqual(p, 7.9656, places=3)

    def test_put_call_parity(self):
        c, p = vs.bs(100.0, 95.0, 0.3, 0.25, 0.03)
        self.assertAlmostEqual(c - p, 100.0 - 95.0 * math.exp(-0.03 * 0.25), places=9)


class Payoffs(unittest.TestCase):
    def test_pnl_by_hand_and_sampling(self):
        vix, spy = {}, {}
        d = dt.date(2010, 1, 4)
        k = 0
        while k < 60:
            if d.weekday() < 5:
                spy[d] = 100.0 + k * 0.0                          # prix plat sauf le jour de règlement
                vix[d] = 0.20
                k += 1
            d += dt.timedelta(1)
        ds = sorted(spy)
        spy[ds[21]] = 90.0                                        # le premier règlement (t+21) tombe à -10 %
        ms = vs.months(vix, spy, RF, 0.015, 0.005)
        m = ms[0]
        sigma = 0.20 - 0.015 - 0.005
        c, p = vs.bs(1.0, 1.0, sigma, vs.T_M, 0.0)
        self.assertEqual(m["d0"], ds[0])
        self.assertEqual(m["d1"], ds[21])                         # pas de 21 jours de cotation
        self.assertAlmostEqual(m["ret"], -0.10, places=12)
        self.assertAlmostEqual(m["e1"], p - 0.10, places=12)       # put vendu : prime moins la perte à l'échéance (S0 - ST = 10 %)
        self.assertAlmostEqual(m["e2"], p + c - 0.10, places=12)   # straddle : prime moins |mouvement|

    def test_leverage_equity_and_drawdown_by_hand(self):
        ms = [{"rf": 0.0, "e1": 0.05}, {"rf": 0.0, "e1": -0.20}, {"rf": 0.0, "e1": 0.10}]
        path = vs.equity(ms, "e1", 2.0)                            # 1,10 puis 0,66 puis 0,792
        self.assertAlmostEqual(path[1], 1.10, places=12)
        self.assertAlmostEqual(path[2], 1.10 * 0.60, places=12)
        self.assertAlmostEqual(vs.maxdd(path), 1 - 0.60, places=12)
        ruin = vs.equity([{"rf": 0.0, "e1": -0.6}], "e1", 2.0)     # perte de 120 % : capital annulé
        self.assertEqual(ruin[-1], 0.0)
        self.assertAlmostEqual(vs.cvar5([float(i) for i in range(100)]), 2.0, places=12)    # moyenne des 5 plus petites : (0+1+2+3+4)/5

    def test_no_lookahead_entry_uses_only_vix_at_entry(self):
        vix, spy = synth(200, 0.15, 0.20, 1)
        a = vs.months(vix, spy, RF)
        vix2 = dict(vix)
        for d in sorted(vix2)[22:]:
            vix2[d] = 0.99                                         # on réécrit le VIX après la première entrée
        b = vs.months(vix2, spy, RF)
        self.assertEqual(a[0]["e1"], b[0]["e1"])                  # l'entrée n'a utilisé que le VIX du jour d'entrée


class Controls(unittest.TestCase):
    def test_positive_control_overpriced_options_are_found(self):
        vix, spy = synth(6000, 0.15, 0.30, 2)                      # volatilité vraie 15 %, VIX 30 % : prime énorme
        ms = vs.months(vix, spy, RF)
        s = vs.stats(ms, "e1", 1.0)
        self.assertGreater(s["z"], 4.0)
        self.assertGreater(s["mean"], 0.01)

    def test_null_fairly_priced_options_give_no_premium(self):
        vix, spy = synth(6000, 0.20, 0.20 + vs.HAIRCUT + vs.HALF_SPREAD, 3)     # volatilité implicite vendue = volatilité vraie
        ms = vs.months(vix, spy, RF)
        s = vs.stats(ms, "e1", 1.0)
        self.assertLess(abs(s["z"]), 3.5)

    def test_cheap_options_lose(self):
        vix, spy = synth(6000, 0.30, 0.15, 4)                      # on vend trop bon marché
        s = vs.stats(vs.months(vix, spy, RF), "e1", 1.0)
        self.assertLess(s["mean"], 0)

    def test_test_window_refuses_when_discovery_fails_or_locked(self):
        self.assertTrue(vs.LOCK.endswith("vrp_test.lock"))


if __name__ == "__main__":
    unittest.main()
