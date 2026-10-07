"""
CLI : python main.py <commande>

  instruments              liste des perps disponibles (id, levier max, min notional)
  fetch  [--days N]        telecharge des bougies 1m vers data/<symbol>_<interval>.csv
  backtest [--csv F | --synthetic | --api --days N]
  paper                    paper trading en temps reel (polling REST), aucun ordre reel
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import time

import yaml

from perp import market_data
from perp.backtest import format_report, load_csv, run_backtest, synthetic
from perp.core import PerpBot
from perp.exchange import PaperExchange
from perp.models import Instrument
from perp.recorder import Recorder
from perp.risk import RiskManager


def load_config(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def cmd_instruments(args, cfg):
    for d in market_data.fetch_instruments():
        print(f"{d['instrument_id']:>4}  {d['symbol']:<14} lev<={d.get('max_leverage')}  "
              f"min_notional={d.get('min_notional')}  cat={d.get('category')}")


def cmd_fetch(args, cfg):
    inst = market_data.resolve_instrument(cfg["symbol"])
    start = int((time.time() - args.days * 86400) * 1000)
    rows = market_data.fetch_klines(inst.iid, args.interval, start)
    os.makedirs("data", exist_ok=True)
    path = f"data/{inst.symbol}_{args.interval}.csv"
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ts", "open", "high", "low", "close"])
        for ts, o, h, l, c in rows:
            w.writerow([int(ts * 1000), o, h, l, c])
    print(f"{len(rows)} bougies -> {path}")


def _inst_for_backtest(cfg, offline: bool) -> Instrument:
    if offline:
        return Instrument(iid=1, symbol=cfg["symbol"], max_leverage=20, min_notional=10)
    return market_data.resolve_instrument(cfg["symbol"])


def cmd_backtest(args, cfg):
    interval_s = 60
    if args.synthetic:
        candles = synthetic(args.n)
        inst = _inst_for_backtest(cfg, True)
        print(f"[synthetique {len(candles)} bougies : valide la plomberie, ne prouve aucun edge]")
    elif args.csv:
        candles = load_csv(args.csv)
        inst = _inst_for_backtest(cfg, args.offline)
    else:
        inst = market_data.resolve_instrument(cfg["symbol"])
        start = int((time.time() - args.days * 86400) * 1000)
        candles = market_data.fetch_klines(inst.iid, "1m", start)
    if not candles:
        sys.exit("aucune bougie")
    res = run_backtest(cfg, inst, candles, interval_s)
    print(format_report(res.metrics()))


def cmd_paper(args, cfg):
    inst = market_data.resolve_instrument(cfg["symbol"])
    equity0 = float(cfg.get("equity", 1000))
    rec = Recorder(mode="paper")
    ex = PaperExchange(equity0, cfg.get("slippage_pct", 0.0002), cfg.get("default_spread_pct", 0.0002),
                       cfg.get("taker_fee"))
    risk = RiskManager(cfg, equity0)

    def on_trade(t):
        rec.record(t)
        print(f"[{t.reason}] {t.side} {t.symbol} {t.entry_price:.2f}->{t.exit_price:.2f} pnl={t.pnl:+.2f}")

    bot = PerpBot(cfg, inst, ex, risk, on_trade=on_trade)
    print(f"Paper {inst.symbol} (iid {inst.iid}), equity {equity0}. Ctrl+C pour arreter.")
    poll = float(cfg.get("poll_seconds", 2))
    try:
        while True:
            try:
                tick = market_data.fetch_tick(inst.iid)
                if cfg.get("ref_symbol") and cfg.get("ref_weight", 0) > 0:
                    try:
                        tick.ref_price = market_data.fetch_binance_ref(cfg["ref_symbol"])
                    except Exception:
                        pass
                bot.on_tick(tick)
            except Exception as e:
                print("tick error:", e)
            time.sleep(poll)
    except KeyboardInterrupt:
        print(f"Equity finale {ex.equity():.2f}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default="config.yaml")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("instruments")
    f = sub.add_parser("fetch"); f.add_argument("--days", type=int, default=7); f.add_argument("--interval", default="1m")
    b = sub.add_parser("backtest")
    b.add_argument("--csv"); b.add_argument("--synthetic", action="store_true")
    b.add_argument("--offline", action="store_true", help="n'appelle pas l'API pour resoudre l'instrument")
    b.add_argument("--days", type=int, default=7); b.add_argument("--n", type=int, default=20000)
    sub.add_parser("paper")
    args = ap.parse_args()
    cfg = load_config(args.config)
    {"instruments": cmd_instruments, "fetch": cmd_fetch, "backtest": cmd_backtest, "paper": cmd_paper}[args.cmd](args, cfg)


if __name__ == "__main__":
    main()
