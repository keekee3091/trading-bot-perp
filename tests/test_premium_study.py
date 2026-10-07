"""Tests de tools/premium_study.py : inversion du funding, aller-retour calculé à la main, plomberie sur prime injectée.

Plomberie : une prime est injectée (funding qui la révèle) puis le prix converge : la stratégie doit la capturer,
du bon côté. Contrôles : sans convergence elle perd exactement le coût ; le sens n'est jamais retourné.
stdlib uniquement, aucun réseau. Lancé par ctest.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import premium_study as ps  # noqa: E402

T0 = 1_791_158_400_000  # lundi 2026-10-05 00:00 UTC, pile sur une heure
HOUR = 3_600_000


def flat_inst(n_hours, base_rate, scale, price=100.0, spread=2.0, max_lev=10.0, sym="X"):
    n = n_hours * 60
    opens = [price] * n
    funding = [(T0 + h * HOUR + 30, base_rate) for h in range(1, n_hours)]
    return ps.Inst(sym, scale, T0, opens, list(opens), list(opens), funding, spread, max_lev)


def set_funding(inst, hour, rate):
    inst.funding = [(ts, rate if ts == T0 + hour * HOUR + 30 else r) for ts, r in inst.funding]


class Inversion(unittest.TestCase):
    def test_band_is_censored(self):
        self.assertIsNone(ps.implied_premium(6.25e-6, 0.5))   # non crypto, intérêt fixe : 0.5 x 0.0001 / 8
        self.assertIsNone(ps.implied_premium(1.25e-5, 1.0))   # crypto
        self.assertIsNone(ps.implied_premium(1.25e-5 + 1e-12, 1.0))  # tolérance flottante

    def test_positive_and_negative_premium(self):
        # P = +20 bps (0.0020) : u = P - 0.0005 = 0.0015 ; FR = u x 0.5 / 8 = 9.375e-5
        self.assertAlmostEqual(ps.implied_premium(9.375e-5, 0.5), 0.0020, 12)
        # P = -20 bps : u = P + 0.0005 = -0.0015 ; FR = -9.375e-5
        self.assertAlmostEqual(ps.implied_premium(-9.375e-5, 0.5), -0.0020, 12)
        # crypto, P = +30 bps : u = 0.0025 ; FR = 0.0025 / 8 = 3.125e-4
        self.assertAlmostEqual(ps.implied_premium(3.125e-4, 1.0), 0.0030, 12)

    def test_roundtrip_formula(self):
        # la formule de la doc puis son inversion redonnent P pour P hors bande
        for scale in (1.0, 0.5):
            for p in (0.0007, 0.0015, 0.004, -0.0006, -0.002, -0.006):
                u = p + max(-0.0005, min(0.0005, 0.0001 - p))
                self.assertAlmostEqual(ps.implied_premium(scale * u / 8, scale), p, 12)


class OneTrade(unittest.TestCase):
    # Short à 100 (premium +20 bps), prix à 99.6 quatre heures plus tard, spread 2 bps, 4 x taux de base reçu.
    # p_in = 100 (1 - 3e-4) = 99.97 ; p_out = 99.6 (1 + 3e-4) = 99.62988 ; brut = -(p_out / p_in - 1) = 0.00340222
    # net = 0.00340222 - 8e-4 + 4 x 6.25e-6 (le short reçoit) = 0.00262722 -> 26.2722 bps
    def test_hand_computed(self):
        inst = flat_inst(12, 6.25e-6, 0.5)
        n = inst.n
        for i in range(4 * 60 + 0, n):  # prix 99.6 à partir de 4 h
            inst.open[i] = 99.6
        t = ps.trade(inst, T0 + 30, -1, 4)
        self.assertAlmostEqual(t["ret_bps"], 26.2722066620, 6)
        self.assertEqual(t["side"], -1)
        self.assertFalse(t["liq"])

    def test_flat_price_loses_exactly_the_cost(self):
        inst = flat_inst(12, 6.25e-6, 0.5)
        for side in (+1, -1):
            t = ps.trade(inst, T0 + 30, side, 4)
            # coût 14 bps (8 frais + 2 spread + 4 slippage) ; le funding (4 x 6.25e-6 = 2.5e-5) est payé par un long
            expect = -14.0 - side * 0.25
            self.assertAlmostEqual(t["ret_bps"], expect, 2)

    def test_liquidation_distance_by_side(self):
        # long 10x, mmr 5 % : liquidation à -5.263 % ; une mèche à -6 % liquide, une mèche à -5 % non
        inst = flat_inst(12, 6.25e-6, 0.5, max_lev=10.0)
        inst.low[60] = 94.0
        t = ps.trade(inst, T0 + 30, +1, 4, leverage=10.0)
        self.assertTrue(t["liq"])
        self.assertEqual(t["margin_ret"], -1.0)
        inst2 = flat_inst(12, 6.25e-6, 0.5, max_lev=10.0)
        inst2.low[60] = 95.0
        self.assertFalse(ps.trade(inst2, T0 + 30, +1, 4, leverage=10.0)["liq"])
        # short : la mèche haute compte (liquidation à +4.76 %)
        inst3 = flat_inst(12, 6.25e-6, 0.5, max_lev=10.0)
        inst3.high[60] = 105.0
        self.assertTrue(ps.trade(inst3, T0 + 30, -1, 4, leverage=10.0)["liq"])


def injected(convergence_bps, n_hours=60, seed_premiums=((10, +30.0), (30, -30.0), (45, +30.0))):
    """Instrument à prime injectée : aux heures données, le funding révèle une prime (bps) ; le prix converge ensuite
    de convergence_bps vers l'index sur 4 h (perp cher : il baisse ; perp bon marché : il monte)."""
    inst = flat_inst(n_hours, 6.25e-6, 0.5)
    for hour, prem in seed_premiums:
        p = prem / 1e4
        u = p + max(-0.0005, min(0.0005, 0.0001 - p))
        set_funding(inst, hour, u * 0.5 / 8)
        i0 = hour * 60
        for k in range(0, 5 * 60):
            frac = min(1.0, k / 240.0)
            drift = -(1 if prem > 0 else -1) * convergence_bps / 1e4 * frac
            for j in range(i0 + k, min(inst.n, i0 + k + 1)):
                inst.open[j] = 100.0 * (1 + drift)
        for j in range(i0 + 5 * 60, inst.n):  # le prix reste convergé après (le décalage ne s'inverse pas)
            inst.open[j] = 100.0 * (1 - (1 if prem > 0 else -1) * convergence_bps / 1e4)
        # remise au niveau initial avant le prochain événement
        nxt = [h for h, _ in seed_premiums if h > hour]
        if nxt:
            for j in range(nxt[0] * 60 - 60, nxt[0] * 60):
                inst.open[j] = 100.0
    return inst


class Plumbing(unittest.TestCase):
    def test_captures_the_injected_premium_on_the_right_side(self):
        inst = injected(convergence_bps=60.0)
        w0, w1 = T0, T0 + 10 ** 12 // 1000 * 1000
        trades = ps.run_strategy([inst], 20, 4, 0, 10 ** 15)
        self.assertEqual(len(trades), 3)
        # sens : perp cher (+30 bps) -> on VEND ; perp bon marché (-30 bps) -> on ACHÈTE
        self.assertEqual([t["side"] for t in trades], [-1, +1, -1])
        for t in trades:
            self.assertGreater(t["ret_bps"], 60.0 - 14.0 - 15.0)  # la convergence de 60 bps moins le coût de 14 bps (marge pour la rampe)
            self.assertAlmostEqual(t["premium_bps"], 30.0 if t["side"] < 0 else -30.0, 6)
        s = ps.stats(trades)
        self.assertGreater(s["mean"], 25.0)
        self.assertEqual(s["win"], 1.0)

    def test_without_convergence_it_just_pays_costs(self):
        inst = injected(convergence_bps=0.0)
        trades = ps.run_strategy([inst], 20, 4, 0, 10 ** 15)
        self.assertEqual(len(trades), 3)
        self.assertLess(ps.stats(trades)["mean"], -13.0)  # coût de 14 bps, funding d'un côté ou de l'autre

    def test_threshold_filters_events(self):
        inst = injected(convergence_bps=60.0)
        self.assertEqual(len(ps.run_strategy([inst], 40, 4, 0, 10 ** 15)), 0)   # |P| = 30 < 40
        self.assertEqual(len(ps.run_strategy([inst], 10, 4, 0, 10 ** 15)), 3)

    def test_sign_is_never_flipped(self):
        # un perp bon marché qui continue de baisser fait perdre : on n'inverse pas le signal pour « corriger »
        inst = injected(convergence_bps=-60.0)  # le prix s'éloigne de l'index au lieu de converger
        trades = ps.run_strategy([inst], 20, 4, 0, 10 ** 15)
        self.assertEqual([t["side"] for t in trades], [-1, +1, -1])
        self.assertLess(ps.stats(trades)["mean"], -50.0)

    def test_one_position_at_a_time(self):
        inst = injected(convergence_bps=60.0, seed_premiums=((10, 30.0), (11, 30.0), (30, -30.0)))
        trades = ps.run_strategy([inst], 20, 4, 0, 10 ** 15)
        self.assertEqual(len(trades), 2)  # l'événement de l'heure 11 tombe pendant la position ouverte à l'heure 10

    def test_random_baseline_on_flat_prices_costs_the_spread_and_fees(self):
        inst = flat_inst(100, 6.25e-6, 0.5)
        draws = ps.random_baseline([inst], {"X": 6}, 4, T0, T0 + 99 * HOUR, draws=20, seed=3)
        self.assertEqual(len(draws), 20)
        for d in draws:
            self.assertLess(abs(d - (-14.0)), 0.5)  # coût de 14 bps, funding de signe aléatoire (|.| < 0.25 bps)


if __name__ == "__main__":
    unittest.main(verbosity=1)
