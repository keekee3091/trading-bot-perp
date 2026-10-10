# H_VRP : pré-enregistrement

**GELÉ le 2026-10-10 après validation des seuils par l'utilisateur.** Décision de l'utilisateur, message authentique dans la session : « Je valide les seuils » (pire mois : pas pire que 0,75 fois celui du marché sur la même fenêtre ET pas pire que -20 % absolu ; drawdown : pas pire que 0,75 fois celui du marché ET pas pire que 45 % ; on retient le plus strict) et « continue de tester ». La phase 2 (chaînes payantes) n'est PAS autorisée, aucun achat. Tout changement après ce gel figure dans la section « Écarts déclarés » en fin de document, daté, sans réécrire ce qui précède.

Rédigé le 2026-10-10 (date réelle). Aucun rendement, alpha ni régression n'a été calculé sur un indice de stratégie. Seules ont été calculées des statistiques du **marché actions** (facteurs French, voir section 9) pour justifier les seuils, et des constats de dates sur les fichiers. Cadre : aucun ordre, aucun courtier, aucun compte, `LiveExchange` reste un stub. Hors Polymarket, comme la piste E. Inventaire des données : `docs/VRP_DATA_INVENTORY.md`.
Divulgation : la piste E (`docs/VRP_REPORT.md`) a déjà mesuré sur des **prix simulés** une prime de variance et un alpha après bêta (put garanti : +0,32 % par mois, t = 4,8 en découverte, +0,21 %, t = 1,4 en test 2019-2026 ; straddle : +0,32 % puis +0,25 %). Les sous-périodes 2019-2026 des indices Cboe recoupent donc en partie des mois déjà vus (marché et VIX identiques) : **ce n'est pas un temps neuf** ; le temps neuf est le suivi prospectif (section 8).

## 1. Hypothèse

**H_VRP** : la vente systématique d'options sur indice (put-write) rapporte un **alpha mensuel strictement positif après bêta**, c'est-à-dire l'ordonnée à l'origine de la régression du rendement excédentaire de l'indice de stratégie sur le rendement excédentaire du marché, avec un **intervalle de confiance à 95 % par bootstrap par blocs qui exclut zéro**. Le résultat primaire est l'alpha, jamais le rendement brut ni le Sharpe.

## 2. Phases

- **Phase 1 (gratuite, indices Cboe)** : rendements mensuels des indices de stratégie publiés (prix d'options réels, VWAP). Régressions, stabilité, sensibilités de coût.
- **Phase 2 (payante, chaînes réelles)** : seulement si la phase 1 passe ET sur décision écrite de l'utilisateur d'acheter des données (liste chiffrée dans l'inventaire). Reproduire la stratégie sur chaînes bid/ask SPX avec spreads réels et commissions. Elle sera pré-enregistrée à part (grille, fenêtres) avant achat ; ici seuls ses critères sont fixés.
- **Phase 3 (hors échantillon et prospectif)** : mêmes règles gelées sur d'autres sous-jacents (section 8) et suivi mensuel prospectif.

## 3. Grille et nombre exact de cellules

**Cellules de décision de la phase 1 : 4**, une par indice, spécification primaire, échantillon complet :

| Cellule | Indice | Échantillon complet (mois de rendement) |
|---|---|---|
| 1 | PUT (put ATM mensuel) | 2007-01 -> 2026-08 (environ 236, quotidien seulement depuis 2007) |
| 2 | PUTY (put 2 % OTM mensuel) | 1986-07 -> 2026-08 (environ 482) |
| 3 | WPUT (put ATM hebdomadaire) | 2006-02 -> 2026-08 (environ 247) |
| 4 | CNDR (condor de fer mensuel) | 1986-07 -> 2026-08 (environ 482) |

Rendement mensuel d'un indice = dernier cours du mois civil sur dernier cours du mois civil précédent (calendrier calé sur les mois de French) ; excès = rendement moins RF du mois. Fin d'échantillon = **2026-08**, dernier mois des facteurs French.
**Spécifications de régression (4)** : (S1) **primaire** : excès de l'indice sur Mkt-RF, erreurs Newey-West (3 retards) ; (S2) trois facteurs Fama-French (Mkt-RF, SMB, HML) ; (S3) S2 plus momentum ; (S4) S1 plus un terme baissier max(-Mkt-RF, 0), car une vente d'options est courte en gamma et un bêta constant sous-estime le risque (rapporte l'alpha ET le bêta baissier).
**Fenêtres (6)** : échantillon complet, deux moitiés (égales en nombre de mois), trois sous-périodes (tiers égaux en nombre de mois, au moins 3 ; chaque tiers au moins 60 mois, sinon fusionné et déclaré).
**Estimations rapportées : 4 indices x 4 spécifications x 6 fenêtres = 96.** Les **4 cellules de décision** sont (indice, S1, échantillon complet) ; les 92 autres servent aux critères de stabilité (signe de l'alpha par moitié et par tiers) et ne sont pas soumises au FDR comme des tests séparés. Indices secondaires **descriptifs, hors décision** : BXM, BXMD, BXY (covered calls ; par parité put-call, un alpha comparable est attendu, c'est un contrôle de cohérence).
**Phase 1 + phase 3** : 4 + 3 (hors échantillon, section 8) = 7 cellules de décision au total ; prospectif : lecture de signe sur les mêmes 4 cellules.

## 4. Puissance, à calculer d'abord

Règle (variance seulement, **avant** de lire un seul alpha ; l'outil écrit un fichier de puissance puis refuse d'afficher un alpha tant que ce fichier n'existe pas) : pour chaque cellule, `se(alpha) = ecart-type du résidu de S1 / racine(n)` avec correction Newey-West, **MDE (puissance 80 %, bilatéral 5 %) = 2,80 x se**. Une cellule est **sous-puissante** si `MDE > 0,30 % par mois` (soit 2 x X, X = 0,15 % par mois, seuil de la piste E, environ 1,8 % par an) ; **sous-puissant = inconclusif, jamais négatif** : la cellule ne sert pas à rejeter l'hypothèse et le verdict final reste « inconclusif » pour elle.
Valeurs indicatives pour un écart-type résiduel supposé (non mesuré sur l'indice) de 2, 3, 4 % par mois, MDE en % par mois (n = 120 / 237 / 480 mois) : n = 120 : 0,51 / 0,77 / 1,02 ; n = 237 : 0,36 / 0,55 / 0,73 ; n = 480 : 0,26 / 0,38 / 0,51. **Attendu : avec un résidu de 2 à 3 %, PUT et WPUT (environ 240 mois) seront sous-puissantes, et PUTY et CNDR (480 mois) limites.** Cela veut dire que l'alpha de 0,2 à 0,3 % par mois vu en piste E n'est pas détectable par une seule cellule de 20 ans ; on le déclare maintenant. Pour les moitiés et tiers, la puissance est encore plus faible : leurs signes sont descriptifs et le critère de stabilité porte sur le **signe**, pas sur la significativité.

## 5. Régressions, statistiques, correction

- **Rendement de marché** : Mkt-RF de French (CRSP, total américain), en pourcentage, mensuel, aligné par mois civil. RF de French pour l'excès. Écart avec le S&P 500 déclaré.
- **IC95 de l'alpha** : bootstrap par blocs mobiles (bloc de 6 mois, 5 000 tirages) sur les couples (excès de l'indice, facteurs) ; intervalle par percentiles. Newey-West rapporté en complément (t) ; la décision utilise le bootstrap.
- **Correction des tests multiples** : p unilatérale de H_VRP (alpha > 0) des 4 cellules de décision de la phase 1, **Benjamini-Hochberg à 5 %** et **Bonferroni avec M**. M = 10 aujourd'hui (famille 13 incluse). **H_VRP phase 1 ajoute 1 à M à sa lecture (M = 11)**, la phase 2 si elle a lieu +1, le hors échantillon +1, le suivi prospectif +1 : au plus M = 14 ; Bonferroni appliqué avec le M courant à chaque lecture, `p x M < 0,05`, en plus de l'exigence de l'IC bootstrap (critère le plus sévère retenu). Les p sont étalonnées par les placebos (lambda = max(1, écart-type robuste de leurs z)).
- **Placebos** : (a) l'excès de l'indice apparié à Mkt-RF décalé de 13 à 60 mois (casse le bêta contemporain) ; (b) mélange par blocs de 12 mois de l'excès de l'indice. Part de p < 0,05 attendue 5 % ; sert à calibrer, pas à juger.
- **Baseline aléatoire** : 1 000 séries « exposition au hasard » : chaque mois, avec probabilité égale au bêta estimé de l'indice, détenir le marché (Mkt-RF + RF), sinon le cash (RF) ; alpha nul par construction. L'alpha de la cellule doit dépasser le 95e centile de ces alphas (borne unilatérale, mêmes fenêtres).
- **Contrôle synthétique positif** (`tests/test_vrp_indices.py`, dans ctest, à écrire en phase 1) : séries mensuelles simulées `RF + beta x (Mkt-RF) + alpha_inj + bruit` ; alpha injecté 0,5 % par mois, bruit 3 %, n = 237, 200 graines : l'alpha est retrouvé avec le bon signe et l'IC exclut zéro dans au moins 80 % des graines ; avec alpha = 0 le taux de rejet reste dans 2 % à 9 % ; test d'absence d'anticipation (retirer les mois futurs ne change pas les rendements passés) ; test d'alignement des mois civils entre les fichiers Cboe et French, avec valeurs calculées à la main.

## 6. Sensibilités (rapportées, certaines entrent dans les critères)

Les indices utilisent des prix de transaction réels (VWAP 11 h 30 à 12 h) sans spread ni commission : on retranche un **surcoût de vente** par roll. Calculé à la main : un put ATM à 1 mois a un vega d'environ `0,3989 x racine(1/12) = 0,115` du notionnel par unité de volatilité, soit **0,115 % du notionnel par point de volatilité** ; pour l'hebdomadaire (1/52) 0,055 % par point et par roll, environ 4,3 rolls par mois.
- Demi-spread de **0, 1, 2, 3 points de volatilité** par vente (0, 0,115, 0,23, 0,35 % par mois pour un roll mensuel) ; **commissions** : 1 $ par contrat de 100 x indice (négligeables, de l'ordre de 0,0002 % du notionnel), rapportées quand même ; coût de marge non modélisé (indices pleinement collatéralisés).
- **Remplacement du VIX moins 1,5 point par VIX moins 3 points** : s'applique au pont avec la piste E (réplication Black-Scholes de la phase 1 pour vérifier la cohérence), pas aux indices à prix réels, où la mesure équivalente est le surcoût ci-dessus.
- Sans les 3 pires mois ; sans 2008-2010 ; sans 1987 (PUTY et CNDR) ; alpha avec Mom ou sans.
- Phase 2 (si elle a lieu) : mêmes surcoûts appliqués à des bid/ask réels (donc sans VWAP), plus VIX moins 3 points comme comparaison avec la piste E.

## 7. Critères de succès proposés

H_VRP phase 1 est **acceptée** seulement si tous les critères sont tenus, sur au moins une cellule de décision non sous-puissante :
1. **Alpha de S1 > 0 et IC95 bootstrap qui exclut zéro** sur l'échantillon complet, ET la cellule reste significative sous BH à 5 % et Bonferroni avec M courant (11 à la phase 1) ; si la phase 2 est faite, mêmes conditions sur la phase 2 ET la phase 1 ;
2. **alpha de S1 positif dans chaque moitié et dans au moins 2 des 3 sous-périodes** (signe seulement) ;
3. **alpha encore positif avec un demi-spread de 2 points de volatilité** (et rapporté à 3 points) ;
4. **alpha de S2 et S3 de même signe positif** (pas d'alpha uniquement dû à l'omission de facteurs) et alpha de S4 positif : l'alpha ne vient pas d'un bêta baissier non linéaire ;
5. **pire mois et drawdown maximal sous les seuils validés** de la section 9 ;
6. bat le 95e centile de la baseline aléatoire ;
7. **signe de l'alpha identique à celui de la phase 1 sur au moins la moitié des sous-jacents hors échantillon** (section 8 : au moins 2 des 3).
**Verdict** : « acceptée » (1 à 7 tenus), « négative » (cellule de puissance suffisante dont l'IC95 est entièrement sous 0,15 % par mois, c'est-à-dire alpha exclu au-dessus de X) , « inconclusive » dans tous les autres cas, y compris sous-puissance. Aucune acceptation ne crée de code d'exécution : la stratégie exige des options réelles et un courtier, hors périmètre de ce dépôt. Une acceptation de la phase 1 déclenche seulement la décision d'acheter ou non des données (phase 2), prise par l'utilisateur.
**Règle d'arrêt** : si la phase 1 n'est pas acceptée, la phase 2 n'est pas achetée.

## 8. Hors échantillon (phase 3)

- **Sous-jacents jamais utilisés par la piste E** : RUT (PUTR, 2001-01 ->), TLT (PTLT, 2005-01 ->), NDX (BXN, covered call 2009-09 ->, **non put-write** : même exposition par parité, déclaré). **3 cellules de décision**, règle gelée identique à S1 (régression sur le rendement excédentaire du **sous-jacent propre** : TLT via Tiingo total return, NDX via `FRED_NASDAQ100` indice de prix, RUT via Mkt-RF et SMB de French faute de série de prix RUT vérifiée, déclaré), échantillon complet, signe de l'alpha et IC95 rapportés. EEM et or **non testés** (accès non établi, voir inventaire). Critère 7 : signe de l'alpha identique à celui de la phase 1 pour au moins 2 des 3.
- **Suivi prospectif** : chaque fin de mois à partir de **2026-09** (septembre 2026 et après, hors des facteurs French actuels), enregistrer les valeurs des 4 indices de la phase 1 (téléchargement unique par mois, même conditions) et les facteurs French du mois dès publication. **Première lecture le 2027-04-01 au plus tôt** (septembre 2026 à février 2027, environ 6 mois), **lecture unique à cette date, descriptive** : signe de l'alpha cumulé et excès moyen ; avec 6 mois et un écart-type de 3 %, le MDE mensuel est de l'ordre de 3,4 % par mois, donc **aucune décision statistique avant au moins 36 mois (2029-10)** ; une lecture décisionnelle ultérieure doit être pré-enregistrée à part. Aucune lecture intermédiaire.

## 9. Seuils du pire mois et du drawdown (validés par l'utilisateur le 2026-10-10)

Justification sans aucun calcul sur les indices de stratégie : statistiques du **marché** (Mkt-RF + RF de French, total américain) sur les mêmes fenêtres.
| Fenêtre | Mois | Écart-type mensuel du marché | Pire mois du marché | 5e centile mensuel | Drawdown maximal du marché |
|---|---|---|---|---|---|
| 1986-06 -> 2026-08 | 483 | 4,49 % | -22,6 % | -7,4 % | 50,3 % |
| 2007-01 -> 2026-08 | 236 | 4,57 % | -17,1 % | -7,9 % | 50,3 % |
| 2007-01 -> 2018-12 | 144 | 4,33 % | -17,1 % | -7,7 % | 50,3 % |
| 2020-01 -> 2026-08 | 80 | 5,03 % | -13,2 % | -8,0 % | 24,8 % |
Argument : une vente de put à la monnaie a un delta de l'ordre de 0,5 (Black-Scholes, donc un bêta attendu proche de 0,5 sans lire la série) ; un seuil de **0,75 fois le marché** laisse une marge de 50 % sur ce bêta pour la convexité et la reconstruction des prix. Seuils validés, **le plus strict des deux** :
- **Pire mois** : pas pire que **0,75 x le pire mois du marché sur la même fenêtre** (soit -17,0 % sur 1986-2026, -12,8 % sur 2007-2026), et jamais pire que **-20 %** en valeur absolue (valeur fixe de la piste E).
- **Drawdown maximal** : pas pire que **0,75 x le drawdown du marché** (soit 37,7 % sur ces fenêtres) et jamais pire que **45 %** (valeur de la piste E).
Conséquence assumée à l'avance : une stratégie qui, comme le marché, subit près de -23 % en octobre 1987 ou -17 % en octobre 2008 avec un bêta supérieur à 0,75 **échoue** ce critère ; c'est le but. Les seuils sont des critères d'acceptation, pas des paramètres à ajuster après la lecture.

## 10. Calendrier et verrous

1. Validation par l'utilisateur (faite le 2026-10-10) ; gel daté dans `CLAUDE.md`.
2. Phase 1, étape 0 : calcul de la puissance (variance seulement), fichier écrit, verrou ; tests de plomberie et contrôle positif.
3. Phase 1, étape 1 : 96 estimations, lecture unique des quatre cellules de décision (verrou contre une seconde lecture).
4. Hors échantillon, puis éventuelle décision d'achat, puis suivi prospectif (première lecture au plus tôt le 2027-04-01).
Tout changement après le gel invalide le test et doit être déclaré. Aucun résultat n'a été calculé à la date de rédaction (2026-10-10).

## Écarts déclarés

(aucun à la date du gel, 2026-10-10.)

**Précisions d'implémentation du 2026-10-10, écrites AVANT tout calcul de puissance, d'alpha ou de rendement d'un indice de stratégie** (ne changent ni les cellules, ni les critères, ni les seuils) :
1. **Premier mois** : un rendement mensuel exige un cours de fin du mois précédent à au plus 7 jours calendaires de la fin de ce mois ; sinon le mois est écarté. PUT n'ayant de quotidien qu'à partir de 2007-01-03, son premier rendement est 2007-02 (environ 235 mois au lieu de 236).
2. **p-value** : p unilatérale (alpha > 0) = 1 - Phi(t_NW / lambda), t_NW = alpha / erreur-type Newey-West (Bartlett, 3 retards, sans correction de petit échantillon) de S1 ; lambda = max(1, écart-type robuste des z placebos). L'IC95 de décision est le bootstrap par blocs.
3. **Placebos centrés** : appliqués littéralement, les placebos de la section 5 conservent la moyenne positive de l'excès de l'indice, donc leurs z ne sont pas des z sous H0 et lambda serait gonflé par l'alpha lui-même. Les placebos sont donc calculés sur `excès de l'indice moins l'alpha de S1 estimé sur l'échantillon complet` (H0 vraie par construction). Le lambda littéral (non centré) est rapporté à côté, non décisionnel. Décidé avant d'avoir vu un alpha.
4. **Seuils pire mois / drawdown** (section 9) : évalués sur la série MENSUELLE de l'indice (même base que le tableau du marché), sur l'échantillon complet de la cellule et sur la même fenêtre pour le marché (Mkt-RF + RF). Le drawdown quotidien de l'indice est rapporté en plus, non décisionnel.
5. **Surcoût de sensibilité** : 0,115 % par point de volatilité et par mois pour PUT, PUTY, CNDR (roll mensuel, valeur ATM utilisée aussi pour PUTY et CNDR, approximation déclarée : CNDR a quatre jambes) ; 0,055 % x 52/12 = 0,2386 % par point et par mois pour WPUT. Le surcoût en points est le demi-spread de la section 6 ; l'alpha d'équilibre (surcoût qui annule l'alpha) est rapporté en points de volatilité.
6. **Baseline aléatoire** : bêta estimé borné à [0, 1] ; calculée sur les 6 fenêtres. **Bootstrap** : IC95 pour S1 (6 fenêtres) et pour les 3 cellules hors échantillon ; S2 à S4 n'ont que le t Newey-West (leur critère porte sur le signe).
7. **Fenêtres d'épisodes de stress** (rapport descriptif) : 1987-09 à 1987-12, 1998-08 à 1998-10, 2002-06 à 2002-10, 2008-09 à 2008-11, 2018-02, 2020-02 à 2020-03, 2022-01 à 2022-10 ; perte du pire mois de la fenêtre, perte sur 3 mois, mois de retour au sommet précédent.
8. **Hors échantillon** : TLT par le total return ajusté Tiingo (`data/tiingo/TLT.csv`, téléchargé le 2026-10-10, 1 requête) ; RUT régressé sur Mkt-RF et SMB (alpha = ordonnée) ; BXN sur le rendement du FRED NASDAQ100 (indice de prix) ; excès = moins RF de French. Puissance calculée de la même façon.
9. **Constat sur les dates de lancement** (recherche web du 2026-10-10, fiche Cboe) : PUTY a pour date de base 1986-06-30 et **date de lancement 2019-02-15** : tout avant est reconstruit (back-tested). Date de lancement de CNDR et de WPUT : NON VÉRIFIÉE ; PUT : quotidien seulement depuis 2007. Un alpha sur la période post-lancement de PUTY (2019-03 ->) est rapporté en descriptif.

**Écarts déclarés le 2026-10-10 APRES la lecture des résultats de la phase 1 (aucun ne change un verdict de cellule, vérifié)** :
10. **Placebos : le centrage de l'écart n°3 était faux.** Retrancher l'alpha de S1 laisse `bêta x moyenne du marché` (environ 0,35 % par mois) dans la série placebo, dont les z restaient donc très positifs : lambda = 3,50 (70 % de |z| > 1,96), non crédible. Défaut de conception de ma part, repéré en lisant lambda, pas un choix. Correction : placebos centrés sur la MOYENNE de l'excès (`vrp_indices.py --mode placebo2`) : lambda = 1,00, part de |z| > 1,96 = 0 %. Les p calibrés du premier lancement (lambda 3,5) et du second (lambda 1) sont tous deux rapportés ; **les quatre cellules ont un IC95 bootstrap qui contient zéro (critère 1 échoue indépendamment de lambda), et BH ne rejette aucune cellule dans les deux cas**.
11. **Contrôle synthétique positif** : le bruit de 3 % écrit en section 5 donne, pour n = 237 et un alpha de 0,5 %, une puissance théorique de 73 % (se = 0,195 %, z = 2,56), sous les 80 % exigés : erreur arithmétique du brouillon. Le test utilise un bruit de 2 % (résidu mesuré : 1,6 à 1,9 %), puissance théorique 98 %. Test passé (alpha injecté retrouvé, taux de rejet nul entre 2 % et 9 %). 300 tirages de bootstrap dans le test (5 000 pour le calcul réel).
12. **Reprise technique du calcul** : après la première exécution complète, le verrou de lecture unique a été retiré pour corriger la colonne `p_bonf_M12` du fichier hors échantillon (valeur non plafonnée). Le calcul est déterministe (graine fixée) : le résumé est identique octet pour octet avant et après (`diff`), aucun autre changement. Aucune cellule n'a été relue avec un autre réglage.
13. **Puissance des cellules hors échantillon** : PUTR et BXN sont sous-puissants (MDE 0,43 et 0,35 % par mois), PTLT puissant (0,21 %) ; le critère 7 ne porte que sur le signe, comme écrit.

