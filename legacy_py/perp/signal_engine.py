"""
Signal directionnel LONG/SHORT pour perps.

Meme logique que le bot Up/Down :
  1. rendement sur `lookback_seconds`
  2. normalise par la volatilite recente -> z-score
  3. sigmoide : P(hausse) = sigmoid(sensitivity * z)
  4. fusion optionnelle avec un prix de reference externe (ex. Binance) 40/60

Adaptation perps : pas de prix de marche binaire a fusionner (le 15 % "consensus Polymarket"
disparait). A la place, un biais de funding optionnel : un funding tres positif signale un
marche long-encombre (leger biais baissier), tres negatif l'inverse (voir `funding_bias`).
"""

from __future__ import annotations

import math
from collections import deque
from typing import Deque, Optional, Tuple

from .models import LONG, SHORT, Signal

MIN_VOL = 1e-5


def sigmoid(x: float) -> float:
    x = max(-500.0, min(500.0, x))
    return 1.0 / (1.0 + math.exp(-x))


class PriceHistory:
    """Historique glissant (ts, prix) avec echantillonnage minimal entre points."""

    def __init__(self, max_seconds: float = 3600.0, min_step: float = 0.0):
        self._d: Deque[Tuple[float, float]] = deque()
        self._max = max_seconds
        self._min_step = min_step

    def add(self, ts: float, price: float) -> None:
        if price <= 0:
            return
        if self._d and ts - self._d[-1][0] < self._min_step:
            self._d[-1] = (self._d[-1][0], price)   # on rafraichit le dernier point
        else:
            self._d.append((ts, price))
        while self._d and ts - self._d[0][0] > self._max:
            self._d.popleft()

    def __len__(self) -> int:
        return len(self._d)

    @property
    def last(self) -> Optional[float]:
        return self._d[-1][1] if self._d else None

    def price_ago(self, now: float, seconds: float) -> Optional[float]:
        """Dernier prix observe a ou avant now - seconds ; None si historique trop court."""
        target = now - seconds
        if not self._d or self._d[0][0] > target:
            return None
        best = None
        for ts, p in self._d:
            if ts <= target:
                best = p
            else:
                break
        return best

    def window(self, now: float, seconds: float):
        return [(t, p) for t, p in self._d if now - t <= seconds]


def rolling_vol(points) -> float:
    """Ecart-type des rendements relatifs point-a-point (filtre les rendements nuls)."""
    if len(points) < 3:
        return MIN_VOL
    rets = []
    for i in range(1, len(points)):
        a, b = points[i - 1][1], points[i][1]
        if a > 0 and b != a:
            rets.append((b - a) / a)
    if len(rets) < 2:
        return MIN_VOL
    m = sum(rets) / len(rets)
    var = sum((r - m) ** 2 for r in rets) / len(rets)
    return max(math.sqrt(var), MIN_VOL)


class SignalEngine:
    def __init__(
        self,
        threshold: float = 0.7,
        lookback_seconds: float = 300.0,
        vol_window_seconds: float = 900.0,
        sensitivity: float = 1.5,
        ref_weight: float = 0.6,
        z_cap: float = 4.0,
        funding_bias: float = 0.0,
    ):
        self.threshold = threshold
        self.lookback = lookback_seconds
        self.vol_window = vol_window_seconds
        self.sensitivity = sensitivity
        self.ref_weight = ref_weight
        self.z_cap = z_cap
        self.funding_bias = funding_bias

    def _z(self, hist: PriceHistory, now: float) -> Optional[Tuple[float, float, float]]:
        """Retourne (z, vol a l'horizon du lookback, prix courant)."""
        ago = hist.price_ago(now, self.lookback)
        cur = hist.last
        if ago is None or cur is None or ago <= 0:
            return None
        pts = hist.window(now, self.vol_window)
        if len(pts) < 5:
            return None
        vol = rolling_vol(pts)
        # La vol est par pas d'echantillonnage ; on la ramene a l'horizon du lookback (racine du temps).
        steps = max(1.0, self.lookback / max(1e-9, (pts[-1][0] - pts[0][0]) / max(1, len(pts) - 1)))
        horizon_vol = vol * math.sqrt(steps)
        ret = (cur - ago) / ago
        z = ret / horizon_vol if horizon_vol > 0 else 0.0
        return z, horizon_vol, cur

    def compute(
        self,
        now: float,
        hist: PriceHistory,
        ref_hist: Optional[PriceHistory] = None,
        funding_rate: float = 0.0,
    ) -> Optional[Signal]:
        base = self._z(hist, now)
        if base is None:
            return None
        z, vol, price = base
        if ref_hist is not None:
            r = self._z(ref_hist, now)
            if r is not None:
                z = (1 - self.ref_weight) * z + self.ref_weight * r[0]
        # Biais funding : funding positif (longs paient) -> on retire un peu de z
        z -= self.funding_bias * funding_rate * 1e4 / 10.0
        z = max(-self.z_cap, min(self.z_cap, z))
        p_up = sigmoid(self.sensitivity * z)
        if p_up >= self.threshold:
            return Signal(LONG, p_up, z, vol, price)
        if (1 - p_up) >= self.threshold:
            return Signal(SHORT, 1 - p_up, z, vol, price)
        return None
