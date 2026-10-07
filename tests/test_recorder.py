"""Tests de tools/recorder.py : métriques de carnet calculées à la main, tolérance aux erreurs, format.

Lancé par ctest (python tests/test_recorder.py). stdlib uniquement, aucun accès réseau.
"""
import json
import os
import sys
import tempfile
import unittest
import urllib.error

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import recorder  # noqa: E402

SAT_NOON = 1791028800.0  # samedi 2026-10-03 12:00 UTC
MON_15 = 1791158400.0 + 15 * 3600  # lundi 2026-10-05 15:00 UTC


class FakeClock:
    def __init__(self, t):
        self.t = t

    def now(self):
        return self.t

    def sleep(self, s):
        self.t += s


INSTRUMENTS = [
    {"instrument_id": 6, "symbol": "BTC-USD", "category": "crypto"},
    {"instrument_id": 15, "symbol": "AAPL-USD", "category": "equity"},
]
TICKERS = [
    {"instrument_id": 6, "symbol": "BTC-USD", "index_price": "100", "mark_price": "101", "last_price": "100.5",
     "mid_price": "100.5", "open_interest": "12.5", "funding_rate": "0.00001", "next_funding": 1791162000000,
     "timestamp": 1791158400123},
    {"instrument_id": 15, "symbol": "AAPL-USD", "index_price": "200", "mark_price": "200", "last_price": "200",
     "mid_price": "200", "open_interest": "3", "funding_rate": None, "next_funding": 1791162000000,
     "timestamp": 1791158400123},
]
BOOK = {"instrument_id": 6, "bids": [["100.4", "1"], ["99", "2"]], "asks": [["100.6", "1"], ["102", "2"]]}
FUNDING = {"data": [{"funding_rate": "0.00001", "timestamp": 1791158400037},
                    {"funding_rate": "-0.00002", "timestamp": 1791154800021}], "more": False}


def good_fetch(path, params=None):
    if path == "/v1/info/instruments":
        return INSTRUMENTS
    if path == "/v1/info/tickers":
        return TICKERS
    if path == "/v1/info/book":
        return BOOK
    if path == "/v1/info/funding":
        return FUNDING
    raise AssertionError(path)


def lines(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


class BookMath(unittest.TestCase):
    # mid = 100.5 ; spread = 0.2 / 100.5 = 19.9005 bps
    def test_book_record(self):
        rec = recorder.book_record(BOOK, "BTC-USD", 6, 1000, 12, 1)
        self.assertAlmostEqual(rec["mid"], 100.5, 12)
        self.assertAlmostEqual(rec["spread_bps"], 0.2 / 100.5 * 1e4, 9)
        # 5 bps : bornes 100.44975 / 100.55025, aucun niveau dedans ; 20 bps : 100.2990 / 100.7010
        self.assertAlmostEqual(rec["depth_bid"]["5"], 0.0, 12)
        self.assertAlmostEqual(rec["depth_ask"]["5"], 0.0, 12)
        self.assertAlmostEqual(rec["depth_bid"]["20"], 100.4, 9)
        self.assertAlmostEqual(rec["depth_ask"]["20"], 100.6, 9)
        self.assertIsNone(rec["slip_buy"]["1000"])  # 304.6 de notionnel affiché seulement
        self.assertEqual(rec["session"], 1)

    def test_market_cost(self):
        asks = [(100.6, 1.0), (102.0, 2.0)]
        mid = 100.5
        # 50 de notionnel, tout au premier niveau : (100.6 - 100.5) / 100.5 = 9.9502 bps
        self.assertAlmostEqual(recorder.market_cost_bps(asks, mid, 50, True), 0.1 / 100.5 * 1e4, 9)
        # 200 : 1 unité à 100.6, puis 99.4 de notionnel à 102 (0.974510 unité) ; vwap = 200 / 1.974510
        vwap = 200 / (1 + 99.4 / 102)
        self.assertAlmostEqual(recorder.market_cost_bps(asks, mid, 200, True), (vwap - mid) / mid * 1e4, 9)
        bids = [(100.4, 1.0), (99.0, 2.0)]
        self.assertAlmostEqual(recorder.market_cost_bps(bids, mid, 50, False), 0.1 / 100.5 * 1e4, 9)
        self.assertIsNone(recorder.market_cost_bps(asks, mid, 1e6, True))

    def test_empty_side_rejected(self):
        with self.assertRaises(ValueError):
            recorder.book_record({"bids": [], "asks": [["1", "1"]]}, "X", 1, 0, 0, 1)

    def test_ticker_record(self):
        r = recorder.ticker_record(TICKERS[0], "BTC-USD", 6, 5, 7, 1)
        self.assertAlmostEqual(r["basis_bps"], 100.0, 9)  # (101 - 100) / 100
        self.assertEqual(recorder.ticker_record(TICKERS[1], "AAPL-USD", 15, 5, 7, 0)["funding"], 0.0)  # null toléré


class Behaviour(unittest.TestCase):
    def make(self, fetch, t0, symbols=("BTC-USD", "AAPL-USD")):
        self.dir = tempfile.mkdtemp()
        clk = FakeClock(t0)
        rec = recorder.Recorder(list(symbols), self.dir, fetch=fetch, clock=clk.now, sleep=clk.sleep)
        return rec, clk

    def day(self, t):
        import time
        return os.path.join(self.dir, time.strftime("%Y-%m-%d", time.gmtime(t)))

    def test_records_and_session_flags(self):
        rec, _ = self.make(good_fetch, SAT_NOON)  # samedi : action fermée, crypto ouverte
        counts = rec.run(tick_s=5, book_s=10, funding_s=600, duration=30)
        d = self.day(SAT_NOON)
        tickers = lines(os.path.join(d, "tickers.jsonl"))
        self.assertGreaterEqual(len(tickers), 2 * 5)
        by = {t["sym"]: t["session"] for t in tickers}
        self.assertEqual(by, {"BTC-USD": 1, "AAPL-USD": 0})
        self.assertTrue(all(isinstance(t["t"], int) for t in tickers))
        books = lines(os.path.join(d, "books.jsonl"))
        self.assertTrue(books and all(b["sym"] in ("BTC-USD", "AAPL-USD") for b in books))
        self.assertEqual(len(books[0]["bids"]), 2)
        self.assertTrue(os.path.exists(os.path.join(d, "instruments.json")))
        self.assertEqual(counts["errors"], 0)

    def test_funding_deduplicated(self):
        rec, _ = self.make(good_fetch, MON_15)
        rec.run(tick_s=5, book_s=10, funding_s=5, duration=40)  # 8 relevés de funding, 2 points publiés
        f = []
        import glob
        for p in glob.glob(os.path.join(self.dir, "*", "funding.jsonl")):
            f += lines(p)
        self.assertEqual(len(f), 4)  # 2 points x 2 symboles, une seule fois chacun
        self.assertEqual({x["ts"] for x in f}, {1791158400037, 1791154800021})

    def test_network_down_never_raises(self):
        def dead(path, params=None):
            raise urllib.error.URLError("certificate verify failed: Hostname mismatch")

        rec, clk = self.make(dead, MON_15)
        counts = rec.run(tick_s=5, book_s=10, funding_s=600, duration=300)
        self.assertGreater(counts["errors"], 2)
        self.assertEqual((counts["tickers"], counts["books"]), (0, 0))
        with open(os.path.join(self.day(MON_15), "errors.log"), encoding="utf-8") as f:
            log = f.read()
        self.assertIn("URLError", log)
        # délai croissant : bien moins d'essais que de pas de 0.5 s (300 s / 0.5 = 600)
        self.assertLess(counts["errors"], 40)

    def test_partial_failure_keeps_other_streams(self):
        def flaky(path, params=None):
            if path == "/v1/info/book":
                raise TimeoutError("lent")
            return good_fetch(path, params)

        rec, _ = self.make(flaky, MON_15)
        counts = rec.run(tick_s=5, book_s=10, funding_s=600, duration=40)
        self.assertGreater(counts["tickers"], 0)
        self.assertEqual(counts["books"], 0)
        self.assertGreater(counts["errors"], 0)

    def test_malformed_payload_is_an_error_not_a_crash(self):
        def bad(path, params=None):
            if path == "/v1/info/tickers":
                return [{"symbol": "BTC-USD"}]  # champs manquants
            return good_fetch(path, params)

        rec, _ = self.make(bad, MON_15)
        counts = rec.run(tick_s=5, book_s=10, funding_s=600, duration=20)
        self.assertGreater(counts["errors"], 0)

    def test_unknown_symbol_logged(self):
        rec, _ = self.make(good_fetch, MON_15, symbols=("BTC-USD", "NOPE-USD"))
        counts = rec.run(duration=10)
        self.assertGreater(counts["errors"], 0)
        self.assertEqual(counts["tickers"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=1)
