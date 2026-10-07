// Panel multi-instruments : un seul jeu de paramètres commun, jamais un réglage par instrument.
//
// Chaque instrument est un sleeve indépendant (equity propre, risk manager propre, pas de limite
// croisée entre instruments). Le portefeuille équipondéré est la moyenne des equity des sleeves,
// échantillonnée à l'heure ; un sleeve pas encore listé reste en cash (equity constante).
#pragma once

#include <string>
#include <utility>
#include <vector>

#include "perp/backtest.hpp"
#include "perp/validate.hpp"

namespace perp {

struct PanelInstrument {
    std::string symbol;
    Config cfg; // config de base + overlay instrument, sans les paramètres de la grille
    std::vector<Candle> candles;
    std::vector<FundingPoint> funding;
};

using Params = std::vector<std::pair<std::string, double>>; // clé de Config -> valeur

// Charge <dir>/<SYM>_1m.csv, <SYM>_funding.csv et <SYM>.instrument.yaml (facultatif) ;
// config_files puis sets (cle=valeur) s'appliquent à tous. Lève sur fichier manquant.
std::vector<PanelInstrument> load_panel(const std::vector<std::string>& symbols, const std::string& dir,
                                        const std::vector<std::string>& config_files,
                                        const std::vector<std::string>& sets);

// Fenêtre [start, end) en secondes epoch ; warmup_s de bougies avant start alimentent le signal.
struct Window {
    double start = 0, end = 1e18, warmup_s = 0;
};

// Epoch (s) du minuit UTC de "YYYY-MM-DD". Lève si malformé.
double parse_date(const std::string& ymd);

struct InstRun {
    std::string symbol;
    BacktestResult res;
    std::vector<Candle> window; // bougies dans [start, end), sans préchauffage
};

struct PanelRun {
    std::vector<InstRun> inst;
    BacktestResult port;          // equity du portefeuille à l'heure (interval_s = 3600)
    std::vector<double> hour_ts;  // début de chaque heure, aligné sur port.equity_curve sans le 1er point
    std::vector<double> port_ret; // rendements horaires du portefeuille
    std::vector<double> mkt_ret;  // rendement horaire équipondéré des instruments actifs (marché)
    Metrics pm;                   // métriques du portefeuille (Sharpe annualisé horaire, DD, rendement)
    int n_active = 0;             // instruments avec des bougies dans la fenêtre
    int n_positive = 0;           // instruments actifs avec PnL net > 0
    long liquidations = 0, liq_guards = 0;
};

// random_prob : une probabilité d'entrée par instrument (même ordre que panel), nullptr = stratégie.
PanelRun run_panel(const std::vector<PanelInstrument>& panel, const Params& params, const Window& w,
                   unsigned threads, const std::vector<double>* random_prob = nullptr,
                   std::uint64_t seed = 0);

struct PanelRandom {
    std::vector<double> entry_prob;              // par instrument, après calibrage
    std::vector<double> sharpe, ret_pct;         // un par tirage, portefeuille
    std::vector<std::vector<double>> inst_pnl;   // [instrument][tirage], PnL net
};

// Même nombre de trades que la stratégie par instrument, mêmes sorties, mêmes coûts.
PanelRandom run_panel_random(const std::vector<PanelInstrument>& panel, const Params& params, const Window& w,
                             const PanelRun& strategy, int runs, std::uint64_t seed, unsigned threads);

// Buy and hold 1x par instrument sur la fenêtre.
std::vector<BacktestResult> panel_buy_hold(const std::vector<PanelInstrument>& panel, const Window& w);

} // namespace perp
