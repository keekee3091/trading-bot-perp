#include "perp/signal.hpp"

#include <algorithm>
#include <cmath>

namespace perp {

double sigmoid(double x) {
    x = std::max(-500.0, std::min(500.0, x));
    return 1.0 / (1.0 + std::exp(-x));
}

void PriceHistory::add(double ts, double price) {
    if (price <= 0) return;
    if (!d_.empty() && ts - d_.back().first < min_step_)
        d_.back().second = price; // on rafraîchit le dernier point
    else
        d_.emplace_back(ts, price);
    while (!d_.empty() && ts - d_.front().first > max_) d_.pop_front();
}

std::optional<double> PriceHistory::price_ago(double now, double seconds) const {
    const double target = now - seconds;
    if (d_.empty() || d_.front().first > target) return std::nullopt;
    for (auto it = d_.rbegin(); it != d_.rend(); ++it)
        if (it->first <= target) return it->second;
    return std::nullopt;
}

// Écart-type (population) des rendements relatifs point à point, rendements nuls filtrés.
static double rolling_vol(std::deque<PriceHistory::Point>::const_iterator first,
                          std::deque<PriceHistory::Point>::const_iterator last) {
    if (last - first < 3) return kMinVol;
    long n = 0;
    double mean = 0, m2 = 0; // Welford
    for (auto it = first + 1; it != last; ++it) {
        const double a = (it - 1)->second, b = it->second;
        if (a > 0 && b != a) {
            const double r = (b - a) / a, d = r - mean;
            ++n;
            mean += d / static_cast<double>(n);
            m2 += d * (r - mean);
        }
    }
    if (n < 2) return kMinVol;
    return std::max(std::sqrt(m2 / static_cast<double>(n)), kMinVol);
}

std::optional<SignalEngine::Z> SignalEngine::z(const PriceHistory& h, double now) const {
    const auto ago = h.price_ago(now, p_.lookback_seconds);
    if (!ago || *ago <= 0) return std::nullopt;
    const auto& d = h.points();
    auto first = d.end();
    while (first != d.begin() && now - (first - 1)->first <= p_.vol_window_seconds) --first;
    const long n = d.end() - first;
    if (n < 5) return std::nullopt;
    const double vol = rolling_vol(first, d.end());
    // La vol est par pas d'échantillonnage : on la ramène à l'horizon du lookback (racine du temps).
    const double avg_step = (d.back().first - first->first) / static_cast<double>(n - 1);
    const double steps = std::max(1.0, p_.lookback_seconds / std::max(1e-9, avg_step));
    const double horizon_vol = vol * std::sqrt(steps);
    const double cur = h.last();
    const double ret = (cur - *ago) / *ago;
    return Z{horizon_vol > 0 ? ret / horizon_vol : 0.0, horizon_vol, cur};
}

std::optional<Signal> SignalEngine::compute(double now, const PriceHistory& hist,
                                            const PriceHistory* ref_hist) const {
    const auto base = z(hist, now);
    if (!base) return std::nullopt;
    double zs = base->z;
    if (ref_hist && !ref_hist->empty())
        if (const auto r = z(*ref_hist, now)) zs = (1 - p_.ref_weight) * zs + p_.ref_weight * r->z;
    zs = std::max(-p_.z_cap, std::min(p_.z_cap, zs));
    const double p_up = sigmoid(p_.sensitivity * zs);
    if (p_up >= p_.threshold) return Signal{Side::Long, p_up, zs, base->vol, base->price};
    if (1 - p_up >= p_.threshold) return Signal{Side::Short, 1 - p_up, zs, base->vol, base->price};
    return std::nullopt;
}

} // namespace perp
