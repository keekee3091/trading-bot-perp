# H4 : résultats trimestriels (SEC EDGAR + Tiingo), rapport final, 2026-10-08

**Conclusion : non testable avec cet univers. Aucun étage 2, aucun code d'exécution.** `LiveExchange` reste un stub, aucun ordre réel. Pré-enregistrement : `CLAUDE.md`, « Pré-enregistrement : H4 ». Outils : `tools/fetch_sec.py`, `tools/earnings_study.py`,
tests `tests/test_earnings_study.py` (dans ctest, réseau simulé, agent factice). Fichiers agrégés : `results/earnings_stage1.csv` (les 15 cellules), `earnings_events.csv` (comptes par action), `earnings_h4c.csv`, `earnings_power.json`, `earnings_summary.txt`.
Aucune donnée brute Tiingo ni SEC dans `results/` ou `docs/` ; `data/sec/` et `data/tiingo/` sont ignorés par git ; le contact SEC est lu dans `.env` et n'est écrit nulle part. **Biais de survie : univers actuel de Polymarket.**

**Accès SEC** : en-tête User-Agent avec contact réel, au plus 10 requêtes par seconde (5 utilisées), cache local.

## Événements couverts

1 500 8-K contenant l'Item 2.02 pour 28 des 34 actions (période 2004 -> 2026). Zéro pour ARM, ASML, BABA, NBIS, SKHY, TSM (émetteurs étrangers, formulaire 6-K). STRC partage le CIK de MSTR : 73 doublons exclus. Classement par l'heure d'acceptation en heure de l'Est
(avec heure d'été) : 75 déposés pendant la séance (exclus), 123 ambigus (la date d'événement déclarée diffère de la date de dépôt : exclus), **1 229 retenus**, dont **587 avec toutes les fenêtres avant 2019 (AMC 576, BMO 11)**. Cas ambigu résiduel : l'heure d'acceptation du 8-K n'est pas l'heure du communiqué.

## Ce qui est mesuré

- **H4a (dérive après annonce) et H4b (rendement avant annonce) : 15 cellules, toutes sous-puissantes.** Écart minimal détectable de 538 à 1 054 bps pour une limite de 47 à 173 bps (3 fois le coût). Les rendements à 5-20 jours des 27 actions (dont NVDA, AMD, TSLA, MSTR, COIN) ont un écart-type de plusieurs centaines de bps ; 576 événements poolés
  ne permettent de détecter que des effets de l'ordre de 500 bps. **La dérive après annonce de la littérature (100 à 300 bps) n'est donc ni confirmée ni infirmée.** Le groupe BMO (11 événements) est inexploitable.
- **H4c (perp, exploratoire, sous-puissant)** : sur 12 nuits d'annonce après clôture dans les 70 jours de perp, le mouvement du perp hors séance explique l'écart d'ouverture réel presque entièrement (**bêta 0.98, R² 1.00**, écart-type de l'écart 844 bps) contre **bêta 0.66, R² 0.66 les autres nuits** (836 nuits).
  Le perp cote 24 h sur 24 : l'annonce est pricée avant l'ouverture. 12 événements : indicatif seulement. Aucun BMO dans la fenêtre perp.
- Rappel : on ne peut agir qu'APRÈS la publication ; la réaction initiale est déjà dans le prix du perp. Coûts non utilisés (aucune cellule testée).

## Limites

Univers (27 actions, dominé par des technologiques qui publient après la clôture), 587 événements de découverte, volatilité élevée de certaines actions, biais de survie, heure d'acceptation différente de l'heure du communiqué. Le test 2019-2026 est intact, M reste à 9.
Un univers de plusieurs centaines d'actions ou un modèle d'écart anormal par rapport au marché (réduisant l'écart-type) permettraient de tester la dérive : hors périmètre et non disponible gratuitement.
