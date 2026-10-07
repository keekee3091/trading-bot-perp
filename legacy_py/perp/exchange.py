"""
Interface d'execution + exchange papier (simulation fidele : spread, slippage, frais, funding, liquidation).

Le meme `PerpBot` tourne sur PaperExchange (backtest et paper live) et sur un exchange reel
(a brancher via `LiveExchange`, voir perp/live.py).
"""

from __future__ import annotations

from typing import Dict, List, Optional, Protocol

from .models import ClosedTrade, Instrument, LONG, SHORT, Position, Tick, sign


class Exchange(Protocol):
    positions: Dict[int, Position]

    def equity(self, prices: Dict[int, float] | None = None) -> float: ...
    def on_tick(self, inst: Instrument, tick: Tick) -> List[ClosedTrade]: ...
    def market_open(self, inst: Instrument, side: str, qty: float, leverage: float, tick: Tick) -> Optional[Position]: ...
    def market_close(self, inst: Instrument, tick: Tick, reason: str) -> Optional[ClosedTrade]:
        pos = self.positions.get(inst.iid)
        if pos is None:
            return None
        bid, ask = self._bid_ask(tick)
        fill = bid * (1 - self.slippage) if pos.side == LONG else ask * (1 + self.slippage)
        fee = pos.qty * fill * self._fee_rate(inst)
        entry_fee = pos.fees_paid
        pos.fees_paid += fee
        self.total_fees += fee
        # Isolation : la perte est plafonnee a la marge
        returned = max(0.0, pos.margin + pos.pnl(fill) - pos.funding_paid - fee)
        self.balance += returned
        return self._finish(pos, fill, tick.ts, reason, returned, entry_fee)

    def _finish(self, pos: Position, exit_price: float, ts: float, reason: str,
                returned: float, entry_fee: float) -> ClosedTrade:
        """PnL net = collateral recupere - (marge + frais d'entree) : frais et funding inclus."""
        net = returned - pos.margin - entry_fee
        t = ClosedTrade(
            symbol=pos.symbol, side=pos.side, entry_price=pos.entry_price, exit_price=exit_price,
            qty=pos.qty, leverage=pos.leverage, margin=pos.margin, pnl=net,
            pnl_pct=net / pos.margin if pos.margin > 0 else 0.0,
            fees=pos.fees_paid, funding=pos.funding_paid, reason=reason,
            held_s=ts - pos.opened_ts, opened_ts=pos.opened_ts, closed_ts=ts,
        )
        self.positions.pop(pos.iid, None)
        self.closed.append(t)
        return t
