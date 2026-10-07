"""Tests de tools/leadlag_study.py : exécution calculée à la main, plomberie à décalage injecté, sens du signal.

Plomberie : le perp est Binance retardé de 20 s (marche aléatoire de 3 bps par seconde) ; la corrélation croisée
doit culminer à L = 20 s et la stratégie doit capturer le décalage, du bon côté. Contrôle : sans décalage elle ne
gagne pas. Le sens n'est jamais retourné. stdlib uniquement, aucun réseau. Lancé par ctest.
"""
import math
import os
import sys
import unittest
from array import array

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import leadlag_study as ll  # noqa: E402


def hand_series(jump_bps):
    """t0 = 0, 300 secondes. Binance : 100 jusqu'à la seconde 99, puis 100 x (1 + jump) à partir de 100.
    Prints du perp : (90.5, 100.00, achat), (96.5, 99.99, vente), (110.5, 100.19, achat), (131.2, 100.17, vente),
    (200.5, 100.10, achat), (250.5, 100.00, vente)."""
    B = array("d", [100.0]) * 300
    for i in range(100, 300):
        B[i] = 100.0 * (1 + jump_bps / 1e4)
    prints = [(90.5, 100.00, 1), (96.5, 99.99, -1), (110.5, 100.19, 1), (131.2, 100.17, -1), (200.5, 100.10, 1), (250.5, 100.00, -1)]
    return ll.Series("H", 0, 300, B, prints)


class Execution(unittest.TestCase):
    # Hausse de Binance de 20 bps à la seconde 100 ; le perp n'a pas bougé : P[100] = 99.99, P[95] = 100.00.
    # g[100] = 1e4 ln(100.2/100) - 1e4 ln(99.99/100) = 19.98 + 1.00 = 20.98 bps > 10 : signal d'ACHAT, t_sig = 101 s.
    # entrée : premier print acheteur >= 102 s : 110.5 s à 100.19 ; sortie : premier print vendeur >= 110.5 + 20 = 130.5 s :
    # 131.2 s à 100.17 ; ret = (100.17 / 100.19 - 1) x 1e4 = -1.99621 bps (coût 0).
    def test_buy_hand_computed(self):
        S = hand_series(+20.0)
        g = S.gap(5)
        self.assertAlmostEqual(g[100], 1e4 * math.log(100.2 / 100.0) - 1e4 * math.log(99.99 / 100.0), 9)
        trades, nofill = ll.run_strategy(S, 5, 10, 20, 0, 300, cost_bps=0.0)
        self.assertEqual(len(trades), 1)
        t = trades[0]
        self.assertEqual(t["side"], +1)
        self.assertAlmostEqual(t["te"], 110.5, 9)
        self.assertAlmostEqual(t["tx"], 131.2, 9)
        self.assertAlmostEqual(t["ret_bps"], (100.17 / 100.19 - 1) * 1e4, 9)
        self.assertAlmostEqual(t["ret_bps"], -1.99621, 4)

    def test_cost_is_subtracted(self):
        S = hand_series(+20.0)
        t = ll.run_strategy(S, 5, 10, 20, 0, 300)[0][0]  # coût par défaut 12 bps
        self.assertAlmostEqual(t["ret_bps"], -1.99621 - 12.0, 4)

    # Baisse de 20 bps : g[100] = 1e4 ln(99.8/100) + 1.0 = -19.98 + 1.00 = -18.98 : VENTE ; entrée au premier print vendeur
    # >= 102 s : 131.2 s à 100.17 ; sortie au premier print acheteur >= 151.2 s : 200.5 s à 100.10 ; ret = -(100.10/100.17 - 1) x 1e4.
    def test_sell_uses_the_opposite_aggressor_prints(self):
        S = hand_series(-20.0)
        trades, _ = ll.run_strategy(S, 5, 10, 20, 0, 300, cost_bps=0.0)
        t = trades[0]
        self.assertEqual(t["side"], -1)
        self.assertAlmostEqual(t["te"], 131.2, 9)
        self.assertAlmostEqual(t["tx"], 200.5, 9)
        self.assertAlmostEqual(t["ret_bps"], -(100.10 / 100.17 - 1) * 1e4, 9)

    def test_no_fill_when_no_print_within_maxwait(self):
        S = hand_series(+20.0)
        self.assertIsNone(ll.fill(S, 100, +1, 20, delay=1.0, maxwait=5.0))   # le premier print acheteur est 8.5 s plus tard
        self.assertIsNotNone(ll.fill(S, 100, +1, 20, delay=1.0, maxwait=60.0))

    def test_one_position_at_a_time(self):
        S = hand_series(+20.0)
        trades, _ = ll.run_strategy(S, 5, 10, 20, 0, 300, cost_bps=0.0)
        self.assertEqual(len(trades), 1)  # les secondes 101 à 104 déclenchent aussi, mais la position est ouverte

    def test_sign_follows_gap_never_flipped(self):
        for jump in (+20.0, -20.0):
            S = hand_series(jump)
            trades, _ = ll.run_strategy(S, 5, 10, 20, 0, 300)
            for t in trades:
                self.assertEqual(t["side"], 1 if t["g"] > 0 else -1)


class Plumbing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lag20 = ll.synthetic_series(20)
        cls.lag0 = ll.synthetic_series(0)

    def test_cross_correlation_peaks_at_the_injected_lag(self):
        S = self.lag20
        tab = ll.xcorr_table(S, S.start_index(), S.n, 1, [-20, -10, 0, 10, 20, 30])
        by = {L: c for L, c, sl, t, n in tab}
        self.assertGreater(by[20], 0.35)  # prints toutes les 2 s alternant bid et ask : bruit de rebond de +-0.5 bp
        for L in (-20, -10, 0, 10, 30):
            self.assertGreater(by[20], by[L] + 0.2)  # le pic est à 20 s, Binance mène
        # pente : le perp reproduit le mouvement Binance retardé : ~1 bps par bps
        self.assertGreater(ll.xcorr_table(S, S.start_index(), S.n, 1, [20])[0][2], 0.3)

    def test_no_lag_no_peak_away_from_zero(self):
        S = self.lag0
        tab = ll.xcorr_table(S, S.start_index(), S.n, 1, [-20, 0, 20])
        by = {L: c for L, c, sl, t, n in tab}
        self.assertGreater(by[0], 0.3)
        self.assertLess(abs(by[20]), 0.1)
        self.assertLess(abs(by[-20]), 0.1)

    def test_strategy_captures_the_lag_on_the_right_side(self):
        trades, _ = ll.run_strategy(self.lag20, 15, 15, 20, 0, self.lag20.n, cost_bps=0.0)
        s = ll.stats(trades)
        self.assertGreater(s["n"], 30)
        self.assertGreater(s["mean"], 3.0)        # capture nette de coût nul : le décalage est bien exploité
        self.assertGreater(s["win"], 0.55)
        for t in trades:
            self.assertEqual(t["side"], 1 if t["g"] > 0 else -1)

    def test_control_without_lag_does_not_win(self):
        t_lag, _ = ll.run_strategy(self.lag20, 15, 15, 20, 0, self.lag20.n, cost_bps=0.0)
        t_nolag, _ = ll.run_strategy(self.lag0, 15, 15, 20, 0, self.lag0.n, cost_bps=0.0)
        m_lag, m_no = ll.stats(t_lag)["mean"], ll.stats(t_nolag)["mean"]
        self.assertLess(m_no, 1.0)                 # sans décalage : au mieux un spread payé (~ -1 bp)
        self.assertGreater(m_lag - m_no, 3.0)

    def test_random_entries_have_no_edge(self):
        draws = ll.random_baseline(self.lag20, 40, 20, 100, self.lag20.n - 200, 20, 3)
        self.assertEqual(len(draws), 20)
        # sans edge : coût de 12 bps + spread payé (~ 1 bp) : environ -13 bps, jamais positif
        self.assertLess(abs(sum(draws) / len(draws) + 13.0), 2.0)

    def test_costs_can_erase_a_small_capture(self):
        trades, _ = ll.run_strategy(self.lag20, 15, 15, 20, 0, self.lag20.n)  # coût 12 bps
        self.assertLess(ll.stats(trades)["mean"], ll.stats(ll.run_strategy(self.lag20, 15, 15, 20, 0, self.lag20.n, cost_bps=0.0)[0])["mean"] - 11.0)


if __name__ == "__main__":
    unittest.main(verbosity=1)
