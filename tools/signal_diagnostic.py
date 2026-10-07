"""Diagnostic du signal, indépendant des sorties : rendement futur signé après un signal momentum.

z = rendement sur L minutes / (écart-type des rendements 1m sur 60 min x sqrt(L)). Pour |z| >= seuil,
on mesure le rendement à l'horizon h dans le sens du signal (positif = le momentum continue, négatif
= retour à la moyenne). Échantillonnage non chevauchant (un événement par h minutes) pour que le
t-stat ne soit pas gonflé. À comparer au coût aller-retour (~14 bps avec les frais tier 0).
stdlib uniquement : python tools/signal_diagnostic.py data/BTC-USD_1m.csv
"""
import csv
import math
import sys


def load(path):
    with open(path) as f:
        return [float(r["close"]) for r in csv.DictReader(f)]


def stats(xs):
    n = len(xs)
    if n < 2:
        return n, 0.0, 0.0
    m = sum(xs) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))
    return n, m, (m / (sd / math.sqrt(n)) if sd > 0 else 0.0)


def run(close, L, h, thr, start, end):
    rets = [0.0] + [close[i] / close[i - 1] - 1 for i in range(1, len(close))]
    out, i = [], max(start, 61 + L)
    while i < end - h:
        w = rets[i - 60:i]
        m = sum(w) / 60
        sd = math.sqrt(sum((r - m) ** 2 for r in w) / 59)
        if sd > 0:
            z = (close[i] / close[i - L] - 1) / (sd * math.sqrt(L))
            if abs(z) >= thr:
                out.append((1 if z > 0 else -1) * (close[i + h] / close[i] - 1) * 1e4)
                i += h
                continue
        i += 1
    return out


if __name__ == "__main__":
    close = load(sys.argv[1])
    n = len(close)
    segs = [("train", 0, int(n * .6)), ("val", int(n * .6), int(n * .8)), ("test", int(n * .8), n)]
    print("%-6s %4s %4s %7s %9s %7s" % ("seg", "L", "h", "events", "mean bps", "t"))
    for name, a, b in segs:
        for L in (5, 15):
            for h in (5, 15, 30, 60):
                ev, m, t = stats(run(close, L, h, 0.8, a, b))
                print("%-6s %4d %4d %7d %9.2f %7.2f" % (name, L, h, ev, m, t))
