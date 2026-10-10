# Piste E : prime de variance (VIX contre volatilité réalisée), rapport final, 2026-10-09

**Verdict pré-enregistré : critères tenus sur la découverte ET sur le test 2019-2026 (lu une seule fois), pour la vente mensuelle d'un put garanti (E1) et d'un straddle (E2) en proxy Black-Scholes. Mais la prime nette de l'exposition aux actions est modeste (+0,2 % par mois, t = 1,4 sur le test), les prix sont des proxys, et aucune exécution n'est possible dans ce dépôt (options d'indice, hors Polymarket). Aucun code d'exécution.**
Pré-enregistrement : `CLAUDE.md`, « Pré-enregistrement : piste E » (écrit avant tout calcul). Outil : `tools/vrp_study.py` (modes `discover`, `test` à lecture unique avec verrou, `alpha` descriptif) ; tests `tests/test_vrp.py` (dans ctest : Black-Scholes à la main, P&L, levier et drawdown, absence d'anticipation, contrôles positif et nul).
Fichiers : `results/vrp_summary.txt`, `results/vrp_test.txt`, `results/vrp_alpha.txt`. Aucune série brute. **Le test 2019-2026 a été lu une fois (M passe à 10).**

## Ce qui est mesuré

Mois non chevauchants de 21 jours de cotation ; VIX de la clôture d'entrée ; règlement en espèces sur le cours brut du SPY ; options à la monnaie au prix Black-Scholes de **VIX moins 1,5 point** (hypothèse sur la pente) avec un demi-spread de 0,5 point à la vente. E1 = put vendu garanti en espèces (levier 1), E2 = straddle vendu non couvert (levier 0,5).

| | Découverte 1993 -> 2018 (310 mois) | Test 2019 -> 2026 (92 mois) |
|---|---|---|
| Prime de variance brute (VIX - volatilité réalisée à 21 jours) | +3,62 points (médiane +4,43, asymétrie -2,35, pire mois -51 points) | +3,83 points (médiane +4,97, pire mois -33 points) |
| Mois où la volatilité réalisée dépasse le VIX | 18 % | 15 % |
| **E1 put garanti** : excès sur le cash par mois | **+0,559 %**, IC95 [+0,31 ; +0,81], Sharpe 0,79 | **+0,783 %**, IC95 [+0,22 ; +1,34], borne Bonferroni +0,145, Sharpe 0,98 |
| E1 : pire mois, drawdown maximal | -12,7 %, 30 % | -16,5 %, 16 % |
| **E2 straddle** (L = 0,5) | **+0,318 %**, Sharpe 0,94, drawdown 8 % | **+0,249 %**, IC95 [+0,03 ; +0,47], borne Bonferroni **+0,001**, Sharpe 0,61 |
| SPY (comparaison) : excès par mois | +0,48 % | +1,07 % |

Critères (1) à (5) tenus sur la découverte et sur le test, pour les deux stratégies ; E2 passe le test de justesse (borne Bonferroni +0,001 %). Aucun capital annulé, aux leviers 0,5, 1 et 2. Le levier 2 donne un drawdown de 33 à 55 % et un pire mois de -19 à -33 % : proportionnel au levier, Sharpe inchangé.

## Lecture honnête

1. **La prime existe dans les données** : le VIX dépasse la volatilité réalisée de 3,6 à 3,8 points en moyenne et dans 82 à 85 % des mois. C'est une prime de risque (la rémunération du risque de krach, à asymétrie négative), pas une inefficience : les pertes arrivent rarement et fortement (pire mois -51 points de volatilité).
2. **L'essentiel du put garanti est de l'exposition aux actions.** Régression sur le SPY (descriptive, non pré-enregistrée) : E1 a un **bêta de 0,49 à 0,54** ; l'**alpha** vaut **+0,32 % par mois** (t = 4,8) sur la découverte mais seulement **+0,21 % par mois (t = 1,4)** sur le test. E2, qui est neutre au marché, donne le même alpha (+0,32 % puis +0,21 %) avec un bêta de ~0 : **la prime de variance pure est d'environ 2,5 à 3,9 % par an, positive mais pas statistiquement établie sur le test seul.**
   Sur 2019-2026, le put garanti (+0,78 % par mois) a rapporté moins que le SPY (+1,07 %), avec moins de risque ; c'est le profil attendu d'une vente d'options en marché haussier.
3. **Les prix sont des proxys favorables.** Black-Scholes à la monnaie avec VIX moins 1,5 point, sans pente de volatilité, sans chaîne réelle ni spreads réels (demi-spread de 0,5 point sur la volatilité), sans dividende, SPY pour le S&P 500. Sensibilité (E1, L = 1, découverte) : de +0,79 % par mois (VIX sans correction, spread nul) à +0,22 % [-0,04 ; +0,47] (VIX moins 3 points, demi-spread de 2 points) : **l'intervalle contient zéro dès que l'hypothèse sur l'IV à la monnaie est plus sévère de 1,5 point et le spread plus large.**
4. **Hors périmètre d'exécution** : il faut des options réelles sur un courtier (SPY ou SPX), un capital réel, des règles de marge ; aucun code d'exécution n'a été écrit, `LiveExchange` reste un stub.

## Limites

Proxys de prix et de dividende ; SPY (ETF) à la place du S&P 500 ; 26 ans de découverte mais peu de crises (2008, 2020, 2022) ; test de 92 mois ; échantillonnage mensuel non chevauchant (pas de profil par jour de la semaine ni de gestion en cours de mois) ; pas de couverture delta de E2 ; pas de frais de courtage ni de coût d'assignation ; la prime est une rémunération du risque de krach : un drawdown de -16 % en un mois (mars 2020) s'est produit dans le test, et un événement plus grand (pire mois de -51 points de volatilité) existe dans la découverte.
Ce que ce résultat dit : **la source de rendement la plus solide trouvée dans ce projet est une prime de risque classique, pas une inefficience de microstructure ; elle est modeste une fois l'exposition aux actions retirée, et son exploitation sort du périmètre de Polymarket.**


---

# H_VRP : données réelles (indices de stratégie Cboe), phase 1 et phase 3, 2026-10-10

**Verdict pré-enregistré : phase 1 NON ACCEPTÉE. Sur les 4 cellules de décision : 1 NÉGATIVE (WPUT), 3 INCONCLUSIVES (PUT par sous-puissance, PUTY et CNDR par intervalle trop large). L'alpha après bêta des indices à prix réels est proche de zéro (de -0,15 à +0,11 % par mois), loin des +0,25 à +0,30 % par mois de la simulation Black-Scholes de la piste E. Aucun IC95 bootstrap n'exclut zéro. Phase 2 non achetée (non autorisée et règle d'arrêt). Aucun code d'exécution.**
Pré-enregistrement gelé le 2026-10-10 après validation des seuils par l'utilisateur : `docs/VRP_PREREG.md` (avec « Écarts déclarés », dont 4 postérieurs à la lecture, tous listés ci-dessous). Outils : `tools/vrp_indices.py` (`--mode power`, `run` à lecture unique, `placebo2`, `bridge`), `tools/vrp_monitor.py` (suivi prospectif), tests `tests/test_vrp_indices.py` (dans ctest). Fichiers agrégés : `results/vrp_real_*.csv|txt` (aucune série brute Cboe ni French). **M passe à 11 (phase 1), 12 avec le hors échantillon.**

## Puissance (calculée d'abord, variance seulement)

Écart-type du résidu de S1 de 1,6 à 1,9 % par mois (l'hypothèse du brouillon, 2 à 3 %, était trop pessimiste). MDE = 2,80 x erreur-type Newey-West de l'alpha ; sous-puissant si MDE > 0,30 %.

| Cellule | Mois | Erreur-type NW | MDE | Statut |
|---|---|---|---|---|
| PUT (2007-02 -> 2026-08) | 235 | 0,122 % | 0,342 % | **sous-puissant : inconclusif** |
| PUTY (1986-07 ->) | 482 | 0,099 % | 0,277 % | puissant |
| WPUT (2006-02 ->) | 247 | 0,107 % | 0,299 % | puissant (de justesse) |
| CNDR (1986-07 ->) | 482 | 0,098 % | 0,275 % | puissant |
| hors échantillon : PUTR / PTLT / BXN | 307 / 259 / 203 | 0,154 / 0,073 / 0,124 % | 0,432 / 0,205 / 0,346 % | PUTR et BXN sous-puissants |

Même une cellule « puissante » ne détecte qu'un alpha de 0,28 à 0,30 % par mois : l'alpha de X = 0,15 % par mois exigé par le critère de la piste E est à 1,5 erreur-type, soit une puissance de l'ordre de 30 %. Ce que la phase 1 peut établir est donc : « pas d'alpha grand », pas « pas d'alpha ».

## Cellules de décision (S1 : excès de l'indice sur Mkt-RF, échantillon complet)

| | PUT | PUTY | WPUT | CNDR |
|---|---|---|---|---|
| Alpha mensuel | -0,003 % | +0,027 % | **-0,148 %** | +0,108 % |
| IC95 bootstrap (blocs de 6 mois, 5 000 tirages) | [-0,23 ; +0,23] | [-0,15 ; +0,22] | [-0,35 ; +0,07] | [-0,07 ; +0,30] |
| t Newey-West (3 retards) | -0,02 | 0,28 | -1,39 | 1,10 |
| Bêta au marché | 0,58 | 0,42 | 0,51 | 0,13 |
| Sharpe (marché sur la même fenêtre) | 0,56 (0,65) | 0,46 (0,56) | 0,36 (0,66) | 0,35 (0,56) |
| p calibré / p x 11 / BH | 0,50 / 1 / non | 0,47 / 1 / non | 0,65 / 1 / non | 0,38 / 1 / non |
| **Verdict de la cellule** | **inconclusif (sous-puissant)** | **inconclusif** | **négatif** (IC sous 0,15 %, puissance suffisante) | **inconclusif** |

Critères gelés (OUI = tenu) : 1 alpha > 0, IC exclut 0, BH, Bonferroni M = 11 : NON partout. 2 alpha > 0 dans chaque moitié et au moins 2 tiers sur 3 : NON partout (moitiés : PUT +0,10 / -0,08 %, PUTY +0,10 / -0,05, WPUT +0,07 / **-0,37** (IC95 [-0,70 ; -0,04]), CNDR +0,33 / -0,10 ; la seconde moitié est négative partout). 3 alpha > 0 avec demi-spread de 2 points : NON partout. 4 alphas S2, S3, S4 > 0 : seulement CNDR. 5 seuils de pire mois et drawdown : seulement CNDR. 6 bat le 95e centile de la baseline aléatoire : NON partout. 7 signe positif sur 2 des 3 hors échantillon : OUI (voir plus bas).

**Seuils validés par l'utilisateur** (le plus strict de 0,75 x marché et de la valeur absolue), évalués sur la série mensuelle de la cellule :

| | Pire mois | Seuil | Drawdown max | Seuil | Plus longue période sous l'eau |
|---|---|---|---|---|---|
| PUT | -17,7 % (marché -17,1) | -12,8 % : **échoue** | 33 % (marché 50) | 38 % : tient | 29 mois |
| PUTY | -22,1 % (marché -22,6) | -16,9 % : **échoue** | 29 % | 38 % : tient | 39 mois |
| WPUT | -14,1 % (marché -17,1) | -12,8 % : **échoue** | 24 % | 38 % : tient | 42 mois |
| CNDR | -9,9 % (marché -22,6) | -16,9 % : tient | 19 % | 38 % : tient | **191 mois** (le sommet de 2012 n'est pas retrouvé) |

Un put-write à la monnaie perd en un mois autant que le marché (-17,7 % contre -17,1 %, octobre 2008) : le critère « pas pire que 0,75 fois le marché » est fait pour cela et il échoue pour les trois put-write.

## Régressions (spécifications S1 à S4, échantillon complet, alpha mensuel)

| | S1 (Mkt-RF) | S2 (+SMB, HML) | S3 (+Mom) | S4 (terme baissier) | bêta haussier / baissier (S4) |
|---|---|---|---|---|---|
| PUT | -0,003 % | -0,000 % | -0,004 % | +0,70 % | 0,39 / 0,78 |
| PUTY | +0,027 % | +0,003 % | -0,002 % | +0,89 % | 0,17 / 0,65 |
| WPUT | -0,148 % | -0,157 % | -0,157 % | +0,47 % | 0,34 / 0,69 |
| CNDR | +0,108 % | +0,105 % | +0,082 % | +1,01 % | -0,13 / 0,37 |

Les facteurs de taille, de valeur et de momentum ne changent rien. L'alpha de S4 (+0,5 à +1,0 %) est l'ordonnée à marché nul et ne se lit pas comme un gain : **la convexité est le signal important**, le bêta baissier est deux à quatre fois le bêta haussier (court gamma : la vente d'options perd plus dans les baisses qu'elle ne gagne dans les hausses). Les 96 estimations sont dans `results/vrp_real_estimates.csv`, les IC par fenêtre dans `vrp_real_windows.csv`. Contrôle de cohérence descriptif par parité put-call, covered calls : BXM -0,07 % (t = -0,70, n = 293), BXMD +0,10 % (t = 1,68), BXY +0,09 % (t = 1,30) : même ordre de grandeur que les put-write, proche de zéro.

## Comparaison avec la simulation Black-Scholes de la piste E (même fenêtre, mois civils contre périodes de 21 jours : approximatif)

| | Excès moyen indice | Excès moyen E1 (VIX - 1,5) | Bêta indice / E1 | Alpha indice / E1 (VIX - 1,5) | Alpha E1 (VIX - 3) |
|---|---|---|---|---|---|
| PUT (2007 ->) | +0,50 % | +0,62 % | 0,58 / 0,53 | -0,00 % / +0,25 % | +0,08 % |
| PUTY (1993 ->) | +0,36 % | +0,60 % | 0,41 / 0,50 | +0,04 % / +0,30 % | +0,13 % |
| WPUT (2006 ->) | +0,29 % | +0,63 % | 0,51 / 0,53 | -0,15 % / +0,26 % | +0,08 % |

(L'alpha de E1 est celui de la régression sur le SPY de la piste E, l'alpha de l'indice celui de S1 sur Mkt-RF ; CNDR n'est pas comparable à un put garanti.) Les prix réels rapportent en moyenne **0,1 à 0,35 % par mois de moins** que la simulation, à bêta voisin : la prime de la piste E était surestimée par le modèle. La simulation avec VIX moins 3 points (+0,08 à +0,13 %) est plus proche des indices réels.

## Sensibilités (alpha de S1 par mois, entre parenthèses le t Newey-West)

| | Sans coût | Demi-spread 1 pt | **2 pt** | 3 pt | Alpha d'équilibre (points de vol) | Sans les 3 pires mois | Sans 2008-2010 |
|---|---|---|---|---|---|---|---|
| PUT | -0,00 % | -0,12 % | -0,23 % (-1,9) | -0,35 % | **-0,03** (nul sans coût) | +0,14 % (1,4) | +0,01 % |
| PUTY | +0,03 % | -0,09 % | -0,20 % (-2,0) | -0,32 % | **+0,24** | +0,15 % (2,2) | +0,06 % |
| WPUT | -0,15 % | -0,39 % | -0,62 % (-5,9) | -0,86 % | négatif | -0,04 % | -0,19 % |
| CNDR | +0,11 % | -0,01 % | -0,12 % (-1,2) | -0,24 % | **+0,94** | +0,18 % (2,0) | +0,12 % |

Surcoût : 0,115 % par point de volatilité et par mois (mensuel), 0,239 % (hebdomadaire). **À partir d'un demi-spread de 0,24 point de volatilité pour PUTY, 0,94 pour CNDR, l'alpha devient nul** (un demi-spread réel sur les options SPX est probablement de l'ordre d'un point ou plus : non mesuré, aucun bid/ask). **Sans les trois pires mois, l'alpha redevient positif** (+0,14 à +0,18 %) : la prime sert à payer ces mois. Avec momentum (S3) rien ne change. PUTY après son lancement (2019-03 ->, n = 90) : alpha -0,001 % (t = -0,01) ; reconstruit avant (n = 392) : +0,036 % (t = 0,34) : pas de différence discernable, période post-lancement courte.

## Épisodes de stress (pire mois ; perte sur 3 mois ; mois pour retrouver le sommet d'avant ; marché entre parenthèses quand utile)

| | 1987-10 | 1998 | 2002 | 2008 | 2018-02 | 2020 | 2022 |
|---|---|---|---|---|---|---|---|
| PUT | hors couverture | hors | hors | -17,6 % ; -27,6 % ; 27 m (marché -17,1 ; -30,5) | -2,2 % ; -1,5 % ; 4 m | -13,4 % ; **-15,6 %** ; 11 m (marché -13,3 ; -9,4) | -5,9 % ; -8,8 % ; 3 m |
| PUTY | -22,1 % ; -26,6 % ; 25 m (marché -22,6 ; -29,9) | -9,5 % ; +2,2 % ; 4 m | -8,5 % ; -12,9 % ; 24 m | -17,1 % ; -25,9 % ; 32 m | -0,5 % ; +1,1 % ; 3 m | -13,6 % ; **-16,3 %** ; 14 m | -5,0 % ; -6,9 % ; 2 m |
| WPUT | hors | hors | hors | -14,1 % ; -24,2 % ; 20 m | -5,7 % ; -9,0 % ; 43 m | -10,3 % ; -10,6 % ; 19 m | -8,8 % ; -12,3 % ; 3 m |
| CNDR | -9,9 % ; -11,6 % ; 12 m | -5,4 % ; +0,4 % ; 7 m | -7,2 % ; -10,9 % ; 17 m | -7,1 % ; -9,4 % ; 1 m | +1,5 % ; +3,6 % ; 97 m | -4,0 % ; -8,2 % ; 73 m | -4,5 % ; -7,6 % ; 50 m |

Les put-write perdent presque autant que le marché en octobre 1987 et 2008, et **davantage que le marché sur trois mois en mars 2020** (-15,6 et -16,3 % contre -9,4 %). Le condor de fer est protégé par ses ailes (pire perte -9,9 %) mais son rendement est plat après 2012 (191 mois sous le sommet) : pas d'alpha non plus. (Délais de retour au sommet dépendant du sommet précédent, indicatifs.)

## Phase 3 descriptive : distribution des pertes mensuelles (excès de l'indice)

| | p1 | p5 | CVaR 5 % | Asymétrie | Excès moyen | Prime / perte de queue |
|---|---|---|---|---|---|---|
| PUT | -9,8 % | -5,1 % | -8,8 % | -1,62 | +0,50 % | 0,057 |
| PUTY | -9,9 % | -3,3 % | -7,7 % | **-3,42** | +0,34 % | 0,044 |
| WPUT | -9,0 % | -4,9 % | -7,7 % | -1,36 | +0,29 % | 0,037 |
| CNDR | -7,8 % | -3,2 % | -6,1 % | -1,88 | +0,21 % | 0,034 |

Le gain mensuel moyen représente 3,4 à 5,7 % de la perte moyenne des 5 % pires mois : il faut 18 à 30 mois ordinaires pour payer un mois de queue.

**Instruments de livraison (description, aucune recommandation d'achat)** : options sur indice SPX (européennes, réglées en espèces, grande taille), SPXW (échéances hebdomadaires), XSP (mini, dixième de l'indice), options SPY (ETF, style américain, livraison physique, risque d'exercice anticipé), options sur futures E-mini. Traitement fiscal, marge et commissions : dépendent du courtier et du pays, NON VÉRIFIÉS. **Ce que la stratégie ne couvre pas** : le risque de gap et de marge (appel de marge au pire moment), l'exercice anticipé (SPY), la liquidité en crise (les spreads s'élargissent), le coût réel d'exécution (aucun spread ni commission dans les indices), la discipline de tenir après une perte de 15 %, l'impôt.

## Hors échantillon (règle S1 gelée, signe de l'alpha)

| | Sous-jacent / régresseurs | n | Alpha mensuel | IC95 | t NW | Bêta | Puissance |
|---|---|---|---|---|---|---|---|
| PUTR (put RUT) | Mkt-RF et SMB (faute de série RUT) | 307 | +0,068 % | [-0,23 ; +0,36] | 0,44 | 0,63 | **sous-puissant** |
| PTLT (put TLT) | TLT, rendement total Tiingo | 259 | +0,143 % | **[+0,004 ; +0,286]** | 1,95 | 0,41 | puissant |
| BXN (covered call NDX) | NASDAQ100 prix (FRED) | 203 | -0,115 % | [-0,37 ; +0,12] | -0,93 | 0,52 | **sous-puissant** |

2 signes positifs sur 3 : critère 7 tenu, mais c'est un critère de signe, sur deux cellules dont une sous-puissante. PTLT est le seul IC95 qui exclut zéro (borne basse +0,004 %), p unilatérale 0,026, p x 12 = 0,31 : **non significatif après Bonferroni**, descriptif. BXN est un covered call, et l'indice de prix NDX omet les dividendes (biais négatif minime).

## Biais connus, limites, ce qui n'a pas pu être vérifié

- **Reconstruction** : PUTY a pour date de lancement 2019-02-15 (fiche Cboe, recherche du 2026-10-10), date de base 1986-06-30 : **81 % de ses 482 mois (392) sont reconstruits**. Lancement de CNDR et de WPUT : NON VÉRIFIÉ (CNDR est aussi reconstruit depuis 1986). PUT n'a de quotidien que depuis 2007.
- **Exécution dans les indices** : VWAP des transactions entre 11 h 30 et 12 h le jour du roll, sans spread, sans commission, sans slippage. Rendements mensuels de l'indice (fin de mois) et du marché (CRSP total américain, pas le S&P 500) non exactement alignés.
- **Pas de survie** (indices), mais peu de crises (1987 seulement via PUTY et CNDR) et un seul régime d'indice.
- **Temps neuf : non.** Les mois 2019-2026 recoupent ceux de la piste E. Le temps neuf est le suivi prospectif (premier relevé au plus tôt le 2027-04-01, aucune décision statistique avant 2029-10) : `tools/vrp_monitor.py` écrit, **testé seulement sur données tronquées** (fixture), pas lancé.
- **Écarts déclarés postérieurs à la lecture** (`docs/VRP_PREREG.md`, items 10 à 13) : placebos recentrés (lambda 3,50 puis 1,00, aucun verdict ne change, BH ne rejette rien dans les deux cas) ; bruit du contrôle positif 2 % au lieu de 3 % (erreur arithmétique du brouillon) ; reprise du calcul à résumé identique ; puissance hors échantillon.
- **Non vérifié** : conditions d'accès automatisé du site Cboe (texte intégral), fills réels, spreads réels des options SPX (aucune chaîne : phase 2 non autorisée), fiscalité, marges.
- **« Puissant » ne veut pas dire « fort »** : seule WPUT est négative au sens gelé ; PUTY et CNDR ont des intervalles compatibles à la fois avec zéro et avec +0,2 à +0,3 % par mois. La prime brute existe (excès moyen de +0,2 à +0,5 % par mois) mais, après retrait du bêta et d'un coût modeste, elle est indiscernable de zéro.
