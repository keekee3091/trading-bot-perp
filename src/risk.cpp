#include "perp/risk.hpp"

#include <algorithm>
#include <cmath>

namespace perp {

double RiskManager::kelly_mult() const {
    if (cfg_.kelly_enabled <= 0) return 1.0;
    const size_t window = static_cast<size_t>(cfg_.kelly_window);
    if (win_.size() < std::max<size_t>(5, window / 2)) return 1.0;
    const size_t n = std::min(window, win_.size());
    double wins = 0, gain_sum = 0, loss_sum = 0;
    long n_gain = 0, n_loss = 0;
    for (size_t i = win_.size() - n; i < win_.size(); ++i) {
        wins += win_[i] ? 1 : 0;
        const double x = pnl_pct_[i];
        if (x > 0) { gain_sum += x; ++n_gain; }
        else if (x < 0) { loss_sum -= x; ++n_loss; }
    }
    if (n_gain == 0 || n_loss == 0) return 1.0;
    const double p = wins / static_cast<double>(n);
    const double b = (gain_sum / static_cast<double>(n_gain)) / (loss_sum / static_cast<double>(n_loss));
    const double f_star = p - (1 - p) / b;
    if (f_star <= 0) return cfg_.kelly_min_mult;
    const double m = cfg_.kelly_scaling * f_star / cfg_.kelly_base_fraction;
    return std::max(cfg_.kelly_min_mult, std::min(cfg_.kelly_max_mult, m));
}

double RiskManager::liq_leverage_cap(const Instrument& inst, double sl_pct, Side side) const {
    const double m = inst.mmr();
    const double d = cfg_.liq_buffer_mult * sl_pct + inst.liquidation_fee + cfg_.liq_guard_pct;
    const double inv = m + d * (side == Side::Long ? 1.0 - m : 1.0 + m);
    return inv > 0 ? 1.0 / inv : inst.max_leverage;
}

double RiskManager::choose_leverage(const Instrument& inst, double sl_pct, Side side) const {
    return std::max(1.0, std::min({cfg_.leverage, inst.max_leverage, liq_leverage_cap(inst, sl_pct, side)}));
}

SizeDecision RiskManager::size(double equity, const Instrument& inst, double sl_pct, Side side,
                               double ann_vol) const {
    SizeDecision out;
    const double min_notional = std::max(inst.min_notional, cfg_.min_notional);
    if (cfg_.sizing_mode >= 1) {
        // Levier de compte m = notionnel / equity. Marge = equity x margin_frac au plus ; au-delà,
        // le levier de position est m / margin_frac (au plus max_leverage).
        double m = cfg_.account_leverage;
        if (cfg_.vol_target_annual > 0) {
            if (ann_vol <= 0) return out;
            m = cfg_.vol_target_annual / ann_vol;
        }
        m = std::min(m, inst.max_leverage * cfg_.margin_frac);
        if (cfg_.apply_liq_cap > 0) m = std::min(m, liq_leverage_cap(inst, sl_pct, side) * cfg_.margin_frac);
        const double notional = equity * m;
        if (notional < min_notional) return out;
        const double lev = std::max(1.0, notional / (equity * cfg_.margin_frac));
        out.notional = notional;
        out.leverage = lev;
        out.margin = notional / lev;
        out.risk_usdc = notional * sl_pct;
        out.kelly_mult = 1.0;
        return out;
    }
    const double km = kelly_mult();
    const double lev = choose_leverage(inst, sl_pct, side);
    const double risk = equity * cfg_.risk_per_trade_pct * km;
    double notional = sl_pct > 0 ? risk / sl_pct : 0.0;
    notional = std::min({notional, cfg_.max_notional_per_trade, equity * cfg_.max_account_leverage});
    // Marge disponible sous les plafonds d'exposition : on réduit la taille plutôt que de
    // proposer ce que check_entry refusera (net : n <= cap - signe x net ; brut : n <= cap - brut).
    if (cfg_.max_net_exposure_pct > 0)
        notional = std::min(notional, std::max(0.0, cfg_.max_net_exposure_pct * equity - sign(side) * net_exposure()));
    if (cfg_.max_gross_exposure_pct > 0)
        notional = std::min(notional, std::max(0.0, cfg_.max_gross_exposure_pct * equity - gross_exposure()));
    if (notional < min_notional) return out;
    double margin = notional / lev;
    if (margin > equity * cfg_.max_margin_pct) {
        margin = equity * cfg_.max_margin_pct;
        notional = margin * lev;
        if (notional < min_notional) return out;
    }
    out.notional = notional;
    out.margin = margin;
    out.leverage = lev;
    out.risk_usdc = risk;
    out.kelly_mult = km;
    return out;
}

void RiskManager::set_exposure(const std::string& symbol, Side side, double notional) {
    net_[symbol] = sign(side) * notional;
}

double RiskManager::net_exposure() const {
    double s = 0;
    for (const auto& kv : net_) s += kv.second;
    return s;
}

double RiskManager::gross_exposure() const {
    double s = 0;
    for (const auto& kv : net_) s += std::fabs(kv.second);
    return s;
}

const char* RiskManager::check_entry(double now, Side side, double notional, double equity) {
    if (halted_) return "halt";
    if (now < pause_until_) return "cooldown";
    while (!entries_.empty() && now - entries_.front() > 86400) entries_.pop_front();
    const int max_hour = static_cast<int>(cfg_.max_entries_per_hour);
    if (max_hour > 0) {
        int last_hour = 0;
        for (double t : entries_) last_hour += now - t <= 3600 ? 1 : 0;
        if (last_hour >= max_hour) return "max_entries_per_hour";
    }
    const int max_day = static_cast<int>(cfg_.max_entries_per_day);
    if (max_day > 0 && static_cast<int>(entries_.size()) >= max_day) return "max_entries_per_day";
    // Plafond net : refusé s'il est dépassé ET que l'entrée augmente |net| (une entrée qui réduit passe).
    const double cap = cfg_.max_net_exposure_pct * equity;
    if (cap > 0) {
        const double after = net_exposure() + sign(side) * notional;
        if (std::fabs(after) > cap * (1 + 1e-9) && std::fabs(after) > std::fabs(net_exposure()))
            return "net_exposure_cap";
    }
    const double gcap = cfg_.max_gross_exposure_pct * equity;
    if (gcap > 0 && gross_exposure() + notional > gcap * (1 + 1e-9)) return "gross_exposure_cap";
    return nullptr;
}

void RiskManager::record_trade(const ClosedTrade& t, double now) {
    session_pnl_ += t.pnl;
    const long day = static_cast<long>(std::floor(now / 86400.0));
    if (!day_set_ || day != day_) {
        day_set_ = true;
        day_ = day;
        day_pnl_ = 0;
    }
    day_pnl_ += t.pnl;
    win_.push_back(t.pnl > 0);
    pnl_pct_.push_back(t.pnl_pct);
    const size_t keep = 200;
    while (win_.size() > keep) { win_.pop_front(); pnl_pct_.pop_front(); }

    if (t.pnl > 0) {
        consec_losses_ = 0;
        pause_until_ = std::max(pause_until_, now + cfg_.cooldown_after_win_s);
    } else {
        ++consec_losses_;
        pause_until_ = std::max(pause_until_, now + cfg_.cooldown_after_loss_s);
        const int mx = static_cast<int>(cfg_.max_consecutive_losses);
        if (mx > 0 && consec_losses_ >= mx) {
            pause_until_ = now + cfg_.loss_streak_pause_s;
            consec_losses_ = 0;
        }
    }
    const double next_day = static_cast<double>(day_ + 1) * 86400.0;
    const double sess_lim = cfg_.max_session_loss_pct * start_equity_;
    if (sess_lim > 0 && session_pnl_ <= -sess_lim) halted_ = true;
    const double day_lim = cfg_.daily_loss_lock_pct * start_equity_;
    if (day_lim > 0 && day_pnl_ <= -day_lim) pause_until_ = std::max(pause_until_, next_day);
    const double prof_lim = cfg_.daily_profit_lock_pct * start_equity_;
    if (prof_lim > 0 && day_pnl_ >= prof_lim) pause_until_ = std::max(pause_until_, next_day);
}

} // namespace perp
