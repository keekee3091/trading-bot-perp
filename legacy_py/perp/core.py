"""
PerpBot : machine a etats par instrument, pilotee tick par tick (identique en backtest, paper et live).

    IDLE -> HOLDING -> IDLE

(ENTERING/EXITING du bot Up/Down disparaissent : les ordres marche IOC sont synchrones cote
exchange papier ; l'adaptateur live gerera les etats intermediaires.)

Pipeline d'entree : signal -> filtres (spread, z-score, edge vs breakeven) -> sizing risque
-> controle d'exposition nette -> ordre marche. Sortie : PositionManager.
"""

from __future__ import annotations

import math
from enum import Enum
from typing import Callable, List, Optional

from .exchange import Exchange
from .models import ClosedTrade, Instrument, Signal, Tick, breakeven_prob, sign
from .position_manager import PositionManager
from .risk import RiskManager
from .signal_engine import PriceHistory, SignalEngine


class State(Enum):
    IDLE = "IDLE"
    HOLDING = "HOLDING"


class PerpBot:
    def __init__(
        self,
        cfg: dict,
        inst: Instrument,
        exchange: Exchange,
        risk: RiskManager,
        on_trade: Optional[Callable[[ClosedTrade], None]] = None,
    ):
        self.cfg = cfg
        self.inst = inst
        self.ex = exchange
        self.risk = risk
        self.on_trade = on_trade
        self.pm = PositionManager(cfg)
        self.hist = PriceHistory(max_seconds=3600, min_step=float(cfg.get("sample_seconds", 5)))
        self.ref_hist = PriceHistory(max_seconds=3600, min_step=float(cfg.get("sample_seconds", 5)))
        self.engine = SignalEngine(
            threshold=cfg.get("signal_threshold", 0.7),
            lookback_seconds=cfg.get("signal_lookback_seconds", 300),
            vol_window_seconds=cfg.get("vol_window_seconds", 900),
            sensitivity=cfg.get("signal_sensitivity", 1.5),
            ref_weight=cfg.get("ref_weight", 0.6),
            funding_bias=cfg.get("funding_bias", 0.0),
        )
        self.state = State.IDLE
        self.last_skip = ""
        self.skips: dict[str, int] = {}

    # ── Helpers ────────────────────────────────────────────────────────────
    def _skip(self, why: str) -> None:
        self.last_skip = why
        self.skips[why] = self.skips.get(why, 0) + 1

    def _in_trading_hours(self, ts: float) -> bool:
        s, e = self.cfg.get("trading_hours_utc_start"), self.cfg.get("trading_hours_utc_end")
        if s is None or e is None:
            return True
        h = (ts % 86400) / 3600
        return (s <= h < e) if s <= e else (h >= s or h < e)

    def round_trip_cost_pct(self, tick: Tick, side: str) -> float:
        """Cout aller-retour en fraction du prix : frais taker x2, slippage x2, demi-spread x2, funding estime."""
        fee = 2 * self.inst.taker_fee if self.cfg.get("taker_fee") is None else 2 * float(self.cfg["taker_fee"])
        slip = 2 * float(self.cfg.get("slippage_pct", 0.0002))
        spread = float(self.cfg.get("default_spread_pct", 0.0002))
        if tick.bid and tick.ask and tick.px > 0:
            spread = (tick.ask - tick.bid) / tick.px
        hold_h = float(self.cfg.get("max_hold_seconds", 900)) / 3600
        funding = max(0.0, sign(side) * tick.funding_rate) * hold_h
        return fee + slip + spread + funding

    # ── Boucle principale ──────────────────────────────────────────────────
    def on_tick(self, tick: Tick) -> List[ClosedTrade]:
        out: List[ClosedTrade] = []
        self.hist.add(tick.ts, tick.px)
        if tick.ref_price:
            self.ref_hist.add(tick.ts, tick.ref_price)

        for t in self.ex.on_tick(self.inst, tick):     # funding + liquidation
            out.append(t)
            self._after_close(t, tick)

        pos = self.ex.positions.get(self.inst.iid)
        if pos is not None:
            self.state = State.HOLDING
            reason = self.pm.check_exits(pos, tick.px, tick.ts)
            if reason:
                t = self.ex.market_close(self.inst, tick, reason)
                if t:
                    out.append(t)
                    self._after_close(t, tick)
        else:
            self.state = State.IDLE
            self._try_enter(tick)
        return out

    def _after_close(self, t: ClosedTrade, tick: Tick) -> None:
        self.risk.set_exposure(self.inst.symbol, None)
        self.risk.record_trade(t, tick.ts)
        self.state = State.IDLE
        if self.on_trade:
            self.on_trade(t)

    # ── Entree ─────────────────────────────────────────────────────────────
    def _try_enter(self, tick: Tick) -> None:
        c = self.cfg
        if not self._in_trading_hours(tick.ts):
            return self._skip("hours")
        sig = self.engine.compute(
            tick.ts, self.hist, self.ref_hist if len(self.ref_hist) else None, tick.funding_rate
        )
        if sig is None:
            return self._skip("no_signal")
        if abs(sig.z_score) < float(c.get("min_z_score", 0.0)):
            return self._skip("z_low")
        if tick.bid and tick.ask:
            spr = (tick.ask - tick.bid) / tick.px
            if spr > float(c.get("max_spread_pct", 0.001)):
                return self._skip("spread")

        # Stop dimensionne sur la vol : jamais plus serre que sl_pct_floor
        sl_pct = max(float(c.get("sl_pct_floor", 0.003)), float(c.get("sl_vol_mult", 1.0)) * sig.volatility)
        sl_pct = min(sl_pct, float(c.get("sl_pct_cap", 0.03)))
        tp_pct = sl_pct * float(c.get("tp_rr", 1.5))

        # Edge : probabilite du signal vs probabilite de breakeven apres couts
        cost = self.round_trip_cost_pct(tick, sig.side)
        be = breakeven_prob(sl_pct, tp_pct, cost)
        if sig.probability - be < float(c.get("min_edge", 0.05)):
            return self._skip("edge")

        equity = self.ex.equity({self.inst.iid: tick.px})
        size = self.risk.size(equity, self.inst, sl_pct, tick.px)
        if size is None:
            return self._skip("size")
        ok, why = self.risk.can_enter(tick.ts, self.inst.symbol, sig.side, size.notional, equity)
        if not ok:
            return self._skip(why)

        qty = self.inst.round_qty(size.notional / tick.px)
        pos = self.ex.market_open(self.inst, sig.side, qty, size.leverage, tick)
        if pos is None:
            return self._skip("rejected")
        self.pm.init_levels(pos, sl_pct, tp_pct)
        self.risk.set_exposure(self.inst.symbol, pos.side, pos.notional)
        self.risk.on_entry(tick.ts)
        self.state = State.HOLDING
