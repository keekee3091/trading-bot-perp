"""
Backtest sur bougies : rejoue le MEME PerpBot sur PaperExchange.

Chaque bougie OHLC est decoupee en 4 ticks (o, puis low/high selon la couleur, puis c) pour que
stops, liquidations et trailing voient les extremes intra-bougie. Hypothese de ce chemin : bougie
haussiere = o,l,h,c ; baissiere = o,h,l,c (approximation, a garder en tete pour la lecture des SL).

Metriques : Sharpe annualise sur la courbe d'equity par bougie, max drawdown, profit factor,
repartition par raison de sortie (c'est LA vue qui avait revele le poids des stop-loss).
"""

from __future__ import annotations

import csv
import math
import random
from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple

from .core import PerpBot
from .exchange import PaperExchange
from .models import ClosedTrade, Instrument, Tick
from .risk import RiskManager

Candle = Tuple[float, float, float, float, float]   # ts_s, o, h, l, c


def load_csv(path: str) -> List[Candle]:
    """CSV avec colonnes ts(ms ou s),open,high,low,close[,volume]."""
    out: List[Candle] = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            ts = float(row["ts"])
            ts = ts / 1000 if ts > 1e11 else ts
            out.append((ts, float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])))
    return sorted(out)


def synthetic(n: int = 20000, interval_s: int = 60, start: float = 100.0, seed: int = 7,
              drift_regimes: bool = True) -> List[Candle]:
    """Marche synthetique GBM avec regimes de tendance (pour tests et demo, PAS pour juger une strategie)."""
    rnd = random.Random(seed)
    ts, px, out = 1_760_000_000.0, start, []
    vol = 0.0006
    mu = 0.0
    for i in range(n):
        if drift_regimes and i % 360 == 0:
            mu = rnd.choice([-1, 0, 0, 1]) * 0.00015
        o = px
        path = [o]
        for _ in range(4):
            path.append(path[-1] * math.exp(mu / 4 + rnd.gauss(0, vol / 2)))
        c = path[-1]
        h, l = max(path), min(path)
        out.append((ts, o, h, l, c))
        px, ts = c, ts + interval_s
    return out


def candle_ticks(c: Candle, interval_s: int, funding_rate: float) -> Iterable[Tick]:
    ts, o, h, l, cl = c
    seq = [o, l, h, cl] if cl >= o else [o, h, l, cl]
    step = interval_s / 4
    for k, px in enumerate(seq):
        yield Tick(ts=ts + k * step, mark=px, index=px, funding_rate=funding_rate)


@dataclass
class BacktestResult:
    trades: List[ClosedTrade]
    equity_curve: List[float]
    start_equity: float
    end_equity: float
    fees: float
    funding: float
    liquidations: int
    skips: Dict[str, int]
    interval_s: int

    def metrics(self) -> dict:
        t = self.trades
        n = len(t)
        wins = [x.pnl for x in t if x.pnl > 0]
        losses = [-x.pnl for x in t if x.pnl <= 0]
        eq = self.equity_curve
        rets = [(eq[i] / eq[i - 1] - 1) for i in range(1, len(eq)) if eq[i - 1] > 0]
        if len(rets) > 2:
            m = sum(rets) / len(rets)
            sd = math.sqrt(sum((r - m) ** 2 for r in rets) / (len(rets) - 1))
            periods_per_year = 365 * 86400 / self.interval_s
            sharpe = (m / sd) * math.sqrt(periods_per_year) if sd > 0 else 0.0
        else:
            sharpe = 0.0
        peak, mdd = eq[0], 0.0
        for v in eq:
            peak = max(peak, v)
            mdd = max(mdd, (peak - v) / peak if peak > 0 else 0)
        by_reason: Dict[str, dict] = {}
        for x in t:
            r = by_reason.setdefault(x.reason, {"n": 0, "pnl": 0.0, "wins": 0})
            r["n"] += 1
            r["pnl"] += x.pnl
            r["wins"] += x.pnl > 0
        return {
            "trades": n,
            "win_rate": len(wins) / n if n else 0.0,
            "pnl": self.end_equity - self.start_equity,
            "return_pct": (self.end_equity / self.start_equity - 1) * 100,
            "sharpe": sharpe,
            "max_drawdown_pct": mdd * 100,
            "profit_factor": (sum(wins) / sum(losses)) if losses and sum(losses) > 0 else float("inf") if wins else 0.0,
            "avg_win": sum(wins) / len(wins) if wins else 0.0,
            "avg_loss": -sum(losses) / len(losses) if losses else 0.0,
            "fees": self.fees,
            "funding": self.funding,
            "liquidations": self.liquidations,
            "avg_hold_s": sum(x.held_s for x in t) / n if n else 0.0,
            "by_reason": by_reason,
            "skips": self.skips,
        }


def run_backtest(cfg: dict, inst: Instrument, candles: List[Candle], interval_s: int = 60) -> BacktestResult:
    bt = cfg.get("backtest", {})
    equity0 = float(cfg.get("equity", 1000))
    ex = PaperExchange(
        balance=equity0,
        slippage_pct=float(cfg.get("slippage_pct", 0.0002)),
        default_spread_pct=float(cfg.get("default_spread_pct", 0.0002)),
        taker_fee=cfg.get("taker_fee"),
    )
    risk = RiskManager(cfg, equity0)
    bot = PerpBot(cfg, inst, ex, risk)
    funding = float(bt.get("funding_rate_per_hour", 0.00001))
    curve = [equity0]
    for c in candles:
        for tick in candle_ticks(c, interval_s, funding):
            bot.on_tick(tick)
        curve.append(ex.equity({inst.iid: c[4]}))
    # fermeture de fin de test au dernier prix
    last = candles[-1]
    if inst.iid in ex.positions:
        ex.market_close(inst, Tick(ts=last[0] + interval_s, mark=last[4], index=last[4]), "end_of_test")
        curve[-1] = ex.equity()
    return BacktestResult(ex.closed, curve, equity0, ex.equity(), ex.total_fees, ex.total_funding,
                          ex.liquidations, bot.skips, interval_s)


def format_report(m: dict) -> str:
    inf = m["profit_factor"]
    lines = [
        f"Trades {m['trades']} | win rate {m['win_rate']:.1%} | PnL {m['pnl']:+.2f} ({m['return_pct']:+.2f}%)",
        f"Sharpe {m['sharpe']:.2f} | max DD {m['max_drawdown_pct']:.2f}% | profit factor {'inf' if inf == float('inf') else f'{inf:.2f}'}",
        f"Gain moyen {m['avg_win']:+.2f} | perte moyenne {m['avg_loss']:+.2f} | tenue moyenne {m['avg_hold_s']:.0f}s",
        f"Frais {m['fees']:.2f} | funding {m['funding']:+.2f} | liquidations {m['liquidations']}",
        "Sorties :",
    ]
    for r, v in sorted(m["by_reason"].items(), key=lambda kv: kv[1]["pnl"]):
        lines.append(f"  {r:<20} n={v['n']:<5} pnl={v['pnl']:+9.2f}  win={v['wins']/v['n']:.0%}")
    top = sorted(m["skips"].items(), key=lambda kv: -kv[1])[:6]
    lines.append("Filtres (top) : " + ", ".join(f"{k}={v}" for k, v in top))
    return "\n".join(lines)
