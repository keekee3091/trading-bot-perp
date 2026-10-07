# Graph Report - trading-bot-perp  (2026-10-07)

## Corpus Check
- 140 files · ~89,846 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 124 file(s) not represented in the graph (top: .csv 117, .jsonl 4, .example 1)

## Summary
- 1614 nodes · 3304 edges · 88 communities (78 shown, 10 thin omitted)
- Extraction: 91% EXTRACTED · 9% INFERRED · 0% AMBIGUOUS · INFERRED: 300 edges (avg confidence: 0.85)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Exchange papier C++
- Risque et instruments
- Tests lead-lag
- CLI sweep et MM
- Recorder et tests fetch
- Metriques MM et couts
- Moteur de fill MM
- Tests TSMOM comptabilite
- Legacy Python bot
- Metriques MM
- Etude TSMOM
- Includes standard C++
- Signal z-score
- Config YAML et docs
- Bougies
- Config X-macro
- Pre-enregistrements et decisions
- Telechargement trades
- Etude premium
- Marks et trades
- Tests economie MM
- Stats panel et bootstrap
- Interface IExchange
- RiskManager
- Grille de sweep
- CLI legacy main.py
- Backtest MM et tests
- Levier et expositions
- Position et funding
- Metriques backtest
- PerpBot machine etats
- Tests premium
- Parametres MM
- Signal et historique prix
- Instrument et arrondis
- Tests direction
- Klines et funding reel
- CLI panel
- Backtest et ticks
- RNG et gauss
- Groupe BacktestResult
- Groupe ClosedTrade
- Groupe backtest
- Groupe calendar
- Groupe argparse
- Groupe Config X-macro table
- Groupe Decision 35: mark at 1 minute, re
- Groupe cstring
- Groupe BacktestResult
- Groupe Instrument
- Groupe vector
- Groupe string
- Groupe test_risk.cpp
- Groupe Exécute un relevé ; toute erreur 
- Groupe docs/DECISION_NOTE.md
- Groupe cctype
- Groupe Verified API facts (trades, mark-
- Groupe backtest.hpp
- Groupe deque
- Groupe Params
- Groupe config.cpp
- Groupe tools/recorder.py
- Groupe bot
- Groupe Decision 12: sizing bounded by ex
- Groupe PnL breakdown by exit reason
- Groupe Window
- Groupe Tick
- Groupe RandomStats
- Groupe backtest.py
- Groupe run_panel()
- Groupe io
- Groupe Markout
- Groupe Decision 1: assert + Werror, no G
- Groupe Decision 27: session rules per ca
- Groupe sign()
- Groupe Decision 11: hourly funding at ep
- Groupe perp/recorder.py
- Groupe CMakeLists.txt build perp_bot
- Groupe SizeDecision
- Groupe Signal
- Groupe Inst
- Groupe Inst
- Groupe ReasonStats
- Groupe live.py
- Groupe Loader
- Groupe Decision 34: signal sense locked
- Groupe Decision 9: mmr confirmed by doc

## God Nodes (most connected - your core abstractions)
1. `Config` - 44 edges
2. `Engine` - 36 edges
3. `PerpBot` - 34 edges
4. `run_backtest()` - 32 edges
5. `MmResult` - 31 edges
6. `RiskManager` - 30 edges
7. `MmMetrics` - 29 edges
8. `Metrics` - 28 edges
9. `PaperExchange` - 28 edges
10. `MmParams` - 27 edges

## Surprising Connections (you probably didn't know these)
- `perpcore (C++17 core library)` --implements--> `C++17 deterministic engine without I/O`  [INFERRED]
  CLAUDE.md → Claude outputs/prompt_claude_code_perp.md
- `run_backtest()` --calls--> `funding_at()`  [INFERRED]
  src/backtest.cpp → include/perp/backtest.hpp
- `run_buy_hold()` --calls--> `funding_at()`  [INFERRED]
  src/validate.cpp → include/perp/backtest.hpp
- `funding_lookup()` --calls--> `funding_at()`  [INFERRED]
  tests/test_validate.cpp → include/perp/backtest.hpp
- `PerpBot::try_enter()` --calls--> `rng_`  [INFERRED]
  src/bot.cpp → include/perp/bot.hpp

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Experiment families all negative** — claude_fam_a, claude_fam_b, claude_fam_mm, claude_fam_c, claude_fam_d, claude_fam_e [EXTRACTED 0.95]
- **perpcore runtime pipeline** — claude_perpbot, claude_signalengine, claude_riskmanager, claude_positionmanager, claude_paperexchange [EXTRACTED 0.95]
- **Pre-registered validation protocol** — claude_prereg, claude_tvt, claude_bonferroni, claude_random_baseline, claude_stop_rule, claude_single_params [EXTRACTED 0.95]
- **Sources de données historiques de la famille E** — data_under_manifest_fred, data_under_manifest_kenneth_french, data_under_manifest_world_bank, docs_decision_note_famille_e [EXTRACTED 1.00]

## Communities (88 total, 10 thin omitted)

### Community 0 - "Exchange papier C++"
Cohesion: 0.08
Nodes (29): PaperExchange, last_mark_, positions_, slippage_, spread_, taker_override_, PaperExchange::bid_ask(), PaperExchange::fee_rate() (+21 more)

### Community 1 - "Risque et instruments"
Cohesion: 0.06
Nodes (29): PerpBot, cfg_, engine_, hist_, inst_, on_open_, on_trade_, pm_ (+21 more)

### Community 2 - "Tests lead-lag"
Cohesion: 0.06
Nodes (19): Execution, hand_series(), Plumbing, build_all(), candidates(), corr_at(), date_s(), fill() (+11 more)

### Community 3 - "CLI sweep et MM"
Cohesion: 0.08
Nodes (42): aggregate(), day_str(), fmt(), InstInfo, category, liq_fee, max_leverage, min_notional (+34 more)

### Community 4 - "Recorder et tests fetch"
Cohesion: 0.07
Nodes (11): FakeApi, Limiter, make_trades(), Pagination, Behaviour, bad(), flaky(), BookMath (+3 more)

### Community 5 - "Metriques MM et couts"
Cohesion: 0.04
Nodes (44): MmExit, cost, fee, liquidation, price, qty, ref, side (+36 more)

### Community 6 - "Moteur de fill MM"
Cohesion: 0.09
Nodes (19): Engine, ask_px, ask_queue, ask_rem, bid_px, bid_queue, bid_rem, cash (+11 more)

### Community 7 - "Tests TSMOM comptabilite"
Cohesion: 0.09
Nodes (8): Accounting, Constants, inst_from_returns(), Liquidation, OneMonth, Plumbing, Statistics, Weights

### Community 8 - "Legacy Python bot"
Cohesion: 0.12
Nodes (5): State, breakeven_prob(), Position, sign(), PositionManager

### Community 9 - "Metriques MM"
Cohesion: 0.07
Nodes (30): MmMetrics, buy, capture_bps, daily_sharpe, days, exit_cost, exit_count, exit_fees (+22 more)

### Community 10 - "Etude TSMOM"
Cohesion: 0.12
Nodes (21): build_inst(), buy_and_hold(), chain_dxy(), compound(), decade_table(), deflated_sharpe(), label(), load_rows() (+13 more)

### Community 11 - "Includes standard C++"
Cohesion: 0.14
Nodes (9): usage(), usage(), day(), main(), params_str(), print_segment(), usage(), verdict() (+1 more)

### Community 12 - "Signal z-score"
Cohesion: 0.13
Nodes (17): Z, price, vol, z, PriceHistory::price_ago(), rolling_vol(), sigmoid(), SignalEngine::compute() (+9 more)

### Community 13 - "Config YAML et docs"
Cohesion: 0.10
Nodes (25): config.yaml paramètres du bot, Circuit breakers, config_panel.yaml paramètres panel figés, Risque, sizing et Kelly, Paramètres de signal z-score momentum, Résumé des trades publics BTC et ETH, Résumé de profondeur d'historique (SPCX-USD), Manifeste des sources de sous-jacents (+17 more)

### Community 14 - "Bougies"
Cohesion: 0.13
Nodes (14): Candle, c, h, l, o, session, ts, closed_ (+6 more)

### Community 15 - "Config X-macro"
Cohesion: 0.13
Nodes (10): Config, strs, PositionManager, cfg_, errors(), main(), parse_values(), set_and_get() (+2 more)

### Community 16 - "Pre-enregistrements et decisions"
Cohesion: 0.12
Nodes (19): Alpha/beta regression on equal-weight market, Bonferroni correction, Buy and hold baseline, config_panel.yaml fixed params, Deflated Sharpe (Bailey, Lopez de Prado), Family A short-term momentum (BTC ETH SOL), Family B long-horizon momentum panel (15 instruments), Hypothesis: regime filter (+11 more)

### Community 17 - "Telechargement trades"
Cohesion: 0.16
Nodes (14): api_get(), ApiError, fetch_funding(), fetch_mark(), fetch_trades(), finalize_trades(), kline_trade_count(), Limiter (+6 more)

### Community 18 - "Etude premium"
Cohesion: 0.16
Nodes (15): by_side(), convergence_profile(), date_ms(), events(), funding_between(), implied_premium(), load_context(), load_inst() (+7 more)

### Community 19 - "Marks et trades"
Cohesion: 0.13
Nodes (19): MarkPoint, mark, ts, Trade, dir, price, qty, settlement (+11 more)

### Community 20 - "Tests economie MM"
Cohesion: 0.15
Nodes (11): book(), Economics, write(), analyse(), fmt(), main(), mean(), quantile() (+3 more)

### Community 21 - "Stats panel et bootstrap"
Cohesion: 0.19
Nodes (14): block_bootstrap(), deflated_sharpe(), kelly_empirical(), kelly_gauss(), moments(), read_returns(), section_dsr(), section_kelly() (+6 more)

### Community 23 - "RiskManager"
Cohesion: 0.09
Nodes (11): RiskManager, cfg_, consec_losses_, day_, day_pnl_, day_set_, entries_, net_ (+3 more)

### Community 24 - "Grille de sweep"
Cohesion: 0.17
Nodes (18): Axis, key, values, SweepRow, m, params, main(), grid_size() (+10 more)

### Community 25 - "CLI legacy main.py"
Cohesion: 0.17
Nodes (15): cmd_backtest(), cmd_fetch(), cmd_instruments(), cmd_paper(), _inst_for_backtest(), load_config(), main(), format_report() (+7 more)

### Community 26 - "Backtest MM et tests"
Cohesion: 0.32
Nodes (22): compute_metrics(), run_mm(), accounting_identity(), base_params(), conservative_hand_computed(), determinism_and_random_baseline(), direction_of_fills(), effective_spread() (+14 more)

### Community 27 - "Levier et expositions"
Cohesion: 0.13
Nodes (9): Side, Long, Short, RiskManager::check_entry(), RiskManager::choose_leverage(), RiskManager::liq_leverage_cap(), RiskManager::record_trade(), RiskManager::set_exposure() (+1 more)

### Community 28 - "Position et funding"
Cohesion: 0.10
Nodes (19): Position, entry_price, fees_paid, funding_hour, funding_paid, high_water, iid, leverage (+11 more)

### Community 29 - "Metriques backtest"
Cohesion: 0.10
Nodes (21): Metrics, avg_hold_s, avg_loss, avg_win, by_reason, fees, funding, gross_pnl (+13 more)

### Community 30 - "PerpBot machine etats"
Cohesion: 0.20
Nodes (4): PerpBot, Exchange, ClosedTrade, Tick

### Community 31 - "Tests premium"
Cohesion: 0.15
Nodes (6): flat_inst(), injected(), Inversion, OneTrade, Plumbing, set_funding()

### Community 32 - "Parametres MM"
Cohesion: 0.10
Nodes (19): MmParams, delta_bps, equity, exit_half_spread_bps, exit_to_frac, fill_model, inv_frac, leverage (+11 more)

### Community 33 - "Signal et historique prix"
Cohesion: 0.14
Nodes (5): Signal, PriceHistory, rolling_vol(), sigmoid(), SignalEngine

### Community 34 - "Instrument et arrondis"
Cohesion: 0.14
Nodes (3): Instrument, RiskManager, SizeDecision

### Community 35 - "Tests direction"
Cohesion: 0.20
Nodes (16): by_side(), cfg(), main(), mirror_series_mirrors_the_sides(), momentum_wins_with_correct_orientation(), pure_noise_does_not_win(), Regime, drift_bps (+8 more)

### Community 36 - "Klines et funding reel"
Cohesion: 0.19
Nodes (7): fetch_funding(), fetch_klines(), fill_gaps(), get(), main(), overlay_yaml(), resolve()

### Community 37 - "CLI panel"
Cohesion: 0.23
Nodes (11): ann_sharpe(), cum_return_pct(), day(), main(), params_str(), quantile(), report_window(), split_csv() (+3 more)

### Community 38 - "Backtest et ticks"
Cohesion: 0.22
Nodes (12): candle_ticks(), accounting_invariants(), backtest_is_deterministic(), candle_tick_order(), csv_roundtrip(), main(), no_trades(), off_session_blocks_entries() (+4 more)

### Community 39 - "RNG et gauss"
Cohesion: 0.24
Nodes (12): Rng, g, synthetic(), buy_and_hold_hand_computed(), buy_and_hold_with_costs_matches_identity(), cfg0(), funding_lookup(), funding_series_equals_constant() (+4 more)

### Community 40 - "Groupe BacktestResult"
Cohesion: 0.12
Nodes (15): InstRun, res, symbol, window, PanelRun, hour_ts, inst, liq_guards (+7 more)

### Community 41 - "Groupe ClosedTrade"
Cohesion: 0.12
Nodes (16): ClosedTrade, closed_ts, entry_price, exit_price, fees, funding, held_s, leverage (+8 more)

### Community 42 - "Groupe backtest"
Cohesion: 0.12
Nodes (10): BetaStats, alpha_ann_pct, beta, n, r2, t_alpha, Split, test (+2 more)

### Community 43 - "Groupe calendar"
Cohesion: 0.26
Nodes (9): analyse(), categories(), load(), main(), compare(), load_fred(), load_perp(), main() (+1 more)

### Community 44 - "Groupe argparse"
Cohesion: 0.29
Nodes (6): fetch(), get(), main(), classify(), collect(), main()

### Community 45 - "Groupe Config X-macro table"
Cohesion: 0.16
Nodes (9): Config X-macro table, IExchange, legacy_py archive, SignalEngine spec (z-score, sigmoid, Binance fusion 40/60), perp_paper (not written), PerpBot, perpcore (C++17 core library), PositionManager (+1 more)

### Community 46 - "Groupe Decision 35: mark at 1 minute, re"
Cohesion: 0.15
Nodes (10): Market making passive family, Four fill bounds (optimistic, conservative queue 0/1000/5000), Hypothesis: maker costs, Markouts / adverse selection, tools/mm_economics.py (abandoned), mm.hpp market making engine, Outcome MM: negative, adverse selection, abandoned, perp_mm (abandoned) (+2 more)

### Community 47 - "Groupe cstring"
Cohesion: 0.32
Nodes (11): base_cfg(), grace_period_emergency_stop(), is(), levels(), liq_guard_accounts_for_liquidation_fee(), long_pos(), main(), sl_tp_long() (+3 more)

### Community 48 - "Groupe BacktestResult"
Cohesion: 0.13
Nodes (13): BacktestResult, candle_ts, end_equity, equity_curve, fees, funding, halt_limit, interval_s (+5 more)

### Community 49 - "Groupe Instrument"
Cohesion: 0.13
Nodes (11): MmData, category, funding, inst, mark, mark_interval_s, symbol, tick (+3 more)

### Community 50 - "Groupe vector"
Cohesion: 0.15
Nodes (13): PanelInstrument, candles, cfg, funding, symbol, PanelRandom, entry_prob, inst_pnl (+5 more)

### Community 52 - "Groupe string"
Cohesion: 0.14
Nodes (11): Instrument, iid, liquidation_fee, maintenance_margin_rate, maker_fee, max_leverage, min_notional, mmr_factor (+3 more)

### Community 53 - "Groupe test_risk.cpp"
Cohesion: 0.30
Nodes (11): cooldowns_and_breakers(), inst50(), kelly(), leverage_bounded_by_target_and_max(), leverage_cap_vs_sl(), leverage_sizing_mode(), main(), max_entries_per_hour() (+3 more)

### Community 55 - "Groupe docs/DECISION_NOTE.md"
Cohesion: 0.15
Nodes (13): docs/DECISION_NOTE.md, CLAUDE.md trading-bot-perp, Family E time-series momentum on underlyings, Funding hypothesis H_F, Outcome E: negative, 4 of 7 criteria fail, Stepwise build: core+tests, backtester, sweep, Python, Scope change: non-crypto underlyings long history, Excluded sources (LBMA, Stooq, Yahoo, key-based APIs) (+5 more)

### Community 56 - "Groupe cctype"
Cohesion: 0.33
Nodes (7): side_name(), format_report(), load_csv(), load_funding_csv(), split(), write_trades_csv(), main()

### Community 57 - "Groupe Verified API facts (trades, mark-"
Cohesion: 0.21
Nodes (12): Verified API facts (trades, mark-history, no book history), Family C mark/index premium, Family D lead-lag vs Binance, Virgin holdout from recorder, Order book imbalance hypothesis, Outcome C: negative, premium does not converge, Outcome D: negative, nothing to see, Verified Polymarket API facts (+4 more)

### Community 58 - "Groupe backtest.hpp"
Cohesion: 0.23
Nodes (9): funding_at(), FundingPoint, rate, ts, RunOptions, funding, random_prob, seed (+1 more)

### Community 59 - "Groupe deque"
Cohesion: 0.17
Nodes (4): PriceHistory, d_, max_, min_step_

### Community 60 - "Groupe Params"
Cohesion: 0.18
Nodes (9): Params, lookback_seconds, ref_weight, sensitivity, threshold, vol_window_seconds, z_cap, SignalEngine (+1 more)

### Community 61 - "Groupe config.cpp"
Cohesion: 0.27
Nodes (8): Config::apply_text(), Config::get(), Config::instrument(), Config::load_file(), Config::set(), Config::set_kv(), Config::str(), trim()

### Community 62 - "Groupe tools/recorder.py"
Cohesion: 0.21
Nodes (7): book_record(), depth_within(), http_get(), levels(), main(), market_cost_bps(), ticker_record()

### Community 63 - "Groupe bot"
Cohesion: 0.20
Nodes (4): engine_params(), history_seconds(), PerpBot::PerpBot(), PerpBot::set_random_entries()

### Community 64 - "Groupe Decision 12: sizing bounded by ex"
Cohesion: 0.18
Nodes (5): Kelly sizing, Leverage analysis (fixed, vol-targeted, Kelly OOS), breakeven_prob edge filter, RiskManager, types.hpp (Instrument, Position, breakeven_prob)

### Community 65 - "Groupe PnL breakdown by exit reason"
Cohesion: 0.18
Nodes (11): PnL breakdown by exit reason, Fee tiers taker/maker, Short Polymarket history (~4 months, one regime), Liquidity rewards program, LiveExchange stub, Outcome A: negative, no raw edge, No real orders, no secrets in repo, tools/paper_runner.py (not written) (+3 more)

### Community 66 - "Groupe Window"
Cohesion: 0.27
Nodes (8): Window, end, start, warmup_s, panel_buy_hold(), run_instrument(), run_panel_random(), slice()

### Community 67 - "Groupe Tick"
Cohesion: 0.18
Nodes (10): Tick, ask, bid, funding_rate, index, mark, ref_price, tradable (+2 more)

### Community 68 - "Groupe RandomStats"
Cohesion: 0.18
Nodes (11): RandomStats, entry_prob, frac_ge, mean_gross, mean_pnl, mean_sharpe, mean_trades, p5 (+3 more)

### Community 69 - "Groupe backtest.py"
Cohesion: 0.27
Nodes (5): BacktestResult, candle_ticks(), load_csv(), run_backtest(), synthetic()

### Community 70 - "Groupe run_panel()"
Cohesion: 0.45
Nodes (9): run_panel(), date_parsing(), late_listing_stays_cash(), main(), make(), params_apply_to_all(), random_panel_baseline(), single_instrument_portfolio_equals_sleeve() (+1 more)

### Community 71 - "Groupe io"
Cohesion: 0.36
Nodes (4): describe(), http(), main(), write_csv()

### Community 72 - "Groupe Markout"
Cohesion: 0.22
Nodes (9): Markout, mean_bps, n, SideStats, fills, mark, notional, trade_proxy (+1 more)

### Community 73 - "Groupe Decision 1: assert + Werror, no G"
Cohesion: 0.25
Nodes (6): market_maker_bot (sibling C++17 project), Backtester 4 ticks per candle + parallel sweep, C++17 deterministic engine without I/O, Prompt pour Claude Code perps, perp_backtest, assert-based tests with CHECK_NEAR

### Community 74 - "Groupe Decision 27: session rules per ca"
Cohesion: 0.39
Nodes (5): Session calendar rules, categories(), check(), in_session(), rewrite()

### Community 75 - "Groupe sign()"
Cohesion: 0.32
Nodes (3): sign(), PositionManager::check_exits(), PositionManager::init_levels()

### Community 76 - "Groupe Decision 11: hourly funding at ep"
Cohesion: 0.29
Nodes (3): Funding carry diagnostic by category, Funding formula F_8h, PaperExchange

### Community 78 - "Groupe CMakeLists.txt build perp_bot"
Cohesion: 0.47
Nodes (6): CMakeLists.txt build perp_bot, exécutables perp_backtest sweep validate panel mm, bibliothèque perpcore, tests ctest assert-based, legacy_py README archive Python, requirements.txt dépendances Python

### Community 79 - "Groupe SizeDecision"
Cohesion: 0.33
Nodes (6): SizeDecision, kelly_mult, leverage, margin, notional, risk_usdc

### Community 80 - "Groupe Signal"
Cohesion: 0.33
Nodes (6): Signal, price, probability, side, volatility, z_score

### Community 83 - "Groupe ReasonStats"
Cohesion: 0.50
Nodes (4): ReasonStats, n, pnl, wins

## Knowledge Gaps
- **381 isolated node(s):** `ts`, `o`, `h`, `l`, `c` (+376 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 672 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **10 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Config` connect `Config X-macro` to `Risque et instruments`, `Tests direction`, `Backtest et ticks`, `RNG et gauss`, `Includes standard C++`, `Bougies`, `Groupe cstring`, `Groupe vector`, `Groupe cstdint`, `Groupe test_risk.cpp`, `RiskManager`, `Grille de sweep`, `Groupe backtest.hpp`, `Groupe config.cpp`, `Groupe bot`?**
  _High betweenness centrality (0.091) - this node is a cross-community bridge._
- **Are the 5 inferred relationships involving `Config` (e.g. with `csv_roundtrip()` and `off_session_blocks_entries()`) actually correct?**
  _`Config` has 5 INFERRED edges - model-reasoned connections that need verification._
- **What connects `ts`, `o`, `h` to the rest of the system?**
  _381 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Exchange papier C++` be split into smaller, more focused modules?**
  _Cohesion score 0.08287961282516637 - nodes in this community are weakly interconnected._
- **Why does `Position` connect `Position et funding` to `Groupe ClosedTrade`, `Groupe sign()`, `Groupe cstdint`, `Groupe string`, `Levier et expositions`?**
  _High betweenness centrality (0.055) - this node is a cross-community bridge._
- **Are the 25 inferred relationships involving `run_backtest()` (e.g. with `funding_at()` and `closed_`) actually correct?**
  _`run_backtest()` has 25 INFERRED edges - model-reasoned connections that need verification._
- **Should `Risque et instruments` be split into smaller, more focused modules?**
  _Cohesion score 0.05505279034690799 - nodes in this community are weakly interconnected._