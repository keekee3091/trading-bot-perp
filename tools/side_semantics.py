"""Établit ce que signifie le champ `side` de /v1/info/trades, par la mesure et non par supposition.

Principe : on relève le carnet (meilleur bid / meilleur ask) toutes les ~1.5 s pendant que l'on relève
les trades récents. Un trade dont le prix est >= au meilleur ask du relevé PRÉCÉDENT est une exécution
au ask, donc l'agresseur est un acheteur ; un prix <= au meilleur bid précédent est une exécution au
bid, donc l'agresseur est un vendeur. On croise avec `side`. Les trades à l'intérieur du spread, ou
dont le carnet a pu bouger entre deux relevés, sont comptés à part (indéterminés).

Les horloges (locale et serveur) ne sont pas synchronisées : on estime le décalage en cherchant la
valeur qui maximise la cohérence, puis on la rapporte (l'estimation est un choix de l'analyse).

python tools/side_semantics.py [--symbols NVDA-USD WTIOIL-USD SOL-USD BTC-USD] [--duration 150]
Sortie : results/side_semantics.txt (+ stdout).
"""
import argparse
import collections
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch_klines import get  # noqa: E402


def collect(symbols, duration):
    inst = {r["symbol"]: int(r["instrument_id"]) for r in get("/v1/info/instruments")}
    books = {s: [] for s in symbols}   # (t_local_ms, bid, ask)
    trades = {s: {} for s in symbols}  # trade_id -> dict
    t_end = time.time() + duration
    last_trades = 0.0
    while time.time() < t_end:
        cycle = time.time()
        for s in symbols:
            try:
                t0 = time.time()
                b = get("/v1/info/book", {"instrument_id": inst[s]})
                t1 = time.time()
                books[s].append(((t0 + t1) / 2 * 1000, float(b["bids"][0][0]), float(b["asks"][0][0])))
            except Exception as e:  # noqa: BLE001
                print("book", s, e, file=sys.stderr)
        if cycle - last_trades >= 6.0:
            last_trades = cycle
            for s in symbols:
                try:
                    d = get("/v1/info/trades", {"instrument_id": inst[s]})
                    for r in d["data"]:
                        trades[s][r["trade_id"]] = r
                except Exception as e:  # noqa: BLE001
                    print("trades", s, e, file=sys.stderr)
        time.sleep(max(0.0, 1.5 - (time.time() - cycle)))
    return books, trades


def classify(books, trades, offset_ms):
    """Pour chaque trade, relevé de carnet le plus récent <= t_trade + offset ; retourne les comptes."""
    import bisect
    ts = [b[0] for b in books]
    cnt = collections.Counter()
    for tr in trades.values():
        t = tr["timestamp"] + offset_ms  # ramené à l'horloge locale
        i = bisect.bisect_right(ts, t) - 1
        if i < 0 or t - ts[i] > 3000:
            cnt[(tr["side"], "hors fenêtre")] += 1
            continue
        _, bid, ask = books[i]
        p = float(tr["price"])
        if p >= ask:
            kind = "au ask (agresseur acheteur)"
        elif p <= bid:
            kind = "au bid (agresseur vendeur)"
        else:
            kind = "dans le spread"
        cnt[(tr["side"], kind)] += 1
    return cnt


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--symbols", nargs="+", default=["NVDA-USD", "WTIOIL-USD", "SOL-USD", "BTC-USD"])
    ap.add_argument("--duration", type=float, default=150.0)
    a = ap.parse_args()
    books, trades = collect(a.symbols, a.duration)
    out = []
    # décalage d'horloge : celui qui maximise la part de trades classés au ask/bid (hors spread)
    for s in a.symbols:
        n_tr = len(trades[s])
        if not n_tr or not books[s]:
            out.append("%s : aucun trade ou aucun carnet relevé" % s)
            continue
        best = None
        for off in range(-3000, 3001, 250):
            c = classify(books[s], trades[s], off)
            decided = sum(v for (side, k), v in c.items() if k.startswith("au "))
            if best is None or decided > best[0]:
                best = (decided, off, c)
        decided, off, c = best
        out.append("%s : %d trades distincts, %d relevés de carnet, décalage horloge retenu %+d ms" % (s, n_tr, len(books[s]), off))
        for side in ("long", "short"):
            tot = sum(v for (sd, k), v in c.items() if sd == side)
            ask = c.get((side, "au ask (agresseur acheteur)"), 0)
            bid = c.get((side, "au bid (agresseur vendeur)"), 0)
            ins = c.get((side, "dans le spread"), 0)
            oth = c.get((side, "hors fenêtre"), 0)
            out.append("   side=%-5s : %4d trades | au ask %4d | au bid %4d | dans le spread %4d | hors fenêtre %4d" %
                       (side, tot, ask, bid, ins, oth))
        sett = sum(1 for t in trades[s].values() if t.get("settlement"))
        out.append("   trades avec settlement=true : %d" % sett)
    # conclusion mécanique (comptes agrégés sur tous les symboles)
    agg = collections.Counter()
    for s in a.symbols:
        if trades[s] and books[s]:
            best = max((classify(books[s], trades[s], off) for off in range(-3000, 3001, 250)),
                       key=lambda c: sum(v for (sd, k), v in c.items() if k.startswith("au ")))
            agg.update(best)
    la, lb = agg[("long", "au ask (agresseur acheteur)")], agg[("long", "au bid (agresseur vendeur)")]
    sa, sb = agg[("short", "au ask (agresseur acheteur)")], agg[("short", "au bid (agresseur vendeur)")]
    out.append("")
    out.append("AGRÉGAT : side=long  -> au ask %d, au bid %d ; side=short -> au ask %d, au bid %d" % (la, lb, sa, sb))
    if la + lb + sa + sb == 0:
        out.append("CONCLUSION : indéterminée (aucun trade classable).")
    elif la > 3 * lb and sb > 3 * sa:
        out.append("CONCLUSION (mesurée) : side=long = l'AGRESSEUR est acheteur (trade au ask), side=short = l'AGRESSEUR est vendeur (trade au bid). "
                   "Le maker est donc du côté opposé : un trade side=short exécute un ordre d'ACHAT passif (bid) ; side=long exécute un ordre de VENTE passif (ask).")
    elif lb > 3 * la and sa > 3 * sb:
        out.append("CONCLUSION (mesurée) : side=long = l'AGRESSEUR est vendeur (trade au bid), side=short = l'AGRESSEUR est acheteur. Sens inversé par rapport à l'usage courant.")
    else:
        out.append("CONCLUSION : ambiguë (ni agresseur acheteur / vendeur ne ressort nettement) : ne pas supposer le sens.")
    os.makedirs("results", exist_ok=True)
    with open("results/side_semantics.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    print("\n".join(out))


if __name__ == "__main__":
    main()
