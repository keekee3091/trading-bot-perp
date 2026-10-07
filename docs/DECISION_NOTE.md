# Note de décision : bot de perps Polymarket, état au 2026-10-05 (mise à jour : actions, Tiingo + perp)

## Décision

**Aucun code d'exécution n'est écrit.** Six familles de stratégies, puis une grille de 894 hypothèses de prédictibilité (voir plus bas), ont été testées avec le même protocole
(grille fixée avant résultat, un seul jeu de paramètres, train / validation / test chronologique avec test touché
une fois, correction pour tests multiples, comparaison à des entrées aléatoires de même rythme, longs et shorts
séparés, coûts réels). **Aucune n'est positive hors échantillon net de coûts.** `LiveExchange` reste un stub.
Aucun ordre réel n'a jamais été passé.

## Résultats de toutes les familles

| Famille | Hypothèse | Données | Points testés | Résultat hors échantillon (test) | Contre le hasard |
|---|---|---|---|---|---|
| A. Momentum court | le momentum sur 3 à 15 min gagne (BTC, ETH, SOL, une par une) | klines 1m, funding réel, 4 mois | 540 par instrument | Sharpe -46.3, -41.3, -47.1 ; PnL net -459, -463, -720 sur 1000 | bat 8 %, 1 %, 5 % des tirages |
| B. Momentum long, panel | idem sur 1 h à 1 j, 15 instruments, un seul jeu de paramètres | idem + indices, matières premières, actions | 64 | Sharpe de portefeuille -7.04, rendement -0.87 %, 2/15 instruments positifs, alpha t = -1.94 | bat 44 % (Sharpe) |
| Market making passif (abandonné) | quotes maker autour du mark, gain de spread | trades publics, mark 1m, funding, 21 instruments à spread large | 30 | borne conservatrice -0.57 %, optimiste -0.81 % ; 3/21 instruments positifs en validation et test | bat 100 % des deltas aléatoires, mais perd |
| C. Prime mark/index (proxy funding) | une prime horaire dépassant le coût converge | funding publié (l'index n'a pas d'historique), klines 1m, 28 instruments | 9 | net -22.7 bps par trade (154 trades), t = -5.25 | bat 10 % des tirages |
| D. Décalage avec Binance (crypto) | le perp suit Binance avec retard, capturable | trades perp + klines Binance 1 s, 5 instruments, 21 jours | 27 | net -9.8 bps par trade (234 trades), t = -8.43 | bat 63 % des tirages, mais chacun perd le coût |
| E. Momentum de séries temporelles, sous-jacents non crypto | momentum 1 à 12 mois long/short, pondéré par la volatilité, sur SP500 (proxy), NAS100, WTI, Brent, or, argent | historiques de 40 à 100 ans (FRED, French, Banque mondiale), coûts et funding Polymarket supposés | 16 | Sharpe +0.31 (+1.9 % par an, t = 1.07) contre +0.56 pour la volatilité égale long seul ; 4 critères sur 7 échouent | bat 58 % des signes aléatoires |
| Grille large (étage 1 puis 2) | 67 variables (flux d'ordres, prix, régime, funding et base, calendrier, inter-actifs, Binance) x 6 horizons de 1 min à 1 jour x 3 groupes (crypto, indices et matières premières, actions liquides) | klines 1m, trades, funding, marks, Binance 1 s, avant le gel du 2026-09-28 ; holdout 2026-09-28 -> 2026-10-05 | 894 cellules planifiées, 473 sous-puissantes, 403 testées | 55 passent le FDR (BH 5 %), 42 stables, **1** avec écart de déciles > coût ; étage 2 sur cette cellule : net **-11.4 bps par trade** (601 trades, t = -12.3) | bat 12 % des entrées aléatoires ; placebos calibrés (4 % de p < 0.05, 0 découverte) |
| Actions (Tiingo + perp) | H1 écart de réouverture, H2 coupe transversale quotidienne 1980-2018, H3 nuit contre séance | Tiingo ajusté (34 actions, biais de survie), klines perp 18 actions | 41 cellules, 28 sous-puissantes, 13 testées | 5 FDR, 4 stables, **0** avec ratio effet / coût > 1 (prime de nuit +9.5 bps contre 16.8 de coût) ; pas d'étage 2 | placebos calibrés (lambda 1) |
| H4 résultats trimestriels (SEC + Tiingo) | dérive après annonce, effet avant annonce, réaction du perp | 1 500 8-K Item 2.02, 28 actions, 587 événements de découverte | 15 cellules, 15 sous-puissantes | non testable (MDE 538 à 1 054 bps) ; H4c descriptif : le perp prend l'annonce avant l'ouverture | n.a. |
| P1 signaux lents + ordres passifs | inversion en coupe transversale (S1) et prime de nuit (S2), exécutés en post-only (maker 1.25 bps) | Tiingo ajusté (longue histoire, effet exécutable), 22 jours de trades perp pour les fills | 5 signaux x 5 à 7 politiques x 4 bornes | S1 non exécutable (-8.4 bps contre +7.1 clôture-clôture) ; S2 : +5 à +7 bps net maker mais sélection adverse de 31 bps contre 5 tolérés, net par signal conservateur -11 à +2 bps, intervalles contenant zéro | non concluant (optimiste positive seule) |

Correction pour tests multiples : Bonferroni sur le t du rendement en test, **M = 9** évaluations de test d'une
hypothèse d'edge dans le projet (A : 3, B : 1, market making : 1, C : 1, D : 1, E : 1, grille large : 1). Aucune famille n'a un rendement
positif en test : la correction n'a jamais été le facteur décisif. Détails, grilles et chiffres par instrument : sections
« Résultat de la validation », « Résultats : famille B », « Résultats : market making » et « Résultats : familles C et
D » de `CLAUDE.md` ; rapports bruts dans `results/`.

## Pourquoi rien ne marche (diagnostics mesurés)

- **Pas d'edge brut sur le momentum.** Le rendement futur signé après un signal momentum est de -3 à +0.6 bps (|t| < 2
  presque partout) contre un coût aller-retour taker d'environ 14 bps (frais 8, spread 2, slippage 4). Le signal est du
  bruit à ces horizons ; les frais font le reste. Le test de sens (`test_direction`) prouve que le signal est bien
  orienté : le momentum gagne sur régimes synthétiques nets ; le résultat réel n'est donc pas un bug de signe, et le
  signal n'a jamais été retourné pour améliorer un résultat.
- **La quotation passive subit la sélection adverse.** Markouts mesurés sur les fills simulés : -7 à -11 bps dès 1 à 60 s,
  plus que le spread capturé net de frais (~5 bps). Chaque fill perd en moyenne ; plus la borne de fill est conservatrice,
  moins on perd.
- **La prime mark/index est persistante, elle ne converge pas.** Après une dislocation de plus de 20 bps, 83 % des cas
  sont encore hors bande 4 h plus tard, 77 % après 12 h ; temps médian de retour dans la bande : 24 h ; |P| moyen 4 h plus
  tard : 32 bps. Prime d'une heure à la suivante : corrélation 0.77. Fader la prime perd plus que le hasard (-22.7 bps).
  Il s'agit en bonne partie d'un écart structurel (base, prix périmés hors séance), pas d'une inefficience qui se
  referme vite.
- **Le retard avec Binance existe, mais il est minuscule.** Le perp suit Binance (corrélation 0.15 à +5 s, 0.10 à +10 s,
  0.05 à +30 s, quasi nulle au-delà de 2 min ; aucune corrélation quand le perp mène) : une impulsion de 10 bps sur
  Binance se traduit par ~1.5 bps de plus sur le perp au lag de 5 s. Le coût aller-retour est de plus de 12 bps :
  **rien à voir**. La stratégie taker obtient -9.8 bps, soit le coût moins ~2 bps de capture brute.
- **Le momentum de séries temporelles sur les sous-jacents longs a un signal réel mais modeste, qui ne survit pas à la
  validation hors échantillon récente.** Sur 1927-2014 le point retenu gagne (Sharpe +0.60 puis +0.92, protège en 2008 : +2.3 %
  contre -34 % pour le buy and hold) et 9 décennies sur 10 sont positives ; sur 2015-2026 il tombe à +0.31 (t = 1.07), derrière une
  simple allocation à volatilité égale long seul (+0.56), les shorts perdent (-0.09 %/mois) et il bat seulement 58 % des signes
  aléatoires. Sur EUR/USD et proxy DXY (non listés) il ne fonctionne pas (Sharpe -0.25 puis -0.15). Le Sharpe ne dépend pas du levier ; le
  levier 5x donne un drawdown de 64 % et 2 liquidations en test. Les frais ne comptent pas à rythme mensuel (< 0.05 % de la marge par
  mois) ; **le funding supposé (5.475 % par an payé par les longs) coûte environ 0.2 de Sharpe**.
- **Le résultat sur le sous-jacent ne s'applique pas tel quel au perp** : le perp NAS100 suit son sous-jacent (corrélation 0.996, niveau
  +4 bps), mais le perp WTI s'écarte du prix spot EIA de -3.2 % en moyenne (corrélation 0.84) car il référence un contrat à terme ; 47 à 62 %
  de la variance des perps tombe hors séance, comportement non mesurable sur le sous-jacent.
- **Le levier ne crée pas d'edge.** Il multiplie rendements et coûts (coût aller-retour en % de la marge = coût en bps x
  levier : 0.12 % à 1x, 1.2 % à 10x pour D ; 0.16 % à 1x, 1.6 % à 10x pour C). Le levier de Kelly estimé hors échantillon est
  négatif ou indistinguable de zéro. Ce n'est pas une solution.
- **Le carry de funding n'est pas une étude à lancer en l'état** : sur actions et BTC le funding est surtout la composante
  d'intérêt fixe (5 à 8 % par an), du même ordre que le coût du capital sur deux plateformes ; NAS100 et WTI montrent un
  excès instable sur 150 jours ; la jambe de couverture n'a pas de données.

## Protocole commun (tel qu'appliqué)

1. Hypothèse, données, grille, fenêtres, critères et décompte des tests écrits dans `CLAUDE.md` **avant** le premier
   résultat (sections « Pré-enregistrement »).
2. Sweep sur train seulement ; top 3 confirmés sur validation ; point final évalué une fois sur test.
3. Un seul jeu de paramètres commun à tous les instruments, jamais de réglage par instrument.
4. Baseline : entrées aléatoires de même rythme (même nombre d'entrées par instrument, mêmes sorties, mêmes coûts).
5. Longs et shorts rapportés séparément ; levier traité en variable d'étude avec son coût en % de la marge.
6. Test de plomberie sur données synthétiques avec l'effet injecté : la stratégie doit le capturer, du bon côté, et ne
   pas gagner sans l'effet (tests dans ctest : 18 exécutables).
7. **Critères d'arrêt** : rendement net moyen > 0 en validation ET en test ; significatif après Bonferroni ; bat >= 75 % des
   tirages aléatoires ; longs et shorts non négatifs ; >= 30 trades en test ; pas de dépendance à quelques trades. Si un
   seul échoue : pas de code d'exécution.

## Limites de ces conclusions (à ne pas surévaluer)

- **Historique court** : 4 mois au plus (2026-05-06 à 2026-10-05, 77 jours seulement pour les actions), un seul régime
  (marché haussier en validation et en test), donc peu d'information sur d'autres régimes.
- **Fenêtres de test courtes et réutilisées** : 9 jours pour le market making, 5 jours pour D, 23 jours pour C et B. Les
  fenêtres de test recoupent calendairement celles des familles précédentes (hypothèses et données différentes, mais même
  marché sur les mêmes jours). Une conclusion négative sur 5 à 9 jours est moins robuste qu'une sur 3 mois.
- **Marchés très fins** : 172 à 1 400 trades par jour sur les actions ; très peu de fills par instrument ; bougies sans trade
  remplies par un prix périmé (37 à 57 % des minutes réelles sur le crypto, 8 à 11 % sur les actions).
- **Pas d'historique d'index ni de carnet** (vérifié : aucun endpoint) : la famille C n'a qu'un proxy horaire de la prime
  (et seulement hors bande de l'intérêt fixe) ; le market making n'avait ni file d'attente ni spread passé coté, d'où deux
  bornes de fill ; la famille D exécute sur des prix imprimés (supposé : prix exécutables).
- **Coûts** : spreads tirés d'un relevé de 5 points par instrument (`data/live_probe/`) et d'un relevé de 45 s ;
  slippage supposé (2 bps par côté) ; frais du palier 0 documenté. Les coûts réels en heures creuses ne sont pas mesurés.
- **Famille E : sources et biais de données** (détail dans `CLAUDE.md` et `data/under/MANIFEST.txt`) : SP500 = rendement TOTAL du marché
  américain (French, dividendes inclus, favorable aux longs), or et argent = moyennes MENSUELLES (biais de lissage, pas de série
  quotidienne légale : LBMA sous licence), WTI et Brent = prix spot EIA (pas le contrat à terme du perp), aucune action individuelle
  (aucune source sans clé à long historique), funding = hypothèse H_F (intérêt fixe seul). Stooq (vérification JavaScript) et Yahoo
  (scraping interdit) ont été écartés ; FRED, French et la Banque mondiale autorisent un usage de recherche personnelle.
- **Famille D limitée au crypto** : aucune source gratuite et légale à 1 s sans clé pour l'or, les indices, les actions
  (Yahoo sans API officielle, Alpha Vantage, Twelve Data, Polygon sous clé et quotas, Stooq sans intraday exploitable).
- **Calendriers de session inférés** (pas officiels, jours fériés ignorés) ; modèle intra-bougie à 4 ticks approximatif.
- **Un échec de protocole n'est pas une preuve d'absence d'edge** : il montre l'absence d'edge pour CES signaux, à CES
  horizons, avec CES coûts, sur CETTE période.

- **Grille large (étages 1 et 2, `docs/ETAGE1_REPORT.md`).** Ce qui prédit réellement le prix à 1 à 15 minutes : le prix de Binance (IC jusqu'à 0.24), BTC et ETH vers les autres cryptos, le flux d'ordres signé,
  le retour à la moyenne de 1 à 4 h à 15 minutes en crypto. L'écart entre déciles extrêmes est de 1 à 15 bps, pour 12 à 16 bps de coût aller-retour : une seule cellule dépasse le coût sur le papier, et à
  l'exécution sur prix imprimés le brut tombe à +0.65 bps (la plus grande part de l'effet mesuré était le rattrapage d'un dernier prix périmé). Le régime de volatilité et le calendrier ne prédisent rien.
  Les horizons de 1 h à 1 jour ne sont pas testables avec si peu d'historique (473 cellules sous-puissantes).

- **Actions (`docs/ACTIONS_REPORT.md`).** Le perp suit déjà l'écart d'ouverture de son sous-jacent (bêta 0.70, R² 0.71, 0.88 le week-end). La prime de nuit des actions américaines est réelle (+9.5 bps par nuit, z 8.7) mais inférieure
  au seuil de rentabilité de 16.8 bps (frais, slippage, spread, funding) ; l'inversion à 5 jours de la coupe transversale vaut 7 bps par jour contre 12 de rotation. Biais de survie : l'univers est celui d'aujourd'hui.

- **H4 (`docs/H4_REPORT.md`).** Avec 27 actions et 587 événements de découverte, les rendements à 5-20 jours après annonce ont un écart-type de plusieurs centaines de bps : on ne détecterait que des effets supérieurs à ~500 bps. La dérive après annonce documentée (100 à 300 bps)
  n'est donc ni confirmée ni infirmée. Sur les nuits d'annonce après clôture, le perp (qui cote 24 h sur 24) prend déjà presque tout l'écart d'ouverture (12 événements).

- **P1 (`docs/P1_REPORT.md`).** L'inversion à 5 jours (7.1 bps par jour clôture-clôture) est un effet de l'écart de nuit : exécutable (entrée à l'ouverture) elle vaut -8.4 bps. La prime de nuit des actions (+9.5 bps) se joue entre 15h55 et 9h35 et reste exécutable : en ordres maker son net serait de +5 à +7 bps par nuit,
  mais les actions perp sont trop fines : 4 à 13 % d'exécution passive, et la sélection adverse après un fill est de -24 à -32 bps à 10 minutes, 5 fois la tolérance : le net conservateur par signal émis va de -11 à +2 bps, intervalles contenant zéro.

## Ce qui justifierait une reprise

Aucune de ces conditions n'est remplie aujourd'hui ; elles sont écrites pour qu'une reprise ne soit pas arbitraire.

1. **Du temps neuf** : un holdout vierge (`tools/recorder.py` à laisser tourner, plusieurs semaines à plusieurs mois :
   tickers avec `index`, `mark` et `basis_bps` toutes les 5 s, carnet à 10 niveaux, funding). Toute nouvelle hypothèse se
   valide dessus, ou compte dans M avec correction.
2. **Une inefficience mesurée avant d'être tradée**, d'amplitude supérieure au coût aller-retour taker réel de
   l'instrument (14 bps environ en taker, plus bas en maker mais avec sélection adverse). Exemples de ce qui la ferait
   apparaître : une prime mark/index mesurée à 5 s (et non plus à l'heure) qui converge de plus de 15 bps en moins de
   quelques minutes ; un retard externe de plus de 12 bps exploitable sur un instrument liquide ; un déséquilibre de
   carnet prédictif à horizon supérieur à la seconde ; un carry avec prix de jambe de couverture disponibles et excès net
   du coût du capital.
3. **Une source de prix externe pour l'or, les indices et les actions** (flux sous licence ou clé personnelle gratuite : Alpha Vantage, Twelve Data, Tiingo ; historique quotidien de l'or et des actions individuelles ; contrats à terme du pétrole) : sans elle, la famille D ne
   dit rien de ces catégories, qui sont celles où le perp a le plus de chances de réagir avec retard.
4. **Un historique de carnet ou de vrais fills** pour revenir sur le market making (hors périmètre actuel) : seul le
   passage de quotes réelles de petite taille, sur plusieurs semaines, lèverait l'incertitude sur la file d'attente.
5. **Pour la famille E précisément** : reprendre si (a) un historique QUOTIDIEN de l'or, de l'argent, du S&P 500 et d'actions individuelles est obtenu légalement, (b) le même protocole (grille de 16 points, mêmes critères) donne un Sharpe net significatif après correction sur une fenêtre de test d'au moins 10 ans ET bat l'allocation à volatilité égale long seul, (c) le perp (et non son sous-jacent spot) est testé sur son propre historique, avec le funding réel mesuré sur au moins un an. Un usage défensif (réduction du risque en 2008) serait une question distincte, hors critères d'edge.
6. **Pour la grille large** : (a) refaire l'étage 1 avec le carnet (F8, `tools/recorder.py`) une fois plusieurs semaines enregistrées, en réservant un holdout neuf ; (b) un historique d'au moins 1 an pour tester 1 h à 1 jour
   en puissance ; (c) mesurer la latence réelle de l'exécution : l'effet Binance existe mais s'éteint en quelques secondes.
8. **Actions** : (a) plusieurs mois de perp de plus pour tester H1b (résidu de réouverture) avec une puissance suffisante, avec le holdout du 2026-09-28 intact ; (b) un coût plus bas (maker, hors périmètre) pour la prime de nuit ; (c) l'accord
   pour un contact réel dans l'en-tête EDGAR (H4, résultats trimestriels).
7. **Même protocole, mêmes critères d'arrêt**, et toute hypothèse nouvelle pré-enregistrée avant le premier résultat.
   Écrire `perp_paper` (JSON lines sur stdin et stdout) puis `tools/paper_runner.py` seulement si une famille remplit tous
   les critères sur du temps neuf.

## Où trouver quoi

- Moteur, tests, commandes : `CLAUDE.md` (build, architecture, invariants testés, décisions numérotées).
- Rapports bruts : `results/` (`validation_*.txt`, `panel_B_report.txt`, `panel_C_leverage.txt`, `panel_stats.txt`,
  `mm_backtest_report.txt`, `premium_funding_report.txt`, `leadlag_report.txt`, `leadlag_xcorr.log`, `funding_diagnostic.txt`).
- Données : `data/` (klines, funding), `data/hist/` (trades, mark 1m), `data/ext/` (Binance 1 s), `data/live/` (enregistreur).
