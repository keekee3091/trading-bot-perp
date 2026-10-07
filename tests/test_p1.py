"""Tests de tools/passive_fills.py et tools/p1_study.py : fills passifs calculés à la main, absence d'anticipation, horaires avec DST,
contrôle positif de l'effet EXÉCUTABLE (une inversion intrajournalière injectée est exécutable, une inversion de nuit ne l'est pas).
stdlib uniquement, aucun réseau. Lancé par ctest.
"""
import calendar
import datetime as dt
import math
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import grid_stage1 as gs  # noqa: E402
import p1_study as p1  # noqa: E402
import passive_fills as pf  # noqa: E402
import stocks_study as ss  # noqa: E402

# (ts, side, notionnel, prix, quantité) ; side +1 = agresseur acheteur, -1 = agresseur vendeur
ROWS = [(1000, -1, 100.0, 100.0, 1), (1500, 1, 300.0, 100.2, 1), (3000, -1, 500.0, 100.0, 5), (4000, -1, 600.0, 99.9, 6),
        (5000, -1, 900.0, 99.9, 9), (6000, 1, 400.0, 100.5, 4), (9000, 1, 700.0, 101.0, 7), (9500, 1, 100.0, 101.1, 1),
        (10000, -1, 200.0, 100.8, 2)]


class Fills(unittest.TestCase):
    def setUp(self):
        self.b = pf.Book(ROWS)

    def test_reference_price_is_last_opposite_print(self):
        self.assertEqual(pf.ref_price(self.b, 1, 2000), 100.0)      # achat : dernier trade d'un vendeur <= 2000
        self.assertEqual(pf.ref_price(self.b, -1, 2000), 100.2)     # vente : dernier trade d'un acheteur
        self.assertIsNone(pf.ref_price(self.b, 1, 500))             # aucun trade avant 500
        self.assertIsNone(pf.ref_price(self.b, 1, 1000 + 400_000))  # plus vieux que 5 minutes

    def test_buy_limit_bounds_by_hand(self):
        # ordre d'achat à 100.0 posté à 2000, valable jusqu'à 8000
        self.assertEqual(pf.passive_fill(self.b, 1, 100.0, 2000, 8000, "opt"), 3000)                  # imprime à 100.0 : servi
        self.assertEqual(pf.passive_fill(self.b, 1, 100.0, 2000, 8000, "cons", 0), 4000)              # strictement sous 100.0
        self.assertEqual(pf.passive_fill(self.b, 1, 100.0, 2000, 8000, "cons", 1000), 5000)           # 600 puis 1500 >= 1000
        self.assertIsNone(pf.passive_fill(self.b, 1, 100.0, 2000, 8000, "cons", 5000))                # file de 5000 jamais consommée
        self.assertIsNone(pf.passive_fill(self.b, 1, 100.0, 2000, 3500, "cons", 0))                   # échéance avant le premier trade strict

    def test_sell_limit_is_symmetric(self):
        # vente à 100.5 postée à 8500 : un acheteur imprimant à 101.0 > 100.5 la sert (9000) ; strictement : idem car 101.0 > 100.5
        self.assertEqual(pf.passive_fill(self.b, -1, 100.5, 8500, 9200, "opt"), 9000)
        self.assertEqual(pf.passive_fill(self.b, -1, 100.5, 8500, 9200, "cons", 0), 9000)
        self.assertIsNone(pf.passive_fill(self.b, -1, 101.0, 8500, 9200, "cons", 0))     # 101.0 n'est pas strictement au-delà
        self.assertEqual(pf.passive_fill(self.b, -1, 101.0, 8500, 9200, "opt"), 9000)

    def test_no_lookahead_in_reference_and_fill_window(self):
        before = pf.ref_price(self.b, 1, 2000)
        b2 = pf.Book(ROWS + [(2500, -1, 50.0, 90.0, 1)])        # un trade FUTUR (après 2000) ne change pas la référence à 2000
        self.assertEqual(pf.ref_price(b2, 1, 2000), before)
        self.assertEqual(pf.passive_fill(self.b, 1, 100.0, 4000, 8000, "opt"), 4000 + 1000)  # seuls les trades > t0 comptent (5000 est le suivant)

    def test_trade_pnl_by_hand(self):
        entry, exit_ = (2000, 8000), (8500, 9200)
        r = pf.run_trade(self.b, None, 1, entry, exit_, "post", "opt", 0)
        # entrée limite 100.0 (fill 3000), sortie limite vendeuse à 100.5 (fill 9000) : brut 50 bps, 2 x 1.25 de frais maker
        self.assertAlmostEqual(r["gross"], 50.0, places=9)
        self.assertAlmostEqual(r["net"], 47.5, places=9)
        self.assertEqual(r["delay"], 1000)
        # funding : taux de 2 bps à 3500 dans l'intervalle (3000, 9000] payé par le long ; 3 bps à 9500 hors intervalle
        r = pf.run_trade(self.b, ([3500, 9500], [2.0, 3.0]), 1, entry, exit_, "post", "opt", 0)
        self.assertAlmostEqual(r["net"], 45.5, places=9)
        # taker : entrée au premier achat >= 3000 (6000 @ 100.5), sortie au premier vente >= 9500 (10000 @ 100.8)
        r = pf.run_trade(self.b, None, 1, (2000, 2000), (8500, 8500), "taker", "opt", 0)
        self.assertAlmostEqual(r["gross"], 1e4 * (100.8 - 100.5) / 100.5, places=9)
        self.assertAlmostEqual(r["net"], 1e4 * (100.8 - 100.5) / 100.5 - 12.0, places=9)
        self.assertFalse(r["maker_entry"])

    def test_unfilled_counts_as_zero_and_fallback_is_taker(self):
        r = pf.run_trade(self.b, None, 1, (2000, 8000), (8500, 9200), "post", "cons", 5000)
        self.assertFalse(r["filled"])
        self.assertEqual(r["net"], 0.0)
        leg = pf.execute_leg(self.b, 1, 2000, 8000, "post_fb", "cons", 5000)      # file de 5000 : pas de fill, repli taker à 8000
        self.assertEqual((leg["status"], leg["maker"], leg["px"]), ("fallback", False, 101.0))

    def test_taker_falls_back_to_last_print_when_no_print_follows(self):
        # no buy aggressor print after 20000: fall back to the last buy print within the previous 5 minutes (9500 at 101.1), executed at t + 1 s
        self.assertEqual(pf.taker_fill(self.b, 1, 20000), (21000, 101.1))
        self.assertIsNone(pf.taker_fill(self.b, 1, 20000 + 400_000))       # no recent print: no execution

    def test_markout_by_hand(self):
        self.assertAlmostEqual(pf.mid_proxy(self.b, 9600), (101.1 + 99.9) / 2, places=12)
        self.assertAlmostEqual(pf.markout(self.b, 1, 3000, 100.0, 6600), 1e4 * (100.5 - 100.0) / 100.0, places=9)
        self.assertAlmostEqual(pf.markout(self.b, -1, 3000, 100.0, 6600), -50.0, places=9)


class Calendar(unittest.TestCase):
    def test_execution_window_with_dst(self):
        # 9h35 et 15h55 heure de l'Est : 13:35 et 19:55 UTC en heure d'été, 14:35 et 20:55 UTC en hiver
        s, w = dt.date(2026, 7, 1), dt.date(2026, 12, 1)
        t = lambda d, h, m: calendar.timegm((d.year, d.month, d.day, h, m, 0)) * 1000
        self.assertEqual(p1.utc_ms(s, 9, 35), t(s, 13, 35))
        self.assertEqual(p1.utc_ms(s, 15, 55), t(s, 19, 55))
        self.assertEqual(p1.utc_ms(w, 9, 35), t(w, 14, 35))
        self.assertEqual(p1.utc_ms(w, 15, 55), t(w, 20, 55))

    def test_entry_is_after_the_signal_close_and_inside_the_session(self):
        d_in, d_out = dt.date(2026, 7, 1), dt.date(2026, 7, 1)
        sig = {"kind": "S1", "d_in": d_in, "d_out": d_out}
        for pol, T in (("taker", None), ("post", "30m"), ("post_fb", "2h"), ("post", "eos")):
            (t0, exp), (x0, x1) = p1.entry_times(sig, pol, T, d_in)
            close_prev = p1.utc_ms(dt.date(2026, 6, 30), 16, 0)
            self.assertGreater(t0, close_prev)                                  # signal à la clôture de J-1, entrée après
            self.assertEqual(t0, p1.utc_ms(d_in, 9, 35))
            self.assertLessEqual(exp, p1.utc_ms(d_in, 15, 55))                  # jamais hors séance
            self.assertLessEqual(x1, p1.utc_ms(d_out, 15, 55))
        s2 = {"kind": "S2", "d_in": dt.date(2026, 7, 1), "d_out": dt.date(2026, 7, 2)}
        (t0, exp), (x0, x1) = p1.entry_times(s2, "post", "2h", None)
        self.assertEqual(exp, p1.utc_ms(s2["d_in"], 15, 55))
        self.assertEqual(x0, p1.utc_ms(s2["d_out"], 9, 35))                     # sortie au premier prix de séance après 9h35


def synth_exec_panel(rng, n, k, b_gap, b_intra, sd=0.01):
    """Chaque jour : écart de nuit et mouvement de séance = -b x (rendement clôture-clôture de la veille) + bruit."""
    P = p1.ExecPanel.__new__(p1.ExecPanel)
    P.tickers = ["S%d" % i for i in range(k)]
    P.n = n
    P.dates = [dt.date(2000, 1, 1) + dt.timedelta(i) for i in range(n)]
    P.lr, P.lro, P.sig = {}, {}, {}
    for t in P.tickers:
        lc, lo, c, prev = [0.0], [0.0], 0.0, 0.0
        for _ in range(n - 1):
            gap = -b_gap * prev + rng.gauss(0, sd)
            intra = -b_intra * prev + rng.gauss(0, sd)
            o = c + gap
            nc = o + intra
            lo.append(o)
            lc.append(nc)
            prev, c = nc - lc[-2], nc
        P.lr[t], P.lro[t] = lc, lo
        P.sig[t] = ss.Panel._vol(lc)
    return P


def base_panel(E):
    P = ss.Panel.__new__(ss.Panel)
    P.__dict__.update({k: v for k, v in E.__dict__.items() if k != "lro"})
    return P


class Executable(unittest.TestCase):
    def test_intraday_reversal_is_executable_overnight_reversal_is_not(self):
        E = synth_exec_panel(random.Random(1), 3000, 20, b_gap=0.0, b_intra=0.2)
        cc, _ = p1.s1_series(base_panel(E), "mom_1", 1)
        ex, _ = p1.s1_series(E, "mom_1", 1)
        s_cc, s_ex = p1.cell_stats(cc, [0.0] * len(cc), 21), p1.cell_stats(ex, [0.0] * len(ex), 21)
        self.assertGreater(s_ex["gross_z"], 4.0)                          # l'inversion de séance est exécutable
        self.assertGreater(s_cc["gross_z"], 4.0)
        E = synth_exec_panel(random.Random(2), 3000, 20, b_gap=0.2, b_intra=0.0)
        cc, _ = p1.s1_series(base_panel(E), "mom_1", 1)
        ex, _ = p1.s1_series(E, "mom_1", 1)
        s_cc, s_ex = p1.cell_stats(cc, [0.0] * len(cc), 21), p1.cell_stats(ex, [0.0] * len(ex), 21)
        self.assertGreater(s_cc["gross_z"], 4.0)                          # l'écart de nuit fait apparaître l'effet clôture-clôture...
        self.assertLess(abs(s_ex["gross_z"]), 3.5)                        # ...mais il n'est PAS exécutable (entrée à l'ouverture)

    def test_net_of_maker_cost_and_null(self):
        E = synth_exec_panel(random.Random(3), 3000, 20, b_gap=0.0, b_intra=0.0)
        ex, _ = p1.s1_series(E, "mom_1", 1)
        st = p1.cell_stats(ex, [5.0] * len(ex), 21)
        self.assertLess(st["z"], 0.0)                                      # sans effet, le net est négatif (le coût)
        self.assertAlmostEqual(st["net"], st["gross"] - 5.0, places=9)


if __name__ == "__main__":
    unittest.main()
