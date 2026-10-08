"""Tests de tools/long_horizon.py : grille, garde du test (date, jours de perp, lecture unique), absence d'anticipation du signal de momentum,
signe du funding, contrôle positif (tendance injectée) et nul. stdlib uniquement, aucun réseau. Lancé par ctest.
"""
import datetime as dt
import os
import random
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import long_horizon as lh  # noqa: E402
import p1_study as p1  # noqa: E402
import stocks_study as ss  # noqa: E402


def trend_panel(rng, n, k, persistence, sd=0.01, drift_sd=0.002):
    """Rendements = dérive lente (autorégressive, persistance donnée) + bruit : un momentum de séries temporelles y existe si persistence > 0."""
    P = p1.ExecPanel.__new__(p1.ExecPanel)
    P.tickers = ["T%d" % i for i in range(k)]
    P.n = n
    P.dates = [dt.date(2000, 1, 3) + dt.timedelta(i) for i in range(n)]
    P.lr, P.lro, P.sig = {}, {}, {}
    for t in P.tickers:
        lc, lo, x, drift = [0.0], [0.0], 0.0, 0.0
        for _ in range(n - 1):
            drift = persistence * drift + rng.gauss(0, drift_sd)
            lo.append(x)                                    # ouverture = clôture de la veille (pas d'écart de nuit dans cette série)
            x += drift + rng.gauss(0, sd)
            lc.append(x)
        P.lr[t], P.lro[t] = lc, lo
        P.sig[t] = ss.Panel._vol(lc)
    return P


class Grid(unittest.TestCase):
    def test_cells_count_and_funding_sign(self):
        self.assertEqual(len(lh.cells()), 12)
        self.assertEqual(lh.HORIZONS, (1, 5, 20, 60))
        # un long de 20 jours paie le funding (coût plus élevé), un short le reçoit : 0.0625 bps par heure
        self.assertAlmostEqual(lh.hold_hours(20), 20 * 33.6 - 17.5, places=9)
        long_cost = lh.RT_COST + ss.FUND_BPS_H * lh.hold_hours(20)
        short_cost = lh.RT_COST - ss.FUND_BPS_H * lh.hold_hours(20)
        self.assertGreater(long_cost, lh.RT_COST)
        self.assertLess(short_cost, lh.RT_COST)


class Guard(unittest.TestCase):
    def test_refuses_before_date_before_enough_days_and_twice(self):
        self.assertIn("2026-12-15", lh.guard(dt.date(2026, 10, 8), 100, False))              # trop tôt
        self.assertIn("40", lh.guard(dt.date(2026, 12, 20), 39, False))                      # pas assez de jours de perp
        self.assertIsNone(lh.guard(dt.date(2026, 12, 15), 40, False))                        # autorisé exactement à la date et au seuil
        self.assertIn("déjà", lh.guard(dt.date(2027, 1, 5), 90, True))                        # jamais deux lectures

    def test_test_mode_refuses_today(self):
        with self.assertRaises(SystemExit) as cm:
            lh.run_test(today=dt.date(2026, 10, 8))
        self.assertIn("REFUSÉ", str(cm.exception))


class Signals(unittest.TestCase):
    def test_tsm_uses_only_the_past_for_the_signal(self):
        P = trend_panel(random.Random(1), 400, 12, 0.9)
        g1, _ = lh.tsm_series(P, 5)
        # on réécrit tout le futur après la date t0 : le signal à t0 (donc la position) ne change pas, seul le gain change
        t0 = 200
        s_before = {tk: 1.0 if P.lr[tk][t0] > P.lr[tk][t0 - 60] else -1.0 for tk in P.tickers}
        for tk in P.tickers:
            for i in range(t0 + 1, P.n):
                P.lr[tk][i] += 0.5
                P.lro[tk][i] += 0.5
        s_after = {tk: 1.0 if P.lr[tk][t0] > P.lr[tk][t0 - 60] else -1.0 for tk in P.tickers}
        self.assertEqual(s_before, s_after)
        self.assertGreater(len(g1), 20)

    def test_positive_control_trend_found_and_null_not(self):
        P = trend_panel(random.Random(2), 3000, 15, 0.97)
        st = lh.stats("TSM", 5, P)
        self.assertGreater(st["gross"], 0)
        self.assertGreater(st["gross_z"], 3.0)                                              # la tendance injectée est retrouvée
        P0 = trend_panel(random.Random(3), 3000, 15, 0.0, drift_sd=0.0)
        st0 = lh.stats("TSM", 5, P0)
        self.assertLess(abs(st0["gross_z"]), 3.5)                                           # sans tendance, rien
        self.assertLess(st0["net"], 0)                                                       # et le net est négatif (le coût)


if __name__ == "__main__":
    unittest.main()
