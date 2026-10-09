"""Tests de tools/pm_calibration.py et tools/fetch_pm.py : dates, prix à T0, rendements calculés à la main, exclusions (marché fermé ou non démarré à T0, prix périmé), jackknife par événement,
intervalle de Wilson, contrôle positif (outsiders surévalués) et nul (calibration parfaite), filtres de l'API (réseau simulé). stdlib uniquement, aucun appel réel. Lancé par ctest.
"""
import datetime as dt
import json
import math
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import fetch_pm as fp  # noqa: E402
import pm_calibration as pm  # noqa: E402

RF = ([dt.date(2020, 1, 1)], [0.04])
UTC = dt.timezone.utc


def market(mid="m1", end="2025-03-31T12:00:00Z", start="2025-01-01T00:00:00Z", closed="2025-04-01 07:20:28+00", yes=0.0, event="e1"):
    return {"id": mid, "question": "q", "yes_token": "t", "yes": yes, "volume": 1e6, "start": start, "end": end, "closed": closed, "event": event, "neg_risk": False}


def ts(s):
    return int(dt.datetime.fromisoformat(s).replace(tzinfo=UTC).timestamp())


class Dates(unittest.TestCase):
    def test_parse_variants(self):
        self.assertEqual(pm.parse_ts("2025-04-01 07:20:28+00"), dt.datetime(2025, 4, 1, 7, 20, 28, tzinfo=UTC))
        self.assertEqual(pm.parse_ts("2025-03-31T12:00:00Z"), dt.datetime(2025, 3, 31, 12, 0, tzinfo=UTC))
        self.assertEqual(pm.parse_ts("2024-12-04T17:50:46.892Z").year, 2024)
        self.assertIsNone(pm.parse_ts(None))

    def test_price_at(self):
        h = [[100, 0.5], [200, 0.6]]
        self.assertEqual(pm.price_at(h, 250), 0.6)
        self.assertEqual(pm.price_at(h, 150), 0.5)
        self.assertIsNone(pm.price_at(h, 50))                       # avant le premier point
        self.assertIsNone(pm.price_at(h, 200 + 2 * 86400 + 1))       # dernier point trop ancien (plus de 2 jours)

    def test_periods(self):
        self.assertEqual(pm.period(dt.date(2025, 6, 30)), "train")
        self.assertEqual(pm.period(dt.date(2025, 7, 1)), "validation")
        self.assertEqual(pm.period(dt.date(2026, 1, 1)), "test")


class Returns(unittest.TestCase):
    def one(self, m, price, t_price="2025-03-24T00:00:00"):
        mk = {m["id"]: m}
        hist = {m["id"]: [[ts(t_price), price]]}
        return pm.build_trades(mk, hist, RF, horizons=(7,))

    def test_longshot_sell_by_hand(self):
        # fin le 31/03 12:00, h = 7 j : T0 = 24/03 12:00 ; prix de Yes 5 % (point du 24/03 00:00, moins de 2 jours) ; Yes perd : on achète No à 0,95 + 0,01 = 0,96 et il gagne
        trs, why = self.one(market(yes=0.0), 0.05)
        self.assertEqual(len(trs), 1)
        t = trs[0]
        days = ((dt.datetime(2025, 4, 1, 7, 20, 28, tzinfo=UTC)) - dt.datetime(2025, 3, 24, 12, 0, tzinfo=UTC)).total_seconds() / 86400
        self.assertAlmostEqual(t["days"], days, places=9)
        self.assertAlmostEqual(t["r"], 1.0 / 0.96 - 1.0 - 0.04 * days / 365.0, places=12)
        self.assertEqual((t["rule"], t["h"], t["period"]), ("LONGSHOT_SELL", 7, "train"))
        # si Yes gagne : on perd tout le dollar investi, plus le coût du capital
        t2 = self.one(market(yes=1.0), 0.05)[0][0]
        self.assertAlmostEqual(t2["r"], -1.0 - 0.04 * days / 365.0, places=12)

    def test_fav_buy_by_hand(self):
        t = self.one(market(yes=1.0), 0.95)[0][0]                     # Yes à 95 %, ask 0,96, gagne
        self.assertEqual(t["rule"], "FAV_BUY")
        self.assertAlmostEqual(t["r"], 1.0 / 0.96 - 1.0 - 0.04 * t["days"] / 365.0, places=12)
        self.assertEqual(len(self.one(market(yes=1.0), 0.50)[0]), 0)  # prix intermédiaire : aucune règle

    def test_exclusions_use_only_information_known_at_T0(self):
        # fermé une heure AVANT T0 : le prix serait déjà résolu -> exclu
        trs, why = self.one(market(closed="2025-03-24 11:00:00+00"), 0.05)
        self.assertEqual(len(trs), 0)
        self.assertEqual(why.get("fermé avant T0"), 1)
        trs, why = self.one(market(start="2025-03-25T00:00:00Z"), 0.05)           # démarré après T0
        self.assertEqual((len(trs), why.get("pas démarré à T0")), (0, 1))
        trs, why = self.one(market(), 0.05, t_price="2025-03-20T00:00:00")        # dernier prix à 4,5 jours de T0
        self.assertEqual((len(trs), why.get("pas de prix récent à T0")), (0, 1))
        # le prix utilisé est celui de T0 : un point POSTÉRIEUR à T0 ne change rien
        mk = {"m1": market(yes=0.0)}
        a = pm.build_trades(mk, {"m1": [[ts("2025-03-24T00:00:00"), 0.05]]}, RF, horizons=(7,))[0]
        b = pm.build_trades(mk, {"m1": [[ts("2025-03-24T00:00:00"), 0.05], [ts("2025-03-30T00:00:00"), 0.99]]}, RF, horizons=(7,))[0]
        self.assertEqual(a[0]["r"], b[0]["r"])


class Statistics(unittest.TestCase):
    def test_jackknife_by_event_by_hand(self):
        trs = [{"event": "E%d" % (i % 6), "r": 0.01 * ((i % 6) - 2) + 0.001 * i} for i in range(36)]
        m, se = pm.jack(trs)
        n = len(trs)
        by = {}
        for t in trs:
            by.setdefault(t["event"], []).append(t["r"])
        S = sum(t["r"] for t in trs)
        th = [(S - sum(v)) / (n - len(v)) for v in by.values()]
        mean_th = sum(th) / len(th)
        want = math.sqrt((len(th) - 1) / len(th) * sum((x - mean_th) ** 2 for x in th))
        self.assertAlmostEqual(m, S / n, places=12)
        self.assertAlmostEqual(se, want, places=12)

    def test_wilson_by_hand(self):
        lo, hi = pm.wilson(0, 10)
        self.assertAlmostEqual(lo, 0.0, places=9)
        self.assertAlmostEqual(hi, 1.96 ** 2 / (10 + 1.96 ** 2), places=9)      # borne haute de Wilson pour 0 succès sur 10


def synthetic(true_scale, seed, n_per_period=3000):
    """Transactions LONGSHOT_SELL : prix de Yes entre 4 et 8 %, probabilité vraie = true_scale x prix (1 = calibration parfaite, 0,5 = outsiders surévalués)."""
    rng = random.Random(seed)
    out = []
    for per, base in (("train", dt.date(2024, 1, 1)), ("validation", dt.date(2025, 8, 1))):
        for i in range(n_per_period):
            p = rng.uniform(0.04, 0.08)
            y = 1.0 if rng.random() < true_scale * p else 0.0
            ask, win = (1 - p) + pm.SPREAD_HALF, 1.0 - y
            carry = 0.0004
            out.append({"rule": "LONGSHOT_SELL", "h": 7, "period": per, "event": "%s%d" % (per, i // 3), "r": win / ask - 1 - carry, "p": p, "y": y, "days": 7.0,
                        "end": base + dt.timedelta(days=i % 300), "ask": ask, "win": win, "carry": carry})
    return out


class Controls(unittest.TestCase):
    def test_overpriced_longshots_are_found(self):
        res = pm.evaluate(synthetic(0.5, 1))
        r = res[("LONGSHOT_SELL", 7)]
        self.assertGreater(r["mean"], 0.015)
        self.assertGreater(r["z"], 4.0)
        self.assertGreaterEqual(r["beat_null"], 0.95)

    def test_perfect_calibration_is_not_found(self):
        res = pm.evaluate(synthetic(1.0, 2))
        r = res[("LONGSHOT_SELL", 7)]
        self.assertLess(r["mean"], pm.X_TRADE)                       # le spread d'un cent plus le coût du capital rendent le net négatif
        self.assertFalse(all(r["criteria"].values()))


class Downloader(unittest.TestCase):
    def test_filters_by_hand(self):
        base = {"closed": True, "outcomes": '["Yes", "No"]', "outcomePrices": '["1", "0"]', "umaResolutionStatus": "resolved", "endDate": "2025-01-01T00:00:00Z",
                "feesEnabled": False, "clobTokenIds": '["a", "b"]', "volumeNum": 500000}
        self.assertEqual(fp.keep(base, 300000), (True, ""))
        self.assertEqual(fp.keep(dict(base, outcomes='["A", "B"]'), 300000)[1], "non binaire Yes/No")
        self.assertEqual(fp.keep(dict(base, outcomePrices='["0.5", "0.5"]'), 300000)[1], "résolution ni 1 ni 0")
        self.assertEqual(fp.keep(dict(base, feesEnabled=True), 300000)[1], "frais activés")
        self.assertEqual(fp.keep(dict(base, volumeNum=1000), 300000)[1], "volume insuffisant")
        self.assertEqual(fp.keep(dict(base, endDate=""), 300000)[1], "date de fin inconnue")

    def test_pagination_stops_and_counts(self):
        pages = {0: [{"closed": True, "outcomes": '["Yes", "No"]', "outcomePrices": '["0", "1"]', "umaResolutionStatus": "resolved", "endDate": "2025-01-01T00:00:00Z",
                      "feesEnabled": False, "clobTokenIds": '["a", "b"]', "volumeNum": 400000, "id": str(i), "question": "q", "events": [{"id": "e"}], "startDate": "x"} for i in range(100)],
                 100: [{"closed": True, "outcomes": '["A", "B"]', "outcomePrices": '["0", "1"]', "umaResolutionStatus": "resolved", "endDate": "x", "clobTokenIds": '["a", "b"]',
                        "volumeNum": 400000}]}
        calls = []

        def fetch(url):
            off = int(url.split("offset=")[1].split("&")[0])
            calls.append(off)
            return pages.get(off, [])
        got = []
        counts = fp.list_markets(dt.date(2025, 1, 1), dt.date(2025, 1, 7), 300000, got.append, fetch)
        self.assertEqual(counts, {"gardé": 100, "non binaire Yes/No": 1})
        self.assertEqual(calls, [0, 100])                              # 100 puis moins de 100 : fin
        self.assertEqual(len(got), 100)


if __name__ == "__main__":
    unittest.main()
