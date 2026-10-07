// Protocole de validation : découpe chronologique, lignes de base aux mêmes coûts.
//
// Découpe train / validation / test dans l'ordre du temps, jamais mélangée. Le sweep ne tourne
// que sur train ; les K meilleurs points sont confirmés sur validation ; test n'est touché
// qu'une fois, pour le point final.
#pragma once

#include <cstdint>
#include <vector>

#include "perp/backtest.hpp"

namespace perp {

struct Split {
    std::vector<Candle> train, val, test;
};
Split split_chrono(const std::vector<Candle>& c, double train_frac = 0.6, double val_frac = 0.2);

// Achat au début, détention, vente à la fin : 1x, mêmes coûts (spread, slippage, frais, funding)
// que la stratégie. Compare des rendements et des Sharpe, pas des PnL absolus : la stratégie
// dimensionne par le risque, pas à 100 % de l'equity.
BacktestResult run_buy_hold(const Config& cfg, const std::vector<Candle>& candles, int interval_s,
                            const std::vector<FundingPoint>* funding);

// Régression du rendement horaire de l'equity de la stratégie sur celui de l'instrument
// (clôtures de bougies, buckets UTC d'une heure). alpha_ann_pct : alpha x 8760 en % de l'equity,
// arithmétique. Le t de alpha suppose des résidus indépendants (optimiste si autocorrélés).
struct BetaStats {
    int n = 0;
    double beta = 0, alpha_ann_pct = 0, t_alpha = 0, r2 = 0;
};
BetaStats beta_regression(const BacktestResult& r, const std::vector<Candle>& candles);
// MCO y = alpha + beta x ; alpha annualisé avec periods_per_year.
BetaStats ols_alpha_beta(const std::vector<double>& y, const std::vector<double>& x, double periods_per_year);

struct RandomStats {
    int runs = 0;
    double entry_prob = 0;   // probabilité d'entrée par tick libre après calibrage
    double mean_trades = 0;  // à comparer à la cible (même rythme)
    double mean_pnl = 0, mean_gross = 0, mean_sharpe = 0;
    double p5 = 0, p50 = 0, p95 = 0; // quantiles du PnL net
    double frac_ge = 0;      // part des tirages dont le PnL net >= celui de la stratégie
};

// Entrées aléatoires avec le même rythme de trades (calibrage de la probabilité d'entrée sur
// target_trades) et exactement la même logique de sortie, de sizing et de coûts.
RandomStats run_random_baseline(const Config& cfg, const std::vector<Candle>& candles, int interval_s,
                                const std::vector<FundingPoint>* funding, double target_trades,
                                double strategy_pnl, int runs, std::uint64_t seed, unsigned threads);

} // namespace perp
