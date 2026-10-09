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
