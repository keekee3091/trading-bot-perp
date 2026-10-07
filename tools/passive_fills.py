"""Simulateur de fills passifs (post-only) à partir des trades publics du perp, bornes optimiste et conservatrice.

Le carnet n'a pas d'historique : le meilleur bid (achat) est approché par le dernier trade d'un agresseur VENDEUR des 5 dernières minutes,
le meilleur ask (vente) par le dernier trade d'un agresseur ACHETEUR (proxy, déclaré). Un ordre limite d'achat au prix p est servi par un
agresseur vendeur qui imprime à p ou en dessous (borne OPTIMISTE, file nulle) ou STRICTEMENT en dessous après que `Q` de notionnel
qualifiant ait été consommé devant nous (borne CONSERVATRICE, file exprimée en notionnel, pas en unités) ; la vente est symétrique.
`side=long` du fichier de trades = agresseur acheteur (mesuré). Fill au prix limite. Pas de fill partiel (ordres de 1 000 de notionnel).
Coûts : maker 1.25 bps par côté ; taker 4 bps + 2 bps de slippage par côté (le prix imprimé inclut déjà le franchissement du spread) ; funding réel.
stdlib uniquement.
"""
import bisect

MAKER_BPS, TAKER_BPS, SLIP_BPS = 1.25, 4.0, 2.0
LOOKBACK_MS = 300_000
TAKER_DELAY_MS = 1000
TAKER_WAIT_MS = 300_000


class Book:
    """Trades d'un instrument : lignes (ts, side(+1 acheteur / -1 vendeur), notionnel, prix, quantité) triées par temps."""

    def __init__(self, rows):
        self.t = {1: [], -1: []}
        self.p = {1: [], -1: []}
        self.n = {1: [], -1: []}
        for ts, s, nt, px, _q in rows:
            self.t[s].append(ts)
            self.p[s].append(px)
            self.n[s].append(nt)


def ref_price(book, side, t0, lookback=LOOKBACK_MS):
    """Proxy du meilleur prix de notre côté à t0 : dernier trade de l'agresseur opposé dans les `lookback` ms avant t0 (inclus)."""
    opp = -side
    j = bisect.bisect_right(book.t[opp], t0) - 1
    if j >= 0 and book.t[opp][j] >= t0 - lookback:
        return book.p[opp][j]
    return None


def passive_fill(book, side, p, t0, t1, bound, queue=0.0):
    """Instant du fill d'un ordre limite posté à t0, valable jusqu'à t1 inclus, ou None. bound : 'opt' ou 'cons'."""
    opp = -side
    ts, ps, ns = book.t[opp], book.p[opp], book.n[opp]
    j = bisect.bisect_right(ts, t0)
    cum = 0.0
    while j < len(ts) and ts[j] <= t1:
        beyond = (ps[j] <= p) if side > 0 else (ps[j] >= p)
        strict = (ps[j] < p) if side > 0 else (ps[j] > p)
        if bound == "opt" and beyond:
            return ts[j]
        if bound == "cons" and strict:
            cum += ns[j]
            if cum >= queue:
                return ts[j]
        j += 1
    return None


def taker_fill(book, side, t, wait=TAKER_WAIT_MS):
    """Premier trade imprimé par un agresseur de notre sens au moins 1 s après t et au plus `wait` ms après : (instant, prix) ou None."""
    j = bisect.bisect_left(book.t[side], t + TAKER_DELAY_MS)
    if j < len(book.t[side]) and book.t[side][j] <= t + wait:
        return book.t[side][j], book.p[side][j]
    # un ordre taker s'exécute toujours contre le carnet : sans trade imprimé dans la fenêtre, repli sur le dernier prix de ce sens
    # imprimé dans les 5 minutes AVANT t (proxy du meilleur prix opposé, éventuellement périmé) ; sans trade récent, pas d'exécution.
    j = bisect.bisect_right(book.t[side], t) - 1
    if j >= 0 and book.t[side][j] >= t - LOOKBACK_MS:
        return t + TAKER_DELAY_MS, book.p[side][j]
    return None


def mid_proxy(book, t, lookback=LOOKBACK_MS):
    """Moyenne du dernier prix d'achat agresseur et du dernier prix de vente agresseur des `lookback` ms avant t (sinon le seul disponible)."""
    v = []
    for s in (1, -1):
        j = bisect.bisect_right(book.t[s], t) - 1
        if j >= 0 and book.t[s][j] >= t - lookback:
            v.append((book.t[s][j], book.p[s][j]))
    if not v:
        return None
    return sum(p for _t, p in v) / len(v)


def markout(book, side, t_fill, p_fill, horizon_ms):
    """Mouvement du mid proxy après le fill, en bps, positif = favorable (achat : le mid monte)."""
    m = mid_proxy(book, t_fill + horizon_ms)
    return None if m is None else side * 1e4 * (m - p_fill) / p_fill


def execute_leg(book, side, t_dec, t_exp, policy, bound, queue):
    """Une jambe. policy : 'taker', 'post' (annulé à t_exp, zéro position sinon), 'post_fb' (repli taker à t_exp).
    Retourne None (non exécutée) ou dict(t, px, maker, status)."""
    if policy == "taker":
        r = taker_fill(book, side, t_dec)
        return None if r is None else {"t": r[0], "px": r[1], "maker": False, "status": "taker"}
    p = ref_price(book, side, t_dec)
    if p is None:
        return None
    t = passive_fill(book, side, p, t_dec, t_exp, bound, queue)
    if t is not None:
        return {"t": t, "px": p, "maker": True, "status": "maker"}
    if policy == "post_fb":
        r = taker_fill(book, side, t_exp)
        return None if r is None else {"t": r[0], "px": r[1], "maker": False, "status": "fallback"}
    return None


def leg_cost(leg):
    return MAKER_BPS if leg["maker"] else TAKER_BPS + SLIP_BPS


def fund_cost(fund, t0, t1, side):
    """Funding payé en bps du notionnel entre t0 et t1 : fund = (instants triés, taux horaires en bps) ; les longs paient si le taux est positif."""
    if not fund:
        return 0.0
    ts, rate = fund
    lo, hi = bisect.bisect_right(ts, t0), bisect.bisect_right(ts, t1)
    return side * sum(rate[lo:hi])


def run_trade(book, fund, side, entry, exit_, policy, bound, queue):
    """entry = (t_dec, t_exp), exit_ = (t_dec, t_exp) pour la sortie. La sortie est taker avec la politique taker ; sinon limite puis repli
    taker obligatoire à l'échéance. Retourne dict(status, net, gross, delay, markouts) ; net = 0 si l'entrée n'est pas exécutée."""
    e = execute_leg(book, side, entry[0], entry[1], policy, bound, queue)
    if e is None:
        return {"status": "unfilled", "net": 0.0, "filled": False}
    xp = "taker" if policy == "taker" else "post_fb"
    x = execute_leg(book, -side, exit_[0], exit_[1], xp, bound, queue)
    if x is None:
        return {"status": "exit_fail", "net": 0.0, "filled": False}
    gross = side * 1e4 * (x["px"] - e["px"]) / e["px"]
    net = gross - leg_cost(e) - leg_cost(x) - fund_cost(fund, e["t"], x["t"], side)
    mo = {h: markout(book, side, e["t"], e["px"], h * 1000) for h in (60, 600, 3600)}
    return {"status": e["status"], "net": net, "gross": gross, "filled": True, "delay": e["t"] - entry[0], "markouts": mo,
            "exit_status": x["status"], "maker_entry": e["maker"], "e_t": e["t"], "x_t": x["t"], "e_px": e["px"], "x_px": x["px"]}
