// perp_validate : protocole de validation hors échantillon.
//   1. découpe chronologique 60/20/20 (train / validation / test), jamais mélangée
//   2. sweep sur train seulement ; les K meilleurs points sont confirmés sur validation
//   3. le point final (meilleur Sharpe de validation parmi les K) est évalué UNE fois sur test
//   4. lignes de base aux mêmes coûts : buy and hold, entrées aléatoires au même rythme
// Le halt de session est désactivé pendant tout le protocole (il tronque les mauvais points et
// biaise le classement) ; la colonne halt_breached dit s'il aurait eu lieu.
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <ctime>
#include <exception>
#include <fstream>
#include <string>
#include <thread>
#include <vector>

#include "perp/backtest.hpp"
#include "perp/config.hpp"
#include "perp/sweep.hpp"
#include "perp/validate.hpp"

using namespace perp;

static void usage() {
    std::puts(
        "usage : perp_validate --csv FICHIER --grid cle=valeurs [--grid ...] [options]\n"
        "  --funding FICHIER   historique de funding (tools/fetch_klines.py) ; sinon taux constant\n"
        "  --config / --set    comme perp_backtest (config.yaml par défaut, overlay instrument en plus)\n"
        "  --k N               points retenus de train pour la validation (défaut 5)\n"
        "  --min-trades N      trades minimum en train pour être éligible (défaut 30)\n"
        "  --min-val-trades N  trades minimum en validation pour être retenu (défaut 10)\n"
        "  --random-runs N     tirages de la ligne de base aléatoire (défaut 200)\n"
        "  --threads N  --seed S  --interval SEC  --sweep-csv FICHIER (grille de train complète)\n"
        "Si aucun point ne tient en validation, test n'est pas touché.");
}

static std::string day(double ts) {
    char b[16];
    const std::time_t t = static_cast<std::time_t>(ts);
    std::strftime(b, sizeof b, "%Y-%m-%d", std::gmtime(&t));
    return b;
}

static std::string params_str(const std::vector<Axis>& axes, const std::vector<double>& p) {
    std::string s;
    char b[64];
    for (size_t i = 0; i < axes.size(); ++i) {
        std::snprintf(b, sizeof b, "%s%s=%g", i ? " " : "", axes[i].key.c_str(), p[i]);
        s += b;
    }
    return s;
}

static Config with_params(Config c, const std::vector<Axis>& axes, const std::vector<double>& p) {
    for (size_t i = 0; i < axes.size(); ++i) c.set(axes[i].key, p[i]);
    return c;
}

static const char* verdict(const Metrics& m) {
    if (m.trades < 30) return "TROP PEU DE TRADES (<30) : aucune conclusion";
    if (m.trades < 100) return "peu de trades (<100) : indicatif seulement";
    if (std::fabs(m.trade_t_stat) < 2) return "PnL par trade non significatif (|t|<2)";
    return "PnL par trade significatif (|t|>=2)";
}

static void print_segment(const char* name, const std::vector<Candle>& c, const BacktestResult& r,
                          const BacktestResult& bh, const RandomStats& rnd) {
    const Metrics m = r.metrics(), b = bh.metrics();
    std::printf("\n== %s : %s -> %s (%.1f jours, %zu bougies)\n", name, day(c.front().ts).c_str(),
                day(c.back().ts).c_str(), (c.back().ts - c.front().ts) / 86400.0, c.size());
    std::printf("  Stratégie : %ld trades, win %.1f%%, Sharpe %.2f, PnL net %+.2f (%+.2f%%), max DD %.1f%%\n",
                m.trades, m.win_rate * 100, m.sharpe, m.pnl, m.return_pct, m.max_drawdown_pct);
    std::printf("    brut %+.2f - frais %.2f - funding %+.2f = net %+.2f | t par trade %.2f | halt aurait eu lieu : %s\n",
                m.gross_pnl, m.fees, m.funding, m.pnl, m.trade_t_stat, m.halt_breached ? "OUI" : "non");
    std::printf("    %s\n", verdict(m));
    long ln = 0, sn = 0, lw = 0, sw = 0;
    double lp = 0, sp = 0;
    for (const auto& t : r.trades) {
        (t.side == Side::Long ? ln : sn) += 1;
        (t.side == Side::Long ? lw : sw) += t.pnl > 0 ? 1 : 0;
        (t.side == Side::Long ? lp : sp) += t.pnl;
    }
    std::printf("    longs : %ld trades, PnL %+.2f, win %.0f%% | shorts : %ld trades, PnL %+.2f, win %.0f%%\n", ln, lp,
                ln ? 100.0 * static_cast<double>(lw) / static_cast<double>(ln) : 0.0, sn, sp,
                sn ? 100.0 * static_cast<double>(sw) / static_cast<double>(sn) : 0.0);
    const BetaStats bs = beta_regression(r, c);
    std::printf("    régression horaire sur l'instrument (n=%d) : beta %.3f, alpha annualisé %+.1f%% de l'equity, t(alpha) %.2f, R2 %.3f\n",
                bs.n, bs.beta, bs.alpha_ann_pct, bs.t_alpha, bs.r2);
    std::printf("    sorties :");
    std::vector<std::pair<std::string, ReasonStats>> rs(m.by_reason.begin(), m.by_reason.end());
    std::sort(rs.begin(), rs.end(), [](const auto& a, const auto& b2) { return a.second.pnl < b2.second.pnl; });
    for (const auto& kv : rs) std::printf(" %s n=%ld pnl=%+.2f;", kv.first.c_str(), kv.second.n, kv.second.pnl);
    std::printf("\n  Buy and hold 1x : %+.2f%% (Sharpe %.2f, max DD %.1f%%, frais %.2f, funding %+.2f)\n",
                b.return_pct, b.sharpe, b.max_drawdown_pct, b.fees, b.funding);
    if (rnd.runs > 0)
        std::printf("  Aléatoire (%d tirages, %.0f trades en moyenne vs %ld) : PnL net moyen %+.2f [p5 %+.2f, p50 %+.2f, p95 %+.2f], "
                    "brut moyen %+.2f, Sharpe moyen %.2f ; la stratégie fait mieux que %.0f%% des tirages\n",
                    rnd.runs, rnd.mean_trades, m.trades, rnd.mean_pnl, rnd.p5, rnd.p50, rnd.p95, rnd.mean_gross,
                    rnd.mean_sharpe, 100.0 * (1.0 - rnd.frac_ge));
}

int main(int argc, char** argv) {
    std::vector<std::string> configs, sets, grids;
    std::string csv, funding_csv, sweep_csv;
    int k = 5, min_trades = 30, min_val_trades = 10, random_runs = 200, interval = 60;
    unsigned threads = 0;
    unsigned long long seed = 1;
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
        else if (a == "--funding") funding_csv = need(i);
        else if (a == "--sweep-csv") sweep_csv = need(i);
        else if (a == "--k") k = std::atoi(need(i));
        else if (a == "--min-trades") min_trades = std::atoi(need(i));
        else if (a == "--min-val-trades") min_val_trades = std::atoi(need(i));
        else if (a == "--random-runs") random_runs = std::atoi(need(i));
        else if (a == "--interval") interval = std::atoi(need(i));
        else if (a == "--threads") threads = static_cast<unsigned>(std::atoi(need(i)));
        else if (a == "--seed") seed = std::strtoull(need(i), nullptr, 10);
        else if (a == "--help" || a == "-h") { usage(); return 0; }
        else { std::fprintf(stderr, "option inconnue : %s\n", a.c_str()); usage(); return 2; }
    }
    if (csv.empty() || grids.empty() || k < 1 || interval <= 0) { usage(); return 2; }
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
        cfg.max_session_loss_pct = 0; // halt désactivé (halt_breached le signale)
        std::vector<Axis> axes;
        for (const auto& g : grids) axes.push_back(parse_axis(g));

        const std::vector<Candle> candles = load_csv(csv);
        if (candles.size() < 3000) {
            std::fprintf(stderr, "trop peu de bougies (%zu)\n", candles.size());
            return 1;
        }
        std::vector<FundingPoint> funding;
        RunOptions opt;
        if (!funding_csv.empty()) {
            funding = load_funding_csv(funding_csv);
            opt.funding = &funding;
        }
        const Split sp = split_chrono(candles);
        const size_t npts = grid_size(axes);
        std::printf("%s | %zu bougies, %s -> %s | funding %s\n", cfg.str("symbol", "?").c_str(), candles.size(),
                    day(candles.front().ts).c_str(), day(candles.back().ts).c_str(),
                    funding.empty() ? "constant (hypothèse)" : "historique réel");
        std::printf("Découpe chronologique : train %zu / validation %zu / test %zu bougies\n", sp.train.size(),
                    sp.val.size(), sp.test.size());
        std::printf("Sweep sur train seulement : %zu points testés. Le meilleur d'une grille large est biaisé à la hausse "
                    "(sélection sur le bruit) ; seule la validation puis le test hors échantillon comptent.\n", npts);

        // 2. sweep train, top K
        const std::vector<SweepRow> rows = run_sweep(cfg, axes, sp.train, interval, threads, opt);
        if (!sweep_csv.empty()) {
            std::ofstream f(sweep_csv);
            write_sweep_csv(f, axes, rows);
        }
        std::vector<const SweepRow*> ranked;
        for (const auto& r : rows)
            if (r.m.trades >= min_trades) ranked.push_back(&r);
        std::sort(ranked.begin(), ranked.end(), [](const SweepRow* a, const SweepRow* b) { return a->m.sharpe > b->m.sharpe; });
        long positive = 0;
        for (const auto& r : rows) positive += r.m.sharpe > 0 ? 1 : 0;
        std::printf("Train : %zu/%zu points éligibles (>= %d trades), %ld avec Sharpe > 0.\n", ranked.size(), npts,
                    min_trades, positive);
        if (ranked.empty()) {
            std::puts("Aucun point éligible : arrêt (validation et test non touchés).");
            return 0;
        }
        if (static_cast<int>(ranked.size()) > k) ranked.resize(static_cast<size_t>(k));

        // confirmation sur validation
        std::puts("\nTop K de train confirmés sur validation :");
        const SweepRow* best = nullptr;
        double best_val = -1e18;
        for (const SweepRow* r : ranked) {
            const Metrics v = run_backtest(with_params(cfg, axes, r->params), sp.val, interval, opt).metrics();
            std::printf("  %-52s train Sharpe %6.2f PnL %+8.2f (%3ld trades) | val Sharpe %6.2f PnL %+8.2f (%3ld trades)\n",
                        params_str(axes, r->params).c_str(), r->m.sharpe, r->m.pnl, r->m.trades, v.sharpe, v.pnl,
                        v.trades);
            if (v.trades >= min_val_trades && v.sharpe > best_val) {
                best_val = v.sharpe;
                best = r;
            }
        }
        std::printf("Points évalués : %zu (train) + %zu (validation) + 1 (test, une seule fois).\n", npts, ranked.size());
        if (!best) {
            std::printf("Aucun des K n'a >= %d trades en validation : pas de point final, test non touché.\n",
                        min_val_trades);
            return 0;
        }
        const Config fin = with_params(cfg, axes, best->params);
        std::printf("\nPoint final (meilleur Sharpe de validation parmi les K) : %s\n", params_str(axes, best->params).c_str());

        // 3-4. rapport train / validation / test avec lignes de base
        const std::vector<Candle>* segs[3] = {&sp.train, &sp.val, &sp.test};
        const char* names[3] = {"TRAIN (in-sample)", "VALIDATION", "TEST (hors échantillon, vu une seule fois)"};
        double test_sharpe = 0, test_pnl = 0;
        for (int s = 0; s < 3; ++s) {
            const BacktestResult r = run_backtest(fin, *segs[s], interval, opt);
            const BacktestResult bh = run_buy_hold(fin, *segs[s], interval, opt.funding);
            const RandomStats rnd = run_random_baseline(fin, *segs[s], interval, opt.funding,
                                                        static_cast<double>(r.trades.size()), r.end_equity - r.start_equity,
                                                        random_runs, seed, threads);
            print_segment(names[s], *segs[s], r, bh, rnd);
            if (s == 2) {
                test_sharpe = r.metrics().sharpe;
                test_pnl = r.end_equity - r.start_equity;
            }
        }
        std::printf("\nRÉSULTAT HORS ÉCHANTILLON : Sharpe %.2f, PnL net %+.2f -> %s\n", test_sharpe, test_pnl,
                    test_sharpe > 0 && test_pnl > 0 ? "positif net de coûts (à confirmer : robustesse, nombre de trades)"
                                                    : "NON positif net de coûts : ne pas passer au paper avec ces paramètres");
    } catch (const std::exception& e) {
        std::fprintf(stderr, "erreur : %s\n", e.what());
        return 1;
    }
    return 0;
}
