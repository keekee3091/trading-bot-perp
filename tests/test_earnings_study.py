"""Tests de tools/earnings_study.py et tools/fetch_sec.py : dates et DST, fenêtre de réaction, absence d'anticipation, contrôle positif.

Réseau simulé : aucun appel réel, aucune adresse réelle dans les fixtures (User-Agent factice). stdlib uniquement. Lancé par ctest.
"""
import datetime as dt
import io
import json
import math
import os
import random
import sys
import tempfile
import unittest
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import earnings_study as es  # noqa: E402
import fetch_sec as fs  # noqa: E402
import grid_stage1 as gs  # noqa: E402

DT = dt.datetime


def weekdays(n, start=dt.date(2010, 1, 4)):
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += dt.timedelta(1)
    return out


class Dates(unittest.TestCase):
    def test_et_conversion_with_dst(self):
        # heure d'été : UTC-4 ; hiver : UTC-5 ; 2026-03-08 07:00 UTC est le basculement (2:00 EST -> 3:00 EDT)
        self.assertEqual(es.et_local(es.parse_utc("2026-07-31T00:30:28.000Z")), DT(2026, 7, 30, 20, 30, 28))
        self.assertEqual(es.et_local(es.parse_utc("2026-01-30T01:30:00.000Z")), DT(2026, 1, 29, 20, 30))
        self.assertEqual(es.et_local(DT(2026, 3, 8, 6, 59)), DT(2026, 3, 8, 1, 59))
        self.assertEqual(es.et_local(DT(2026, 3, 8, 7, 0)), DT(2026, 3, 8, 3, 0))
        self.assertEqual(es.et_local(DT(2026, 11, 1, 5, 59)), DT(2026, 11, 1, 1, 59))     # encore EDT
        self.assertEqual(es.et_local(DT(2026, 11, 1, 6, 0)), DT(2026, 11, 1, 1, 0))       # EST : l'heure repasse à 1:00

    def test_same_clock_time_in_summer_and_winter(self):
        # 16:05 de l'Est est AMC été comme hiver : 20:05 UTC en été, 21:05 UTC en hiver
        for s in ("2026-07-15T20:05:00.000Z", "2026-01-15T21:05:00.000Z"):
            self.assertEqual(es.et_local(es.parse_utc(s)).time(), dt.time(16, 5))

    def test_reaction_day(self):
        D = weekdays(10)          # lun 4 janv 2010 ... vendredi 15 janv
        tue, wed, fri, mon = 1, 2, 4, 5
        self.assertEqual(es.reaction_day(DT(2010, 1, 5, 7, 0), D), ("BMO", tue, ""))         # avant l'ouverture : le jour même
        self.assertEqual(es.reaction_day(DT(2010, 1, 5, 16, 30), D), ("AMC", wed, ""))       # après la clôture : le lendemain
        self.assertEqual(es.reaction_day(DT(2010, 1, 8, 17, 0), D), ("AMC", mon, ""))        # vendredi soir : lundi
        self.assertEqual(es.reaction_day(DT(2010, 1, 9, 10, 0), D), ("AMC", mon, ""))        # samedi : lundi
        self.assertEqual(es.reaction_day(DT(2010, 1, 10, 6, 0), D), ("BMO", mon, ""))        # dimanche tôt : lundi
        self.assertEqual(es.reaction_day(DT(2010, 1, 5, 9, 30), D)[0], None)                  # 9:30 exactement : en séance
        self.assertEqual(es.reaction_day(DT(2010, 1, 5, 15, 59), D)[0], None)
        self.assertEqual(es.reaction_day(DT(2010, 1, 5, 16, 0), D)[:2], ("AMC", wed))


def stock_from(prices, start=dt.date(2010, 1, 4)):
    s = es.Stock.__new__(es.Stock)
    s.ticker = "X"
    s.dates = weekdays(len(prices), start)
    s.lc = [math.log(p) for p in prices]
    return s


class Features(unittest.TestCase):
    def prices(self, n, seed):
        rng = random.Random(seed)
        p, out = 100.0, []
        for _ in range(n):
            p *= math.exp(rng.gauss(0, 0.015))
            out.append(p)
        return out

    def test_by_hand(self):
        px = [100.0 + (i % 3) * 0.5 for i in range(110)]
        px[80] = 110.0                     # réaction en E = 80, la veille vaut 100 + (79 % 3) * 0.5 = 100.5
        px[85] = 121.0
        s = stock_from(px)
        f = es.feats(s, 80, until=dt.date(2100, 1, 1))
        self.assertAlmostEqual(f["react"], 1e4 * math.log(110 / px[79]), places=9)
        self.assertAlmostEqual(f["d5"], 1e4 * math.log(121 / 110), places=9)
        rets = [math.log(px[i] / px[i - 1]) for i in range(19, 79)]       # 60 rendements finissant en E-2 = 78
        sig = (sum(r * r for r in rets) / 60 - (sum(rets) / 60) ** 2) ** 0.5 * 1e4
        self.assertAlmostEqual(f["sig"], sig, places=6)
        self.assertAlmostEqual(f["pre_z"], 1e4 * math.log(px[79] / px[74]) / (sig * math.sqrt(5)), places=6)
        self.assertIsNone(es.feats(s, 61, until=dt.date(2100, 1, 1)))   # pas assez d'historique pour la volatilité

    def test_no_lookahead(self):
        px = self.prices(200, 1)
        full = stock_from(px)
        E = 100
        a = es.feats(full, E, until=dt.date(2100, 1, 1))
        cut = stock_from(px[:E + 21])                                   # on supprime tout après E + 20
        b = es.feats(cut, E, until=dt.date(2100, 1, 1))
        for k in ("z_ann", "pre_z", "react", "sig", "d5", "d20"):
            self.assertEqual(a[k], b[k])
        # modifier un prix futur (E + 5) ne change ni la réaction, ni la volatilité, ni l'avant-annonce
        px2 = list(px)
        px2[E + 5] *= 1.5
        c = es.feats(stock_from(px2), E, until=dt.date(2100, 1, 1))
        for k in ("z_ann", "pre_z", "sig"):
            self.assertEqual(a[k], c[k])
        self.assertNotEqual(a["d5"], c["d5"])

    def test_placebo_events_avoid_real_ones(self):
        s = stock_from(self.prices(400, 2))
        kept = [{"ticker": "X", "grp": "AMC", "E": e, "local": None, "filing_date": ""} for e in (100, 160, 220, 280)]
        out, _ = es.event_feats(kept, {"X": s}, until=dt.date(2100, 1, 1), shift=(10, 40), rng=random.Random(3))
        real = {100, 160, 220, 280}
        for f in out:
            self.assertTrue(all(abs(f["E"] - r) > 3 for r in real))


def synth_events(rng, n, beta):
    evs = []
    for i in range(n):
        sig = rng.uniform(100, 300)
        z = rng.gauss(0, 1)
        d5 = beta * z * sig * math.sqrt(5) + rng.gauss(0, 1) * sig * math.sqrt(5)
        evs.append({"ticker": "T%d" % (i % 20), "grp": "AMC", "sig": sig, "z_ann": z, "pre_z": rng.gauss(0, 1), "d5": d5,
                    "d5_n": d5 / (sig * math.sqrt(5)), "date": dt.date(2005, 1, 1) + dt.timedelta(days=7 * i)})
    return evs


class Plumbing(unittest.TestCase):
    def test_positive_control_found_with_right_sign(self):
        for beta in (0.15, -0.15):
            r = es.cell_stats(synth_events(random.Random(7), 1500, beta), "z_ann", "d5")
            self.assertEqual(r["ic"] > 0, beta > 0)
            self.assertGreater(abs(r["z"]), 4.0)
            self.assertEqual(r["spread_bps"] > 0, beta > 0)

    def test_null_nothing_found(self):
        zs = [es.cell_stats(synth_events(random.Random(s), 1500, 0.0), "z_ann", "d5")["z"] for s in range(8)]
        self.assertLess(max(abs(z) for z in zs), 3.5, zs)
        self.assertGreater(min(gs.bh_q([gs.phi_p(z) for z in zs])), 0.05)


class Sec(unittest.TestCase):
    def setUp(self):
        self.calls = []
        main = {"filings": {"recent": {"form": ["8-K", "8-K", "10-Q", "8-K"], "items": ["2.02,9.01", "5.02", "", "7.01,2.02"],
                                       "filingDate": ["2020-01-30", "2020-02-01", "2020-02-02", "2020-05-01"],
                                       "acceptanceDateTime": ["2020-01-30T21:30:00.000Z", "2020-02-01T14:00:00.000Z",
                                                              "2020-02-02T14:00:00.000Z", "2020-05-01T20:30:00.000Z"],
                                       "reportDate": ["2020-01-30", "", "", "2020-05-01"],
                                       "accessionNumber": ["a", "b", "c", "d"]},
                             "files": [{"name": "CIK0000000001-submissions-001.json"}]}}
        older = {"form": ["8-K"], "items": ["2.02"], "filingDate": ["2010-04-20"], "acceptanceDateTime": ["2010-04-20T20:10:00.000Z"],
                 "reportDate": ["2010-04-20"], "accessionNumber": ["z"]}
        self.pages = {"https://data.sec.gov/submissions/CIK0000000001.json": main,
                      "https://data.sec.gov/submissions/CIK0000000001-submissions-001.json": older}
        outer = self

        class R(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def opener(req, timeout=0):
            outer.calls.append((req.full_url, req.get_header("User-agent")))
            return R(json.dumps(outer.pages[req.full_url]).encode())
        self.opener = opener

    def test_events_filtered_cached_and_ua_in_header_only(self):
        with tempfile.TemporaryDirectory() as d:
            ev = fs.events_for(1, "TEST-AGENT contact@example.invalid", out=d, opener=self.opener, sleep=lambda s: None)
            self.assertEqual([e["accession"] for e in ev], ["z", "a", "d"])        # seulement les 8-K avec 2.02, triés
            n = len(self.calls)
            fs.events_for(1, "TEST-AGENT contact@example.invalid", out=d, opener=self.opener, sleep=lambda s: None)
            self.assertEqual(len(self.calls), n)                                   # cache : aucune requête de plus
        for url, ua in self.calls:
            self.assertNotIn("TEST-AGENT", url)
            self.assertEqual(ua, "TEST-AGENT contact@example.invalid")

    def test_rate_limit_at_most_5_per_second(self):
        t = [0.0]
        slept = []
        fs._last[0] = 0.0
        with tempfile.TemporaryDirectory() as d:
            for i in range(10):
                self.pages["https://data.sec.gov/f%d" % i] = {}
                fs.fetch("https://data.sec.gov/f%d" % i, "UA", os.path.join(d, "f%d" % i), opener=self.opener,
                         now=lambda: t[0], sleep=lambda s: (slept.append(s), t.__setitem__(0, t[0] + s)))
        self.assertAlmostEqual(t[0], 0.2 * 10, places=6)       # 10 requêtes : 0.2 s avant chacune (5 par seconde au plus)


if __name__ == "__main__":
    unittest.main()
