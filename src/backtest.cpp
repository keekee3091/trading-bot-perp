#include "perp/backtest.hpp"

#include <algorithm>
#include <cctype>
#include <cmath>
#include <cstdio>
#include <fstream>
#include <limits>
#include <random>
#include <sstream>
#include <stdexcept>

#include "perp/bot.hpp"
#include "perp/exchange.hpp"
#include "perp/risk.hpp"

namespace perp {

// ── CSV ────────────────────────────────────────────────────────────────────

static std::vector<std::string> split(const std::string& line) {
    std::vector<std::string> out;
    std::string cur;
    std::istringstream ss(line);
    while (std::getline(ss, cur, ',')) {
        while (!cur.empty() && (cur.back() == '\r' || cur.back() == ' ')) cur.pop_back();
        out.push_back(cur);
    }
    return out;
}

std::vector<Candle> load_csv(const std::string& path) {
    std::ifstream f(path);
    if (!f) throw std::runtime_error("csv illisible : " + path);
    std::string line;
    if (!std::getline(f, line)) throw std::runtime_error("csv vide : " + path);
    int ix[5] = {-1, -1, -1, -1, -1};
    int session_ix = -1; // colonne facultative : 0 = hors session
    const char* names[5] = {"ts", "open", "high", "low", "close"};
    const auto head = split(line);
    for (size_t i = 0; i < head.size(); ++i) {
        std::string h = head[i];
        std::transform(h.begin(), h.end(), h.begin(), [](unsigned char ch) { return std::tolower(ch); });
        for (int k = 0; k < 5; ++k)
            if (h == names[k]) ix[k] = static_cast<int>(i);
        if (h == "session") session_ix = static_cast<int>(i);
    }
    for (int k = 0; k < 5; ++k)
        if (ix[k] < 0) throw std::runtime_error(std::string("colonne manquante : ") + names[k]);
    const int need = *std::max_element(ix, ix + 5);

    std::vector<Candle> out;
    while (std::getline(f, line)) {
        const auto row = split(line);
        if (static_cast<int>(row.size()) <= need) continue;
        try {
            double ts = std::stod(row[ix[0]]);
            if (ts > 1e11) ts /= 1000.0; // millisecondes
            Candle c{ts, std::stod(row[ix[1]]), std::stod(row[ix[2]]), std::stod(row[ix[3]]),
                     std::stod(row[ix[4]])};
            if (session_ix >= 0 && static_cast<int>(row.size()) > session_ix)
                c.session = std::stod(row[static_cast<size_t>(session_ix)]) != 0.0;
            if (c.o > 0 && c.h > 0 && c.l > 0 && c.c > 0 && c.h >= c.l && std::isfinite(c.c))
                out.push_back(c);
        } catch (const std::exception&) {
            continue; // ligne illisible : ignorée
        }
    }
    std::sort(out.begin(), out.end(), [](const Candle& a, const Candle& b) { return a.ts < b.ts; });
    out.erase(std::unique(out.begin(), out.end(),
                          [](const Candle& a, const Candle& b) { return a.ts == b.ts; }),
              out.end());
    return out;
}

std::vector<FundingPoint> load_funding_csv(const std::string& path) {
    std::ifstream f(path);
    if (!f) throw std::runtime_error("funding illisible : " + path);
    std::string line;
    std::getline(f, line); // en-tête
    std::vector<FundingPoint> out;
    while (std::getline(f, line)) {
        const auto row = split(line);
        if (row.size() < 2) continue;
        try {
            double ts = std::stod(row[0]);
            if (ts > 1e11) ts /= 1000.0;
            out.push_back({ts, std::stod(row[1])});
        } catch (const std::exception&) {
            continue;
        }
    }
    std::sort(out.begin(), out.end(), [](const FundingPoint& a, const FundingPoint& b) { return a.ts < b.ts; });
    return out;
}

// ── Synthétique ────────────────────────────────────────────────────────────

namespace {
// mt19937_64 est portable bit à bit, contrairement à std::normal_distribution.
struct Rng {
    std::mt19937_64 g;
    explicit Rng(std::uint64_t seed) : g(seed) {}
    double uniform() { return (static_cast<double>(g() >> 11) + 0.5) * (1.0 / 9007199254740992.0); }
    double gauss(double sd) {
        const double u1 = uniform(), u2 = uniform();
        return sd * std::sqrt(-2.0 * std::log(u1)) * std::cos(2.0 * 3.14159265358979323846 * u2);
    }
};
} // namespace

std::vector<Candle> synthetic(int n, int interval_s, double start, std::uint64_t seed) {
    Rng rng(seed);
    std::vector<Candle> out;
    out.reserve(static_cast<size_t>(std::max(n, 0)));
    double ts = 1'760'000'000.0, px = start;
    const double vol = 0.0006;
    double mu = 0.0;
    const double regimes[4] = {-1, 0, 0, 1};
    for (int i = 0; i < n; ++i) {
        if (i % 360 == 0) mu = regimes[static_cast<int>(rng.uniform() * 4) & 3] * 0.00015;
        double path[5] = {px, 0, 0, 0, 0};
        for (int k = 1; k < 5; ++k) path[k] = path[k - 1] * std::exp(mu / 4 + rng.gauss(vol / 2));
        const double c = path[4];
        out.push_back({ts, px, *std::max_element(path, path + 5), *std::min_element(path, path + 5), c});
        px = c;
        ts += interval_s;
    }
    return out;
}

std::array<Tick, 4> candle_ticks(const Candle& c, int interval_s, double funding_rate) {
    const double seq[4] = {c.o, c.c >= c.o ? c.l : c.h, c.c >= c.o ? c.h : c.l, c.c};
    const double step = interval_s / 4.0;
    std::array<Tick, 4> out;
    for (int k = 0; k < 4; ++k) {
        Tick& t = out[static_cast<size_t>(k)];
        t.ts = c.ts + k * step;
        t.mark = t.index = seq[k];
        t.funding_rate = funding_rate;
        t.tradable = c.session;
    }
    return out;
}

// ── Métriques ──────────────────────────────────────────────────────────────

Metrics BacktestResult::metrics() const {
    Metrics m;
    m.trades = static_cast<long>(trades.size());
    double win_sum = 0, loss_sum = 0, hold = 0;
    long wins = 0, losses = 0;
    for (const auto& t : trades) {
        if (t.pnl > 0) { ++wins; win_sum += t.pnl; }
        else { ++losses; loss_sum -= t.pnl; }
        hold += t.held_s;
        ReasonStats& r = m.by_reason[t.reason];
        ++r.n;
        r.pnl += t.pnl;
        r.wins += t.pnl > 0 ? 1 : 0;
    }
    const auto& eq = equity_curve;
    std::vector<double> rets;
    for (size_t i = 1; i < eq.size(); ++i)
        if (eq[i - 1] > 0) rets.push_back(eq[i] / eq[i - 1] - 1);
    if (rets.size() > 2) {
        double mean = 0;
        for (double r : rets) mean += r;
        mean /= static_cast<double>(rets.size());
        double var = 0;
        for (double r : rets) var += (r - mean) * (r - mean);
        const double sd = std::sqrt(var / static_cast<double>(rets.size() - 1));
        const double per_year = 365.0 * 86400.0 / interval_s;
        m.sharpe = sd > 0 ? mean / sd * std::sqrt(per_year) : 0.0;
    }
    double peak = eq.empty() ? 0 : eq[0], mdd = 0;
    for (double v : eq) {
        peak = std::max(peak, v);
        if (peak > 0) mdd = std::max(mdd, (peak - v) / peak);
    }
    m.win_rate = m.trades ? static_cast<double>(wins) / static_cast<double>(m.trades) : 0.0;
    m.pnl = end_equity - start_equity;
    m.return_pct = start_equity > 0 ? (end_equity / start_equity - 1) * 100 : 0.0;
    m.max_drawdown_pct = mdd * 100;
    m.profit_factor = loss_sum > 0 ? win_sum / loss_sum
                                   : (wins > 0 ? std::numeric_limits<double>::infinity() : 0.0);
    m.avg_win = wins ? win_sum / static_cast<double>(wins) : 0.0;
    m.avg_loss = losses ? -loss_sum / static_cast<double>(losses) : 0.0;
    m.avg_hold_s = m.trades ? hold / static_cast<double>(m.trades) : 0.0;
    m.fees = fees;
    m.funding = funding;
    m.shortfall = shortfall;
    double cum = 0, sum = 0, sum2 = 0;
    for (const auto& t : trades) {
        m.gross_pnl += sign(t.side) * t.qty * (t.exit_price - t.entry_price);
        cum += t.pnl;
        sum += t.pnl;
        sum2 += t.pnl * t.pnl;
        if (halt_limit > 0 && cum <= -halt_limit) m.halt_breached = true;
    }
    if (trades.size() > 1) {
        const double n = static_cast<double>(trades.size()), mean = sum / n;
        const double sd = std::sqrt(std::max(0.0, (sum2 - n * mean * mean) / (n - 1)));
        m.trade_t_stat = sd > 0 ? mean / (sd / std::sqrt(n)) : 0.0;
    }
    m.liquidations = liquidations;
    m.skips = skips;
    return m;
}

// ── Exécution ──────────────────────────────────────────────────────────────

BacktestResult run_backtest(const Config& cfg, const std::vector<Candle>& candles, int interval_s,
                            const RunOptions& opt) {
    const Instrument inst = cfg.instrument();
    PaperExchange ex(cfg.equity, cfg.slippage_pct, cfg.default_spread_pct, cfg.taker_fee);
    RiskManager risk(cfg, cfg.equity);
    PerpBot bot(cfg, inst, ex, risk);
    if (opt.random_prob > 0) bot.set_random_entries(opt.random_prob, opt.seed);

    BacktestResult res;
    res.interval_s = interval_s;
    res.start_equity = cfg.equity;
    res.halt_limit = cfg.halt_report_pct * cfg.equity;
    res.equity_curve.push_back(cfg.equity);
    size_t fi = 0; // les ticks sont croissants : pointeur sur le dernier taux publié
    for (const Candle& c : candles) {
        const bool warm = c.ts < opt.start_ts;
        for (Tick t : candle_ticks(c, interval_s, cfg.bt_funding_rate_per_hour)) {
            t.warmup = warm;
            if (opt.funding) t.funding_rate = funding_at(*opt.funding, fi, t.ts);
            bot.on_tick(t);
        }
        if (!warm) {
            res.equity_curve.push_back(ex.equity());
            res.candle_ts.push_back(c.ts);
        }
    }
    if (!candles.empty() && ex.position(inst.iid)) {
        const Candle& last = candles.back();
        Tick t;
        t.ts = last.ts + interval_s;
        t.mark = t.index = last.c;
        ex.market_close(inst, t, "end_of_test");
        res.equity_curve.back() = ex.equity();
    }
    res.trades = ex.closed();
    res.end_equity = ex.equity();
    res.fees = ex.total_fees();
    res.funding = ex.total_funding();
    res.shortfall = ex.shortfall();
    res.liquidations = ex.liquidations();
    res.skips = bot.skips();
    return res;
}

// ── Sorties ────────────────────────────────────────────────────────────────

std::string format_report(const Metrics& m) {
    char buf[256];
    std::string out;
    auto add = [&](const char* fmt, auto... args) {
        std::snprintf(buf, sizeof buf, fmt, args...);
        out += buf;
    };
    add("Trades %ld | win rate %.1f%% | PnL %+.2f (%+.2f%%)\n", m.trades, m.win_rate * 100, m.pnl,
        m.return_pct);
    if (std::isinf(m.profit_factor))
        add("Sharpe %.2f | max DD %.2f%% | profit factor inf\n", m.sharpe, m.max_drawdown_pct);
    else
        add("Sharpe %.2f | max DD %.2f%% | profit factor %.2f\n", m.sharpe, m.max_drawdown_pct,
            m.profit_factor);
    add("Gain moyen %+.2f | perte moyenne %+.2f | tenue moyenne %.0fs\n", m.avg_win, m.avg_loss,
        m.avg_hold_s);
    add("Frais %.2f | funding %+.2f | liquidations %ld | shortfall %.2f\n", m.fees, m.funding,
        m.liquidations, m.shortfall);
    out += "Sorties (PnL net par raison, pire en premier) :\n";
    std::vector<std::pair<std::string, ReasonStats>> rs(m.by_reason.begin(), m.by_reason.end());
    std::sort(rs.begin(), rs.end(), [](const auto& a, const auto& b) { return a.second.pnl < b.second.pnl; });
    for (const auto& kv : rs)
        add("  %-22s n=%-5ld pnl=%+10.2f  win=%.0f%%\n", kv.first.c_str(), kv.second.n, kv.second.pnl,
            100.0 * static_cast<double>(kv.second.wins) / static_cast<double>(kv.second.n));
    std::vector<std::pair<std::string, long>> sk(m.skips.begin(), m.skips.end());
    std::sort(sk.begin(), sk.end(), [](const auto& a, const auto& b) { return a.second > b.second; });
    out += "Filtres (top) :";
    for (size_t i = 0; i < sk.size() && i < 6; ++i) {
        add(" %s=%ld", sk[i].first.c_str(), sk[i].second);
        if (i + 1 < sk.size() && i + 1 < 6) out += ",";
    }
    out += "\n";
    return out;
}

void write_trades_csv(const std::string& path, const std::vector<ClosedTrade>& trades) {
    std::ofstream f(path);
    if (!f) throw std::runtime_error("ecriture impossible : " + path);
    f << "symbol,side,opened_ts,closed_ts,entry_price,exit_price,qty,leverage,margin,pnl,pnl_pct,fees,"
         "funding,reason,held_s\n";
    f.precision(12);
    for (const auto& t : trades)
        f << t.symbol << ',' << side_name(t.side) << ',' << t.opened_ts << ',' << t.closed_ts << ','
          << t.entry_price << ',' << t.exit_price << ',' << t.qty << ',' << t.leverage << ','
          << t.margin << ',' << t.pnl << ',' << t.pnl_pct << ',' << t.fees << ',' << t.funding << ','
          << t.reason << ',' << t.held_s << '\n';
}

} // namespace perp
