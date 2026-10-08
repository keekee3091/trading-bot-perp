# Piste B : horizons longs, pré-enregistrement (2026-10-08)

Source de référence : `CLAUDE.md`, « Pré-enregistrement : piste B ». Ce document en donne la procédure et le calendrier. Outil : `tools/long_horizon.py` ; tests `tests/test_long_horizon.py` (dans ctest).

## Calendrier

| Date | Étape |
|---|---|
| 2026-10-08 | Pré-enregistrement, puissance (`--mode power`), découverte sur l'historique long avant 2019 (`--mode discover`) : liste des finalistes figée dans `results/long_horizon_finalists.json` |
| jusqu'au 2026-12-15 | Aucune lecture du test. Laisser tourner la collecte (perp, `tools/recorder_xvenue.py`) ; télécharger klines, trades et funding du perp après le 2026-09-28 |
| 2026-12-15 et au moins 40 jours de cotation de perp après le gel | **Lecture unique** : `python tools/long_horizon.py --mode test` (refuse avant la date, avant 40 jours, et une seconde fois) |

## Grille et règles (résumé)

- Signaux : TSM (signe du rendement des 60 derniers jours), XSM (quintiles du rendement de 120 jours sans le dernier mois), XSR (inversion du rendement de 20 jours en coupe transversale) ; détentions de 1, 5, 20 et 60 jours de cotation ; entrée à l'ouverture J, sortie à la clôture J+h-1. 12 cellules ; 6 sous-puissantes (20 et 60 jours) ; 6 testées.
- Prime de nuit : reprise de P1 (S2a, S2b), non ré-estimée ; lue avec le holdout.
- Coût : 15,5 bps par aller-retour d'une jambe (31 bps pour le long/short en coupe transversale) plus le funding réel de la durée (0,0625 bps par heure, payé par les longs, reçu par les shorts).
- Découverte : net > 0 unilatéral, jackknife par blocs, 3 plis, BH-FDR 5 %, placebos, rapport effet / coût > 1 ; au plus un finaliste par signal.
- Lecture : test Tiingo 2019-01-01 -> 2026-09-27 des finalistes (Bonferroni avec M = 9 + finalistes, deux moitiés positives, 75 % des tirages aléatoires battus, longs et shorts non négatifs) et validation de l'exécution sur le perp (funding réalisé de même signe et à ±30 % de l'hypothèse, base moyenne par jour inférieure à la moitié de l'effet net par jour, aucune liquidation à L = 2).
- Règle d'arrêt : aucun finaliste ou un critère échoué = conclusion négative ; aucun code d'exécution ; `LiveExchange` reste un stub.

## Pièges

- Les résultats sur sous-jacents long terme ne se transfèrent au perp que si la base et le funding ne les mangent pas : c'est précisément ce que la validation d'exécution vérifie.
- Les détentions de 20 et 60 jours ne sont pas testables avec cet univers (peu de périodes non chevauchantes) : inconclusif, pas négatif. Elles ne peuvent pas non plus être validées sur le perp avant des mois (une détention de 60 jours dure plus longtemps que le holdout disponible en décembre).
- Biais de survie (univers actuel de Polymarket) ; un seul régime pour le perp.
