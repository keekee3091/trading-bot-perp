// perp_mm : backtest passif de market making sur l'historique de trades, protocole hors échantillon.
//
//   --mode search    grille fixée sur TRAIN (borne conservatrice décisive), top K confirmés sur VALIDATION,
//                    point final évalué UNE fois sur TEST, avec les quatre bornes de fill, la baseline
//                    de deltas aléatoires, les métriques par instrument et le verdict de la règle d'arrêt
//   --mode control   paramètres donnés (--params), instruments quelconques, fenêtre libre : contrôle
//                    (instruments à spread étroit), sans sélection
//
// Un seul jeu de paramètres commun à tous les instruments. Les cinq bornes de fill sont toujours
// toutes rapportées ; la borne décisive est la conservatrice avec file d'attente supposée de 1000.
#include <algorithm>
#include <cmath>
#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <ctime>
#include <exception>
#include <fstream>
#include <map>
#include <numeric>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

#include "perp/mm.hpp"
#include "perp/panel.hpp"
#include "perp/sweep.hpp"

using namespace perp;

namespace {

struct InstInfo {
    std::string category;
    int price_decimals = 2;
    double max_leverage = 10, liq_fee = 0.005, min_notional = 10;
};

struct Variant {
    const char* name;
    int model;
    double queue;
};
const Variant kVariants[4] = {{"optimiste", 0, 0}, {"conserv. q=0", 1, 0}, {"conserv. q=1000", 1, 1000}, {"conserv. q=5000", 1, 5000}};
constexpr int kDecisive = 2;
const double kDeltas[5] = {1, 2, 3, 5, 8};

std::string fmt(const char* f, ...) {
    char b[1024];
    va_list ap;
    va_start(ap, f);
    std::vsnprintf(b, sizeof b, f, ap);
    va_end(ap);
    return b;
}

std::vector<std::string> split_csv(const std::string& s) {
    std::vector<std::string> out;
    std::stringstream ss(s);
    std::string t;
    while (std::getline(ss, t, ',')) {
        while (!t.empty() && (t.back() == '\r' || t.back() == ' ')) t.pop_back();
        if (!t.empty()) out.push_back(t);
    }
    return out;
}

std::map<std::string, InstInfo> load_instruments(const std::string& path) {
    std::ifstream f(path);
    if (!f) throw std::runtime_error("instruments.csv illisible : " + path + " (python tools/fetch_trades.py --instruments-only)");
    std::string line;
    std::getline(f, line);
    std::map<std::string, InstInfo> out;
    while (std::getline(f, line)) {
        const auto r = split_csv(line);
        if (r.size() < 6) continue;
        InstInfo i;
        i.category = r[1];
        i.price_decimals = std::atoi(r[2].c_str());
        i.max_leverage = std::atof(r[3].c_str());
        i.liq_fee = std::atof(r[4].c_str());
        i.min_notional = std::atof(r[5].c_str());
        out[r[0]] = i;
    }
    return out;
}

MmData load_data(const std::string& sym, const std::string& dir, const std::map<std::string, InstInfo>& info, bool long_is_buyer) {
    auto it = info.find(sym);
    if (it == info.end()) throw std::runtime_error("instrument absent de instruments.csv : " + sym);
    MmData d;
    d.symbol = sym;
    d.category = it->second.category;
    d.inst.symbol = sym;
    d.inst.max_leverage = it->second.max_leverage;
    d.inst.liquidation_fee = it->second.liq_fee;
    d.inst.min_notional = it->second.min_notional;
    d.tick = std::pow(10.0, -it->second.price_decimals);
    d.trades = load_trades_csv(dir + "/" + sym + "_trades.csv", long_is_buyer);
    d.mark = load_mark_csv(dir + "/" + sym + "_mark_1m.csv");
    d.funding = load_funding_csv(dir + "/" + sym + "_funding.csv");
    if (d.trades.empty() || d.mark.empty()) throw std::runtime_error("pas de trades ou de mark : " + sym);
    return d;
}

bool set_param(MmParams& p, const std::string& k, double v) {
    if (k == "delta_bps") p.delta_bps = v;
    else if (k == "leverage") p.leverage = v;
    else if (k == "inv_frac") p.inv_frac = v;
    else if (k == "order_frac") p.order_frac = v;
    else if (k == "skew_frac") p.skew_frac = v;
    else if (k == "requote_s") p.requote_s = v;
    else if (k == "equity") p.equity = v;
    else if (k == "maker_fee_bps") p.maker_fee_bps = v;
    else if (k == "taker_fee_bps") p.taker_fee_bps = v;
    else if (k == "slippage_bps") p.slippage_bps = v;
    else if (k == "exit_to_frac") p.exit_to_frac = v;
    else return false;
    return true;
}

using KV = std::vector<std::pair<std::string, double>>;

std::string kv_str(const KV& kv) {
    std::string s;
    for (size_t i = 0; i < kv.size(); ++i) s += fmt("%s%s=%g", i ? " " : "", kv[i].first.c_str(), kv[i].second);
    return s;
}

struct Win {
    double t0 = 0, t1 = 0;
};

// Exécute tous les instruments sur la fenêtre avec une variante de fill.
std::vector<MmResult> run_all(const std::vector<MmData>& data, const std::vector<double>& exit_half, const KV& kv,
                              const Variant& v, const Win& w, unsigned threads, bool random_delta = false,
                              std::uint64_t seed = 1) {
    std::vector<MmResult> out(data.size());
    parallel_for(data.size(), threads, [&](size_t i) {
        MmParams p;
        for (const auto& e : kv)
            if (!set_param(p, e.first, e.second)) throw std::runtime_error("parametre inconnu : " + e.first);
        p.fill_model = v.model;
        p.queue_ahead_notional = v.queue;
        p.exit_half_spread_bps = exit_half[i];
        p.random_delta = random_delta;
        p.random_deltas.assign(kDeltas, kDeltas + 5);
        p.seed = seed + 7919 * i;
        const double t0 = std::max(w.t0, std::ceil(data[i].trades.front().ts / 60.0) * 60.0);
        const double t1 = std::min(w.t1, data[i].trades.back().ts + 1.0);
        if (t1 <= t0) {
            out[i].start_equity = out[i].end_equity = p.equity;
            return;
        }
        out[i] = run_mm(data[i], p, t0, t1);
    });
    return out;
}

struct Port {
    double net_pct = 0;     // moyenne sur les instruments du rendement net en % de l'equity initiale
    int n_pos = 0, n = 0;
    double sharpe = 0, t = 0;
    int n_days = 0;
    std::vector<double> daily;
};

Port aggregate(const std::vector<MmResult>& res) {
    Port p;
    p.n = static_cast<int>(res.size());
    std::map<long, std::pair<double, int>> day;
    for (const MmResult& r : res) {
        const double pct = r.start_equity > 0 ? 100.0 * (r.end_equity - r.start_equity) / r.start_equity : 0.0;
        p.net_pct += pct / static_cast<double>(res.size());
        p.n_pos += pct > 0 ? 1 : 0;
        for (const auto& kv : daily_returns(r)) {
            day[kv.first].first += kv.second;
            day[kv.first].second += 1;
        }
    }
    for (const auto& kv : day) p.daily.push_back(kv.second.first / static_cast<double>(kv.second.second));
    p.n_days = static_cast<int>(p.daily.size());
    if (p.daily.size() >= 3) {
        double mu = 0;
        for (double x : p.daily) mu += x;
        mu /= static_cast<double>(p.daily.size());
        double v = 0;
        for (double x : p.daily) v += (x - mu) * (x - mu);
        const double sd = std::sqrt(v / static_cast<double>(p.daily.size() - 1));
        p.sharpe = sd > 0 ? mu / sd * std::sqrt(365.0) : 0.0;
        p.t = sd > 0 ? mu / (sd / std::sqrt(static_cast<double>(p.daily.size()))) : 0.0;
    }
    return p;
}

double normal_cdf(double x) { return 0.5 * std::erfc(-x / std::sqrt(2.0)); }

std::string day_str(double ts) {
    char b[16];
    const std::time_t t = static_cast<std::time_t>(ts);
    std::strftime(b, sizeof b, "%Y-%m-%d", std::gmtime(&t));
    return b;
}

double parse_date_utc(const std::string& s) { return parse_date(s); }

std::string read_file(const std::string& p) {
    std::ifstream f(p);
    std::stringstream ss;
    ss << f.rdbuf();
    return ss.str();
}

// ── rapport d'une fenêtre ─────────────────────────────────────────────────

struct Pooled {
    long n[4][2] = {};      // [horizon][côté]
    double sum[4][2] = {};
    long nm[2][2] = {};
    double summ[2][2] = {};
};

void pool(Pooled& P, const MmMetrics& m) {
    const SideStats* sides[2] = {&m.buy, &m.sell};
    for (int s = 0; s < 2; ++s) {
        for (int k = 0; k < 4; ++k) {
            P.n[k][s] += sides[s]->trade_proxy[k].n;
            P.sum[k][s] += sides[s]->trade_proxy[k].mean_bps * static_cast<double>(sides[s]->trade_proxy[k].n);
        }
        for (int k = 0; k < 2; ++k) {
            P.nm[k][s] += sides[s]->mark[k].n;
            P.summ[k][s] += sides[s]->mark[k].mean_bps * static_cast<double>(sides[s]->mark[k].n);
        }
    }
}

std::string markout_line(const Pooled& P, const char* label) {
    auto g = [](double s, long n) { return n ? s / static_cast<double>(n) : std::nan(""); };
    std::string out = fmt("    markouts %s, mesurés sur le mid proxy des trades (bps, positif = favorable ; achat/vente) :", label);
    const char* hn[4] = {"1 s", "10 s", "60 s", "5 min"};
    for (int k = 0; k < 4; ++k) out += fmt(" %s %+.2f/%+.2f (n=%ld/%ld);", hn[k], g(P.sum[k][0], P.n[k][0]), g(P.sum[k][1], P.n[k][1]), P.n[k][0], P.n[k][1]);
    out += fmt("\n    markouts %s, sur le mark connu à t+h : 60 s %+.2f/%+.2f ; 5 min %+.2f/%+.2f\n", label, g(P.summ[0][0], P.nm[0][0]),
               g(P.summ[0][1], P.nm[0][1]), g(P.summ[1][0], P.nm[1][0]), g(P.summ[1][1], P.nm[1][1]));
    return out;
}

} // namespace

int main(int argc, char** argv) {
    std::string mode, hist = "data/hist", out_path = "results/mm_backtest_report.txt", params_file;
    std::string train_end, val_end, from_date, to_date;
    std::vector<std::string> symbols;
    int k = 3, random_runs = 50, long_is_buyer = -1;
    unsigned threads = 0;
    unsigned long long seed = 1;
    std::vector<std::string> axes_specs;
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
        else if (a == "--hist-dir") hist = need(i);
        else if (a == "--long-is-buyer") long_is_buyer = std::atoi(need(i));
        else if (a == "--train-end") train_end = need(i);
        else if (a == "--val-end") val_end = need(i);
        else if (a == "--from") from_date = need(i);
        else if (a == "--to") to_date = need(i);
        else if (a == "--grid") axes_specs.push_back(need(i));
        else if (a == "--params") params_file = need(i);
        else if (a == "--k") k = std::atoi(need(i));
        else if (a == "--random-runs") random_runs = std::atoi(need(i));
        else if (a == "--threads") threads = static_cast<unsigned>(std::atoi(need(i)));
        else if (a == "--seed") seed = std::strtoull(need(i), nullptr, 10);
        else if (a == "--out") out_path = need(i);
        else { std::fprintf(stderr, "option inconnue : %s\n", a.c_str()); return 2; }
    }
    if ((mode != "search" && mode != "control") || symbols.empty() || long_is_buyer < 0) {
        std::puts("usage : perp_mm --mode search|control --symbols A,B --long-is-buyer 1|0 [--hist-dir data/hist]\n"
                  "  search : --grid cle=v1,v2 (répétable) --train-end DATE --val-end DATE [--k 3] [--random-runs 50]\n"
                  "  control : --params fichier --from DATE [--to DATE]\n"
                  "  commun : --threads N --seed S --out results/mm_backtest_report.txt\n"
                  "--long-is-buyer : 1 si side=long désigne l'agresseur acheteur (voir tools/side_semantics.py)");
        return 2;
    }
    try {
        const auto info = load_instruments(hist + "/instruments.csv");
        std::vector<MmData> data;
        for (const auto& s : symbols) data.push_back(load_data(s, hist, info, long_is_buyer == 1));
        if (mode == "search" && !to_date.empty()) { // coupe les données (test de plomberie hors fenêtre de test réelle)
            const double cut = parse_date_utc(to_date);
            for (auto& d : data) {
                d.trades.erase(std::remove_if(d.trades.begin(), d.trades.end(), [&](const Trade& t) { return t.ts >= cut; }), d.trades.end());
                if (d.trades.empty()) throw std::runtime_error("plus de trades après --to : " + d.symbol);
            }
        }
        std::string rep;
        auto P = [&](const std::string& s) { rep += s; };

        double data_t0 = 1e18, data_t1 = 0;
        for (const auto& d : data) {
            data_t0 = std::min(data_t0, d.trades.front().ts);
            data_t1 = std::max(data_t1, d.trades.back().ts);
        }

        if (mode == "control") {
            KV kv;
            {
                std::ifstream f(params_file);
                if (!f) throw std::runtime_error("params illisible : " + params_file);
                std::string line;
                while (std::getline(f, line)) {
                    const size_t eq = line.find('=');
                    if (eq != std::string::npos) kv.emplace_back(line.substr(0, eq), std::atof(line.c_str() + eq + 1));
                }
            }
            const double t0 = from_date.empty() ? data_t0 : parse_date_utc(from_date);
            const double t1 = to_date.empty() ? data_t1 + 1 : parse_date_utc(to_date);
            std::vector<double> exit_half(data.size(), 2.0);
            for (size_t i = 0; i < data.size(); ++i) {
                long nw = 0;
                const double es = effective_spread_bps(data[i], t0, t1, 60, -1, &nw);
                exit_half[i] = std::isnan(es) ? 2.0 : std::min(20.0, std::max(0.0, es / 2));
            }
            P(fmt("CONTRÔLE (sans sélection) : %s ; fenêtre %s -> %s ; paramètres %s\n", mode.c_str(), day_str(t0).c_str(), day_str(t1).c_str(), kv_str(kv).c_str()));
            P(fmt("%-11s %-9s %7s %10s %9s | %s\n", "instrument", "catég.", "spr.eff", "fills/j(opt)", "", "net % par borne : optimiste | q=0 | q=1000 | q=5000"));
            std::vector<std::vector<MmResult>> res;
            for (const Variant& v : kVariants) res.push_back(run_all(data, exit_half, kv, v, {t0, t1}, threads));
            for (size_t i = 0; i < data.size(); ++i) {
                const MmMetrics m = compute_metrics(res[0][i], data[i]);
                long nw = 0;
                const double es = effective_spread_bps(data[i], t0, t1, 60, -1, &nw);
                P(fmt("%-11s %-9s %7.2f %10.1f %9s |", data[i].symbol.c_str(), data[i].category.c_str(), es, m.fills_per_day, ""));
                for (int vi = 0; vi < 4; ++vi) P(fmt(" %+8.3f", res[static_cast<size_t>(vi)][i].start_equity > 0 ? 100.0 * (res[static_cast<size_t>(vi)][i].end_equity - res[static_cast<size_t>(vi)][i].start_equity) / res[static_cast<size_t>(vi)][i].start_equity : 0.0));
                P("\n");
            }
            for (int vi = 0; vi < 4; ++vi) {
                const Port pt = aggregate(res[static_cast<size_t>(vi)]);
                P(fmt("Portefeuille équipondéré, %-16s : net %+.3f %% (moyenne), %d/%d instruments positifs, Sharpe journalier %.2f (%d jours)\n", kVariants[vi].name, pt.net_pct, pt.n_pos, pt.n, pt.sharpe, pt.n_days));
            }
            std::fputs(rep.c_str(), stdout);
            std::ofstream f(out_path.empty() ? "results/mm_control.txt" : out_path + ".control.txt");
            f << rep;
            return 0;
        }

        // ── mode search ───────────────────────────────────────────────────
        if (axes_specs.empty() || train_end.empty() || val_end.empty()) { std::fputs("search : --grid, --train-end et --val-end requis\n", stderr); return 2; }
        struct Axis2 { std::string key; std::vector<double> v; };
        std::vector<Axis2> axes;
        for (const auto& spec : axes_specs) {
            const size_t eq = spec.find('=');
            Axis2 a;
            a.key = spec.substr(0, eq);
            for (const auto& t : split_csv(spec.substr(eq + 1))) a.v.push_back(std::atof(t.c_str()));
            MmParams probe;
            if (!set_param(probe, a.key, 0)) throw std::runtime_error("axe inconnu : " + a.key);
            axes.push_back(a);
        }
        size_t npts = 1;
        for (const auto& a : axes) npts *= a.v.size();
        const double t_train = parse_date_utc(train_end), t_val = parse_date_utc(val_end);
        const Win w_train{data_t0, t_train}, w_val{t_train, t_val}, w_test{t_val, data_t1 + 1};

        // coût de sortie taker : demi-spread effectif estimé sur le TRAIN (mesuré, par instrument)
        std::vector<double> exit_half(data.size(), 2.0);
        std::vector<double> es_train(data.size(), std::nan("")), es_in(data.size(), std::nan("")), es_off(data.size(), std::nan(""));
        for (size_t i = 0; i < data.size(); ++i) {
            long nw = 0;
            es_train[i] = effective_spread_bps(data[i], w_train.t0, w_train.t1, 60, -1, &nw);
            es_in[i] = effective_spread_bps(data[i], w_train.t0, w_train.t1, 60, 1, &nw);
            es_off[i] = effective_spread_bps(data[i], w_train.t0, w_train.t1, 60, 0, &nw);
            exit_half[i] = std::isnan(es_train[i]) ? 2.0 : std::min(20.0, std::max(0.0, es_train[i] / 2));
        }

        P("BACKTEST PASSIF DE MARKET MAKING SUR HISTORIQUE DE TRADES : RAPPORT\n");
        P(fmt("Généré le %s UTC. Univers : %zu instruments à spread large. Fenêtres : train %s -> %s, validation %s -> %s, test %s -> %s.\n",
              day_str(static_cast<double>(std::time(nullptr))).c_str(), data.size(), day_str(w_train.t0).c_str(), day_str(w_train.t1).c_str(),
              day_str(w_val.t0).c_str(), day_str(w_val.t1).c_str(), day_str(w_test.t0).c_str(), day_str(data_t1).c_str()));
        P("\n== 1. Données (mesuré)\n");
        P(read_file(hist + "/trades_summary.txt"));
        P("\n== 2. Sens du champ side (mesuré, tools/side_semantics.py)\n");
        {
            const std::string t = read_file("results/side_semantics.txt");
            P(t.empty() ? "(results/side_semantics.txt absent)\n" : t);
        }
        P(fmt("Mapping utilisé : side=long -> agresseur %s.\n", long_is_buyer == 1 ? "ACHETEUR" : "VENDEUR"));
        P("\n== 3. Ce qui est mesuré, supposé, non identifiable\n");
        P("[MESURÉ] trades (prix, quantité, horodatage ms, side, settlement), mark à 1 minute (dernier mark du bucket, connu à la fin du bucket, utilisé à cette date), funding horaire publié, frais documentés (maker 1.25 bps post-only, taker 4 bps), mmr = 0.5 / levier max, frais de liquidation, tick de prix, sessions (règles de calendrier).\n");
        P("[SUPPOSÉ] règle de fill (cinq bornes, ci-dessous) ; file d'attente devant nous (volume à consommer d'abord : 0, 1000 ou 5000 de notionnel selon la borne) ; prix d'une sortie taker = mark +- (demi-spread effectif estimé sur les trades du train + 2 bps de slippage) ; quotes recalculées toutes les 60 s (résolution du mark) et seulement alors ; ordres de taille fixe (25 % du plafond d'inventaire) ; impact nul de nos ordres sur le flux ; funding payé sur l'inventaire au mark.\n");
        P("[NON IDENTIFIABLE sans carnet historique] notre position réelle dans la file ; le vrai spread passé et sa dynamique (on n'a qu'un proxy : le spread effectif des trades) ; la profondeur ; le flux d'ordres annulés ; la qualité de notre fill face aux autres makers. Aucun historique de carnet n'existe (voir CLAUDE.md : aucun endpoint, le paramètre temporel de /v1/info/book est ignoré).\n");
        P("Les markouts à 1 s et 10 s utilisent un mid PROXY bâti sur les trades (moyenne du dernier prix d'achat agresseur et du dernier prix de vente agresseur dans les 60 s) : ce n'est pas le mid du carnet.\n");
        P("\n== 4. Protocole (pré-enregistré dans CLAUDE.md avant tout résultat)\n");
        P(fmt("Grille : %s, soit %zu points ; un seul jeu de paramètres pour tous les instruments. Sélection sur TRAIN par le rendement net moyen du portefeuille équipondéré (borne décisive : %s) ; top K = %d confirmés sur VALIDATION ; point final évalué UNE fois sur TEST. Tests : %zu points (train) + %d (validation) + 1 (test) ; correction pour tests multiples : Bonferroni, M = 5 évaluations de test d'une hypothèse d'edge dans le projet (3 + 1 + 1).\n",
              [&] { std::string s; for (const auto& a : axes) { s += a.key + "={"; for (size_t i = 0; i < a.v.size(); ++i) s += fmt("%s%g", i ? "," : "", a.v[i]); s += "} "; } return s; }().c_str(), npts, kVariants[kDecisive].name, k, npts, k));

        // grille sur train
        struct Row { KV kv; Port port[4]; };
        std::vector<Row> rows(npts);
        for (size_t idx = 0; idx < npts; ++idx) {
            size_t rest = idx;
            rows[idx].kv.resize(axes.size());
            for (size_t a = axes.size(); a-- > 0;) {
                rows[idx].kv[a] = {axes[a].key, axes[a].v[rest % axes[a].v.size()]};
                rest /= axes[a].v.size();
            }
        }
        for (size_t idx = 0; idx < npts; ++idx)
            for (int vi = 0; vi < 4; ++vi) rows[idx].port[vi] = aggregate(run_all(data, exit_half, rows[idx].kv, kVariants[vi], w_train, threads));
        {
            std::ofstream f("results/mm_train_grid.csv");
            for (const auto& a : axes) f << a.key << ',';
            f << "net_pct_opt,net_pct_q0,net_pct_q1000,net_pct_q5000,npos_q1000,sharpe_q1000\n";
            for (const Row& r : rows) {
                for (const auto& e : r.kv) f << e.second << ',';
                f << r.port[0].net_pct << ',' << r.port[1].net_pct << ',' << r.port[2].net_pct << ',' << r.port[3].net_pct << ',' << r.port[kDecisive].n_pos << ',' << r.port[kDecisive].sharpe << '\n';
            }
        }
        std::vector<const Row*> ranked;
        long pos_dec = 0, pos_opt = 0;
        for (const Row& r : rows) {
            ranked.push_back(&r);
            pos_dec += r.port[kDecisive].net_pct > 0 ? 1 : 0;
            pos_opt += r.port[0].net_pct > 0 ? 1 : 0;
        }
        std::sort(ranked.begin(), ranked.end(), [](const Row* a, const Row* b) { return a->port[kDecisive].net_pct > b->port[kDecisive].net_pct; });
        P("\n== 5. Sélection sur TRAIN\n");
        P(fmt("Points avec net moyen > 0 sur train : borne optimiste %ld/%zu, borne décisive (%s) %ld/%zu.\n", pos_opt, npts, kVariants[kDecisive].name, pos_dec, npts));
        P("Top K sur la borne décisive, puis les quatre bornes sur validation :\n");
        const Row* best = nullptr;
        double best_val = -1e18;
        const size_t kk = std::min<size_t>(static_cast<size_t>(k), ranked.size());
        for (size_t i = 0; i < kk; ++i) {
            const Row& r = *ranked[i];
            P(fmt("  %-44s train net %+7.3f%% (opt %+7.3f%%) | val :", kv_str(r.kv).c_str(), r.port[kDecisive].net_pct, r.port[0].net_pct));
            Port vp[4];
            for (int vi = 0; vi < 4; ++vi) {
                vp[vi] = aggregate(run_all(data, exit_half, r.kv, kVariants[vi], w_val, threads));
                P(fmt(" %s %+7.3f%%", vi == 0 ? "opt" : (vi == 1 ? "q0" : (vi == 2 ? "q1000" : "q5000")), vp[vi].net_pct));
            }
            P(fmt(" | %d/%d instruments positifs (q1000)\n", vp[kDecisive].n_pos, vp[kDecisive].n));
            if (vp[kDecisive].net_pct > best_val) {
                best_val = vp[kDecisive].net_pct;
                best = &r;
            }
        }
        if (!best) throw std::runtime_error("aucun point");
        P(fmt("Point final (meilleur net de validation sur la borne décisive) : %s\n", kv_str(best->kv).c_str()));
        {
            std::ofstream f("results/mm_final.txt");
            for (const auto& e : best->kv) f << e.first << '=' << e.second << '\n';
        }
        const KV fin = best->kv;

        // rapports par fenêtre
        struct WinRes { std::vector<MmResult> res[4]; Port port[4]; };
        auto eval = [&](const Win& w) {
            WinRes wr;
            for (int vi = 0; vi < 4; ++vi) {
                wr.res[vi] = run_all(data, exit_half, fin, kVariants[vi], w, threads);
                wr.port[vi] = aggregate(wr.res[vi]);
            }
            return wr;
        };
        const WinRes rt = eval(w_train), rv = eval(w_val), rtest = eval(w_test);
        P("\n== 6. Résultat du point final sur chaque fenêtre (net moyen en % de l'equity initiale, portefeuille équipondéré de sleeves de 1000)\n");
        P(fmt("%-10s | %s\n", "fenêtre", "optimiste | cons. q=0 | cons. q=1000 (décisive) | cons. q=5000   ; Sharpe journalier (jours) ; instruments positifs"));
        const char* wn[3] = {"train", "validation", "TEST"};
        const WinRes* wrs[3] = {&rt, &rv, &rtest};
        for (int wi = 0; wi < 3; ++wi) {
            P(fmt("%-10s |", wn[wi]));
            for (int vi = 0; vi < 4; ++vi) P(fmt(" %+9.3f%%", wrs[wi]->port[vi].net_pct));
            P(fmt("   ; Sharpe j. (q1000) %.2f (%d j) ; %d/%d | optimiste %d/%d\n", wrs[wi]->port[kDecisive].sharpe, wrs[wi]->port[kDecisive].n_days,
                  wrs[wi]->port[kDecisive].n_pos, wrs[wi]->port[kDecisive].n, wrs[wi]->port[0].n_pos, wrs[wi]->port[0].n));
        }

        // détail par instrument sur validation et test
        for (int wi = 1; wi < 3; ++wi) {
            const Win& w = wi == 1 ? w_val : w_test;
            const WinRes& wr = *wrs[wi];
            P(fmt("\n== 7.%d Détail par instrument, %s (%s -> %s)\n", wi, wn[wi], day_str(w.t0).c_str(), day_str(std::min(w.t1, data_t1)).c_str()));
            P(fmt("%-11s %-9s | %-6s %-6s %-6s %-6s | %7s %7s %7s %7s %7s | %6s %6s %6s | %6s %5s %5s %5s | %5s %7s %9s %9s\n", "instrument", "catég.", "opt%", "q0%", "q1000%", "q5000%",
                  "fills/j", "cap.bps", "exitcost", "#exit", "net$q1k", "DD%", "Sh.j", "pres%", "inv.m", "inv95", "@cap%", "spEff", "vol%", "seuil1%$", "notre7j$", "ses.in$"));
            Pooled pool_q, pool_o;
            for (size_t i = 0; i < data.size(); ++i) {
                const MmMetrics mq = compute_metrics(wr.res[kDecisive][i], data[i]);
                const MmMetrics mo = compute_metrics(wr.res[0][i], data[i]);
                pool(pool_q, mq);
                pool(pool_o, mo);
                auto pct = [&](int vi) { const MmResult& r = wr.res[vi][i]; return r.start_equity > 0 ? 100.0 * (r.end_equity - r.start_equity) / r.start_equity : 0.0; };
                long nw = 0;
                const double es = effective_spread_bps(data[i], w.t0, std::min(w.t1, data_t1 + 1), 60, -1, &nw);
                P(fmt("%-11s %-9s | %+6.2f %+6.2f %+6.2f %+6.2f | %7.1f %7.2f %7.3f %7ld %+7.2f | %6.2f %6.2f %6.1f | %6.2f %5.2f %5.1f %5.1f | %5.2f %7.2f %9.0f %9.0f\n",
                      data[i].symbol.c_str(), data[i].category.c_str(), pct(0), pct(1), pct(2), pct(3), mq.fills_per_day, mq.capture_bps, mq.exit_cost,
                      mq.exit_count, mq.net_pnl, mq.max_dd_pct, mq.daily_sharpe, 100 * mq.presence_frac, mq.inv_mean_abs, mq.inv_p95_abs,
                      100 * mq.inv_at_cap_share, es, 100 * mq.volume_share, mq.threshold_1pct_7d, mq.notional_per_day * 7, mq.in_session.pnl));
            }
            P("  (opt/q0/q1000/q5000 : net % par borne ; cap.bps : spread capturé vs mark à q1000 ; exitcost : coût des sorties taker en $ ; net$q1k : PnL net en $ ; DD% et Sh.j : drawdown max et Sharpe journalier ; pres% : temps avec deux quotes à moins de 20 bps du mark ; inv.m / inv95 : |inventaire| / plafond, moyenne et p95 ; @cap% : échantillons proches du plafond ; spEff : spread effectif estimé sur les trades, bps ; vol% : notre notionnel / volume total des trades de l'instrument ; seuil1%$ : 1 % du volume de trades sur 7 jours, en $ ; notre7j$ : notre notionnel exécuté ramené à 7 jours ; ses.in$ : PnL attribué aux heures de séance.)\n");
            P(markout_line(pool_q, "borne conservatrice q=1000, tous instruments"));
            P(markout_line(pool_o, "borne optimiste, tous instruments"));
            P("    markouts par instrument (borne q=1000, mid proxy des trades, bps ; achat/vente) : 1 s | 10 s | 60 s | 5 min | mark 5 min" + std::string(1, '\n'));
            for (size_t i = 0; i < data.size(); ++i) {
                const MmMetrics mq = compute_metrics(wr.res[kDecisive][i], data[i]);
                P(fmt("      %-11s fills achat/vente %ld/%ld :", data[i].symbol.c_str(), mq.buy.fills, mq.sell.fills));
                for (int h = 0; h < 4; ++h) P(fmt(" %+6.2f/%+6.2f |", mq.buy.trade_proxy[h].mean_bps, mq.sell.trade_proxy[h].mean_bps));
                P(fmt(" %+6.2f/%+6.2f", mq.buy.mark[1].mean_bps, mq.sell.mark[1].mean_bps) + std::string(1, '\n'));
            }
            // spread effectif séance / hors séance sur la fenêtre
            P("    spread effectif estimé (bps, médiane par fenêtre de 60 s ; séance / hors séance) : ");
            for (size_t i = 0; i < data.size(); ++i) {
                long n1 = 0, n0 = 0;
                const double e1 = effective_spread_bps(data[i], w.t0, std::min(w.t1, data_t1 + 1), 60, 1, &n1);
                const double e0 = effective_spread_bps(data[i], w.t0, std::min(w.t1, data_t1 + 1), 60, 0, &n0);
                P(fmt("%s %.1f/%.1f (n=%ld/%ld); ", data[i].symbol.c_str(), e1, e0, n1, n0));
            }
            P("\n");
            // séance / hors séance, PnL et fills (borne décisive)
            double fi = 0, fo = 0, pi_ = 0, po = 0, ci = 0, co = 0, ni = 0, no = 0;
            for (size_t i = 0; i < data.size(); ++i) {
                const MmMetrics mq = compute_metrics(wr.res[kDecisive][i], data[i]);
                fi += static_cast<double>(mq.in_session.fills);
                fo += static_cast<double>(mq.off_session.fills);
                pi_ += mq.in_session.pnl;
                po += mq.off_session.pnl;
                ci += mq.in_session.capture_bps * mq.in_session.notional;
                co += mq.off_session.capture_bps * mq.off_session.notional;
                ni += mq.in_session.notional;
                no += mq.off_session.notional;
            }
            P(fmt("    séance / hors séance (q1000, tous instruments) : fills %.0f / %.0f ; spread capturé %.2f / %.2f bps ; PnL net %+.2f / %+.2f $\n", fi, fo, ni > 0 ? ci / ni : 0.0,
                  no > 0 ? co / no : 0.0, pi_, po));
        }

        // 7.0 par delta : autres paramètres du point final, train et validation seulement
        P("\n== 7.0 Par delta (autres paramètres du point final), TRAIN et VALIDATION seulement : le test n'est évalué que pour le point final\n");
        P(fmt("%-7s %-12s | %8s %8s %8s %9s %9s %9s %9s\n", "delta", "fenêtre/borne", "fills/j", "cap.bps", "net%", "mo60 ach.", "mo60 vte", "exitcost$", "#exit"));
        for (double dl : kDeltas) {
            KV kvd = fin;
            for (auto& e : kvd)
                if (e.first == "delta_bps") e.second = dl;
            const Win* ws[2] = {&w_train, &w_val};
            const char* wnm[2] = {"train", "validation"};
            for (int wi = 0; wi < 2; ++wi)
                for (int vi : {0, kDecisive}) {
                    const auto res = run_all(data, exit_half, kvd, kVariants[vi], *ws[wi], threads);
                    double fills = 0, capn = 0, notional = 0, ec = 0;
                    long ne = 0;
                    Pooled pl;
                    for (size_t i = 0; i < data.size(); ++i) {
                        const MmMetrics m = compute_metrics(res[i], data[i]);
                        fills += m.fills_per_day / static_cast<double>(data.size());
                        capn += m.capture_bps * m.notional_per_day * m.days;
                        notional += m.notional_per_day * m.days;
                        ec += m.exit_cost;
                        ne += m.exit_count;
                        pool(pl, m);
                    }
                    const double mo_b = pl.n[2][0] ? pl.sum[2][0] / static_cast<double>(pl.n[2][0]) : std::nan("");
                    const double mo_s = pl.n[2][1] ? pl.sum[2][1] / static_cast<double>(pl.n[2][1]) : std::nan("");
                    P(fmt("%-7g %-6s %-5s | %8.1f %8.2f %+8.3f %+9.2f %+9.2f %9.3f %9ld\n", dl, wnm[wi], vi == 0 ? "opt" : "q1000", fills,
                          notional > 0 ? capn / notional : 0.0, aggregate(res).net_pct, mo_b, mo_s, ec, ne));
                }
        }

        // baseline : deltas aléatoires, même fréquence de requote
        P("\n== 8. Baseline : quotes à delta aléatoire (tirés dans {1,2,3,5,8} bps à chaque requote et chaque côté), même fréquence, mêmes règles, borne q=1000\n");
        for (int wi = 1; wi < 3; ++wi) {
            const Win& w = wi == 1 ? w_val : w_test;
            std::vector<double> nets(static_cast<size_t>(random_runs));
            parallel_for(nets.size(), threads, [&](size_t s) {
                nets[s] = aggregate(run_all(data, exit_half, fin, kVariants[kDecisive], w, 1, true, seed + 1000 * (s + 1))).net_pct;
            });
            std::sort(nets.begin(), nets.end());
            const double strat = wrs[wi]->port[kDecisive].net_pct;
            long ge = 0;
            for (double x : nets) ge += x >= strat ? 1 : 0;
            double mean = 0;
            for (double x : nets) mean += x / static_cast<double>(nets.size());
            P(fmt("  %-10s : stratégie %+.3f %% ; aléatoire (%d tirages) moyenne %+.3f %% [p5 %+.3f, p50 %+.3f, p95 %+.3f] ; la stratégie fait mieux que %.0f %% des tirages\n", wn[wi], strat,
                  random_runs, mean, nets[nets.size() * 5 / 100], nets[nets.size() / 2], nets[nets.size() * 95 / 100], 100.0 * (1.0 - static_cast<double>(ge) / static_cast<double>(nets.size()))));
        }

        // significativité et verdict
        const Port& dv = rv.port[kDecisive];
        const Port& dt = rtest.port[kDecisive];
        const double p_t = 1.0 - normal_cdf(dt.t);
        P("\n== 9. Significativité (test, borne décisive)\n");
        P(fmt("Rendement journalier du portefeuille : t = %.2f sur %d jours, p unilatérale %.4f, Bonferroni (M=5) : p x 5 = %.4f -> %s\n", dt.t, dt.n_days, p_t, std::min(1.0, 5 * p_t),
              5 * p_t < 0.05 ? "significatif" : "NON significatif"));
        // instruments positifs sur validation ET test (borne décisive)
        int both = 0;
        for (size_t i = 0; i < data.size(); ++i) {
            auto pc = [&](const MmResult& r) { return r.end_equity > r.start_equity; };
            if (pc(rv.res[kDecisive][i]) && pc(rtest.res[kDecisive][i])) ++both;
        }
        const bool dec_pos = dv.net_pct > 0 && dt.net_pct > 0;
        const bool opt_pos = rv.port[0].net_pct > 0 && rtest.port[0].net_pct > 0;
        P("\n== 10. VERDICT (règle d'arrêt)\n");
        P(fmt("Borne conservatrice décisive (q=1000) : validation %+.3f %%, test %+.3f %% ; instruments positifs sur validation ET test : %d/%zu. Borne optimiste : validation %+.3f %%, test %+.3f %%.\n",
              dv.net_pct, dt.net_pct, both, data.size(), rv.port[0].net_pct, rtest.port[0].net_pct));
        if (!dec_pos) {
            P(opt_pos ? "RÉSULTAT NON CONCLUANT : seule la borne optimiste est positive ; la borne conservatrice ne l'est pas sur validation et test. Ce n'est pas un succès. Aucun code d'exécution.\n"
                      : "CONCLUSION NÉGATIVE : le PnL net de la borne conservatrice n'est pas positif sur validation et test après frais, funding et sorties taker, et la borne optimiste ne l'est pas non plus. Aucun code d'exécution.\n");
        } else if (both < 5 || 5 * p_t >= 0.05) {
            P(fmt("POSITIF MAIS NON ROBUSTE : borne conservatrice positive en moyenne, mais %d instrument(s) positifs sur validation et test (< 5 exigés) ou test non significatif après Bonferroni. Résultat non concluant, aucun code d'exécution.\n", both));
        } else {
            P("POSITIF ET ROBUSTE selon les critères pré-enregistrés (borne conservatrice, >= 5 instruments, Bonferroni) : à confirmer sur du temps neuf avant tout développement d'exécution.\n");
        }
        P("Aucun gain de récompense de liquidité n'est estimé en dollars (paramètres non documentés : nombre de marchés actifs, fréquence des snapshots, volume maker total). 'pres%' donne seulement le temps de présence de nos quotes à moins de 20 bps du mark (proxy du mid).\n");

        std::fputs(rep.c_str(), stdout);
        std::ofstream f(out_path);
        f << rep;
    } catch (const std::exception& e) {
        std::fprintf(stderr, "erreur : %s\n", e.what());
        return 1;
    }
    return 0;
}
