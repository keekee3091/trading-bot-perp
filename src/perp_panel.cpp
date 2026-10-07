// perp_panel : validation hors échantillon en PANEL (un seul jeu de paramètres pour tous les
// instruments) et analyse du levier.
//
//   --mode search    sweep sur train, top K confirmés sur validation, point final évalué UNE fois sur
//                    test, avec lignes de base (buy and hold, entrées aléatoires), longs/shorts, beta
//   --mode leverage  paramètres donnés (--params fichier ou --set) : courbe de levier fixe, levier
//                    vol-ciblé, sur validation et test
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <exception>
#include <ctime>
#include <fstream>
#include <numeric>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

#include "perp/panel.hpp"
#include "perp/sweep.hpp"

using namespace perp;

static void usage() {
    std::puts(
        "usage : perp_panel --mode search|leverage --symbols A,B,C [options]\n"
        "  --data-dir D        défaut data\n"
        "  --config F          répétable, après config.yaml par défaut (ex. config_panel.yaml)\n"
        "  --set cle=valeur    répétable\n"
        "  --train-end DATE --val-end DATE   bornes UTC (YYYY-MM-DD) : train < train-end <= val < val-end <= test\n"
        "  --warmup-days N     préchauffage de l'historique avant val et test (défaut 2)\n"
        "  --out-prefix P      défaut results/panel\n"
        "  --threads N  --seed S  --random-runs N (défaut 100)\n"
        "search : --grid cle=valeurs (répétable) --k 5 --min-trades 100 --min-val-trades 30\n"
        "leverage : --params fichier (cle=valeur par ligne, écrit par search)");
}

static std::vector<std::string> split_csv(const std::string& s) {
    std::vector<std::string> out;
    std::stringstream ss(s);
    std::string t;
    while (std::getline(ss, t, ',')) {
        if (!t.empty()) out.push_back(t);
    }
    return out;
}

static std::string params_str(const Params& p) {
    std::string s;
    char b[96];
    for (size_t i = 0; i < p.size(); ++i) {
        std::snprintf(b, sizeof b, "%s%s=%g", i ? " " : "", p[i].first.c_str(), p[i].second);
        s += b;
    }
    return s;
}

static double quantile(std::vector<double> v, double q) {
    if (v.empty()) return 0;
    std::sort(v.begin(), v.end());
    return v[static_cast<size_t>(q * static_cast<double>(v.size() - 1))];
}

static void write_returns(const std::string& path, const PanelRun& r) {
    std::ofstream f(path);
    f << "ts,port_ret,mkt_ret\n";
    f.precision(12);
    for (size_t i = 0; i < r.hour_ts.size(); ++i) f << r.hour_ts[i] << ',' << r.port_ret[i] << ',' << r.mkt_ret[i] << '\n';
}

static double cum_return_pct(const std::vector<double>& r) {
    double e = 1;
    for (double x : r) e *= 1 + x;
    return (e - 1) * 100;
}

static double ann_sharpe(const std::vector<double>& r) {
    if (r.size() < 3) return 0;
    double m = 0;
    for (double x : r) m += x;
    m /= static_cast<double>(r.size());
    double v = 0;
    for (double x : r) v += (x - m) * (x - m);
    const double sd = std::sqrt(v / static_cast<double>(r.size() - 1));
    return sd > 0 ? m / sd * std::sqrt(8760.0) : 0.0;
}

static std::string day(double ts) {
    char b[16];
    const std::time_t t = static_cast<std::time_t>(ts);
    std::strftime(b, sizeof b, "%Y-%m-%d", std::gmtime(&t));
    return b;
}

static const char* verdict(long trades, double t) {
    if (trades < 30) return "TROP PEU DE TRADES (<30)";
    if (trades < 100) return "peu de trades (<100), indicatif";
    return std::fabs(t) < 2 ? "PnL par trade non significatif (|t|<2)" : "PnL par trade significatif (|t|>=2)";
}

// Rapport complet d'une fenêtre pour un jeu de paramètres.
static PanelRun report_window(const char* name, const std::vector<PanelInstrument>& panel, const Params& params,
                              const Window& w, int random_runs, std::uint64_t seed, unsigned threads,
                              bool detail) {
    const PanelRun pr = run_panel(panel, params, w, threads);
    const Metrics& m = pr.pm;
    double nlong = 0, nshort = 0, plong = 0, pshort = 0;
    for (const auto& t : pr.port.trades) {
        (t.side == Side::Long ? nlong : nshort) += 1;
        (t.side == Side::Long ? plong : pshort) += t.pnl;
    }
    const double cap = pr.port.start_equity * static_cast<double>(panel.size());
    std::printf("\n== %s : %s -> %s\n", name, day(w.start).c_str(), day(pr.hour_ts.empty() ? w.start : pr.hour_ts.back()).c_str());
    std::printf("  Portefeuille équipondéré : Sharpe %.2f, rendement net %+.2f%%, max DD %.2f%%, %ld trades (win %.1f%%), "
                "instruments positifs %d/%d\n",
                m.sharpe, m.return_pct, m.max_drawdown_pct, m.trades, m.win_rate * 100, pr.n_positive, pr.n_active);
    std::printf("    brut %+.2f%% - frais %.2f%% - funding %+.2f%% = net %+.2f%% du capital | t par trade %.2f | %s\n",
                100 * m.gross_pnl / cap, 100 * m.fees / cap, 100 * m.funding / cap, m.return_pct, m.trade_t_stat,
                verdict(m.trades, m.trade_t_stat));
    std::printf("    longs : %.0f trades, PnL %+.2f%% du capital | shorts : %.0f trades, PnL %+.2f%% | liquidations %ld, liq_guard %ld\n",
                nlong, 100 * plong / cap, nshort, 100 * pshort / cap, pr.liquidations, pr.liq_guards);
    const BetaStats bs = ols_alpha_beta(pr.port_ret, pr.mkt_ret, 8760.0);
    std::printf("    beta au marché équipondéré %.3f, alpha annualisé %+.2f%% du capital, t(alpha) %.2f, R2 %.3f (n=%d h)\n",
                bs.beta, bs.alpha_ann_pct, bs.t_alpha, bs.r2, bs.n);
    std::printf("    sorties :");
    std::vector<std::pair<std::string, ReasonStats>> rs(m.by_reason.begin(), m.by_reason.end());
    std::sort(rs.begin(), rs.end(), [](const auto& a, const auto& b) { return a.second.pnl < b.second.pnl; });
    for (const auto& kv : rs) std::printf(" %s n=%ld pnl=%+.0f;", kv.first.c_str(), kv.second.n, kv.second.pnl);
    std::printf("\n    marché équipondéré sans coûts (buy and hold) : %+.2f%%, Sharpe %.2f\n", cum_return_pct(pr.mkt_ret),
                ann_sharpe(pr.mkt_ret));

    if (random_runs > 0) {
        const PanelRandom rnd = run_panel_random(panel, params, w, pr, random_runs, seed, threads);
        double ge_s = 0, ge_r = 0;
        for (size_t j = 0; j < rnd.sharpe.size(); ++j) {
            ge_s += rnd.sharpe[j] >= m.sharpe ? 1 : 0;
            ge_r += rnd.ret_pct[j] >= m.return_pct ? 1 : 0;
        }
        const double n = static_cast<double>(rnd.sharpe.size());
        std::printf("    entrées aléatoires (%d tirages, même nombre de trades par instrument) : Sharpe moyen %.2f [p5 %.2f, p95 %.2f], "
                    "rendement moyen %+.2f%% [p5 %+.2f, p95 %+.2f] ; la stratégie fait mieux que %.0f%% des tirages en Sharpe, %.0f%% en rendement\n",
                    random_runs, std::accumulate(rnd.sharpe.begin(), rnd.sharpe.end(), 0.0) / n,
                    quantile(rnd.sharpe, 0.05), quantile(rnd.sharpe, 0.95),
                    std::accumulate(rnd.ret_pct.begin(), rnd.ret_pct.end(), 0.0) / n, quantile(rnd.ret_pct, 0.05),
                    quantile(rnd.ret_pct, 0.95), 100 * (1 - ge_s / n), 100 * (1 - ge_r / n));
        if (detail) {
            const auto bh = panel_buy_hold(panel, w);
            std::printf("    %-11s %6s %5s %7s %8s %8s %8s %8s %8s %7s %6s %6s %7s %7s %6s\n", "instrument", "trades", "win%",
                        "Sharpe", "net%", "brut%", "frais%", "fund%", "long%", "short%", "beta", "t(a)", "B&H%", "coût%mrg",
                        "bat%");
            for (size_t i = 0; i < panel.size(); ++i) {
                const InstRun& ir = pr.inst[i];
                if (ir.window.empty()) continue;
                const Metrics im = ir.res.metrics();
                const double e0 = ir.res.start_equity;
                double lp = 0, sp = 0, lev = 0;
                for (const auto& t : ir.res.trades) {
                    (t.side == Side::Long ? lp : sp) += t.pnl;
                    lev += t.leverage;
                }
                lev = ir.res.trades.empty() ? 0 : lev / static_cast<double>(ir.res.trades.size());
                const BetaStats ib = beta_regression(ir.res, ir.window);
                const Config& c = panel[i].cfg;
                const double fee = c.taker_fee >= 0 ? c.taker_fee : c.inst_taker_fee;
                const double rt_bps = (2 * fee + c.default_spread_pct + 2 * c.slippage_pct) * 1e4; // aller-retour, du notionnel
                double beat = 0;
                for (double p : rnd.inst_pnl[i]) beat += p <= ir.res.end_equity - e0 ? 1 : 0;
                std::printf("    %-11s %6ld %5.1f %7.2f %8.2f %8.2f %8.2f %8.3f %8.2f %7.2f %6.2f %6.2f %7.2f %7.2f %6.0f\n",
                            ir.symbol.c_str(), im.trades, im.win_rate * 100, im.sharpe, im.return_pct, 100 * im.gross_pnl / e0,
                            100 * im.fees / e0, 100 * im.funding / e0, 100 * lp / e0, 100 * sp / e0, ib.beta, ib.t_alpha,
                            bh[i].metrics().return_pct, rt_bps / 100.0 * lev, 100 * beat / static_cast<double>(rnd.inst_pnl[i].size()));
            }
            std::puts("    (coût%mrg = coût aller-retour du modèle, en % de la marge : bps du notionnel x levier de position moyen)");
        }
    }
    return pr;
}

int main(int argc, char** argv) {
    std::vector<std::string> configs, sets, grids, symbols;
    std::string mode, data_dir = "data", out = "results/panel", params_file, train_end, val_end;
    int k = 5, min_trades = 100, min_val_trades = 30, random_runs = 100;
    double warmup_days = 2;
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
        if (a == "--mode") mode = need(i);
        else if (a == "--symbols") symbols = split_csv(need(i));
        else if (a == "--data-dir") data_dir = need(i);
        else if (a == "--config") configs.push_back(need(i));
        else if (a == "--set") sets.push_back(need(i));
        else if (a == "--grid") grids.push_back(need(i));
        else if (a == "--train-end") train_end = need(i);
        else if (a == "--val-end") val_end = need(i);
        else if (a == "--warmup-days") warmup_days = std::atof(need(i));
        else if (a == "--out-prefix") out = need(i);
        else if (a == "--params") params_file = need(i);
        else if (a == "--k") k = std::atoi(need(i));
        else if (a == "--min-trades") min_trades = std::atoi(need(i));
        else if (a == "--min-val-trades") min_val_trades = std::atoi(need(i));
        else if (a == "--random-runs") random_runs = std::atoi(need(i));
        else if (a == "--threads") threads = static_cast<unsigned>(std::atoi(need(i)));
        else if (a == "--seed") seed = std::strtoull(need(i), nullptr, 10);
        else if (a == "--help" || a == "-h") { usage(); return 0; }
        else { std::fprintf(stderr, "option inconnue : %s\n", a.c_str()); usage(); return 2; }
    }
    if ((mode != "search" && mode != "leverage") || symbols.empty() || train_end.empty() || val_end.empty()) {
        usage();
        return 2;
    }
    if (configs.empty()) configs.push_back("config.yaml");
    else configs.insert(configs.begin(), "config.yaml");

    try {
        const std::vector<PanelInstrument> panel = load_panel(symbols, data_dir, configs, sets);
        const double t_train = parse_date(train_end), t_val = parse_date(val_end);
        const double warm = warmup_days * 86400;
        double first = 1e18;
        for (const auto& p : panel) first = std::min(first, p.candles.front().ts);
        const Window w_train{first, t_train, 0}, w_val{t_train, t_val, warm}, w_test{t_val, 1e18, warm};
        std::printf("Panel de %zu instruments : %s\n", panel.size(), [&] {
            std::string s;
            for (const auto& p : panel) s += (s.empty() ? "" : ", ") + p.symbol;
            return s;
        }().c_str());
        std::printf("Fenêtres UTC : train %s -> %s | validation %s -> %s | test %s -> fin des données\n",
                    day(first).c_str(), day(t_train).c_str(), day(t_train).c_str(), day(t_val).c_str(), day(t_val).c_str());

        if (mode == "search") {
            if (grids.empty()) { usage(); return 2; }
            std::vector<Axis> axes;
            for (const auto& g : grids) axes.push_back(parse_axis(g));
            const size_t npts = grid_size(axes);
            std::printf("Sweep sur train seulement : %zu points testés (un seul jeu de paramètres pour tous les instruments). "
                        "Le meilleur d'une grille large est biaisé à la hausse ; seuls la validation puis le test comptent.\n", npts);

            struct Row { Params p; Metrics m; int npos, nact; size_t hours; };
            std::vector<Row> rows(npts);
            parallel_for(npts, threads, [&](size_t idx) {
                Params p;
                size_t rest = idx;
                p.resize(axes.size());
                for (size_t a = axes.size(); a-- > 0;) {
                    p[a] = {axes[a].key, axes[a].values[rest % axes[a].values.size()]};
                    rest /= axes[a].values.size();
                }
                const PanelRun pr = run_panel(panel, p, w_train, 1);
                rows[idx] = Row{p, pr.pm, pr.n_positive, pr.n_active, pr.hour_ts.size()};
            });
            {
                std::ofstream f(out + "_train_sweep.csv");
                for (const auto& a : axes) f << a.key << ',';
                f << "trades,sharpe,return_pct,max_dd_pct,n_positive,n_active,hours\n";
                f.precision(10);
                for (const Row& r : rows) {
                    for (const auto& kv : r.p) f << kv.second << ',';
                    f << r.m.trades << ',' << r.m.sharpe << ',' << r.m.return_pct << ',' << r.m.max_drawdown_pct << ','
                      << r.npos << ',' << r.nact << ',' << r.hours << '\n';
                }
            }
            std::vector<const Row*> ranked;
            long positive = 0;
            for (const Row& r : rows) {
                positive += r.m.sharpe > 0 ? 1 : 0;
                if (r.m.trades >= min_trades) ranked.push_back(&r);
            }
            std::sort(ranked.begin(), ranked.end(), [](const Row* a, const Row* b) { return a->m.sharpe > b->m.sharpe; });
            std::printf("Train : %zu/%zu points éligibles (>= %d trades au total), %ld avec Sharpe de portefeuille > 0.\n",
                        ranked.size(), npts, min_trades, positive);
            if (ranked.empty()) { std::puts("Aucun point éligible : arrêt, validation et test non touchés."); return 0; }
            if (static_cast<int>(ranked.size()) > k) ranked.resize(static_cast<size_t>(k));

            std::puts("\nTop K de train confirmés sur validation (Sharpe de portefeuille) :");
            const Row* best = nullptr;
            double best_val = -1e18;
            for (const Row* r : ranked) {
                const PanelRun v = run_panel(panel, r->p, w_val, threads);
                std::printf("  %-90s train %6.2f (%+7.2f%%, %4ld tr) | val %6.2f (%+7.2f%%, %4ld tr, %d/%d pos.)\n",
                            params_str(r->p).c_str(), r->m.sharpe, r->m.return_pct, r->m.trades, v.pm.sharpe,
                            v.pm.return_pct, v.pm.trades, v.n_positive, v.n_active);
                if (v.pm.trades >= min_val_trades && v.pm.sharpe > best_val) {
                    best_val = v.pm.sharpe;
                    best = r;
                }
            }
            std::printf("Points évalués : %zu (train) + %zu (validation) + 1 (test, une seule fois).\n", npts, ranked.size());
            if (!best) {
                std::printf("Aucun des K n'a >= %d trades en validation : pas de point final, test non touché.\n", min_val_trades);
                return 0;
            }
            std::printf("\nPoint final (meilleur Sharpe de validation parmi les K) : %s\n", params_str(best->p).c_str());
            {
                std::ofstream f(out + "_final.txt");
                for (const auto& kv : best->p) f << kv.first << '=' << kv.second << '\n';
            }
            const PanelRun tr = report_window("TRAIN (in-sample)", panel, best->p, w_train, random_runs, seed, threads, false);
            write_returns(out + "_returns_train.csv", tr);
            const PanelRun va = report_window("VALIDATION", panel, best->p, w_val, random_runs, seed, threads, false);
            write_returns(out + "_returns_val.csv", va);
            const PanelRun te = report_window("TEST (hors échantillon, évalué une seule fois pour cette famille)", panel, best->p,
                                              w_test, random_runs, seed, threads, true);
            write_returns(out + "_returns_test.csv", te);
            std::printf("\nRÉSULTAT HORS ÉCHANTILLON : Sharpe de portefeuille %.2f, rendement net %+.2f%%, %d/%d instruments positifs\n",
                        te.pm.sharpe, te.pm.return_pct, te.n_positive, te.n_active);
            return 0;
        }

        // mode leverage
        Params base;
        if (!params_file.empty()) {
            std::ifstream f(params_file);
            if (!f) { std::fprintf(stderr, "params illisible : %s\n", params_file.c_str()); return 1; }
            std::string line;
            while (std::getline(f, line)) {
                const size_t eq = line.find('=');
                if (eq != std::string::npos) base.emplace_back(line.substr(0, eq), std::atof(line.c_str() + eq + 1));
            }
        }
        std::printf("Paramètres de signal et de sortie : %s\n", params_str(base).c_str());
        struct Level { std::string name; Params extra; };
        const Params no_caps = {{"sizing_mode", 1}, {"kelly_enabled", 0}, {"max_net_exposure_pct", 0}, {"max_gross_exposure_pct", 0}};
        std::vector<Level> levels;
        levels.push_back({"risque 1%/SL (mode 0)", {}});
        for (double m : {1.0, 2.0, 5.0, 10.0}) {
            Params p = no_caps;
            p.insert(p.end(), {{"account_leverage", m}, {"apply_liq_cap", 0}});
            char b[32];
            std::snprintf(b, sizeof b, "levier fixe %gx", m);
            levels.push_back({b, p});
        }
        for (double v : {0.10, 0.20, 0.40}) {
            Params p = no_caps;
            p.insert(p.end(), {{"vol_target_annual", v}, {"apply_liq_cap", 1}});
            char b[40];
            std::snprintf(b, sizeof b, "vol cible %.0f%% (cap liq)", v * 100);
            levels.push_back({b, p});
        }
        const Window* wins[2] = {&w_val, &w_test};
        const char* wnames[2] = {"VALIDATION", "TEST"};
        for (int wi = 0; wi < 2; ++wi) {
            std::printf("\n== Courbe de levier, %s (%s -> fin)\n", wnames[wi], day(wins[wi]->start).c_str());
            std::printf("  %-26s %7s %9s %8s %6s %7s %6s %9s %9s\n", "niveau", "Sharpe", "net%", "maxDD%", "liq.", "liqgrd", "trades",
                        "lev.pos.", "coût%mrg");
            for (const Level& lv : levels) {
                Params p = base;
                p.insert(p.end(), lv.extra.begin(), lv.extra.end());
                const PanelRun pr = run_panel(panel, p, *wins[wi], threads);
                double lev = 0;
                for (const auto& t : pr.port.trades) lev += t.leverage;
                lev = pr.port.trades.empty() ? 0 : lev / static_cast<double>(pr.port.trades.size());
                const Config& c = panel[0].cfg;
                const double rt_bps = (2 * (c.taker_fee >= 0 ? c.taker_fee : c.inst_taker_fee) + c.default_spread_pct + 2 * c.slippage_pct) * 1e4;
                std::printf("  %-26s %7.2f %+9.2f %8.2f %6ld %7ld %6ld %9.2f %9.2f\n", lv.name.c_str(), pr.pm.sharpe, pr.pm.return_pct,
                            pr.pm.max_drawdown_pct, pr.liquidations, pr.liq_guards, pr.pm.trades, lev, rt_bps / 100.0 * lev);
                if (lv.name == "levier fixe 1x") write_returns(out + "_lev1_" + (wi ? "test" : "val") + ".csv", pr);
            }
        }
        std::puts("\n(coût%mrg : coût aller-retour du modèle, en bps du notionnel, multiplié par le levier de position moyen, en % de la marge)");
    } catch (const std::exception& e) {
        std::fprintf(stderr, "erreur : %s\n", e.what());
        return 1;
    }
    return 0;
}
