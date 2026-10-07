// Signal directionnel : rendement sur lookback normalisé par la vol, z-score,
// sigmoïde, fusion optionnelle d'un prix de référence (Binance) 40/60.
// Pas de biais funding en v1 (l'échelle de l'ancien 1e4/10 était arbitraire).
#pragma once

#include <deque>
#include <optional>
#include <utility>

#include "perp/types.hpp"

namespace perp {

constexpr double kMinVol = 1e-5;

double sigmoid(double x);

// Historique glissant (ts, prix) avec échantillonnage minimal entre points.
class PriceHistory {
public:
    using Point = std::pair<double, double>;

    explicit PriceHistory(double max_seconds = 3600.0, double min_step = 0.0)
        : max_(max_seconds), min_step_(min_step) {}

    void add(double ts, double price);
    size_t size() const { return d_.size(); }
    bool empty() const { return d_.empty(); }
    double last() const { return d_.back().second; }
    const std::deque<Point>& points() const { return d_; }
    // Dernier prix observé à ou avant now - seconds ; nullopt si l'historique est trop court.
    std::optional<double> price_ago(double now, double seconds) const;

private:
    std::deque<Point> d_;
    double max_, min_step_;
};

class SignalEngine {
public:
    struct Params {
        double threshold = 0.7;
        double lookback_seconds = 300;
        double vol_window_seconds = 900;
        double sensitivity = 1.5;
        double ref_weight = 0.6;
        double z_cap = 4.0;
    };

    explicit SignalEngine(const Params& p) : p_(p) {}

    std::optional<Signal> compute(double now, const PriceHistory& hist,
                                  const PriceHistory* ref_hist = nullptr) const;

private:
    struct Z { double z, vol, price; };
    std::optional<Z> z(const PriceHistory& h, double now) const;
    Params p_;
};

} // namespace perp
