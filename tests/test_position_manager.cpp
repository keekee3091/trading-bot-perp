#include <cstring>

#include "check.hpp"
#include "perp/position_manager.hpp"

using namespace perp;

static Config base_cfg() {
    Config c;
    c.trailing_activation_pct = 0; // désactivé sauf test dédié
    c.min_hold_seconds = 20;
    c.emergency_sl_mult = 1.5;
    c.time_exit_seconds = 600;
    c.max_hold_seconds = 1800;
    c.liq_guard_pct = 0.002;
    return c;
}

static bool is(const char* got, const char* want) {
    return got && std::strcmp(got, want) == 0;
}

// Long E=100, 5x (marge 20, mmr 2.5 % -> liq 82.05), SL 1 % = 99, TP 1.5 % = 101.5.
static Position long_pos(const PositionManager& pm) {
    Position p;
    p.side = Side::Long;
    p.entry_price = 100;
    p.qty = 1;
    p.leverage = 5;
    p.margin = 20;
    p.mmr = 0.025;
    p.liq_fee = 0.005;
    p.opened_ts = 1000;
    pm.init_levels(p, 0.01, 0.015);
    return p;
}

static void levels() {
    PositionManager pm(base_cfg());
    Position p = long_pos(pm);
    CHECK_NEAR(p.sl_price, 99, 1e-12);
    CHECK_NEAR(p.tp_price, 101.5, 1e-12);
    Position s = p;
    s.side = Side::Short;
    pm.init_levels(s, 0.01, 0.015);
    CHECK_NEAR(s.sl_price, 101, 1e-12);
    CHECK_NEAR(s.tp_price, 98.5, 1e-12);
}

static void sl_tp_long() {
    PositionManager pm(base_cfg());
    Position p = long_pos(pm);
    assert(!pm.check_exits(p, 99.5, 1100));
    assert(is(pm.check_exits(p, 98.9, 1100), "stop_loss"));
    assert(is(pm.check_exits(p, 99.0, 1100), "stop_loss")); // égalité déclenche
    assert(is(pm.check_exits(p, 101.6, 1100), "take_profit"));
}

static void sl_tp_short() {
    PositionManager pm(base_cfg());
    Position p = long_pos(pm);
    p.side = Side::Short;
    pm.init_levels(p, 0.01, 0.015); // SL 101, TP 98.5
    assert(!pm.check_exits(p, 100.5, 1100));
    assert(is(pm.check_exits(p, 101.1, 1100), "stop_loss"));
    assert(is(pm.check_exits(p, 98.4, 1100), "take_profit"));
}

// Grace : pendant min_hold seul le SL d'urgence (distance x 1.5, soit 98.5) s'applique.
static void grace_period_emergency_stop() {
    PositionManager pm(base_cfg());
    Position p = long_pos(pm);
    assert(!pm.check_exits(p, 98.9, 1010));                                   // âge 10 s : SL normal ignoré
    assert(is(pm.check_exits(p, 98.4, 1010), "stop_loss_emergency"));
    assert(is(pm.check_exits(p, 98.9, 1020), "stop_loss"));                   // âge 20 s : SL normal
}

static void time_exits() {
    PositionManager pm(base_cfg());
    Position p = long_pos(pm);
    assert(is(pm.check_exits(p, 100.0, 1600), "time_exit"));  // âge 600, pnl 0 >= 0
    assert(!pm.check_exits(p, 99.9, 1600));                   // pnl négatif : on garde
    assert(!pm.check_exits(p, 99.9, 2799));
    assert(is(pm.check_exits(p, 99.9, 2800), "max_hold"));    // âge 1800
}

// Trailing : activation à +0.6 %, distance 0.3 %.
static void trailing() {
    Config c = base_cfg();
    c.trailing_activation_pct = 0.006;
    c.trailing_distance_pct = 0.003;
    PositionManager pm(c);
    Position p = long_pos(pm);
    p.tp_price = 110; // hors de portée
    assert(!pm.check_exits(p, 100.5, 1100));
    assert(!p.trail_active);
    assert(!pm.check_exits(p, 100.7, 1100)); // +0.7 % : activation
    assert(p.trail_active);
    CHECK_NEAR(p.trail_price, 100.7 * 0.997, 1e-9);
    assert(!pm.check_exits(p, 101.0, 1100)); // nouveau plus haut
    CHECK_NEAR(p.high_water, 101.0, 1e-12);
    CHECK_NEAR(p.trail_price, 101.0 * 0.997, 1e-9);
    assert(!pm.check_exits(p, 100.8, 1100));
    assert(is(pm.check_exits(p, 100.6, 1100), "trailing_stop")); // 100.697 touché
    // le trailing ne recule jamais
    CHECK_NEAR(p.trail_price, 101.0 * 0.997, 1e-9);
}

// Long E=100, 10x (marge 10), mmr 5 % : liq = 90 / 0.95 = 94.7368.
// Le garde-fou sort à distance <= guard 0.2 % + frais de liquidation 0.5 % = 0.7 % :
//   95.6 -> (95.6 - 94.7368) / 95.6 = 0.903 %, on garde ;
//   95.3 -> 0.591 %, on sort (alors qu'avec 0.2 % seul, on resterait).
static void liq_guard_accounts_for_liquidation_fee() {
    PositionManager pm(base_cfg());
    Position p;
    p.side = Side::Long;
    p.entry_price = 100;
    p.qty = 1;
    p.leverage = 10;
    p.margin = 10;
    p.mmr = 0.05;
    p.liq_fee = 0.005;
    p.opened_ts = 1000;
    pm.init_levels(p, 0.2, 0.2); // SL très lointain : seul le garde-fou parle
    assert(!pm.check_exits(p, 95.6, 1100));
    assert(is(pm.check_exits(p, 95.3, 1100), "liq_guard"));
    assert(p.liq_distance_pct(95.3) > 0.002); // le seuil nu (0.2 %) n'aurait pas suffi

    Position s = p; // short symétrique : liq = 110 / 1.05 = 104.7619
    s.side = Side::Short;
    pm.init_levels(s, 0.2, 0.2);
    assert(!pm.check_exits(s, 104.0, 1100));
    assert(is(pm.check_exits(s, 104.1, 1100), "liq_guard")); // (104.7619 - 104.1) / 104.1 = 0.636 %
}

int main() {
    levels();
    sl_tp_long();
    sl_tp_short();
    grace_period_emergency_stop();
    time_exits();
    trailing();
    liq_guard_accounts_for_liquidation_fee();
    std::puts("test_position_manager OK");
}
