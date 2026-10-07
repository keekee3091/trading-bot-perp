"""
Gestion du risque pour perps : sizing, levier, Kelly, circuit breakers, exposition nette.

Reprend les briques du bot Up/Down :
  - Kelly glissant (fenetre de trades recents, ratio gain/perte reel)
  - cooldown apres perte, max pertes consecutives, verrous de perte/gain
  - plafond d'exposition (ici exposition NETTE signee, multi-actifs)

Adaptation perps : la mise n'est plus un montant d'USDC sur un token a [0,1] mais un
risque en % d'equity. Notionnel = risque_USDC / distance_SL ; marge = notionnel / levier.
Le levier est borne pour que la liquidation reste bien au-dela du stop.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, Tuple

from .models import ClosedTrade, Instrument, LONG, SHORT, sign


@dataclass
class SizeDecision:
    notional: float
    margin:   float
    leverage: float
    risk_usdc: float
    kelly_mult: float


class RiskManager:
    def __init__(self, cfg: dict, start_equity: float):
        self.cfg = cfg
        self.start_equity = start_equity
        self.session_pnl = 0.0
        self.day_pnl = 0.0
        self._day = None
        self.consec_losses = 0
        self.pause_until = 0.0
        self.halted = False
        self.halt_reason = ""
        self._hist_win: Deque[bool] = deque(maxlen=200)
        self._hist_pnl_pct: Deque[float] = deque(maxlen=200)
        self._net: Dict[str, float] = {}       # symbole -> notionnel signe
        self._entries: Deque[float] = deque()  # timestamps d'entrees (limite horaire)

    # ── Kelly ──────────────────────────────────────────────────────────────
    def kelly_mult(self) -> float:
        c = self.cfg
        if not c.get("kelly_enabled", True):
            return 1.0
        window = int(c.get("kelly_window", 30))
        if len(self._hist_win) < max(5, window // 2):
            return 1.0
        wins = list(self._hist_win)[-window:]
        pnls = list(self._hist_pnl_pct)[-window:]
        p = sum(wins) / len(wins)
        gains = [x for x in pnls if x > 0]
        losses = [-x for x in pnls if x < 0]
        if not gains or not losses:
            return 1.0
        b = (sum(gains) / len(gains)) / (sum(losses) / len(losses))
        f_star = p - (1 - p) / b
        lo = float(c.get("kelly_min_mult", 0.3))
        hi = float(c.get("kelly_max_mult", 1.5))
        if f_star <= 0:
            return lo
        return max(lo, min(hi, float(c.get("kelly_scaling", 0.5)) * f_star * 4))

    # ── Sizing ─────────────────────────────────────────────────────────────
    def choose_leverage(self, inst: Instrument, sl_pct: float) -> float:
        """Levier cible, plafonne pour garder la liquidation a >= liq_buffer_mult x la distance SL."""
        c = self.cfg
        target = float(c.get("leverage", 5))
        buf = float(c.get("liq_buffer_mult", 2.0))
        cap_liq = 1.0 / (buf * sl_pct + inst.mmr) if sl_pct > 0 else target
        return max(1.0, min(target, inst.max_leverage, cap_liq))

    def size(self, equity: float, inst: Instrument, sl_pct: float, price: float) -> SizeDecision | None:
        c = self.cfg
        km = self.kelly_mult()
        lev = self.choose_leverage(inst, sl_pct)
        risk = equity * float(c.get("risk_per_trade_pct", 0.01)) * km
        notional = risk / sl_pct if sl_pct > 0 else 0.0
        notional = min(notional,
                       float(c.get("max_notional_per_trade", 5000)),
                       equity * float(c.get("max_account_leverage", 3.0)))
        if notional < max(inst.min_notional, float(c.get("min_notional", 10))):
            return None
        margin = notional / lev
        if margin > equity * float(c.get("max_margin_pct", 0.5)):
            margin = equity * float(c.get("max_margin_pct", 0.5))
            notional = margin * lev
            if notional < inst.min_notional:
                return None
        return SizeDecision(notional, margin, lev, risk, km)

    # ── Exposition nette ───────────────────────────────────────────────────
    def set_exposure(self, symbol: str, side: str | None, notional: float = 0.0) -> None:
        if side is None:
            self._net.pop(symbol, None)
        else:
            self._net[symbol] = sign(side) * notional

    def net_exposure(self) -> float:
        return sum(self._net.values())

    def gross_exposure(self) -> float:
        return sum(abs(v) for v in self._net.values())

    # ── Autorisation d'entree ──────────────────────────────────────────────
    def can_enter(self, now: float, symbol: str, side: str, notional: float, equity: float) -> Tuple[bool, str]:
        c = self.cfg
        if self.halted:
            return False, f"halt:{self.halt_reason}"
        if now < self.pause_until:
            return False, "cooldown"
        max_hour = int(c.get("max_entries_per_hour", 0))
        if max_hour > 0:
            while self._entries and now - self._entries[0] > 3600:
                self._entries.popleft()
            if len(self._entries) >= max_hour:
                return False, "max_entries_per_hour"
        cap = float(c.get("max_net_exposure_pct", 0)) * equity
        if cap > 0:
            after = self.net_exposure() + sign(side) * notional
            if abs(after) > cap and abs(after) > abs(self.net_exposure()):
                return False, "net_exposure_cap"
        gcap = float(c.get("max_gross_exposure_pct", 0)) * equity
        if gcap > 0 and self.gross_exposure() + notional > gcap:
            return False, "gross_exposure_cap"
        return True, ""

    def on_entry(self, now: float) -> None:
        self._entries.append(now)

    # ── Suivi des resultats ────────────────────────────────────────────────
    def record_trade(self, t: ClosedTrade, now: float) -> None:
        c = self.cfg
        self.session_pnl += t.pnl
        day = int(now // 86400)
        if day != self._day:
            self._day, self.day_pnl = day, 0.0
        self.day_pnl += t.pnl
        self._hist_win.append(t.pnl > 0)
        self._hist_pnl_pct.append(t.pnl_pct)

        if t.pnl > 0:
            self.consec_losses = 0
            self.pause_until = max(self.pause_until, now + float(c.get("cooldown_after_win_s", 0)))
        else:
            self.consec_losses += 1
            self.pause_until = max(self.pause_until, now + float(c.get("cooldown_after_loss_s", 60)))
            mx = int(c.get("max_consecutive_losses", 3))
            if mx > 0 and self.consec_losses >= mx:
                self.pause_until = now + float(c.get("loss_streak_pause_s", 900))
                self.consec_losses = 0

        sess_lim = float(c.get("max_session_loss_pct", 0)) * self.start_equity
        if sess_lim > 0 and self.session_pnl <= -sess_lim:
            self.halted, self.halt_reason = True, "max_session_loss"
        day_lim = float(c.get("daily_loss_lock_pct", 0)) * self.start_equity
        if day_lim > 0 and self.day_pnl <= -day_lim:
            self.pause_until = max(self.pause_until, (self._day + 1) * 86400)
        prof_lim = float(c.get("daily_profit_lock_pct", 0)) * self.start_equity
        if prof_lim > 0 and self.day_pnl >= prof_lim:
            self.pause_until = max(self.pause_until, (self._day + 1) * 86400)
