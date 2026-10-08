# Piste A : carry de funding avec couverture (short perp, long sous-jacent), rapport final, 2026-10-08

**Verdict pré-enregistré : INCONCLUSIF (intervalle trop large), avec des estimations ponctuelles négatives partout et une arithmétique structurellement défavorable. Aucun code d'exécution.** `LiveExchange` reste un stub. Le holdout (après le 2026-09-28) n'a pas été lu : M reste à 9.
Pré-enregistrement : `CLAUDE.md`, « Pré-enregistrement : piste A ». Outil : `tools/carry_study.py` ; tests `tests/test_carry.py` (dans ctest : funding, P&L et signe calculés à la main, identité comptable, coût d'opportunité, distance de liquidation, absence d'anticipation, bootstrap déterministe, contrôles positif et nul).
Fichiers agrégés : `results/carry_instruments.csv`, `results/carry_pooled.csv` (96 réglages avec intervalle), `results/carry_summary.txt`. Aucune donnée brute Tiingo.

## Ce qui est mesuré (32 instruments, 41 à 144 jours, 21 semaines, découverte avant le 2026-09-28)

Univers : 27 actions (jambe longue = l'action), SP500 / NAS100 / GOLD / SILVER / WTIOIL couverts par SPY / QQQ / GLD / SLV / USO. Exclus et comptés : voir `CLAUDE.md` (STRC, BABA, ZM, DRAM, EWY, NCLD, SOXL, BRENTOIL, SKHYNIX, CXMT, SAMSUNG, UNITREE, DELL, CRWV, CBRS, MRVL, crypto).

| Catégorie | n | Funding reçu par le short (par an) | Base moyenne (sous-jacent moins perp, dividendes inclus) | Excès net de référence |
|---|---|---|---|---|
| Actions | 27 | **+5,38 %** (24 sur 32 instruments à funding positif au moins 70 % des jours dans les deux moitiés) | -1,14 % | -4,11 % |
| Indices et matières premières via ETF | 4 | +2,69 % (NAS100 +15,3 %, SILVER +3,4 %, SP500 -0,4 %, GOLD -7,6 %) | -0,42 % | -5,59 % |
| WTI via USO | 1 | -21,0 % (le short paie) | +36,4 % (USO et le contrat à terme du perp divergent) | +7,1 % (artefact de la base) |

**Cas de référence** (détention 30 jours, perp à levier 2, couverture 3 bps par côté, marge non rémunérée, poids égaux) : **excès net poolé -3,94 % par an, IC95 [-11,21 ; +1,88]** (largeur 13,1 %, soit 6 fois la limite de 2 % : inconclusif). Moitiés du temps : -43 % puis -1 % (la première moitié ne contient que 5 à 6 instruments, dont l'anomalie SPCX ci-dessous).
12 instruments sur 32 ont un excès positif. Sans SPCX (sensibilité post hoc de qualité de données, voir plus bas) : -1,71 % [-4,86 ; +3,85], toujours trop large.

**L'arithmétique, qui est la partie précise de ce résultat** : le carry brut poolé (funding + base) est de **4,34 % par an**, contre un taux sans risque de **3,79 %**. Le coût d'opportunité du capital (jambe longue + marge du perp) vaut `rf x (1 + 1/L)`.

| Levier du perp L | Carry brut moins coût d'opportunité | Jours de détention pour amortir 21 bps d'aller-retour |
|---|---|---|
| 1 | -3,24 % par an | jamais |
| 2 | -1,34 % | jamais |
| 5 | -0,21 % | jamais |
| 10 | +0,17 % | 451 |

Excès net poolé (H = 30, h = 3 bps, marge non rémunérée) : L = 1 : -5,84 % ; L = 2 : -3,94 % ; L = 5 : -2,81 % ; L = 10 : -2,43 %. Marge rémunérée au taux sans risque (H = 30, L = 2) : -2,05 %. Détention de 90 jours (L = 2, couverture 3 bps) : -2,21 % [-9,47 ; +3,61] ; 7 jours : -12,5 %.
**Le funding d'intérêt (5,5 % par an) couvre à peine le coût du capital immobilisé sur deux jambes (3,8 % x (1 + 1/L)) : le carry ne bat pas le cash**, quel que soit L, avant même les frais et la base. Il faudrait une marge rémunérée ET un levier élevé ET une détention de plus de 3 mois, c'est-à-dire un edge de 1 % par an pour un risque de liquidation du short.

## Risque de base et de liquidation

- **Écart-type de la base journalière** : de 10 bps (SP500, NAS100) à 75 bps (ARM, QCOM) pour les actions liquides, 12 à 16 bps pour GOLD et SILVER, 70 bps pour le WTI. Pas de surcroît net de base hors séance ni le week-end dans cet échantillon (écart-type du vendredi au lundi comparable ou plus faible, sauf le WTI : 83 contre 64 bps).
- **Liquidation du short sans transfert de marge (L = 2, détention de 30 jours)** : 5,6 % des fenêtres en moyenne entre instruments, concentrées sur des titres qui ont gagné plus de 45 % en 30 jours dans cet échantillon haussier : MSTR 71 %, CRCL 43 %, SPCX 29 %, SNDK 23 %, INTC 9 %. La jambe longue gagne alors la même somme, mais seul un transfert entre plateformes (délai et coût non quantifiables en lecture seule) évite la liquidation.
  Pire fenêtre de 30 jours de la base moyenne poolée : -8,5 % de N (dominée par l'anomalie SPCX, voir ci-dessous).
- **SPCX** : le prix du perp s'est figé à 300,0 les 17 et 18 juin 2026 (bornes de prix du démarrage), soit une base de -5 658 et +3 350 bps ces jours-là, alors qu'elle est de quelques bps ensuite. C'est une anomalie de démarrage, pas un risque récurrent. Retirer SPCX est une sensibilité POST HOC de qualité de données, déclarée ; le cas de référence pré-enregistré la conserve.
- **Dividendes** : 13 dates ex-dividende dans l'échantillon, dividende moyen 17,3 bps ; l'écart (rendement du perp moins rendement du prix brut du sous-jacent) vaut +5,9 bps en moyenne : le perp ne semble pas baisser tout à fait du dividende, mais avec n = 13 et un bruit de 20 à 60 bps, c'est **indéterminé**.

## Critères pré-enregistrés (cas de référence)

(1) excès > 1 % : non. (2) borne basse > 0 : non. (3) positif dans les deux moitiés : non. (4) au moins 60 % des instruments positifs : non (12 sur 32). (5) stabilité du funding : oui (24 sur 32). (6) liquidations à L = 2 inférieures à 5 % : non (5,6 %). (7) pire base de 30 jours inférieure à 3 % : non (-8,5 %, anomalie SPCX comprise).
Règle de largeur : intervalle de 13,1 % de large, donc **inconclusif et non négatif** pour le signe de l'espérance. Mais la partie précise du calcul (funding contre coût d'opportunité) est défavorable à tous les niveaux de levier.

## Limites et écarts déclarés

- **Puissance** : 41 à 144 jours, un seul régime haussier, base à écart-type de 10 à 75 bps par jour : la moyenne de la base n'est pas estimable avec précision (l'intervalle de bootstrap en témoigne). Le funding, lui, est précis.
- **Écart** : la stabilité du funding est mesurée sur le signe de la SOMME JOURNALIÈRE des taux horaires (et non heure par heure comme écrit dans le pré-enregistrement).
- **Non vérifié** : la marge est-elle rémunérée (deux cas rapportés) ; le funding reçu est supposé celui publié (signe et échelle 0,5 d'après la doc, aucun paiement réel observé) ; frais et spread de la couverture (3 bps par côté, hypothèse) ; transferts de marge entre plateformes ; coût d'emprunt ou de marge de la jambe longue (au comptant, 1x).
- **Univers** : biais de survie (actions cotées aujourd'hui chez Polymarket), WTI via USO (contrats à terme, roulement), erreur de suivi des ETF.
- **À reprendre si** : la marge devient rémunérée, un levier de marge sur la jambe longue (portefeuille de marge) abaisse le coût du capital, ou plus de 6 mois de données donnent un intervalle étroit sur la base.
