"""H_VRP, suivi prospectif mensuel (lecture seule). Lit data/vrp/ (fichiers Cboe et French mis à jour A LA MAIN, un téléchargement par mois),
ajoute dans results/vrp_prospective_log.csv les rendements EXCEDENTAIRES mensuels des 4 indices pour les mois >= 2026-09 dont les facteurs French existent.
Aucune écriture hors results/. Première lecture (alpha cumulé, descriptif, UNE fois) refusée avant 2027-04-01 ; aucune lecture intermédiaire.
python tools/vrp_monitor.py [--asof AAAA-MM-JJ]
"""
import argparse
import csv
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vrp_indices as vi  # noqa: E402

FIRST_YM = 202609
FIRST_READ = dt.date(2027, 4, 1)


def update_log(data, out):
    ff = vi.load_ff(data)
    path = os.path.join(out, "vrp_prospective_log.csv")
    done = set()
    if os.path.exists(path):
        done = {(r["ym"], r["index"]) for r in csv.DictReader(open(path, encoding="utf-8"))}
    new = []
    for name, _ in vi.CELLS:
        ret = vi.monthly_returns(vi.load_cboe(os.path.join(data, "vrp", name + "_History.csv")))
        for ym in sorted(ret):
            if ym >= FIRST_YM and ym in ff and (str(ym), name) not in done:
                new.append({"ym": ym, "index": name, "excess": round(ret[ym] - ff[ym]["rf"], 6), "mkt_rf": ff[ym]["mkt"]})
    if new:
        os.makedirs(out, exist_ok=True)
        fresh = not os.path.exists(path)
        with open(path, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["ym", "index", "excess", "mkt_rf"])
            if fresh:
                w.writeheader()
            w.writerows(new)
    return len(new)


def first_read(out):
    """Lecture unique, descriptive : excès moyen et alpha de S1 (MCO, sans inférence) par indice."""
    lock = os.path.join(out, "vrp_prospective.lock")
    if os.path.exists(lock):
        return ["lecture déjà faite"]
    rows = list(csv.DictReader(open(os.path.join(out, "vrp_prospective_log.csv"), encoding="utf-8")))
    open(lock, "w").write("lu")
    lines = []
    for name, _ in vi.CELLS:
        r = [x for x in rows if x["index"] == name]
        y, x = [float(v["excess"]) for v in r], [float(v["mkt_rf"]) for v in r]
        a = vi.ols(y, [x])[0][0] if len(y) > 2 else float("nan")
        lines.append("%s : %d mois, excès moyen %+.3f %%, alpha S1 %+.3f %% par mois (descriptif)" % (name, len(y), 100 * sum(y) / max(len(y), 1), 100 * a))
    return lines


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--asof", default=None)
    ap.add_argument("--data", default="data")
    ap.add_argument("--out", default="results")
    a = ap.parse_args(argv)
    asof = dt.date.fromisoformat(a.asof) if a.asof else dt.date.today()
    n = update_log(a.data, a.out)
    print("%d lignes ajoutées au journal" % n)
    if asof < FIRST_READ:
        print("lecture refusée avant %s (pas de lecture intermédiaire)" % FIRST_READ)
        return
    print("\n".join(first_read(a.out)))


if __name__ == "__main__":
    main()
