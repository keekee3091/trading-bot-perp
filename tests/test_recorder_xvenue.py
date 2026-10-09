"""Tests de tools/recorder_xvenue.py : appariement par nom d'actif, format des enregistrements, garde de débit, résilience, santé. Réseau simulé.
Aucun appel réel, aucune clé, aucune adresse. stdlib uniquement. Lancé par ctest.
"""
import json
import os
import sys
import tempfile
import unittest
import urllib.error

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import recorder_xvenue as rx  # noqa: E402

POLY = [{"symbol": "BTC-USD", "instrument_id": 6, "base_asset": "BTC", "category": "crypto"},
        {"symbol": "SP500-USD", "instrument_id": 1, "base_asset": "SP500", "category": "index"},
        {"symbol": "NAS100-USD", "instrument_id": 4, "base_asset": "NAS100", "category": "index"},
        {"symbol": "GOOG-USD", "instrument_id": 11, "base_asset": "GOOGL", "category": "equity"},
        {"symbol": "ZZZ-USD", "instrument_id": 99, "base_asset": "ZZZ", "category": "equity"}]


class Clock:
    def __init__(self, t=1_800_000_000.0):
        self.t = t

    def __call__(self):
        self.t += 0.05
        return self.t

    def sleep(self, s):
        self.t += s


def fake_poly(path, params=None):
    if path == "/v1/info/book":
        return {"instrument_id": params["instrument_id"], "bids": [[str(100 - i), "1"] for i in range(6)], "asks": [[str(101 + i), "1"] for i in range(6)],
                "timestamp": 1_800_000_000_100, "sequence": 7}
    if path == "/v1/info/tickers":
        return [{"symbol": "BTC-USD", "index_price": "100.5", "mark_price": "100.6", "funding_rate": "0.00001", "next_funding": 1, "timestamp": 2}]
    raise AssertionError(path)


def fake_hl(body):
    if body["type"] == "l2Book":
        return {"coin": body["coin"], "time": 1_800_000_000_120,
                "levels": [[{"px": str(100 - i), "sz": "1", "n": 1} for i in range(6)], [{"px": str(101 + i), "sz": "1", "n": 1} for i in range(6)]]}
    if body["type"] == "metaAndAssetCtxs":
        return [{"universe": [{"name": "BTC"}, {"name": "ETH"}]},
                [{"markPx": "100", "oraclePx": "99", "funding": "0.0000125", "openInterest": "5", "premium": "0.0001", "midPx": "100"}, {"markPx": "1"}]]
    raise AssertionError(body)


class Pairs(unittest.TestCase):
    def test_pairing_by_asset_name_and_unverified_flags(self):
        pairs = rx.build_pairs(POLY, ["BTC", "ETH"], ["xyz:SP500", "xyz:XYZ100", "xyz:GOOGL", "xyz:CL"], ["BTC", "SP500", "NAS100", "GOOGL", "WTIOIL", "ZZZ"])
        by = {p["base"]: p for p in pairs}
        self.assertEqual((by["BTC"]["hl_coin"], by["BTC"]["verified"]), ("BTC", True))
        self.assertEqual((by["SP500"]["hl_coin"], by["SP500"]["verified"]), ("xyz:SP500", True))
        self.assertEqual((by["GOOGL"]["hl_coin"], by["GOOGL"]["poly_symbol"]), ("xyz:GOOGL", "GOOG-USD"))     # apparié par base_asset, pas par symbole
        self.assertEqual((by["NAS100"]["hl_coin"], by["NAS100"]["verified"]), ("xyz:XYZ100", False))         # équivalence non établie : signalée
        self.assertNotIn("WTIOIL", by)                                                                       # absent de Polymarket dans cette fixture
        self.assertNotIn("ZZZ", by)                                                                          # pas d'équivalent Hyperliquid : non apparié


class Recording(unittest.TestCase):
    def rec(self, d, fetch_poly=fake_poly, fetch_hl=fake_hl, n=2):
        pairs = rx.build_pairs(POLY, ["BTC", "ETH"], ["xyz:SP500"], ["BTC", "SP500"])[:n]
        c = Clock()
        return rx.XRecorder(pairs, d, 7.0, fetch_poly, fetch_hl, c, c.sleep), c

    def test_one_cycle_record_format(self):
        with tempfile.TemporaryDirectory() as d:
            r, c = self.rec(d)
            for p in r.pairs:
                r.sample_pair(p)
            day = r.day_dir()
            with open(os.path.join(day, "pairs.jsonl"), encoding="utf-8") as f:
                rows = [json.loads(x) for x in f]
            self.assertEqual(len(rows), 2)
            x = rows[0]
            self.assertEqual(len(x["poly"]["bids"]), 5)                       # 5 niveaux conservés sur 6 reçus
            self.assertEqual(x["poly"]["bids"][0], [100.0, 1.0])
            self.assertEqual(x["hl"]["asks"][0], [101.0, 1.0])
            self.assertEqual((x["poly"]["srv"], x["hl"]["srv"]), (1_800_000_000_100, 1_800_000_000_120))
            self.assertLessEqual(x["poly"]["send"], x["poly"]["recv"])        # horodatage local avant l'envoi et à la réception
            self.assertLessEqual(x["hl"]["send"], x["hl"]["recv"])
            r.ctx()
            with open(os.path.join(day, "ctx.jsonl"), encoding="utf-8") as f:
                ctx = json.loads(f.readline())
            self.assertEqual(ctx["hl"]["BTC"]["oraclePx"], "99")
            self.assertEqual(ctx["poly"]["BTC-USD"]["index_price"], "100.5")
            r.clock_check(n=2)
            with open(os.path.join(day, "clock.jsonl"), encoding="utf-8") as f:
                clk = json.loads(f.readline())
            self.assertIn("hl_offset_ms", clk)
            self.assertGreater(clk["hl_rtt_ms"], 0)

    def test_network_errors_never_crash_and_429_backs_off(self):
        def bad_poly(path, params=None):
            raise urllib.error.HTTPError("u", 429, "Too Many Requests", {}, None)
        with tempfile.TemporaryDirectory() as d:
            r, c = self.rec(d, fetch_poly=bad_poly)
            t0 = c.t
            r.sample_pair(r.pairs[0])
            self.assertEqual(r.counts["errors"], 1)
            self.assertGreaterEqual(c.t - t0, 5.0)                            # attente après un 429
            self.assertEqual(r.counts["pairs"], 0)
            with open(os.path.join(r.day_dir(), "errors.log"), encoding="utf-8") as f:
                self.assertIn("HTTPError", f.read())

    def test_rate_budget_guard(self):
        self.assertAlmostEqual(rx.hl_weight_per_min(18, 7.0), 18 * 2 * 60 / 7.0 + 40, places=9)
        self.assertLess(rx.hl_weight_per_min(18, 7.0), rx.HL_WEIGHT_MAX)
        self.assertLessEqual(rx.poly_rps(18, 7.0), rx.POLY_RPS_MAX)
        self.assertGreater(rx.poly_rps(18, 6.0), rx.POLY_RPS_MAX)             # plus de 3 requêtes par seconde pour Polymarket : refusé
        with self.assertRaises(SystemExit):
            rx.XRecorder([{"base": str(i), "poly_id": i, "hl_coin": "X", "poly_symbol": "S", "verified": True} for i in range(18)], tempfile.gettempdir(), 6.0)


class Health(unittest.TestCase):
    def test_coverage_gaps_and_continuous_days(self):
        with tempfile.TemporaryDirectory() as d:
            period = 100.0                                   # attendu : 864 échantillons par jour et par paire
            for day, n, gap_at in (("2026-10-01", 864, None), ("2026-10-02", 864, None), ("2026-10-03", 300, None), ("2026-10-04", 864, 400)):
                os.makedirs(os.path.join(d, day))
                with open(os.path.join(d, day, "pairs.jsonl"), "w", encoding="utf-8") as f:
                    for pair in ("A", "B"):
                        t = 0.0
                        for i in range(n):
                            t += period if not (gap_at and i == gap_at) else 1000.0
                            f.write(json.dumps({"pair": pair, "poly": {"send": t * 1000}}) + "\n")
            h = rx.health(d, period=period, n_pairs=2)
            self.assertAlmostEqual(h["days"]["2026-10-01"]["coverage_median"], 1.0, places=9)
            self.assertAlmostEqual(h["days"]["2026-10-03"]["coverage_median"], 300 / 864, places=9)
            self.assertEqual(h["days"]["2026-10-04"]["max_gap_s"], 1000.0)
            self.assertEqual(h["continuous_days"], 2)        # 1 et 2 octobre bons ; le 3 manque de couverture ; le 4 a un trou de plus de 5 minutes


class Ntp(unittest.TestCase):
    def packet(self, t2, t3):
        import struct
        def enc(t):
            sec = int(t)
            return struct.pack("!II", sec + rx.NTP_UNIX, int((t - sec) * 2 ** 32))
        return bytes(32) + enc(t2) + enc(t3)

    def fake_socket(self, pkt):
        class S:
            def __init__(self, *a):
                self.sent = None

            def settimeout(self, t):
                pass

            def sendto(self, data, addr):
                self.sent = (data, addr)

            def recvfrom(self, n):
                return pkt, ("x", 123)

            def close(self):
                pass
        return S

    def test_sntp_offset_and_rtt_by_hand(self):
        # T1 = 1000.0 (envoi local), T2 = 1000.55 (réception serveur), T3 = 1000.56 (émission serveur), T4 = 1000.1 (réception locale)
        # décalage = ((T2 - T1) + (T3 - T4)) / 2 = (0.55 + 0.46) / 2 = 0.505 s ; aller-retour réseau = (T4 - T1) - (T3 - T2) = 0.1 - 0.01 = 0.09 s
        ticks = iter([1000.0, 1000.1])
        off, rtt = rx.ntp_offset("example.invalid", sock_factory=self.fake_socket(self.packet(1000.55, 1000.56)), clock=lambda: next(ticks))
        self.assertAlmostEqual(off, 505.0, delta=0.05)
        self.assertAlmostEqual(rtt, 90.0, delta=0.05)

    def test_request_is_a_client_sntp_packet(self):
        sent = {}

        class S(self.fake_socket(self.packet(1.0, 1.0))):
            def sendto(self, data, addr):
                sent["d"], sent["a"] = data, addr
        ticks = iter([0.0, 0.0])
        rx.ntp_offset("example.invalid", sock_factory=S, clock=lambda: next(ticks))
        self.assertEqual((len(sent["d"]), sent["d"][0], sent["a"][1]), (48, 0x1b, 123))      # LI 0, version 3, mode 3 ; port 123

    def test_clock_check_records_ntp_and_snapshot_age(self):
        with tempfile.TemporaryDirectory() as d:
            pairs = rx.build_pairs(POLY, ["BTC", "ETH"], ["xyz:SP500"], ["BTC"])
            c = Clock()
            r = rx.XRecorder(pairs, d, 7.0, fake_poly, fake_hl, c, c.sleep)
            r.ntp = lambda server: (-8.0, 25.0)
            r.clock_check(n=2)
            with open(os.path.join(r.day_dir(), "clock.jsonl"), encoding="utf-8") as f:
                rec = json.loads(f.readline())
            self.assertEqual((rec["ntp_offset_ms"], rec["ntp_rtt_ms"]), (-8.0, 25.0))
            self.assertAlmostEqual(rec["hl_snapshot_age_ms"], -rec["hl_offset_ms"], places=9)

    def test_health_ntp_range_by_hand(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "2026-10-09"))
            with open(os.path.join(d, "2026-10-09", "pairs.jsonl"), "w", encoding="utf-8") as f:
                f.write(json.dumps({"pair": "A", "poly": {"send": 1000.0}}) + "\n")
            with open(os.path.join(d, "2026-10-09", "clock.jsonl"), "w", encoding="utf-8") as f:
                for o in (-5.0, -12.0, -8.0):
                    f.write(json.dumps({"hl_offset_ms": -600.0, "poly_offset_ms": -150.0, "ntp_offset_ms": o}) + "\n")
            h = rx.health(d, 7.0, 1)
            self.assertEqual((h["ntp_offset_range_ms"], h["ntp_offset_max_abs_ms"], h["ntp_n"]), (7.0, 12.0, 3))
            self.assertEqual(h["snapshot_age_median_ms"], {"hl": 600.0, "poly": 150.0})      # anciens enregistrements sans champ d'âge : repli sur -décalage


class NoSecrets(unittest.TestCase):
    def test_no_credentials_or_addresses_in_source(self):
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools", "recorder_xvenue.py"), encoding="utf-8") as f:
            src = f.read().lower()
        for bad in ("@gmail", "private_key", "api_key", "authorization"):
            self.assertNotIn(bad, src)


if __name__ == "__main__":
    unittest.main()
