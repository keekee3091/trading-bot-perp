// Balayage de paramètres : grille cartésienne, un backtest par point, multi-thread.
// C'est la raison d'être du C++ ici. Les résultats sont dans l'ordre de la grille quel que
// soit le nombre de threads (chaque point est indépendant et déterministe).
//
// Attention : tout classement par Sharpe sur les MÊMES bougies est in-sample. Sur une grille
// large, le meilleur point est en grande partie du bruit ajusté ; valider hors échantillon.
#pragma once

#include <functional>
#include <ostream>
#include <string>
#include <vector>

#include "perp/backtest.hpp"

namespace perp {

// Exécute fn(0..n-1) sur `threads` threads (0 = tous les coeurs), le thread appelant inclus.
// La première exception levée est relancée après l'arrêt des autres.
void parallel_for(size_t n, unsigned threads, const std::function<void(size_t)>& fn);

struct Axis {
    std::string key;
    std::vector<double> values;
};

// "cle=1,2,3" ou "cle=debut:fin:pas" (bornes incluses). Lève std::runtime_error si malformé
// ou si la clé n'existe pas dans Config.
Axis parse_axis(const std::string& spec);

struct SweepRow {
    std::vector<double> params; // une valeur par axe, dans l'ordre des axes
    Metrics m;
};

// threads == 0 : std::thread::hardware_concurrency(). Le dernier axe varie le plus vite.
std::vector<SweepRow> run_sweep(const Config& base, const std::vector<Axis>& axes,
                                const std::vector<Candle>& candles, int interval_s, unsigned threads,
                                const RunOptions& opt = {});

size_t grid_size(const std::vector<Axis>& axes);
void write_sweep_csv(std::ostream& os, const std::vector<Axis>& axes, const std::vector<SweepRow>& rows);

} // namespace perp
