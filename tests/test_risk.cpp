#include "check.hpp"
#include "perp/risk.hpp"

using namespace perp;

static ClosedTrade trade(double pnl, double pnl_pct) {
    ClosedTrade t;
    t.pnl = pnl;
    t.pnl_pct = pnl_pct;
    return t;
}

static Instrument inst50() {
    Instrument i;
    i.max_leverage = 50; // mmr = 0.5 / 50 = 1 %
    i.liquidation_fee = 0.005;
    i.min_notional = 10;
    return i;
}

// D = buf x sl + frais de liquidation + garde = 2 x 0.01 + 0.005 + 0.002 = 0.027
//   long  : 1/L = 0.01 + 0.027 x 0.99 = 0.03673  -> L = 27.2256...
//   short : 1/L = 0.01 + 0.027 x 1.01 = 0.03727  -> L = 26.8315...
static void leverage_cap_vs_sl() {
    Config c;
    c.leverage = 50;
    RiskManager r(c, 1000);
    const Instrument i = inst50();
    CHECK_NEAR(r.choose_leverage(i, 0.01, Side::Long), 1.0 / 0.03673, 1e-9);
    CHECK_NEAR(r.choose_leverage(i, 0.01, Side::Short), 1.0 / 0.03727, 1e-9);

    // Propriété : à ce levier, la liquidation est exactement à D du prix d'entrée.
    for (Side s : {Side::Long, Side::Short}) {
        const double lev = r.choose_leverage(i, 0.01, s);
        Position p;
        p.side = s;
        p.entry_price = 100;
        p.qty = 1;
        p.leverage = lev;
        p.margin = 100 / lev;
        p.mmr = i.mmr();
        CHECK_NEAR(p.liq_distance_pct(100), 0.027, 1e-12);
    }
}

static void leverage_bounded_by_target_and_max() {
    Config c;
    c.leverage = 5;
    RiskManager r(c, 1000);
    CHECK_NEAR(r.choose_leverage(inst50(), 0.001, Side::Long), 5.0, 1e-12); // cible
    c.leverage = 100;
    c.liq_guard_pct = 0;
    RiskManager r2(c, 1000);
    Instrument i = inst50();
    i.liquidation_fee = 0;
    // SL minuscule : le plafond liquidation (~99.98x) dépasse max_leverage, c'est max_leverage qui borne
    CHECK_NEAR(r2.choose_leverage(i, 1e-6, Side::Long), 50.0, 1e-12);
    // SL énorme : plancher à 1x
    CHECK_NEAR(r2.choose_leverage(i, 5.0, Side::Long), 1.0, 1e-12);
}

// equity 1000, risque 1 % = 10, SL 1 % -> notionnel 1000 ; levier 5 -> marge 200.
static void sizing() {
    Config c;
    RiskManager r(c, 1000);
    const Instrument i = inst50();
    SizeDecision s = r.size(1000, i, 0.01, Side::Long);
    CHECK_NEAR(s.notional, 1000, 1e-9);
    CHECK_NEAR(s.leverage, 5, 1e-9);
    CHECK_NEAR(s.margin, 200, 1e-9);
    CHECK_NEAR(s.risk_usdc, 10, 1e-9);

    // SL 0.1 % : notionnel 10000, plafonné à 3 x equity = 3000 puis au net 2 x equity = 2000 : marge 400
    s = r.size(1000, i, 0.001, Side::Long);
    CHECK_NEAR(s.notional, 2000, 1e-9);
    CHECK_NEAR(s.margin, 400, 1e-9);

    // Sans plafond d'exposition : 3000, marge 600 > 50 % -> marge 500, notionnel 2500
    Config free = c;
    free.max_net_exposure_pct = 0;
    free.max_gross_exposure_pct = 0;
    s = RiskManager(free, 1000).size(1000, i, 0.001, Side::Long);
    CHECK_NEAR(s.margin, 500, 1e-9);
    CHECK_NEAR(s.notional, 2500, 1e-9);

    // Marge restante sous le plafond net (2000) : net long 1500 -> un long ajoute 500 au plus ;
    // un short peut aller jusqu'à 3500 en net, mais le brut (4000 - 1500) borne à 2500, puis le sizing à 3000 : 2500
    RiskManager e(c, 1000);
    e.set_exposure("A", Side::Long, 1500);
    CHECK_NEAR(e.size(1000, i, 0.001, Side::Long).notional, 500, 1e-9);
    CHECK_NEAR(e.size(1000, i, 0.001, Side::Short).notional, 2500, 1e-9);
    // Plafond atteint : plus d'entrée du même côté (notionnel 0 = refus)
    e.set_exposure("A", Side::Long, 2000);
    assert(e.size(1000, i, 0.001, Side::Long).notional == 0);

    // Trop petit : 0.5 de risque / 0.1 = 5 < min 10 -> pas d'entrée
    assert(r.size(50, i, 0.1, Side::Long).notional == 0);
}

// 20 trades : 12 gains +0.10, 8 pertes -0.05. p = 0.6, b = 2, f* = 0.6 - 0.4/2 = 0.4,
// mult = scaling 0.5 x 0.4 / 0.25 = 0.8.
static void kelly() {
    Config c;
    RiskManager r(c, 1000);
    for (int k = 0; k < 4; ++k) r.record_trade(trade(1, 0.10), 1e9);
    assert(r.kelly_mult() == 1.0); // pas assez d'historique (< window/2 = 15)
    for (int k = 0; k < 20; ++k) r.record_trade(k % 5 < 3 ? trade(1, 0.10) : trade(-1, -0.05), 1e9 + k * 1e5);
    // 4 gains de plus + 12 gains + 8 pertes sur 24 -> on se place sur la fenêtre de 30 : recalcul direct
    // gains 16, pertes 8 : p = 2/3, b = 2, f* = 2/3 - (1/3)/2 = 0.5, mult = 0.5 x 0.5 / 0.25 = 1.0
    CHECK_NEAR(r.kelly_mult(), 1.0, 1e-9);

    RiskManager r2(c, 1000);
    for (int k = 0; k < 20; ++k) r2.record_trade(k % 5 < 3 ? trade(1, 0.10) : trade(-1, -0.05), 1e9 + k * 1e5);
    CHECK_NEAR(r2.kelly_mult(), 0.8, 1e-9);

    // Espérance négative : plancher
    RiskManager r3(c, 1000);
    for (int k = 0; k < 20; ++k) r3.record_trade(k % 5 < 2 ? trade(1, 0.05) : trade(-1, -0.10), 1e9 + k * 1e5);
    CHECK_NEAR(r3.kelly_mult(), c.kelly_min_mult, 1e-12);

    // Que des gains : pas de ratio défini -> 1.0
    RiskManager r4(c, 1000);
    for (int k = 0; k < 20; ++k) r4.record_trade(trade(1, 0.1), 1e9 + k * 1e5);
    CHECK_NEAR(r4.kelly_mult(), 1.0, 1e-12);

    // Plafond haut
    RiskManager r5(c, 1000);
    for (int k = 0; k < 20; ++k) r5.record_trade(k % 10 == 0 ? trade(-1, -0.01) : trade(1, 0.5), 1e9 + k * 1e5);
    CHECK_NEAR(r5.kelly_mult(), c.kelly_max_mult, 1e-12);

    c.kelly_enabled = 0;
    RiskManager r6(c, 1000);
    for (int k = 0; k < 20; ++k) r6.record_trade(k % 5 < 3 ? trade(1, 0.10) : trade(-1, -0.05), 1e9 + k * 1e5);
    CHECK_NEAR(r6.kelly_mult(), 1.0, 1e-12);
}

// Sizing par levier de compte (mode 1) : mmr 1 %, max 50x, equity 1000, margin_frac 0.95.
//   m = 5            -> notionnel 5000, levier de position 5000 / 950 = 5.263, marge 950
//   m = 100 (borné)  -> max_leverage x margin_frac = 47.5 -> notionnel 47500, levier 50, marge 950
//   cible de vol 20 %, vol réalisée 10 % -> m = 2 : notionnel 2000, levier 2.105, marge 950
//   cible 20 %, vol 40 % -> m = 0.5 : notionnel 500, levier 1, marge 500 (pas de levier < 1)
//   plafond liquidation (D = 2 x 0.01 + 0.005 + 0.002 = 0.027 -> L <= 27.2256 long) : m <= 25.87
static void leverage_sizing_mode() {
    Config c;
    c.sizing_mode = 1;
    c.apply_liq_cap = 0;
    c.account_leverage = 5;
    const Instrument i = inst50();
    SizeDecision s = RiskManager(c, 1000).size(1000, i, 0.01, Side::Long);
    CHECK_NEAR(s.notional, 5000, 1e-9);
    CHECK_NEAR(s.leverage, 5000.0 / 950.0, 1e-9);
    CHECK_NEAR(s.margin, 950, 1e-9);
    c.account_leverage = 100;
    s = RiskManager(c, 1000).size(1000, i, 0.01, Side::Long);
    CHECK_NEAR(s.notional, 47500, 1e-9);
    CHECK_NEAR(s.leverage, 50, 1e-9);
    CHECK_NEAR(s.margin, 950, 1e-9);
    // les plafonds d'exposition du mode risque ne s'appliquent pas ici
    c.max_net_exposure_pct = 0.5;
    CHECK_NEAR(RiskManager(c, 1000).size(1000, i, 0.01, Side::Long).notional, 47500, 1e-9);

    c = Config();
    c.sizing_mode = 1;
    c.apply_liq_cap = 0;
    c.vol_target_annual = 0.20;
    s = RiskManager(c, 1000).size(1000, i, 0.01, Side::Long, 0.10);
    CHECK_NEAR(s.notional, 2000, 1e-9);
    CHECK_NEAR(s.leverage, 2000.0 / 950.0, 1e-9);
    CHECK_NEAR(s.margin, 950, 1e-9);
    s = RiskManager(c, 1000).size(1000, i, 0.01, Side::Long, 0.40);
    CHECK_NEAR(s.notional, 500, 1e-9);
    CHECK_NEAR(s.leverage, 1, 1e-12);
    CHECK_NEAR(s.margin, 500, 1e-9);
    assert(RiskManager(c, 1000).size(1000, i, 0.01, Side::Long, 0.0).notional == 0); // vol inconnue
    // vol très faible : le plafond liquidation borne le levier de compte
    c.apply_liq_cap = 1;
    c.vol_target_annual = 0.20;
    s = RiskManager(c, 1000).size(1000, i, 0.01, Side::Long, 0.001); // m voulu = 200
    CHECK_NEAR(s.notional / 1000, 27.2256 * 0.95, 1e-3);
    assert(s.leverage <= 27.23);
}

static void net_and_gross_exposure() {
    Config c;
    c.max_net_exposure_pct = 2.0; // plafond net 2000 sur equity 1000
    c.max_gross_exposure_pct = 4.0;
    RiskManager r(c, 1000);
    r.set_exposure("A", Side::Long, 1000);
    r.set_exposure("B", Side::Short, 400);
    CHECK_NEAR(r.net_exposure(), 600, 1e-9);
    CHECK_NEAR(r.gross_exposure(), 1400, 1e-9);

    assert(std::string(r.check_entry(0, Side::Long, 1500, 1000)) == "net_exposure_cap"); // 2100 > 2000
    assert(r.check_entry(0, Side::Long, 1300, 1000) == nullptr);                         // 1900
    assert(r.check_entry(0, Side::Short, 1500, 1000) == nullptr);                        // -900

    // Entrée qui réduit un net déjà au-dessus du plafond : autorisée
    c.max_net_exposure_pct = 1.0;
    RiskManager r2(c, 1000);
    r2.set_exposure("A", Side::Long, 1500);
    assert(r2.check_entry(0, Side::Short, 200, 1000) == nullptr);                        // net 1300 < 1500
    assert(std::string(r2.check_entry(0, Side::Long, 10, 1000)) == "net_exposure_cap");

    // Plafond brut : 3000 + 1000 + 500 = 4500 > 4000, net désactivé
    c.max_net_exposure_pct = 0;
    RiskManager r3(c, 1000);
    r3.set_exposure("A", Side::Long, 1000);
    r3.set_exposure("B", Side::Short, 3000);
    assert(std::string(r3.check_entry(0, Side::Long, 500, 1000)) == "gross_exposure_cap");
    r3.clear_exposure("B");
    assert(r3.check_entry(0, Side::Long, 500, 1000) == nullptr);
}

static void cooldowns_and_breakers() {
    Config c; // cooldown perte 60 s, 3 pertes de suite -> pause 900 s
    RiskManager r(c, 1000);
    r.record_trade(trade(-1, -0.01), 1000);
    assert(std::string(r.check_entry(1030, Side::Long, 100, 1000)) == "cooldown");
    assert(r.check_entry(1061, Side::Long, 100, 1000) == nullptr);
    r.record_trade(trade(-1, -0.01), 2000);
    r.record_trade(trade(-1, -0.01), 3000); // 3e perte de suite
    assert(std::string(r.check_entry(3500, Side::Long, 100, 1000)) == "cooldown");
    assert(r.check_entry(3901, Side::Long, 100, 1000) == nullptr);

    // Verrou perte journalier : -50 sur start 1000 (5 %) -> pause jusqu'à minuit UTC
    RiskManager d(c, 1000);
    const double day0 = 20000.0 * 86400;
    d.record_trade(trade(-50, -0.1), day0 + 3600);
    assert(std::string(d.check_entry(day0 + 80000, Side::Long, 100, 1000)) == "cooldown");
    assert(d.check_entry(day0 + 86400, Side::Long, 100, 1000) == nullptr);

    // Arrêt de session : -100 (10 %)
    RiskManager h(c, 1000);
    h.record_trade(trade(-100, -0.5), 5000);
    assert(h.halted());
    assert(std::string(h.check_entry(1e12, Side::Long, 100, 1000)) == "halt");

    // Un gain remet le compteur de pertes de suite à zéro
    RiskManager w(c, 1000);
    w.record_trade(trade(-1, -0.01), 100);
    w.record_trade(trade(-1, -0.01), 300);
    w.record_trade(trade(1, 0.01), 500);
    w.record_trade(trade(-1, -0.01), 700);
    assert(w.check_entry(900, Side::Long, 100, 1000) == nullptr); // pas de pause longue
}

static void max_entries_per_hour() {
    Config c;
    c.max_entries_per_hour = 3;
    RiskManager r(c, 1000);
    for (int k = 0; k < 3; ++k) {
        assert(r.check_entry(100.0 * k, Side::Long, 100, 1000) == nullptr);
        r.on_entry(100.0 * k);
    }
    assert(std::string(r.check_entry(400, Side::Long, 100, 1000)) == "max_entries_per_hour");
    assert(r.check_entry(3601, Side::Long, 100, 1000) == nullptr); // la première a expiré
}

int main() {
    leverage_cap_vs_sl();
    leverage_bounded_by_target_and_max();
    sizing();
    leverage_sizing_mode();
    kelly();
    net_and_gross_exposure();
    cooldowns_and_breakers();
    max_entries_per_hour();
    std::puts("test_risk OK");
}
