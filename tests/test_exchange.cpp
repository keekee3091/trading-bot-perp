#include "check.hpp"
#include "perp/exchange.hpp"
#include "perp/live_exchange.hpp"

using namespace perp;

static Instrument inst(double max_lev = 20) {
    Instrument i;
    i.iid = 1;
    i.max_leverage = max_lev;
    i.min_notional = 10;
    i.taker_fee = 0.0004;
    i.liquidation_fee = 0.005;
    return i; // mmr = 0.5 / 20 = 0.025
}

static Tick tick(double ts, double px, double funding = 0.0) {
    Tick t;
    t.ts = ts;
    t.mark = t.index = px;
    t.funding_rate = funding;
    return t;
}

constexpr double H = 3600.0;

// Long q=2, 10x, slippage 0.1 %, spread 0, taker 0.04 %, funding 1e-4/h.
//   entrée : fill 100 x 1.001 = 100.1, notionnel 200.2, marge 20.02, frais 0.08008
//   funding : une heure franchie, 2 x 105 x 1e-4 = 0.021 payé
//   sortie à 110 : fill 110 x 0.999 = 109.89, frais 2 x 109.89 x 0.0004 = 0.087912
//   PnL brut 2 x (109.89 - 100.1) = 19.58
//   net = 19.58 - 0.08008 - 0.087912 - 0.021 = 19.391008
static void long_net_pnl_with_fees_and_funding() {
    PaperExchange ex(1000, 0.001, 0.0);
    const Instrument i = inst();
    Position* p = ex.market_open(i, Side::Long, 2, 10, tick(1000 * H + 100, 100));
    assert(p);
    CHECK_NEAR(p->entry_price, 100.1, 1e-9);
    CHECK_NEAR(p->margin, 20.02, 1e-9);
    CHECK_NEAR(p->fees_paid, 0.08008, 1e-9);
    CHECK_NEAR(ex.balance(), 1000 - 20.02 - 0.08008, 1e-9);

    assert(ex.on_tick(i, tick(1000 * H + 200, 102, 1e-4)).empty()); // même heure : pas de funding
    CHECK_NEAR(p->funding_paid, 0.0, 1e-12);
    assert(ex.on_tick(i, tick(1001 * H + 10, 105, 1e-4)).empty());
    CHECK_NEAR(p->funding_paid, 0.021, 1e-9);

    const auto t = ex.market_close(i, tick(1001 * H + 60, 110, 1e-4), "test");
    assert(t);
    CHECK_NEAR(t->exit_price, 109.89, 1e-9);
    CHECK_NEAR(t->pnl, 19.391008, 1e-9);
    CHECK_NEAR(t->pnl_pct, 19.391008 / 20.02, 1e-9);
    CHECK_NEAR(t->fees, 0.08008 + 0.087912, 1e-9);
    CHECK_NEAR(t->funding, 0.021, 1e-9);
    CHECK_NEAR(ex.balance(), 1000 + 19.391008, 1e-9);
    CHECK_NEAR(ex.equity(), 1000 + t->pnl, 1e-9);
    assert(ex.position(1) == nullptr);
}

// Short q=1, 5x : fill bid 100 x 0.999 = 99.9, marge 19.98, frais 0.03996.
// Funding > 0 : le short reçoit, 1 x 98 x 1e-4 = 0.0098.
// Sortie à 95 : fill 95 x 1.001 = 95.095, frais 0.038038, PnL brut 4.805.
// net = 4.805 - 0.03996 - 0.038038 + 0.0098 = 4.736802
static void short_net_pnl_with_fees_and_funding() {
    PaperExchange ex(1000, 0.001, 0.0);
    const Instrument i = inst();
    Position* p = ex.market_open(i, Side::Short, 1, 5, tick(2000 * H + 5, 100));
    assert(p);
    CHECK_NEAR(p->entry_price, 99.9, 1e-9);
    ex.on_tick(i, tick(2001 * H + 5, 98, 1e-4));
    CHECK_NEAR(p->funding_paid, -0.0098, 1e-9);
    const auto t = ex.market_close(i, tick(2001 * H + 30, 95), "test");
    assert(t);
    CHECK_NEAR(t->pnl, 4.736802, 1e-9);
    CHECK_NEAR(ex.total_funding(), -0.0098, 1e-9);
}

// Deux heures franchies en un tick : deux charges.
static void funding_charged_per_hour_crossed() {
    PaperExchange ex(1000, 0.0, 0.0);
    const Instrument i = inst();
    Position* p = ex.market_open(i, Side::Long, 1, 10, tick(3000 * H + 100, 100));
    assert(p);
    ex.on_tick(i, tick(3002 * H + 1, 100, 2e-4)); // 2 x (1 x 100 x 2e-4)
    CHECK_NEAR(p->funding_paid, 0.04, 1e-12);
}

// Long q=1, 10x, sans slippage ni spread, mmr 5 % : marge 10, frais 0.04, liq 90 / 0.95 = 94.7368.
//   tick à 94.7 : fill 94.7, frais de liquidation 94.7 x (0.0004 + 0.005) = 0.51138
//   rendu = 10 + (94.7 - 100) - 0.51138 = 4.18862, net = 4.18862 - 10 - 0.04 = -5.85138
static void long_liquidation_exact() {
    PaperExchange ex(1000, 0.0, 0.0);
    Instrument i = inst();
    i.maintenance_margin_rate = 0.05;
    Position* p = ex.market_open(i, Side::Long, 1, 10, tick(4000 * H + 1, 100));
    assert(p);
    CHECK_NEAR(p->liq_price(), 94.7368421052632, 1e-9);
    assert(ex.on_tick(i, tick(4000 * H + 2, 94.74)).empty()); // juste au-dessus
    const auto out = ex.on_tick(i, tick(4000 * H + 3, 94.7));
    assert(out.size() == 1);
    assert(out[0].reason == "liquidation");
    CHECK_NEAR(out[0].exit_price, 94.7, 1e-12);
    CHECK_NEAR(out[0].pnl, -5.85138, 1e-9);
    CHECK_NEAR(out[0].fees, 0.04 + 0.51138, 1e-9);
    assert(ex.liquidations() == 1);
    assert(ex.position(1) == nullptr);
    CHECK_NEAR(ex.balance(), 1000 - 5.85138, 1e-9);
}

// Short symétrique : liq (100 + 10) / 1.05 = 104.7619 ; tick à 105 :
// frais 105 x 0.0054 = 0.567, rendu 10 - 5 - 0.567 = 4.433, net = 4.433 - 10 - 0.04 = -5.607.
static void short_liquidation_exact() {
    PaperExchange ex(1000, 0.0, 0.0);
    Instrument i = inst();
    i.maintenance_margin_rate = 0.05;
    Position* p = ex.market_open(i, Side::Short, 1, 10, tick(5000 * H + 1, 100));
    assert(p);
    CHECK_NEAR(p->liq_price(), 104.761904761905, 1e-9);
    assert(ex.on_tick(i, tick(5000 * H + 2, 104.7)).empty());
    const auto out = ex.on_tick(i, tick(5000 * H + 3, 105));
    assert(out.size() == 1 && out[0].reason == "liquidation");
    CHECK_NEAR(out[0].pnl, -5.607, 1e-9);
}

// Tick qui saute le seuil : perte plafonnée à la marge (isolation), le reste est un shortfall.
// Long q=1, 20x, marge 5 ; tick à 90 : 5 - 10 - 90 x 0.0054 = -5.486 -> rendu 0, net = -5 - 0.04.
static void gap_through_liquidation_caps_loss_at_margin() {
    PaperExchange ex(1000, 0.0, 0.0);
    const Instrument i = inst();
    ex.market_open(i, Side::Long, 1, 20, tick(6000 * H + 1, 100));
    const auto out = ex.on_tick(i, tick(6000 * H + 2, 90));
    assert(out.size() == 1);
    CHECK_NEAR(out[0].pnl, -5.04, 1e-9);
    CHECK_NEAR(ex.shortfall(), 5.486, 1e-9);
    CHECK_NEAR(ex.balance(), 1000 - 5.04, 1e-9);
}

static void rejections() {
    PaperExchange ex(100, 0.0, 0.0);
    const Instrument i = inst(10);
    assert(!ex.market_open(i, Side::Long, 1, 11, tick(1, 100)));   // levier > max
    assert(!ex.market_open(i, Side::Long, 1, 0.5, tick(1, 100)));  // levier < 1
    assert(!ex.market_open(i, Side::Long, 0.05, 5, tick(1, 100))); // notionnel 5 < min 10
    assert(!ex.market_open(i, Side::Long, 2, 1, tick(1, 100)));    // marge 200 > solde 100
    assert(ex.market_open(i, Side::Long, 1, 2, tick(1, 100)));
    assert(!ex.market_open(i, Side::Long, 1, 2, tick(2, 100)));    // déjà en position
}

// Cohérence estimateur / fills : ouvrir puis fermer au même tick coûte exactement
// round_trip_cost x prix x quantité. Chiffré : slippage 0.1 %, spread 0.04 %, taker 0.04 % :
//   entrée 100 x 1.0002 x 1.001 = 100.12002, sortie 100 x 0.9998 x 0.999 = 99.88002
//   (0.24 + 0.0004 x 200.00004) / 100 = 0.00320000016
static void round_trip_cost_matches_fills() {
    const Instrument i = inst();
    for (Side s : {Side::Long, Side::Short}) {
        PaperExchange ex(1000, 0.001, 0.0004);
        const Tick t = tick(7000 * H + 1, 100);
        const double cost = ex.round_trip_cost(i, t, s, 0);
        CHECK_NEAR(cost, 0.00320000016, 1e-12);
        assert(ex.market_open(i, s, 3, 5, t));
        const auto c = ex.market_close(i, t, "x");
        assert(c);
        CHECK_NEAR(c->pnl, -cost * 100 * 3, 1e-9);
    }
    // funding estimé : les longs paient quand le taux est positif, les shorts n'en tiennent pas compte
    PaperExchange ex(1000, 0.001, 0.0004);
    const Tick f = tick(1, 100, 1e-4);
    CHECK_NEAR(ex.round_trip_cost(i, f, Side::Long, 3600) - ex.round_trip_cost(i, f, Side::Short, 3600),
               1e-4, 1e-12);
}

// Bid/ask du tick prioritaires sur le spread par défaut.
static void tick_book_used() {
    PaperExchange ex(1000, 0.0, 0.5); // spread par défaut énorme, ignoré
    const Instrument i = inst();
    Tick t = tick(1, 100);
    t.bid = 99.9;
    t.ask = 100.1;
    Position* p = ex.market_open(i, Side::Long, 1, 5, t);
    assert(p);
    CHECK_NEAR(p->entry_price, 100.1, 1e-12);
}

static void taker_override() {
    PaperExchange ex(1000, 0.0, 0.0, 0.001);
    const Instrument i = inst();
    Position* p = ex.market_open(i, Side::Long, 1, 5, tick(1, 100));
    assert(p);
    CHECK_NEAR(p->fees_paid, 0.1, 1e-12);
}

static void live_is_a_stub() {
    bool threw = false;
    try {
        LiveExchange live;
    } catch (const std::logic_error&) {
        threw = true;
    }
    assert(threw);
}

int main() {
    long_net_pnl_with_fees_and_funding();
    short_net_pnl_with_fees_and_funding();
    funding_charged_per_hour_crossed();
    long_liquidation_exact();
    short_liquidation_exact();
    gap_through_liquidation_caps_loss_at_margin();
    rejections();
    round_trip_cost_matches_fills();
    tick_book_used();
    taker_override();
    live_is_a_stub();
    std::puts("test_exchange OK");
}
