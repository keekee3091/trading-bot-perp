#include "check.hpp"
#include "perp/types.hpp"

using namespace perp;

static Position make(Side side, double entry, double qty, double lev, double mmr) {
    Position p;
    p.side = side;
    p.entry_price = entry;
    p.qty = qty;
    p.leverage = lev;
    p.margin = qty * entry / lev;
    p.mmr = mmr;
    return p;
}

// E=100, q=2, 10x : marge 20, notionnel 200, mmr 5 %.
//   long  : P = (200 - 20) / (2 x 0.95) = 94.736842...
//   short : P = (200 + 20) / (2 x 1.05) = 104.761904...
static void liq_price_exact() {
    CHECK_NEAR(make(Side::Long, 100, 2, 10, 0.05).liq_price(), 180.0 / 1.9, 1e-9);
    CHECK_NEAR(make(Side::Long, 100, 2, 10, 0.05).liq_price(), 94.7368421052632, 1e-9);
    CHECK_NEAR(make(Side::Short, 100, 2, 10, 0.05).liq_price(), 220.0 / 2.1, 1e-9);
    CHECK_NEAR(make(Side::Short, 100, 2, 10, 0.05).liq_price(), 104.761904761905, 1e-9);
}

// Propriété : au prix de liquidation, equity == mmr x notionnel au prix courant.
static void liq_price_is_maintenance_threshold() {
    for (Side s : {Side::Long, Side::Short}) {
        Position p = make(s, 100, 2, 10, 0.05);
        p.funding_paid = 1.5;
        const double liq = p.liq_price();
        CHECK_NEAR(p.equity(liq), p.mmr * p.qty * liq, 1e-9);
    }
}

// Le funding payé rapproche la liquidation : C = 20 - 2 = 18, P = (200 - 18) / 1.9.
static void funding_moves_liq_price() {
    Position p = make(Side::Long, 100, 2, 10, 0.05);
    p.funding_paid = 2.0;
    CHECK_NEAR(p.liq_price(), 182.0 / 1.9, 1e-9);
    Position s = make(Side::Short, 100, 2, 10, 0.05);
    s.funding_paid = 2.0;
    CHECK_NEAR(s.liq_price(), 218.0 / 2.1, 1e-9);
    // funding reçu éloigne la liquidation
    s.funding_paid = -2.0;
    CHECK_NEAR(s.liq_price(), 222.0 / 2.1, 1e-9);
}

static void liq_distance() {
    Position p = make(Side::Long, 100, 2, 10, 0.05);
    CHECK_NEAR(p.liq_distance_pct(100), (100 - 180.0 / 1.9) / 100, 1e-12);
    Position s = make(Side::Short, 100, 2, 10, 0.05);
    CHECK_NEAR(s.liq_distance_pct(100), (220.0 / 2.1 - 100) / 100, 1e-12);
}

static void mmr_default_and_override() {
    Instrument i;
    i.max_leverage = 20;
    CHECK_NEAR(i.mmr(), 0.025, 1e-12); // 0.5 / 20
    i.mmr_factor = 0.4;
    CHECK_NEAR(i.mmr(), 0.02, 1e-12);
    i.maintenance_margin_rate = 0.03;
    CHECK_NEAR(i.mmr(), 0.03, 1e-12);
}

static void round_qty_floors() {
    Instrument i;
    i.qty_decimals = 3;
    CHECK_NEAR(i.round_qty(1.2349999), 1.234, 1e-12);
    CHECK_NEAR(i.round_qty(0.3), 0.3, 1e-12); // pas d'erreur flottante vers le bas
}

// p = (sl + c) / (sl + tp) : (0.01 + 0.001) / (0.01 + 0.015) = 0.44
static void breakeven() {
    CHECK_NEAR(breakeven_prob(0.01, 0.015, 0.001), 0.44, 1e-12);
    CHECK_NEAR(breakeven_prob(0.01, 0.015, 0.0), 0.4, 1e-12); // rr 1.5 : 1/(1+1.5)
    CHECK_NEAR(breakeven_prob(0.01, 0.015, 1.0), 1.0, 1e-12); // plafonné
    CHECK_NEAR(breakeven_prob(0.0, 0.0, 0.001), 1.0, 1e-12);
}

int main() {
    liq_price_exact();
    liq_price_is_maintenance_threshold();
    funding_moves_liq_price();
    liq_distance();
    mmr_default_and_override();
    round_qty_floors();
    breakeven();
    std::puts("test_types OK");
}
