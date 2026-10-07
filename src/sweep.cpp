#include "perp/sweep.hpp"

#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <exception>
#include <mutex>
#include <stdexcept>
#include <thread>

namespace perp {

static double to_num(const std::string& s, const std::string& spec) {
    char* end = nullptr;
    const double v = std::strtod(s.c_str(), &end);
    if (s.empty() || *end != '\0') throw std::runtime_error("valeur illisible dans '" + spec + "'");
    return v;
}

Axis parse_axis(const std::string& spec) {
    const size_t eq = spec.find('=');
    if (eq == std::string::npos || eq == 0) throw std::runtime_error("grille : cle=valeurs attendu : " + spec);
    Axis a;
    a.key = spec.substr(0, eq);
    Config probe;
    if (!probe.set(a.key, 0)) throw std::runtime_error("grille : cle inconnue : " + a.key);
    const std::string vals = spec.substr(eq + 1);
    if (vals.find(':') != std::string::npos) {
        const size_t c1 = vals.find(':'), c2 = vals.find(':', c1 + 1);
        if (c2 == std::string::npos) throw std::runtime_error("grille : debut:fin:pas attendu : " + spec);
        const double lo = to_num(vals.substr(0, c1), spec), hi = to_num(vals.substr(c1 + 1, c2 - c1 - 1), spec),
                     step = to_num(vals.substr(c2 + 1), spec);
        if (step <= 0 || hi < lo) throw std::runtime_error("grille : pas > 0 et fin >= debut : " + spec);
        const long n = static_cast<long>(std::floor((hi - lo) / step + 1e-9)) + 1;
        if (n > 100000) throw std::runtime_error("grille : trop de valeurs : " + spec);
        for (long i = 0; i < n; ++i) a.values.push_back(lo + static_cast<double>(i) * step); // pas d'accumulation
    } else {
        size_t pos = 0;
        while (pos <= vals.size()) {
            const size_t comma = vals.find(',', pos);
            const std::string tok = vals.substr(pos, comma == std::string::npos ? std::string::npos : comma - pos);
            a.values.push_back(to_num(tok, spec));
            if (comma == std::string::npos) break;
            pos = comma + 1;
        }
    }
    return a;
}

size_t grid_size(const std::vector<Axis>& axes) {
    size_t n = 1;
    for (const auto& a : axes) {
        if (a.values.empty()) throw std::runtime_error("axe vide : " + a.key);
        if (n > 100'000'000 / a.values.size()) throw std::runtime_error("grille trop grande (> 1e8 points)");
        n *= a.values.size();
    }
    return n;
}

void parallel_for(size_t n, unsigned threads, const std::function<void(size_t)>& fn) {
    if (n == 0) return;
    if (threads == 0) threads = std::max(1u, std::thread::hardware_concurrency());
    threads = static_cast<unsigned>(std::min<size_t>(threads, n));
    std::atomic<size_t> next{0};
    std::exception_ptr error;
    std::mutex error_mu;
    auto worker = [&]() {
        for (;;) {
            const size_t idx = next.fetch_add(1);
            if (idx >= n) return;
            try {
                fn(idx);
            } catch (...) {
                std::lock_guard<std::mutex> lk(error_mu);
                if (!error) error = std::current_exception();
                next = n; // on arrête les autres
                return;
            }
        }
    };
    std::vector<std::thread> pool;
    for (unsigned t = 1; t < threads; ++t) pool.emplace_back(worker);
    worker(); // le thread appelant travaille aussi
    for (auto& t : pool) t.join();
    if (error) std::rethrow_exception(error);
}

std::vector<SweepRow> run_sweep(const Config& base, const std::vector<Axis>& axes,
                                const std::vector<Candle>& candles, int interval_s, unsigned threads,
                                const RunOptions& opt) {
    std::vector<SweepRow> rows(grid_size(axes));
    parallel_for(rows.size(), threads, [&](size_t idx) {
        Config cfg = base;
        SweepRow& row = rows[idx];
        size_t rest = idx;
        row.params.assign(axes.size(), 0.0);
        for (size_t k = axes.size(); k-- > 0;) { // dernier axe = chiffre de poids faible
            row.params[k] = axes[k].values[rest % axes[k].values.size()];
            rest /= axes[k].values.size();
            cfg.set(axes[k].key, row.params[k]);
        }
        row.m = run_backtest(cfg, candles, interval_s, opt).metrics();
    });
    return rows;
}

static const char* const kReasons[] = {"stop_loss",    "stop_loss_emergency", "take_profit",
                                       "trailing_stop", "time_exit",          "max_hold",
                                       "liq_guard",     "liquidation",        "end_of_test"};

void write_sweep_csv(std::ostream& os, const std::vector<Axis>& axes, const std::vector<SweepRow>& rows) {
    for (const auto& a : axes) os << a.key << ',';
    os << "trades,win_rate,pnl,return_pct,sharpe,max_drawdown_pct,profit_factor,avg_hold_s,fees,funding,"
          "liquidations,gross_pnl,trade_t_stat,halt_breached";
    for (const char* r : kReasons) os << ",pnl_" << r;
    os << '\n';
    char buf[64];
    auto num = [&](double v) {
        if (std::isinf(v)) std::snprintf(buf, sizeof buf, "inf");
        else std::snprintf(buf, sizeof buf, "%.10g", v);
        os << buf;
    };
    for (const auto& row : rows) {
        for (double p : row.params) { num(p); os << ','; }
        const Metrics& m = row.m;
        os << m.trades << ',';
        for (double v : {m.win_rate, m.pnl, m.return_pct, m.sharpe, m.max_drawdown_pct, m.profit_factor,
                         m.avg_hold_s, m.fees, m.funding}) {
            num(v);
            os << ',';
        }
        os << m.liquidations << ',';
        num(m.gross_pnl);
        os << ',';
        num(m.trade_t_stat);
        os << ',' << (m.halt_breached ? 1 : 0);
        for (const char* r : kReasons) {
            auto it = m.by_reason.find(r);
            os << ',';
            num(it == m.by_reason.end() ? 0.0 : it->second.pnl);
        }
        os << '\n';
    }
}

} // namespace perp
