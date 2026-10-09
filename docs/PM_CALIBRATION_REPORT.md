# Piste F : calibration des marchés de prédiction Polymarket, rapport de découverte, 2026-10-09

**Verdict pré-enregistré : NÉGATIF pour LONGSHOT_SELL (les trois horizons) ; FAV_BUY non concluant (trop peu de transactions, rendement positif non significatif). Le test 2026 n'est pas lu. Aucun code de négociation.** Aucun compte, aucun ordre ; **l'éligibilité à négocier ces marchés dépend de votre pays et n'est pas traitée ici**.
Pré-enregistrement : `CLAUDE.md`, « Pré-enregistrement : piste F ». Outils : `tools/fetch_pm.py` (API publiques Gamma et CLOB, `data/pm/` ignoré par git), `tools/pm_calibration.py` ; tests `tests/test_pm_calibration.py` (dans ctest : rendements calculés à la main, exclusions, jackknife par événement, intervalle de Wilson, contrôles positif et nul, filtres de l'API).
Fichiers : `results/pm_summary.txt`, `results/pm_calibration.csv`.

## Données

11 546 marchés binaires Yes / No résolus, volume >= 300 000 $, date de fin du 2023-01-01 au 2026-09-30, sans frais activés (exclus et comptés : 20 572 non binaires, 5 011 à frais activés, 28 non résolus, 12 ni 1 ni 0). Découpage chronologique : train jusqu'au 2025-06-30 (3 826), validation jusqu'au 2025-12-31 (3 659), test 2026 (4 061, **non lu**).
Prix de Yes à `fin - h` (dernier point journalier de l'historique), uniquement pour les marchés démarrés et encore ouverts à cet instant. Exclusions (marché x horizon) : 9 170 « pas démarré à T0 » (beaucoup de marchés très courts), 6 265 « déjà fermé », 6 343 « prix d'achat >= 1 » (favoris à 99 % ou plus, hors de portée avec 1 cent de spread), 783 sans prix récent.

## Résultats de la découverte (rendement net par dollar investi, après 1 cent de spread et coût du capital)

| Règle | h | Transactions (train / validation) | Rendement net moyen | Train / validation | Critères |
|---|---|---|---|---|---|
| LONGSHOT_SELL (acheter No si Yes < 10 %) | 1 jour | 498 / 401 | **-1,58 %** (se 0,72) | -1,34 % / -1,89 % | NÉGATIF |
| | 7 jours | 532 / 479 | **-1,36 %** (se 0,59) | -0,35 % / -2,49 % | NÉGATIF |
| | 30 jours | 504 / 383 | -0,81 % (se 0,63) | -0,10 % / -1,74 % | NÉGATIF |
| FAV_BUY (acheter Yes si Yes >= 90 %) | 1 jour | 125 / 138 | -2,13 % (se 1,58) | -0,43 % / -3,67 % | NÉGATIF |
| | 7 jours | 88 / 58 | +1,19 % (se 1,24) | +0,73 % / +1,88 % | non concluant (n < 300, q = 0,51) |
| | 30 jours | 70 / 40 | +1,73 % (se 1,36) | +1,80 % / +1,62 % | non concluant (n < 300, q = 0,51) |

**Aucun biais favori / outsider exploitable.** La table de calibration (21 cellules, descriptive) montre des marchés **bien calibrés** : les contrats à 0-5 % gagnent 0,7 à 0,9 % du temps pour un prix moyen de 0,8 à 1,1 % (écart entre -0,5 et +0,1 point) ; ceux à 5-10 % gagnent 7,1 à 8,5 % pour un prix de 7,0 à 7,2 % ; au milieu (20-80 %), l'écart reste dans le bruit. Le gain théorique d'un point ou deux ne couvre pas 1 cent de spread (environ 1 % sur un achat à 0,96).
Sous l'hypothèse de calibration parfaite, la vente d'outsiders rapporterait déjà moins que le spread : le rendement observé ne bat que 24 à 81 % des tirages de cette hypothèse nulle, loin des 95 % exigés.

## Observation post hoc, à ne pas exploiter telle quelle

À 1 jour de la fin, les contrats à **10-20 %** gagnent **21,6 %** du temps pour un prix moyen de 14,6 % (écart +7,0 points, intervalle de Wilson [17,7 ; 26,0], n = 371) : « Yes » semble sous-évalué dans cette tranche, ce qui est l'inverse du biais habituel. Cette tranche n'était dans aucune règle pré-enregistrée ; la repérer après coup parmi 21 cellules est de l'exploration, pas une preuve (avec 21 cellules examinées, un ou deux écarts de cette taille apparaissent par hasard).
**Elle ne doit être testée que sur des marchés postérieurs au 2026-09-30, avec une règle écrite avant de les lire** ; les marchés de 2026 déjà téléchargés servent de test uniquement si une règle pré-enregistrée passe la découverte, ce qui n'est pas le cas.

## Limites

- **Spread supposé** (1 cent payé, aucune profondeur de carnet historique) ; taille de position non étudiée ; résolution contestée (UMA) non modélisée ; marchés récents surreprésentés (2025-2026) ; filtre de volume sur la vie entière du marché ; corrélation entre marchés d'un même événement gérée par un jackknife par événement.
- **Marchés à frais activés exclus** (5 011) : ce sont des marchés récents sur lesquels les frais peuvent supprimer toute marge ; la conclusion ne s'applique pas à eux.
- **Ce n'est pas un résultat d'éligibilité** : poursuivre cette piste suppose de pouvoir négocier légalement ces marchés.
