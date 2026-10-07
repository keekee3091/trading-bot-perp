# P1 : signaux lents et exécution passive (post-only), rapport final, 2026-10-09

**Conclusion : aucun signal n'est positif et robuste. Aucun code d'exécution.** `LiveExchange` reste un stub, aucun ordre réel. Le test Tiingo 2019-2026 et le holdout du perp après le 2026-09-28 sont intacts ; M reste à 9 (aucun finaliste).
Pré-enregistrement : `CLAUDE.md`, « Pré-enregistrement : P1 » (signaux, politiques, bornes, critères, 124 estimations dont 31 cellules d'exécution). Outils : `tools/p1_study.py`, `tools/passive_fills.py` ; tests `tests/test_p1.py` (dans ctest : fills passifs calculés à la main, absence d'anticipation,
horaires avec heure d'été, contrôle positif de l'effet exécutable). Fichiers : `results/p1_partA.csv`, `p1_partB.csv`, `p1_summary.txt` (premier lancement conservé : `*_run1.*`).
**Biais de survie : univers actuel de Polymarket. Historique perp court : 22 jours de cotation. Spread hors séance non mesuré : aucun ordre hors séance.**

## Signaux (listés avant tout calcul)

S1 (inversion en coupe transversale, 34 actions) : S1a rendement de 1 jour tenu 1 jour, S1b rendement de 5 jours tenu 1 jour (la cellule à 7.1 bps par jour), S1c rendement de 5 jours tenu 5 jours. S2 (rapport effet / coût taker > 0.4, horizon >= 1 heure, significatif dans sa phase) :
S2a prime de nuit toutes nuits (+9.55 bps, ratio 0.57), S2b nuits de semaine (+10.15 bps, ratio 0.61). Non simulés, avec leur chiffre : `resid_15` idx_cmd 60 min (0.52, q 0.040, instable), et six cellules sans signification (`resid_60` 0.85 q 0.115, `resid_240` 0.60, `rn_60` 0.43, `mom_20` 0.54, `mom_60` 0.45, séance du lundi 0.60).

## Partie A : l'effet exécutable (longue histoire, avant 2019)

| Signal | Effet clôture-clôture | **Effet exécutable** (entrée ouverture J, sortie clôture J+h-1) | Coût maker / taker | Net maker | Résultat |
|---|---|---|---|---|---|
| S1a | -0.53 bps | **-3.90** (se 3.6) | 5.0 / 31.0 | -8.90 (z -2.5) | non |
| S1b | **+7.09** | **-8.40** (se 3.8) | 5.0 / 31.0 | -13.40 (z -3.5) | non |
| S1c | +12.29 | +6.93 (se 20.7) | 5.0 / 31.0 | +1.93 (z 0.1) | non concluant |
| S2a prime de nuit | +9.55 | +9.55 (se 1.1) | 4.19 / 17.19 | **+5.35** (z 4.9, 3 plis positifs 3.9 / 9.9 / 2.2) | passe |
| S2b nuits de semaine | +10.15 | +10.15 (se 1.3) | 3.59 / 16.59 | **+6.56** (z 5.0, plis 7.1 / 9.6 / 3.0) | passe |

**Le point de conception critique se confirme : l'inversion à 5 jours est un effet de l'écart de nuit.** Mesurée de clôture à clôture elle vaut +7.1 bps par jour ; exécutée comme on peut l'exécuter (entrée à l'ouverture, qui ne capte pas l'écart de nuit) elle vaut **-8.4 bps** (net -13.4, z = -3.5) : au cours de la
séance, les perdants de la veille continuent de baisser (momentum), et le signal n'est jamais retourné après coup. L'exécution passive n'a rien à sauver ici. (Approximation de la longue histoire : ouverture et clôture officielles au lieu de 9h35 et 15h55 ; l'exécution exacte est mesurée sur le perp.)
La prime de nuit S2 survit, car elle se joue entre 15h55 et 9h35 : le coût passe de 17 à 4 bps avec des ordres maker, et le net est de +5 à +7 bps par nuit si les ordres sont exécutés au prix du signal.

## Partie B : exécution passive sur le perp (2026-08-26 -> 09-25, 22 jours de cotation, 30 actions)

Simulateur de fills sur les trades (meilleur bid / ask = proxy du dernier trade de l'agresseur opposé), bornes optimiste et conservatrice (file de 1 000 de notionnel, décisive), ordres de 1 000, frais maker 1.25 bps, funding réel, résultat PAR SIGNAL ÉMIS (non-exécutés à zéro).
- **Taux d'exécution passif : 4 à 13 %**, délai de 6 à 106 minutes. Les actions perp sont très fines : la plupart des ordres limites ne sont jamais servis.
- **Sélection adverse** (markout du prix 10 minutes après un fill maker, borne conservatrice) : **-24 à -32 bps pour S2** (-44 à -74 bps à 1 heure), -51 à -58 bps pour S1. Un ordre limite n'est servi que lorsque le prix traverse notre niveau, donc surtout quand il continue ensuite dans le sens défavorable.
- **S2, net par signal émis, borne conservatrice** : entrée 30 minutes avant la clôture avec repli taker : **+2.15 bps** [-8.8, +16.2] (S2a) et +0.95 [-10.6, +17.5] (S2b) ; sans repli : -2.9 et -2.7 ; entrée 2 heures avant : **-8.4 [-15.3, -1.3] et -11.1 [-18.5, -3.7]** (significativement négatif). Aucun intervalle Bonferroni (31 cellules) n'exclut zéro. Borne optimiste : +5.5 bps à 30 minutes,
  négatif à 2 heures. Base taker : +7.5 [-21, +40] (S2a), -1.9 (S2b). **Non concluant** (optimiste positive seule, conservatrice non robuste), et la qualité de fill est le vrai obstacle.
- **Point mort (qualité de fill minimale)** : S2 tolère une sélection adverse de **A\* = +5.35 bps (S2a) et +6.56 bps (S2b)** (effet par transaction moins coût maker) ; on observe 31 bps : **5 fois trop**. Taux de fill minimal pour 1 bps par signal : impossible (le taux de fill n'y change rien : le net par fill est négatif). Il faudrait que le markout à 10 minutes d'un fill maker soit
  meilleur que -5 bps, c'est-à-dire que le prix ne bouge pas contre nous après être servi : exclu dans un marché si fin.
- **S1** : S1a négatif ; S1b positif sur ces 22 jours (+10.4 bps par signal, [1.2, 21.5], Bonferroni bas -3.2) mais contredit les 25 ans de la partie A (-8.4 bps, z = -3.5) : l'erreur-type de 10 à 35 bps par signal sur 22 jours rend ce résultat indiscernable du bruit ; il ne passe pas le critère (1) (partie A). S1c : [-17, +85], non concluant.
- **Puissance** : l'erreur-type du net par signal est de 10 à 35 bps pour des effets attendus de quelques bps : la partie B ne peut pas trancher le signe d'un net de quelques bps ; elle mesure surtout le taux de fill, le délai et la sélection adverse, et c'est là qu'elle conclut.
- **Levier** (politique c, T = 2 h, borne conservatrice, descriptif) : S2a : 1x equity 0.982, 2x 0.965, 5x 0.915 (drawdown 9.2 %), aucune liquidation : le levier amplifie une perte ; S1c : 2 liquidations à 5x.

## Limites

Biais de survie (l'effet de nuit est probablement surestimé), 22 jours de perp (une seule saison de résultats, un régime), proxy du carnet par les trades (le meilleur bid réel est inconnu, le fill conservateur est un modèle), taker proxy non fiable à 44-52 % de disponibilité, spread hors séance non mesuré (aucun ordre hors séance), file d'attente en notionnel.
Ce qui changerait la conclusion : un carnet réel (l'enregistreur, plusieurs semaines) pour mesurer les vrais fills passifs de la prime de nuit, avec un holdout neuf ; sans quoi, 17 bps de coût taker contre 10 bps d'effet, et 5 bps d'effet net maker réduits à zéro par la sélection adverse.
