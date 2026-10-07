"""Tests de tools/stocks_study.py et tools/fetch_tiingo.py : calculs à la main, contrôles positifs et nuls, absence d'anticipation.

Contrôle positif H2 : une autocorrélation injectée (momentum ou retour à la moyenne) est retrouvée avec le bon signe ; nul :
rien. H3 : une dérive nocturne injectée est retrouvée. H1 : mouvement et écart calculés à la main sur un jour synthétique.
Téléchargeur : limiteur de débit simulé, clé jamais dans l'URL. stdlib uniquement, aucun réseau. Lancé par ctest.
"""
import datetime as dt
import io
import math
import os
import random
import sys
import tempfile
import unittest
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import fetch_tiingo as ft  # noqa: E402
import grid_stage1 as gs  # noqa: E402
import stocks_study as ss  # noqa: E402

NAN = float("nan")


def synth_panel(rng, n_days, n_stocks, phi, sd=0.01):
    """Panneau synthétique : rendement du jour = phi x rendement de la veille + bruit ; indépendant entre actions."""
    P = ss.Panel.__new__(ss.Panel)
    P.tickers = ["S%d" % i for i in range(n_stocks)]
    P.n = n_days
    P.dates = [dt.date(2000, 1, 1) + dt.timedelta(i) for i in range(n_days)]
    P.lr, P.sig = {}, {}
    for t in P.tickers:
        a, r, x = [0.0], 0.0, 0.0
        for _ in range(n_days - 1):
            r = phi * r + rng.gauss(0, sd)
            x += r
            a.append(x)
        P.lr[t] = a
        P.sig[t] = ss.Panel._vol(a)
    return P


class Calendar(unittest.TestCase):
    def test_dst_and_session(self):
        # 2026 : mars commence un dimanche, le 2e dimanche est le 8 ; novembre commence un dimanche (le 1er) : fin exclue
        self.assertTrue(ss.us_dst(dt.date(2026, 3, 8)))
        self.assertFalse(ss.us_dst(dt.date(2026, 3, 7)))
        self.assertTrue(ss.us_dst(dt.date(2026, 10, 31)))
        self.assertFalse(ss.us_dst(dt.date(2026, 11, 1)))
        self.assertEqual(ss.session_minutes(dt.date(2026, 7, 1)), (810, 1200))     # 13:30 et 20:00 UTC
        self.assertEqual(ss.session_minutes(dt.date(2026, 12, 1)), (870, 1260))    # 14:30 et 21:00 UTC


class Stats(unittest.TestCase):
    def test_jackknife_mean_blen1_is_classic(self):
        v = [float(i) for i in range(1, 21)]
        m, se = ss.jk_mean(v, 1)
        # moyenne 10.5, écart-type d'échantillon racine(35), erreur-type racine(35) / racine(20)
        self.assertAlmostEqual(m, 10.5, places=12)
        self.assertAlmostEqual(se, math.sqrt(35) / math.sqrt(20), places=10)

    def test_h1_obs_by_hand(self):
        gs.G = 10 * 1440
        gs.T0_MS = gs.calendar.timegm((2026, 6, 1, 0, 0, 0)) * 1000
        perp = gs.Inst("X")
        perp.C = gs.narr(100.0)
        perp.start = 0
        d0, d1 = dt.date(2026, 6, 2), dt.date(2026, 6, 3)      # mardi, mercredi (heure d'été : 13:30 et 20:00 UTC)

        def idx(d, minute):
            return (d - dt.date(2026, 6, 1)).days * 1440 + minute
        perp.C[idx(d0, 1199)] = 100.0        # clôture veille : barre qui débute à 19:59
        perp.C[idx(d1, 809)] = 101.0         # juste avant l'ouverture : barre de 13:29
        perp.C[idx(d1, 810)] = 101.0         # P0
        perp.C[idx(d1, 840)] = 102.01        # +30 min
        perp.C[idx(d1, 930)] = 100.0         # +2 h
        perp.C[idx(d1, 1199)] = 103.0        # clôture
        tg = {"date": [d0, d1], "O": [99.0, 100.5], "C": [100.0, 103.0]}
        r = ss.h1_obs("X-USD", "X", perp, tg, until=dt.date(2026, 7, 1))
        self.assertEqual(len(r), 1)
        r = r[0]
        self.assertAlmostEqual(r["move"], 1e4 * math.log(101 / 100), places=9)       # perp : 100 -> 101
        self.assertAlmostEqual(r["gap"], 1e4 * math.log(100.5 / 100.0), places=9)    # sous-jacent : clôture 100, ouverture 100.5
        self.assertAlmostEqual(r["res"], r["move"] - r["gap"], places=9)
        self.assertAlmostEqual(r["f30"], 1e4 * math.log(102.01 / 101), places=9)
        self.assertAlmostEqual(r["fc"], 1e4 * math.log(103 / 101), places=9)
        self.assertTrue(r["wd"] and not r["wk"])


class H2(unittest.TestCase):
    def test_injected_momentum_and_reversal_found_with_right_sign(self):
        for phi, want in ((0.15, 1), (-0.15, -1)):
            P = synth_panel(random.Random(3), 3000, 20, phi)
            st = ss.h2_stats(ss.h2_series(P, "mom_1", 1), 1)
            self.assertEqual(st["ic"] > 0, want > 0)
            self.assertGreater(abs(st["z"]), 4.0)
            self.assertEqual(st["spread"] > 0, want > 0)

    def test_null_nothing_found(self):
        P = synth_panel(random.Random(4), 3000, 20, 0.0)
        zs = []
        for v in ("mom_1", "mom_5", "mom_20", "mom_60", "mom_60s"):
            zs.append(ss.h2_stats(ss.h2_series(P, v, 1), 1)["z"])
        self.assertLess(max(abs(z) for z in zs), 3.5, zs)
        q = gs.bh_q([gs.phi_p(z) for z in zs])
        self.assertGreater(min(q), 0.05)

    def test_no_lookahead_signal_and_vol(self):
        P = synth_panel(random.Random(5), 600, 5, 0.1)
        cut = 400
        Q = ss.Panel.__new__(ss.Panel)
        Q.tickers, Q.n, Q.dates = P.tickers, cut, P.dates[:cut]
        Q.lr = {t: a[:cut] for t, a in P.lr.items()}
        Q.sig = {t: ss.Panel._vol(a) for t, a in Q.lr.items()}
        for var in ss.H2_VARS:
            for t in range(cut):
                for i in range(5):
                    a, b = P.signal(var, t, i), Q.signal(var, t, i)
                    self.assertTrue((a != a and b != b) or a == b, (var, t))
        for tk in P.tickers:
            for t in range(cut):
                a, b = P.sig[tk][t], Q.sig[tk][t]
                self.assertTrue((a != a and b != b) or a == b)


class H3(unittest.TestCase):
    def test_injected_overnight_drift_found_and_placebo_null(self):
        rng = random.Random(6)
        vals = [20.0 + rng.gauss(0, 60) for _ in range(3000)]       # +20 bps par nuit, bruit 60 bps
        st = ss.h3_stats(vals, 20, "ON", "all")
        self.assertGreater(st["z"], 4.0)
        self.assertAlmostEqual(st["cost"], ss.COST_RT + ss.FUND_BPS_H * 20.0, places=9)   # long : paie le funding
        self.assertAlmostEqual(st["tradab"], st["mean"] / st["cost"], places=12)
        zs = [ss.h3_stats(ss.sign_flip(vals, 20, random.Random(k)), 20, "ON", "all")["z"] for k in range(40)]
        self.assertLess(sum(abs(z) > 3 for z in zs), 3)
        q = [x for x in gs.bh_q([gs.phi_p(z) for z in zs]) if x == x]
        self.assertGreater(min(q), 0.05)


class Downloader(unittest.TestCase):
    def test_rate_limiter_waits_at_50_per_hour(self):
        now = [10000.0]
        slept = []

        def sleep(s):
            slept.append(s)
            now[0] += s + 1
        st = {"requests": [now[0] - 100 + i for i in range(ft.PER_HOUR)], "months": {}, "tickers": {}}
        ft.wait_slot(st, now=lambda: now[0], sleep=sleep)
        self.assertTrue(slept and max(slept) <= 600 and sum(slept) > 3000)   # attente par pas de 10 min jusqu'à la sortie de l'heure
        self.assertLess(len([x for x in st["requests"] if now[0] - x < 3600]), ft.PER_HOUR)

    def test_key_is_in_header_not_in_url_and_not_printed(self):
        seen = {}

        class R(io.BytesIO):
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False
        real = urllib.request.urlopen

        def fake(req, timeout=0):
            seen["url"], seen["auth"] = req.full_url, req.get_header("Authorization")
            return R(b"[]")
        urllib.request.urlopen = fake
        old = ft.STATE
        try:
            with tempfile.TemporaryDirectory() as d:
                ft.STATE = os.path.join(d, "s.json")
                ft.OUT = d
                st = {"requests": [], "months": {}, "tickers": {}}
                code, _ = ft.get("SECRETKEY123", "AAPL", st)
        finally:
            urllib.request.urlopen = real
            ft.STATE = old
        self.assertEqual(code, 200)
        self.assertNotIn("SECRETKEY123", seen["url"])
        self.assertEqual(seen["auth"], "Token SECRETKEY123")

    def test_env_and_data_are_gitignored(self):
        root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
        with open(os.path.join(root, ".gitignore"), encoding="utf-8") as f:
            ig = f.read().split()
        self.assertIn(".env", ig)
        self.assertIn("data/tiingo/", ig)
        self.assertIn("results/", ig)


if __name__ == "__main__":
    unittest.main()
