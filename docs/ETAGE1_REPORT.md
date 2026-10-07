# Grille d'hypothèses large, étage 1 (prédictibilité brute) et étage 2 (tradabilité) : rapport final, 2026-10-07

**Conclusion : négative. Aucun code d'exécution.** Sur 894 cellules planifiées, 403 testées, 55 passent le FDR, 42 sont stables sur
3 plis chronologiques, **1 seule** a un écart de déciles supérieur au coût aller-retour (Binance mène le perp, crypto, horizon 5 minutes). Testée à l'étage 2 sur le holdout
(touché une fois), avec exécution sur prix imprimés et coûts réels : **net -11.4 bps par trade, t = -12.3 (601 trades), bat 12 % des entrées aléatoires.**
La règle d'arrêt s'applique : pas de `perp_paper`. `LiveExchange` reste un stub, aucun ordre réel.

Pré-enregistrement complet (grille, règles, critères, étage 2) : `CLAUDE.md`, section « Pré-enregistrement : grille d'hypothèses large, étage 1 ». Outils :
`tools/grid_stage1.py` (modes `plan`, `power`, `run`), `tools/grid_stage2.py`, tests `tests/test_grid_stage1.py` (dans ctest).
Toutes les cellules, les nulles comprises : `results/grille_etage1.csv` (894 lignes), IC par instrument `results/grille_etage1_instruments.csv`, cartes de chaleur
`results/heatmap_F1.svg` à `heatmap_F7.svg`, puissance `results/etage1_power.csv`, synthèse `results/etage1_summary.txt`, étage 2 `results/etage2_report.txt`.

## 1. Combien de cellules, combien passent le FDR, faux positifs attendus, placebos

| | Nombre |
|---|---|
| Cellules planifiées (67 variables, 149 couples variable x groupe, 6 horizons) | **894** |
| Exclues pour sous-puissance (règle écrite avant tout résultat, MDE > 3 x coût) | 473 |
| Indisponibles (variable constante, indicateur sans observation, moins de 3 instruments utilisables) | 18 |
| **Testées** (famille du BH) | **403** |
| p < 0.05 non corrigé | 86 (21 %), contre 20 attendues sous l'hypothèse nulle |
| **Passent le FDR, BH 5 %** | **55** (dont 44 crypto, 9 equity, 2 idx_cmd) |
| Faux positifs attendus parmi ces 55 | au plus 5 %, soit environ 3 |
| Stables sur 3 plis (signe de l'IC et de l'écart de déciles identique dans les 3 plis) | 42 |
| Ratio de tradabilité > 1 (écart de déciles / coût aller-retour) | **1** |

**Placebos** (mêmes 403 cellules, deux variantes) : variable décalée d'un retard aléatoire de 2 à 10 jours, **4.4 % de p < 0.05** (nominal 5 %), 1.3 % de p < 0.01, **0 découverte BH** ;
variable mélangée par blocs de 120 minutes, **4.0 %** de p < 0.05, 1.4 % de p < 0.01, **0 découverte BH** ; |z| maximum 3.6 et 3.4, écart-type robuste de z de 0.94 et 0.89. Les erreurs-types
(jackknife par blocs de jours, dispersion entre instruments) sont donc **bien calibrées, pas optimistes** : facteur d'étalonnage lambda = 1.00, le BH avec et sans étalonnage donne les mêmes 55 découvertes.

**Contrôle positif** (`tests/test_grid_stage1.py`) : une saisonnalité intrajournalière injectée (+0.8 puis -0.8 bps) est retrouvée avec |z| > 4 et le bon signe ; une autocorrélation injectée de 0.2 est retrouvée
(IC > 0.02, z > 4) ; sur du bruit pur, aucune cellule ne survit au BH et moins de 20 % ont p < 0.05 ; l'absence d'anticipation est vérifiée sur 25 variables en tronquant le futur.

## 2. Cellules retenues par le FDR : taille de l'effet contre le coût, stabilité, puissance

**Puissance (écrite avant résultat, `results/etage1_power.csv`).** Le MDE (écart de déciles détectable à p = 0.001, puissance 80 %) vaut 1 à 10 bps à 1 et 5 minutes, et dépasse
3 fois le coût (12 à 16 bps) au-delà : **les horizons de 1 h (sauf idx_cmd), 4 h et 1 jour ne sont pas testables avec 14 à 150 jours de données**, 473 cellules sont exclues, dont tous les
horizons longs des cryptos et des actions. Cette étude ne dit rien de ces horizons (la famille B de `CLAUDE.md` les avait testés de façon plus directe). Les cellules F1 et F7 crypto n'ont que 14 jours et 3 à 5 instruments.

**Où sont les 55 découvertes** (aucune à 1 jour, 4 h, 1 h hors idx_cmd : sous-puissance) :

| Famille | testées | FDR | stables | passent l'étage 1 | max \|IC\| | plus grand ratio parmi les FDR |
|---|---|---|---|---|---|---|
| F1 flux d'ordres | 42 | 14 | 14 | 0 | 0.161 | 0.26 |
| F2 prix | 92 | 10 | 3 | 0 | 0.051 | 0.36 |
| F3 régime | 54 | 0 | 0 | 0 | 0.036 | |
| F4 funding et base | 46 | 6 | 5 | 0 | 0.320 | 0.77 |
| F5 calendrier | 61 | 0 | 0 | 0 | 0.031 | |
| F6 inter-actifs | 84 | 11 | 6 | 0 | 0.077 | 0.60 |
| F7 Binance (crypto) | 24 | 14 | 14 | **1** | 0.240 | **1.17** |
| F8 carnet | non testé (enregistreur : 2 jours, après le gel du holdout) | | | | | |

Découvertes par groupe et horizon (FDR / testées) : crypto 1 min 21/62, 5 min 14/62, 15 min 9/60 ; equity 1 min 7/46, 5 min 2/34 ; idx_cmd 1 min 1/36, 1 h 1/34, le reste 0.
**Tout ce qui existe est à 1 à 15 minutes, surtout en crypto, et plus de 70 % des IC significatifs sont positifs (continuation).**

Cellules stables les plus proches de couvrir le coût (écart de déciles D10 - D1 en bps, coût aller-retour du groupe, ratio, IC) :

| Famille | Variable | Groupe | h | IC | z | Écart de déciles | Coût | Ratio |
|---|---|---|---|---|---|---|---|---|
| F7 | rendement Binance 1 min | crypto | 5 min | +0.181 | 13.5 | +15.2 | 13.0 | **1.17** |
| F7 | écart Binance - perp, 5 min | crypto | 5 min | +0.148 | 5.9 | +10.0 | 13.0 | 0.77 |
| F7 | écart Binance - perp, 1 min | crypto | 5 min | +0.160 | 8.5 | +8.9 | 13.0 | 0.69 |
| F6 | rendement ETH passé 1 min | crypto | 5 min | +0.061 | 3.3 | +8.2 | 13.7 | 0.60 |
| F7 | écart Binance - perp, 5 min | crypto | 15 min | +0.102 | 4.5 | +7.4 | 12.4 | 0.59 |
| F7 | rendement Binance 1 min | crypto | 1 min | +0.240 | 21.4 | +7.6 | 13.4 | 0.56 |
| F6 | rendement BTC passé 1 min | crypto | 5 min | +0.050 | 6.6 | +7.8 | 13.8 | 0.56 |
| F2 | retour à la moyenne 4 h normalisé | crypto | 15 min | -0.039 | -3.7 | -4.7 | 13.2 | 0.36 |
| F1 | déséquilibre signé 10 s à 15 min, séquence d'agresseurs | equity, crypto | 1 à 5 min | +0.03 à +0.16 | 4.6 à 12 | +1 à +3.5 | 13.5 à 16.1 | 0.06 à 0.26 |

Non stable mais plus grand IC de toute la grille : **F4 `basis_ml` (écart mark - dernier prix) en equity à 1 min : IC +0.32**, z = 21, ratio 0.77, mais son signe change dans un pli : c'est un artefact de
prix périmés (le mark bouge avec le sous-jacent, le dernier prix imprimé non), pas une prédiction exploitable.

Lecture : le **flux d'ordres** prédit le prix à 1 minute (IC 0.11 à 0.16, signe stable) mais l'écart de déciles n'est que de 2 à 3 bps, un cinquième du coût. **Binance mène le perp** de façon très significative
et stable (z jusqu'à 21, les 3 plis du même signe, 15 bps entre déciles extrêmes à 5 minutes), c'est la seule cellule au-dessus du coût. **Le funding** (niveau, variation) ne prédit presque rien (|IC| 0.01), de même que la phase dans l'heure de règlement
hors un effet equity à 5 min de 3 bps. **Le régime de volatilité et le calendrier** ne prédisent rien : F3 \|z\| maximum 2.6, F5 \|z\| maximum inférieur à 2.

## 3. Étage 2 : la seule cellule candidate, testée une fois sur le holdout

Cellule : F7, rendement passé de Binance sur 1 minute, groupe crypto (BTC, ETH, SOL, XRP), horizon 5 minutes. Étage 1 : D1 = -7.14 bps, D10 = +8.07 bps ; côté retenu : haut, sens ACHAT, figés d'avance
(règle : acheter quand le rendement Binance de la dernière minute dépasse le décile supérieur de la fenêtre de découverte, sortie 5 minutes plus tard, pas de stop). Exécution sur prix imprimés (entrée au premier trade
d'un agresseur acheteur 1 s après la fin de la minute, sortie au premier trade d'un agresseur vendeur 1 s après l'horizon), frais 4 bps x2, slippage 2 bps x2, funding réel.

| Fenêtre | Trades | Net moyen | Brut moyen | t | Gagnants |
|---|---|---|---|---|---|
| Train 2026-09-14 -> 09-23 | 932 | -7.43 bps | +4.58 | -7.66 | 30.7 % |
| Validation -> 09-28 | 382 | -8.98 bps | +3.03 | -6.34 | 29.8 % |
| **Test (holdout) 09-28 -> 10-05** | **601** | **-11.36 bps** | **+0.65** | **-12.31** | 25.0 % |

Les cinq critères pré-enregistrés échouent (net > 0 : non ; Bonferroni M = 9 : non ; bat 75 % des tirages aléatoires : 12 % seulement, la baseline aléatoire fait -10.2 bps ; côté tradé >= 0 : non ; hors 5 meilleurs trades > 0 : non).
Par instrument en test : BTC -9.3, ETH -10.1, SOL -15.5 (XRP, 4 trades). **Levier** (test) : 1x -0.11 % de la marge par trade (coût frais et slippage 0.12 % de la marge), equity 0.50, drawdown 50 % ; 2x equity 0.25 ;
5x equity 0.03, drawdown 97 % ; volatilité cible 10 % : equity 0.86, 20 % : 0.74 ; **0 liquidation** (les mouvements de 5 minutes sont petits) : le levier ne fait qu'amplifier la perte.

**Pourquoi l'effet disparaît entre les deux étages.** Le brut tombe de +8 bps (écart de déciles côté haut à l'étage 1, mesuré à partir du dernier prix imprimé) à +0.65 bps (test, exécution sur prix imprimés) : la plus grande part de
« la prédiction » de l'étage 1 est le rattrapage d'un dernier prix périmé, que l'on ne peut pas acheter, et le reste est inférieur à 12 bps de frais et de slippage. Rien n'invalide la relation elle-même (Binance mène bien le perp, cohérent avec la famille D :
corrélation croisée de 0.15 à +5 s) : elle n'est pas capturable par un preneur de liquidité à ce coût.

## 4. Carte de ce qui existe et pourquoi cela ne couvre pas les coûts

- **Corrélations réelles mesurées (à 1 à 15 minutes)** : Binance vers perp (IC 0.05 à 0.24), BTC et ETH vers les autres cryptos (0.03 à 0.08), flux d'ordres vers prix (0.04 à 0.16), position dans la fourchette et rendement normalisé de 1 à 4 h vers le prix 15 minutes plus tard en crypto (retour à la moyenne, IC -0.03 à -0.05), mark contre dernier prix en actions (0.32, artefact).
- **Taille en bps** : au mieux 15 bps entre déciles extrêmes (cellule F7 ci-dessus), 5 à 10 bps pour les meilleures autres, 2 à 4 bps pour le flux d'ordres, 1 bps ou moins pour le funding. **Une jambe seule rapporte au plus 62 % du coût** (rapport de jambe 0.62), 29 % à 1 minute.
- **Coût aller-retour de 12 à 16 bps** (frais 4 bps x2, slippage 2 bps x2, spread 0.1 à 4 bps) : les effets mesurés sont des **fractions** de ce coût, et à l'exécution sur prix imprimés la plus grande est réduite à quelques dixièmes de bps. Les effets les plus significatifs sont aussi les
  plus courts (1 minute), là où le coût pèse le plus.
- **Ce que l'étage 1 ne peut pas dire** : les horizons de 1 h à 1 jour (sous-puissance), le carnet (F8, 2 jours d'enregistreur seulement, réservés au holdout), l'index (pas d'historique), le funding et les liquidations Binance (non récupérés), les actions hors des 7 plus liquides,
  le rendement par rapport à un coût plus bas (maker, hors périmètre).

## 5. Limites, écarts déclarés, honnêteté

- **Écarts au pré-enregistrement** (déclarés dans `CLAUDE.md`, avant l'étage 2) : (1) ex aequo dans les déciles, cellules écartées à tort au premier lancement (67 sur 421), corrigé et relancé ; (2) ancrage des plis F1 crypto (HYPE a des trades depuis le 26 août mais la fenêtre F1 crypto commence le 14 septembre), corrigé et relancé : le seul effet est de rendre « stables » 10 cellules F1
  de plus, aucune ne passe le ratio > 1 ; (3) exécution de l'étage 2 sur prix imprimés au lieu de la clôture, décidée avant le résultat. Dans chaque cas la même et unique cellule candidate sort avant et après. Les sorties de chaque lancement sont conservées (`results/*_run1.*`, `*_run2.*`).
- **Holdout** : la cellule candidate a consommé le holdout du 2026-09-28 au 2026-10-05 (7 jours). M passe à 9 pour Bonferroni. Le même marché et les mêmes jours ont servi aux tests précédents (A à D) avec d'autres hypothèses : déclaré.
- **Mesure** : dernier prix imprimé, périmé dans les minutes creuses, rebond bid-ask : l'étage 1 surestime des effets de très court terme (cf. étage 2). Jackknife par blocs de jours avec peu de jours (14 à 150) : étalonné par placebos, pas démontré en général.
- **Puissance** : MDE calculé avec l'écart-type (queues épaisses ignorées), donc optimiste. Exclure 473 cellules est un choix écrit d'avance, qui réduit le nombre de comparaisons mais retire tout verdict sur les horizons longs.
- **Seul résultat de ce travail** : sur l'ensemble de l'espace testé, rien n'est exploitable par un preneur de liquidité. Cela ne dit rien du carnet, de la latence sous la seconde, de l'exécution maker, de 1 h à 1 jour sur davantage de données, ni des actions illiquides.
