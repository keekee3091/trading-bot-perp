// perp_backtest : rejoue des bougies sur le PerpBot + PaperExchange et imprime le rapport.
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <exception>
#include <string>
#include <vector>

#include "perp/backtest.hpp"
#include "perp/config.hpp"

using namespace perp;

static void usage() {
    std::puts(
        "usage : perp_backtest (--csv FICHIER | --synthetic N) [options]\n"
        "  --config FICHIER   yaml, répétable, les suivants écrasent (défaut : config.yaml)\n"
        "  --set cle=valeur   surcharge d'un paramètre, répétable (ex. --set leverage=3)\n"
        "  --interval SEC     durée d'une bougie (défaut 60), sert au Sharpe annualisé\n"
        "  --seed S           graine du synthétique (défaut 7)\n"
        "  --trades FICHIER   écrit les trades en CSV\n"
        "Le synthétique valide la plomberie, il ne prouve aucun edge.");
}

int main(int argc, char** argv) {
    std::vector<std::string> configs, sets;
    std::string csv, trades_out;
    int synth_n = 0, interval = 60;
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
        else if (a == "--csv") csv = need(i);
        else if (a == "--synthetic") synth_n = std::atoi(need(i));
        else if (a == "--interval") interval = std::atoi(need(i));
        else if (a == "--seed") seed = std::strtoull(need(i), nullptr, 10);
        else if (a == "--trades") trades_out = need(i);
        else if (a == "--help" || a == "-h") { usage(); return 0; }
        else { std::fprintf(stderr, "option inconnue : %s\n", a.c_str()); usage(); return 2; }
    }
    if (csv.empty() == (synth_n <= 0) || interval <= 0) { usage(); return 2; }
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
        std::vector<Candle> candles;
        if (!csv.empty()) {
            candles = load_csv(csv);
        } else {
            candles = synthetic(synth_n, interval, 100.0, seed);
            std::printf("[synthetique %zu bougies : valide la plomberie, ne prouve aucun edge]\n",
                        candles.size());
        }
        if (candles.empty()) {
            std::fprintf(stderr, "aucune bougie\n");
            return 1;
        }
        const BacktestResult res = run_backtest(cfg, candles, interval);
        std::printf("%s %zu bougies de %ds\n", cfg.str("symbol", "?").c_str(), candles.size(), interval);
        std::fputs(format_report(res.metrics()).c_str(), stdout);
        if (!trades_out.empty()) write_trades_csv(trades_out, res.trades);
    } catch (const std::exception& e) {
        std::fprintf(stderr, "erreur : %s\n", e.what());
        return 1;
    }
    return 0;
}
