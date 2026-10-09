"""Tests de tools/funding_xvenue.py et tools/fetch_hl.py : règle de décision, signe du funding, comptabilité horaire, coûts, liquidation, absence d'anticipation,
bootstrap déterministe, pagination du téléchargeur (réseau simulé). stdlib uniquement, aucun appel réel. Lancé par ctest.
"""
import calendar
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import fetch_hl as fh  # noqa: E402
import funding_xvenue as fx  # noqa: E402

NAN = float("nan")
START = calendar.timegm((2026, 6, 1, 0, 0, 0)) // 3600          # lundi 2026-06-01 00:00 UTC
META = {"spread_poly": 3.5, "spread_hl": 3.5, "maxlev_poly": 10.0, "maxlev_hl": 10.0}


def make_pair(n, f_poly, f_hl, c_poly=100.0, c_hl=100.0, hi_hl=None, lo_poly=None):
    hours = list(range(START, START + n))
    cp = [c_poly] * n if not isinstance(c_poly, list) else c_poly
    ch = [c_hl] * n if not isinstance(c_hl, list) else c_hl
    return fx.Pair("X", hours, [f_poly] * n if not isinstance(f_poly, list) else f_poly, [f_hl] * n if not isinstance(f_hl, list) else f_hl, cp, ch,
                   list(cp), [lo_poly or v for v in cp], hi_hl or list(ch), list(ch), dict(META))


class Decision(unittest.TestCase):
    def test_rule_by_hand(self):
        p = make_pair(600, 0.0, 2e-5)                       # Hyperliquid paie 2e-5 de plus par heure : 17,5 % par an
        self.assertEqual(fx.decide(p, 100)[0], 0)           # moins de 14 jours d'historique : cash
        pos, ann = fx.decide(p, 400)
        self.assertEqual(pos, 1)                            # short Hyperliquid, long Polymarket
        self.assertAlmostEqual(ann, 2e-5 * 8760, places=9)
        self.assertEqual(fx.decide(make_pair(600, 0.0, 1e-6), 400)[0], 0)        # 0,876 % par an < theta = 2 % : cash
        self.assertEqual(fx.decide(make_pair(600, 2e-5, 0.0), 400)[0], -1)       # inverse : short Polymarket, long Hyperliquid

    def test_no_lookahead(self):
        f = [0.0] * 600
        a = make_pair(600, 0.0, f)
        g = list(f)
        for j in range(400, 600):                           # on réécrit tout l'avenir après l'indice de décision
            g[j] = 5e-4
        b = make_pair(600, 0.0, g)
        self.assertEqual(fx.decide(a, 400), fx.decide(b, 400))


class Accounting(unittest.TestCase):
    def test_hourly_pnl_by_hand(self):
        p = make_pair(672, 0.0, 2e-5)
        rows, eps = fx.simulate(p, 0.04)
        by_i = {r[0]: r for r in rows}
        # i = 336 (lundi, 14 jours plus tard) : décision +1 ; coût d'entrée = (7,75 + 8,25) bps = 16 bps ; funding = f_hl - f_poly = 2e-5 reçu par le short Hyperliquid
        self.assertEqual(by_i[336][1], 1)
        self.assertAlmostEqual(by_i[336][4], 16.0 / 1e4, places=12)
        self.assertAlmostEqual(by_i[336][2], 2e-5, places=15)
        self.assertAlmostEqual(by_i[336][5], 0.04 * (1 / 3 + 1 / 3) / 8760, places=15)           # coût des deux marges à levier 3
        self.assertEqual(by_i[504][4], 0.0)                 # lundi suivant : même décision, aucun coût
        self.assertEqual(by_i[100][1], 0)                   # avant le warm-up : cash, aucun flux
        self.assertEqual((by_i[100][2], by_i[100][3], by_i[100][5]), (0.0, 0.0, 0.0))
        self.assertEqual(len(eps), 1)                       # un seul épisode, clos à la dernière heure
        self.assertEqual(eps[0]["entry"], 336)

    def test_funding_sign_both_directions(self):
        # position -1 : short Polymarket reçoit f_poly, long Hyperliquid paie f_hl
        p = make_pair(600, 3e-5, 1e-5)
        rows, _ = fx.simulate(p, 0.0)
        r = {x[0]: x for x in rows}[400]
        self.assertEqual(r[1], -1)
        self.assertAlmostEqual(r[2], 3e-5 - 1e-5, places=15)

    def test_basis_is_long_leg_minus_short_leg(self):
        c_poly = [100.0] * 600
        c_poly[400] = 101.0                                  # Polymarket +1 % à l'heure 400 ; Hyperliquid inchangé
        p = make_pair(600, 0.0, 2e-5, c_poly=c_poly)
        rows, _ = fx.simulate(p, 0.0)
        r = {x[0]: x for x in rows}[400]
        self.assertEqual(r[1], 1)                            # long Polymarket, short Hyperliquid : on gagne
        self.assertAlmostEqual(r[3], 0.01, places=12)

    def test_identity(self):
        p = make_pair(672, 0.0, 2e-5)
        s = fx.summarize_pair(p, lambda _p: 0.04)
        tot = sum(x[2] + x[3] - x[4] - x[5] for x in s["rows"])
        self.assertAlmostEqual(s["excess_ann"], tot / s["hours"] * 8760, places=12)
        self.assertAlmostEqual(s["excess_ann"], s["funding_ann"] + s["basis_ann"] - s["cost_ann"] - s["cap_ann"], places=12)

    def test_hl_fee_doubles_the_hl_leg(self):
        p = make_pair(600, 0.0, 2e-5)
        rows, _ = fx.simulate(p, 0.0, hl_fee=9.0)
        self.assertAlmostEqual({x[0]: x for x in rows}[336][4], (7.75 + 9.0 + 2.0 + 1.75) / 1e4, places=12)


class Liquidation(unittest.TestCase):
    def test_distance_by_hand(self):
        n = 600
        hi = [100.0] * n
        hi[450] = 140.0                                      # Hyperliquid +40 % (jambe courte) : perte
        p = make_pair(n, 0.0, 2e-5, hi_hl=hi)
        _rows, eps = fx.simulate(p, 0.0)
        share3, _ = fx.liquidation_share(p, eps, 3)          # distance 1/3 - 0,05 = 28,3 % : liquidé
        share2, _ = fx.liquidation_share(p, eps, 2)          # distance 45 % : pas liquidé
        self.assertEqual((share3, share2), (1.0, 0.0))


class Weekly(unittest.TestCase):
    def test_week_sums_and_bootstrap_deterministic(self):
        p = make_pair(672, 0.0, 2e-5)
        rows, _ = fx.simulate(p, 0.0)
        t = fx.week_sums(p, rows)
        self.assertEqual(sum(a[1] for a in t.values()), len(rows))
        tabs = {"X": t, "Y": t}
        weeks = sorted(t)
        self.assertEqual(fx.bootstrap(tabs, weeks, draws=50), fx.bootstrap(tabs, weeks, draws=50))


class Downloader(unittest.TestCase):
    def test_funding_pagination_and_dedup(self):
        calls = []

        def fetch(body):
            calls.append(body)
            t = body["startTime"]
            n = 500 if t == 0 else 20
            return [{"time": t + i, "fundingRate": "0.00001", "premium": "0.0001"} for i in range(n)]
        rows = fh.funding_history("BTC", 0, 10 ** 12, fetch)
        self.assertEqual(len(calls), 2)                      # deux pages : 500 puis 20 (< 500 : fin)
        self.assertEqual(calls[1]["startTime"], 500)         # la page suivante démarre 1 ms après le dernier point reçu
        self.assertEqual(len(rows), 520)
        self.assertEqual(len({r[0] for r in rows}), 520)

    def test_files_named_without_colon_and_no_secrets(self):
        self.assertEqual(fh.fname("xyz:AAPL"), "xyz_AAPL")
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools", "fetch_hl.py"), encoding="utf-8") as f:
            src = f.read().lower()
        for bad in ("@gmail", "private_key", "api_key", "authorization"):
            self.assertNotIn(bad, src)


if __name__ == "__main__":
    unittest.main()
