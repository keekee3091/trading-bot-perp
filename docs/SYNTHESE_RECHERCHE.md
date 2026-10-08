# Bot perps Polymarket : synthèse de recherche (version corrigée, 2026-10-08)

## Résumé

Aucune des dix familles de stratégies testées (momentum court, momentum long en panel, market making, prime mark/index, décalage avec Binance, momentum de séries temporelles, grille large, actions, résultats trimestriels, exécution passive) ne montre un edge positif et robuste net de coûts sur les perps Polymarket.
**Aucun code d'exécution n'a été écrit, aucun ordre réel n'a été passé** (`LiveExchange` reste un stub). La conclusion vaut pour ces signaux, ces horizons et ces coûts, sur environ 4 mois d'historique perp et un seul régime de marché ; elle ne prouve pas qu'aucun edge n'existe.

Le levier n'a jamais aidé : il amplifie la perte quand l'edge est nul ou négatif (Kelly estimé négatif). Deux résultats sortent positifs sans être exploitables :
- le momentum de séries temporelles sur sous-jacents non crypto (Sharpe net +0,31 en test, t = 1,07, 4 critères sur 7 échoués) ;
- la prime de nuit des actions (environ +10 bps par nuit sur plusieurs décennies, univers croissant de quelques titres à 34), qui repose sur un univers biaisé vers les gagnantes actuelles et **n'est pas démontrée réalisable en exécution passive** (sélection adverse 5 fois trop forte sur 22 jours de perp).

**Décision recommandée** : archiver le dépôt comme cadre de recherche (cœur C++, protocole de validation, note de décision) et ne rouvrir que sur une hypothèse nouvelle, écrite avant de voir les données, avec du temps neuf ou une source externe légale.

## Ce qui a été construit

Un moteur C++17 (`perpcore`) indépendant de la plateforme, validé par 22 tests ctest avec `-Werror`, et des outils Python (stdlib) pour les données ; un premier jet Python archivé dans `legacy_py/`.
- `perpcore` : types, signal, risque (Kelly, sizing, plafond de levier lié à la liquidation), sorties, exchange papier (spread, slippage, frais, funding, liquidation isolée), machine à états `PerpBot`.
- `perp_backtest`, `perp_sweep` (grille multi-thread, résultats identiques à 1 ou N threads), `perp_validate`, `perp_panel`.
- Outils : téléchargement de bougies, trades, funding, Tiingo, SEC, enregistreur de marché en lecture seule, études par famille, simulateur de fills passifs.
- Garde-fous : `LiveExchange` lève une exception ; aucun secret dans le dépôt (`.env` ignoré) ; aucune règle de signal jamais inversée après coup.
- Tests : valeurs calculées à la main (prix de liquidation, PnL net, fills passifs), identité d'equity à 1e-9, déterminisme, sens du signal sur séries synthétiques, contrôles positifs et nuls, absence d'anticipation, horaires avec heure d'été.

## Méthode

Même protocole pour chaque famille : grille et critères écrits dans `CLAUDE.md` avant tout résultat ; un seul jeu de paramètres commun ; découpe chronologique avec test touché une fois ; nombre de tests annoncé et correction (Bonferroni, M de 4 à 9 ; Benjamini-Hochberg pour les grilles larges) ; comparaison à buy and hold et à des entrées aléatoires de même rythme ; longs et shorts séparés ; plomberie sur données synthétiques ; règle d'arrêt. Les fenêtres de test de plusieurs familles se recoupent, ce qui est signalé dans chaque rapport.

## Résultats par famille

| Famille | Données | Résultat hors échantillon | Verdict |
|---|---|---|---|
| Momentum court (1 à 5 min), crypto | BTC, ETH, SOL, 126 à 129 jours, 540 points | Sharpe -46,3 / -41,3 / -47,1 ; PnL net -459 / -463 / -720 sur 1 000 | Négatif : rendement futur après signal de -3 à +0,6 bp pour 14 bps de coût |
| Momentum long en panel | 15 instruments, 64 points | Sharpe -7,04 ; -0,87 % contre +4,26 % pour le marché ; alpha -12,8 % par an (t = -1,94) | Négatif : 2 instruments positifs sur 15 |
| Market making passif | 21 instruments, 40,7 jours de trades | Conservatrice -0,57 %, optimiste -0,81 % | Négatif, abandonné : le prix s'éloigne de 7 à 11 bps contre chaque fill |
| Prime mark/index | funding publié comme proxy, 28 instruments | -22,7 bps net par trade (154 trades) | Négatif : 83 % des dislocations encore hors bande 4 h plus tard |
| Décalage avec Binance | 5 cryptos contre Binance spot 1 s | -9,8 bps net par trade (234 trades) | Négatif : 10 bps de Binance donnent environ 1,5 bp sur le perp |
| Momentum de séries temporelles | sous-jacents non crypto, 1927-2026 | Sharpe net +0,31 (t = 1,07) contre +0,56 volatilité égale long seul | Non concluant : 3 critères sur 7 réussis |
| Grille large (étages 1 et 2) | 894 cellules : 473 exclues (puissance), 18 indisponibles, 403 testées | 55 passent BH-FDR, 42 stables ; seul candidat : Binance 1 min vers perp 5 min (15,2 bps contre 13,0 de coût) ; holdout net -11,4 bps par trade (601 trades), brut +8 bps tombé à +0,65 sur prix imprimés | Négatif |
| Actions (Tiingo) | 34 actions, 13 cellules testées sur 41 | Le perp explique l'écart d'ouverture (bêta 0,70, R² 0,71 ; week-ends 0,89 et 0,88). **Retour à la moyenne à 5 jours : +7,1 bps par jour clôture-clôture, mais -8,4 bps exécutable** (voir P1). Prime de nuit +9,5 bps contre 16,8 de coût taker | Négatif : le retour à la moyenne n'est pas exécutable, la prime de nuit est réelle mais sous le coût taker |
| Résultats trimestriels (H4) | 1 500 8-K, 587 événements de découverte, 15 cellules | Effet minimal détectable 540 à 1 050 bps contre une limite de 47 à 173 ; H4c sur 12 nuits : bêta 0,98, R² 1,00 | **Non testable** (ni succès ni échec) ; le perp prend l'annonce avant l'ouverture |
| Exécution passive (P1) | partie A : longue histoire ; partie B : 22 jours de trades perp | voir ci-dessous | Voir ci-dessous |

### P1 en détail (verdict par signal)

- **S1a et S1b : négatifs, avec de la puissance** (25 ans, erreur-type de 3,6 à 3,8 bps par jour) : exécutable, S1a vaut -3,9 bps et S1b -8,4 bps (z = -3,5), contre -0,5 et +7,1 de clôture à clôture. Le signal n'est jamais retourné. S1b paraît positif sur les 22 jours de perp (+10,4 bps par signal, borne Bonferroni basse -3,2), ce qui contredit les 25 ans et relève du bruit.
- **S1c : non concluant** (+6,9 ± 20,7 bps).
- **S2 (prime de nuit) : non concluant sur le signe du net.** Partie A : net maker +5,35 et +6,56 bps par nuit (z ≈ 5, 3 plis positifs). Partie B (borne conservatrice, file de 1 000) : taux de fill de 4 à 13 %, net par signal émis de -11 à +2 bps, tous les intervalles Bonferroni contenant zéro, et -8,4 et -11,1 bps significativement négatifs à T = 2 h. Sélection adverse mesurée après un fill maker : -24 à -32 bps à 10 minutes, contre 5,4 et 6,6 bps tolérés (environ 5 fois trop). **Cette mesure repose sur quelques dizaines de fills, sans intervalle de confiance sur les markouts : elle est cohérente avec le net négatif à 2 h, mais forte plutôt que démontrée.** Taux de fill minimal pour 1 bps par signal : impossible.
- **Puissance de la partie B** : erreur-type de 10 à 35 bps par signal pour des effets de quelques bps : elle ne tranche pas le signe d'un net de quelques bps. **Conclusion de la règle pré-enregistrée : aucun signal positif et robuste ; S2 non concluant.**

## Levier, coûts, funding

- Le levier ne crée pas d'edge : sur le panel il passe de -2,6 % à 1x à -25,6 % à 10x en test (drawdown 29,9 %), Kelly hors échantillon -13 ; sur P1, S2 à 5x : equity 0,915 ; S1c : 2 liquidations à 5x.
- Coûts : taker 0,04 %, maker 0,0125 % (palier 0), environ 14 bps d'aller-retour avec spread et slippage ; 0,15 % de la marge à 1x, 1,46 % à 10x. MMR = 0,5 / levier max (doc).
- Funding : hors crypto, surtout une composante d'intérêt d'environ 5,5 % par an payée par les longs ; excès hors intérêt seulement sur NAS100 et WTI (15 à 21 % par an), instable.
- Perp contre sous-jacent : NAS100 suit de près (corrélation quotidienne 0,996) mais 47 % de sa variance tombe hors séance ; le WTI ne suit pas le spot (niveau -3,2 %, corrélation 0,84), il référence un contrat à terme.
- Récompenses de liquidité : budget de 75 000 $ par jour, éligibilité à 1 % du volume maker sur 7 jours ; taille des pools non documentée, aucun gain estimé.

## Limites

- Environ 4 mois d'historique perp, un seul régime haussier, marchés très fins ; fenêtres de test de 5 à 23 jours qui se recoupent entre familles.
- Aucun historique de carnet ni d'index : file d'attente, spread passé et profondeur non identifiables (bornes de fill, proxys par les trades). Spread simulé de 2 bps issu d'un relevé ponctuel en séance, non calibré hors séance ni le week-end. Sessions inférées, jours fériés ignorés, ADL non modélisé.
- Sous-jacents : or et argent seulement en moyennes mensuelles, WTI et Brent en spot ; actions via Tiingo (plan gratuit, licence « Internal Use Only ») avec un **biais de survie** (univers actuel de Polymarket) ; Stooq, LBMA et Yahoo exclus pour raisons d'usage. Hyperliquid (trade.xyz) : au plus un an d'historique.
- Plusieurs tests sont sous-puissants (H4, partie B de P1, H1b) : ils sont inconclusifs, pas négatifs.
- Hygiène : la clé Tiingo a été collée dans une conversation et doit être régénérée ; aucune donnée brute Tiingo ou SEC ne doit être redistribuée.

## Options de suite

1. Archiver le dépôt comme cadre de recherche : cœur C++, protocole, `docs/DECISION_NOTE.md`, `results/`.
2. Laisser tourner `tools/recorder.py` (index, mark, funding, carnet) sur une machine toujours allumée : seule source d'historique de carnet et holdout vierge. Mesurer avec lui les vrais fills passifs de la prime de nuit.
3. Rouvrir H1b et H4 dans 2 à 3 mois (plus de nuits perp, donc plus de puissance), avec un holdout neuf après le 2026-09-28 ; compléter or, argent et contrats à terme WTI et Brent.
4. Ne rouvrir que sur une inefficience mesurée supérieure au coût aller-retour avant d'être tradée, hypothèse pré-enregistrée, temps neuf, test hors échantillon jamais utilisé. Même règle d'arrêt.
