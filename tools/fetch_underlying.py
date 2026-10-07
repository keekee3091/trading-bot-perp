"""Historiques longs des sous-jacents non crypto, sources publiques SANS clé et à usage de recherche personnelle.

Sources retenues après lecture de leurs conditions d'usage (détail dans CLAUDE.md et data/under/MANIFEST.txt) :
  FRED (Réserve fédérale de Saint-Louis) : usage personnel, non commercial, éducatif autorisé ; séries sous copyright de
      tiers (Nasdaq, S&P) : usage strictement personnel ; extraction non perturbatrice. Séries : NASDAQ100, NASDAQCOM, DCOILWTICO,
      DCOILBRENTEU (EIA), DEXUSEU, DEXJPUS, DEXUSUK, DTWEXM, DTWEXBGS (Fed H.10), DTB3.
  Bibliothèque de données de Kenneth French (Dartmouth) : rendement quotidien du marché actions américain depuis 1926 (CRSP,
      pondéré par la capitalisation, dividendes inclus) ; copyright Fama et French, aucune clause d'interdiction trouvée sur la
      page, usage de recherche courant avec citation (Fama et French) ; pas de licence explicite : usage personnel seulement.
  Banque mondiale, « Pink Sheet » (CMO) : prix MENSUELS MOYENS or et argent depuis 1960 ; conditions : usage informatif et non
      commercial, avec attribution (« The World Bank Group authorizes the use of this material subject to the terms and
      conditions on its website »).
SOURCES EXCLUES : Yahoo Finance (pas d'API publique officielle, scraping contraire aux conditions d'usage) ; Stooq (exige une
vérification JavaScript : on ne la contourne pas) ; LBMA / ICE Benchmark Administration (403, licence requise pour les données
historiques) ; Alpha Vantage, Twelve Data, Tiingo, Polygon (clé personnelle à créer, quotas ; non utilisés ici).

Aucune authentification, aucun contournement. Un User-Agent honnête est envoyé (un User-Agent de navigateur est freiné par FRED).
Sortie : data/under/<NOM>.csv (date,value) et data/under/MANIFEST.txt (source, période, trous, ajustements).

python tools/fetch_underlying.py
"""
import csv
import io
import os
import re
import sys
import time
import urllib.request
import zipfile
import xml.etree.ElementTree as ET

UA = "trading-bot-perp-research/1.0 (personal, non-commercial)"
OUT = "data/under"

FRED = {
    "NASDAQ100": "Nasdaq-100, indice de prix (pas de dividendes), clôture quotidienne",
    "NASDAQCOM": "Nasdaq Composite, indice de prix, clôture quotidienne",
    "DCOILWTICO": "WTI Cushing, prix spot EIA ($/baril), PAS corrigé du roll ; négatif le 2020-04-20 et 04-21",
    "DCOILBRENTEU": "Brent Europe, prix spot EIA ($/baril)",
    "DEXUSEU": "EUR/USD (dollars par euro), Fed H.10, midi à New York",
    "DEXJPUS": "USD/JPY (yens par dollar), Fed H.10",
    "DEXUSUK": "GBP/USD (dollars par livre), Fed H.10",
    "DTWEXM": "Indice du dollar contre grandes devises, ancienne série, 1973 à 2019 (proxy du DXY, pas le DXY d'ICE)",
    "DTWEXBGS": "Indice du dollar large (broad), depuis 2006 (proxy du DXY, pas le DXY d'ICE)",
    "DTB3": "Bon du Trésor 3 mois, taux secondaire (% par an), repère sans risque",
}


def http(url, timeout=90):
    req = urllib.request.Request(url, headers={"user-agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def write_csv(name, rows):
    path = os.path.join(OUT, name + ".csv")
    with open(path, "w", newline="") as f:
        f.write("date,value\n")
        for d, v in rows:
            f.write("%s,%.10g\n" % (d, v))
    return path


def describe(name, rows, note, source, terms, manifest):
    gaps = 0
    mx = 0
    from datetime import date
    prev = None
    for d, _ in rows:
        y, m, dd = (int(x) for x in d.split("-"))
        cur = date(y, m, dd)
        if prev is not None:
            g = (cur - prev).days
            mx = max(mx, g)
            gaps += 1 if g > 5 else 0
        prev = cur
    manifest.append("%-16s %s -> %s  n=%d  trous > 5 j : %d (écart max %d j)\n    source : %s\n    conditions : %s\n    ajustements : %s\n"
                    % (name, rows[0][0], rows[-1][0], len(rows), gaps, mx, source, terms, note))


def main():
    os.makedirs(OUT, exist_ok=True)
    manifest = ["MANIFESTE DES SOURCES (généré le %s UTC)\n" % time.strftime("%Y-%m-%d %H:%M", time.gmtime())]
    for sid, note in FRED.items():
        raw = http("https://fred.stlouisfed.org/graph/fredgraph.csv?id=" + sid).decode("utf-8")
        rows = []
        for r in list(csv.reader(io.StringIO(raw)))[1:]:
            if len(r) > 1 and r[1] not in (".", ""):
                rows.append((r[0], float(r[1])))
        write_csv("FRED_" + sid, rows)
        describe("FRED_" + sid, rows, note, "https://fred.stlouisfed.org/series/" + sid,
                 "FRED : usage personnel, non commercial, éducatif ; séries à copyright tiers : usage strictement personnel", manifest)
        time.sleep(0.5)
    # Kenneth French : rendement quotidien du marché (Mkt-RF + RF), dividendes inclus
    z = zipfile.ZipFile(io.BytesIO(http("https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_Factors_daily_CSV.zip")))
    txt = z.read(z.namelist()[0]).decode("latin1")
    level, rows, ret = 100.0, [], []
    for line in txt.splitlines():
        p = [x.strip() for x in line.split(",")]
        if len(p) >= 5 and re.fullmatch(r"\d{8}", p[0]):
            r = (float(p[1]) + float(p[4])) / 100.0
            level *= 1.0 + r
            d = p[0]
            rows.append(("%s-%s-%s" % (d[:4], d[4:6], d[6:]), level))
    write_csv("FRENCH_US_MKT_TR", rows)
    describe("FRENCH_US_MKT_TR", rows, "indice de RENDEMENT TOTAL cumulé (dividendes inclus) du marché actions américain CRSP pondéré par la "
             "capitalisation, base 100 ; PROXY du S&P 500, pas le S&P 500 ; un perp d'indice ne verse pas de dividendes : biais favorable aux longs",
             "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html (F-F_Research_Data_Factors_daily)",
             "copyright Fama et French, pas de licence explicite, aucune interdiction trouvée ; usage de recherche personnelle avec citation", manifest)
    # Banque mondiale : or et argent, moyennes mensuelles
    xl = http("https://thedocs.worldbank.org/en/doc/74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/related/CMO-Historical-Data-Monthly.xlsx")
    zz = zipfile.ZipFile(io.BytesIO(xl))
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    ss = ["".join(t.text or "" for t in si.iter("{%s}t" % ns["m"])) for si in ET.fromstring(zz.read("xl/sharedStrings.xml")).findall("m:si", ns)]
    root = ET.fromstring(zz.read("xl/worksheets/sheet2.xml"))
    table = []
    for r in root.iter("{%s}row" % ns["m"]):
        row = {}
        for c in r.findall("m:c", ns):
            v = c.find("m:v", ns)
            if v is None:
                continue
            row[re.sub(r"\d+", "", c.get("r"))] = ss[int(v.text)] if c.get("t") == "s" else v.text
        table.append(row)
    header = next(r for r in table if "Crude oil, average" in r.values())
    col = {v.strip(): k for k, v in header.items()}
    for key, name in (("Gold", "WB_GOLD"), ("Silver", "WB_SILVER")):
        c = col[key]
        out = []
        for r in table:
            d = r.get("A", "")
            if re.fullmatch(r"\d{4}M\d{2}", d) and c in r:
                try:
                    out.append(("%s-%s-01" % (d[:4], d[5:]), float(r[c])))
                except ValueError:
                    pass
        write_csv(name, out)
        describe(name, out, "prix MENSUEL MOYEN en $ par once troy (moyenne des cours journaliers du mois) : biais de lissage "
                 "(autocorrélation artificielle des rendements, signal et exécution au même prix moyen) : résultats non fiables pour le momentum",
                 "World Bank Commodity Price Data (Pink Sheet), CMO-Historical-Data-Monthly.xlsx",
                 "usage informatif et non commercial avec attribution à The World Bank Group", manifest)
    with open(os.path.join(OUT, "MANIFEST.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(manifest))
    print("\n".join(manifest))


if __name__ == "__main__":
    main()
