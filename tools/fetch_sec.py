"""Téléchargeur EDGAR (SEC) : événements de résultats trimestriels (8-K, Item 2.02) des actions de l'univers Tiingo.

Conditions d'accès automatisé de la SEC (sec.gov/os/accessing-edgar-data) : en-tête User-Agent déclarant un contact réel et
au plus 10 requêtes par seconde (ici 5), sinon blocage (403 ou 429). Le User-Agent est lu dans .env (SEC_USER_AGENT) et n'est ni
écrit dans le code, ni affiché, ni journalisé, ni mis dans une URL. Cache local data/sec/ (ignoré par git) : aucun téléchargement
redondant ; reprise sur erreur avec attente croissante. Sorties : data/sec/events.csv (déduit des soumissions publiques).

python tools/fetch_sec.py --all
stdlib uniquement.
"""
import argparse
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.request

OUT = os.path.join("data", "sec")
MIN_INTERVAL = 0.2          # 5 requêtes par seconde au plus (plafond officiel : 10)
_last = [0.0]


def load_ua(path=".env"):
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.startswith("SEC_USER_AGENT="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def fetch(url, ua, cache, opener=urllib.request.urlopen, now=time.time, sleep=time.sleep):
    """Retourne le contenu (octets) de l'URL, depuis le cache s'il existe. Une seule requête par fichier."""
    if os.path.exists(cache):
        with open(cache, "rb") as f:
            return f.read()
    for attempt in range(8):
        wait = MIN_INTERVAL - (now() - _last[0])
        if wait > 0:
            sleep(wait)
        _last[0] = now()
        req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept-Encoding": "identity"})
        try:
            with opener(req, timeout=60) as r:
                data = r.read()
            os.makedirs(os.path.dirname(cache), exist_ok=True)
            tmp = cache + ".tmp"
            with open(tmp, "wb") as f:
                f.write(data)
            os.replace(tmp, cache)
            return data
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            sleep(30 * (attempt + 1) if e.code in (403, 429) else 10 * (attempt + 1))
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            sleep(10 * (attempt + 1))
    return None


def ticker_to_cik(ua, out=OUT, **kw):
    raw = fetch("https://www.sec.gov/files/company_tickers.json", ua, os.path.join(out, "company_tickers.json"), **kw)
    return {v["ticker"].upper(): int(v["cik_str"]) for v in json.loads(raw).values()}


def events_for(cik, ua, out=OUT, **kw):
    """Soumissions 8-K contenant l'Item 2.02. Retourne une liste de dicts (date de dépôt, heure d'acceptation UTC, etc.)."""
    base = fetch("https://data.sec.gov/submissions/CIK%010d.json" % cik, ua, os.path.join(out, "CIK%010d.json" % cik), **kw)
    if base is None:
        return None
    d = json.loads(base)
    pages = [d["filings"]["recent"]]
    for f in d["filings"].get("files", []):
        raw = fetch("https://data.sec.gov/submissions/" + f["name"], ua, os.path.join(out, f["name"]), **kw)
        if raw:
            pages.append(json.loads(raw))
    ev = []
    for p in pages:
        for i, form in enumerate(p["form"]):
            if form == "8-K" and "2.02" in [x.strip() for x in p["items"][i].split(",")]:
                ev.append({"cik": cik, "filing_date": p["filingDate"][i], "acceptance_utc": p["acceptanceDateTime"][i],
                           "report_date": p["reportDate"][i], "items": p["items"][i], "accession": p["accessionNumber"][i]})
    return sorted(ev, key=lambda e: e["acceptance_utc"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()
    ua = load_ua()
    if not ua:
        sys.exit("SEC_USER_AGENT absente de .env")
    st = json.load(open(os.path.join("data", "tiingo", "_state.json"), encoding="utf-8"))["tickers"]
    tickers = sorted(t for t, v in st.items() if v.get("status") == "ok")
    cik = ticker_to_cik(ua)
    rows, summary = [], []
    for t in tickers:
        if t not in cik:
            summary.append((t, None, 0, "", "CIK introuvable"))
            continue
        ev = events_for(cik[t], ua)
        if ev is None:
            summary.append((t, cik[t], 0, "", "soumissions introuvables"))
            continue
        for e in ev:
            rows.append([t, e["cik"], e["filing_date"], e["acceptance_utc"], e["report_date"], e["items"], e["accession"]])
        summary.append((t, cik[t], len(ev), "%s -> %s" % (ev[0]["filing_date"], ev[-1]["filing_date"]) if ev else "", ""))
    with open(os.path.join(OUT, "events.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ticker", "cik", "filing_date", "acceptance_utc", "report_date", "items", "accession"])
        w.writerows(rows)
    for s in summary:
        print("%-8s cik=%s événements 8-K 2.02 : %3d %s %s" % (s[0], s[1], s[2], s[3], s[4]))
    print("total %d événements, %d actions avec au moins un" % (len(rows), sum(1 for s in summary if s[2] > 0)))


if __name__ == "__main__":
    main()
