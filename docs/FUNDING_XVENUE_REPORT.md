# Piste D : différence de funding entre plateformes (Polymarket et Hyperliquid), rapport de découverte, 2026-10-09

**Verdict pré-enregistré : INCONCLUSIF (intervalle de 5,8 % de large pour une limite de 2 %). L'estimation ponctuelle est légèrement positive mais fragile : elle repose sur quelques actifs. Aucun code d'exécution.** `LiveExchange` reste un stub. Le holdout (après le 2026-09-28) n'est pas lu.
Pré-enregistrement : `CLAUDE.md`, « Pré-enregistrement : piste D ». Outils : `tools/fetch_hl.py` (téléchargeur Hyperliquid, API publique), `tools/funding_xvenue.py` ; tests `tests/test_funding_xvenue.py` (dans ctest : règle de décision, signe du funding, comptabilité horaire, coûts, liquidation, absence d'anticipation, pagination).
Fichiers : `results/funding_xvenue_instruments.csv`, `results/funding_xvenue_sensitivity.csv`, `results/funding_xvenue_summary.txt`. Données brutes (`data/hl/`) ignorées par git.

## Mécanisme et données

On est short sur la plateforme où le funding moyen des 14 derniers jours est le plus élevé et long sur l'autre, pour le MÊME actif (appariement par nom). Aucune jambe sur le sous-jacent : le capital immobilisé est celui des deux marges (à levier 3 : 67 % de N), contre 2N pour le carry avec couverture.
38 actifs avec au moins 40 jours de funding des deux côtés avant le 2026-09-28 (BTC, ETH, SOL, XRP, HYPE ; SP500, GOLD, SILVER, BRENTOIL ; 29 actions et ETF), 989 à 3 474 heures chacun. Position ouverte le lundi à 00:00 UTC si l'écart annualisé dépasse 2 % ; coûts : Polymarket 4 + 2 bps + demi-spread, Hyperliquid 4,5 + 2 bps + demi-spread (barème de base, palier 0).

## Résultats (référence : levier 3 sur chaque plateforme, theta 2 %, marge non rémunérée)

| Mesure | Valeur |
|---|---|
| **Excès net poolé** | **+1,31 % par an**, IC95 [-1,03 ; +4,74] |
| Moitiés du temps | +1,39 % puis **-0,33 %** |
| Instruments positifs | **16 sur 38** |
| Semaines à décision confirmée par l'écart réalisé | 123 sur 170 (72 %) |
| Épisodes liquidés à L = 3 | **7,7 %** (65 épisodes) |
| Pire fenêtre de base de 30 jours (poolée) | -0,14 % de N |
| Composantes moyennes (par instrument, temps à plat compris) | funding +2,29 %, base +2,10 %, coûts 2,07 %, coût du capital 1,02 % |

Critères : (1) excès > 1 % **oui** ; (2) borne basse > 0 **non** ; (3) deux moitiés positives **non** ; (4) 60 % des instruments positifs **non** (16/38) ; (5) décisions confirmées **oui** ; (6) liquidations <= 5 % **non** ; (7) base <= 3 % **oui**.

**Lecture honnête.**
- **Le signe de la décision est fiable** : le funding de la semaine détenue suit celui des 14 jours précédents dans 72 % des cas. Le mécanisme existe.
- **Mais le résultat moyen est porté par quelques actifs** : SILVER +33,9 % par an (base de +37 % : le prix de l'argent a divergé entre les deux plateformes), BRENTOIL +14,0 %, COIN +13,9 %, STRC +11,9 %. **Le médian vaut 0,0 %** ; sans SILVER la moyenne tombe à +0,43 % ; sans les trois meilleurs, elle vaut -0,34 % (calculs post hoc, descriptifs).
- **La base moyenne est positive (+2,1 %)** : quand un marché paie plus de funding, c'est souvent qu'il est cher par rapport à l'autre, et le prix converge ensuite. Le funding différentiel et la convergence sont corrélés : c'est cohérent avec la piste C, qui mesurera les écarts de prix eux-mêmes.
- **Crypto seule : -2,4 %** (5 actifs) ; non crypto : +1,9 % [-0,7 ; +5,5].

## Sensibilités (non décisionnelles)

| Réglage | Excès poolé | IC95 |
|---|---|---|
| theta 0 % / 5 % | +0,57 % / +1,10 % | [-2,0 ; +4,4] / [-0,2 ; +3,0] |
| Frais Hyperliquid doublés (9 bps) | +0,70 % | [-1,7 ; +4,1] |
| Sans DRAM, STRC, SKHY, SPCX (définition de contrat incertaine) | +1,30 % | [-1,7 ; +5,4] |
| Levier 1 / 2 / 5 / 10 | -0,72 % / +0,80 % / +1,72 % / +2,03 % | tous contiennent 0 |

Un levier plus élevé améliore le chiffre (moins de capital immobilisé) mais augmente la part d'épisodes liquidés : sans transfert de marge entre plateformes, un épisode de plusieurs semaines sur une action volatile est liquidé dès qu'un des deux marchés bouge de plus de `1/L - mmr`.

## Limites

- **Puissance** : 4 mois, 38 actifs mais quelques épisodes seulement par actif (de 0 à 5), un seul régime ; l'intervalle ne permet pas de conclure.
- **Appariement par nom** : l'équivalence des définitions de contrat (DRAM, STRC, SKHY, SPCX, et l'argent) n'est pas vérifiée ; la base mesure aussi cet écart. NAS100 et WTIOIL sont exclus (équivalence non établie).
- **Frais Hyperliquid pour les marchés HIP-3** (mode croissance, part du déployeur de 0 à 300 %) : non établis ; sensibilité à 9 bps.
- **Non modélisé** : transferts de marge entre plateformes (délais, frais), capital sur deux plateformes, risque de contrepartie (Polymarket, Hyperliquid, déployeur HIP-3), modification des paramètres de funding par un déployeur, restrictions d'accès, fiscalité.
- **Biais de survie** : actifs encore cotés des deux côtés aujourd'hui.

## Suite pré-enregistrée

La règle est gelée (14 jours, theta 2 %, L = 3, frais ci-dessus). **Lecture du holdout le 2026-12-15 au plus tôt, après au moins 60 jours de données au-delà du gel, une seule fois**, avec les mêmes critères, sur les données postérieures au 2026-09-28 (funding et prix des deux plateformes, dont l'enregistreur inter-plateformes). M passerait à 10.
