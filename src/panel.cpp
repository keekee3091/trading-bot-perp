#include "perp/panel.hpp"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <fstream>
#include <stdexcept>

#include "perp/sweep.hpp"

namespace perp {

static bool file_exists(const std::string& p) {
    std::ifstream f(p);
    return static_cast<bool>(f);
}

std::vector<PanelInstrument> load_panel(const std::vector<std::string>& symbols, const std::string& dir,
                                        const std::vector<std::string>& config_files,
                                        const std::vector<std::string>& sets) {
    std::vector<PanelInstrument> out;
    for (const auto& sym : symbols) {
        PanelInstrument pi;
        pi.symbol = sym;
        for (const auto& f : config_files) pi.cfg.load_file(f);
        const std::string overlay = dir + "/" + sym + ".instrument.yaml";
        if (file_exists(overlay)) pi.cfg.load_file(overlay);
        for (const auto& s : sets) {
            const size_t eq = s.find('=');
            if (eq == std::string::npos || !pi.cfg.set_kv(s.substr(0, eq), s.substr(eq + 1)))
                throw std::runtime_error("--set invalide ou cle inconnue : " + s);
        }
        pi.cfg.strs["symbol"] = sym;
        pi.candles = load_csv(dir + "/" + sym + "_1m.csv");
        pi.funding = load_funding_csv(dir + "/" + sym + "_funding.csv");
        if (pi.candles.empty()) throw std::runtime_error("aucune bougie : " + sym);
        out.push_back(std::move(pi));
    }
    return out;
}

double parse_date(const std::string& ymd) {
    int y, m, d;
    if (std::sscanf(ymd.c_str(), "%d-%d-%d", &y, &m, &d) != 3 || m < 1 || m > 12 || d < 1 || d > 31)
        throw std::runtime_error("date attendue YYYY-MM-DD : " + ymd);
    // days_from_civil (H. Hinnant)
    y -= m <= 2;
    const int era = (y >= 0 ? y : y - 399) / 400;
    const int yoe = y - era * 400;
    const int doy = (153 * (m + (m > 2 ? -3 : 9)) + 2) / 5 + d - 1;
    const int doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    return (era * 146097 + doe - 719468) * 86400.0;
}

static std::vector<Candle> slice(const std::vector<Candle>& c, double from, double to) {
    auto lo = std::lower_bound(c.begin(), c.end(), from, [](const Candle& x, double t) { return x.ts < t; });
    auto hi = std::lower_bound(c.begin(), c.end(), to, [](const Candle& x, double t) { return x.ts < t; });
    return std::vector<Candle>(lo, hi);
}

static InstRun run_instrument(const PanelInstrument& pi, const Params& params, const Window& w, double prob,
                              std::uint64_t seed) {
    Config cfg = pi.cfg;
    for (const auto& p : params)
        if (!cfg.set(p.first, p.second)) throw std::runtime_error("cle inconnue : " + p.first);
    InstRun ir;
    ir.symbol = pi.symbol;
    ir.window = slice(pi.candles, w.start, w.end);
    ir.res.start_equity = ir.res.end_equity = cfg.equity;
    if (ir.window.empty()) return ir;
    const std::vector<Candle> with_warm = slice(pi.candles, w.start - w.warmup_s, w.end);
    RunOptions o;
    o.funding = &pi.funding;
    o.start_ts = w.start;
    o.random_prob = prob;
    o.seed = seed;
    ir.res = run_backtest(cfg, with_warm, 60, o);
    return ir;
}

PanelRun run_panel(const std::vector<PanelInstrument>& panel, const Params& params, const Window& w,
                   unsigned threads, const std::vector<double>* random_prob, std::uint64_t seed) {
    PanelRun pr;
    const size_t n = panel.size();
    pr.inst.resize(n);
    parallel_for(n, threads, [&](size_t i) {
        pr.inst[i] = run_instrument(panel[i], params, w, random_prob ? (*random_prob)[i] : 0.0,
                                    seed + 7919 * i);
    });

    // Grille horaire commune : de l'heure de w.start à l'heure de la dernière bougie de fenêtre.
    double last_ts = w.start;
    for (const auto& ir : pr.inst)
        if (!ir.window.empty()) last_ts = std::max(last_ts, ir.window.back().ts);
    const long h0 = static_cast<long>(std::floor(w.start / 3600.0));
    const long h1 = static_cast<long>(std::floor(last_ts / 3600.0));
    const size_t H = static_cast<size_t>(h1 - h0 + 1);

    std::vector<std::vector<double>> eq(n, std::vector<double>(H, 0.0)), px(n, std::vector<double>(H, 0.0));
    std::vector<long> first_h(n, -1), last_h(n, -1);
    double start_sum = 0;
    for (size_t i = 0; i < n; ++i) {
        const InstRun& ir = pr.inst[i];
        start_sum += ir.res.start_equity;
        std::vector<bool> seen(H, false);
        for (size_t k = 0; k < ir.res.candle_ts.size(); ++k) {
            const long h = static_cast<long>(std::floor(ir.res.candle_ts[k] / 3600.0)) - h0;
            if (h < 0 || h >= static_cast<long>(H)) continue;
            eq[i][static_cast<size_t>(h)] = ir.res.equity_curve[k + 1]; // dernier point de l'heure
            px[i][static_cast<size_t>(h)] = ir.window[k].c;
            seen[static_cast<size_t>(h)] = true;
            if (first_h[i] < 0) first_h[i] = h;
            last_h[i] = h;
        }
        double cur = ir.res.start_equity, cpx = 0;
        for (size_t h = 0; h < H; ++h) { // report en avant ; cash avant le premier point
            if (seen[h]) { cur = eq[i][h]; cpx = px[i][h]; }
            eq[i][h] = cur;
            px[i][h] = cpx;
        }
        if (!ir.window.empty()) ++pr.n_active;
        if (!ir.window.empty() && ir.res.end_equity > ir.res.start_equity) ++pr.n_positive;
    }

    std::vector<double> curve;
    curve.push_back(start_sum / static_cast<double>(n));
    for (size_t h = 0; h < H; ++h) {
        double s = 0;
        for (size_t i = 0; i < n; ++i) s += eq[i][h];
        curve.push_back(s / static_cast<double>(n));
        pr.hour_ts.push_back(static_cast<double>(h0 + static_cast<long>(h)) * 3600.0);
        pr.port_ret.push_back(curve[h] > 0 ? curve[h + 1] / curve[h] - 1 : 0.0);
        double m = 0;
        int cnt = 0;
        if (h > 0)
            for (size_t i = 0; i < n; ++i)
                if (first_h[i] >= 0 && static_cast<long>(h - 1) >= first_h[i] && static_cast<long>(h) <= last_h[i] &&
                    px[i][h - 1] > 0) {
                    m += px[i][h] / px[i][h - 1] - 1;
                    ++cnt;
                }
        pr.mkt_ret.push_back(cnt ? m / cnt : 0.0);
    }
    pr.port.interval_s = 3600;
    pr.port.equity_curve = curve;
    pr.port.candle_ts = pr.hour_ts;
    pr.port.start_equity = curve.front();
    pr.port.end_equity = curve.back();
    for (const auto& ir : pr.inst) {
        pr.port.trades.insert(pr.port.trades.end(), ir.res.trades.begin(), ir.res.trades.end());
        pr.port.fees += ir.res.fees;
        pr.port.funding += ir.res.funding;
        pr.port.liquidations += ir.res.liquidations;
        pr.port.shortfall += ir.res.shortfall;
        for (const auto& kv : ir.res.skips) pr.port.skips[kv.first] += kv.second;
        pr.liquidations += ir.res.liquidations;
    }
    for (const auto& t : pr.port.trades) pr.liq_guards += t.reason == "liq_guard" ? 1 : 0;
    pr.pm = pr.port.metrics();
    return pr;
}

PanelRandom run_panel_random(const std::vector<PanelInstrument>& panel, const Params& params, const Window& w,
                             const PanelRun& strategy, int runs, std::uint64_t seed, unsigned threads) {
    PanelRandom out;
    const size_t n = panel.size();
    out.entry_prob.assign(n, 1e-12); // ~0 : instrument sans trade de référence, aucune entrée
    parallel_for(n, threads, [&](size_t i) {
        const double target = static_cast<double>(strategy.inst[i].res.trades.size());
        if (target < 1 || strategy.inst[i].window.empty()) return;
        double q = std::min(1.0, target / (static_cast<double>(strategy.inst[i].window.size()) * 4.0 * 0.3));
        for (int it = 0; it < 6; ++it) {
            const double obs = static_cast<double>(run_instrument(panel[i], params, w, q, seed).res.trades.size());
            q = std::min(1.0, q * (obs > 0 ? target / obs : 4.0));
        }
        out.entry_prob[i] = q;
    });
    out.sharpe.assign(static_cast<size_t>(runs), 0.0);
    out.ret_pct.assign(static_cast<size_t>(runs), 0.0);
    out.inst_pnl.assign(n, std::vector<double>(static_cast<size_t>(runs), 0.0));
    parallel_for(static_cast<size_t>(runs), threads, [&](size_t j) {
        const PanelRun r = run_panel(panel, params, w, 1, &out.entry_prob, seed + 1 + j * 104729);
        out.sharpe[j] = r.pm.sharpe;
        out.ret_pct[j] = r.pm.return_pct;
        for (size_t i = 0; i < n; ++i) out.inst_pnl[i][j] = r.inst[i].res.end_equity - r.inst[i].res.start_equity;
    });
    return out;
}

std::vector<BacktestResult> panel_buy_hold(const std::vector<PanelInstrument>& panel, const Window& w) {
    std::vector<BacktestResult> out;
    for (const auto& pi : panel) {
        const std::vector<Candle> c = slice(pi.candles, w.start, w.end);
        if (c.empty()) {
            BacktestResult r;
            r.start_equity = r.end_equity = pi.cfg.equity;
            out.push_back(r);
        } else {
            out.push_back(run_buy_hold(pi.cfg, c, 60, &pi.funding));
        }
    }
    return out;
}

} // namespace perp
