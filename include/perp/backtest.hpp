// Backtest sur bougies : rejoue le MÊME PerpBot sur PaperExchange.
//
// Chaque bougie OHLC est découpée en 4 ticks (o, puis low/high selon la couleur, puis c) pour
// que stops, liquidations et trailing voient les extrêmes intra-bougie. Hypothèse de chemin :
// bougie haussière = o,l,h,c ; baissière = o,h,l,c. C'est une approximation : l'ordre réel de
// l'extrême est inconnu, ce qui biaise la lecture des SL et TP touchés dans la même bougie.
#pragma once

#include <array>
#include <cstdint>
#include <map>
#include <string>
#include <vector>

#include "perp/config.hpp"
#include "perp/types.hpp"

namespace perp {

struct Candle {
    double ts, o, h, l, c; // ts en secondes epoch (ouverture)
    bool session = true;   // false : hors session (colonne csv `session`), pas d'entrée
};

// CSV avec en-tête : ts (ms ou s), open, high, low, close[, volume]. Trié par ts, doublons retirés.
// Lève std::runtime_error si le fichier ou une colonne manque.
std::vector<Candle> load_csv(const std::string& path);

// Marché synthétique GBM à régimes de tendance, déterministe (RNG portable). Valide la
// plomberie ; ne prouve aucun edge.
std::vector<Candle> synthetic(int n, int interval_s = 60, double start = 100.0, std::uint64_t seed = 7);

std::array<Tick, 4> candle_ticks(const Candle& c, int interval_s, double funding_rate);

// Taux de funding horaire observé : ts en secondes, rate par heure (positif : les longs paient).
struct FundingPoint {
    double ts, rate;
};

// CSV ts(ms),rate produit par tools/fetch_klines.py. Trié par ts.
std::vector<FundingPoint> load_funding_csv(const std::string& path);

// Dernier taux publié à ts + 1 s (les publications sont horodatées quelques ms après l'heure pile).
// idx est un curseur monotone : le réutiliser pour des ts croissants. 0 avant la première publication.
inline double funding_at(const std::vector<FundingPoint>& f, size_t& idx, double ts) {
    while (idx < f.size() && f[idx].ts <= ts + 1.0) ++idx;
    return idx == 0 ? 0.0 : f[idx - 1].rate;
}

struct ReasonStats {
    long n = 0, wins = 0;
    double pnl = 0;
};

struct Metrics {
    long trades = 0;
    double win_rate = 0, pnl = 0, return_pct = 0, sharpe = 0, max_drawdown_pct = 0;
    double profit_factor = 0, avg_win = 0, avg_loss = 0, avg_hold_s = 0;
    double fees = 0, funding = 0, shortfall = 0;
    double gross_pnl = 0;       // somme de signe x qté x (sortie - entrée), avant frais et funding
    double trade_t_stat = 0;    // moyenne / erreur standard du PnL par trade (0 si < 2 trades)
    bool halt_breached = false; // le PnL cumulé a touché -halt_report_pct x equity
    long liquidations = 0;
    std::map<std::string, ReasonStats> by_reason;
    std::map<std::string, long> skips;
};

struct BacktestResult {
    std::vector<ClosedTrade> trades;
    std::vector<double> equity_curve; // une valeur par bougie, + l'equity initiale en tête
    std::vector<double> candle_ts;    // ts des bougies, parallèle à equity_curve sans son premier élément
    double start_equity = 0, end_equity = 0;
    double fees = 0, funding = 0, shortfall = 0;
    int liquidations = 0;
    std::map<std::string, long> skips;
    int interval_s = 60;
    double halt_limit = 0; // perte cumulée (positive) à partir de laquelle un halt de session aurait eu lieu

    Metrics metrics() const;
};

struct RunOptions {
    // Funding réel (step : dernier taux publié à ts + 1 s). nullptr : taux constant
    // cfg.bt_funding_rate_per_hour. Avant le premier point publié : 0.
    const std::vector<FundingPoint>* funding = nullptr;
    // Ligne de base : entrées aléatoires (côté à pile ou face, filtres z et edge ignorés, reste du
    // pipeline identique) avec probabilité random_prob par tick libre. 0 : la stratégie.
    double random_prob = 0;
    std::uint64_t seed = 0;
    // Bougies antérieures à start_ts : préchauffage (l'historique du signal est alimenté, aucune
    // entrée, rien dans la courbe d'equity). 0 : pas de préchauffage.
    double start_ts = 0;
};

// Instrument et coûts tirés de cfg. La position ouverte en fin de test est fermée au dernier
// prix (raison "end_of_test"), donc end_equity = start_equity + somme des PnL nets.
BacktestResult run_backtest(const Config& cfg, const std::vector<Candle>& candles, int interval_s = 60,
                            const RunOptions& opt = {});

std::string format_report(const Metrics& m);
void write_trades_csv(const std::string& path, const std::vector<ClosedTrade>& trades);

} // namespace perp
