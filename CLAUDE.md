# trading-bot-perp : bot de perps Polymarket, moteur C++17

Adaptation à Polymarket Perps (API vérifiée le 2026-10-05) de la logique du bot Up/Down
(`C:\Dev\trading-bot`). Le moteur est en C++17 (déterministe, sans I/O), Python ne sera qu'une
couche d'orchestration fine. **Aucun ordre réel n'est branché** : `LiveExchange` est un stub qui
lève une exception, tant que backtest puis paper n'ont pas montré un Sharpe positif net de frais.

## État

| Étape | État |
|---|---|
| 1. Cœur `perpcore` + tests | fait |
| 2. Backtester CLI `perp_backtest`, sweep `perp_sweep` | fait |
| 3. `tools/fetch_klines.py` (klines, funding, instrument), univers de 15 instruments, sessions | fait |
| 4. Protocole `perp_validate` (mono-instrument) puis `perp_panel` (panel, un seul jeu de paramètres) | fait |
| 5. Famille A, momentum court (BTC, ETH, SOL) | **fait : négatif** |
| 6. Famille B, momentum horizon long, panel de 15 instruments | **fait : négatif, aucun critère tenu** |
| 7. Analyse du levier (courbe, vol-ciblé, Kelly hors échantillon) | **fait : l'edge est négatif, le levier n'est pas une solution** |
| 8. Diagnostic funding par catégorie | fait |
| 9. Enregistreur de carnet `tools/recorder.py` (lecture seule) | fait, à laisser tourner pour constituer le holdout |
| 10. Test du sens du signal (`tests/test_direction.cpp`) | fait : le momentum gagne sur régimes synthétiques, longs et shorts bien orientés |
| 11. Économie du market making (`tools/mm_economics.py`) | fait, **aucune conclusion avant plusieurs jours de données** |
| 12. Historique de trades (`tools/fetch_trades.py`), sens de `side` mesuré (`tools/side_semantics.py`) | fait |
| 13. Backtest passif de market making (`perp_mm`, `mm.hpp`) | fait, négatif, **ABANDONNÉ le 2026-10-05** (périmètre : plus de quotation passive) |
| 14. Famille C : prime mark/index (index sans historique : proxy par le funding publié, `tools/premium_study.py`) | fait, négatif |
| 15. Famille D : décalage avec Binance, crypto (`tools/leadlag_study.py`, `tools/fetch_binance.py`) | fait, négatif (« rien à voir ») |
| 16. Famille E : momentum de séries temporelles sur sous-jacents non crypto (`tools/tsmom_study.py`, `tools/fetch_underlying.py`) | fait, négatif (4 critères sur 7 échouent) |
| 17. Note de décision (`docs/DECISION_NOTE.md`) | mise à jour |
| 28. Piste F : calibration des marchés de prédiction Polymarket (`tools/fetch_pm.py`, `tools/pm_calibration.py`) | **fait : négatif** (vente d'outsiders -0,8 à -1,6 % par trade), achat de favoris non concluant ; test 2026 non lu ; rapport `docs/PM_CALIBRATION_REPORT.md` |
| 29. H_VRP (prime de variance, prix réels, indices Cboe) | **phase 0 faite, pré-enregistrement en attente de validation** (`docs/VRP_DATA_INVENTORY.md`, `docs/VRP_PREREG.md` brouillon non gelé) ; aucun résultat calculé |
| 27. Piste E : prime de variance VIX (`tools/vrp_study.py`, hors Polymarket) | **fait : critères tenus** (découverte et test 2019-2026 lu une fois, M = 10) mais alpha modeste (+0,21 % par mois, t = 1,4 sur le test) et proxys de prix, rapport `docs/VRP_REPORT.md` |
| 26. Piste D : différence de funding entre plateformes (`tools/funding_xvenue.py`, `tools/fetch_hl.py`) | **fait : inconclusif** (+1,31 % par an, IC95 [-1,0 ; +4,7], porté par quelques actifs), lecture du holdout pré-enregistrée le 2026-12-15, rapport `docs/FUNDING_XVENUE_REPORT.md` |
| 25. Piste C : écart entre plateformes, phase 1 (`tools/recorder_xvenue.py`) | **collecte en cours** depuis le 2026-10-08, aucune analyse, phase 2 au plus tôt le 2026-10-22 |
| 24. Piste B : horizons longs (`tools/long_horizon.py`) | **découverte faite : aucun finaliste** (TSM 5 jours net +8,65 bps, z 0,88, instable) ; 20 et 60 jours sous-puissants ; test non lu |
| 23. Piste A : carry de funding avec couverture (`tools/carry_study.py`) | **fait : inconclusif** (IC trop large), carry brut 4,34 % contre rf 3,79 %, rapport `docs/CARRY_REPORT.md` |
| 22. P1 signaux lents + exécution passive (`tools/p1_study.py`, `tools/passive_fills.py`) | **fait : aucun signal positif et robuste** (S1 non exécutable : -8.4 bps ; S2 prime de nuit : sélection adverse 5 fois trop forte), rapport `docs/P1_REPORT.md` |
| 21. H4 résultats trimestriels (SEC EDGAR + Tiingo, `tools/fetch_sec.py`, `tools/earnings_study.py`) | **fait : non testable** (15 cellules sous-puissantes), H4c descriptif ; rapport `docs/H4_REPORT.md` |
| 20. Actions (Tiingo + perp) : H1 écart de réouverture, H2 coupe transversale quotidienne, H3 nuit contre séance (`tools/fetch_tiingo.py`, `tools/stocks_study.py`) | **fait : négatif à l'étage 1** (13 cellules testées sur 41, 0 avec ratio effet / coût > 1), rapport `docs/ACTIONS_REPORT.md` |
| 19. Grille d'hypothèses large : étage 1 (`tools/grid_stage1.py`, 894 cellules planifiées, 403 testées) et étage 2 (`tools/grid_stage2.py`) | **fait : négatif** (1 cellule passe l'étage 1, net -11.4 bps par trade au holdout), rapport `docs/ETAGE1_REPORT.md` |
| 18. `perp_paper` + `tools/paper_runner.py` | **non écrit, volontairement** (règle d'arrêt) |

## Résultat de la validation (données réelles, 2026-05-29 -> 2026-10-05)

**La stratégie n'a pas d'edge : Sharpe hors échantillon négatif sur les trois instruments.**
Règle d'arrêt appliquée : pas de `perp_paper` avec ces paramètres. Rapports complets dans
`results/validation_<SYMBOLE>.txt` (grille de train dans `results/sweep_train_<SYMBOLE>.csv`).

Historique disponible (Polymarket Perps, minutes avec trades uniquement) :

| Instrument | Période | Jours | Minutes avec trades | Funding |
|---|---|---|---|---|
| BTC-USD | 2026-05-29 -> 2026-10-05 | 129 | 57 % | 2898 points |
| ETH-USD | 2026-06-01 -> 2026-10-05 | 126 | 45 % | 2896 points |
| SOL-USD | 2026-06-01 -> 2026-10-05 | 126 | 37 % | 2893 points |

Protocole (grille fixée avant tout résultat, 540 points : `signal_threshold` 0.6:0.8:0.05,
`signal_lookback_seconds` 180/300/600/900, `sl_vol_mult` 1/1.5/2, `tp_rr` 1/1.5/2,
`time_exit_seconds` 300/600/1800 ; lancée une seule fois par instrument) :

| | Train Sharpe (PnL net) | Validation | Test (vu une fois) | Test, trades | Test, brut / frais | Test, aléatoire (PnL net moyen) | Test, buy and hold |
|---|---|---|---|---|---|---|---|
| BTC-USD | -21.7 (-897) | -39.6 (-480) | **-46.3 (-459)** | 608 | -213 / 247 | -420, bat 8 % | +7.8 % |
| ETH-USD | -33.0 (-877) | -26.0 (-473) | **-41.3 (-463)** | 623 | -234 / 230 | -384, bat 1 % | +7.8 % |
| SOL-USD | -14.2 (-927) | -31.0 (-551) | **-47.1 (-720)** | 1005 | -345 / 375 | -677, bat 5 % | +16.8 % |

(PnL sur 1000 d'equity, funding réel inclus, halt de session désactivé ; il aurait eu lieu dans
tous les cas.) 0 point sur 540 a un Sharpe > 0 en train, sur les trois instruments.

Diagnostics :
- **Le signal n'a pas d'edge brut.** `tools/signal_diagnostic.py` : rendement futur signé après
  un signal momentum (|z| >= 0.8, événements non chevauchants) = entre -3 et +0.6 bps selon
  l'horizon, |t| < 2 presque partout (ETH train L=15 min, h=60 min : -3.1 bps, t = -2.1). Le coût
  aller-retour est d'environ 14 bps (frais taker 2 x 4 bps, spread 2, slippage 4). Il faudrait
  un edge brut d'au moins ~14 bps par trade ; on mesure ~0.
- **Les coûts décident du reste** : 600 à 2700 trades (soit 8 à 35 par jour), frais = 40 à 75 %
  de la perte nette. La stratégie fait environ aussi bien que des entrées aléatoires de même
  rythme (mieux que 1 à 8 % des tirages en test, 82 % en train sur SOL seulement), donc le
  signal n'ajoute rien de mesurable.
- **Les sorties aggravent** : `max_hold` concentre la perte (BTC test : -428 sur 339 trades), car
  `time_exit` ne sort qu'en gain ; les perdants restent jusqu'à `max_hold`. Les SL pèsent sur SOL
  (-762 test), comme dans le bot Up/Down.
- **Les trois périodes sont cohérentes** (tout est négatif partout, pas de sur-ajustement
  apparent), mais seulement ~4 mois et un seul régime (marché haussier en validation et test :
  buy and hold +8 à +34 %), donc peu de conclusion sur d'autres régimes.
- **Ce que l'on peut et ne peut pas conclure** : le résultat négatif est statistiquement solide
  (t par trade de -3 à -12 sur des centaines de trades) pour CETTE famille de signaux, à CE
  coût, sur CETTE période. Il ne dit rien d'une autre stratégie.

Hypothèses à tester ensuite (une seule à la fois, même protocole, nouvelle grille fixée avant de
regarder) :
1. **Coûts** : ordres limites post-only (maker 1.25 bps au lieu de 4) ; exige un modèle de fill
   maker (file d'attente, fill partiel, sélection adverse) qui n'existe pas. Le gain théorique est
   de 5.5 bps par aller-retour, insuffisant seul face à ~0 d'edge.
2. **Horizon** : signal sur 1h à 1j au lieu de 5 à 15 min, pour que le mouvement attendu dépasse
   largement 14 bps ; beaucoup moins de trades. Le diagnostic à 60 min est déjà négatif (L=15).
3. **Retour à la moyenne** plutôt que momentum : le signe est négatif de façon répétée à 30 et
   60 min (BTC test -1.2 et -2.4 bps), mais faible, |t| < 2, et insuffisant face aux coûts.
4. **Filtre de régime** : trader seulement quand la vol réalisée ou le volume est élevé (43 à 63 %
   des minutes n'ont aucun trade, leur prix est périmé).
5. **Autre source d'edge** : funding (cash and carry avec une jambe de couverture, hors
   périmètre du bot actuel), écart perp/index, ou carnet (déséquilibre au touch).

## Pré-enregistrement : hypothèse 1 en panel (horizon long), écrit AVANT tout résultat

Écrit le 2026-10-05 (UTC, après `perp_panel` et `config_panel.yaml`, avant le premier lancement).
Tout ce qui suit est figé ; un changement après coup invalide le test et doit être déclaré comme tel.

**Univers (15 instruments, `results/panel_symbols.txt`)** : SP500, NAS100 (index), GOLD, SILVER,
WTIOIL (commodity), BTC, ETH, SOL (crypto), AAPL, MSFT, GOOG, AMZN, NVDA, META, TSLA (equity).
Choisis sur l'historique disponible (>= 100 jours pour les 8 premiers, 77 jours pour les actions, qui
n'existent qu'à partir du 2026-07-20) et la notoriété de liquidité, **avant** de voir un résultat de
stratégie. Les 73 autres instruments (87 jours ou moins, souvent ~19 j) sont exclus ; HYPE (89 j),
SPCX (112 j) aussi, faute de raison de les préférer.
**Un seul jeu de paramètres pour tous.** Jamais de réglage par instrument.

**Paramètres fixes** : `config_panel.yaml` (sur `config.yaml`). **Grille** (64 points,
`results/grid_panel.txt`) : `signal_lookback_seconds` 3600 / 14400 / 43200 / 86400,
`time_exit_seconds` 3600 / 14400 / 43200 / 86400, `sl_vol_mult` 1 / 2, `signal_threshold` 0.7 / 0.8.

**Fenêtres UTC** : train jusqu'au 2026-08-15 (exclu), validation 2026-08-15 -> 2026-09-10, test
2026-09-10 -> fin des données (2026-10-05). Validation et test sont précédés de 2 jours de
préchauffage de l'historique (aucune entrée). Mêmes dates pour tous les instruments.

**Procédure** : sweep sur train, classement par Sharpe du portefeuille équipondéré (sleeves
indépendants de 1000, equity moyenne à l'heure, sleeve non listé = cash), >= 100 trades au total ;
top K = 5 confirmés sur validation ; point final = meilleur Sharpe de validation (>= 30 trades) ;
test évalué une seule fois pour ce point.

**Décompte des tests déjà faits (avant ce panel)** :
- Famille A, momentum court (BTC, ETH, SOL) : 540 points x 3 instruments en train (1620
  backtests), 5 x 3 = 15 en validation, **3 évaluations sur test** (une par instrument).
- Diagnostics descriptifs (`signal_diagnostic.py`, `funding_diagnostic.py`) : non comptés comme
  tests d'hypothèse, mais `signal_diagnostic.py` a affiché la période de test.
- **Le jeu de test (2026-09-10 -> 2026-10-05) est donc consommé pour BTC, ETH, SOL** par la famille A.
  Pour ces trois instruments, cette famille B est un **deuxième regard sur le même test**. Pour les
  12 autres instruments (index, commodities, actions) c'est le premier. Le rapport sépare les deux.
- Famille B (ce panel) : 64 points en train, 5 en validation, 1 évaluation sur test.
- **Nombre total d'évaluations de test d'une hypothèse d'edge : M = 3 + 1 = 4.**

**Correction des tests multiples (choix : Bonferroni)** sur la p-value du test, M = 4 : p unilatérale
du Sharpe horaire du portefeuille sur test (t = moyenne / (écart-type / racine n), normale), à
multiplier par 4. Seuil : p x 4 < 0.05, soit t > 2.24 environ. Raison du choix : simple, prudent, et
le test est la seule sélection qui compte. En complément, **Sharpe déflaté** (Bailey et Lopez de
Prado) calculé sur le train : il mesure combien le meilleur point d'une grille de 64 s'explique par la
chance de la sélection ; il n'est pas un critère de décision.

**Critères de succès, tous requis (sinon pas de `perp_paper`)** sur le point final :
1. Sharpe de portefeuille > 0 et rendement net > 0 en validation ET en test, frais, spread, slippage
   et funding réel inclus ;
2. Bonferroni : p x 4 < 0.05 sur le test ;
3. au moins 60 % des instruments actifs positifs en test ;
4. la stratégie bat au moins 75 % des tirages aléatoires (même nombre de trades par instrument, mêmes
   sorties) en Sharpe de portefeuille sur test ;
5. alpha de la régression sur le marché équipondéré avec t > 0 (rapporté ; un Sharpe positif qui n'est
   que du beta ne compte pas).

**Analyse du levier (C)** : exécutée avec le point final quel qu'il soit, sur validation et test (la
courbe de levier remet à l'échelle les mêmes rendements : descriptive, non comptée dans M). Règle
d'interprétation écrite d'avance : si le Sharpe hors échantillon n'est pas positif, le levier de
Kelly estimé est <= 0 et **le levier n'est pas une solution** ; la courbe sert alors seulement à
chiffrer la perte, les liquidations et le coût en % de la marge.

## Résultats : famille B (panel, horizon long) et levier, 2026-10-05

Protocole exactement tel que pré-enregistré ci-dessus (rien n'a été changé après coup ; un test de
plomberie a d'abord tourné sur des données tronquées avant la fenêtre de test, sans la consommer).
Rapports : `results/panel_B_report.txt`, `results/panel_C_leverage.txt`, `results/panel_stats.txt`.

**Résultat : les 5 critères de succès échouent. Pas de `perp_paper`.**

Sweep (64 points, train) : **0 point sur 64 avec un Sharpe de portefeuille > 0** (meilleur -1.69).
Point final retenu sur validation : `signal_lookback_seconds=86400`, `time_exit_seconds=43200`,
`sl_vol_mult=2`, `signal_threshold=0.8`.

| Fenêtre | Sharpe portefeuille | Rendement net | Trades | Instruments positifs | Brut / frais | Bat les aléatoires |
|---|---|---|---|---|---|---|
| Train 2026-05-06 -> 08-15 | -1.70 | -1.09 % | 619 | 9/15 | -0.52 % / 0.89 % | 52 % (Sharpe) |
| Validation 08-15 -> 09-10 | +1.06 | +0.15 % | 168 | 6/15 | +0.40 % / 0.25 % | 94 % |
| **Test 09-10 -> 10-05** | **-7.04** | **-0.87 %** | 197 | **2/15** | -0.59 % / 0.28 % | **44 % (Sharpe), 6 % (rendement)** |

(rendements en % du capital total de 15 sleeves de 1000 ; Sharpe annualisé sur rendements horaires.)

Critères pré-enregistrés, sur le test : (1) Sharpe > 0 en validation ET test : **non** (test -7.04) ;
(2) Bonferroni M=4 : t = -1.87, p unilatérale 0.969, p x 4 = 1 : **non** ; (3) >= 60 % d'instruments
positifs : **non** (2/15 = 13 %, NVDA +0.06 %, META +0.01 %) ; (4) bat >= 75 % des tirages aléatoires :
**non** (44 %) ; (5) alpha avec t > 0 : **non** (alpha annualisé -12.8 %, t = -1.94, beta 0.008).
Sharpe déflaté du train (64 essais) : 0.000 (aucun essai positif).

Détails du test (point final) :
- **Longs et shorts** : longs 111 trades, -0.45 % du capital ; shorts 86 trades, -0.41 % : aucun des deux
  côtés n'a d'edge.
- **Beta** : 0.008, la stratégie est quasi neutre au marché ; le marché équipondéré (buy and hold, sans
  coûts) fait +4.26 % sur la fenêtre, la stratégie -0.87 %.
- **Test partagé** : BTC, ETH, SOL (test déjà consommé par la famille A, deuxième regard) : -2.36 %, -2.42 %,
  -0.40 % ; les 12 autres instruments (premier regard) : somme -7.80 % pour 12 sleeves, soit -0.65 % en
  moyenne (seuls NVDA et META sont positifs, de moins de 0.1 %). Les deux sous-ensembles sont négatifs.
- **Sorties** : `time_exit` 193 trades pour -91, `stop_loss` 3 pour -34 : le risque n'est pas dans les stops
  (3 seulement) mais dans le fait que les positions tenues 12 h ne gagnent pas en moyenne.
- **Coûts** : 0.28 % du capital en frais sur 0.59 % de perte brute : l'edge brut est négatif avant les
  coûts. Chiffre de coût aller-retour du modèle : 14 bps du notionnel.

### Analyse du levier (point final, validation et test, descriptive, non comptée dans M)

Sizing par levier de compte (mode 1 : notionnel = equity x levier, margin_frac 0.95, plafonds du mode
risque désactivés), levier fixe sans plafond de liquidation pour que les liquidations puissent apparaître,
vol-ciblé avec plafond `liq_buffer_mult`.

| Test | Sharpe | Net | Max DD | Liquid. | liq_guard | Levier de position moyen | Coût aller-retour en % de la marge |
|---|---|---|---|---|---|---|---|
| risque 1 %/SL (mode 0) | -7.04 | -0.87 % | 0.95 % | 0 | 0 | 4.98 | 0.70 |
| fixe 1x | -4.79 | -2.64 % | 3.22 % | 0 | 0 | 1.05 | 0.15 |
| fixe 2x | -5.14 | -5.59 % | 6.70 % | 0 | 0 | 2.11 | 0.29 |
| fixe 5x | -5.38 | -14.02 % | 16.52 % | 0 | 0 | 5.26 | 0.74 |
| fixe 10x | -5.40 | -25.63 % | 29.87 % | 0 | 0 | 10.43 | 1.46 |
| vol cible 10 % | -7.05 | -0.91 % | 1.00 % | 0 | 0 | 1.00 | 0.14 |
| vol cible 20 % | -7.06 | -1.81 % | 1.99 % | 0 | 0 | 1.04 | 0.15 |
| vol cible 40 % | -7.10 | -3.62 % | 3.97 % | 0 | 0 | 1.32 | 0.18 |

(La validation, positive à +1.06 en mode 0 et à +1.67 à 1x, donne +9.6 % net à 10x mais avec 42.8 % de
drawdown et un Sharpe qui ne croît pas avec le levier : 1.67, 1.41, 0.90, 1.60 pour 1x, 2x, 5x, 10x.)

**Kelly hors échantillon** (rendements horaires du portefeuille à 1x) :
- validation : mu > 0 (Sharpe +1.67) mais f* = +17 avec un intervalle bootstrap à 90 % de [-60, +69] :
  non distinguable de zéro, kurtosis 26 (queues très épaisses), pire heure -0.73 % ;
- test : f* = -61, levier empirique optimal 0 ;
- validation + test : f* = -13, levier empirique optimal 0, **edge hors échantillon négatif**.
**Conclusion : le levier n'est pas une solution.** Un levier multiplie les rendements et les coûts
(0.15 % de la marge par aller-retour à 1x, 1.46 % à 10x) sans créer d'edge ; sur le test il ne fait
qu'amplifier la perte (-2.6 % à 1x, -25.6 % à 10x). Le ciblage de volatilité ne rend pas le résultat
meilleur : la volatilité réalisée à l'horizon de 1 jour est élevée (crypto, actions), donc le levier
cible reste proche de 1x, et le Sharpe est inchangé à -7.05.

### Diagnostic funding par catégorie (`tools/funding_diagnostic.py`, `results/funding_diagnostic.txt`)

Doc : `F_8h = scale x (mean_P + clamp(0.0001 - mean_P, +/-0.0005))`, scale 1.0 crypto, 0.5 sinon. Sans
prime, le taux est donc la composante d'intérêt fixe : 1.25e-5 par heure (11 % par an) en crypto,
6.25e-6 (5.5 % par an) hors crypto, payés par les longs. Les taux publiés incluent déjà le scale.

| Catégorie | Funding annualisé moyen | Côté qui reçoit | Net 90 j / 365 j après un aller-retour* |
|---|---|---|---|
| equity (7 actions) | +5.99 % | short perp | +5.1 % / +5.8 % |
| index (SP500, NAS100) | +7.79 % (SP500 0 %, NAS100 +15.6 %) | short perp | +7.0 % / +7.6 % |
| crypto (BTC, ETH, SOL) | +4.34 % (BTC 8.2 %, ETH 3.6 %, SOL 1.2 %) | short perp | +2.8 % / +4.0 % |
| commodity (GOLD, SILVER, WTI) | -7.79 % (WTI -21 %, GOLD -6 %, SILVER +3.9 %) | long perp | +9.4 % / +10.2 % |

*coûts aller-retour supposés : perp 14 bps + couverture 6 à 23 bps selon la catégorie (hypothèses), avant
risques non chiffrés (emprunt, roll des futures, base, liquidation de la jambe perp, capital sur deux
plateformes, dividendes), et avant le coût du capital (repère 4 %/an).

**Le carry vaut-il une étude ? Pas en l'état.** (1) Actions et BTC : le funding est presque uniquement la
composante d'intérêt fixe (98 % d'heures positives sur les actions, écart-type faible), soit 5 à 8 % par
an, du même ordre que le coût du capital immobilisé sur deux plateformes : l'excès net est d'environ 1 à 2 %
avant des risques non chiffrés. (2) NAS100 et WTI montrent un excès lié à la prime (15 à 21 % par an) mais
instable (écart-type supérieur à la moyenne), sur 150 jours seulement, et WTI exige un roll de futures
non modélisé. (3) On ne dispose ni du prix de la jambe de couverture ni de la base perp/couverture : une
étude honnête est impossible avec les données actuelles. Étape la moins chère : l'enregistreur capture déjà
la base mark/index et le funding en continu ; la relire dans quelques semaines pour NAS100, WTI et BTC.

### Spread réel mesuré (un relevé de 45 s, lundi 2026-10-05 vers 17 h UTC, heures de séance)

Spread médian en bps du mid, puis coût d'un ordre marché de 5 000 de notionnel (acheteur) : BTC 0.1 / 0.1,
ETH 0.7 / 0.7, SOL 0.8 / 1.0, SP500 0.1 / 0.8, NAS100 1.0 / 0.5, GOLD 0.2 / 0.3, SILVER 2.4 / 1.5,
WTI 4.2 / 2.4, AAPL 3.9 / 1.9, MSFT 3.0 / 1.5, NVDA 3.6 / 3.3, TSLA 3.2 / 2.1. Le spread simulé de 2 bps et
le slippage de 2 bps par côté sont donc **prudents pour BTC et les indices**, et **proches de la réalité
pour les actions et WTI** en séance ; ces chiffres sont d'un seul instant, en séance, et ne valent pas
pour les heures creuses ni le week-end. À calibrer avec l'enregistreur.

## Build, tests, exécution

Windows, MSYS2 (g++ 14, CMake 3.31, Ninja). Warnings stricts, `-Werror`.

```
cmake -S . -B build -G Ninja
cmake --build build
ctest --test-dir build --output-on-failure

# Release pour les backtests et sweeps
cmake -S . -B build-release -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build-release

./build-release/perp_backtest --synthetic 20000 --seed 7
./build-release/perp_backtest --csv data/BTC-USD_1m.csv --trades results/trades.csv
./build-release/perp_backtest --csv data/BTC-USD_1m.csv --set leverage=3 --set min_edge=0.03
python tools/fetch_klines.py                 # data/<SYM>_1m.csv, _funding.csv, .instrument.yaml
./build-release/perp_validate --csv data/BTC-USD_1m.csv --funding data/BTC-USD_funding.csv \
    --config config.yaml --config data/BTC-USD.instrument.yaml --set symbol=BTC-USD \
    $(cat results/grid.txt)                    # train -> top K -> validation -> test une fois + lignes de base
python tools/signal_diagnostic.py data/BTC-USD_1m.csv
./build-release/perp_sweep --csv data/BTC-USD_1m.csv \
    --grid signal_threshold=0.6:0.8:0.05 --grid tp_rr=1,1.5,2 --grid leverage=2,3,5 \
    --out results/sweep.csv

# Panel multi-instruments (un seul jeu de paramètres), hors échantillon, puis levier, puis statistiques
python tools/fetch_klines.py --symbols SP500-USD NAS100-USD GOLD-USD SILVER-USD WTIOIL-USD AAPL-USD ...
python tools/survey_universe.py                # data/universe_survey.csv : catégorie, jours d'historique
python tools/sessions.py --apply               # colonne session dans data/*_1m.csv ; --check : profil d'activité
./build-release/perp_panel --mode search --symbols $(cat results/panel_symbols.txt) --config config_panel.yaml \
    --train-end 2026-08-15 --val-end 2026-09-10 $(cat results/grid_panel.txt) --out-prefix results/panel
./build-release/perp_panel --mode leverage --symbols $(cat results/panel_symbols.txt) --config config_panel.yaml \
    --train-end 2026-08-15 --val-end 2026-09-10 --params results/panel_final.txt --out-prefix results/panel
python tools/panel_stats.py                    # Bonferroni, Sharpe déflaté, Kelly
python tools/funding_diagnostic.py             # funding par instrument et par catégorie
python tools/recorder.py                       # enregistre carnet, tickers, funding (lecture seule), Ctrl+C pour arrêter
```

Les commandes se lancent depuis la racine du dépôt (`config.yaml` est cherché dans le dossier
courant). `--set` et `--grid` acceptent toute clé de `config.yaml` (y compris `instrument.*`).
Une clé inconnue est une erreur, pas un avertissement.

## Architecture

```
CMakeLists.txt
config.yaml            paramètres (jamais de secret ici : .env)
config_panel.yaml      paramètres FIXES de la famille B (pré-enregistrés)
include/perp/          en-têtes publics
  types.hpp            Instrument, Tick, Position (liq_price exact), ClosedTrade, Signal, breakeven_prob
  config.hpp           table X-macro (membre, clé yaml, défaut) : chargement, --set, grilles
  signal.hpp           PriceHistory, SignalEngine (rendement/vol, z, sigmoïde, fusion référence)
  risk.hpp             RiskManager : Kelly, sizing, plafond de levier, breakers, expositions
  position_manager.hpp SL / TP / trailing / time exit / garde-fou liquidation
  exchange.hpp         IExchange + PaperExchange (spread, slippage, frais, funding, liquidation)
  live_exchange.hpp    stub documenté (lève std::logic_error)
  bot.hpp              PerpBot : IDLE <-> HOLDING, identique en backtest, paper et live
  backtest.hpp         bougies, CSV, synthétique, 4 ticks par bougie, métriques, rapport
  sweep.hpp            grille cartésienne multi-thread, parallel_for
  validate.hpp         découpe chronologique, buy and hold, entrées aléatoires, régression alpha/beta
  panel.hpp            panel de sleeves indépendants, portefeuille équipondéré horaire, lignes de base
  mm.hpp               ABANDONNÉ : backtest passif de market making (rejeu de trades, bornes de fill, métriques)
src/                   implémentations + perp_backtest, perp_sweep, perp_validate, perp_panel (CLI) ;
                       perp_mm : ABANDONNÉ (quotation passive, résultat négatif, conservé pour mémoire)
tests/                 assert-based, check.hpp (CHECK_NEAR), un exécutable par module
legacy_py/             archive du premier jet Python, non testé, ne pas compléter
tools/                 fetch_klines, survey_universe, sessions, signal_diagnostic, funding_diagnostic,
                       panel_stats, recorder, fetch_trades, side_semantics, premium_study, leadlag_study,
                       fetch_binance, fetch_underlying, tsmom_study, underlying_vs_perp, grid_stage1, grid_stage2, fetch_tiingo, stocks_study, fetch_sec, earnings_study, p1_study, passive_fills, carry_study, long_horizon, recorder_xvenue, fetch_hl, funding_xvenue, vrp_study, fetch_pm, pm_calibration (stdlib uniquement) ;
                       mm_economics : ABANDONNÉ (quotation passive)
data/                  klines, funding, overlays instrument (CSV ignorés par git) ; data/under/ : sous-jacents longs ;
                       data/live/ : enregistreur ;
                       data/hist/ : trades, mark 1m, funding, instruments.csv (fetch_trades)
results/               grilles fixées (grid.txt, grid_panel.txt), rapports (panel_*, validation_*)
```

Flux d'un tick : `PerpBot::on_tick` met à jour l'historique, appelle `IExchange::on_tick`
(funding puis liquidation), puis soit `PositionManager::check_exits` (position ouverte, sortie
au marché), soit le pipeline d'entrée : signal, filtres (heures, z, spread), edge vs
`breakeven_prob`, sizing, `check_entry`, ordre marché.

Le backtest découpe chaque bougie en 4 ticks (o, l/h selon la couleur, h/l, c). C'est une
approximation : l'ordre réel de l'extrême est inconnu, donc SL et TP touchés dans la même
bougie sont départagés par convention (bougie haussière : le low d'abord).

## Conventions

- C++17, `-Wall -Wextra -Wpedantic -Werror`, pas de dépendance externe, pas de GoogleTest.
- Tests : `assert` (avec `#undef NDEBUG` pour rester actifs en Release) et `CHECK_NEAR`.
  Les valeurs attendues sont **calculées à la main** et la dérivation est dans le commentaire du
  test. Un test vert sans dérivation lisible n'est pas une preuve.
- Docs et commentaires : virgules, pas de tirets longs.
- Les prix sont des `double` (contrairement à `market_maker_bot`, en ticks entiers) : le moteur
  ne fait pas de matching, il simule des fills au marché.

## Invariants testés

- Prix de liquidation exact, long et short, avec et sans funding (`test_types`).
- PnL net avec frais et funding, long et short, calculé à la main (`test_exchange`).
- Liquidation : seuil, frais de liquidation au fill, perte plafonnée à la marge, shortfall.
- `round_trip_cost` = coût réel d'un aller-retour ouvert/fermé au même tick (même modèle).
- Plafond de levier : à ce levier, la liquidation est exactement à `D` du prix d'entrée.
- Sur un backtest complet : `equity finale = equity initiale + somme des PnL nets`
  (1e-9), la ventilation par raison somme au PnL total, identité par trade
  `pnl = signe x qté x (sortie - entrée) - frais - funding`, perte <= marge.
- Déterminisme : même entrée, mêmes trades bit à bit ; sweep identique à 1 ou N threads.
- **Sens du signal** (`test_direction`) : sur des régimes synthétiques nets (hausse, baisse, hausse), la
  stratégie par défaut gagne net et brut, les longs dans les hausses, les shorts dans les baisses, la
  première entrée après un retournement va dans le nouveau sens, la série miroir donne les côtés inverses,
  et sur du bruit pur elle ne gagne pas. Vérifié par mutation : avec Long et Short échangés dans
  `SignalEngine::compute`, ce test échoue. **Règle : ne jamais retourner le signal pour améliorer un
  résultat réel (data mining).** Un échec de ce test est un bug de signe, à signaler avant tout.

## Décisions techniques non triviales

1. **Tests** : assert + `-Werror` comme `market_maker_bot`, pas de GoogleTest (décision utilisateur).
2. **Pont Python** : sous-processus, JSON lines sur stdin/stdout (`perp_paper`), pas de pybind11
   (décision utilisateur). Pas encore écrit.
3. **Parité Python abandonnée** : le `PaperExchange` Python était tronqué ; il n'est pas complété.
   Les tests à résultats calculés à la main le remplacent. `perp/` et `main.py` sont archivés
   dans `legacy_py/`.
4. **Biais funding retiré en v1** : l'échelle `1e4/10` de l'ancien code était arbitraire. À
   réintroduire avec une unité claire (par exemple z-score du funding sur son historique).
5. **Seuil de liquidation** : `equity = mmr x notionnel au prix courant`, avec
   `equity = marge - funding payé + PnL`. Formule exacte (pas de mmr sur le notionnel d'entrée
   comme dans le Python) : long `P = (qE - C) / (q(1 - m))`, short `P = (qE + C) / (q(1 + m))`,
   `C = marge - funding`. Le funding payé déplace donc le seuil, `liq_price()` est dynamique.
6. **Frais de liquidation au fill** : doc `liquidation-mechanics` : `FillFee = Notional x (taux taker +
   taux de liquidation)`. `PaperExchange` facture donc `(taker + liquidation_fee) x notionnel` quand la
   liquidation se déclenche, au prix du tick observé (pire cas si le tick a sauté le seuil). Corrigé le
   2026-10-05 : la version précédente ne facturait que `liquidation_fee`. La perte est plafonnée à la
   marge (marge isolée) ; l'excédent est compté dans `shortfall()`.
7. **liq_guard tient compte de ces frais** : le garde-fou sort quand la distance à la liquidation
   est `<= liq_guard_pct + liquidation_fee`. Il reste ainsi de quoi couvrir les frais de liquidation.
8. **Plafond de levier** : distance de liquidation exigée `D = liq_buffer_mult x SL + liquidation_fee
   + liq_guard_pct`, donc le garde-fou ne se déclenche qu'après le SL. Formule exacte par côté
   (`1/L = mmr + D(1 -/+ mmr)`), pas l'approximation `1/(buf x SL + mmr)` du Python.
9. **mmr** : **confirmé par la doc** (`margin`) : `MMR = 0.5 / MaxLeverage`, taux plat par marché,
   indépendant de la taille, du tier et du levier choisi ; `MaxLeverage` est le levier max du marché
   (tier 0). `mmr_factor = 0.5` reste configurable ; `instrument.mmr` force un taux fixe. Les risk tiers ne
   servent qu'à plafonner le levier selon le notionnel (`invalid_leverage` au-delà).
10. **Coût aller-retour** : calculé par `IExchange::round_trip_cost`, qui réutilise les fonctions
    de fill de l'exchange (demi-spread et slippage de chaque côté, frais x2, funding estimé). Un
    test garantit qu'il égale le coût réel d'un aller-retour. Funding estimé = `max(0, signe x
    taux) x durée`, la durée attendue étant `time_exit_seconds` (sinon `max_hold_seconds`).
11. **Funding** : prélevé à chaque passage d'heure epoch, au notionnel courant (`qté x prix x
    taux`), les longs paient si taux > 0, les shorts reçoivent. Backtest : taux constant
    (`backtest.funding_rate_per_hour`, hypothèse), pas l'historique réel.
12. **Sizing et plafonds d'exposition** (défaut corrigé) : le Python proposait jusqu'à
    `max_account_leverage` (3x) alors que `max_net_exposure_pct` plafonnait à 2x, donc **toutes
    les entrées étaient refusées** avec la config par défaut. `RiskManager::size` borne maintenant
    le notionnel à la marge restante sous les plafonds net et brut.
13. **Kelly** : la constante magique `x4` du Python devient `kelly_base_fraction = 0.25` (fraction
    de Kelly après scaling pour laquelle le multiplicateur vaut 1). Comportement par défaut
    identique : `mult = scaling x f* / 0.25`, borné par `kelly_min_mult` / `kelly_max_mult`.
14. **Config** : table X-macro, YAML réduit (clé: valeur, sections d'un niveau, `null` = défaut,
    pas de `#` dans les valeurs). `taker_fee < 0` signifie « tier de l'instrument ».
15. **Pas de logique maker** : le bot n'envoie que des ordres marché (IOC). `maker_fee` est dans
    `Instrument` mais inutilisé.
16. **RNG du synthétique** : `mt19937_64` + Box-Muller maison, car `std::normal_distribution`
    n'est pas portable bit à bit entre bibliothèques standard.
17. **Sweep** : le thread appelant travaille aussi ; chaque point est indépendant (copie de
    `Config`), les résultats sont écrits à leur index, donc pas de verrou sur les données et un
    ordre de sortie déterministe. `--min-trades` filtre le classement affiché.
18. **Sorties au marché** : un SL est un ordre marché déclenché sur le tick, il remplit donc au
    prix du tick moins demi-spread et slippage, pas au prix du SL (le slippage de stop est modélisé).

19. **Données** : `/v1/info/klines` ne renvoie que les minutes avec au moins un trade ; les trous
    sont remplis par une bougie plate au dernier close (volume 0), sinon le temps saute et la vol
    est mal mesurée. 37 à 57 % des minutes sont réelles : le marché est fin, les prix périmés
    biaisent la vol à la baisse.
20. **Funding réel** : `/v1/info/funding` (pages de 100 en ordre décroissant, `start_timestamp=0`
    puis `end_timestamp` reculant). Rejoué en step : le taux publié à `ts + 37 ms` s'applique dès
    l'heure pile (`funding_at`, tolérance 1 s). Avant la première publication : 0. Le taux
    constant `backtest.funding_rate_per_hour` ne sert plus que sans fichier funding.
21. **risk_tiers** : levier max par tranche de notionnel (BTC 50x jusqu'à 250 000, puis 25x), pas un taux
    de maintenance (le MMR est plat, voir 9). L'overlay prend le levier du tier 0 ; sans conséquence tant
    que le notionnel par trade reste sous 250 000 (SOL : 20x puis 10x à 250 000).
22. **Validation** : 60/20/20 chronologique, démarrage à froid de chaque segment (historique vide,
    ~5 min perdues). Sweep sur train seulement, top K (5) par Sharpe avec >= 30 trades, confirmés
    sur validation, point final = meilleur Sharpe de validation parmi les K (>= 10 trades), test
    évalué une seule fois. Si aucun K ne tient en validation, test n'est pas touché. Halt de
    session désactivé pendant le protocole ; `halt_breached` (seuil `halt_report_pct`) le signale.
23. **Lignes de base** : buy and hold 1x (mêmes spread, slippage, frais, funding ; à comparer en
    rendement et Sharpe, pas en PnL absolu). Entrées aléatoires : `PerpBot::set_random_entries`
    (côté à pile ou face, filtres z et edge ignorés, tout le reste identique : SL dimensionné sur
    la vol, cooldowns, plafonds), probabilité d'entrée par tick calibrée (6 itérations) pour le
    même nombre de trades que la stratégie, 200 tirages.
24. **`--set`** accepte `symbol`, `mode`, `ref_symbol` (texte) en plus des paramètres numériques.

25. **Panel** : chaque instrument est un sleeve indépendant (equity 1000, risk manager propre, aucune
    limite croisée). Portefeuille équipondéré = moyenne des equity des sleeves, échantillonnée à l'heure ;
    un sleeve pas encore listé reste en cash (equity constante). Sharpe annualisé sur rendements
    horaires (x racine de 8760). Marché équipondéré = moyenne des rendements horaires des instruments
    actifs (sert de benchmark et de régresseur du beta).
26. **Préchauffage** : 2 jours de bougies avant validation et test alimentent l'historique du signal
    sans entrée ni courbe d'equity (`Tick::warmup`, `RunOptions::start_ts`). Train démarre à froid.
27. **Sessions** : la doc dit que les perps tournent 24/7 et que la session ne change que les flux de
    prix externes (index et mark) ; pas de calendrier exposé par l'API. Règles par catégorie dans
    `tools/sessions.py` (crypto toujours ouvert ; index et commodity fermés du vendredi 21:00 au dimanche
    22:00 UTC ; actions ouvertes lun-ven 13:30-20:00 UTC), colonne `session` des CSV. Contrôle : l'activité
    est 1.6 à 3.9 fois plus forte en séance. Hors session : pas d'entrée et le prix n'alimente pas
    l'historique du signal (pas de liquidité prise pour acquise) ; sorties, funding et liquidation
    continuent. La réouverture apparaît comme un gap (un seul gros rendement dans la vol). Jours fériés
    ignorés. `close_only` est lu dans `universe_survey.csv` (faux pour tous aujourd'hui) mais pas encore
    appliqué par le panel : exclure à la main tout instrument qui le deviendrait.
28. **Funding non-crypto** : les taux publiés incluent déjà le scale 0.5, rien à réappliquer dans le
    backtest ; l'estimation de coût d'entrée utilise le taux courant du tick.
29. **Sizing par levier** (`sizing_mode: 1`) : levier de compte `m` = `account_leverage`, ou
    `vol_target_annual / vol réalisée annualisée` (vol d'horizon du signal x racine(an / lookback)),
    borné par `max_leverage x margin_frac` et, si `apply_liq_cap`, par le plafond de liquidation
    (`liq_buffer_mult`). Notionnel = equity x m ; marge = min(notionnel, equity x margin_frac) ; levier de
    position = max(1, notionnel / marge) ; jamais de levier de position < 1, donc un levier cible < 1
    réduit le notionnel au lieu de réduire la marge. Les plafonds net, brut et max_notional ne
    s'appliquent pas dans ce mode (les mettre à 0 pour `check_entry`). Le mode 0 (risque / SL) reste le
    défaut : il y a découplé le levier du PnL, qui ne dépend que du risque par trade.
30. **Plafond d'entrées par jour** (`max_entries_per_day`) et historique de signal dimensionné sur
    `max(lookback, fenêtre de vol) + 300 s` (3600 s minimum), pour les lookbacks jusqu'à 1 jour.
31. **Statistiques de décision** (`tools/panel_stats.py`) : Bonferroni sur le t du Sharpe horaire du
    test (M = nombre total d'évaluations de test d'une hypothèse d'edge) comme critère ; Sharpe déflaté
    (Bailey, Lopez de Prado) sur le train, informatif ; Kelly gaussien `mu/sigma^2`, levier empirique
    maximisant la moyenne de `log(1 + L r)`, bootstrap par blocs de 24 h. Le t suppose des rendements
    horaires indépendants (optimiste s'ils sont autocorrélés).
32. **Univers** : `tools/survey_universe.py` (un appel klines par instrument, début réel de l'historique :
    `ui_live_time` n'est pas le début des données, BTC a des klines deux mois avant). 9 instruments sur
    88 ont >= 100 jours, 34 >= 60 jours, la plupart ~19 jours. Les actions sont très fines (8 à 11 % de
    minutes avec trades, 14 à 20 % en séance).
33. **Enregistreur** : voir la section « Format de l'enregistreur ».
34. **Sens du signal** : `test_direction` verrouille l'orientation (voir Invariants). Le signal n'est
    jamais retourné pour améliorer un résultat réel : un signal inversé trouvé par les données est du data
    mining, et le diagnostic de retour à la moyenne reste une hypothèse à valider sur du temps neuf.
35. **Mark à 1 minute, requote toutes les 60 s** : le mark à 1 s coûte 3456 requêtes par instrument et par
    40 jours (≈ 40 000 pour 12 instruments) ; à 1 minute, 58. Le mark d'un bucket n'étant connu qu'à sa fin,
    les quotes sont recalculées aux frontières de minute avec le dernier bucket terminé : aucune anticipation et
    aucune staleness au moment du recalcul (les quotes sont statiques entre deux recalculs, comme en
    réalité). On ne teste donc pas de requote plus rapide qu'une minute.
36. **Comptabilité du market making** (`MmResult`) : compte de marge simple (cash, inventaire, mark à marché).
    Décomposition vérifiée : `equity finale = equity initiale + capture de spread + PnL d'inventaire - frais
    maker - frais taker - frais de liquidation - funding - coût des sorties taker`, où capture = somme
    `signe x qté x (mark - prix de fill)` au mark en vigueur, PnL d'inventaire = somme `inventaire x variation
    du mark`. Réutilise de `perpcore` : `Instrument` (mmr = 0.5 / levier max, frais de liquidation),
    `FundingPoint` / `funding_at`, les chargeurs CSV, `parallel_for`. `PaperExchange` n'est pas utilisé : il
    modélise une position unique ouverte et fermée au marché, pas un inventaire alimenté par des fills passifs.
37. **Sortie taker** : prix = `mark x (1 -/+ (demi-spread effectif + 2 bps))`, frais 4 bps. Le demi-spread
    effectif est estimé par instrument sur les trades du TRAIN (écart entre prix moyen des achats et des
    ventes agresseurs par fenêtre de 60 s contenant les deux sens, médiane, plafonné à 20 bps) : c'est une
    MESURE de proxy (le spread coté réel passé n'existe pas), jamais le spread du carnet.
38. **Markouts** : à 1 s et 10 s sur un mid PROXY des trades (moyenne du dernier prix d'achat agresseur et du
    dernier prix de vente agresseur dans les 60 s, à défaut dernier prix) ; à 60 s et 5 min en plus sur le
    mark connu à t + h. Positif = favorable (achat : mid futur - prix de fill ; vente : l'inverse). C'est la
    sélection adverse MESURÉE sur les fills simulés, pas sur de vrais fills.
39. **Sessions** : fills et PnL ventilés par session (mêmes règles de calendrier que `tools/sessions.py`,
    recodées dans `in_session` de `mm.cpp`, testées contre les mêmes dates que le test Python).
40. **Protocole du market making** : voir « Pré-enregistrement : market making passif ». Un sleeve de 1000 par
    instrument, portefeuille équipondéré (moyenne des rendements nets en % et rendement journalier moyen),
    baseline à delta aléatoire, Bonferroni M = 5.

## Pré-enregistrement : market making passif sur historique de trades, écrit AVANT tout résultat

Écrit le 2026-10-05 17:56 UTC, après `tests/test_mm.cpp` et `perp_mm`, avant le premier lancement sur données réelles.
Un changement après coup invalide le test et doit être déclaré comme tel.

**Moteur** (`include/perp/mm.hpp`, `src/mm.cpp`) : rejeu des trades publics dans l'ordre. Toutes les 60 s
(résolution du mark à 1 minute, voir plus bas), les quotes sont recalculées autour du mark connu :
`bid = ref x (1 - (delta + decalage))`, `ask = ref x (1 + (delta - decalage))`, `decalage = skew_frac x delta x
(inventaire / plafond)`, arrondis au tick (bid vers le bas, ask vers le haut). Post-only, frais maker 1.25
bps. Plafond d'inventaire (notionnel) = `levier x inv_frac x equity` ; marge à plafond plein = `inv_frac x
equity`. Un ordre = 25 % du plafond. On ne cote pas un côté si l'ordre ferait dépasser le plafond.
Dépassement du plafond (par mouvement du mark) : sortie taker vers 0.5 x plafond au prix `mark x (1 -/+
(demi-spread effectif + 2 bps))` avec frais taker 4 bps. Funding horaire réel sur l'inventaire. Liquidation
simulée (equity <= mmr x notionnel, mmr = 0.5 / levier max ; frais taker + frais de liquidation ; marge
épuisée = fin de simulation). Un sleeve de 1000 par instrument, sans interaction.

**Sens du flux** : `side=long` = agresseur ACHETEUR (mesuré, `results/side_semantics.txt` : 52 trades long
au ask contre 6 au bid ; 41 short au bid contre 5 au ask). Un bid n'est servi que par un agresseur vendeur,
un ask que par un agresseur acheteur. Les trades `settlement=true` ne servent aucun fill.

**Bornes de fill (quatre, toutes rapportées dans tout rapport)** : optimiste (un agresseur de sens opposé
imprime à notre prix ou au-delà, on est servi de min(quantité du trade, reste de notre ordre), file nulle) ;
conservatrice (prix STRICTEMENT au-delà de la quote), avec file d'attente supposée devant nous de 0, 1000
ou 5000 de notionnel (volume cumulé des trades qualifiants à consommer avant d'être servi). **Borne
décisive pour la règle d'arrêt : conservatrice avec file de 1000.** Les trois autres sont des analyses de
sensibilité.

**Univers : 21 instruments à spread large**, choisis par la règle « spread médian >= 2.5 bps » (= 2 x frais
maker 1.25 : en dessous, l'aller-retour est négatif avant toute sélection adverse) sur le relevé de carnet
du 2026-10-05 (5 relevés par instrument, `data/live_probe/`) : AAPL, MSFT, NVDA, TSLA, GOOG, AMZN, META,
SNDK, INTC, SKHYNIX, ARM, ASML, DRAM, TSM, AMD, MU, HYPE, SKHY, AVGO, SPCX, WTIOIL. Exclus car < 2.5 bps :
SILVER (2.30), QCOM (1.10), SOL, ETH, NAS100, GOLD, SP500, BTC ; ils servent de **contrôle descriptif**
(derniers 14 jours, paramètres finaux, aucune sélection). Le relevé est mince (5 points) : la
classification est approximative, déclarée comme telle.

**Fenêtres UTC** (trades de 2026-08-26 à la fin des données, 40 jours) : train 2026-08-26 -> 2026-09-19,
validation 2026-09-19 -> 2026-09-27, test 2026-09-27 -> fin. Le calendrier du test recoupe celui consommé
par les familles directionnelles A et B (2026-09-10 -> 2026-10-05) : hypothèse, données et signal
différents, mais c'est le même marché sur les mêmes jours ; déclaré.

**Grille FIXÉE (30 points)** : `delta_bps` {1, 2, 3, 5, 8} x `leverage` {1, 3, 10} x `inv_frac` {0.25, 0.5}.
Fixes : `skew_frac` 0.5, `order_frac` 0.25, requote 60 s, frais maker 1.25 bps, taker 4 bps, slippage de
sortie 2 bps, `exit_to_frac` 0.5, equity 1000 par sleeve. **Un seul jeu de paramètres pour tous les
instruments.** Demi-spread de sortie = demi-spread effectif estimé sur les trades du TRAIN de chaque
instrument (mesure, fenêtres de 60 s, médiane), plafonné à 20 bps.

**Procédure** : sélection sur TRAIN par le rendement net moyen du portefeuille équipondéré sur la borne
décisive ; top K = 3 confirmés sur VALIDATION ; point final = meilleur net de validation (borne
décisive) ; test évalué UNE fois. Baseline : mêmes quotes mais delta tiré au hasard dans {1, 2, 3, 5, 8}
à chaque requote et chaque côté (50 tirages), mêmes règles et mêmes coûts.

**Décompte et correction** : 30 points en train (x 4 bornes calculées, une seule décisive), 3 en
validation, 1 sur test. Évaluations de test d'une hypothèse d'edge dans le projet : famille A (3) + famille B
(1) + market making (1) = **M = 5**, correction de **Bonferroni** sur le t du rendement journalier du
portefeuille en test (seuil p x 5 < 0.05).

**Critères de succès, tous requis, sur la borne décisive** : (1) rendement net moyen du portefeuille > 0
en validation ET en test, après frais maker, funding et sorties taker ; (2) au moins 5 des 21 instruments
positifs en validation ET en test ; (3) Bonferroni (M = 5) significatif sur le test ; (4) bat au moins
75 % des tirages de la baseline aléatoire sur le test.
**Règle d'arrêt** : si (1) n'est pas vérifié, conclusion NÉGATIVE, aucun code d'exécution. Si seule la borne
optimiste est positive : « non concluant », pas un succès. Si (1) est vrai mais (2) ou (3) non : « positif
mais non robuste », non concluant. Aucun gain de récompense de liquidité n'est estimé en dollars (paramètres
non documentés) ; on rapporte seulement le temps de présence des quotes à moins de 20 bps du mark et la
part de notre volume dans le volume total de trades (= volume maker de la plateforme, un maker par trade).

## Historique de trades Polymarket Perps : faits établis (2026-10-05)

Tout ce qui suit a été vérifié par essai sur l'API, sauf mention « doc ».

- **`/v1/info/trades`** : pages de 100 au plus (doc : « at most 100 trades per request »), du plus récent au
  plus ancien, `more` indique la suite. `start_timestamp` inclusif, **`end_timestamp` EXCLUSIF** (la page
  suivante ne contient pas les trades de la milliseconde frontière, alors qu'une page coupe parfois au
  milieu d'une milliseconde : jusqu'à 21 trades partagent une milliseconde dans une page ; le téléchargeur
  remonte avec `plus_ancien + 1` et dédoublonne par `trade_id`). `limit`, `page_size`, `from_id` sont
  ignorés ; un paramètre `cursor` existe (« invalid cursor » sur une valeur quelconque) mais son format
  n'est pas documenté et n'est pas utilisé. Champs : `trade_id` (unique, **non monotone** dans le temps),
  `instrument_id`, `side` (`long` / `short`), `price`, `quantity`, `settlement` (booléen), `timestamp`
  (ms), `hash` (« 0x » vide). **Aucun identifiant de compte, d'ordre, de maker ni de taker.**
- **Sens de `side` (mesuré, `tools/side_semantics.py`, `results/side_semantics.txt`)** : on relève le carnet
  toutes les 1.5 s en parallèle des trades et on classe chaque trade selon qu'il imprime au meilleur ask ou au
  meilleur bid du relevé précédent. Sur 5 instruments et 12 minutes : `side=long` imprime au ask 52 fois et
  au bid 6 fois ; `side=short` imprime au bid 41 fois et au ask 5 fois. **`side=long` = l'agresseur est
  acheteur (il prend le ask), `side=short` = l'agresseur est vendeur (il prend le bid).** Le maker est de
  l'autre côté : un trade `short` exécute un ordre d'ACHAT passif, un trade `long` un ordre de VENTE passif.
  Limites : ~100 trades classables (le reste tombe hors fenêtre de relevé ou dans une fenêtre où le carnet
  a bougé), horloges locale et serveur non synchronisées (décalage retenu entre -3 s et -0.5 s), environ 10 %
  de trades classés à contre-sens (le carnet a bougé entre deux relevés). La doc ne définit pas `side`.
- **Profondeur et complétude** : l'historique de trades remonte jusqu'au début de chaque instrument et rien
  n'est masqué par l'API sur la fenêtre téléchargée : pour chaque instrument contrôlé, **nombre de trades
  téléchargés / somme du champ `trades` des klines 1m sur la même période = 1.000 à 1.019**
  (`data/hist/trades_summary.txt`).
- **`/v1/info/mark-history`** : `interval` obligatoire parmi `1s`, `1m`, `5m`, `15m`, `30m`, `1h`, `4h`, `6h`,
  `12h`, `1d`, `1w` ; `start_timestamp` obligatoire ; 1000 points par page au plus, ordre croissant ; **seuls
  les buckets contenant une mise à jour du mark sont renvoyés** (doc) ; la valeur est **le dernier mark du
  bucket**, donc connue seulement à la fin du bucket (utilisé comme tel, sans anticipation). Les premières
  lignes d'un instrument peuvent valoir 0 (pas encore de mark) : ignorées. À 1 s, 40 jours coûtent 3456
  requêtes par instrument : on utilise `1m` (58 requêtes).
- **Historique de carnet : il n'existe pas.** La doc ne décrit que le carnet COURANT (`/v1/info/book`, profondeurs
  10, 100, 500) et des flux temps réel (WebSocket). Essais : `/v1/info/book` avec `timestamp`, `ts`,
  `start_timestamp` ou `end_timestamp` renvoie le carnet courant (paramètre ignoré) ; `book-history`,
  `orderbook`, `book/history`, `depth`, `snapshots`, `spread-history`, `quotes`, `l2` répondent 404.
  `/v1/info/bbo` existe mais ne donne que le meilleur bid/ask COURANT. Conséquence : ni la position dans la
  file, ni le vrai spread passé, ni la profondeur passée ne sont identifiables ; seul l'enregistreur
  (`tools/recorder.py`) peut les constituer, vers l'avant.
- **Limite de débit** : non documentée ; un 429 est apparu quand ~4 requêtes par seconde du téléchargeur se
  sont ajoutées à des sondes manuelles parallèles. `tools/fetch_trades.py` limite le débit GLOBAL (défaut 4 par
  seconde), recule exponentiellement sur 429, 5xx et erreurs réseau (Retry-After respecté), et est reprenable.

## Résultats : market making passif sur historique de trades (2026-10-05)

Protocole exactement tel que pré-enregistré (aucun paramètre changé après coup). Un test de plomberie a
d'abord tourné sur des données coupées avant la fenêtre de test réelle. Rapport complet :
`results/mm_backtest_report.txt` ; grille de train : `results/mm_train_grid.csv`.

**Conclusion NÉGATIVE. Le PnL net de la borne conservatrice décisive (strictement au-delà, file de 1000) n'est
positif ni en validation ni en test, et la borne optimiste ne l'est pas non plus. Aucun code d'exécution.**

Données (21 instruments, 2026-08-26 -> 2026-10-05, 40.7 jours, `data/hist/trades_summary.txt`) : marché
extrêmement fin, **de 172 à 1405 trades par jour et par instrument** (AAPL 538, NVDA 362, MSFT 352, TSLA 384,
WTI 1405, HYPE 1303, TSM 172), notionnel de 3 à 20 M$ par instrument sur 40 jours (soit 0.1 à 0.5 M$ par jour pour une
action). Complet : trades téléchargés / somme des klines 1.000 à 1.019.

| Fenêtre | Optimiste | Cons. q=0 | **Cons. q=1000 (décisive)** | Cons. q=5000 | Instruments positifs (q=1000) |
|---|---|---|---|---|---|
| Train 08-26 -> 09-19 | -2.586 % | -2.425 % | **-1.312 %** | -0.683 % | 7/21 |
| Validation 09-19 -> 09-27 | -0.817 % | -0.855 % | **-0.357 %** | -0.105 % | 7/21 |
| **Test 09-27 -> 10-05** | **-0.811 %** | -0.822 % | **-0.568 %** | -0.155 % | **5/21** |

(rendement net moyen en % de l'equity de 1000 par sleeve ; point final `delta_bps=8`, `leverage=1`,
`inv_frac=0.25`.) **0 point sur 30 est positif en train, sur aucune borne.** Instruments positifs sur validation
ET test (décisive) : **3/21**. Sharpe journalier du portefeuille : -17.8 (validation), -19.5 (test). Bonferroni (M=5) :
t = -3.06 sur 9 jours, p unilatérale 0.9989, non significatif. Baseline de deltas aléatoires : la stratégie fait
mieux que 100 % des tirages (le delta aléatoire moyen est à -0.99 % en test) : choisir un delta large perd moins que
choisir au hasard, mais perd quand même.

Critères pré-enregistrés : (1) portefeuille conservateur > 0 en validation ET test : **non** ; (2) >= 5 instruments
positifs en validation ET test : **non** (3) ; (3) Bonferroni : **non** ; (4) bat >= 75 % des tirages : oui (100 %),
sans importance puisque (1) échoue. L'ordre des bornes est la signature de la sélection adverse : plus la borne est
conservatrice (moins de fills), moins on perd (-0.81 % optimiste, -0.57 % q=1000, -0.16 % q=5000 en test), c'est-à-dire
que **chaque fill simulé perd de l'argent en moyenne**.

**Pourquoi (mesuré sur les fills simulés, test, borne conservatrice, tous instruments)** :
- spread capturé par rapport au mark : ~7.7 bps au delta de 8 (= delta, par construction) ; frais maker 1.25 bps par jambe ;
- **markouts (sélection adverse mesurée)** sur le mid proxy des trades, achat / vente : 1 s -7.2 / -6.9 bps, 10 s -8.2 /
  -7.8, 60 s -11.1 / -9.9, 5 min -9.0 / -7.7 ; sur le mark à t+60 s : -8.7 / -7.4. Le prix s'éloigne de 7 à 11 bps
  contre nous dès la seconde qui suit le fill, soit plus que le spread capturé net des frais (~5.2 bps) : le gain de
  spread est entièrement mangé, et au-delà. En validation, markouts à 60 s de -9.4 / -14.9 bps.
- **par delta (train et validation seulement)** : le markout à 60 s s'aggrave quand le delta grandit (achat -8.8 bps à
  delta 1 contre -13.9 à delta 8 en train) : on est servi surtout quand le prix traverse nos quotes, donc quand il
  bouge contre nous ; le spread capturé croît avec le delta mais moins vite que la sélection adverse. Le net reste
  négatif à tous les deltas.
- **séance / hors séance** : 1255 fills en séance contre 540 hors séance (test) ; spread capturé identique (7.63 /
  7.68, c'est le delta) ; PnL net -75.6 $ en séance et -43.7 $ hors séance (somme des 21 sleeves) : perdant
  dans les deux régimes. Spread effectif estimé sur les trades : de ~0 à ~4 bps selon l'instrument, médiane par
  fenêtre de 60 s, bruitée (peu de trades par fenêtre) : c'est un proxy, pas le spread coté.
- **sorties taker** : rares (0 à 1 par instrument en test, coût total de l'ordre de 0.1 $) : le plafond d'inventaire
  est rarement dépassé, le problème n'est pas l'inventaire mais la sélection adverse.
- **Les instruments les moins mauvais** (TSM, AMD, NVDA, GOOG en test, +0.3 à +0.8 %) ont 2 à 6 fills par jour : trop
  peu de fills pour distinguer le hasard (le test ne dure que 9 jours) ; les plus mauvais sont les plus actifs (WTI
  -2.5 %, ARM -1.7 %, SPCX -1.4 %, MU -1.3 %, HYPE -1.9 %).

**Récompenses de liquidité (aucun gain en dollars estimé)** : en prenant le volume de trades comme volume maker (un
maker par trade) et en lisant le seuil d'éligibilité de 1 % sur 7 jours instrument par instrument (lecture
incertaine : la doc ne dit pas s'il est par marché ou global), le seuil représente, en test, **de 10 000 $ (AVGO) à
132 000 $ (WTI) de notionnel exécuté par semaine**, 13 000 à 64 000 $ pour la plupart des actions (HYPE 95 000 $).
Notre notionnel exécuté ramené à 7 jours est de 600 à 6 000 $ pour les actions, 15 700 $ pour HYPE et 21 500 $ pour
WTI : de l'ordre de 5 à 15 % du seuil. Notre part du volume total de trades est de 0.04 % à 0.17 %. Temps de
présence de nos quotes à moins de 20 bps du mark : 67 % à 100 % du temps (colonne `pres%`). La formule de
récompense ne peut pas être évaluée (nombre de marchés actifs et volume maker total non documentés) ; **il
faudrait en outre que la récompense compense une perte de l'ordre de 0.6 % de l'equity en 9 jours, soit
~6 $ par sleeve de 1000**, ce qu'aucune donnée n'établit.

**Ce qui n'a pas pu être fait** : contrôle sur les instruments à spread étroit (BTC, ETH, SOL, SP500, GOLD, NAS100,
SILVER, QCOM) : non téléchargés ; par construction (spread médian < 2.5 bps = 2 x frais maker) leur aller-retour est
négatif avant toute sélection adverse, ce qui rend le contrôle peu informatif. Le mode `perp_mm --mode control` existe
pour le lancer si besoin.

**Limites de cette conclusion** : (a) 9 jours de test et très peu de fills par instrument ; la conclusion repose sur
la cohérence des markouts négatifs sur 21 instruments et trois fenêtres, pas sur un test précis par instrument ;
(b) les bornes de fill sont des modèles, pas des fills réels : une borne optimiste négative est une information forte
(même en étant servi dès que le prix touche notre quote, on perd), mais une borne conservatrice ne dit pas ce que
ferait un vrai maker bien placé dans la file ; (c) le mark à 1 minute, la requote à 60 s, des ordres statiques entre
deux requotes : un maker réel qui annule et recote en quelques centaines de millisecondes éviterait une partie de la
sélection adverse que l'on mesure (le markout à 1 s est déjà de -7 bps, ce qui suggère qu'elle est en partie
instantanée, mais le modèle ne peut pas le trancher) ; (d) aucun historique de carnet : ni file, ni spread coté passé.

## Changement de périmètre (2026-10-05) : fin de la quotation passive, cible directionnelle ou preneur de liquidité

La quotation passive est abandonnée : `perp_mm`, `mm.hpp`, `tools/mm_economics.py`, `tools/recorder.py` côté
carnet pour le market making ne servent plus à décider (ils restent dans le dépôt, étiquetés abandonnés, et leur
résultat négatif est consigné dans `docs/DECISION_NOTE.md`). Cible : un bot directionnel ou preneur de liquidité
(taker). Le moteur C++ (`perpcore`) reste la base ; les études d'événements des familles C et D sont en Python
(stdlib), car ce sont des études d'événements sur des séries de prix et non des simulations de portefeuille
complètes, et que les chiffres décisifs se vérifient à la main (tests Python avec valeurs calculées à la main).

## Pré-enregistrement : familles C (prime mark/index) et D (décalage avec un prix externe), écrit AVANT tout résultat

Écrit le 2026-10-05 18:43 UTC, avant la première exécution de `tools/premium_study.py --mode search` et de
`tools/leadlag_study.py --mode search` sur données réelles. Un changement après coup invalide le test.

### Ce qui existe (vérifié par essai et par la doc, 2026-10-05)

- **Historique du prix index : il n'existe pas.** `/v1/info/index?asset=BTC` (asset sans le suffixe `-USD`) renvoie
  seulement l'index COURANT (`index_price`, `constituents` vide) ; `interval` et `start_timestamp` sont ignorés. Les
  noms `index-history`, `index-price-history`, `index-prices`, `premium-history`, `premium`, `funding-premium`
  répondent 404. `klines` et `mark-history` acceptent sans effet les paramètres `price`, `type`, `price_type`
  (ignorés : mêmes données). `/v1/info/tickers` donne `index_price`, `mark_price`, `last_price`, `mid_price` COURANTS.
  **Les données de la prime mark/index ne peuvent donc venir que de l'enregistreur** (`tools/recorder.py` écrit
  `index`, `mark`, `basis_bps` toutes les 5 s dans `data/live/`), vers l'avant.
- **Seule trace historique partielle de la prime : le funding publié.** Par la formule de la doc,
  `F_8h = scale x (P + clamp(0.0001 - P, +/-0.0005))`, `FR_heure = F_8h / 8`, la prime horaire moyenne P (impact
  prices contre l'index) est déductible quand elle sort de la bande [-4, +6] bps (en dessous, le taux vaut l'intérêt
  fixe et P est CENSURÉ) : `P = u + 0.0005` si `u > 0.0001`, `P = u - 0.0005` si `u < 0.0001`, avec
  `u = 8 x FR / scale`. C'est une prime HORAIRE moyenne, publiée à la fin de l'heure, observable seulement en
  dislocation. Cela permet de tester une version grossière de la famille C sur 4 mois d'historique.
- **Sources de prix externes gratuites et légales** : (a) crypto : Binance spot, API publique, sans clé, klines à 1 s
  avec plusieurs semaines d'historique (testé : BTC, ETH, SOL, XRP, HYPE) ; (b) or : PAXG sur Binance est un jeton
  adossé à l'or, quasi sans volume à 1 s (volume nul sur la plupart des secondes) : trop mince, non retenu ;
  (c) actions, indices, pétrole : aucune source gratuite et légale à 1 s sans clé. Yahoo Finance n'a pas d'API
  publique officielle (scraping contraire aux conditions d'usage) ; Alpha Vantage, Twelve Data, Polygon exigent une
  clé et limitent fortement les requêtes à 1 minute de résolution ; Stooq ne fournit plus d'intraday gratuit
  exploitable. **On se limite donc au crypto** pour la famille D (BTC, ETH, SOL, XRP, HYPE).

### Famille C (prime) : étude sur le funding-implied premium

**Hypothèse** : quand la prime horaire moyenne publiée sort de la bande avec |P| > theta, le prix du perp converge
vers l'index dans les H heures suivantes, d'une quantité supérieure au coût aller-retour taker.
**Stratégie** (taker, `tools/premium_study.py`) : à la publication, P > theta : VENDRE le perp ; P < -theta : ACHETER ;
sortie H heures plus tard ; une position à la fois par instrument. **Le sens n'est jamais retourné.** Prix :
ouvertures des bougies 1m (entrée à la minute de publication, sortie H heures plus tard). Coût aller-retour =
2 x 4 bps de frais + spread médian du relevé de carnet de l'instrument (`data/live_probe/`, 5 relevés) + 2 x 2 bps
de slippage ; funding réellement payé ou reçu pendant la détention (taux publiés). Marge isolée : liquidation
testée sur les mèches des bougies 1m (distance exacte par côté, mmr = 0.5 / levier max).
**Univers** : les 28 instruments pour lesquels `data/<SYM>_1m.csv` et `data/<SYM>_funding.csv` existent (BTC, ETH,
SOL, HYPE, SP500, NAS100, GOLD, SILVER, WTIOIL, SPCX, 16 actions). Fenêtres UTC : train < 2026-08-20 ; validation
2026-08-20 -> 2026-09-12 ; test >= 2026-09-12 (>= 23 jours, jusqu'à 2026-10-05).
**Grille FIXÉE (9 points)** : `theta` {10, 20, 40} bps x `H` {1, 4, 12} heures ; un seul jeu pour tous les
instruments. Levier : variable d'étude SÉPARÉE (1, 2, 3, 5, 10 sur validation et test pour le point final : rendement
moyen par trade sur la marge, liquidations, coût en % de la marge), descriptive, non comptée dans M.
**Procédure** : sélection sur TRAIN par le rendement net moyen par trade (bps du notionnel), pool de tous les
instruments, >= 30 trades ; top 3 confirmés sur VALIDATION (>= 10 trades) ; point final évalué UNE fois sur TEST.
Baseline : mêmes nombres d'entrées par instrument, heures pleines tirées au hasard, côté au hasard, mêmes coûts et
même durée (200 tirages). Longs et shorts rapportés séparément.

### Famille D (décalage avec Binance) : crypto uniquement

**Hypothèse** : le prix du perp suit avec retard le prix Binance spot ; l'écart capturable à horizon de quelques
secondes dépasse le coût aller-retour taker.
**Mesure descriptive (non comptée dans M, fenêtres train + validation seulement)** : corrélation croisée entre le
rendement du perp (prix des trades) et le rendement Binance retardé de 1 s à 5 min (et avance du perp sur Binance),
par instrument, avec la pente (réaction attendue en bps par bps) et son implication pour un mouvement Binance de 10 bps.
**Stratégie** (taker, `tools/leadlag_study.py`) : à la seconde t, écart `g = (ln B_t - ln B_{t-w}) - (ln P_t - ln P_{t-w})`
en bps (B : clôture Binance 1 s, P : dernier prix imprimé du perp) ; si `g > theta` ACHETER le perp, si `g < -theta`
VENDRE ; **le sens n'est jamais retourné**. Exécution : le premier trade du perp d'agresseur acheteur (pour acheter)
ou vendeur (pour vendre) imprimé au moins 1 s après le signal, et au plus 60 s après (sinon pas de fill, compté) ;
sortie : le premier trade d'agresseur opposé imprimé H secondes après l'entrée (au plus 60 s d'attente). Les prix
d'exécution sont des PRIX IMPRIMÉS (le spread est donc payé implicitement) ; coût ajouté : 2 x 4 bps de frais + 2 x
2 bps de slippage = 12 bps. Une position à la fois par instrument.
**Instruments** : BTC, ETH, SOL, XRP, HYPE. **Fenêtres UTC** (données du 2026-09-14 à la fin) : train < 2026-09-26 ;
validation 2026-09-26 -> 2026-10-01 ; test >= 2026-10-01 (environ 5 jours).
**Grille FIXÉE (27 points)** : `w` {5, 15, 60} s x `theta` {5, 10, 20} bps x `H` {10, 30, 120} s ; un seul jeu pour tous.
Levier : étude séparée comme pour C. Procédure et baseline identiques à C (aléatoire : mêmes nombres d'entrées par
instrument, secondes tirées au hasard, côté au hasard, même règle d'exécution).

### Décompte, correction et critères communs

- Évaluations de test d'une hypothèse d'edge dans le projet : famille A (3) + famille B (1) + market making (1) +
  famille C (1) + famille D (1) = **M = 7** ; correction de **Bonferroni** sur le t du rendement par trade en test
  (p unilatérale x 7 < 0.05).
- Points évalués : C : 9 (train) + 3 (validation) + 1 (test) ; D : 27 + 3 + 1.
- **Critères de succès, tous requis, sur le point final** : (1) rendement net moyen par trade > 0 en validation ET en
  test, avec >= 30 trades en test ; (2) Bonferroni (M = 7) significatif en test ; (3) la stratégie bat >= 75 % des
  tirages aléatoires en test ; (4) longs et shorts n'ont pas un rendement net moyen négatif en test (côté avec >= 10
  trades) ; (5) le résultat n'est pas dû à une poignée de trades (rapport du meilleur trade au total).
- **Règle d'arrêt** : si rien n'est positif et robuste hors échantillon net de coûts, aucun code d'exécution.
- Plomberie : sur données synthétiques avec prime ou décalage injectés, la stratégie doit les capturer, du bon côté
  (tests `test_premium_study.py` et `test_leadlag_study.py`, dans ctest).
- Les fenêtres de test recoupent calendairement celles des familles précédentes ; données et hypothèses diffèrent ;
  déclaré.

## Résultats : familles C (prime) et D (décalage avec Binance), 2026-10-05

Protocole exactement tel que pré-enregistré. Synthèse de toutes les familles et conditions de reprise :
`docs/DECISION_NOTE.md`. Rapports : `results/premium_funding_report.txt`, `results/leadlag_report.txt`,
`results/leadlag_xcorr.log`.

**Les deux familles sont NÉGATIVES. Aucun code d'exécution.**

### Famille C : prime mark/index (proxy funding, 28 instruments)

- **Ce qui existe** : aucun historique de l'index (voir pré-enregistrement) ; l'enregistreur est la seule source de la
  prime à 5 s. Faute de mieux, test sur la prime HORAIRE déduite du funding publié (observable seulement hors de la bande
  [-4, +6] bps) : 61 174 heures, 28.5 % observables, 8.3 % avec |P| > 10 bps.
- **Convergence (train + validation seulement)** : sur 1612 dislocations |P| > 20 bps, la prime est encore hors bande
  après 1 h dans 92 % des cas, après 4 h dans 83 %, après 12 h dans 77 %, après 24 h dans 74 % ; temps médian de retour dans la bande
  24 h (p25 4 h, p75 48 h) ; |P| moyen 1 h, 4 h, 12 h plus tard (quand encore observable) : 34.2, 31.8, 28.7 bps. Corrélation
  de la prime d'une heure observable avec la suivante : 0.77. **La prime ne converge pas à l'échelle de 1 à 12 h.**
- **Stratégie (fader la prime, taker)** : 9 points en train, 0 avec rendement net moyen > 0 (meilleur theta = 40, H = 1 h :
  -8.4 bps). Point final : theta = 20 bps, H = 1 h. Train : -15.5 bps net (1025 trades), validation : -20.7 bps (153),
  **test : -22.7 bps du notionnel (154 trades, t = -5.25, win 27 %)**, coût aller-retour moyen 15.2 bps. Longs -25.0 bps,
  shorts -20.3 bps (aucun des deux côtés ne gagne). Entrées aléatoires de même rythme : -16.8 bps ; la stratégie fait mieux que
  10 % des tirages en test. Bonferroni (M = 7) : p = 1. Levier : le rendement par trade sur la marge est -0.23 % à 1x et
  -2.27 % à 10x (coût aller-retour 0.16 % à 1x, 1.63 % à 10x de la marge), 0 liquidation. Le levier amplifie la perte.
- **Limite** : la prime horaire moyenne est un proxy grossier (pas de réaction à la minute ou à la seconde), censuré dans
  la bande ; elle contient une part structurelle (base USDT/USD, prix périmés hors séance). Elle ne dit rien d'une
  convergence en quelques minutes, que seul l'enregistreur (`index`, `mark` à 5 s) pourra mesurer.

### Famille D : décalage avec Binance spot (crypto : BTC, ETH, SOL, XRP, HYPE)

- **Source externe** : Binance spot, klines 1 s, 2026-09-14 -> 2026-10-05 ; or, indices, actions : aucune source gratuite et
  légale à 1 s sans clé, donc non testés.
- **Corrélation croisée (train + validation)** : le perp SUIT Binance avec un retard court. Résolution 5 s : corrélation
  moyenne de 0.15 à L = +5 s (BTC 0.148, ETH 0.164, SOL 0.154, XRP 0.085, HYPE 0.074), 0.10 à +10 s, 0.05 à +30 s, 0.02 à
  +60 s, ~0 à +2 min et +5 min ; **côté perp qui mène : ~0** (|corr| < 0.012). Pente : 10 bps de mouvement Binance
  s'accompagnent de 1.51 bps de rendement perp au lag de 5 s, 0.96 à 10 s, 0.48 à 30 s (à 1 s de résolution : 0.71 bps à
  +1 s). **L'amplitude capturable est de l'ordre de quelques bps, très en dessous du coût aller-retour taker (12 bps de frais
  et slippage, plus le spread payé).**
- **Stratégie (27 points)** : 0 point avec rendement net moyen > 0 en train (tous autour de -9.6 à -9.9 bps). Point final :
  w = 60 s, theta = 20 bps, H = 30 s. Train -9.6 bps (1332 trades), validation -8.2 bps (483), **test -9.8 bps (234 trades,
  t = -8.43, win 20 %)** ; longs -11.3 bps, shorts -8.4 bps. Entrées aléatoires : -10.6 bps ; la stratégie fait mieux que 63 %
  des tirages, mais le gain brut (~2 bps) ne couvre pas 12 bps de coût. Beaucoup de signaux ne se remplissent pas (de 34 000 à
  147 000 « sans fill » en train : pas de trade imprimé dans le sens voulu dans les 60 s). Bonferroni (M = 7) : p = 1. Levier :
  -0.10 % par trade sur la marge à 1x, -0.98 % à 10x (coût 0.12 % à 1x, 1.2 % à 10x), 0 liquidation.
- **Conclusion : « rien à voir »** : un décalage réel mais inférieur au coût. Plomberie : sur décalage injecté (20 s), la
  corrélation croisée culmine à 20 s et la stratégie le capture (tests `test_leadlag_study.py`).

## Changement de périmètre (2026-10-05, suite) : sous-jacents non crypto, historiques longs

Nouveau périmètre : instruments non crypto (indices, matières premières, actions, éventuellement devises), testés sur le
SOUS-JACENT avec un historique long (plusieurs décennies), puis à valider sur le perp lui-même. Pas de market making,
pas de signal inversé a posteriori. Les familles précédentes restent consignées dans `docs/DECISION_NOTE.md`.

### Sources de données : conditions d'usage vérifiées une par une (2026-10-05)

| Source | Données obtenues | Conditions d'usage lues | Statut |
|---|---|---|---|
| **FRED** (Réserve fédérale de Saint-Louis), `fredgraph.csv` du bouton « Download » | NASDAQ100 (1986 -> 2026), NASDAQCOM (1971 ->), WTI spot EIA (1986 ->), Brent spot EIA (1987 ->), EUR/USD (1999 ->), USD/JPY et GBP/USD (1971 ->), indice dollar large (1973-2019 puis 2006 ->), bon du Trésor 3 mois | « données pour un usage personnel, non commercial, éducatif et public » ; séries à copyright tiers (Nasdaq, S&P) : usage personnel seulement ; extraction non perturbatrice ; citer FRED | **AUTORISÉ** pour une recherche personnelle |
| **FRED, S&P 500** | seulement 10 ans (2016 ->), accord de licence S&P Dow Jones Indices | idem, 10 ans d'historique maximum | autorisé mais **trop court** : non utilisé |
| **Bibliothèque de Kenneth French** (Dartmouth) | rendement quotidien du marché actions américain 1926 -> 2026 (CRSP pondéré, dividendes inclus) | copyright Fama et French ; aucune clause d'interdiction trouvée ; pas de licence explicite ; usage de recherche courant avec citation | **toléré, usage personnel seulement** ; PROXY du S&P 500 |
| **Banque mondiale, Pink Sheet** | or et argent, prix MENSUELS MOYENS 1960 -> 2026 | « usage informatif et non commercial », attribution à The World Bank Group | **AUTORISÉ** ; biais de lissage (moyennes) |
| LBMA / ICE Benchmark Administration (or, argent quotidiens) | réponse 403, licence IBA requise pour les données historiques | licence payante | **EXCLU** |
| Stooq | exige une vérification JavaScript pour télécharger | contournement non fait | **EXCLU** |
| Yahoo Finance | aucune API publique officielle | scraping contraire aux conditions d'usage | **EXCLU** |
| Alpha Vantage, Twelve Data, Tiingo, Polygon | historiques d'actions individuelles | clé personnelle à créer et quotas ; je ne peux pas ouvrir de compte | **NON UTILISÉS** (voir plus bas) |

**Ce qui manque et que les sources autorisées ne donnent pas** : l'or et l'argent QUOTIDIENS (seulement des moyennes
mensuelles), le S&P 500 lui-même (proxy : marché américain total return), le Brent des futures (spot EIA), le DXY d'ICE
(proxys Fed), et **toute action individuelle** (aucune source sans clé à long historique) : les perps d'actions ne sont donc
PAS testés dans cette famille. Les devises (EUR/USD, DXY) ne sont pas listées chez Polymarket (catégories : crypto, index,
equity, commodity) : elles sont rapportées à part, à titre descriptif.
Fichiers, périodes, trous et ajustements : `data/under/MANIFEST.txt` (généré par `tools/fetch_underlying.py`).
**Ajustements et limites** : French = rendement TOTAL (dividendes inclus, un perp d'indice n'en verse pas : biais favorable
aux longs) ; NASDAQ100 = indice de prix ; WTI et Brent = prix SPOT EIA, pas de roll de futures à corriger mais pas d'historique de
futures ; WTI négatif les 2020-04-20 et 04-21 (points non positifs écartés du chemin quotidien) ; or et argent = moyennes
mensuelles (le signal et l'exécution au même prix moyen créent une autocorrélation artificielle : **résultats non fiables
pour le momentum, rapportés mais non décisifs seuls**) ; trous de jours fériés de FRED écartés ; aucun split ni dividende
individuel (pas d'actions).

### Hyperliquid, trade.xyz : endpoint d'historique pour perps non crypto (doc officielle et essai, 2026-10-05)

- **Existe** : l'API publique `POST https://api.hyperliquid.xyz/info` avec `type: "candleSnapshot"` (bougies de 1m à 1M ;
  doc : « **seulement les 5000 dernières bougies** » ; préfixe du dex pour les perps HIP-3, par exemple `xyz:XYZ100`) et
  `type: "fundingHistory"` (par `coin`, 500 points par page, `startTime` inclusif, supporte les dex HIP-3). trade.xyz est le
  déployeur `xyz` (HIP-3) : **131 perps** non crypto (indices XYZ100, SP500, JP225, KR200 ; or, argent, platine, palladium,
  cuivre, pétrole CL et Brent, gaz ; EUR, JPY, GBP, KRW, DXY ; dizaines d'actions).
- **Durée mesurée** (bougies journalières et funding disponibles depuis la cotation) : XYZ100 depuis 2025-10-13 (358 jours),
  TSLA 2025-11-13, NVDA 2025-11-12, GOLD 2025-12-22, EUR 2025-12-23, SILVER 2025-12-26, BRENTOIL 2026-03-04, SP500 2026-03-18 ;
  les bougies de 1 h ne remontent qu'à 2026-03-11 (limite des 5000). **Au plus environ un an : insuffisant pour un
  backtest de plusieurs régimes**, utile seulement pour comparer un perp à son sous-jacent. Non téléchargé ici (pas de
  décision qui en dépende).

### Famille E : momentum de séries temporelles, grille et critères FIXÉS avant tout résultat

Écrit le 2026-10-05 20:55 UTC, avant la première exécution de `tools/tsmom_study.py --mode search` sur les données réelles.

**Univers de décision (6 instruments, tous listés chez Polymarket)** : SP500 (proxy : French, rendement total), NAS100
(FRED NASDAQ100), WTI (FRED, spot EIA), BRENT (FRED, spot EIA), GOLD et SILVER (Banque mondiale, moyennes mensuelles).
Sleeves de capital égal. **Extras descriptifs, hors décision** : EUR/USD, proxy DXY (chaîne DTWEXM puis DTWEXBGS).
**Sous-ensemble robuste (critère 7)** : SP500, NAS100, WTI, BRENT (séries quotidiennes, sans biais de lissage).

**Signal et position** (rééquilibrage à la fin de chaque mois, position tenue le mois suivant) : rendement cumulé sur L mois,
`s = signe(P_t / P_{t-L} - 1)` ; `ls` (long/short : +1 ou -1) ou `lo` (long seul : +1 ou 0). Pondération : `equal` (|w| = 1) ou
`volscaled` (`w = 0.10 / sigma`, sigma = écart-type annualisé des 12 derniers rendements mensuels, |w| plafonné à 3). Au moins
12 rendements mensuels d'historique requis. **Le sens n'est jamais retourné. Un seul jeu de paramètres pour tous les instruments,
jamais de réglage par instrument.**
**Grille FIXÉE (16 points)** : L {1, 3, 6, 12} x {ls, lo} x {equal, volscaled}.

**Modèle de coûts Polymarket (appliqué à chaque rééquilibrage)** : coût = |variation de poids| x (frais taker 4 bps + demi-spread
+ slippage 2 bps). Demi-spread tiré du relevé de carnet du 2026-10-05 (médiane, 5 relevés) : SP500 0.13 bps de spread, NAS100
0.32, GOLD 0.24, SILVER 2.30, WTI 3.68 (Brent : valeur du WTI, non mesurée) ; extras : 2 bps. **Funding : HYPOTHÈSE H_F, écrite
avant les résultats** : seule la composante d'intérêt fixe du funding non crypto s'applique, `0.5 x 0.01 % / 8 h` = 6.25e-6 par heure
soit **0.4563 % du notionnel par mois, payé par les longs, reçu par les shorts** (5.475 % par an), la prime étant supposée de
moyenne nulle. Mesuré sur 4 mois seulement (non utilisé) : funding moyen annualisé SP500 0 %, NAS100 +15.6 %, GOLD -6.2 %,
SILVER +3.9 %, WTI -21 %, très bruité. Sensibilité rapportée : funding nul. Levier : plafond de levier par instrument (50x SP500,
NAS100 ; 20x or, argent, pétrole ; 10x par défaut), `|w| x multiplicateur` plafonné à 95 % du levier max. **Liquidation simulée** :
marge isolée par sleeve, maintenance `mmr = 0.5 / levier max`, test sur le chemin QUOTIDIEN du mois quand il existe (séries
quotidiennes) ; sur les moyennes mensuelles (or, argent) test à la fin du mois seulement (limite). Une liquidation fait perdre
tout le capital du sleeve pour le mois, qui repart le mois suivant. Levier traité comme variable : multiplicateurs 1x, 2x, 5x et
volatilité cible 5 %, 10 %, 20 % par sleeve, avec drawdown, nombre de liquidations, pire mois, coût en % de la marge.

**Fenêtres** : train 1927-01 -> 2004-12 ; validation 2005-01 -> 2014-12 (inclut 2008) ; test 2015-01 -> fin des données
(2026-08, inclut 2020 et 2022). Sélection sur train par le Sharpe net mensuel annualisé du portefeuille ; top 3 confirmés sur
validation ; point final évalué UNE fois sur test. **Walk-forward (descriptif)** : à partir de 2005, chaque janvier on
re-sélectionne le meilleur des 16 points sur les données antérieures (>= 120 mois) et on le trade l'année suivante ; la série
recousue relit la fenêtre de test et n'est donc PAS un critère. **Régimes** : 2008 (2008-01 -> 2009-03), 2020 (2020-02 -> 2020-12),
2022 (2022-01 -> 2022-12), résultats par décennie.
**Baselines** : (a) buy and hold des 6 instruments (1x, mêmes coûts et funding) ; (b) allocation à volatilité égale long seul
(`w = 0.10 / sigma`, rééquilibrée chaque mois) ; (c) signes aléatoires : chaque mois et chaque instrument, signe tiré au hasard
avec les mêmes proportions de long, de short et de flat que la stratégie, mêmes poids, coûts et funding (500 tirages).
Longs et shorts rapportés séparément (contribution moyenne par mois de chaque côté).

**Décompte et correction** : 16 points en train, 3 en validation, 1 sur test. Évaluations de test d'une hypothèse d'edge dans
le projet : A (3) + B (1) + market making (1) + C (1) + D (1) + **E (1)** = **M = 8** ; **Bonferroni** sur le t du rendement
mensuel net moyen en test (p unilatérale x 8 < 0.05). En complément, Sharpe déflaté (Bailey, Lopez de Prado) sur le train, 16 essais,
informatif.

**Critères de succès, tous requis, sur le point final** : (1) Sharpe net (coûts et funding H_F inclus) > 0 en validation ET en test ;
(2) Bonferroni (M = 8) significatif en test ; (3) robustesse d'un régime à l'autre : rendement net positif dans au moins 2 des 3
fenêtres de stress (2008, 2020, 2022) ET dans au moins 60 % des décennies disposant de >= 60 mois ; (4) bat >= 75 % des tirages à
signes aléatoires en Sharpe sur le test ; (5) le Sharpe du test dépasse celui de l'allocation à volatilité égale long seul ;
(6) pour les variantes `ls`, les contributions moyennes des longs ET des shorts sont >= 0 en test ; (7) le sous-ensemble robuste
(SP500, NAS100, WTI, BRENT) a un Sharpe net > 0 en test.
**Règle d'arrêt** : si l'un des critères échoue, conclusion négative et aucun code d'exécution.
**Mesuré sur le sous-jacent** : tout ce qui précède. **À valider sur le perp lui-même (NON mesuré ici)** : l'écart de prix
perp / sous-jacent (base, prime, prix périmés), le comportement hors séance et le week-end, le spread et le slippage réels à la
taille d'un portefeuille, le funding réel (prime moyenne non nulle, mesuré à +-6 à +-21 % par an sur 4 mois), la liquidation
intramensuelle pour l'or et l'argent (moyennes mensuelles), les jours fériés, la continuité de cotation du perp (cotations
récentes : au plus ~1 an d'historique).

## Résultats : famille E (momentum de séries temporelles, sous-jacents non crypto), 2026-10-05

Protocole exactement tel que pré-enregistré (grille de 16 points, un seul jeu de paramètres, train 1927-2004, validation
2005-2014, test 2015-2026, test touché une fois). Rapport : `results/tsmom_report.txt` ; écart perp / sous-jacent :
`results/underlying_vs_perp.txt` ; sources : `data/under/MANIFEST.txt`. Synthèse de toutes les familles :
`docs/DECISION_NOTE.md`.

**Conclusion NÉGATIVE : 4 des 7 critères pré-enregistrés échouent. Aucun code d'exécution.** Tout ce qui suit est mesuré
SUR LE SOUS-JACENT (proxy pour SP500, NASDAQ100 pour NAS100, spot EIA pour WTI et Brent, moyennes mensuelles pour l'or et
l'argent) ; ce qui reste à valider sur le perp est en dernière partie.

Point final (sélectionné sur train puis validation) : **L = 12 mois, long/short, pondération par la volatilité (cible 10 % par
sleeve)**. Portefeuille équipondéré des 6 instruments, net de coûts Polymarket et de la hypothèse de funding H_F :

| | Train 1927-2004 | Validation 2005-2014 | **Test 2015-2026** |
|---|---|---|---|
| Stratégie : Sharpe (CAGR, drawdown max, t) | +0.60 (+5.3 %, 30 %, 5.3) | +0.92 (+5.9 %, 9 %, 2.9) | **+0.31 (+1.9 %, 16 %, 1.07)** |
| Buy and hold 1x des 6 | +0.27 | +0.28 | +0.52 (+8.9 %) |
| Volatilité égale, long seul | +0.35 | +0.32 | **+0.56** (+4.2 %) |

Les 16 points ont un Sharpe net > 0 en train (meilleur 0.60, DSR 1.000 : une grille de 16 ne produit pas ce Sharpe par chance
de sélection). En validation le point final est significatif (t = 2.9) ; **en test il ne l'est plus (t = 1.07)**.

| Critère pré-enregistré | Résultat |
|---|---|
| 1. Sharpe net > 0 en validation ET test | **OUI** (+0.92, +0.31) |
| 2. Bonferroni (M = 8) significatif en test | **NON** (t = 1.07, p x 8 = 1) |
| 3. Robustesse : >= 2/3 stress positifs ET >= 60 % des décennies | **OUI** (stress 2/3, décennies 9/10) |
| 4. Bat >= 75 % des signes aléatoires (test) | **NON** (58 %) |
| 5. Sharpe test > volatilité égale long seul | **NON** (+0.31 contre +0.56) |
| 6. Longs ET shorts >= 0 en test | **NON** (longs +0.275, shorts -0.094 %/mois) |
| 7. Sous-ensemble robuste (SP500, NAS100, WTI, BRENT) : Sharpe > 0 en test | **OUI** (+0.11) |

- **Régimes** (rendement composé, stratégie / buy and hold / volatilité égale long seul) : 2008 (2008-01 -> 2009-03) +2.3 % / -34.0 % /
  -13.2 % ; 2020 +7.2 % / +27.6 % / +1.7 % ; 2022 -4.2 % / -10.1 % / -7.2 %. La stratégie protège en 2008 (c'est son apport) et
  rate le rebond de 2020. **Par décennie** (Sharpe) : 1930s +0.36, 1940s +0.42, 1950s +0.90, **1960s -0.15**, 1970s +1.31, 1980s +0.80,
  1990s +0.62, 2000s +0.53, 2010s +0.62, 2020s +0.59 (82 mois) ; elle bat à la fois le buy and hold et la volatilité égale long seul dans 6 décennies sur 10 (1930s, 1970s, 1980s,
  1990s, 2000s, 2010s) ; elle fait moins bien en 1940s (égalité), 1950s, 1960s et 2020s (marchés haussiers ou sans tendance).
- **Longs et shorts** : les longs contribuent +0.39, +0.35, +0.28 %/mois (train, validation, test) ; les shorts +0.08, +0.15, **-0.09**.
  Le gain vient surtout des longs et de la sortie du marché ; **les shorts n'ont perdu qu'en test**.
- **Par instrument en test** : NAS100 +0.48, SILVER +0.48, GOLD +0.28, SP500 +0.13, WTI -0.10, BRENT -0.14 (Sharpe du sleeve) ;
  le pétrole perd (long 63 mois, short 78 mois sur 141 : de nombreux changements de sens). EUR/USD et proxy DXY (hors
  listing Polymarket) : Sharpe +0.33 (train), -0.25 (validation), -0.15 (test) : le même signal n'y fonctionne pas.
- **Walk-forward (descriptif)** : re-sélection annuelle du meilleur des 16 à partir de 2005 : Sharpe +0.39 (CAGR +2.3 %, DD 18 %) ;
  2008 -7.8 % (le point retenu en cours d'année n'était pas celui qui protégeait), 2020 +7.2 %, 2022 -4.2 %.
- **Sensibilité au funding** : sans H_F, Sharpe de validation +1.19 et de test +0.49 (contre +0.92 et +0.31). Le funding supposé
  (5.475 % par an payé par les longs) coûte environ 0.2 de Sharpe ; sa valeur réelle (prime moyenne non nulle, mesurée de -21 % à
  +16 % par an selon l'instrument sur 4 mois) peut le changer dans les deux sens.
- **Levier** (point final, descriptif) : le Sharpe ne change pas avec le levier ou la volatilité cible (validation +0.92, test +0.31
  ou +0.32) ; le CAGR et le drawdown suivent. 1x : +1.9 % par an, drawdown 16 % (test) ; 2x : +3.4 %, 30 % ; **5x : +5.0 %, drawdown
  64 %, pire mois -43 %, 2 liquidations en test** ; vol cible 20 % : +3.2 %, 30 %. Coût d'exécution : de 0.005 % à 0.05 % de la marge par
  mois, négligeable (rééquilibrage mensuel) : **le funding et l'absence d'edge pèsent, pas les frais**.
- **Signes aléatoires** (chaîne de Markov à 3 états, mêmes proportions et même rythme, 300 tirages) : Sharpe moyen +0.26 en test
  [p5 -0.17, p95 +0.72] : l'échantillon aléatoire est lui-même positif parce que les marchés ont monté, ce qui rend le
  signal peu distinctif en test.

**Ce qui reste à valider sur le perp lui-même (mesuré en partie, `tools/underlying_vs_perp.py`, ~5 mois)** :
- **NAS100** : le perp suit son sous-jacent de très près : corrélation quotidienne 0.996, écart de niveau moyen +4.3 bps (écart-type 10, extrêmes
  -21 et +40 bps), écart-type de la différence quotidienne 12.3 bps. **47 % de la variance du perp tombe hors séance US** (19 % des
  heures) : le comportement hors séance est celui du perp, non mesurable sur le sous-jacent.
- **WTI** : **le perp ne suit PAS le prix spot EIA** : écart de niveau moyen -320 bps (écart-type 222, de -747 à +801), corrélation
  quotidienne 0.84, écart-type de la différence 204 bps ; 62 % de la variance hors séance. Le perp référence très probablement un contrat à
  terme (base spot / terme, roll) : **le résultat sur le spot EIA ne s'applique pas au perp WTI ni Brent**, qui doivent être testés sur leur
  propre historique (au plus ~5 mois chez Polymarket, ~1 an chez Hyperliquid xyz).
- **Non mesuré** : écart de l'or et de l'argent (pas de série quotidienne), de SP500 (proxy rendement total), spread et slippage réels
  à la taille d'un portefeuille, funding réel de long terme, jours fériés, liquidation intramensuelle de l'or et de l'argent, continuité
  de cotation (listés depuis 2026-05 chez Polymarket).

## Doc : récompenses de liquidité et frais (lue le 2026-10-05, sans extrapolation)

Sources : `docs.polymarket.com/perps/liquidity-rewards.md` et `.../perps/learn-about-trading/fees.md`
(copie brute dans `results/docs_rewards_fees.txt`).

**Frais** (taux appliqués au notionnel `abs(prix x quantité)`, en pUSD, paliers sur le volume des 30 derniers
jours, réévalués chaque jour UTC) :

| Volume 30 j >= | Taker | Maker |
|---|---|---|
| 0 $ | 0.0400 % | 0.0125 % |
| 1 M$ | 0.0370 % | 0.0100 % |
| 5 M$ | 0.0350 % | 0.0080 % |
| 25 M$ | 0.0300 % | 0.0050 % |
| 100 M$ | 0.0270 % | 0.0020 % |
| 500 M$ | 0.0250 % | 0.0000 % |
| 1 Md$ | 0.0200 % | -0.0050 % (rebate) |

Un maker ne reçoit un rebate qu'à partir du palier de 1 Md$ de volume sur 30 jours. Un sous-ensemble de
comptes créés pendant la bêta est temporairement au barème du palier supérieur. En liquidation, le fill paie
en plus un taux de liquidation propre au marché (page liquidation-mechanics).

**Récompenses de liquidité** (tous les comptes sont automatiquement candidats, sans candidature ni liste) :
- **Budget** : 75 000 $ par jour, répartis **à parts égales entre les marchés actifs** ; un pool par marché ;
  les makers au score non nul se partagent le pool du marché au prorata de leur score. Période de 24 h de
  12:00 UTC à 12:00 UTC, créditée en pUSD sur le compte, étiquetée par sa date de fin.
- **Score** : `raw_score = maker_score^0.35 x active_liquidity_score^0.65 x uptime`.
- **Éligibilité** : au moins **1 % du volume maker des 7 derniers jours** (la part de l'entité est utilisée si
  le compte appartient à une entité de récompenses). Les trades entre un même compte, ou entre comptes d'une
  même entité connue, ne comptent pas. Pendant les 7 premiers jours du programme, la fenêtre démarre au
  début du programme.
- **Maker score** : `log(1 + min(part, 25 %) / 1 %) / log(1 + 25 % / 1 %)` : plafonné à 25 % de part.
- **Liquidité active** : le carnet est échantillonné plusieurs fois par période ; seule la liquidité posée à
  **moins de 20 bps du mid** compte, avec les poids 1.00 (jusqu'à 5 bps), 0.25 (5 à 10 bps), 0.10 (10 à 20
  bps), 0 au-delà ; frontières arrondies vers l'extérieur au tick valide suivant. Notionnel crédité plafonné à
  **100 000 $ par palier, par côté et par marché** (plafond indépendant pour chaque côté et chaque palier).
  `tier_score = min(notionnel, 100 000) x poids` ; les scores bid et ask se combinent par moyenne harmonique
  `2 x bid x ask / (bid + ask)` : zéro si un côté est absent.
- **Uptime** : part des snapshots terminés où le compte avait de la liquidité qualifiante des deux côtés ;
  le score de liquidité active est la moyenne sur les snapshots qualifiants.
- Polymarket peut modifier les paramètres ou disqualifier une activité manipulatrice ou abusive.

**Ce qui n'est PAS documenté** (à ne pas extrapoler) : le nombre de marchés « actifs » et leur définition
(donc la taille réelle d'un pool : 75 000 $ divisés par un nombre inconnu) ; la fréquence et le nombre de
snapshots par période ; le volume maker total d'un marché ou de l'exchange (donc ni la part de 1 %, ni le
partage du pool, ne sont calculables ici) ; si le seuil de 1 % s'apprécie par marché ou globalement (la page
des frais définit la « part maker » comme volume maker du compte divisé par le **volume total de l'exchange**,
la page des récompenses parle de « volume maker » : formulations différentes, non réconciliées) ; la date de
début du programme et sa durée ; les délais de versement ; les plafonds de récompense par compte ou par
marché autres que ceux ci-dessus ; le traitement des ordres post-only ou reduce-only ; l'effet sur les
frais. Aucune estimation de gain de récompense n'est donc faite dans ce dépôt.

## Économie du market making (`tools/mm_economics.py`)

Lit `data/live/` (enregistreur), sans ordre ni authentification. Par instrument, **en séance et hors séance
séparément** : spread moyen, médian, p90 `[MESURÉ]` ; profondeur au touch (notionnel au meilleur bid et au
meilleur ask, notionnel dans 5 bps) `[MESURÉ]` ; volatilité à court terme du mid (variance réalisée par
seconde sur les tickers, intervalles > 30 s exclus, ramenée à 1 s, 10 s, 60 s) `[MESURÉ]` ; P&L théorique
d'un aller-retour maker = spread - 2 x frais maker, avant sélection adverse `[DÉRIVÉ]` ; seuil de sélection
adverse par exécution qui annule le gain = (spread - 2 x frais maker) / 2 `[DÉRIVÉ]` ; horizon tau* tel
qu'un mouvement de 1 sigma égale ce seuil `[DÉRIVÉ]`.

`[SUPPOSÉ]` (écrit en tête de chaque rapport) : exécution des deux jambes au touch avec probabilité 1, sans
file d'attente ni fill partiel ; frais maker 1.25 bps par jambe (palier 0, `--maker-fee-bps`) ; ni inventaire,
ni funding, ni latence, ni récompenses de liquidité ; mid en marche aléatoire à variance constante.
`[NON MESURABLE ICI]` : la sélection adverse réelle, qui exige les exécutions du carnet et le mouvement du mid
après chacune. Le rapport affiche en tête **DONNÉES INSUFFISANTES** tant que l'enregistrement couvre moins de
`--min-days` jours (3 par défaut) : à lire alors comme indicatif, **sans conclusion**.

Avec les 45 secondes enregistrées à ce jour, l'outil ne permet rien de conclure. Le seul fait structurel,
qui ne dépend pas de la quantité de données : quand le spread moyen est inférieur à 2 x 1.25 = 2.5 bps,
l'aller-retour est négatif avant toute sélection adverse ; c'est le cas, sur ce relevé en séance, de BTC,
ETH, SOL, SP500, NAS100 et GOLD (spreads de 0.3 à 1.3 bps). Les récompenses de liquidité, non estimables
(voir ci-dessus), seraient le seul moyen de compenser. À relire après plusieurs jours, séance et hors séance.

## Format de l'enregistreur (`tools/recorder.py`, lecture seule, aucun ordre ni authentification)

JSON lines (un objet par ligne), rotation par jour UTC sous `data/live/<AAAA-MM-JJ>/`. Échantillon par
défaut : BTC, ETH, SOL, SP500, NAS100, GOLD, SILVER, WTIOIL, AAPL, MSFT, NVDA, TSLA (`--symbols` pour
changer). Fréquences : tickers 5 s (une requête pour tous), carnet 15 s par instrument (étalés), funding
600 s. Toute erreur (réseau, DNS, TLS, HTTP, JSON, champ manquant) est écrite dans `errors.log` ; la boucle
continue avec un délai croissant (jusqu'à 60 s) et ne plante jamais ; rien ne contourne un blocage réseau.

| Fichier | Contenu |
|---|---|
| `tickers.jsonl` | `t` (ms local), `sym`, `iid`, `session` (0/1), `lat_ms`, `index`, `mark`, `last`, `mid`, `oi`, `funding` (taux horaire courant), `next_funding`, `srv_ts`, `basis_bps` = (mark - index) / index x 1e4 |
| `books.jsonl` | mêmes champs communs ; `bids`, `asks` (10 niveaux `[prix, quantité]`), `bid`, `ask`, `mid`, `spread_bps`, `depth_bid` et `depth_ask` (notionnel cumulé à 5 et 20 bps du mid, clés `"5"` et `"20"`), `slip_buy` et `slip_sell` (coût de marché en bps vs mid pour 1000, 5000, 20000 de notionnel, `null` si 10 niveaux ne suffisent pas) |
| `funding.jsonl` | `sym`, `iid`, `ts` (ms, publication), `rate` (taux horaire), dédoublonné |
| `instruments.json` | instantané de `/v1/info/instruments` (une fois par jour) |
| `errors.log` | `horodatage où type: message` |

Usage prévu : (1) calibrer `default_spread_pct` et `slippage_pct` par instrument et par tranche horaire
avec `spread_bps` et `slip_*` ; (2) tester le déséquilibre du carnet (profondeurs `depth_bid` / `depth_ask`)
comme signal court ; (3) construire un modèle de fill maker ; (4) **holdout vierge** : aucune stratégie
n'a été réglée sur ces données, à réserver à une validation unique. Ne pas les utiliser pour
choisir des paramètres. Lancer : `python tools/recorder.py` (Ctrl+C pour arrêter), environ 15 Mo par jour
pour 12 instruments. Tests : `tests/test_recorder.py` (hors réseau, dans `ctest`).

## Pré-enregistrement : grille d'hypothèses large, étage 1 (prédictibilité brute), écrit AVANT tout résultat

Écrit le 2026-10-07, après `tools/grid_stage1.py --mode plan` et `--mode power` (qui n'utilisent que les rendements
futurs, jamais une variable) et après le test de plomberie sur données synthétiques, avant le premier calcul
`--mode run` sur données réelles. Un changement après coup invalide le test et doit être déclaré comme tel.
Cadre : aucun ordre réel, `LiveExchange` reste un stub, pas de market making, aucun signal retourné après coup.
Décision de l'utilisateur : grille large en deux étages, étage 2 seulement pour les cellules qui passent l'étage 1.

### Données, holdout, fenêtres

- **Gel du holdout : 2026-09-28 00:00 UTC.** L'étage 1 n'utilise que des données STRICTEMENT AVANT cette date (trades, klines,
  funding, marks, Binance). Tout ce qui est après (du 2026-09-28 à la fin des données, **y compris `data/live/`, l'enregistreur**)
  n'est lu qu'une seule fois, à l'étage 2, pour les candidats finaux. Compromis : holdout de 7 jours, pour garder 14 jours (cryptos
  sur trades et Binance) à 33 jours (autres sur trades) de découverte. Le calendrier du holdout recoupe celui des tests des
  familles A, B, MM, C, D (même marché, hypothèses et données différentes) : déclaré.
- **Fenêtre de découverte** : klines 1 minute de 2026-05-01 (T0) à 2026-09-28 (début de l'historique de chaque instrument :
  crypto, indices et matières premières depuis ~2026-05-06 à 06-01, actions depuis 2026-07-20). **Fenêtres plus courtes** : F1 (trades)
  commence le 2026-09-14 pour les cryptos et le 2026-08-26 pour les actions ; F7 (Binance) le 2026-09-14. Trois plis chronologiques
  de durée égale entre le début de fenêtre du groupe et le gel.
- **Instruments** (groupes poolés par classe) : `crypto` = BTC, ETH, SOL, XRP, HYPE (XRP n'a pas de klines : barres 1 minute
  reconstruites depuis ses trades, depuis le 2026-09-14 ; pas de funding XRP) ; `idx_cmd` = SP500, NAS100, GOLD, SILVER, WTIOIL ;
  `equity` = AAPL, MSFT, GOOG, AMZN, NVDA, META, TSLA (actions liquides). Les autres actions (AMD, ARM, ...) ne sont pas testées.
  Une cellule (variable, groupe) n'existe que si au moins 3 instruments du groupe ont la donnée requise (sinon indisponible).
- **Observation et rendement futur** : fin de la minute i ; observation seulement si la minute i a au moins un trade et, hors
  crypto, si la session est ouverte en i ET en i+h (colonne `session` ; HYPE sans colonne = 1). Rendement futur = ln(C[i+h]/C[i])
  en bps, C = dernier prix imprimé reporté. **Horizons** : 1 min, 5 min, 15 min, 1 h, 4 h, 1 jour. **Pas d'échantillonnage**
  (instants de décision multiples du pas, pour des observations quasi non chevauchantes) : 1, 5, 15, 15, 30, 60 minutes.
  Limite connue : le dernier prix imprimé est périmé dans les minutes creuses et contient un rebond bid-ask ; une variable de
  flux positive (dernier trade à l'ask) peut ainsi produire un renversement mécanique à 1 min : ce rebond est une propriété de la
  mesure, il fait partie de ce qu'on rapporte, et le ratio de tradabilité à coût réel (étage 2) est le juge.
- **Coût aller-retour par instrument** (ratio de tradabilité) = 2 x 4 bps de frais + 2 x 2 bps de slippage + spread médian du relevé
  de carnet de `data/live_probe/` (repli 2.5 bps sans relevé). Funding exclu à l'étage 1 (réel à l'étage 2).

### La grille : 67 variables, 149 couples (variable, groupe), 894 cellules planifiées

Cellule = (variable, horizon, groupe). **Décompte annoncé : 894 cellules planifiées** (crypto 372, idx_cmd 216, equity 306 ; F1 132, F2 192,
F3 108, F4 114, F5 126, F6 174, F7 48). Toutes les variables n'utilisent que des données connues à la fin de la minute i.

- **F1 flux d'ordres** (crypto, equity ; `side=long` = agresseur acheteur, mesuré ; trades de règlement exclus ; notionnel = prix x quantité) :
  `imb_10s`, `imb_1m`, `imb_5m`, `imb_15m` = (acheteur - vendeur) / (acheteur + vendeur) en notionnel sur la fenêtre ; `ntr_1m`, `ntr_15m` =
  ln(1 + nombre de trades) ; `vs_1m` = ln(notionnel de la minute / notionnel moyen par minute des 60 minutes précédentes), `vs_5m` =
  même chose sur 5 minutes contre la moyenne des 1440 minutes précédentes ; `big_15m`, `big_60m` = déséquilibre des gros trades
  (notionnel >= 90e centile du jour UTC précédent) ; `run_len` = longueur signée de la séquence en cours d'agresseurs du même côté
  (plafonnée à 50, ordre intra-milliseconde supposé celui du fichier). idx_cmd n'a pas de cellule F1 (seul WTIOIL a des trades).
- **F2 prix** (3 groupes) : `rn_5, rn_15, rn_60, rn_240, rn_1440` = rendement passé de k minutes / (volatilité par minute des 240 dernières
  minutes x racine de k) ; `range_15, range_60, range_240` = ln(plus haut / plus bas) en bps ; `rpos_60, rpos_240` = position du dernier prix
  dans [plus bas, plus haut] ; `gap_open` (idx_cmd, equity) = rendement entre la dernière clôture de la session précédente et le prix
  5 minutes après l'ouverture, défini dans les 60 premières minutes de la session. Momentum et retour à la moyenne sont la MÊME variable : le signe
  de l'IC dit lequel existe (jamais de variable miroir).
- **F3 régime** (3 groupes) : `vr_60_1440` = ln(vol 60 min / vol 1440 min), `vr_15_240` ; `vov_24h` = écart-type / moyenne des 24 dernières
  volatilités horaires (heures UTC terminées) ; `idle_before` = ln(1 + minutes sans trade avant la minute en cours) ; `zf_60`, `zf_1440` = part des
  minutes sans trade sur 60 et 1440 minutes.
- **F4 funding et base** (3 groupes, funding publié en step, connu à la publication) : `fund_lvl` (bps par heure), `fund_d1h`, `fund_d8h`
  (variations sur 1 h et 8 h), `xs_fund` (rang en coupe transversale du niveau de funding dans le groupe, au moins 3 instruments) ;
  `ph_pre` (indicateur : 5 dernières minutes avant l'heure pile), `ph_post` (5 premières minutes après l'heure pile), binaires, écart = moyenne
  si 1 moins moyenne si 0 ; `basis_ml` (equity seulement) = ln(mark du bucket / dernier prix) en bps. **L'index n'a pas d'historique** :
  écart mark / index non testable à l'étage 1.
- **F5 calendrier** (3 groupes) : `tod_sin`, `tod_cos` (heure UTC), `dow_sin`, `dow_cos` (position dans la semaine UTC) : testent seulement la
  première harmonique ; `weekend` (binaire) ; `prox_open`, `prox_close` = minutes signées (écrêtées à +-240) par rapport à 13:30 et 20:00 UTC les jours
  de semaine (ouverture et clôture des actions US en heure d'été, valable sur toute la fenêtre). Les sessions propres aux indices et aux matières
  premières (réouverture dominicale) ne sont pas testées séparément : déclaré.
- **F6 inter-actifs** : crypto : `lead_btc_1/5/15/60` (rendement passé de BTC sur k minutes, cibles ETH, SOL, XRP, HYPE), `lead_eth_1/5/15/60` (cibles
  BTC, SOL, XRP, HYPE) ; equity : `lead_nas_5/15/60` (NAS100, cibles les 7 actions) ; 3 groupes : `xs_ret_5/60/1440` (rang du rendement passé de k minutes dans
  le groupe : momentum et reversal sont le signe de l'IC), `resid_15/60/240` (rendement passé de k minutes moins la moyenne des autres instruments du
  groupe : bêta de marché fixé à 1, approximation déclarée).
- **F7 externe public, cryptos seulement** (Binance spot, klines 1 s agrégées à la minute ; seulement open, close, volume : pas de volume taker) :
  `bn_ret_1/5/15` (rendement passé Binance), `bn_gap_1/5` (rendement Binance moins rendement perp, sur 1 et 5 minutes), `bn_sv_1/5` (PROXY du flux : volume signé par
  le sens de la bougie de 1 s, divisé par le volume), `bn_vsurp_1` (ln du volume de la minute / moyenne des 60 minutes précédentes). **Non testés (non récupérés)** :
  funding Binance, liquidations Binance.
- **F8 carnet : NON TESTÉ.** L'enregistreur ne couvre que 2026-10-04 et 10-05, après le gel du holdout : l'utiliser ici le détruirait. Réservé à
  l'étage 2, exploratoire.

### Puissance et exclusions (règle fixée avant résultat, n'utilise que y)

Pour chaque (instrument, horizon, fenêtre) : écart minimal détectable du spread de déciles extrêmes `MDE = (z_0.001 + z_0.80) x sigma_h x racine(2 / (0.1 x n_eff))`
avec `z_0.001 + z_0.80 = 3.29 + 0.84`, `sigma_h` l'écart-type du rendement futur, `n_eff` = nombre d'observations espacées x min(1, pas / h) ; au moins 300
observations. **Un instrument est exclu à cet horizon si MDE > 3 x son coût aller-retour.** Pour un groupe, on poole les instruments retenus : `MDE_groupe = 4.13 x
moyenne(erreurs-types) / racine(k_eff)`, `k_eff = k / (1 + (k-1) x rho)` avec rho = corrélation moyenne des rendements futurs entre instruments (repli 0.3) ; **le
groupe est exclu à cet horizon si MDE_groupe > 3 x coût moyen ou s'il reste moins de 3 instruments**. Limite : l'écart-type ignore les queues épaisses, le MDE est donc
optimiste. **Résultat (`results/etage1_power.csv`, `.json`) : 421 cellules retenues sur 894, 473 exclues comme sous-puissantes.** Horizons exclus : crypto 1 h, 4 h, 1 jour ;
idx_cmd 4 h et 1 jour ; equity 15 min, 1 h, 4 h, 1 jour (et F1 equity 5 min : 2 instruments seulement sur la fenêtre de trades). L'étage 1 ne dit donc RIEN des
horizons de 4 h et 1 jour (historique trop court), ni de 1 h hors idx_cmd.

### Statistiques, erreurs-types, tests multiples

- **IC de rang** = corrélation de Pearson des rangs (rangs moyens, ex aequo traités) de la variable et du rendement futur, dans l'échantillon de la cellule, par instrument,
  puis moyenne simple des instruments du groupe. **Écart de déciles** = rendement futur moyen du décile supérieur de la variable moins celui du décile inférieur (déciles propres à chaque instrument sur
  la fenêtre de découverte ; variables binaires : valeur 1 moins valeur 0), en bps, moyenne des instruments.
- **Erreur-type robuste** : jackknife par blocs de jours (supprimer un jour, 3 jours pour l'horizon 1 jour, MÊME bloc pour tous les instruments : tient compte de la dépendance
  temporelle et de la corrélation entre instruments), et dispersion de l'IC entre instruments (si >= 4 instruments) ; **on retient la plus grande**. z = IC / erreur-type, p bilatérale
  normale. Un bootstrap par blocs temporels de confirmation n'est écrit que si une cellule survit à l'étage 1.
- **Plis** : IC et écart de déciles calculés sur 3 plis chronologiques ; la cellule est **stable** si l'IC ET l'écart de déciles de chacun des 3 plis ont le signe de l'IC global.
- **FDR** : Benjamini-Hochberg à 5 % sur TOUTES les cellules retenues (421), p-valeurs étalonnées par les placebos (voir ci-dessous). **Faux positifs attendus : 0.05 x 421 ~ 21 cellules à p < 0.05 non corrigé ;
  sous BH à q = 5 %, au plus 5 % des découvertes sont fausses en moyenne.** Les cellules d'un même (variable, groupe) à plusieurs horizons sont corrélées : BH reste valide sous dépendance positive.
- **Placebos** (mêmes cellules, même procédure, variables décalées d'un retard aléatoire de 2 à 10 jours plus des minutes hors multiple de jour ; et mélangées par blocs de 120 minutes) : on rapporte la part de
  p < 0.05 (nominal 5 %), les découvertes BH et l'écart-type robuste des z placebos `sigma_pl = médiane(|z|) / 0.6745`. **Étalonnage fixé d'avance : lambda = max(1, sigma_pl) sur les deux placebos
  poolés ; les z des cellules réelles sont divisés par lambda avant BH** (le BH sans étalonnage est aussi rapporté). Les placebos servent à calibrer, pas à juger une cellule.
- **Contrôle positif** : test synthétique (`tests/test_grid_stage1.py`, dans ctest) : une relation injectée de signe connu doit être retrouvée par le pipeline (IC du bon signe, FDR, sur plusieurs
  graines) ; une relation nulle ne doit pas être trouvée ; absence d'anticipation vérifiée en tronquant les séries (les variables à l'instant t ne changent pas si l'on supprime le futur).
- **Passe l'étage 1** = (a) FDR (q étalonné <= 5 %) ET (b) stable sur les 3 plis ET (c) ratio de tradabilité = |écart de déciles| / coût aller-retour du groupe > 1 ET (d) cellule non exclue pour sous-puissance.
  Le rapport écrit TOUTES les cellules (`results/grille_etage1.csv`, `results/grille_etage1_instruments.csv`, cartes de chaleur `results/heatmap_F1.svg` ... `F7.svg`), les nulles comprises. Si rien ne passe : carte des
  corrélations mesurées et pourquoi elles ne couvrent pas les coûts.
- **Choix techniques libres** (notés ici) : IC calculé sur les rangs de l'échantillon espacé (exact, recalculé quand la variable est indéfinie pour certaines minutes) ; seuil des gros trades du jour précédent ;
  barres XRP reconstruites des trades ; HYPE session = 1 ; instruments à poids égaux dans un groupe ; `ntr_*` et `idle_before` utilisent les comptes de trades des klines ou des trades ;
  numpy absent, tout est en stdlib (`tools/grid_stage1.py`).

### Étage 2 (écrit maintenant, exécuté seulement si l'étage 1 laisse des cellules)

- Candidats : cellules avec `passes_stage1 = 1`. **Au plus un par famille** (celui au plus grand ratio de tradabilité), donc 7 candidats finaux au maximum. S'il n'y en a aucun : arrêt, conclusion négative, aucun code d'étage 2.
- Règle simple, sans optimisation de stop : entrée au marché (taker) à la clôture de la minute i quand la variable dépasse le seuil de décile (déciles estimés sur la fenêtre de découverte, par instrument, figés) du côté extrême
  où le rendement moyen de l'étage 1 est le plus grand en valeur absolue ; **le sens = le signe de ce rendement moyen mesuré à l'étage 1, jamais modifié ensuite** ; sortie à la clôture de la minute i+h ; une position à la fois par instrument ;
  pas de stop, pas de take profit. Un seul jeu de paramètres pour tous les instruments du groupe.
- Coûts : frais taker 4 bps x2, demi-spread du relevé de carnet de chaque côté (repli 1.25 bps), slippage 2 bps par côté, **funding réel** payé ou reçu pendant la détention (fichiers funding), liquidation testée sur les mèches 1 minute
  (marge isolée, mmr = 0.5 / levier max). **Levier variable d'étude** : 1x, 2x, 5x, volatilité cible 10 %, 20 %, avec coût d'exécution en % de la marge, drawdown, liquidations.
- Fenêtres : train = deux premiers tiers de la fenêtre de découverte, validation = dernier tiers, **test = holdout du 2026-09-28 à la fin des données, touché une seule fois par candidat** (le carnet de l'enregistreur n'y entre
  qu'en F8, exploratoire).
- Baseline : mêmes nombres d'entrées par instrument, minutes éligibles tirées au hasard, même côté et même horizon, mêmes coûts (200 tirages). Longs et shorts séparés.
- Décompte : évaluations de test d'une hypothèse d'edge = 8 (A 3, B 1, MM 1, C 1, D 1, E 1) + nombre de candidats finaux testés (au plus 7) ; **Bonferroni sur le t du rendement net par trade en test** (p x M < 0.05).
- Critères de succès, tous requis : (1) rendement net moyen par trade > 0 en validation ET en test, avec >= 30 trades en test ; (2) Bonferroni significatif en test ; (3) bat >= 75 % des tirages aléatoires en test ;
  (4) longs et shorts non négatifs en test (côté avec >= 10 trades) ; (5) le résultat ne dépend pas des 5 meilleurs trades (le total net sans eux reste > 0). **Règle d'arrêt : sinon conclusion négative, aucun code d'exécution
  (`perp_paper` non écrit).**

### Écarts déclarés au pré-enregistrement (écrits avant le lancement de l'étage 2)

1. **Ex aequo dans les déciles (corrigé après le premier lancement de l'étage 1).** Le premier lancement (`results/*_run1.*`, 354 cellules calculées sur 421) a laissé
   67 cellules sans résultat : pour les variables à beaucoup d'ex aequo (`ntr_1m`, `idle_before`, `prox_*`, `fund_lvl`), les rangs moyens plaçaient tout le bloc d'ex aequo au milieu
   et le décile extrême était vide, donc la cellule était écartée par erreur au lieu d'être testée. Défaut d'implémentation, pas un résultat. Correction : groupes extrêmes définis par
   valeur seuil, ex aequo inclus (`v <= 10e centile`, `v >= 90e centile`, taille éventuellement supérieure à 10 %), cellule écartée si les deux seuils coïncident ou si un groupe a moins
   de 20 observations. Relance complète. Les IC, erreurs-types et plis ne dépendent pas de ce choix ; le BH porte désormais sur 403 cellules calculées (et non 354) ; les 18
   cellules restantes sont réellement indisponibles (variable constante, indicateur sans observation à 1 ou à 0, ou moins de 3 instruments avec assez d'observations). Les deux
   lancements donnent la même seule cellule qui passe l'étage 1.
2. **Exécution de l'étage 2.** Le pré-enregistrement disait « entrée au marché à la clôture de la minute i ». Or le dernier prix imprimé est périmé et contient un rebond bid-ask : une entrée
   à C[i] rattraperait mécaniquement un prix déjà bougé (artefact de l'étage 1, qui mesure à partir de C[i]). L'étage 2 exécute donc, comme la famille D, sur PRIX IMPRIMÉS : entrée au premier
   trade d'agresseur du bon côté (acheteur pour acheter) imprimé au moins 1 s après la fin de la minute i et au plus 60 s après (sinon pas de fill, compté) ; sortie au premier trade d'agresseur opposé
   imprimé au moins 1 s après t_i + h minutes (au plus 300 s, sinon trade abandonné, compté) ; le spread est payé implicitement ; coûts ajoutés 2 x 4 bps de frais + 2 x 2 bps de slippage ; funding
   réel aux heures pleines traversées. L'exécution à la clôture avec le coût aller-retour de l'étage 1 est rapportée en sensibilité, non décisionnelle. Décidé avant tout résultat de l'étage 2.
3. **Ancrage des plis F1 crypto (corrigé après le deuxième lancement).** Les plis étaient ancrés au plus ancien départ de données du groupe (HYPE : trades depuis le 26 août) alors que la fenêtre F1
   crypto commence le 14 septembre : le pli 1 était vide, donc 10 cellules F1 crypto à IC significatif n'étaient pas déclarées « stables ». Défaut d'implémentation (le jeu de plis ne change
   ni IC, ni erreurs-types, ni FDR). Correction : ancrage au maximum du départ de données et du début de la fenêtre de la famille ; relance complète (`results/*_run2.*` conservés). Effet : stables
   32 -> 42, seule cellule candidate inchangée (aucune des 10 n'a de ratio de tradabilité > 0.26). L'étage 2 n'a pas été relancé (aucune de ses entrées n'a changé : mêmes D1 et D10).
4. **Liquidation de l'étage 2** : excursion adverse mesurée sur les mèches (plus bas ou plus haut) des klines 1 minute entre la minute du signal et celle de la sortie ; liquidation si elle dépasse la
   distance `1/levier de position - mmr` (mmr = 0.5 / levier max de l'instrument) ; perte = 100 % de la marge.

## Résultats : grille d'hypothèses large, étage 1 et étage 2 (2026-10-07)

Rapport complet : `docs/ETAGE1_REPORT.md` (cellules, FDR, placebos, puissance, carte des corrélations, étage 2). Fichiers : `results/grille_etage1.csv` (toutes les 894 cellules, nulles comprises),
`results/grille_etage1_instruments.csv`, `results/heatmap_F1.svg` à `F7.svg`, `results/etage1_power.csv`, `results/etage1_summary.txt`, `results/etage2_report.txt`.

**Conclusion NÉGATIVE. Aucun code d'exécution.** 894 cellules planifiées, 473 exclues (sous-puissantes : horizons de 1 h, 4 h, 1 jour presque partout), 18 indisponibles, **403 testées** ;
p < 0.05 non corrigé : 86 (20 attendues) ; **55 passent le FDR (BH 5 %)**, dont 44 en crypto ; 42 stables sur 3 plis ; **1 seule** passe le ratio de tradabilité > 1 : F7, rendement Binance sur 1 minute,
crypto, horizon 5 minutes (IC +0.181, z 13.5, écart de déciles 15.2 bps contre 13.0 bps de coût). Placebos : 4.4 % (retard) et 4.0 % (mélange par blocs) de p < 0.05, 0 découverte BH, lambda = 1.00 : erreurs-types
calibrées. F3 (régime) et F5 (calendrier) : rien (|z| maximum 2.6). F4 : `basis_ml` equity IC +0.32 à 1 minute mais instable, artefact de prix périmés. Flux d'ordres (F1) : IC 0.03 à 0.16 stable, mais 1 à 3 bps
entre déciles. F8 (carnet) : non testé. **Étage 2** (seule cellule, holdout 2026-09-28 -> 2026-10-05, touché une fois, exécution sur prix imprimés, frais 4 bps x2, slippage 2 bps x2, funding réel) : train -7.4 bps (932 trades),
validation -9.0 (382), **test -11.4 bps par trade (601 trades, t = -12.3)**, brut +0.65 bps, bat 12 % des entrées aléatoires ; les 5 critères échouent ; levier : 1x equity 0.50, 5x equity 0.03, aucune
liquidation, le levier amplifie la perte. L'effet de l'étage 1 (+8 bps côté haut) est surtout le rattrapage d'un dernier prix périmé. M passe à 9 pour Bonferroni.

## Pré-enregistrement : actions (Tiingo + perp), écrit AVANT tout résultat

Écrit le 2026-10-08, après `tools/fetch_tiingo.py`, `tools/stocks_study.py --mode plan` et `--mode power` (qui n'utilisent que des rendements, jamais une variable ni une relation) et après les tests de plomberie
(`tests/test_stocks_study.py`). Cadre : aucun ordre réel, `LiveExchange` reste un stub, pas de market making, aucun signal retourné après coup. Un changement après coup invalide le test et doit être déclaré.

### Données

- **Tiingo, plan gratuit** : 50 requêtes par heure, 1 000 par jour, 500 symboles par mois ; **licence « Internal Use Only » : usage personnel, aucune donnée brute dans `docs/`, `results/` ni aucun fichier partagé**
  (`data/tiingo/` est dans `.gitignore`, `results/` aussi ; `results/` ne contient que des statistiques agrégées). Clé dans `.env` (`TIINGO_API_KEY`, `.env` ignoré), envoyée en en-tête `Authorization`, jamais dans l'URL ni
  dans un journal. `tools/fetch_tiingo.py` : reprenable (état `data/tiingo/_state.json`), limiteur glissant 48 par heure et 950 par jour, une requête par ticker (historique complet), reprise sur erreurs réseau et 429.
- **Test d'AAPL avant tout le reste** : 11 544 jours du 1980-12-12 au 2026-10-06 ; prix **ajustés des splits et des dividendes** (champs `adjOpen/adjHigh/adjLow/adjClose/adjVolume`, plus `divCash`, `splitFactor`) :
  5 splits (1987, 2000, 2005, 2014 : 7, 2020 : 4), 90 dividendes ; au jour d'un split le rendement ajusté est +1 % à +10 % alors que le brut vaut -47 % à -85 % ; au jour du dernier dividende (0.27 sur 313.33) le rapport
  ajusté / brut saute de 0.99912 (attendu 1 - 0.27 / 313.33 = 0.99914) ; l'ajusté vaut le brut à la dernière date ; 248 à 254 jours par an ; seulement 3 trous de plus de 4 jours, tous des fermetures de marché réelles
  (11 septembre 2001, 2 janvier 2007, ouragan Sandy 2012) ; aucun volume nul, aucune bougie ajustée incohérente. Le total return ajusté est utilisé pour toutes les rendements (l'écart d'ouverture `adjOpen_t / adjClose_{t-1}`
  est un écart en total return, il inclut donc le dividende ex-date retiré ; le perp ne verse pas de dividende : écart négligeable à 1 jour, déclaré).
- **Univers** (`results/stocks_universe.csv`, métadonnées agrégées) : 38 instruments de catégorie action de `/v1/info/instruments` (2026-10-08), ticker Tiingo = `base_asset` (GOOG-USD est GOOGL). **4 absents chez Tiingo, exclus** :
  SKHYNIX, SAMSUNG, CXMT (non américains, non cotés aux États-Unis) et UNITREE (pré-IPO). **34 actions utilisables**, dont 26 avec plus de 5 ans de profondeur et 14 avec plus de 20 ans (INTC depuis 1980, AAPL 1980, AMD 1983, ORCL et MSFT 1986...) ; NBIS reprend l'historique de son prédécesseur (Yandex, 2011) ;
  les récentes (SPCX 80 jours, SKHY 62, CBRS 100, ARM 3 ans, SNDK 1 an) alimentent le panneau mais peu d'historique. **Biais de survie : l'univers est celui des actions listées AUJOURD'HUI par Polymarket (grandes capitalisations liquides,
  gagnantes récentes) ; tout résultat de longue histoire est biaisé en faveur des gagnantes et ce biais est étiqueté dans chaque rapport.** Perp : 13 klines 1 minute supplémentaires ont été téléchargés (QCOM, HOOD, MSTR, STRC, CRCL, COIN, RKLB, LITE,
  NBIS, ORCL, PLTR, BABA, ZM, 48 à 59 jours, 4 à 6 % de minutes avec trades).
- **Coûts** : frais taker 4 bps x2, slippage 2 bps x2, spread 3.5 bps en séance (relevé existant : 3 à 4 bps ; hors séance non mesuré, pas de test hors séance) soit **15.5 bps par aller-retour d'une action** ; coût d'un côté 7.75 bps (4 + 2 + demi-spread 1.75) ;
  funding : composante d'intérêt fixe 6.25e-6 par heure (0.0625 bps par heure, 5.475 % par an) payée par les longs et reçue par les shorts (un portefeuille long/short équipondéré se compense), historique réel de funding existant seulement depuis juillet
  2026 (non utilisé en étage 1, utilisé en étage 2 pour les périodes qu'il couvre). Rotation : coût d'un rebalancement long/short = 4 x rotation x 7.75 bps par unité de capital de jambe (rotation mesurée = part des titres changés, deux jambes, fermer puis ouvrir).

### Les hypothèses et la grille (41 cellules planifiées soumises au FDR, plus 3 descriptives H1a)

- **H1 écart de réouverture** (période perp, jours de séance, horaires par règle avec DST : 13:30 et 20:00 UTC en heure d'été américaine, 14:30 et 21:00 sinon ; jours de séance = jours de cotation du sous-jacent Tiingo).
  Mouvement du perp hors séance `move` = ln(P(13:29) / P(clôture veille 19:59)), écart réel `gap` = ln(adjOpen_t / adjClose_{t-1}) (bps), P(m) = clôture de la barre d'une minute qui débute en m (connue à m+1) ; résidu `res = move - gap`.
  **H1a (3 cellules descriptives, hors FDR)** : régression de `gap` sur `move` (bêta, erreur-type groupée par date et par action, R²) pour toutes les nuits, nuits de semaine, week-ends : si le bêta est proche de 1 le perp est déjà informatif.
  **H1b (12 cellules)** : `res` et `gap` (continuation puis retour : IC de rang et déciles) contre le rendement du perp de l'ouverture (barre de 13:30) à +30 minutes, +2 h, la clôture, sur toutes les nuits et les nuits de semaine ;
  variable normalisée par l'écart-type de chaque action, IC poolé, erreur-type jackknife par jour. Univers : actions avec au moins 40 jours de perp avant le gel (2026-09-28).
- **H2 coupe transversale quotidienne, longue histoire** : variables `mom_1, mom_5, mom_20, mom_60, mom_120` (rendement sur L jours) et `mom_60s, mom_120s` (idem sans le dernier mois : de t-L-21 à t-21 ; les sauts n'ont pas de sens pour 1, 5 et 20 jours) ;
  momentum et reversal sont le signe de l'IC ; au moins 10 titres par date ; **rendement ultérieur à 1, 5 et 21 jours** de clôture à clôture, dates non chevauchantes (rééquilibrage quotidien, hebdomadaire, mensuel) ; IC de rang par date, quintiles long/short équipondérés
  et pondérés par 1 / volatilité (60 jours), rotation mesurée. **21 cellules**.
- **H3 nuit contre séance** : rendement nuit `ON` = ln(adjOpen_t / adjClose_{t-1}), séance `ID` = ln(adjClose_t / adjOpen_t), moyenne équipondérée des actions par date ; sous-ensembles toutes les nuits, semaine (mar-ven), week-end (lundi) ; en plus sur le perp
  (`move` et clôture contre ouverture, avant le gel). **8 cellules** (2 x (3 Tiingo + 1 perp)). Seuil de rentabilité = |moyenne| / (15.5 bps +- funding de la durée de détention : 0.0625 bps par heure, 17.5 h la nuit de semaine, 65.5 h le week-end).
- **H4 résultats trimestriels : sautée.** Source gratuite et légale identifiée : EDGAR de la SEC (8-K, rubrique 2.02, horodatage d'acceptation). Elle exige un en-tête `User-Agent` avec un contact réel (nom et adresse électronique) : une requête avec un contact
  générique est refusée (HTTP 403, essayée deux fois). Pas d'adresse personnelle envoyée sans accord explicite : non faite ; Tiingo gratuit n'a pas de calendrier de résultats.

### Fenêtres, plis, puissance (règle fixée d'avance, n'utilise que les rendements)

- **Longue histoire (H2, H3 Tiingo)** : train jusqu'à 2012 inclus, validation 2013 à 2018, test 2019 au 2026-10-06. L'étage 1 n'utilise que **train + validation (avant 2019-01-01)** ; **le test 2019 -> 2026 n'est lu qu'une fois, à l'étage 2**, pour les finalistes.
  Trois plis chronologiques de nombre égal de dates dans la fenêtre de découverte. **Perp (H1, H3 perp)** : découverte avant le 2026-09-28, holdout ensuite (touché une fois à l'étage 2, l'enregistreur ensuite aussi).
- **Puissance** : écart minimal détectable (p = 0.001, puissance 80 %, `4.13 x erreur-type sous H0`) comparé à 3 fois le coût : H1b : déciles poolés, erreur-type avec effet de date (rho entre actions du même jour) ; H2 : spread de quintiles, `racine(2/q) x
  dispersion transversale / racine(nombre de dates)` avec q le nombre de titres par quintile, comparé à 3 x (4 x 0.5 x 7.75 = 15.5) bps ; H3 : `sigma / racine(n)` contre 3 x coût. **Une cellule dont le MDE dépasse 3 fois le coût n'est pas testée (sous-puissante).**
  **Résultat (`results/stocks_power.json`) : 13 cellules retenues sur 41.** Exclues : **les 12 cellules H1b** (18 actions, 42 à 71 jours chacune, 686 à 848 couples action-jour : MDE de 195 à 357 bps, contre une limite de 46.5 bps ; les gaps d'ouverture du perp sont des mouvements
  d'une centaine de bps), les 14 cellules H2 à 5 et 21 jours (MDE 52 et 217 bps contre 46.5 : trop peu de titres par quintile et de dates), et les 2 cellules H3 sur le perp (48 jours, MDE 84 à 91 bps). **Retenues : H2 quotidien (7 cellules) et H3 Tiingo (6 cellules).**
  H1b n'est donc pas testable en l'état (il faudrait plusieurs mois de perp supplémentaires) ; H1a, descriptif, est rapporté.
- **Univers H1** : 18 actions avec au moins 40 jours de perp avant le gel (AAPL, AMD, AMZN, ARM, ASML, AVGO, GOOG, INTC, META, MSFT, MU, NVDA, QCOM, SKHY, SNDK, SPCX, TSLA, TSM) ; les autres ont moins de 40 jours à la date du gel.

### Statistiques, tests multiples, contrôles

- H2 : IC de rang par date (Spearman, rangs moyens), moyenne sur les dates, erreur-type jackknife par blocs de dates consécutives (environ un mois : 21 dates à 1 jour) ; écart de quintiles équipondéré (principal) et pondéré par 1 / volatilité ; ratio = |écart| / (4 x rotation x 7.75).
  H3 : moyenne par date, jackknife par blocs de 20 dates, p normale. Plis : signe de l'IC (ou de la moyenne) et de l'écart identique dans les 3 plis. **Robustesse au titre (H2)** : retirer un titre à la fois ne change pas le signe de l'IC.
- **FDR** : Benjamini-Hochberg à 5 % sur les cellules testées (au plus 13), p étalonnées par les placebos (lambda = max(1, écart-type robuste des z placebos)). **Placebos** : H2 : signal décalé d'un retard de 30 à 250 jours, signal mélangé par blocs de 20 jours (la coupe transversale
  d'une autre date) ; H3 : signes tirés au hasard par blocs de 20 et de 60 dates. **Faux positifs attendus : 0.05 x 13 = 0.65** à p < 0.05 non corrigé.
- **Contrôle positif** (`tests/test_stocks_study.py`) : une autocorrélation journalière injectée (momentum ou reversal, 0.15) est retrouvée avec le bon signe, |z| > 4 ; sur du bruit rien ne passe le BH ; une dérive nocturne injectée de +20 bps est retrouvée ; mouvement et résidu H1 calculés à la main ; absence d'anticipation vérifiée
  (signaux et volatilité inchangés quand on supprime le futur) ; horaires de séance avec DST ; téléchargeur : limiteur de débit simulé, clé dans l'en-tête et jamais dans l'URL, `.env` et `data/tiingo/` ignorés.
- **Passe l'étage 1** = FDR (q étalonné <= 5 %) ET stable sur 3 plis ET robuste au titre ET ratio effet / coût > 1. Résultats : **toutes les cellules** (nulles, exclues, indisponibles) dans `results/stocks_stage1.csv`, carte de chaleur `results/stocks_heatmap.svg`, H1a dans `results/stocks_h1a.csv`.

### Étage 2 (écrit maintenant, exécuté seulement pour les cellules qui passent l'étage 1)

- **Au plus un finaliste par hypothèse** (plus grand ratio) : au maximum 2 (H2 et H3 ; H1b est hors étage). **M : 9 aujourd'hui (A 3, B 1, MM 1, C 1, D 1, E 1, grille large 1) ; M = 9 + nombre de finalistes testés** (annoncé : 9 + 0 à 2). Bonferroni sur le t du rendement net en test.
- **H2** : au rebalancement quotidien, long du quintile supérieur et short du quintile inférieur de la variable (le sens = signe de l'IC mesuré à l'étage 1, jamais modifié), pondération par 1 / volatilité 60 jours, au moins 10 titres, un seul jeu de paramètres pour toutes les actions ; coûts 7.75 bps par côté et par titre changé
  (rotation réelle), funding : intérêt fixe long contre short (net nul pour un portefeuille équilibré) ; levier : 1x, 2x, 5x, volatilité cible 10 % et 20 %, avec coût en % de la marge, drawdown, liquidations (mèches journalières ajustées, mmr = 0.5 / levier max, 10x pour une action) ; **test = 2019 -> 2026-10-06 touché une fois** (train jusqu'à 2012, validation 2013-2018) ;
  baseline : mêmes dates, rangs des titres mélangés (même rotation moyenne), 200 tirages ; longs et shorts séparés.
- **H3** : acheter (ou vendre selon le signe) chaque action à la clôture et sortir à l'ouverture, 1x, coût 15.5 bps plus le funding de la durée ; baseline = tenir les mêmes titres la séance (ouverture -> clôture) ; même test 2019 -> 2026, une fois.
- **Critères de succès, tous requis** : (1) net moyen par trade (ou par rebalancement) > 0 en validation ET en test ; (2) Bonferroni significatif en test ; (3) bat >= 75 % des tirages aléatoires ; (4) longs et shorts non négatifs en test ; (5) le résultat ne dépend pas des 5 meilleurs périodes ;
  (6) le test 2019-2026 reste positif sur la moitié la plus récente (2023-2026). **Règle d'arrêt : sinon conclusion négative, aucun code d'exécution.**

## Résultats : actions (Tiingo + perp), étage 1, 2026-10-08

Rapport : `docs/ACTIONS_REPORT.md` ; fichiers agrégés `results/stocks_*.{csv,json,txt,svg}` (aucune donnée brute Tiingo). **Conclusion NÉGATIVE à l'étage 1, aucun étage 2, aucun code d'exécution.** Biais de survie (univers actuel de Polymarket) étiqueté.
41 cellules planifiées, **28 sous-puissantes (écartées par la règle écrite d'avance), 13 testées**, 5 passent le FDR (BH 5 %, placebos calibrés, lambda = 1), 4 stables sur 3 plis, **0 avec ratio effet / coût > 1**.
- **H1a** (descriptif) : écart d'ouverture réel sur mouvement hors séance du perp : **bêta 0.70, R² 0.71** (0.66 et 0.67 en semaine, **0.89 et 0.88 le week-end**) : le perp est déjà informatif. **H1b non testable** (686 à 848 couples action-jour, MDE de 195 à 357 bps) ; descriptif : IC négatifs (-0.02 à -0.09), |z| <= 1.9.
- **H2** (daily seulement, 5 et 21 jours sous-puissants) : inversion fine à 1 et 5 jours (IC -0.012 et -0.010, q 0.016 et 0.044), **7.1 bps par jour bruts contre 12 bps de rotation** (ratio 0.59) ; pas de momentum à 20, 60, 120 jours.
- **H3** : la prime de nuit est réelle (**+9.5 bps par nuit, z = 8.7**, stable) mais le seuil de rentabilité est **16.8 bps** (ratio 0.57 ; 0.61 en semaine ; 0.38 le week-end) ; la séance est négative, non significative.
- H4 (résultats trimestriels) sautée : EDGAR exige un contact réel dans l'en-tête (403 sinon). M reste à 9. Le test 2019-2026 et le holdout perp du 2026-09-28 sont intacts.

## Pré-enregistrement : H4, résultats trimestriels (SEC EDGAR + Tiingo), écrit AVANT tout résultat

Écrit le 2026-10-08, après `tools/fetch_sec.py`, `tools/earnings_study.py --mode plan` et `--mode power` (rendements seulement, aucune relation) et `tests/test_earnings_study.py`. Cadre : aucun ordre réel, `LiveExchange` reste un stub,
pas de market making, aucun signal retourné après coup.

- **Accès SEC** : conditions d'accès automatisé d'EDGAR en une ligne : un en-tête `User-Agent` déclarant un contact réel et au plus 10 requêtes par seconde, sinon blocage (403 constaté sans contact). Le contact est autorisé explicitement par l'utilisateur pour cet usage
  et rien d'autre ; il est lu dans `.env` (`SEC_USER_AGENT`), jamais écrit dans le code, les tests, les rapports, les journaux, le dépôt ni les URL (les tests utilisent un agent factice et un réseau simulé). Téléchargeur : 5 requêtes par seconde, cache `data/sec/`
  (ignoré par git, aucun téléchargement redondant), reprise avec attente croissante.
- **Événements** : 8-K de forme exacte « 8-K » dont les items contiennent 2.02, via l'API de soumissions (page récente + fichiers historiques), CIK par `company_tickers.json`. **1 500 événements, 28 actions sur 34** ; 0 pour ARM, ASML, BABA, NBIS, SKHY, TSM (émetteurs étrangers :
  6-K, pas de 8-K) ; STRC partage le CIK de MSTR (doublon exclu, 73 événements). Période 2004 -> 2026 (l'Item 2.02 existe depuis 2003).
- **Classement** (heure d'acceptation EDGAR UTC convertie en heure de l'Est avec heure d'été exacte, bascule à 07:00 UTC le 2e dimanche de mars et 06:00 UTC le 1er dimanche de novembre) : avant 9:30 (BMO) : jour de réaction E = premier jour de cotation >= date de dépôt ; à partir de 16:00 (AMC) :
  E = premier jour de cotation > date de dépôt ; dépôt un jour sans cotation : E = premier jour de cotation suivant ; **pendant la séance (9:30-16:00 un jour de cotation) : exclu, compté** (75). Fenêtre de réaction = clôture(E-1) -> clôture(E) (le signal est la réaction du prix elle-même, pas de consensus d'analystes).
  **Ambigu et exclu, compté** : date de l'événement déclarée (`reportDate`) différente de la date de dépôt (le communiqué précède probablement le dépôt) : 123. Limite : l'heure d'acceptation du 8-K n'est pas l'heure du communiqué ; la date du trimestre n'est pas dans les métadonnées du 8-K (calendriers fiscaux différents) : non utilisée.
  **Retenus : 1 229** ; avec fenêtres complètes (60 jours de volatilité avant, 20 jours après) **avant 2019 : 587 (AMC 576, BMO 11)** : les 8-K à l'ouverture sont rares dans cet univers (grandes capitalisations technologiques qui publient après la clôture).
- **Grille (15 cellules soumises au FDR, plus 3 descriptives H4c)** : variable normalisée par la volatilité de l'action (écart-type des 60 rendements journaliers finissant en E-2), sous-groupes BMO, AMC et poolé.
  **H4a** (9) : `z_ann` = rendement d'annonce / volatilité, contre le rendement cumulé de clôture(E) à clôture(E+h), h = 5, 10, 20 jours de cotation. **H4b** (6) : `pre_z` = rendement de J-5 à J-1 (clôture E-6 -> clôture E-1) / (volatilité x racine(5)), contre la réaction elle-même et le rendement cumulé de E à E+5.
  **H4c** (3, perp, exploratoire, hors FDR) : nuits d'annonce AMC, BMO et poolées : bêta et R² de l'écart d'ouverture réel sur le mouvement du perp hors séance, contre les autres nuits (référence H1a : bêta 0.70, R² 0.71).
- **Fenêtres et statistiques** : longue histoire, train jusqu'à 2012, validation 2013-2018, **test 2019 -> 2026 jamais lu à l'étage 1 et encore intact** (H2 et H3 n'ont pas atteint l'étage 2 : aucun recoupement avec un test déjà consommé ; si un candidat atteint l'étage 2, le même test servira
  à plusieurs hypothèses : à déclarer). Étage 1 : événements avec toutes les fenêtres avant 2019-01-01 ; pseudo-instrument poolé (variable normalisée, IC de rang sur le rendement normalisé par `volatilité x racine(h)`, écart de déciles en bps bruts), jackknife par mois civil
  (clusters de date), 3 plis chronologiques, robustesse au titre (retirer une action à la fois), ratio = |écart de déciles| / 15.5 bps (frais et slippage 12 + spread 3.5 ; funding de la durée reporté à part en rapport de jambe : 0.0625 bps par heure x 33.6 heures par jour de cotation). Biais de survie : univers actuel de Polymarket,
  étiqueté.
- **Puissance (règle fixée d'avance)** : MDE du spread de déciles `4.13 x sigma x racine(2 / (0.1 x n_eff))` (n_eff corrigé de l'effet de mois) contre 3 x (15.5 + funding de la durée) ; sous-puissant => non testé. **Résultat : les 15 cellules sont sous-puissantes** (BMO : 11 événements ;
  AMC et poolé : 576 et 587 événements, MDE de 538 à 1 054 bps contre une limite de 47 à 173 bps : les rendements à 5-20 jours des actions concernées ont un écart-type de plusieurs centaines de bps). **H4a et H4b ne sont donc pas testables avec cet univers** (27 actions, 587 événements de découverte) : on ne détecte
  pas un effet de moins de ~500 bps, donc pas la dérive après annonce documentée dans la littérature (de l'ordre de 100 à 300 bps). Le test 2019-2026 n'est pas touché. H4c est rapporté en descriptif exploratoire et sous-puissant (quelques dizaines d'événements dans les 40 à 70 jours de perp).
- **FDR, placebos, étage 2** (appliqués si une cellule est testable) : Benjamini-Hochberg à 5 %, placebos « dates d'annonce décalées au hasard » (10 à 40 puis 41 à 120 jours de cotation, loin des vrais événements) ; contrôle positif synthétique (dérive injectée retrouvée avec le bon signe) ; étage 2 seulement pour
  FDR + stable + robuste + ratio > 1, un finaliste par hypothèse, M = 9 + finalistes (annoncé : 9 aujourd'hui, car aucun test n'est consommé).

## Résultats : H4, résultats trimestriels (2026-10-08)

Rapport : `docs/H4_REPORT.md` ; fichiers agrégés `results/earnings_*.{csv,json,txt,svg}` (aucune donnée brute Tiingo ni SEC redistribuée). **1 500 événements 8-K Item 2.02 (28 actions)**, 1 229 retenus après classement, **587 avec fenêtres complètes avant 2019 (AMC 576, BMO 11)**.
**Les 15 cellules H4a et H4b sont sous-puissantes (MDE de 538 à 1 054 bps contre 47 à 173 bps) : H4 n'est pas testable avec cet univers.** Aucun test, FDR vide, aucun étage 2. Le test 2019-2026 est intact, M reste à 9. H4c (exploratoire, perp) : sur 12 nuits d'annonce AMC dans les 70 jours de perp, le mouvement hors
séance du perp explique l'écart d'ouverture réel presque entièrement (bêta 0.98, R² 1.00, écart-type du gap 844 bps) contre bêta 0.66 et R² 0.66 les autres nuits : le perp prend l'annonce avant l'ouverture (il cote 24 heures sur 24) ; 12 événements : indicatif seulement. Pas de BMO dans la fenêtre perp.

## Pré-enregistrement : P1, signaux lents et exécution passive, écrit AVANT tout résultat

Écrit le 2026-10-08, avant `tools/p1_study.py` et toute mesure P1. Cadre : aucun ordre réel, `LiveExchange` reste un stub, aucun signal retourné après coup, pas de nouvelle recherche de signal. Les phases A à E, grille large, actions et H4 sont terminées
(H4 non testable) ; P1 agit sur le COÛT : ordres post-only maker (1.25 bps, pas de franchissement du spread) contre taker (4 bps + 2 bps de slippage + spread payé implicitement).

### Signaux (fixés et listés avant tout calcul, avec le chiffre qui les justifie)

- **S1 inversion en coupe transversale des actions** (34 titres, au moins 10 par date, quintiles : long du quintile le plus bas, short du plus haut, jamais retourné après coup ; signe négatif de l'IC mesuré dans la phase actions : `mom_5` q = 0.044, 7.1 bps par jour bruts contre 12.0 de coût taker ; `mom_1` q = 0.016 mais écart de quintiles +0.5 bps, 25.0 de coût) :
  **S1a** : rendement de 1 jour, tenu 1 jour ; **S1b** : rendement de 5 jours, tenu 1 jour (la cellule observée : 7.1 bps par jour) ; **S1c** : rendement de 5 jours, tenu 5 jours (entrée J, sortie J+4).
- **S2 tout signal des phases précédentes avec rapport effet / coût taker > 0.4 ET horizon >= 1 heure ET significatif (BH q <= 5 %) dans sa phase** (lecture explicite : un « signal » est un effet distinguable de zéro dans sa propre phase) :
  **S2a** : acheter chaque action à la clôture et sortir à l'ouverture suivante (prime de nuit, phase actions H3, toutes nuits : +9.5 bps par nuit, z = 8.7, q = 4e-17, ratio 0.57) ; **S2b** : idem les nuits de semaine seulement (+10.2 bps, ratio 0.61). Durée de funding exacte : 17.5 h en semaine, 65.5 h
  le week-end, soit 27.1 h en moyenne sur toutes les nuits (la phase actions avait compté 20 h : écart de 0.4 bps, sans conséquence sur ses conclusions).
  **Listés et non simulés** (justification chiffrée) : `resid_15` idx_cmd 60 min (grille large : ratio 0.52, q = 0.040, mais instable sur les plis et sans historique intrajournalier long) ; non significatifs dans leur phase malgré un rapport > 0.4 : `resid_60` idx_cmd 60 min (0.85, q = 0.115), `resid_240` idx_cmd (0.60,
  q = 0.354), `rn_60` idx_cmd (0.43, q = 0.38), `mom_20` quotidien (0.54, q = 0.51), `mom_60` quotidien (0.45, q = 0.23), séance du lundi (0.60, q = 0.16). Familles A à E : aucune cellule positive hors échantillon. Tout ce qui est plus rapide qu'une heure (flux d'ordres, Binance, inter-actifs crypto) est exclu :
  la sélection adverse y est trop forte.

### Cohérence signal / exécution (le point de conception critique)

- L'effet de 7.1 bps est mesuré de clôture à clôture ; il inclut l'écart de nuit, qu'une exécution passive à l'ouverture ne capte pas. Effet **exécutable** : signal calculé à la clôture de J-1, entrée au premier prix de séance **après 9h35 heure de l'Est** (jamais hors séance : oracle figé, spread non mesuré), sortie à **15h55** le jour J
  (S1a, S1b) ou J+4 (S1c). Les horaires sont convertis en UTC avec l'heure d'été exacte (13:35 et 19:55 UTC en heure d'été, 14:35 et 20:55 sinon). **Longue histoire (Tiingo, quotidien)** : l'entrée est approchée par l'ouverture officielle (adjOpen) et la sortie par la clôture officielle (adjClose) : approximation d'une minute à cinq
  minutes d'écart sur les 9h35 / 15h55, déclarée ; l'effet exécutable de la longue histoire est `ln(adjClose_{J+h-1} / adjOpen_J)`, rapporté À CÔTÉ de l'effet clôture-clôture `ln(adjClose / adjClose_{J-1})` ; **seul l'effet exécutable sert aux décisions**. L'exécution exacte (9h35 et 15h55) est mesurée sur le perp (partie B).
  S2 : entrée à 15h55 (en séance) et sortie au premier prix après 9h35 le jour suivant ; sur la longue histoire l'effet exécutable est approché par clôture -> ouverture (prime de nuit déjà mesurée), l'exécution exacte étant mesurée sur le perp.

### Partie A : effet exécutable sur la longue histoire (5 cellules soumises au FDR : S1a, S1b, S1c, S2a, S2b)

- Données Tiingo ajustées, train jusqu'à 2012, validation 2013-2018, **test 2019 -> 2026 jamais lu et encore intact** (la phase actions n'a pas atteint son étage 2) ; la découverte n'utilise que l'avant-2019 ; le test n'est lu qu'une fois, seulement pour une cellule qui passe la partie A.
- Statistique par cellule : série par date de l'effet exécutable d'un portefeuille long/short équipondéré (S1) ou de la moyenne transversale du rendement nocturne (S2), IC de rang rapporté ; coût maker = `4 x rotation x 1.25 bps` (S1, deux jambes fermées puis ouvertes) ou `2 x 1.25 bps + funding de la durée` (S2) ; **net = effet exécutable moins coût maker**.
  Rapport effet / coût maker et effet / coût taker (`4 x rotation x 7.75`) rapportés. Erreur-type : jackknife par blocs de dates (environ un mois), 3 plis chronologiques. Test unilatéral « net > 0 », Benjamini-Hochberg 5 % sur les 5 cellules, p étalonnées par des placebos du **brut** (signal décalé de 30 à 250 jours, signal mélangé par blocs de 20 jours ;
  signes aléatoires par blocs de 20 et 60 dates pour S2) : lambda = max(1, écart-type robuste de z).
- **Une cellule passe la partie A** = BH q <= 5 % ET net > 0 dans chacun des 3 plis ET robuste au retrait d'un titre (S1 seulement). La puissance (erreur-type et écart minimal détectable du net) est rapportée ; **si l'intervalle de confiance du net est trop large pour trancher, c'est écrit : non concluant**.

### Partie B : exécution passive sur le perp (période 2026-08-26 -> 2026-09-25, 22 jours de cotation, trades téléchargés pour les 29 actions ; holdout après le 2026-09-28 gelé)

- **Simulateur de fills basé sur les trades** (`tools/passive_fills.py`, réutilise le modèle du market making abandonné) : meilleur bid / ask = proxy (dernier trade de l'agresseur opposé des 5 dernières minutes, pas d'ordre s'il n'y en a pas) ; achat limite servi par un agresseur vendeur qui imprime à p ou en dessous (**optimiste**, file nulle) ou
  strictement en dessous après consommation de `Q` de notionnel qualifiant (**conservatrice**, file en notionnel : Q = 0, **1 000 (décisive)**, 5 000) ; ordres de 1 000 de notionnel, 1x, pas de fill partiel ; fill au prix limite. Taker : premier trade de l'agresseur du bon sens au moins 1 s après l'instant (au plus 5 minutes).
- **Politiques d'entrée (grille fixée)** : (a) taker au premier prix de séance (base) ; (b) limite post-only annulée après T, **sans repli** (non exécuté = zéro position) ; (c) idem **avec repli taker** à l'échéance ; T = 30 minutes, 2 heures, fin de séance (15h55) pour S1 (décision 9h35) ; pour S2 : décision à 15h55 - T avec T = 30 minutes ou 2 heures
  (l'échéance est toujours 15h55 ; « fin de séance » n'a pas de sens pour une entrée de nuit). Sortie : taker avec (a) ; sinon limite postée à 15h25 (S1) ou 9h35 (S2) valable 30 minutes avec **repli taker obligatoire** à l'échéance (une position ne peut pas rester ouverte).
- **Cellules annoncées** : S1 (3 signaux) x 7 politiques + S2 (2 signaux) x 5 politiques = **31 cellules d'exécution**, chacune sous 4 variantes de borne (optimiste, conservatrice Q = 0, 1 000, 5 000) soit 124 estimations ; **décisive : conservatrice Q = 1 000**.
- **Mesures** : taux d'exécution, délai moyen avant fill, **markout** (mouvement du mid proxy 1 min, 10 min et 1 h après le fill, positif = favorable : c'est la sélection adverse), PnL net par transaction exécutée ET **par signal émis (les non-exécutés comptent, à zéro)** ; frais maker 1.25 bps, taker 4 + 2 bps, **funding réel** (taux publiés) ;
  intervalle de confiance à 95 % par bootstrap par jour d'entrée (2 000 tirages) ; longs et shorts séparés ; moitiés de la période ; **baseline aléatoire** (mêmes nombres de signaux par jour et par côté, titres tirés au hasard parmi ceux négociables, même politique, 200 tirages) ; **levier** 1x, 2x, 5x, volatilité cible 10 % et 20 %
  appliqué à la politique de référence (c, T = 2 h) avec drawdown et liquidations (mèches des klines 1 minute).
- **Puissance** : 22 jours, quelques dizaines à quelques centaines de signaux par cellule, écart-type du net par transaction de 100 à 300 bps : l'erreur-type du net moyen par signal est de l'ordre de 10 à 25 bps, **plus que les effets attendus** (quelques bps). Annoncé d'avance : la partie B ne tranchera pas sur le signe d'un net de quelques bps ;
  elle sert à mesurer taux de fill, délai et markouts, et à calculer le **taux de fill et la qualité de fill minimaux** : sélection adverse maximale tolérée `A* = effet exécutable par transaction - coût maker - funding` (comparée aux markouts mesurés) et taux de fill minimal pour 1 bps par signal.

### Critères et règle d'arrêt

- **Positif robuste** (tous requis) : (1) partie A passée pour le signal ; (2) borne **conservatrice** (Q = 1 000) : net par signal émis > 0 avec borne basse de l'intervalle à 95 % > 0, positif dans les deux moitiés de la période, longs et shorts non négatifs, bat >= 75 % des tirages aléatoires ; (3) confirmation **une fois** sur le holdout du perp (après le 2026-09-28)
  et sur le test 2019-2026 (effet brut exécutable positif, une seule lecture) ; (4) Bonferroni sur le nombre de cellules d'exécution testées (31) et M mis à jour.
- **Non concluant** : borne optimiste positive seule, ou conservatrice positive mais intervalle contenant zéro. **Négatif** : borne optimiste non positive. Dans tous les cas, **aucun code d'exécution** tant que ce n'est pas positif, robuste et significatif hors échantillon.
- **M** : 9 aujourd'hui (A 3, B 1, MM 1, C 1, D 1, E 1, grille large 1) ; P1 ajoute au plus un finaliste par signal (5) s'il passe la partie A et la partie B : M annoncé = 9 + nombre de finalistes (aucun, donc 9, tant qu'aucun test hors échantillon n'est consommé).
- **Limites annoncées** : biais de survie (univers actuel de Polymarket), historique perp court (22 jours de cotation, 4 à 6 % de minutes avec trades pour les actions récentes), spread hors séance non mesuré (aucune entrée ni sortie hors séance), pas d'historique de carnet (proxy par les trades), file d'attente modélisée.

### Écarts déclarés au pré-enregistrement P1 (écrits avant la conclusion)

1. **Coût de l'effet exécutable de S1** : le pré-enregistrement parlait d'un coût de rotation ; l'exécution exécutable (entrée à l'ouverture, sortie à la clôture chaque période) ferme et rouvre TOUTES les positions chaque période (la rotation vaut 1, l'écart de nuit n'étant plus porté) : coût maker 4 x 1.25 = 5.0 bps par période et par unité de jambe,
   coût taker 4 x 7.75 = 31.0 bps. C'est une conséquence de la cohérence signal / exécution voulue, pas un changement de règle.
2. **Modèle taker** : au premier lancement de la partie B (`results/p1_summary_run1.txt`, `p1_partB_run1.csv`), un ordre taker n'était « exécuté » que si un trade du bon sens s'imprimait dans les 5 minutes (taux d'exécution de 21 à 28 %, artefact : un taker s'exécute toujours contre le carnet). Corrigé : sans trade imprimé après l'instant,
   repli sur le dernier trade de ce sens des 5 minutes précédentes (proxy périmé du meilleur prix opposé) ; sans trade récent, pas d'exécution (le taux taker reste de 44 à 52 % sur ces actions fines : il mesure la disponibilité d'un proxy de prix, pas la liquidité). Les conclusions sont les mêmes avant et après.
3. **Baseline aléatoire de S2** : S2 achète toutes les actions négociables chaque nuit (règle de calendrier, aucune sélection) : le tirage de « mêmes nombres de signaux » redonne exactement le même ensemble, baseline dégénérée ; sans objet pour S2 (critère « bat 75 % des tirages » non applicable), appliquée à S1.
4. **Intervalle Bonferroni** : borne basse du bootstrap par jour à 1 - 0.05 / 31 (5 000 tirages), ajoutée à l'intervalle à 95 %, car le critère (4) de la règle fixe la correction sur 31 cellules.

## Résultats : P1, signaux lents et exécution passive (2026-10-08)

Rapport : `docs/P1_REPORT.md` ; fichiers : `results/p1_partA.csv`, `p1_partB.csv`, `p1_summary.txt`. **Conclusion : AUCUN signal positif et robuste. Aucun code d'exécution.** Aucun test hors échantillon consommé (le test Tiingo 2019-2026 et le holdout perp du 2026-09-28 sont intacts), M reste à 9.
- **Partie A, effet exécutable (longue histoire, avant 2019)** : **l'inversion S1 n'est pas exécutable** : l'effet clôture-clôture de 7.09 bps (S1b) devient **-8.40 bps** en exécutable (entrée à l'ouverture, sortie à la clôture ; z net = -3.5) : la totalité de l'inversion se joue dans l'écart de nuit, que l'on n'exécute pas ;
  S1a -3.90 (clôture-clôture -0.53), S1c +6.93 bps ± 20.7 (non concluant). **S2 (prime de nuit) passe la partie A** : +9.55 bps (S2a) et +10.15 bps (S2b) bruts, **net du coût maker +5.35 et +6.56 bps par nuit** (z = 4.9 et 5.0, BH q ~ 0, positif dans les 3 plis).
- **Partie B, exécution passive sur le perp (22 jours, 30 actions, borne conservatrice Q = 1 000)** : le taux d'exécution passif n'est que de **4 à 13 %** (délai 6 à 106 minutes) et la sélection adverse est très forte : markout à 10 minutes de **-24 à -32 bps** après un fill maker de S2 (-44 à -74 bps à 1 heure), alors que S2 ne tolère que **A\* = +5.35 et +6.56 bps** de sélection adverse
  (effet par transaction moins coût maker) : un facteur 5 trop élevé. Net par signal émis (non-exécutés à zéro) de S2, conservatrice : T = 30 minutes avec repli taker **+2.15 bps** [-8.8, +16.2] (S2a) et +0.95 [-10.6, +17.5] (S2b), **tous les intervalles Bonferroni contiennent zéro** ; T = 2 heures : **-8.4 [-15.3, -1.3] et -11.1 [-18.5, -3.7]** (négatif significatif). La borne optimiste est positive à 30 minutes (+5.5 bps) : **non concluant**.
  Taux de fill minimal pour 1 bps par signal : **impossible** (la sélection adverse observée dépasse la tolérée).
- S1 sur 22 jours de perp : S1b est positif en exécutable (+10.4 bps par signal, conservatrice, intervalle à 95 % [1.2, 21.5], Bonferroni [-3.2, ...]) mais contredit les 25 ans de la partie A (-8.4 bps, z = -3.5) : bruit d'un échantillon de 22 jours (erreur-type de 10 à 35 bps par signal), pas un signal ; S1a négatif ; S1c [-17, +85] non concluant.
- **Levier** (politique c, 2 h, descriptif) : S2a : 1x equity 0.982, 5x equity 0.915 avec drawdown de 9.2 %, aucune liquidation (le levier amplifie la perte) ; S1c : deux liquidations à 5x (drawdown 18 %).
- **Limites** : biais de survie, historique perp court (22 jours de cotation, la puissance d'un net de quelques bps est nulle : erreur-type de 10 à 35 bps), spread hors séance non mesuré (jamais d'ordre hors séance), proxy du meilleur bid / ask par les trades, file d'attente modélisée, entrée de la longue histoire approchée par l'ouverture et la clôture officielles.

## Pré-enregistrement : piste A, carry de funding avec couverture, écrit AVANT tout résultat

Écrit le 2026-10-08 (date réelle vérifiée avec `date`), après l'inventaire des données (couverture seulement) et avant tout calcul de P&L, de base ou de carry. Cadre : aucun ordre réel, `LiveExchange` reste un stub, aucun signal retourné, pas de market making.
Famille 11. **M : 9 aujourd'hui ; la lecture du holdout (après le 2026-09-28) par cette piste, si les critères passent sur la découverte, est une évaluation de test de plus : M = 10.**

**Hypothèse H_A** : hors crypto, le funding est surtout une composante d'intérêt (0.0625 bps par heure, 5.475 % par an) payée par les longs aux shorts. Un short perp couvert par une position longue sur le sous-jacent encaisse ce funding sans exposition directionnelle. H_A : le rendement net annualisé de ce carry,
après coût d'opportunité du capital (taux sans risque), frais d'entrée et de sortie des deux jambes, spread, slippage et base, est strictement positif au-delà d'une prime X fixée ici (**X = 1.0 % par an**) avec un intervalle de confiance à 95 % qui exclut zéro.

### Univers et couverture (fixés avant résultat)

- **Instruments** : tous les instruments non crypto de Polymarket avec au moins 40 jours de funding avant le gel du 2026-09-28 ET une jambe de couverture détenable avec des données : **27 actions** (SPCX, MU, SKHY, AAPL, MSFT, GOOG (GOOGL), AMZN, NVDA, META, TSLA, AMD, INTC, AVGO, QCOM, ARM, TSM, ASML, SNDK, HOOD, MSTR, CRCL, COIN, RKLB, LITE, NBIS, ORCL, PLTR ; couverture = l'action elle-même, prix ajustés Tiingo) et **5 indices et matières premières par ETF** :
  SP500 par SPY, NAS100 par QQQ, GOLD par GLD, SILVER par SLV, WTIOIL par USO (Tiingo, plan gratuit). **Exclus et comptés** : STRC (actions de préférence), BABA et ZM (38 jours seulement), DRAM, EWY, NCLD, SOXL (sous-jacent non établi), BRENTOIL (pas de funding), SKHYNIX, CXMT, SAMSUNG, UNITREE (absents chez Tiingo), DELL, CRWV, CBRS, MRVL (pas de funding),
  toute la crypto (hors périmètre de la piste : pas de couverture hors plateforme). **Total : 32 instruments.** Fait notable : USO est un panier de contrats à terme avec coût de roulement (le perp WTI référence un contrat à terme) et la base ETF / indice contient l'erreur de suivi ; le WTI est conservé, étiqueté, et rapporté à part.
- **Données** : funding horaire réel (`/v1/info/funding`, fichiers `data/<SYM>_funding.csv`, taux publié incluant déjà le facteur 0.5 hors crypto, les longs paient quand il est positif d'après la doc ; **non vérifié par un paiement réel**, aucun compte), prix du perp au dernier prix de la barre de 1 minute qui précède la clôture des actions américaines (19:59 UTC en heure d'été), plus bas et plus haut de 1 minute entre deux clôtures,
  sous-jacent Tiingo (rendement total ajusté des splits ET dividendes) aux mêmes dates, taux sans risque = bon du Trésor à 3 mois (FRED DTB3).
- **Fenêtre** : découverte avant le 2026-09-28 (41 à 144 jours selon l'instrument) ; holdout du 2026-09-28 à la fin des données, lu une seule fois et seulement si les critères passent sur la découverte.

### Comptabilité du carry (par unité de notionnel N de la jambe longue)

- **Jambe longue** : N en sous-jacent (rendement total). **Jambe courte** : N en perp short avec marge M = N / L (L levier du perp, variable : 1, 2, 5, 10, plafonné au levier max de l'instrument ; la jambe longue est au comptant, 1x). Le « vol-ciblé » ne s'applique pas : la position est neutre au marché, L est le levier de marge.
- **P&L journalier de clôture à clôture** = `base + funding` avec `base = rendement total du sous-jacent - rendement du prix du perp` (les dividendes du sous-jacent, que le perp ne verse pas, y apparaissent automatiquement ; si le perp ne baisse pas à la date ex-dividende, la base le montre) et `funding = somme des taux horaires publiés entre deux clôtures` reçue par le short quand elle est positive, payée sinon (week-ends et jours fériés compris, le funding court 24 h sur 24).
- **Coûts** : aller-retour perp = 2 x 4 bps de frais taker + 2 x 2 bps de slippage + spread (relevé de carnet de chaque instrument, 3.5 bps par défaut) ; aller-retour de la couverture = **2 x h avec h = 3 bps par côté (hypothèse explicite)**, sensibilité h = 0, 1, 5 ; amortis sur la durée de détention H (7, 30, 90 jours).
- **Coût d'opportunité du capital** : `rf x (N + M)` par an, c'est-à-dire que le carry est comparé à du cash qui rapporterait rf sur le même capital. **Marge rémunérée ? Non documenté, deux cas rapportés** : (i) marge non rémunérée (cas de base), (ii) marge rémunérée au taux sans risque.
- **Excès net annualisé** (par unité de N) = `365 x moyenne calendaire de (base + funding) - coûts aller-retour x 365 / H - rf x (1 + 1/L)` (cas i). Estimé sur la série journalière (dates non chevauchantes) ; intervalle de confiance par bootstrap par blocs de semaines.
- **Risque de liquidation du short** : sans transfert de marge entre plateformes (délai non quantifiable en lecture seule), le short est liquidé si le plus haut du perp dépasse le prix d'entrée de `1/L - mmr` avec `mmr = 0.5 / levier max` ; on rapporte, pour chaque L et chaque H, la part des fenêtres (départ chaque jour) où cela arrive. Le coût de rééquilibrage de la marge n'est pas modélisé.

### Calcul de puissance (annoncé d'avance) et critères de succès

- **Puissance** : le funding reçu est mesuré avec précision (série quasi déterministe) ; la base est un niveau borné, pas une marche aléatoire, mais sa moyenne sur 40 à 144 jours n'est pas estimable avec précision : l'intervalle du bootstrap quantifie cela. **Si la largeur de l'intervalle à 95 % de l'excès net poolé dépasse 2 X = 2 % par an, la piste est déclarée inconclusive**, jamais négative.
- **Cas de référence (primaire)** : détention H = 30 jours, levier du perp L = 2, couverture h = 3 bps par côté, marge non rémunérée, instruments poolés à poids égaux. **Critères de succès, tous requis** : (1) excès net poolé > X = 1.0 % par an ; (2) borne basse de l'intervalle à 95 % par blocs > 0 ; (3) positif dans les deux moitiés du temps ; (4) au moins 60 % des 32 instruments (20) ont un excès net positif ; (5) le funding est positif au moins 70 % des heures dans les deux moitiés pour au moins 60 % des instruments
  (stabilité) ; (6) part des fenêtres de 30 jours liquidées sans transfert de marge, à L = 2, <= 5 % ; (7) la base ne coûte pas plus de 3 % de N sur une fenêtre de 30 jours en moyenne poolée (pire fenêtre poolée). **Règle d'arrêt** : sinon conclusion négative (ou inconclusive si le critère de largeur est violé), aucun code d'exécution.
- **Sensibilités rapportées (non décisionnelles)** : L = 1, 5, 10 ; H = 7, 90 ; h = 0, 1, 5 ; marge rémunérée ; par catégorie (actions, indices et ETF, WTI) ; hors les cinq instruments les plus volatils. Comparaison à la simple détention du sous-jacent : rendement et volatilité annualisés sur la même période.
- **Pièges à vérifier** : signe et échelle du funding (0.5 hors crypto, déjà inclus), comportement hors séance et week-end de la base (écart-type de la base du vendredi au lundi contre les jours de semaine), date ex-dividende, biais de survie des actions Tiingo (univers actuel de Polymarket), un seul régime (haussier) dans les données.
- **Livrables** : `tools/carry_study.py`, `tests/test_carry.py` (dans ctest), `docs/CARRY_REPORT.md`, `results/carry_*.csv` (agrégats seulement, aucune donnée brute Tiingo).

## Résultats : piste A, carry de funding avec couverture (2026-10-08)

Rapport : `docs/CARRY_REPORT.md` ; fichiers `results/carry_instruments.csv`, `carry_pooled.csv` (96 réglages), `carry_summary.txt`. **Verdict pré-enregistré : INCONCLUSIF (intervalle de 13,1 % de large pour une limite de 2 %), avec des estimations ponctuelles négatives et une arithmétique défavorable. Aucun code d'exécution ; le holdout n'est pas lu, M reste à 9.**
32 instruments (27 actions, 5 indices et matières premières couverts par ETF), 41 à 144 jours. Funding reçu par le short : actions +5,38 % par an, indices et matières +2,7 %, WTI -21 %. Cas de référence (30 jours, L = 2, couverture 3 bps, marge non rémunérée) : excès net poolé **-3,94 % par an, IC95 [-11,2 ; +1,9]**, 12 instruments sur 32 positifs.
**Arithmétique** : carry brut poolé 4,34 % par an contre un taux sans risque de 3,79 % : le coût d'opportunité `rf x (1 + 1/L)` l'emporte à tous les leviers (L = 10 : +0,17 % avant frais, 451 jours pour amortir l'aller-retour). Risque : 5,6 % des fenêtres de 30 jours liquidées à L = 2 sans transfert de marge (MSTR 71 %, CRCL 43 %). Anomalie de démarrage SPCX (perp figé à 300 les 17 et 18 juin) : sensibilité post hoc -1,71 % [-4,9 ; +3,9].
Écart déclaré : stabilité du funding mesurée sur le signe de la somme journalière, pas heure par heure.

## Pré-enregistrement : piste B, horizons longs (sélection maintenant, test plus tard), écrit AVANT tout résultat

Écrit le 2026-10-08 (date réelle), après `tools/long_horizon.py --mode power` (variance seulement, aucune relation) et avant `--mode discover`. Détail : `docs/LONG_HORIZON_PREREG.md`. Aucun ordre réel, `LiveExchange` reste un stub, aucun signal retourné après coup.

- **Hypothèse H_B** : parmi une grille courte et fermée, au moins un signal a une espérance nette positive à une détention d'au moins 1 jour. **Séparation sélection / validation** : le signal est estimé sur l'historique long des sous-jacents (Tiingo ajusté, 34 actions et 5 ETF : SPY, QQQ, GLD, SLV, USO) ; le perp (4 mois) ne sert qu'à valider l'exécution (base, funding, coûts).
- **Grille (12 cellules plus 2 reprises de P1)** : signaux **TSM** (momentum de séries temporelles : position = signe du rendement des 60 derniers jours, long ou short, par instrument, 39 instruments), **XSM** (momentum en coupe transversale : quintiles du rendement de 120 jours en sautant le dernier mois, 34 actions), **XSR** (inversion en coupe transversale du rendement de 20 jours), fois les détentions
  **1, 5, 20 et 60 jours de cotation** (entrée à l'ouverture J, sortie à la clôture J+h-1, cohérence signal / exécution de P1) = 12 cellules. La prime de nuit est **reprise de P1** (S2a et S2b : partie A passée, partie B non concluante) et lue avec le holdout, non ré-estimée. **1 h et 4 h ne sont pas dans la grille** : aucune donnée intrajournalière longue légale pour les sélectionner (les 4 mois de perp ne suffisent pas).
- **Coûts** : taker 4 bps x2 + slippage 2 bps x2 + spread 3.5 = 15.5 bps par aller-retour d'une jambe (31 bps par période pour les deux jambes du long/short en coupe transversale) ; **funding réel sur toute la durée** : intérêt payé par les longs, reçu par les shorts (0.0625 bps par heure ; un long de 20 jours paie 30 bps, de 60 jours 90 bps), signe selon la position. **Levier** (1x, 2x, 5x, 10x, volatilité ciblée) rapporté avec drawdown et liquidations à la lecture du test.
- **Puissance (règle de 3 fois le coût, variance seulement, `results/long_horizon_power.json`)** : **6 cellules retenues sur 12** (TSM, XSM, XSR à 1 et 5 jours) ; **les 6 cellules à 20 et 60 jours sont sous-puissantes** (MDE de 146 à 1 188 bps contre des limites de 72 à 123 bps pour 89 à 271 périodes non chevauchantes avant 2019) : **les détentions de 20 et 60 jours ne sont pas testables avec cet univers et cette profondeur**, déclarées inconclusives, pas négatives.
- **Découverte (avant 2019, train <= 2012, validation 2013-2018)** : net = effet exécutable moins coût ; test unilatéral « net > 0 », erreur-type jackknife par blocs d'un mois, 3 plis chronologiques, BH-FDR à 5 % sur les 6 cellules, p étalonnées par placebos du brut (signes aléatoires par blocs de 20 et 60 périodes pour TSM ; signal décalé et mélangé pour XSM et XSR). **Finaliste** = BH q <= 5 % ET net > 0 dans les 3 plis ET rapport effet / coût > 1 ; **au plus un par signal** (le plus grand rapport).
- **Holdout vierge et lecture unique** : le test se fait à partir du **2026-12-15** ET après au moins **40 jours de cotation de perp** postérieurs au gel du 2026-09-28 (`tools/long_horizon.py --mode test` refuse sinon, et refuse une seconde lecture : verrou). Il lit (T1) le test Tiingo **2019-01-01 -> 2026-09-27** des finalistes (net par période > 0, correction de Bonferroni avec M = 9 + nombre de finalistes, positif dans les deux moitiés, bat 75 % des tirages aléatoires,
  longs et shorts non négatifs) et (T2) la validation de l'exécution sur le perp après le gel (funding réalisé de même signe et dans ±30 % de l'hypothèse, base moyenne par jour inférieure à 0.5 fois l'effet net par jour, jamais de liquidation à L = 2). **Les fenêtres de test des familles précédentes ne sont pas rouvertes** (le test Tiingo 2019-2026 n'a été lu par aucune phase). **Règle d'arrêt** : sinon conclusion négative, aucun code d'exécution.
- **M** : 9 aujourd'hui (aucun test hors échantillon consommé par A, B, C) ; B ajoute au plus 3 évaluations (un finaliste par signal).
- **Enregistreur** : `tools/recorder.py` (Polymarket seul) n'a plus tourné depuis le 2026-10-05 ; le holdout du perp provient des klines, trades et funding téléchargés à la date du test ; l'enregistreur inter-plateformes (piste C) tourne depuis le 2026-10-08 et son contrôle de santé écrit le nombre de jours continus.

## Pré-enregistrement : piste C, écart entre plateformes (phase 1 : collecte seulement), écrit AVANT toute lecture

Écrit le 2026-10-08. **Aucune analyse, aucune stratégie en phase 1.** Outil : `tools/recorder_xvenue.py`, tests `tests/test_recorder_xvenue.py` (réseau simulé). Lecture seule, aucune clé, aucun ordre.
- **Plateformes et appariement** : Polymarket Perps et Hyperliquid (dex principal et dex HIP-3 `xyz` de trade.xyz). Appariement par le NOM DE L'ACTIF (`base_asset` contre le nom Hyperliquid), jamais supposé : 18 paires dont 16 appariées par nom (BTC, ETH, SOL, XRP, HYPE ; SP500, GOLD, SILVER, BRENTOIL ; AAPL, MSFT, NVDA, TSLA, AMZN, META, GOOGL) et **2 d'équivalence non établie, enregistrées avec `verified = false`** (NAS100 contre XYZ100, WTIOIL contre CL). Non appariés par nom : SKHYNIX, SAMSUNG.
- **Données** : toutes les 7 secondes par paire, les deux carnets demandés en parallèle, 5 niveaux par côté, horodatage local à l'envoi et à la réception, horodatage serveur de chaque plateforme (Polymarket : `timestamp` ; Hyperliquid : `time`) ; toutes les minutes : mark, index ou oracle, funding, intérêt ouvert, prime (Hyperliquid `metaAndAssetCtxs`, Polymarket `/v1/info/tickers`) ; toutes les heures : décalage d'horloge et latence (5 mesures).
  **Limite de principe : un sondage REST toutes les 7 secondes ne mesure pas des écarts qui durent moins d'environ 0.5 s (latence mesurée : Hyperliquid 300 ms, Polymarket 80 ms depuis cette machine, décalage d'horloge de l'ordre de 0.2 à 0.6 s entre l'horodatage serveur du carnet et l'horloge locale) ; les écarts sub-seconde ne sont pas mesurables.**
- **Limites de débit lues dans la doc (2026-10-08)** : Hyperliquid, par IP, poids agrégé de 1 200 par minute, `l2Book` 2, `metaAndAssetCtxs` 20 ; débit prévu 349 par minute (29 %). Polymarket : non documenté ; 2,6 requêtes par seconde (des 429 sont apparus vers 4 requêtes par seconde) ; le programme refuse de démarrer au-delà de 900 de poids ou de 3 requêtes par seconde, attend en cas de 429.
- **Critère de passage à la phase 2 (fixé maintenant)** : **au moins 14 jours consécutifs** avec, chaque jour, couverture médiane >= 90 % des échantillons attendus et plus long trou <= 5 minutes pour au moins 17 paires sur 18 ; instabilité de l'horloge LOCALE (écart entre les valeurs extrêmes de son décalage mesuré par NTP, voir l'amendement ci-dessous) <= 300 ms ; taux d'erreurs HTTP <= 1 %. Contrôle de santé : `python tools/recorder_xvenue.py --health`. **Les 3 derniers jours de collecte sont gardés vierges** (holdout de la phase 2).
- **AMENDEMENT du 2026-10-09 (décidé avant toute lecture d'un écart de prix, sur la seule foi du contrôle de santé) : critère d'horloge.** La première version mesurait « horodatage serveur du carnet moins milieu de la requête locale », qui mélange le décalage de l'horloge et le retard variable de l'instantané du carnet : variation observée de 839 ms pour un critère de 300 ms, sans rapport avec l'horloge. Remplacement : le décalage de l'horloge locale est mesuré par **SNTP** (UDP 123, `time.cloudflare.com` puis `pool.ntp.org`, médiane de 3 mesures par heure) ;
  le critère de variation <= 300 ms porte sur ce décalage NTP (mesures préliminaires le 2026-10-09 : de -5 à -12 ms). L'âge de l'instantané de chaque plateforme (horodatage serveur moins instant d'envoi) est rapporté séparément, sans critère : il sert de marge d'incertitude sur les écarts de la phase 2. Les enregistrements antérieurs au redémarrage n'ont pas de mesure NTP : le critère se calcule sur les mesures NTP disponibles (au moins 24 à la lecture).
- **Phase 2 (écrite d'avance, exécutée après les 14 jours)** : (1) distribution de l'écart de mid `(mid Hyperliquid - mid Polymarket) / mid` par instrument et par heure ; (2) écart EXÉCUTABLE pour un notionnel V = 1 000 et 5 000 : prix moyen d'exécution à la vente sur un lieu moins prix moyen à l'achat sur l'autre (profondeur des 5 niveaux), moins frais taker des deux côtés (**barème d'Hyperliquid, y compris celui du dex HIP-3 `xyz`, à lire dans la doc au démarrage de la phase 2, non supposé** ; Polymarket 4 bps) et moins 2 bps de marge de slippage ;
  (3) persistance : part des événements exécutables encore exécutables 14 secondes plus tard (deux échantillons) ; (4) risque d'une jambe : perte moyenne si seul le premier côté est exécuté, estimée par le mouvement du mid de l'autre lieu sur 1 à 7 secondes ; (5) contraintes de capital non quantifiables en lecture seule (marge sur deux plateformes, retraits, délais) : dites, non estimées.
  **Critères de succès, tous requis** : part des échantillons à écart exécutable net >= 2 bps (V = 1 000) supérieure à 5 % pour au moins 5 paires vérifiées ; persistance >= 50 % à 14 secondes ; espérance nette par événement après le modèle de risque d'une jambe > 0 avec un intervalle de confiance à 95 % par blocs de jours qui exclut zéro ; positif sur les 3 derniers jours vierges ; Bonferroni sur le nombre de paires testées. **Règle d'arrêt inchangée.**
- **M** : 9 ; la phase 2, si elle atteint la lecture du holdout (3 derniers jours), ajoute 1.

## Résultats : piste B, découverte sur l'historique long (2026-10-08), et état de la piste C

**Piste B : aucun finaliste.** Découverte avant 2019 sur 39 instruments (34 actions et 5 ETF), exécutable (entrée à l'ouverture J, sortie à la clôture J+h-1), net du coût taker et du funding de la durée, 6 cellules testées (20 et 60 jours sous-puissants : inconclusifs) :
TSM 1 jour : brut +3,85 bps, coût 15,6, net -11,7 (z = -7,8) ; **TSM 5 jours : brut +26,0 bps, coût 17,4, net +8,65 (se 9,8, z = 0,88), plis +35 / +5 / -14 : non significatif et instable** ; XSM 1 et 5 jours : nets -33,8 et -24,6 ; XSR (inversion du rendement de 20 jours) 1 et 5 jours : nets -49,9 et -63,0 (l'inversion se joue dans l'écart de nuit, comme S1 de P1).
BH-FDR : rien ne passe. **Le test 2019-2026 et le holdout du perp n'ont pas été lus** ; `tools/long_horizon.py --mode test` conclurait « aucun finaliste » à la date. Fichiers : `results/long_horizon_discovery.csv`, `long_horizon_power.json`, `long_horizon_finalists.json` (vide). M reste à 9.

**Piste C : phase 1 (collecte) en cours depuis le 2026-10-08 ~17:05 UTC**, `tools/recorder_xvenue.py` (18 paires, un échantillon toutes les 7 secondes par paire, débit prévu 349 de poids Hyperliquid par minute et 2,6 requêtes par seconde pour Polymarket), sortie `data/xvenue/` (ignoré par git). Aucune analyse. Passage à la phase 2 au plus tôt le 2026-10-23 (les 14 jours complets commencent le 2026-10-09) si le contrôle de santé (`python tools/recorder_xvenue.py --health`) montre 14 jours consécutifs.
**Le processus doit tourner sur une machine toujours allumée** (il s'arrête avec la session ou l'extinction du poste ; reprise automatique impossible sans planificateur) ; les trous sont comptés dans le contrôle de santé.

## Pré-enregistrement : piste D, différence de funding entre plateformes (Polymarket et Hyperliquid), écrit AVANT tout résultat

Écrit le 2026-10-09 (date réelle). Divulgation : en testant l'API Hyperliquid j'ai vu les 500 premières heures de funding de trois actifs (BTC +3,7 % par an, xyz:AAPL +0,5 %, xyz:GOLD +8,9 %), aucun P&L ni aucune différence entre plateformes. Famille 12. Aucun ordre réel, `LiveExchange` reste un stub, aucun signal retourné après coup.

**Hypothèse H_D** : une position neutre au marché formée de deux perps du MÊME actif (short sur la plateforme où le funding moyen récent est le plus élevé, long sur l'autre) rapporte un excès net strictement positif sur le cash, après frais, spread, base entre plateformes et coût d'opportunité des deux marges. Aucune jambe sur le sous-jacent : le capital immobilisé est celui des deux marges (N/L1 + N/L2),
bien inférieur aux 2N de la piste A.

- **Univers (fixé par règle, comptes seulement)** : actifs de Polymarket appariés par NOM d'actif (`base_asset`) à Hyperliquid (dex principal ou dex HIP-3 `xyz`), avec au moins 40 jours de funding sur Polymarket avant le gel du 2026-09-28 : **38 actifs** (BTC, ETH, SOL, XRP, HYPE ; SP500, GOLD, SILVER, BRENTOIL ; 29 actions et ETF dont DRAM et STRC). **Exclus** : 44 appariements par nom avec moins de 40 jours de funding sur Polymarket (38 cryptos moins liquides, BABA, ZM, DELL, CRWV, CBRS, MRVL, CXMT, EWY, NCLD, SOXL, UNITREE) ;
  NAS100 et WTIOIL (équivalence avec XYZ100 et CL non établie). **L'équivalence des définitions de contrat n'est vérifiée que par le nom** (DRAM, STRC, SKHY, SPCX en particulier peuvent différer d'une plateforme à l'autre) : la base entre plateformes mesure aussi cet écart de définition ; sensibilité sans ces quatre actifs.
- **Données** : funding horaire Polymarket (`data/<SYM>_funding.csv`) et Hyperliquid (`fundingHistory`, `tools/fetch_hl.py`, `data/hl/`) ; prix : clôtures horaires Polymarket (klines 1 minute) et bougies 1 heure Hyperliquid (`candleSnapshot`, au plus 5 000 bougies) ; plus hauts et plus bas horaires pour les liquidations ; taux sans risque FRED DTB3.
- **Règle de position** : chaque lundi 00:00 UTC, écart moyen des 14 jours PRÉCÉDENTS `(funding Hyperliquid - funding Polymarket)` annualisé ; si sa valeur absolue dépasse **theta = 2 % par an**, position (short là où le funding est le plus haut, long ailleurs) pendant la semaine suivante, sinon cash ; changement de position = sortie puis entrée.
  Le funding est payé à chaque heure pleine par la jambe longue si le taux est positif et reçu par la jambe courte. Warm-up de 14 jours.
- **P&L horaire par unité de notionnel N par jambe** : funding net + base (rendement de la jambe longue moins rendement de la jambe courte, prix horaires) - coûts d'entrée et de sortie - coût d'opportunité `rf x (1/L1 + 1/L2)` tant qu'une position existe. Excès annualisé sur N, temps à plat compris (le cash vaut 0 par construction).
- **Coûts (explicites)** : Polymarket, un sens = frais taker 4 bps + slippage 2 bps + demi-spread (relevé de carnet de l'instrument, 3,5 bps par défaut) ; Hyperliquid, un sens = frais taker **4,5 bps (barème de base, palier 0, doc lue le 2026-10-08)** + slippage 2 bps + demi-spread (relevé de l'enregistreur inter-plateformes, 3,5 bps par défaut). Pour les marchés HIP-3, le barème dépend du « mode croissance » (frais de protocole réduits de 90 %) et d'une part de frais du déployeur de 0 à 300 % : **non établi pour `xyz`, sensibilité : frais Hyperliquid doublés**.
- **Levier** : L1 = L2 = 3 en référence (distance de liquidation `1/L - mmr` par plateforme) ; sensibilités 1, 2, 5, 10. Marge non rémunérée (cas de base) et rémunérée au taux sans risque. Les transferts de marge entre plateformes ne sont pas modélisés (délais, frais de retrait et de pont non quantifiables en lecture seule).
- **Estimateur** : moyenne sur les instruments, poids égaux ; intervalle de confiance à 95 % par bootstrap de blocs de semaines tirés pour tous les instruments à la fois (2 000 tirages).
- **Puissance et critères (tous requis, sinon inconclusif ou négatif)** : si la largeur de l'intervalle à 95 % dépasse 2 X = 2 % par an (**X = 1,0 % par an**), la piste est inconclusive. Succès : (1) excès net poolé > X ; (2) borne basse de l'intervalle > 0 ; (3) positif dans les deux moitiés du temps ; (4) au moins 60 % des instruments positifs ; (5) le signe de la décision est celui de l'écart réalisé la semaine détenue dans au moins 60 % des semaines en position ;
  (6) part des épisodes liquidés à L = 3 inférieure ou égale à 5 % ; (7) pire fenêtre de 30 jours de la base moyenne poolée supérieure ou égale à -3 % de N. Holdout après le 2026-09-28 (y compris l'enregistreur inter-plateformes), lu une seule fois si les critères passent : M = 10.
- **Sensibilités non décisionnelles** : theta 0 % et 5 % ; frais Hyperliquid doublés ; crypto contre non crypto ; sans DRAM, STRC, SKHY, SPCX ; levier 1 à 10 ; marge rémunérée.
- **Risques non modélisés, déclarés** : capital sur deux plateformes et délais de transfert, risque de contrepartie (Polymarket, Hyperliquid, déployeur HIP-3), modification des paramètres de funding par un déployeur HIP-3 (multiplicateur, intérêt), restrictions d'accès selon le pays, fiscalité.

## Résultats : piste D, différence de funding entre plateformes (2026-10-09)

Rapport : `docs/FUNDING_XVENUE_REPORT.md` ; fichiers `results/funding_xvenue_*.csv|txt`. **Verdict pré-enregistré : INCONCLUSIF (intervalle de 5,8 % de large pour une limite de 2 %).** 38 actifs appariés par nom ; référence (L = 3, theta 2 %) : excès net poolé **+1,31 % par an**, IC95 [-1,03 ; +4,74], moitiés +1,39 % puis -0,33 %, **16 instruments positifs sur 38**, décision confirmée dans 72 % des semaines,
épisodes liquidés à L = 3 : 7,7 %. Critères (1), (5), (7) tenus ; (2), (3), (4), (6) échoués. **Le résultat repose sur quelques actifs** (SILVER +33,9 %, BRENTOIL, COIN, STRC) : médiane 0,0 %, sans SILVER +0,43 %, sans les trois meilleurs -0,34 % (post hoc, descriptif). Crypto seule -2,4 %. Aucun code d'exécution, holdout non lu, M reste à 9.
**Lecture du holdout pré-enregistrée (règle gelée : 14 jours, theta 2 %, L = 3, frais inchangés) le 2026-12-15 au plus tôt, après au moins 60 jours au-delà du gel, une seule fois, mêmes critères ; M passerait à 10.** Déclaré : cette date est fixée après avoir vu les résultats de découverte, sans modifier ni la règle ni les critères.

## Pré-enregistrement : piste E, prime de variance (VIX contre volatilité réalisée), écrit AVANT tout résultat

Écrit le 2026-10-09. Famille 13. Aucun ordre réel, `LiveExchange` reste un stub, aucun signal retourné. **Hors Polymarket** : les options d'indice ne se négocient pas sur Polymarket Perps ; l'étude mesure si la source de rendement existe, avec des proxys explicites, sans ordres. Divulgation : aucune statistique VIX / S&P n'a été calculée dans ce projet avant cette ligne.

**Hypothèse H_E** : l'indice VIX (volatilité implicite à 30 jours du S&P 500) dépasse en moyenne la volatilité réalisée qui suit ; vendre cette volatilité chaque mois rapporte une prime de risque positive nette de coûts, avec des pertes rares et fortes que le drawdown doit juger.

- **Données (déjà dans le dépôt)** : VIX de FRED (`data/under/FRED_VIXCLS.csv`, depuis 1990), cours du S&P 500 par l'ETF SPY (Tiingo, cours bruts non ajustés pour le règlement des options, depuis 1993-01-29), taux sans risque DTB3. **Découverte : avant 2019 (train <= 2012, validation 2013-2018). Test 2019 -> 2026-10 : lu une seule fois, seulement si la découverte passe les critères (1) à (5) ci-dessous.**
- **Échantillonnage** : mois non chevauchants de 21 jours de cotation (T = 21 / 252 an), entrée à la clôture t avec le VIX de la clôture t, règlement à la clôture t+21 (règlement en espèces, pas de couverture delta). Pas de chaînes d'options (non disponibles gratuitement) : **prix par Black-Scholes avec une volatilité implicite à la monnaie = VIX - 1,5 point de volatilité** (le VIX contient la pente des puts hors de la monnaie et dépasse la volatilité à la monnaie ; hypothèse explicite, sensibilités 0 et 3 points), taux sans risque, sans dividende ; demi-spread de 0,5 point de volatilité payé à la vente (sensibilités 0, 1 et 2 points).
- **Mesure descriptive (hors décision)** : prime de variance brute `VIX - volatilité réalisée à 21 jours` en points de volatilité, moyenne, médiane, asymétrie, pire mois, part des mois où la volatilité réalisée dépasse le VIX.
- **Stratégies (2 cellules soumises à la décision)** : **E1 vente d'un put à la monnaie sur le SPY, garantie en espèces** (type indice PUT du CBOE) ; **E2 vente d'un straddle à la monnaie** (call et put), non couvert. Pour un levier `L` (notionnel de l'option en fraction du capital) : rendement excédentaire du mois = `L x (prime - perte à l'échéance) / S0` ; le capital non engagé rapporte le taux sans risque ; mesure : rendement total du capital `1 + rf x T + L x P&L / S0`.
  **Cas de référence : E1 avec L = 1, E2 avec L = 0,5.** Levier variable : 0,5, 1, 2 avec drawdown maximal, pire mois, probabilité de ruine (capital <= 0), CVaR à 5 %.
- **Statistiques** : moyenne mensuelle du rendement excédentaire, erreur-type par jackknife sur blocs de 3 mois, Sharpe annualisé, comparaison avec le SPY (Sharpe et drawdown, descriptif). Correction : Bonferroni sur les 2 cellules de référence pour la lecture du test.
- **Critères de succès sur la découverte, tous requis (pour E1 de référence, puis pour E2 séparément)** : (1) rendement excédentaire moyen > X = 0,15 % par mois (environ 1,8 % par an) ; (2) borne basse de l'intervalle à 95 % > 0 ; (3) positif dans le train ET dans la validation ; (4) drawdown maximal du capital <= 45 % et pire mois >= -20 % ; (5) Sharpe > 0,3 ; (6) toujours positif sans 2008-2010 (la prime n'est pas un seul épisode). **Si (1) à (5) tiennent : lecture unique du test 2019-2026** avec les mêmes critères, M passe à 10 (ou plus).
- **Règle d'arrêt** : sinon conclusion négative pour cette stratégie. **Même positif, aucun code d'exécution : la stratégie exige des options réelles sur un courtier, hors périmètre de ce dépôt.** Un résultat positif signifierait seulement que la prime existe et que la question suivante est l'exécution et le capital réel.
- **Limites annoncées** : proxys de prix (VIX moins 1,5 point, pas de pente, pas de dividende), pas de couverture delta, pas de chaînes d'options réelles ni de spreads réels, SPY comme proxy du S&P 500, un siècle de volatilité mais peu de crises (2008, 2020, 2022), biais de survie nul pour l'indice.

## Résultats : piste E, prime de variance (2026-10-09)

Rapport : `docs/VRP_REPORT.md` ; fichiers `results/vrp_summary.txt`, `vrp_test.txt` (lu une seule fois, verrou), `vrp_alpha.txt`. **Critères (1) à (5) tenus sur la découverte (310 mois) ET sur le test 2019-2026 (92 mois) pour E1 (put garanti) et E2 (straddle), en proxy Black-Scholes (VIX - 1,5 point, demi-spread 0,5 point). M passe à 10.**
E1 L = 1 : +0,56 % par mois (découverte, Sharpe 0,79, drawdown 30 %) puis +0,78 % (test, borne Bonferroni +0,145, Sharpe 0,98, pire mois -16,5 %) ; E2 L = 0,5 : +0,32 % puis +0,25 % (borne Bonferroni +0,001). Prime de variance brute : VIX moins volatilité réalisée de +3,6 à +3,8 points, positive dans 82 à 85 % des mois, asymétrie négative.
**Descriptif, non pré-enregistré : E1 a un bêta de 0,5 au SPY ; l'alpha vaut +0,32 % par mois (t = 4,8) sur la découverte mais +0,21 % (t = 1,4) sur le test (E2, neutre au marché : même alpha)** : la prime pure est de l'ordre de 2,5 à 3,9 % par an. Sensibilité : l'intervalle contient zéro avec VIX - 3 points et un demi-spread de 2 points. Hors Polymarket (options d'indice réelles requises) : aucun code d'exécution.

## Pré-enregistrement : piste F, calibration des marchés de prédiction Polymarket, écrit AVANT tout résultat

Écrit le 2026-10-09. Famille 14. Aucun ordre réel, aucun accès à un compte ; **autre domaine que les perps** : les contrats binaires Yes / No de Polymarket. **L'éligibilité à négocier ces marchés dépend du pays de l'utilisateur** (l'accès à polymarket.com est restreint dans certains pays, dont la France d'après l'incident ANJ rencontré au début du projet) : ce n'est pas du ressort de ce dépôt, aucun code de négociation n'est écrit, et rien ici ne contourne une restriction.
Divulgation : seuls des comptes de marchés et des champs de métadonnées ont été vus (11 546 marchés), aucun prix historique ni résolution.

**Hypothèse H_F** : le biais favori / outsider documenté pour les paris existe sur Polymarket : les contrats à faible prix (< 10 %) gagnent moins souvent que leur prix et les contrats à prix élevé (>= 90 %) gagnent plus souvent ; acheter le côté sous-évalué rapporte une espérance nette positive après spread et coût du capital.

- **Données (`tools/fetch_pm.py`, API publiques Gamma et CLOB)** : marchés fermés, binaires Yes / No, résolus à 1 ou 0, volume total >= 300 000 $, date de fin programmée connue, sans frais activés, dont la date de fin va du 2023-01-01 au 2026-09-30. **11 546 marchés retenus** ; exclus et comptés : 20 572 non binaires (issues nommées, sports), 5 011 avec frais activés, 28 non résolus, 12 ni 1 ni 0. Historique de prix du jeton Yes : 1 point par jour (`prices-history`).
  Le choix du volume total (>= 300 000 $) filtre sur une propriété de la vie du marché, indépendante de l'issue mais corrélée à son intérêt : biais déclaré. Univers dominé par les marchés récents (2025-2026).
- **Découpage chronologique (par date de fin)** : train jusqu'au 2025-06-30 (3 826 marchés, 1 585 événements), validation du 2025-07-01 au 2025-12-31 (3 659 marchés, 1 519 événements), **test du 2026-01-01 au 2026-09-30 (4 061 marchés, 1 469 événements), lu une seule fois, seulement si les critères passent sur la découverte (train + validation)**.
- **Prix et horizon** : pour chaque marché et chaque horizon `h` = 1, 7, 30 jours, instant `T0 = date de fin - h` ; prix = dernier point de l'historique antérieur à T0 et distant de moins de 2 jours ; le marché doit être démarré et ENCORE OUVERT à T0 (jamais d'information postérieure) ; sinon exclu pour cet horizon (compté).
- **Règles (6 cellules soumises à la décision)** : **LONGSHOT_SELL** = acheter « No » quand le prix de « Yes » est inférieur à 10 % ; **FAV_BUY** = acheter « Yes » quand son prix est supérieur ou égal à 90 % ; chacune à h = 1, 7, 30. Coût d'exécution : on paie le prix plus **1 cent** par part (spread supposé de 2 cents, moitié payée ; sensibilités 0,5, 2 et 3 cents) ; pas de frais (marchés à frais exclus) ; coût du capital : `rf x jours réels jusqu'à la résolution / 365`.
  Rendement par dollar investi = `gain / coût - 1` (gain = 1 si le côté acheté gagne, sinon 0), moins le coût du capital.
- **Descriptif (21 cellules, hors décision)** : table de calibration par horizon et par tranche de prix de Yes (0-5, 5-10, 10-20, 20-80, 80-90, 90-95, 95-100 %) : écart `fréquence réalisée - prix moyen`, intervalle de Wilson.
- **Erreur-type** : jackknife en supprimant un événement à la fois (les marchés d'un même événement sont corrélés ; les groupes à somme 1 sont comptés comme un seul événement).
- **Critères de succès (tous requis, pour chaque règle)** : (1) rendement net moyen par transaction > X = 1,0 % ; (2) borne basse de l'IC95 > 0 sur train + validation ET rendement moyen positif dans le train et dans la validation séparément ; (3) au moins 300 transactions dans chacun ; (4) Benjamini-Hochberg à 5 % sur les 6 cellules ; (5) bat 95 % de 1 000 tirages de l'**hypothèse nulle de calibration parfaite** (mêmes transactions, issues tirées selon Bernoulli(prix de Yes) ; remplace un tirage aléatoire de marchés, sans sens ici puisque le rendement dépend du prix : amendement écrit avant tout résultat) ; (6) positif après retrait des 5 événements les plus rentables ; (7) positif avec 2 cents de spread payés ; (8) au moins 20 transactions en moyenne par mois (capacité). **Test lu une fois si au moins une règle passe (1) à (8)** ; Bonferroni sur le nombre de règles qui passent ; M passerait à 11.
- **Règle d'arrêt** : sinon conclusion négative. Même positif, aucun code d'exécution. **Limites annoncées** : spread supposé (pas de carnet historique), taille de position non étudiée (profondeur inconnue), risque de contestation de résolution (UMA) non modélisé, marchés récents surreprésentés, corrélation entre marchés d'un même événement.

## Résultats : piste F, calibration des marchés de prédiction (2026-10-09)

Rapport : `docs/PM_CALIBRATION_REPORT.md` ; fichiers `results/pm_summary.txt`, `results/pm_calibration.csv`. **11 546 marchés binaires résolus (>= 300 000 $), 6 cellules de décision : LONGSHOT_SELL négatif aux trois horizons (-1,58 %, -1,36 %, -0,81 % par trade, train et validation tous deux négatifs), FAV_BUY non concluant (110 à 263 transactions, +1,2 % et +1,7 % non significatifs).** Le test 2026 (4 061 marchés) n'est pas lu, M reste à 10.
Les marchés sont bien calibrés (contrats à 0-5 % : 0,7 à 0,9 % de gains pour 0,8 à 1,1 % de prix moyen) ; le spread supposé de 1 cent dépasse l'écart de calibration. Observation post hoc, non exploitable telle quelle : à 1 jour, les contrats à 10-20 % gagnent 21,6 % du temps pour un prix de 14,6 % (n = 371, Wilson [17,7 ; 26,0]) ; à tester uniquement sur des marchés postérieurs au 2026-09-30 avec une règle écrite avant. L'éligibilité à négocier ces marchés dépend du pays et n'est pas traitée.

## Hypothèses restantes (non vérifiées)

- MMR plat 0.5 / levier max : confirmé par la doc ; l'ADL n'est pas modélisé ; le fill de liquidation au
  prix du tick est une hypothèse pessimiste.
- Frais de liquidation 0.5 % : valeur de `/v1/info/instruments` pour tous les instruments du panel.
- Testnet, canaux WS privés : non vérifiés.
- Sessions : règles de calendrier par catégorie inférées de la doc et du profil d'activité, pas d'un
  calendrier officiel ; jours fériés ignorés ; pas de gestion de `close_only` dans le panel.
- Spread et slippage simulés (2 bps + 2 bps par côté) : un seul relevé de 45 s en séance (voir plus haut),
  non calibré pour les heures creuses ; l'enregistreur est là pour ça.
- Chemin intra-bougie (4 ticks) approximatif ; Sharpe sur l'equity par bougie ou par heure.
- Funding : historique réel rejoué ; hors crypto il vaut presque toujours la composante d'intérêt fixe.
- Le test (2026-09-10 -> 2026-10-05) est consommé pour BTC, ETH, SOL (familles A et B) et vu une fois
  pour les 12 autres instruments (famille B). **Toute nouvelle hypothèse doit se valider sur du temps neuf**
  (données de l'enregistreur) ou être comptée dans M (nombre de tests de test), avec correction.
- Les actions sont très fines et ne couvrent que 77 jours ; les résultats par action sont bruités
  (6 à 31 trades en test).
- Contexte du bot Up/Down : ~51 % de win rate mais Sharpe négatif ; le rapport ventile le PnL par raison
  de sortie.

- Market making : conclusion négative sur 21 instruments à spread large, 9 jours de test, bornes de fill modélisées ;
  une requote plus rapide que la minute, ou de vrais fills (enregistreur + ordres réels, hors périmètre), pourraient
  changer le chiffre mais pas le signe des markouts mesurés (-7 bps dès 1 s).

## Prochaines étapes

Règle d'arrêt inchangée : pas de `perp_paper` tant qu'une stratégie n'a pas, sur du temps neuf, un Sharpe
positif net de coûts, robuste et significatif après correction des tests multiples.

1. **Laisser tourner `tools/recorder.py`** (de préférence sur une machine toujours allumée) : en quelques
   semaines, holdout vierge et mesures réelles de spread, profondeur, base mark/index, funding.
2. Hypothèses encore ouvertes, une à la fois, grille fixée avant de regarder : retour à la moyenne à
   l'horizon de quelques heures (signe négatif répété dans les diagnostics, faible) ; filtre de régime
   sur vol et volume ; déséquilibre du carnet (exige l'enregistreur) ; ordres maker (exige un modèle de
   fill) ; carry sur NAS100, WTI, BTC (exige le prix de la jambe de couverture).
3. Seulement si l'une d'elles passe tous les critères : `perp_paper` (ticks JSON lines sur stdin,
   événements `open` / `close` / `summary` sur stdout) puis `tools/paper_runner.py`. `LiveExchange` reste
   un stub ; aucun ordre réel.
