"""Tests de tools/carry_study.py : funding et P&L du carry calculés à la main, signe (le short reçoit le funding positif), identité comptable,
coûts et coût d'opportunité, distance de liquidation, absence d'anticipation, bootstrap déterministe, contrôle positif et nul.
stdlib uniquement, aucun réseau. Lancé par ctest.
"""
import datetime as dt
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import carry_study as cs  # noqa: E402
import grid_stage1 as gs  # noqa: E402

NAN = float("nan")
RF = ([dt.date(2026, 1, 1)], [0.04])


def perp_with(closes, highs=None, n_days=40):
    """Perp synthétique : barre de clôture (19:59 UTC en heure d'été) de chaque date donnée = prix ; plus haut du jour = highs."""
    gs.G = n_days * 1440
    p = gs.Inst("X")
    p.C, p.H, p.L = gs.narr(100.0), gs.narr(100.0), gs.narr(100.0)
    p.start = 0
    for d, c in closes.items():
        i = (gs.calendar.timegm(d.timetuple()) * 1000 - gs.T0_MS) // 60000 + 1199
        p.C[i] = p.H[i] = p.L[i] = c
        if highs and d in highs:
            p.H[i - 5] = highs[d]
    return p


def tiingo_with(dates, adj, raw=None, div=None):
    return {"date": dates, "adj": adj, "raw": raw or adj, "div": div or [0.0] * len(dates)}


D = [dt.date(2026, 6, 2) + dt.timedelta(i) for i in range(5)]      # mardi 2 juin au samedi 6 juin ; on n'utilise que des jours de semaine ci-dessous
WK = [dt.date(2026, 6, 2), dt.date(2026, 6, 3), dt.date(2026, 6, 4), dt.date(2026, 6, 5), dt.date(2026, 6, 8)]


class Accounting(unittest.TestCase):
    def test_funding_between_by_hand(self):
        f = ([1000, 2000, 3000], [1e-5, 2e-5, -1e-5])
        self.assertAlmostEqual(cs.funding_between(f, 1000, 3000), 2e-5 - 1e-5, places=15)    # (1000, 3000] : 2000 et 3000
        self.assertAlmostEqual(cs.funding_between(f, 0, 1000), 1e-5, places=15)

    def test_pair_pnl_sign_and_components(self):
        # perp 100 -> 101 (+1 %), sous-jacent total return +1.5 % : base = +0.5 % ; funding reçu par le short 3e-5 + 3e-5
        perp = perp_with({WK[0]: 100.0, WK[1]: 101.0}, highs={WK[1]: 101.5})
        t0 = gs.T0_MS + ((gs.calendar.timegm(WK[0].timetuple()) * 1000 - gs.T0_MS) // 60000 + 1200) * 60000
        fund = ([t0 + 3600_000, t0 + 7200_000, t0 + 90_000_000], [3e-5, 3e-5, 9e-5])         # les deux premiers dans (clôture 1, clôture 2], le troisième après
        rows = cs.build_rows("X", "X", perp, tiingo_with([WK[0], WK[1]], [200.0, 203.0]), fund, RF)
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertAlmostEqual(r["under_ret"], 0.015, places=12)
        self.assertAlmostEqual(r["perp_ret"], 0.01, places=12)
        self.assertAlmostEqual(r["basis"], 0.005, places=12)
        self.assertAlmostEqual(r["fund"], 6e-5, places=15)           # positif : reçu par le short
        self.assertEqual(r["cal"], 1)
        self.assertAlmostEqual(r["hi"], 101.5, places=9)
        self.assertEqual(r["rf"], 0.04)

    def test_accounting_identity_and_deducts(self):
        rows = [{"basis": 0.001, "fund": 6.25e-6 * 24, "cal": 1, "rf": 0.04} for _ in range(10)]
        # carry brut annualisé = 365 x (0.001 + 1.5e-4) ; coûts : (15.5 + 2 x 3) bps = 21.5 bps, amortis sur 30 jours ; coût du capital : rf x (1 + 1/L)
        g = cs.gross_ann(rows)
        self.assertAlmostEqual(g, 365 * (0.001 + 6.25e-6 * 24), places=12)
        cost, cap, rf = cs.deducts(rows, 15.5, 30, 2, 3.0, "i")
        self.assertAlmostEqual(cost, 21.5e-4 * 365 / 30, places=12)
        self.assertAlmostEqual(cap, 0.04 * 1.5, places=12)
        self.assertEqual(rf, 0.04)
        self.assertAlmostEqual(cs.deducts(rows, 15.5, 30, 2, 3.0, "ii")[1], 0.04, places=12)       # marge rémunérée : on ne perd que rf sur N
        self.assertAlmostEqual(cs.excess_ann(rows, 15.5, 30, 2, 3.0, "i"), g - cost - cap, places=12)

    def test_pure_interest_carry_does_not_beat_cash_at_low_leverage(self):
        # funding d'intérêt pur 5.475 % par an, base nulle, rf = 4 % : à L = 1 le capital double (2N) : 5.475 - 8 - coûts < 0
        rows = [{"basis": 0.0, "fund": 6.25e-6 * 24, "cal": 1, "rf": 0.04} for _ in range(10)]
        self.assertAlmostEqual(cs.gross_ann(rows), 0.05475, places=9)
        self.assertLess(cs.excess_ann(rows, 15.5, 90, 1, 0.0, "i"), 0)
        self.assertGreater(cs.excess_ann(rows, 15.5, 90, 10, 0.0, "ii"), 0)                       # marge rémunérée et peu de coûts : 5.475 - 4 - 0.27 > 0

    def test_liquidation_distance_by_hand(self):
        rows = [{"date": dt.date(2026, 6, 3), "cal": 1, "p_prev": 100.0, "hi": 106.0}, {"date": dt.date(2026, 6, 4), "cal": 1, "p_prev": 100.0, "hi": 100.0}]
        # levier max 10 : mmr = 5 %. L = 2 : distance 45 % (pas de liquidation à +6 %) ; L = 10 : distance 5 % (liquidé à +6 %)
        self.assertEqual(cs.liquidation_share(rows, 1, 2, 10.0)[0], 0.0)
        self.assertEqual(cs.liquidation_share(rows, 1, 10, 10.0)[0], 0.5)

    def test_worst_window_basis_by_hand(self):
        s = [(dt.date(2026, 6, 1) + dt.timedelta(i), v) for i, v in enumerate([0.01, -0.02, -0.03, 0.04, 0.0])]
        # fenêtre de 2 jours calendaires : sommes (-0.02 - 0.03) = -0.05 est la pire
        self.assertAlmostEqual(cs.worst_window_basis(s, 1), -0.03, places=12)
        self.assertAlmostEqual(cs.worst_window_basis(s, 2), -0.05, places=12)


class Statistics(unittest.TestCase):
    def pooled(self, fund_h, basis_sd, seed):
        rng = random.Random(seed)
        out = {}
        for k in range(8):
            rows, d = [], dt.date(2026, 6, 1)
            for _ in range(120):
                d += dt.timedelta(1)
                rows.append({"date": d, "cal": 1, "basis": rng.gauss(0, basis_sd), "fund": fund_h * 24, "rf": 0.04})
            out["I%d" % k] = rows
        return out

    def test_bootstrap_is_deterministic_and_ci_contains_truth(self):
        rows_by = self.pooled(6.25e-6, 0.002, 1)
        tab, weeks = cs.prepare_weeks(rows_by)
        a = cs.bootstrap_gross(tab, weeks, draws=400)
        b = cs.bootstrap_gross(tab, weeks, draws=400)
        self.assertEqual(a, b)
        lo, hi = a[int(0.025 * len(a))], a[int(0.975 * len(a))]
        self.assertLess(lo, 0.05475 + 0.0)           # le carry d'intérêt injecté (5.475 %) est dans l'intervalle (base de moyenne nulle)
        self.assertGreater(hi, 0.05475 - 0.05)
        self.assertGreater(hi - lo, 0.0)

    def test_injected_carry_found_and_null_not(self):
        rows_by = self.pooled(6.25e-6, 0.0005, 2)             # base peu bruitée : le carry est précis
        tab, weeks = cs.prepare_weeks(rows_by)
        boot = cs.bootstrap_gross(tab, weeks, draws=400)
        self.assertGreater(boot[int(0.025 * len(boot))], 0.03)                                  # borne basse >> 0
        rows_by = self.pooled(0.0, 0.002, 3)
        tab, weeks = cs.prepare_weeks(rows_by)
        boot = cs.bootstrap_gross(tab, weeks, draws=400)
        self.assertLess(boot[int(0.025 * len(boot))], 0.0)                                      # sans funding, l'intervalle contient 0
        self.assertGreater(boot[int(0.975 * len(boot))], 0.0)

    def test_no_lookahead_in_rows(self):
        closes = {WK[i]: 100.0 + i for i in range(5)}
        perp = perp_with(closes)
        tg = tiingo_with(WK, [200.0, 202.0, 204.0, 203.0, 210.0])
        fund = ([gs.T0_MS + 10 ** 9], [1e-5])
        full = cs.build_rows("X", "X", perp, tg, fund, RF)
        cut = cs.build_rows("X", "X", perp, tiingo_with(WK[:3], [200.0, 202.0, 204.0]), fund, RF)
        for a, b in zip(cut, full):
            for k in ("basis", "fund", "perp_ret", "under_ret", "hi", "lo", "rf"):
                self.assertEqual(a[k], b[k])


if __name__ == "__main__":
    unittest.main()
