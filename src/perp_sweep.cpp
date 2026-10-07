// perp_sweep : balayage multi-thread d'une grille de paramètres, sortie CSV.
#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <exception>
#include <fstream>
#include <string>
#include <thread>
#include <vector>

#include "perp/backtest.hpp"
#include "perp/config.hpp"
#include "perp/sweep.hpp"

using namespace perp;

static void usage() {
    std::puts(
        "usage : perp_sweep (--csv FICHIER | --synthetic N) --grid cle=valeurs [--grid ...] [options]\n"
        "  --grid cle=1,2,3 | cle=debut:fin:pas   un axe par option (produit cartésien)\n"
        "  --threads N        défaut : tous les coeurs\n"
        "  --out FICHIER      CSV complet (défaut : sweep.csv)\n"
        "  --top N            lignes du classement affiché (défaut 10)\n"
        "  --min-trades N     exclut du classement les points avec moins de N trades (défaut 30)\n"
        "  --config / --set / --interval / --seed : comme perp_backtest\n"
        "Le classement est in-sample : le meilleur point d'une grille large est surtout du bruit ajusté.");
}

int main(int argc, char** argv) {
    std::vector<std::string> configs, sets, grids;
    std::string csv, out = "sweep.csv";
    int synth_n = 0, interval = 60, top = 10, min_trades = 30;
    unsigned threads = 0;
    unsigned long long seed = 7;
    auto need = [&](int& i) -> const char* {
        if (i + 1 >= argc) {
            std::fprintf(stderr, "valeur manquante après %s\n", argv[i]);
            std::exit(2);
        }
        return argv[++i];
    };
    for (int i = 1; i < argc; ++i) {
        const std::string a = argv[i];
        if (a == "--config") configs.push_back(need(i));
        else if (a == "--set") sets.push_back(need(i));
        else if (a == "--grid") grids.push_back(need(i));
        else if (a == "--csv") csv = need(i);
        else if (a == "--synthetic") synth_n = std::atoi(need(i));
        else if (a == "--interval") interval = std::atoi(need(i));
        else if (a == "--seed") seed = std::strtoull(need(i), nullptr, 10);
        else if (a == "--threads") threads = static_cast<unsigned>(std::atoi(need(i)));
        else if (a == "--out") out = need(i);
        else if (a == "--top") top = std::atoi(need(i));
        else if (a == "--min-trades") min_trades = std::atoi(need(i));
        else if (a == "--help" || a == "-h") { usage(); return 0; }
        else { std::fprintf(stderr, "option inconnue : %s\n", a.c_str()); usage(); return 2; }
    }
    if (csv.empty() == (synth_n <= 0) || grids.empty() || interval <= 0) { usage(); return 2; }
    if (configs.empty()) configs.push_back("config.yaml");

    try {
        Config cfg;
        for (const auto& f : configs) cfg.load_file(f);
        for (const auto& s : sets) {
            const size_t eq = s.find('=');
            if (eq == std::string::npos || !cfg.set_kv(s.substr(0, eq), s.substr(eq + 1))) {
                std::fprintf(stderr, "--set invalide ou cle inconnue : %s\n", s.c_str());
                return 2;
            }
        }
        std::vector<Axis> axes;
        for (const auto& g : grids) axes.push_back(parse_axis(g));
        const std::vector<Candle> candles =
            csv.empty() ? synthetic(synth_n, interval, 100.0, seed) : load_csv(csv);
        if (candles.empty()) {
            std::fprintf(stderr, "aucune bougie\n");
            return 1;
        }
        if (csv.empty()) std::puts("[synthetique : valide la plomberie, ne prouve aucun edge]");
        std::printf("%zu points x %zu bougies, %u threads\n", grid_size(axes), candles.size(),
                    threads ? threads : std::max(1u, std::thread::hardware_concurrency()));

        const std::vector<SweepRow> rows = run_sweep(cfg, axes, candles, interval, threads);

        std::ofstream f(out);
        if (!f) {
            std::fprintf(stderr, "ecriture impossible : %s\n", out.c_str());
            return 1;
        }
        write_sweep_csv(f, axes, rows);
        std::printf("CSV : %s\n", out.c_str());

        std::vector<const SweepRow*> ranked;
        for (const auto& r : rows)
            if (r.m.trades >= min_trades) ranked.push_back(&r);
        std::sort(ranked.begin(), ranked.end(),
                  [](const SweepRow* a, const SweepRow* b) { return a->m.sharpe > b->m.sharpe; });
        std::printf("Classement par Sharpe (in-sample, >= %d trades, %zu/%zu points éligibles) :\n", min_trades,
                    ranked.size(), rows.size());
        for (int k = 0; k < top && k < static_cast<int>(ranked.size()); ++k) {
            const SweepRow& r = *ranked[static_cast<size_t>(k)];
            std::printf("  %2d.", k + 1);
            for (size_t a = 0; a < axes.size(); ++a) std::printf(" %s=%g", axes[a].key.c_str(), r.params[a]);
            std::printf(" | sharpe %.2f pnl %+.2f dd %.1f%% trades %ld\n", r.m.sharpe, r.m.pnl,
                        r.m.max_drawdown_pct, r.m.trades);
        }
    } catch (const std::exception& e) {
        std::fprintf(stderr, "erreur : %s\n", e.what());
        return 1;
    }
    return 0;
}
