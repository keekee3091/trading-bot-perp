"""Tests de la pagination de tools/fetch_trades.py contre un faux serveur (aucun réseau).

Le faux serveur reproduit le comportement établi par essai : pages de 100 du plus récent au plus ancien,
`end_timestamp` EXCLUSIF, `start_timestamp` inclusif, nombreux trades à la même milliseconde.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import fetch_trades as ft  # noqa: E402


def make_trades(n, per_ms):
    # ts = 10_000 + i // per_ms : per_ms trades partagent chaque milliseconde (cassures de page au milieu d'une ms)
    return [{"trade_id": 900000 + i * 7919 % 100003 + i, "instrument_id": 1, "side": "long" if i % 3 else "short",
             "price": str(100 + i % 5), "quantity": "0.5", "settlement": False, "timestamp": 10_000 + i // per_ms}
            for i in range(n)]


class FakeApi:
    def __init__(self, trades, stop_after=None):
        self.trades = trades
        self.calls = 0
        self.stop_after = stop_after

    def __call__(self, limiter, path, params=None, retries=6):
        self.calls += 1
        if self.stop_after and self.calls > self.stop_after:
            ft.STOP.set()
        rows = [t for t in self.trades if params["start_timestamp"] <= t["timestamp"] < params["end_timestamp"]]
        rows.sort(key=lambda t: (t["timestamp"], t["trade_id"]), reverse=True)
        return {"data": rows[:100], "more": len(rows) > 100}


class Pagination(unittest.TestCase):
    def setUp(self):
        self.out = tempfile.mkdtemp()
        ft.STOP.clear()
        self.orig = ft.api_get

    def tearDown(self):
        ft.api_get = self.orig
        ft.STOP.clear()

    def run_fetch(self, trades, start_ms=0, stop_after=None):
        ft.api_get = FakeApi(trades, stop_after)
        # le faux serveur ignore l'horloge : end_ms est fixé par time.time() dans fetch_trades ; assez grand
        return ft.fetch_trades(None, "T", 1, start_ms, self.out, lambda m: None)

    def read_final(self):
        ft.finalize_trades(self.out, "T")
        with open(os.path.join(self.out, "T_trades.csv")) as f:
            next(f)
            return [line.strip().split(",") for line in f]

    def test_no_loss_no_duplicate_with_same_ms_ties(self):
        trades = make_trades(1050, per_ms=7)  # 7 par ms : les pages de 100 coupent au milieu d'une ms
        st = self.run_fetch(trades)
        self.assertTrue(st["done"])
        rows = self.read_final()
        ids = [r[1] for r in rows]
        self.assertEqual(len(ids), 1050)
        self.assertEqual(len(set(ids)), 1050)
        self.assertEqual({str(t["trade_id"]) for t in trades}, set(ids))
        ts = [int(r[0]) for r in rows]
        self.assertEqual(ts, sorted(ts))  # trié par temps croissant

    def test_start_bound_respected(self):
        trades = make_trades(500, per_ms=5)  # ts 10000 .. 10099
        self.run_fetch(trades, start_ms=10_050)
        rows = self.read_final()
        self.assertTrue(rows and min(int(r[0]) for r in rows) >= 10_050 - 0)  # une page entière peut dépasser le bord
        self.assertTrue(all(int(r[0]) >= 10_050 - 100 for r in rows))
        self.assertTrue(set(str(t["trade_id"]) for t in trades if t["timestamp"] >= 10_050) <= {r[1] for r in rows})

    def test_resume_after_interruption(self):
        trades = make_trades(1050, per_ms=7)
        st = self.run_fetch(trades, stop_after=3)  # interrompu après 3 pages
        self.assertFalse(st["done"])
        self.assertLess(st["rows"], 1050)
        ft.STOP.clear()
        st = self.run_fetch(trades)  # reprise
        self.assertTrue(st["done"])
        ids = [r[1] for r in self.read_final()]
        self.assertEqual(len(ids), 1050)
        self.assertEqual(len(set(ids)), 1050)

    def test_over_100_trades_in_one_ms_is_counted_not_hung(self):
        trades = make_trades(300, per_ms=150)  # 150 trades à la même ms : plus d'une page
        st = self.run_fetch(trades)
        self.assertTrue(st["done"])
        self.assertGreaterEqual(st["skipped_ms"], 1)  # perte déclarée, pas de boucle infinie
        self.assertLess(self.calls_total(), 20)

    def calls_total(self):
        return ft.api_get.calls


class Limiter(unittest.TestCase):
    def test_global_rate(self):
        import time
        lim = ft.Limiter(50.0)  # 20 ms entre deux requêtes
        t0 = time.monotonic()
        for _ in range(11):
            lim.wait()
        self.assertGreaterEqual(time.monotonic() - t0, 10 * 0.02 * 0.9)


if __name__ == "__main__":
    unittest.main(verbosity=1)
