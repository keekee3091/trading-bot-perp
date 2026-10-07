# Prompt pour Claude Code : bot de trading perps Polymarket (moteur C++17)

Contexte : dossier `C:\Dev\trading-bot-perp`. Je veux adapter la logique de mon bot Polymarket Up/Down (dossier frère `C:\Dev\trading-bot`, lis `CLAUDE.md`, `bot/signal_engine.py`, `bot/position_manager.py`, la section Kelly de `bot/core.py`, `tools/backtest_full.py`) aux perps Polymarket. Le moteur doit être en C++17, avec Python en simple couche d'orchestration. Je travaille en parallèle sur `market_maker_bot` (C++17), garde un style cohérent (CMake, GoogleTest, pas de dépendance exotique). Le plugin ponytail reste actif.

## État actuel du dossier

Un premier jet Python partiel et NON TESTÉ existe peut-être dans `perp/` (models, signal_engine, risk, position_manager, exchange papier, core, backtest). Fais un `ls` d'abord. Sers-t'en comme spécification de référence, pas comme code à garder : on porte la logique en C++ puis on supprime ou archive la version Python. Ne fais aucune hypothèse sur ce qui a été écrit sans le relire.

## Faits vérifiés sur l'API (doc officielle, 2026-10-05)

- REST `https://api.perpetuals.polymarket.com`, WS `wss://ws.perpetuals.polymarket.com/v1/ws`.
- Données publiques : `GET /v1/info/instruments | tickers | book | klines | mark-history | trades | funding`. Klines : `[ts_ms, open, high, low, close, volume, trades]`, prix en chaînes.
- Les `instrument_id` ne sont pas stables entre doc et prod (id 1 = SP500-USD en prod). Toujours résoudre par `symbol` (ex. `BTC-USD`). 90 instruments, levier max variable (SP500 50x, GOLD 20x).
- Ordres : `POST /v1/trade/orders`, corps `{op:{type:"createOrders",args:[{iid,buy,p,qty,tif,po,ro,c}]},sig,salt,ts}`, tif `ioc|gtc|fok`, `po` post-only, `ro` reduce-only.
- Auth : EIP-712 `CreateProxy` (Polygon 137) puis `POST /v1/account/proxy` pour obtenir `proxy_secret`. SDK Python officiel `polymarket` (`AsyncSecureClient`).
- Frais tier 0 : taker 0.04 %, maker 0.0125 %. Funding horaire, formule `F_8h = scale*(mean_P + clamp(0.0001 - mean_P, ±0.0005))` / 8, cap 4 %/h, longs paient si perp > index. Liquidation : marge ratio = equity / maintenance margin < 1, frais de liquidation (0.5 % sur les instruments vus), ADL en dernier recours.
- Non vérifié : format exact de `/book`, risk tiers (maintenance margin réelle), testnet, canaux WS privés. Ne pas inventer : lire `docs.polymarket.com/perps/*` et le dire quand c'est une hypothèse.

## Ce qu'il faut construire

1. **Cœur C++17 (bibliothèque `perpcore`)**, déterministe, sans I/O :
   - `Instrument`, `Tick`, `Position` (marge isolée, prix de liquidation, funding cumulé), `ClosedTrade`.
   - `SignalEngine` : rendement sur lookback, normalisé par la vol, z-score, sigmoïde, fusion optionnelle d'un prix de référence (Binance) 40/60. Plus de "consensus Polymarket 15 %" : pas de prix binaire. Option de biais funding.
   - Edge : proba du signal vs `breakeven_prob = (sl + coût) / (sl + tp)` avec coût = frais x2 + slippage x2 + spread + funding estimé. Filtre `min_edge`.
   - `RiskManager` : Kelly glissant (fenêtre de trades, ratio gain/perte réel, bornes min/max), sizing par risque (notionnel = risque / distance SL, marge = notionnel / levier), levier plafonné pour que la liquidation reste à >= `liq_buffer_mult` x la distance SL, cooldowns, max pertes consécutives, verrous perte/gain journaliers, max entrées/heure, **exposition nette signée et brute multi-actifs** (paramètre dédié pour nettoyer la position nette).
   - `PositionManager` : SL/TP/trailing/time exit/garde-fou liquidation, tous en % du sous-jacent, SL dimensionné sur la vol, période de grâce `min_hold` avec SL d'urgence élargi. Contexte : mon bot Up/Down avait ~51 % de win rate mais un Sharpe négatif, les stop-loss étaient le principal poids. Le rapport doit donc **ventiler le PnL par raison de sortie**.
   - `PaperExchange` : spread, slippage, frais taker/maker, funding horaire, liquidation isolée, PnL net = collatéral récupéré moins (marge + frais d'entrée).
   - `PerpBot` : état IDLE/HOLDING piloté tick par tick, identique en backtest, paper et live (interface `IExchange`).
2. **Backtester C++** : rejoue des bougies 1m (CSV) en 4 ticks par bougie (o, extrême selon la couleur, extrême, c), Sharpe annualisé sur courbe d'equity, max drawdown, profit factor, ventilation par sortie, filtres déclenchés. Exécutable CLI `perp_backtest` + **balayage de paramètres multi-thread** (grille sur seuil, SL/TP, levier, lookback) avec sortie CSV. C'est la vraie raison du C++ ici.
3. **Couche Python fine** (`tools/`) : téléchargement des klines et résolution des instruments par symbole, paper trading temps réel par polling REST qui alimente le moteur (pybind11 ou sous-processus, tranche et justifie), journal SQLite. Pas d'exécution live pour l'instant : `LiveExchange` reste un stub documenté tant que backtest puis paper n'ont pas montré un Sharpe positif net de frais.
4. **Tests** GoogleTest : liquidation (prix exact long/short), PnL net avec frais et funding, Kelly, plafond de levier vs SL, exposition nette, `breakeven_prob`, déterminisme du backtest, et un test de **parité** : mêmes bougies, mêmes trades que la référence Python si elle est conservée.
5. **Données** : récupérer des vrais klines BTC-USD et ETH-USD (le synthétique ne sert qu'à valider la plomberie, il ne prouve aucun edge) et dire honnêtement si l'historique disponible est trop court pour conclure.

## Contraintes

- Aucun ordre réel, aucun secret dans le dépôt (`.env`, jamais dans le YAML).
- Remplace les tirets longs par des virgules dans les docs et commentaires.
- Avant d'écrire du code : propose-moi l'arborescence et les interfaces (`IExchange`, structure de config) en un message court, puis implémente par étapes (cœur + tests, puis backtester, puis sweep, puis couche Python), en lançant les tests à chaque étape.
- Termine par un `CLAUDE.md` du dossier (commandes de build, test, backtest, architecture).
