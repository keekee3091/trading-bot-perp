#include "perp/position_manager.hpp"

#include <cmath>

namespace perp {

void PositionManager::init_levels(Position& pos, double sl_pct, double tp_pct) const {
    const int s = sign(pos.side);
    pos.sl_price = pos.entry_price * (1 - s * sl_pct);
    pos.tp_price = pos.entry_price * (1 + s * tp_pct);
    pos.high_water = pos.entry_price;
    pos.trail_active = false;
    pos.trail_price = 0;
}

const char* PositionManager::check_exits(Position& pos, double price, double now) const {
    const Config& c = cfg_;
    const int s = sign(pos.side);
    const double age = now - pos.opened_ts;
    const double pnl_pct = pos.pnl_pct_underlying(price);

    // 1. Garde-fou liquidation. Sortir coûte un frais taker ; se faire liquider coûte la marge
    // restante et les frais de liquidation, facturés au fill. La marge de sécurité inclut donc
    // ces frais : on sort tant qu'il reste de quoi les couvrir.
    if (pos.liq_distance_pct(price) <= c.liq_guard_pct + pos.liq_fee) return "liq_guard";

    // 2. Trailing stop
    const double act = c.trailing_activation_pct, dist = c.trailing_distance_pct;
    if (act > 0 && dist > 0) {
        if (!pos.trail_active) {
            if (pnl_pct >= act) {
                pos.trail_active = true;
                pos.high_water = price;
                pos.trail_price = price * (1 - s * dist);
            }
        } else {
            if ((price - pos.high_water) * s > 0) {
                pos.high_water = price;
                pos.trail_price = price * (1 - s * dist);
            }
            if ((price - pos.trail_price) * s <= 0) return "trailing_stop";
        }
    }

    // 3. Stop loss (grace min_hold : seul un SL d'urgence élargi s'applique)
    const double sl_dist = std::fabs(pos.entry_price - pos.sl_price) / pos.entry_price;
    if (age < c.min_hold_seconds) {
        const double emergency = pos.entry_price * (1 - s * sl_dist * c.emergency_sl_mult);
        if ((price - emergency) * s <= 0) return "stop_loss_emergency";
    } else if ((price - pos.sl_price) * s <= 0) {
        return "stop_loss";
    }

    // 4. Take profit
    if ((price - pos.tp_price) * s >= 0) return "take_profit";

    // 5. Sorties temporelles
    if (c.time_exit_seconds > 0 && age >= c.time_exit_seconds && pnl_pct >= c.time_exit_min_pnl_pct)
        return "time_exit";
    if (c.max_hold_seconds > 0 && age >= c.max_hold_seconds) return "max_hold";
    return nullptr;
}

} // namespace perp
