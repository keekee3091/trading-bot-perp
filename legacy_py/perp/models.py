"""
Modeles de base pour les perps Polymarket.

Differences cles avec le bot binaire (Up/Down) :
  - le payoff n'est plus borne [0, 1] : PnL lineaire en prix x quantite x levier
  - il y a une liquidation (prix de liquidation), du funding horaire et des frais maker/taker
  - la "probabilite" ne se compare plus a un prix de marche : on la compare a la
    probabilite de breakeven (SL, TP, frais, funding), voir breakeven_prob()
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

LONG = "long"
SHORT = "short"


def sign(side: str) -> int:
    return 1 if side == LONG else -1


@dataclass(frozen=True)
class Instrument:
    """Parametres d'un perp (a charger depuis GET /v1/info/instruments)."""
    iid:            int
    symbol:         str            # ex. "BTC-USD"
    max_leverage:   float = 10.0
    min_notional:   float = 10.0
    price_decimals: int   = 2
    qty_decimals:   int   = 4
    liquidation_fee: float = 0.005   # fraction du notionnel liquide
    taker_fee:      float = 0.0004   # 0.04 % tier 0
    maker_fee:      float = 0.000125 # 0.0125 % tier 0
    # Taux de marge de maintenance. Hypothese par defaut : 0.5 / max_leverage.
    # A remplacer par les risk_tiers reels de l'instrument.
    maintenance_margin_rate: float = 0.0

    @property
    def mmr(self) -> float:
        if self.maintenance_margin_rate > 0:
            return self.maintenance_margin_rate
        return 0.5 / max(self.max_leverage, 1.0)

    @staticmethod
    def from_api(d: dict) -> "Instrument":
        return Instrument(
            iid=int(d["instrument_id"]),
            symbol=d["symbol"],
            max_leverage=float(d.get("max_leverage", 10)),
            min_notional=float(d.get("min_notional", 10)),
            price_decimals=int(d.get("price_decimals", 2)),
            qty_decimals=int(d.get("quantity_decimals", 4)),
            liquidation_fee=float(d.get("liquidation_fee", 0.005)),
        )

    def round_qty(self, qty: float) -> float:
        f = 10 ** self.qty_decimals
        return int(qty * f) / f   # arrondi vers le bas : on ne depasse jamais la marge

    def round_price(self, p: float) -> float:
        return round(p, self.price_decimals)


@dataclass
class Tick:
    """Snapshot de marche. bid/ask peuvent etre 0 : l'exchange applique alors un spread par defaut."""
    ts:           float          # secondes epoch
    mark:         float
    index:        float = 0.0
    bid:          float = 0.0
    ask:          float = 0.0
    funding_rate: float = 0.0    # taux horaire (positif : les longs paient les shorts)
    ref_price:    float = 0.0    # prix de reference externe optionnel (ex. Binance)

    @property
    def px(self) -> float:
        return self.index or self.mark


@dataclass
class Position:
    iid:         int
    symbol:      str
    side:        str             # LONG / SHORT
    entry_price: float
    qty:         float           # en unites de base, toujours > 0
    leverage:    float
    margin:      float           # collateral isole bloque
    mmr:         float
    opened_ts:   float = field(default_factory=time.time)
    funding_paid: float = 0.0    # cumul, positif = paye
    fees_paid:    float = 0.0
    # Gestion de sortie (renseignes par le PositionManager)
    sl_price:    float = 0.0
    tp_price:    float = 0.0
    high_water:  float = 0.0     # meilleur prix favorable depuis l'entree
    trail_active: bool = False
    trail_price: float = 0.0
    window_tag:  str = ""

    @property
    def notional(self) -> float:
        return self.qty * self.entry_price

    @property
    def liq_price(self) -> float:
        """Liquidation en marge isolee (hors frais) : equity = maintenance margin."""
        if self.side == LONG:
            return self.entry_price * (1.0 - 1.0 / self.leverage + self.mmr)
        return self.entry_price * (1.0 + 1.0 / self.leverage - self.mmr)

    def pnl(self, price: float) -> float:
        return sign(self.side) * self.qty * (price - self.entry_price)

    def pnl_pct_underlying(self, price: float) -> float:
        return sign(self.side) * (price - self.entry_price) / self.entry_price

    def equity(self, price: float) -> float:
        return self.margin + self.pnl(price) - self.funding_paid

    def liq_distance_pct(self, price: float) -> float:
        """Distance relative (positive) entre le prix courant et la liquidation."""
        if self.side == LONG:
            return (price - self.liq_price) / price
        return (self.liq_price - price) / price


@dataclass
class ClosedTrade:
    symbol:      str
    side:        str
    entry_price: float
    exit_price:  float
    qty:         float
    leverage:    float
    margin:      float
    pnl:         float          # net : frais et funding inclus
    pnl_pct:     float          # sur la marge engagee
    fees:        float
    funding:     float
    reason:      str
    held_s:      float
    opened_ts:   float = 0.0
    closed_ts:   float = 0.0


@dataclass
class Signal:
    side:        str            # LONG / SHORT
    probability: float
    z_score:     float
    volatility:  float          # vol relative ramenee a l'horizon du lookback
    price:       float


def breakeven_prob(sl_pct: float, tp_pct: float, cost_pct: float) -> float:
    """
    Probabilite minimale de toucher le TP avant le SL pour avoir une esperance nulle,
    en comptant les couts aller-retour (frais + slippage + funding estime), tous en
    fraction du prix sous-jacent :
        p*(tp - c) - (1-p)*(sl + c) = 0  =>  p = (sl + c) / (sl + tp)
    """
    denom = sl_pct + tp_pct
    if denom <= 0:
        return 1.0
    return min(1.0, max(0.0, (sl_pct + cost_pct) / denom))
