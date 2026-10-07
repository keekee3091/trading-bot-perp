"""
Sorties de position pour perps : stop loss, take profit, trailing, time exit, garde-fou liquidation.

Tous les seuils sont exprimes en % de mouvement du prix SOUS-JACENT (pas en % de la marge),
pour rester independants du levier. Un SL de 0.6 % a 5x = 3 % de la marge.

Lecon du bot Up/Down : les stop-loss serres etaient le principal poids sur le Sharpe.
D'ou : SL dimensionne sur la volatilite (sl_vol_mult), periode de grace min_hold avec
SL d'urgence elargi, et sortie temporelle (time exit) plutot que stop systematique.
"""

from __future__ import annotations

from typing import Optional

from .models import LONG, Position, sign


class PositionManager:
    def __init__(self, cfg: dict):
        self.cfg = cfg

    def init_levels(self, pos: Position, sl_pct: float, tp_pct: float) -> None:
        s = sign(pos.side)
        pos.sl_price = pos.entry_price * (1 - s * sl_pct)
        pos.tp_price = pos.entry_price * (1 + s * tp_pct)
        pos.high_water = pos.entry_price
        pos.trail_active = False
        pos.trail_price = 0.0

    def check_exits(self, pos: Position, price: float, now: float) -> Optional[str]:
        c = self.cfg
        s = sign(pos.side)
        age = now - pos.opened_ts
        pnl_pct = pos.pnl_pct_underlying(price)

        # 1. Garde-fou liquidation : on sort AVANT la liquidation (qui coute la marge + frais de liquidation)
        guard = float(c.get("liq_guard_pct", 0.002))
        if pos.liq_distance_pct(price) <= guard:
            return "liq_guard"

        # 2. Trailing stop
        act = float(c.get("trailing_activation_pct", 0))
        dist = float(c.get("trailing_distance_pct", 0))
        if act > 0 and dist > 0:
            if not pos.trail_active:
                if pnl_pct >= act:
                    pos.trail_active = True
                    pos.high_water = price
                    pos.trail_price = price * (1 - s * dist)
            else:
                if (price - pos.high_water) * s > 0:
                    pos.high_water = price
                    pos.trail_price = price * (1 - s * dist)
                if (price - pos.trail_price) * s <= 0:
                    return "trailing_stop"

        # 3. Stop loss (grace min_hold : seul un SL d'urgence elargi s'applique)
        min_hold = float(c.get("min_hold_seconds", 0))
        sl_dist = abs(pos.entry_price - pos.sl_price) / pos.entry_price
        if age < min_hold:
            emergency = pos.entry_price * (1 - s * sl_dist * float(c.get("emergency_sl_mult", 1.5)))
            if (price - emergency) * s <= 0:
                return "stop_loss_emergency"
        elif (price - pos.sl_price) * s <= 0:
            return "stop_loss"

        # 4. Take profit
        if (price - pos.tp_price) * s >= 0:
            return "take_profit"

        # 5. Sorties temporelles
        te = float(c.get("time_exit_seconds", 0))
        if te > 0 and age >= te and pnl_pct >= float(c.get("time_exit_min_pnl_pct", 0.0)):
            return "time_exit"
        mh = float(c.get("max_hold_seconds", 0))
        if mh > 0 and age >= mh:
            return "max_hold"
        return None
