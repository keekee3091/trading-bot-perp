#include "perp/bot.hpp"

#include <algorithm>
#include <cmath>

namespace perp {

static SignalEngine::Params engine_params(const Config& c) {
    SignalEngine::Params p;
    p.threshold = c.signal_threshold;
    p.lookback_seconds = c.signal_lookback_seconds;
    p.vol_window_seconds = c.vol_window_seconds;
    p.sensitivity = c.signal_sensitivity;
    p.ref_weight = c.ref_weight;
    p.z_cap = c.z_cap;
    return p;
}

// Assez d'historique pour le lookback et la fenêtre de vol, 3600 s au minimum.
static double history_seconds(const Config& c) {
    return std::max(3600.0, std::max(c.signal_lookback_seconds, c.vol_window_seconds) + 300.0);
}

PerpBot::PerpBot(const Config& cfg, const Instrument& inst, IExchange& ex, RiskManager& risk)
    : cfg_(cfg), inst_(inst), ex_(ex), risk_(risk), pm_(cfg),
      hist_(history_seconds(cfg), cfg.sample_seconds), ref_hist_(history_seconds(cfg), cfg.sample_seconds),
      engine_(engine_params(cfg)) {}

void PerpBot::set_random_entries(double prob, std::uint64_t seed) {
    random_ = true;
    random_prob_ = prob;
    rng_.seed(seed);
    // Seuil 0.5 : le moteur renvoie toujours un signal dès que la vol est mesurable, on n'en
    // garde que la volatilité (dimensionnement du SL) ; le côté est tiré au hasard.
    SignalEngine::Params p = engine_params(cfg_);
    p.threshold = 0.5;
    engine_ = SignalEngine(p);
}

bool PerpBot::in_trading_hours(double ts) const {
    const double s = cfg_.trading_hours_utc_start, e = cfg_.trading_hours_utc_end;
    if (s < 0 || e < 0) return true;
    const double h = std::fmod(ts, 86400.0) / 3600.0;
    return s <= e ? (h >= s && h < e) : (h >= s || h < e);
}

std::vector<ClosedTrade> PerpBot::on_tick(const Tick& tick) {
    std::vector<ClosedTrade> out;
    // Hors session le prix vient de flux de repli minces : il ne nourrit pas le signal (la
    // réouverture apparaît alors comme un seul gros rendement : le gap).
    if (tick.tradable) hist_.add(tick.ts, tick.px());
    if (tick.ref_price > 0) ref_hist_.add(tick.ts, tick.ref_price);

    for (auto& t : ex_.on_tick(inst_, tick)) { // funding + liquidation
        after_close(t, tick);
        out.push_back(std::move(t));
    }

    if (Position* pos = ex_.position(inst_.iid)) {
        state_ = State::Holding;
        if (const char* reason = pm_.check_exits(*pos, tick.px(), tick.ts)) {
            if (auto t = ex_.market_close(inst_, tick, reason)) {
                after_close(*t, tick);
                out.push_back(std::move(*t));
            }
        }
    } else {
        state_ = State::Idle;
        try_enter(tick);
    }
    return out;
}

void PerpBot::after_close(const ClosedTrade& t, const Tick& tick) {
    risk_.clear_exposure(inst_.symbol);
    risk_.record_trade(t, tick.ts);
    state_ = State::Idle;
    if (on_trade_) on_trade_(t);
}

void PerpBot::try_enter(const Tick& tick) {
    const Config& c = cfg_;
    if (tick.warmup) return skip("warmup");
    if (!tick.tradable) return skip("off_session");
    if (!in_trading_hours(tick.ts)) return skip("hours");
    if (random_ && static_cast<double>(rng_() >> 11) * (1.0 / 9007199254740992.0) >= random_prob_)
        return skip("random_wait");
    auto sig = engine_.compute(tick.ts, hist_, ref_hist_.empty() ? nullptr : &ref_hist_);
    if (!sig) return skip("no_signal");
    if (random_) sig->side = (rng_() & 1) ? Side::Long : Side::Short;
    if (!random_ && std::fabs(sig->z_score) < c.min_z_score) return skip("z_low");
    if (tick.bid > 0 && tick.ask > 0 && (tick.ask - tick.bid) / tick.px() > c.max_spread_pct)
        return skip("spread");

    // Stop dimensionné sur la vol, jamais plus serré que le plancher ni plus large que le plafond.
    double sl_pct = std::max(c.sl_pct_floor, c.sl_vol_mult * sig->volatility);
    sl_pct = std::min(sl_pct, c.sl_pct_cap);
    const double tp_pct = sl_pct * c.tp_rr;

    // Edge : proba du signal vs breakeven après coûts. Durée de détention attendue pour le
    // funding : la sortie temporelle si elle existe, sinon la détention max.
    const double hold_s = c.time_exit_seconds > 0 ? c.time_exit_seconds : c.max_hold_seconds;
    const double cost = ex_.round_trip_cost(inst_, tick, sig->side, hold_s);
    if (!random_ && sig->probability - breakeven_prob(sl_pct, tp_pct, cost) < c.min_edge)
        return skip("edge");

    const double equity = ex_.equity();
    // Volatilité réalisée annualisée : la vol d'horizon du signal ramenée à l'année (racine du temps).
    const double ann_vol = sig->volatility * std::sqrt(31536000.0 / c.signal_lookback_seconds);
    const SizeDecision size = risk_.size(equity, inst_, sl_pct, sig->side, ann_vol);
    if (size.notional <= 0) return skip("size");
    if (const char* why = risk_.check_entry(tick.ts, sig->side, size.notional, equity)) return skip(why);

    const double qty = inst_.round_qty(size.notional / tick.px());
    Position* pos = ex_.market_open(inst_, sig->side, qty, size.leverage, tick);
    if (!pos) return skip("rejected");
    pm_.init_levels(*pos, sl_pct, tp_pct);
    risk_.set_exposure(inst_.symbol, pos->side, pos->notional());
    risk_.on_entry(tick.ts);
    state_ = State::Holding;
    if (on_open_) on_open_(*pos);
}

} // namespace perp
