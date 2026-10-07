// Sorties : garde-fou liquidation, trailing, SL (avec grace min_hold), TP, sorties temporelles.
// Tous les seuils sont en % du prix sous-jacent, indépendants du levier.
#pragma once

#include "perp/config.hpp"
#include "perp/types.hpp"

namespace perp {

class PositionManager {
public:
    explicit PositionManager(const Config& cfg) : cfg_(cfg) {}

    void init_levels(Position& pos, double sl_pct, double tp_pct) const;

    // nullptr si on garde la position, sinon la raison de sortie.
    // Mute pos (trailing : high_water, trail_price).
    const char* check_exits(Position& pos, double price, double now) const;

private:
    Config cfg_;
};

} // namespace perp
