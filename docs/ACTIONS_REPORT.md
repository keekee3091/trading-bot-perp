# Actions : écart de réouverture, coupe transversale, nuit contre séance : rapport final, 2026-10-08

**Conclusion : négative à l'étage 1, donc pas d'étage 2 et aucun code d'exécution.** Rien ne passe avec un rapport effet / coût supérieur à 1. `LiveExchange` reste un stub, aucun ordre réel.
Pré-enregistrement (grille, règles, étage 2, puissance) : `CLAUDE.md`, section « Pré-enregistrement : actions ». Outils : `tools/fetch_tiingo.py`, `tools/stocks_study.py`, tests `tests/test_stocks_study.py` (dans ctest).
Fichiers agrégés : `results/stocks_stage1.csv` (les 41 cellules, exclues comprises), `results/stocks_h1a.csv`, `results/stocks_h1b_descriptive.csv`, `results/stocks_universe.csv`, `results/stocks_power.json`,
`results/stocks_heatmap.svg`, `results/stocks_summary.txt`. **Aucune donnée brute Tiingo (licence « Internal Use Only ») dans `docs/` ni `results/` ; `data/tiingo/` et `.env` sont ignorés par git.**

**Biais de survie : l'univers est celui des actions listées AUJOURD'HUI par Polymarket (grandes capitalisations liquides, gagnantes récentes). Tous les résultats de longue histoire (H2, H3) surestiment ce qu'on aurait obtenu en choisissant l'univers à l'époque.**
Un résultat positif aurait été à prendre avec ce biais ; un résultat négatif y résiste mieux.

## Ce qui a été mesuré

**Données.** 34 actions utilisables sur 38 (SKHYNIX, SAMSUNG, CXMT : non américains ; UNITREE : pré-IPO ; absents chez Tiingo, exclus). AAPL testée seule d'abord : prix ajustés des splits et des dividendes (vérifié au jour de 5 splits
et d'un dividende), 11 544 jours depuis 1980-12-12, 3 trous de plus de 4 jours (11 septembre 2001, 2 janvier 2007, ouragan Sandy), tous de vraies fermetures. 26 actions ont plus de 5 ans d'historique, 14 plus de 20 ans. Perp : 18 actions
avec au moins 40 jours avant le gel du 2026-09-28 (42 à 71 jours chacune).

**Grille** : 41 cellules soumises au FDR (H1b 12, H2 21, H3 8) plus 3 cellules descriptives H1a. **Puissance** (règle écrite avant résultat, MDE > 3 x coût) : **28 cellules sous-puissantes, 13 testées** (H2 quotidien 7, H3 Tiingo 6).
Faux positifs attendus : 0.65. Placebos (signal décalé, mélangé par blocs, signes aléatoires) : 7.7 % de p < 0.05 sur 26 valeurs, |z| max 3.0, écart-type robuste de z 0.87, lambda = 1.00 : erreurs-types calibrées. 5 cellules passent le FDR, 4 sont stables,
**0 passent le ratio effet / coût > 1.**

### H1 : écart de réouverture (perp, 18 actions, 48 jours en moyenne)

- **H1a (descriptif)** : l'écart d'ouverture réel régressé sur le mouvement hors séance du perp donne un **bêta de 0.70 (erreur-type 0.19 groupée par date, 0.20 par action) et un R² de 0.71** (toutes les nuits) ; 0.66 et 0.67 les nuits de semaine ; **0.89 et 0.88
  le week-end** (88 % de la variance de l'écart du lundi est déjà dans le mouvement du perp). Écart-type de l'écart réel 254 bps, du mouvement du perp 304 bps. **Le perp est donc déjà très informatif (bêta entre 0.66 et 0.89), plus le week-end** : il reste environ 30 % de la
  variance de l'écart d'ouverture que le perp ne contient pas (écart-type résiduel d'environ 140 bps), mais en exploiter la partie prévisible demande de la puissance qu'on n'a pas.
- **H1b (résidu puis rendement du perp à +30 min, +2 h, clôture)** : **non testable, les 12 cellules sont sous-puissantes** (686 à 848 couples action-jour, MDE de 195 à 357 bps contre une limite de 46.5 bps). À titre purement descriptif
  (`results/stocks_h1b_descriptive.csv`, hors FDR) : l'IC du résidu et de l'écart avec le rendement ultérieur est négatif partout (-0.02 à -0.09, signe d'un retour après sur-réaction), mais |z| au plus 1.9 : indiscernable de zéro.
  Il faudrait plusieurs mois de perp de plus (le holdout après le 2026-09-28 reste intact pour cela).

### H2 : coupe transversale quotidienne, 1980 à 2018 (découverte), 5 à 21 jours exclus pour sous-puissance

| Variable | IC | z | q | Écart de quintiles (bps / jour) | Coût de rotation (bps) | Ratio | Stable |
|---|---|---|---|---|---|---|---|
| mom_1 (rendement de la veille) | -0.0118 | -2.91 | 0.016 | +0.5 | 25.0 | 0.02 | non |
| mom_5 | -0.0097 | -2.39 | 0.044 | -7.1 | 12.0 | 0.59 | oui |
| mom_20, mom_60, mom_120, mom_60s, mom_120s | de +0.003 à +0.009 | 0.65 à 1.93 | >= 0.11 | de -0.7 à +3.5 | 2.7 à 6.4 | 0.12 à 0.54 | non |

Il y a une fine inversion à 1 et 5 jours (les gagnants de la veille ou de la semaine sous-performent le lendemain, IC de -0.01) : pas un résultat à rejeter (q = 0.016 et 0.044), mais **7 bps par jour bruts contre 12 bps de coût de rotation** (le portefeuille
long/short change environ 40 % de ses titres chaque jour, 4 x rotation x 7.75 bps). Aucun momentum à 20, 60, 120 jours, avec ou sans saut du dernier mois. Les rebalancements hebdomadaire et mensuel sont sous-puissants (peu de titres par quintile : au plus 34 actions).

### H3 : nuit contre séance, 1980 à 2018

| Sous-ensemble | Rendement moyen (bps) | z | Coût aller-retour + funding (bps) | Ratio | Stable |
|---|---|---|---|---|---|
| **Nuit, toutes** | **+9.55** par nuit | 8.7 | 16.8 | **0.57** | oui |
| Nuit de semaine (mar-ven) | +10.15 | 7.8 | 16.6 | 0.61 | oui |
| Nuit de week-end (vendredi -> lundi) | +7.53 | 2.6 | 19.6 | 0.38 | oui |
| Séance, toutes | -2.69 | -1.2 | 15.1 | 0.18 | non |
| Séance de semaine / lundi | -1.73 / -9.11 | -0.8 / -1.6 | 15.1 | 0.11 / 0.60 | non |

Le rendement nocturne positif est statistiquement net, stable et significatif après FDR (z jusqu'à 8.7) : c'est la prime de nuit connue des actions américaines. **Mais 9.5 à 10 bps par nuit ne couvrent pas 16.8 bps de coût** (frais 8, slippage 4, spread 3.5, funding de 17.5 heures
d'intérêt payé par le long 1.1 bps), soit **57 à 61 % du seuil de rentabilité**, et ce sur un univers biaisé en faveur des gagnantes (qui surestime la prime). Le seuil de rentabilité est donc de l'ordre de 17 bps par nuit, contre 10 mesurés. Un coût maker (1.25 bps par côté) changerait le calcul, mais le
market making est hors périmètre. Les 2 cellules H3 sur le perp (48 jours) sont sous-puissantes. Le test 2019-2026 n'a pas été touché.

## Carte des relations mesurées (effet en bps contre coût)

| Relation | Effet mesuré | Coût | Couvre le coût ? |
|---|---|---|---|
| Écart d'ouverture réel expliqué par le mouvement du perp | bêta 0.70, R² 0.71 (0.88 le week-end) | n.a. | le perp est déjà informatif |
| Résidu perp - gap puis rendement du perp | IC -0.02 à -0.09, \|z\| <= 1.9, sous-puissant | 15.9 | non testable |
| Inversion à 5 jours, coupe transversale | -7.1 bps par jour brut | 12.0 (rotation) | non (0.59) |
| Prime de nuit des actions | +9.5 à +10.2 bps par nuit | 16.8 | non (0.57 à 0.61) |
| Momentum 20 à 120 jours | indiscernable de zéro | n.a. | non |
| Séance (ouverture -> clôture) | -2.7 bps, n.s. | 15.1 | non |

## Limites

- **Biais de survie** (univers actuel de Polymarket) : voir en tête. **Historique perp court** (48 à 71 jours, 4 à 6 % de minutes avec trades pour les actions récentes) : H1 est sous-puissante, la conclusion sur H1b est « on ne sait pas », pas « il n'y a rien ».
- **Licence** : Tiingo gratuit « Internal Use Only » : aucune donnée brute publiée, résultats agrégés seulement ; clé hors dépôt (`.env` ignoré).
- Les 41 cellules sont celles de la spécification ; 5 et 21 jours (H2) et le perp (H3, H1b) sont exclus par la règle de puissance, pas par choix a posteriori. La stratégie de rotation longue/courte à 5 jours aurait peut-être eu plus de puissance avec un univers de plusieurs centaines de titres : non disponible ici.
- Spread hors séance non mesuré (les actions sont fines, les écarts de réouverture sont dans cette zone : H1 en particulier est exposé à ce risque). Le coût de 15.5 bps est celui d'un aller-retour en séance.
- H4 (résultats trimestriels) non faite : la seule source libre et légale (EDGAR, 8-K 2.02) exige un contact réel dans l'en-tête ; sur accord pour l'adresse à utiliser, elle peut être ajoutée.
- Le holdout du 2026-09-28 au 2026-10-06 (perp) et le test 2019-2026 (long) sont intacts. M reste à 9 (aucun test de l'étage 2).
