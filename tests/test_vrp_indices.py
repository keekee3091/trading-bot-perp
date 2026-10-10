"""Tests de tools/vrp_indices.py et vrp_monitor.py : valeurs calculées à la main (rendements, MCO, Newey-West, bootstrap, BH, seuils, drawdown),
absence d'anticipation, alignement des mois, contrôle synthétique positif et nul, suivi prospectif sur données tronquées. stdlib, sans réseau."""
import datetime as dt
import math
import os
import random
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import vrp_indices as vi  # noqa: E402
import vrp_monitor as vm  # noqa: E402

D = dt.date


class Returns(unittest.TestCase):
    def test_month_returns_by_hand(self):
        # 100 -> 110 -> 99 : +10 %, puis 99 / 110 - 1 = -10 %
        r = vi.monthly_returns({D(2020, 1, 31): 100.0, D(2020, 2, 28): 110.0, D(2020, 3, 31): 99.0})
        self.assertAlmostEqual(r[202002], 0.10)
        self.assertAlmostEqual(r[202003], -0.10)

    def test_gap_month_dropped(self):
        # dernier point de février le 15 : à plus de 7 jours de la fin du mois, février et mars sont sans rendement
        r = vi.monthly_returns({D(2020, 1, 31): 100.0, D(2020, 2, 15): 110.0, D(2020, 3, 31): 99.0})
        self.assertEqual(r, {})

    def test_no_lookahead(self):
        s = {D(2020, m, 28 if m == 2 else 30 if m in (4, 6) else 31): 100.0 + m * m for m in range(1, 7)}
        full = vi.monthly_returns(s)
        cut = vi.monthly_returns({d: v for d, v in s.items() if d <= D(2020, 4, 30)})
        for ym, v in cut.items():
            self.assertAlmostEqual(full[ym], v)

    def test_alignment_with_french(self):
        ff = {202002: {"mkt": 0.01, "smb": 0.0, "hml": 0.0, "rf": 0.001, "mom": 0.0}}
        rows = vi.build_rows({202002: 0.10, 202003: 0.0}, ff)
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0]["y"], 0.099)


class Stats(unittest.TestCase):
    X, Y = [1.0, 2, 3, 4, 5], [2.0, 4, 5, 4, 5]

    def test_ols_by_hand(self):
        # pente Sxy / Sxx = 6 / 10 = 0,6 ; constante 4 - 0,6 x 3 = 2,2 ; résidus -0,8 ; 0,6 ; 1 ; -0,6 ; -0,2 (somme des carrés 2,4)
        f = vi.fit(self.Y, [self.X])
        self.assertAlmostEqual(f["beta"][0], 2.2)
        self.assertAlmostEqual(f["beta"][1], 0.6)
        self.assertAlmostEqual(f["sd"], math.sqrt(2.4 / 3))
        self.assertAlmostEqual(f["se_iid"], math.sqrt(2.4 / 3) * math.sqrt(1 / 5 + 9 / 10))

    def test_newey_west_by_hand(self):
        # constante seule, y = 1 2 3 4 10, moyenne 4, résidus -3 -2 -1 0 6 ; S = 50 + 2 x 0,5 x 8 = 58 (un retard, poids de Bartlett 1/2) ; var = 58 / 25
        beta, res, inv, X = vi.ols([1.0, 2, 3, 4, 10], [])
        self.assertAlmostEqual(vi.nw_se(res, inv, X, lags=1)[0], math.sqrt(58 / 25))

    def test_bootstrap_indices(self):
        class R:
            seq = [4, 1]

            def randrange(self, n):
                return self.seq.pop(0)
        # n = 5, blocs de 3 à partir de 4 puis 1 : 4 0 1 | 1 2 3 -> tronqué à 5 : 4 0 1 1 2
        self.assertEqual(vi.mbb_indices(5, 3, R()), [4, 0, 1, 1, 2])

    def test_bh(self):
        # m = 4 : 0,001 <= 0,05 x 1 / 4 oui ; 0,03 > 0,025 ; 0,04 > 0,0375 : un seul rejet
        self.assertEqual(vi.bh([0.001, 0.04, 0.03, 0.5]), [True, False, False, False])

    def test_drawdown(self):
        # chemin 1 ; 1,1 ; 0,88 ; 0,924 : creux 0,88 sous 1,1 = 20 % ; deux mois sous le sommet
        dd, ln = vi.dd_stats([0.1, -0.2, 0.05])
        self.assertAlmostEqual(dd, 0.2)
        self.assertEqual(ln, 2)

    def test_thresholds(self):
        # marché -20 % puis +10 % : pire mois -0,2 -> 0,75 x = -0,15 (plus strict que -0,20) ; drawdown 20 % -> 15 %
        t = vi.thresholds([{"mkt": -0.2, "rf": 0.0}, {"mkt": 0.1, "rf": 0.0}])
        self.assertAlmostEqual(t["worst_min"], -0.15)
        self.assertAlmostEqual(t["dd_max"], 0.15)
        # pire mois -40 % : 0,75 x = -0,30, la valeur absolue -0,20 est plus stricte
        self.assertAlmostEqual(vi.thresholds([{"mkt": -0.4, "rf": 0.0}])["worst_min"], -0.20)


def synth(alpha, noise, seed, n=237):
    rng = random.Random(seed)
    x = [rng.gauss(0.006, 0.045) for _ in range(n)]
    y = [0.5 * m + alpha + rng.gauss(0, noise) for m in x]
    return x, y


class Controls(unittest.TestCase):
    def rejection(self, alpha, seeds=200):
        pos = neg = 0
        for s in range(seeds):
            x, y = synth(alpha, 0.02, s)
            lo, hi = vi.boot_alpha_ci(y, [x], 300, random.Random(1000 + s))
            pos += lo > 0
            neg += hi < 0
        return pos / seeds, neg / seeds

    def test_positive_control(self):
        # alpha injecté 0,5 % par mois, bruit 2 % (voir Ecarts : 3 % donnerait une puissance théorique de 73 %), n = 237
        pos, neg = self.rejection(0.005)
        self.assertGreaterEqual(pos, 0.80)
        self.assertEqual(neg, 0.0)

    def test_null_control(self):
        pos, neg = self.rejection(0.0)
        self.assertTrue(0.02 <= pos + neg <= 0.09, (pos, neg))


def fixture(tmp):
    os.makedirs(os.path.join(tmp, "vrp"))
    ff = ",Mkt-RF,SMB,HML,RF\n202609,   2.00,  0.1,  0.1,   0.40\n202610,  -1.00,  0.1,  0.1,   0.40\n202611,   1.00,  0.1,  0.1,   0.40\n"
    mom = ",Mom\n202609,   0.5\n202610,   0.5\n202611,   0.5\n"
    for n, t in (("ff3.zip", ff), ("mom.zip", mom)):
        with zipfile.ZipFile(os.path.join(tmp, "vrp", n), "w") as z:
            z.writestr("f.csv", t)
    for name in ("PUT", "PUTY", "WPUT", "CNDR"):
        with open(os.path.join(tmp, "vrp", name + "_History.csv"), "w") as f:
            f.write("DATE,%s\n08/31/2026,100\n09/30/2026,101\n10/30/2026,100.5\n11/30/2026,102\n" % name)


class Monitor(unittest.TestCase):
    def test_log_and_first_read_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture(tmp)
            out = os.path.join(tmp, "res")
            vm.main(["--asof", "2027-01-15", "--data", tmp, "--out", out])
            path = os.path.join(out, "vrp_prospective_log.csv")
            log = open(path).read().splitlines()
            # 4 indices x 3 mois ; septembre : 101 / 100 - 1 = 1 % moins RF 0,4 % = 0,6 %
            self.assertEqual(len(log), 1 + 12)
            self.assertIn("202609,PUT,0.006,0.02", log[1])
            self.assertFalse(os.path.exists(os.path.join(out, "vrp_prospective.lock")))
            vm.main(["--asof", "2027-01-16", "--data", tmp, "--out", out])
            self.assertEqual(len(open(path).read().splitlines()), 13)   # idempotent
            vm.main(["--asof", "2027-04-01", "--data", tmp, "--out", out])
            self.assertTrue(os.path.exists(os.path.join(out, "vrp_prospective.lock")))


if __name__ == "__main__":
    unittest.main()
