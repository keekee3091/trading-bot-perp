"""Tests de tools/mm_economics.py : chiffres calculés à la main sur des données synthétiques minimales.

Lancé par ctest. stdlib uniquement, aucun réseau.
"""
import json
import math
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import mm_economics as mm  # noqa: E402

DAY = 86_400_000


def write(d, name, rows):
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, name), "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def book(t, sym, session, bid, ask, bq=2.0, aq=3.0):
    mid = (bid + ask) / 2
    return {"t": t, "sym": sym, "session": session,
            "bids": [[bid, bq]], "asks": [[ask, aq]], "mid": mid, "spread_bps": (ask - bid) / mid * 1e4,
            "depth_bid": {"5": 0.0, "20": 0.0}, "depth_ask": {"5": 0.0, "20": 0.0}}


class Economics(unittest.TestCase):
    def build(self, days):
        d = tempfile.mkdtemp()
        day = os.path.join(d, "2026-10-05")
        t0 = 1_791_158_400_000
        # Séance : spread 10 bps exactement (mid 100, bid 99.95, ask 100.05) sur 4 relevés
        bks = [book(t0 + i * 15000, "X", 1, 99.95, 100.05) for i in range(4)]
        # Hors séance : spread 4 bps (99.98 / 100.02), 2 relevés
        bks += [book(t0 + 100000 + i * 15000, "X", 0, 99.98, 100.02) for i in range(2)]
        # Dernier relevé loin dans le temps pour fixer la durée de l'enregistrement
        bks.append(book(t0 + int(days * DAY), "X", 1, 99.95, 100.05))
        write(day, "books.jsonl", bks)
        # Ticker en séance : le mid alterne 100, 100.01 toutes les 5 s (8 relevés, 7 intervalles)
        tks = [{"t": t0 + i * 5000, "sym": "X", "session": 1, "mid": 100.0 + 0.01 * (i % 2)} for i in range(8)]
        write(day, "tickers.jsonl", tks)
        return d

    def test_hand_computed(self):
        res = mm.analyse(self.build(1.0), 1.25)
        row = {(r["sym"], r["session"]): r for r in res["rows"]}[("X", 1)]
        self.assertEqual(row["n_book"], 5)
        # [MESURÉ] spread : 10 bps (4 relevés) et le relevé final aussi à 10 bps
        self.assertAlmostEqual(row["spread_mean"], 10.0, 6)
        # touch : bid 99.95 x 2 = 199.9 ; ask 100.05 x 3 = 300.15
        self.assertAlmostEqual(row["touch_bid"], 199.9, 9)
        self.assertAlmostEqual(row["touch_ask"], 300.15, 9)
        # [DÉRIVÉ] aller-retour = 10 - 2 x 1.25 = 7.5 bps ; 0.75 $ pour 1000 ; seuil AS = 3.75 bps
        self.assertAlmostEqual(row["rt_bps"], 7.5, 6)
        self.assertAlmostEqual(row["rt_per_1000"], 0.75, 6)
        self.assertAlmostEqual(row["as_breakeven"], 3.75, 6)
        # [MESURÉ] vol : r = ln(100.01 / 100) ou son opposé, |r| = 9.9995e-5 ; 7 intervalles de 5 s
        r = math.log(100.01 / 100.0)
        sigma = math.sqrt(7 * r * r / 35.0)  # variance par seconde
        self.assertAlmostEqual(row["sig_bps_sqrt_s"], sigma * 1e4, 9)
        self.assertAlmostEqual(row["vol_60s"], sigma * 1e4 * math.sqrt(60), 9)
        # tau* = (3.75 / sigma_bps)^2
        self.assertAlmostEqual(row["tau_star"], (3.75 / (sigma * 1e4)) ** 2, 6)

    def test_session_split(self):
        res = mm.analyse(self.build(1.0), 1.25)
        row = {(r["sym"], r["session"]): r for r in res["rows"]}[("X", 0)]
        self.assertEqual(row["n_book"], 2)
        self.assertAlmostEqual(row["spread_mean"], 4.0, 6)          # 0.04 / 100 = 4 bps
        self.assertAlmostEqual(row["rt_bps"], 1.5, 6)               # 4 - 2.5
        self.assertTrue(math.isnan(row["sig_bps_sqrt_s"]))          # pas de ticker hors séance : inconnu, pas 0

    def test_negative_round_trip_flagged(self):
        d = tempfile.mkdtemp()
        t0 = 1_791_158_400_000
        write(os.path.join(d, "2026-10-05"), "books.jsonl", [book(t0 + i * 1000, "B", 1, 99.998, 100.002) for i in range(3)])
        res = mm.analyse(d, 1.25)  # spread 0.4 bps < 2.5
        self.assertLess(res["rows"][0]["rt_bps"], 0)
        self.assertTrue(math.isnan(res["rows"][0]["tau_star"]))     # pas de seuil positif
        self.assertIn("aller-retour négatif", mm.report(res, 1.25, 3.0))

    def test_insufficient_data_banner(self):
        res = mm.analyse(self.build(1.0), 1.25)
        self.assertIn("DONNÉES INSUFFISANTES", mm.report(res, 1.25, 3.0))
        res = mm.analyse(self.build(5.0), 1.25)
        self.assertNotIn("DONNÉES INSUFFISANTES", mm.report(res, 1.25, 3.0))

    def test_gaps_excluded_from_volatility(self):
        pts = [(0.0, 100.0), (5.0, 100.01), (1000.0, 200.0), (1005.0, 200.02)]  # trou de 995 s ignoré
        sig, n = mm.realized_vol_per_sqrt_s(pts)
        self.assertEqual(n, 2)
        r1, r2 = math.log(100.01 / 100.0), math.log(200.02 / 200.0)
        self.assertAlmostEqual(sig, math.sqrt((r1 * r1 + r2 * r2) / 10.0), 12)

    def test_tolerates_truncated_line_and_empty_dir(self):
        d = tempfile.mkdtemp()
        os.makedirs(os.path.join(d, "2026-10-05"))
        with open(os.path.join(d, "2026-10-05", "books.jsonl"), "w", encoding="utf-8") as f:
            f.write(json.dumps(book(1_791_158_400_000, "X", 1, 99.95, 100.05)) + "\n")
            f.write('{"t": 17911584')  # ligne coupée par un arrêt brutal
        self.assertEqual(len(mm.analyse(d, 1.25)["rows"]), 1)
        self.assertEqual(mm.analyse(tempfile.mkdtemp(), 1.25)["rows"], [])


if __name__ == "__main__":
    unittest.main(verbosity=1)
