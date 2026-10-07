#include "perp/validate.hpp"

#include <algorithm>
#include <cmath>
#include <stdexcept>

#include "perp/exchange.hpp"
#include "perp/sweep.hpp"

namespace perp {

BetaStats beta_regression(const BacktestResult& r, const std::vector<Candle>& candles) {
    BetaStats out;
    if (r.equity_curve.size() != candles.size() + 1) return out;
    std::vector<double> eq, px;
    long bucket = -1;
    for (size_t i = 0; i < candles.size(); ++i) {
        const long b = static_cast<long>(std::floor(candles[i].ts / 3600.0));
        if (b != bucket) {
            eq.push_back(0);
            px.push_back(0);
            bucket = b;
        }
        eq.back() = r.equity_curve[i + 1]; // dernier point du bucket
        px.back() = candles[i].c;
    }
    std::vector<double> y, x;
    for (size_t k = 1; k < eq.size(); ++k) {
        if (eq[k - 1] <= 0 || px[k - 1] <= 0) continue;
        y.push_back(eq[k] / eq[k - 1] - 1);
        x.push_back(px[k] / px[k - 1] - 1);
    }
    return ols_alpha_beta(y, x, 8760.0);
}

BetaStats ols_alpha_beta(const std::vector<double>& y, const std::vector<double>& x, double periods_per_year) {
    BetaStats out;
    const double n = static_cast<double>(y.size());
    if (n < 10 || x.size() != y.size()) return out;
    double mx = 0, my = 0;
    for (size_t i = 0; i < y.size(); ++i) { mx += x[i]; my += y[i]; }
    mx /= n;
    my /= n;
    double sxx = 0, sxy = 0, syy = 0;
    for (size_t i = 0; i < y.size(); ++i) {
        sxx += (x[i] - mx) * (x[i] - mx);
        sxy += (x[i] - mx) * (y[i] - my);
        syy += (y[i] - my) * (y[i] - my);
    }
    if (sxx <= 0) return out;
    out.n = static_cast<int>(n);
    out.beta = sxy / sxx;
    const double alpha = my - out.beta * mx;
    double rss = 0;
    for (size_t i = 0; i < y.size(); ++i) {
        const double e = y[i] - alpha - out.beta * x[i];
        rss += e * e;
    }
    const double s2 = rss / (n - 2);
    const double se = std::sqrt(s2 * (1.0 / n + mx * mx / sxx));
    out.alpha_ann_pct = alpha * periods_per_year * 100.0;
    out.t_alpha = se > 0 ? alpha / se : 0.0;
    out.r2 = syy > 0 ? 1.0 - rss / syy : 0.0;
    return out;
}

Split split_chrono(const std::vector<Candle>& c, double train_frac, double val_frac) {
    const size_t n = c.size();
    const size_t i1 = static_cast<size_t>(static_cast<double>(n) * train_frac);
    const size_t i2 = static_cast<size_t>(static_cast<double>(n) * (train_frac + val_frac));
    Split s;
    s.train.assign(c.begin(), c.begin() + static_cast<std::ptrdiff_t>(i1));
    s.val.assign(c.begin() + static_cast<std::ptrdiff_t>(i1), c.begin() + static_cast<std::ptrdiff_t>(i2));
    s.test.assign(c.begin() + static_cast<std::ptrdiff_t>(i2), c.end());
    return s;
}

BacktestResult run_buy_hold(const Config& cfg, const std::vector<Candle>& candles, int interval_s,
                            const std::vector<FundingPoint>* funding) {
    if (candles.empty()) throw std::runtime_error("buy and hold : aucune bougie");
    const Instrument inst = cfg.instrument();
    PaperExchange ex(cfg.equity, cfg.slippage_pct, cfg.default_spread_pct, cfg.taker_fee);
    BacktestResult res;
    res.interval_s = interval_s;
    res.start_equity = cfg.equity;
    res.equity_curve.push_back(cfg.equity);
    size_t fi = 0;
    bool opened = false;
    for (const Candle& c : candles) {
        for (Tick t : candle_ticks(c, interval_s, 0.0)) {
            t.funding_rate = funding ? funding_at(*funding, fi, t.ts) : cfg.bt_funding_rate_per_hour;
            if (!opened) {
                // 99,9 % de l'equity, 1x : marge + frais d'entrée doivent tenir dans le solde.
                const double fee = cfg.taker_fee >= 0 ? cfg.taker_fee : inst.taker_fee;
                const double fill = t.px() * (1 + cfg.default_spread_pct / 2) * (1 + cfg.slippage_pct);
                const double qty = inst.round_qty(cfg.equity * 0.999 / (fill * (1 + fee)));
                if (!ex.market_open(inst, Side::Long, qty, 1.0, t)) throw std::runtime_error("buy and hold : ordre rejete");
                opened = true;
            }
            ex.on_tick(inst, t);
        }
        res.equity_curve.push_back(ex.equity());
    }
    Tick t;
    t.ts = candles.back().ts + interval_s;
    t.mark = t.index = candles.back().c;
    ex.market_close(inst, t, "buy_and_hold_end");
    res.equity_curve.back() = ex.equity();
    res.trades = ex.closed();
    res.end_equity = ex.equity();
    res.fees = ex.total_fees();
    res.funding = ex.total_funding();
    res.halt_limit = 0;
    return res;
}

RandomStats run_random_baseline(const Config& cfg, const std::vector<Candle>& candles, int interval_s,
                                const std::vector<FundingPoint>* funding, double target_trades,
                                double strategy_pnl, int runs, std::uint64_t seed, unsigned threads) {
    RandomStats st;
    st.runs = runs;
    if (target_trades < 1 || candles.empty() || runs < 1) return st;
    RunOptions opt;
    opt.funding = funding;
    // Calibrage : la probabilité par tick libre qui donne ~target_trades (cooldowns et plafonds
    // du risk manager compris). Quelques itérations multiplicatives sur une graine fixe.
    double q = std::min(1.0, target_trades / (static_cast<double>(candles.size()) * 4.0 * 0.3));
    for (int it = 0; it < 6; ++it) {
        opt.random_prob = q;
        opt.seed = seed;
        const double obs = static_cast<double>(run_backtest(cfg, candles, interval_s, opt).trades.size());
        q = std::min(1.0, q * (obs > 0 ? target_trades / obs : 4.0));
    }
    st.entry_prob = q;
    std::vector<Metrics> ms(static_cast<size_t>(runs));
    parallel_for(ms.size(), threads, [&](size_t i) {
        RunOptions o = opt;
        o.random_prob = q;
        o.seed = seed + 1 + i;
        ms[i] = run_backtest(cfg, candles, interval_s, o).metrics();
    });
    std::vector<double> pnl;
    for (const Metrics& m : ms) {
        pnl.push_back(m.pnl);
        st.mean_trades += static_cast<double>(m.trades);
        st.mean_pnl += m.pnl;
        st.mean_gross += m.gross_pnl;
        st.mean_sharpe += m.sharpe;
        st.frac_ge += m.pnl >= strategy_pnl ? 1.0 : 0.0;
    }
    const double n = static_cast<double>(runs);
    st.mean_trades /= n;
    st.mean_pnl /= n;
    st.mean_gross /= n;
    st.mean_sharpe /= n;
    st.frac_ge /= n;
    std::sort(pnl.begin(), pnl.end());
    auto quant = [&](double p) { return pnl[static_cast<size_t>(p * static_cast<double>(pnl.size() - 1))]; };
    st.p5 = quant(0.05);
    st.p50 = quant(0.5);
    st.p95 = quant(0.95);
    return st;
}

} // namespace perp
