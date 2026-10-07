// Tests du backtest passif de market making : fills et PnL calculés à la main, sens des fills,
// invariant de comptabilité, déterminisme, flux non informé (le MM gagne) et flux informé (il perd).
#include <cmath>
#include <cstdio>
#include <fstream>
#include <random>
#include <vector>

#include "check.hpp"
#include "perp/mm.hpp"

using namespace perp;

namespace {

constexpr double T0 = 1791158400.0 + 54000.0; // lundi 2026-10-05 15:00 UTC

MmData flat_data(double mark = 100.0, double secs = 4000) {
    MmData d;
    d.symbol = "TEST";
    d.category = "crypto";
    d.inst.max_leverage = 10; // mmr = 0.5 / 10 = 5 %
    d.inst.liquidation_fee = 0.005;
    d.inst.min_notional = 10;
    d.tick = 0.01;
    d.mark_interval_s = 60;
    for (double t = T0 - 120; t < T0 + secs; t += 60) d.mark.push_back({t, mark});
    return d;
}

Trade tr(double dt, double price, double qty, int dir) { return {T0 + dt, price, qty, dir, false}; }

// L = 1, inv_frac = 1 : plafond = equity = 1000 ; order_frac 0.1 : ordre de 100 de notionnel = 1 unité à 100.
MmParams base_params() {
    MmParams p;
    p.delta_bps = 10.0; // bid 99.9, ask 100.1
    p.leverage = 1.0;
    p.inv_frac = 1.0;
    p.order_frac = 0.1;
    p.equity = 1000.0;
    return p;
}

// ── fills et PnL à la main ────────────────────────────────────────────────
// Quotes : bid 99.9, ask 100.1, 1 unité chacune, frais maker 1.25 bps, mark constant 100, fenêtre de 30 s
// (une seule requote). Tape :
//   +1 s vendeur @99.90 x3   : optimiste servi (prix == quote), conservatrice non (pas strictement au-delà)
//   +2 s vendeur @99.89 x0.4 : au-delà : conservatrice servie de 0.4 ; optimiste : bid déjà servi (1 unité)
//   +3 s acheteur @100.10 x5 : optimiste : ask servi de 1 ; conservatrice : égalité, non servi
//   +4 s acheteur @100.20 x0.25 : au-delà : conservatrice servie de 0.25
void optimistic_hand_computed() {
    MmData d = flat_data();
    d.trades = {tr(1, 99.90, 3, -1), tr(2, 99.89, 0.4, -1), tr(3, 100.10, 5, +1), tr(4, 100.20, 0.25, +1)};
    MmParams p = base_params();
    p.fill_model = 0;
    const MmResult r = run_mm(d, p, T0, T0 + 30);
    assert(r.fills.size() == 2);
    assert(r.fills[0].side == +1 && r.fills[1].side == -1);
    CHECK_NEAR(r.fills[0].price, 99.9, 1e-12);
    CHECK_NEAR(r.fills[0].qty, 1.0, 1e-12);
    CHECK_NEAR(r.fills[1].price, 100.1, 1e-12);
    CHECK_NEAR(r.fills[1].qty, 1.0, 1e-12);
    // capture 1 x (100 - 99.9) + 1 x (100.1 - 100) = 0.2 ; frais 1.25e-4 x (99.9 + 100.1) = 0.025
    CHECK_NEAR(r.spread_capture, 0.2, 1e-9);
    CHECK_NEAR(r.maker_fees, 0.025, 1e-9);
    CHECK_NEAR(r.end_equity, 1000.175, 1e-9);
    CHECK_NEAR(r.end_inventory_units, 0.0, 1e-12);
}

void conservative_hand_computed() {
    MmData d = flat_data();
    d.trades = {tr(1, 99.90, 3, -1), tr(2, 99.89, 0.4, -1), tr(3, 100.10, 5, +1), tr(4, 100.20, 0.25, +1)};
    MmParams p = base_params();
    p.fill_model = 1;
    const MmResult r = run_mm(d, p, T0, T0 + 30);
    assert(r.fills.size() == 2);
    CHECK_NEAR(r.fills[0].qty, 0.4, 1e-12);   // l'égalité du premier trade n'a pas servi
    CHECK_NEAR(r.fills[1].qty, 0.25, 1e-12);  // l'égalité du troisième non plus
    // capture 0.4 x 0.1 + 0.25 x 0.1 = 0.065 ; frais 1.25e-4 x (0.4 x 99.9 + 0.25 x 100.1) = 0.008123125
    CHECK_NEAR(r.spread_capture, 0.065, 1e-9);
    CHECK_NEAR(r.maker_fees, 0.008123125, 1e-12);
    CHECK_NEAR(r.end_equity, 1000.056876875, 1e-9);
    CHECK_NEAR(r.end_inventory_units, 0.15, 1e-12);
}

// File d'attente : 5 de notionnel... ici 20 de notionnel = 0.2 unité devant nous ; le trade de 0.4 au-delà
// consomme d'abord la file (0.2) puis nous sert de 0.2 ; le suivant, de 0.3, nous sert du reste.
void queue_ahead_is_consumed_first() {
    MmData d = flat_data();
    d.trades = {tr(2, 99.89, 0.4, -1), tr(3, 99.88, 0.3, -1)};
    MmParams p = base_params();
    p.fill_model = 1;
    p.queue_ahead_notional = 20.0; // 0.2 unité à 100
    const MmResult r = run_mm(d, p, T0, T0 + 30);
    assert(r.fills.size() == 2);
    CHECK_NEAR(r.fills[0].qty, 0.2, 1e-12);
    CHECK_NEAR(r.fills[1].qty, 0.3, 1e-12);
}

// ── sens : un bid n'est servi que par un agresseur vendeur, un ask que par un acheteur ──
void direction_of_fills() {
    MmData d = flat_data();
    // agresseur ACHETEUR à 99.8 (sous notre bid) : ne sert pas notre bid ; agresseur vendeur à 100.2 : ne sert pas notre ask
    d.trades = {tr(1, 99.80, 5, +1), tr(2, 100.20, 5, -1)};
    MmParams p = base_params();
    assert(run_mm(d, p, T0, T0 + 30).fills.empty());
    p.require_side = false; // sans la condition de sens, ces prix serviraient les deux quotes
    assert(run_mm(d, p, T0, T0 + 30).fills.size() == 2);
    // et le cas normal : quote d'achat servie par un trade vendeur
    d.trades = {tr(1, 99.85, 5, -1)};
    p.require_side = true;
    const MmResult r = run_mm(d, p, T0, T0 + 30);
    assert(r.fills.size() == 1 && r.fills[0].side == +1 && r.end_inventory_units > 0);
}

// Arrondi au tick : bid vers le bas, ask vers le haut (tick 0.05 : 99.9 -> 99.90, 100.1 -> 100.10 ; delta 12 bps -> 99.88 -> 99.85)
void quotes_rounded_to_tick() {
    MmData d = flat_data();
    d.tick = 0.05;
    MmParams p = base_params();
    p.delta_bps = 12.0; // bid 99.88 -> 99.85 ; ask 100.12 -> 100.15
    d.trades = {tr(1, 99.86, 5, -1), tr(2, 100.14, 5, +1), tr(3, 99.85, 5, -1), tr(4, 100.15, 5, +1)};
    p.fill_model = 0;
    const MmResult r = run_mm(d, p, T0, T0 + 30);
    assert(r.fills.size() == 2); // 99.86 n'atteint pas 99.85, 100.14 n'atteint pas 100.15 ; les deux suivants oui
    CHECK_NEAR(r.fills[0].price, 99.85, 1e-12);
    CHECK_NEAR(r.fills[1].price, 100.15, 1e-12);
}

// ── funding sur l'inventaire ──
// Long 1 unité acheté à +1 s ; une heure pile est franchie (taux 1e-4 par heure) : le long paie 1 x 100 x 1e-4 = 0.01.
// equity = 1000 + 0.1 - 0.0124875 - 0.01 = 1000.0775125
void funding_on_inventory() {
    MmData d = flat_data(100.0, 5000);
    const double h = std::floor(T0 / 3600.0) * 3600.0; // heure pile précédente
    d.funding = {{h - 3600, 1e-4}, {h + 3600, 1e-4}};
    d.trades = {tr(1, 99.85, 5, -1)};
    MmParams p = base_params();
    const double t_end = h + 3600 + 300; // franchit h + 3600
    const MmResult r = run_mm(d, p, T0, t_end);
    CHECK_NEAR(r.funding, 0.01, 1e-12);
    CHECK_NEAR(r.end_equity, 1000.0775125, 1e-9);
}

// ── sortie taker quand l'inventaire dépasse le plafond ──
// L = 1, inv_frac 0.1 (plafond ~100), ordre 0.8 unité. Achat de 0.8 @99.9 ; le mark passe à 130 :
// equity = 920.07001 + 104 = 1024.07001, plafond 102.407001, notionnel 104 > plafond => sortie vers 0.5 x plafond.
//   qté = (104 - 51.2035005) / 130 = 0.406126919..., prix = 130 (1 - 4e-4) = 129.948, frais 4 bps
void taker_exit_on_cap() {
    MmData d = flat_data(100.0, 4000);
    for (auto& m : d.mark)
        if (m.ts >= T0 + 120) m.mark = 130.0;
    d.trades = {tr(1, 99.85, 5, -1)};
    MmParams p = base_params();
    p.inv_frac = 0.1;
    p.order_frac = 0.8;
    p.exit_half_spread_bps = 2.0;
    p.slippage_bps = 2.0;
    const MmResult r = run_mm(d, p, T0, T0 + 400);
    assert(r.fills.size() == 1);
    CHECK_NEAR(r.fills[0].qty, 0.8, 1e-12);
    assert(!r.exits.empty());
    const MmExit& e = r.exits[0];
    assert(e.side == -1 && !e.liquidation);
    CHECK_NEAR(e.qty, 0.40612691923076927, 1e-9);
    CHECK_NEAR(e.price, 129.948, 1e-9);
    CHECK_NEAR(e.fee, 0.021110152360080004, 1e-9);
    CHECK_NEAR(r.exit_cost, 0.021118599799996956, 1e-9);
    CHECK_NEAR(r.inventory_pnl, 24.0, 1e-9); // 0.8 x (130 - 100)
    // aucune récidive tant que le notionnel reste sous le plafond
    CHECK_NEAR(r.end_inventory_units, 0.3938730807692308, 1e-9);
}

// ── liquidation : levier 10x, 100 unités achetées @99.9, le mark tombe à 90 ──
// equity = 1000 - 9990 - 1.24875 + 9000 = 8.75 <= mm = 100 x 90 x 5 % = 450 : liquidation,
// prix 89.964, frais 100 x 89.964 x (4 bps + 0.5 %) = 48.58 : la marge est épuisée (perte plafonnée à zéro).
void liquidation() {
    MmData d = flat_data(100.0, 4000);
    for (auto& m : d.mark)
        if (m.ts >= T0 + 120) m.mark = 90.0;
    d.trades = {tr(1, 99.85, 500, -1)};
    MmParams p = base_params();
    p.leverage = 10.0;
    p.inv_frac = 1.0;
    p.order_frac = 1.0; // 10 000 de notionnel = 100 unités
    const MmResult r = run_mm(d, p, T0, T0 + 400);
    assert(r.fills.size() == 1);
    CHECK_NEAR(r.fills[0].qty, 100.0, 1e-9);
    assert(r.liquidations == 1 && r.bust);
    assert(!r.exits.empty() && r.exits[0].liquidation);
    CHECK_NEAR(r.exits[0].price, 89.964, 1e-9);
    CHECK_NEAR(r.exits[0].fee, 48.58056, 1e-9);
    CHECK_NEAR(r.end_equity, 0.0, 1e-9);
}

// ── tape synthétique : flux non informé / informé ─────────────────────────
struct Tape {
    MmData d;
};

// mid : 100 ; chaque trade : sens aléatoire, écart u ~ Exp(moyenne 3 bps) du côté de l'agresseur.
// informed : après chaque trade, le mid se déplace de kappa bps dans le sens de l'agresseur (impact permanent).
Tape make_tape(int n, bool informed, double kappa_bps, unsigned seed) {
    Tape t;
    t.d = flat_data(100.0, 0);
    t.d.mark.clear();
    std::mt19937_64 g(seed);
    auto uni = [&]() { return (static_cast<double>(g() >> 11) + 0.5) / 9007199254740992.0; };
    double mid = 100.0, ts = T0;
    double next_mark = T0 - 120;
    t.d.mark.push_back({next_mark, mid});
    for (int i = 0; i < n; ++i) {
        ts += 5.0;
        while (next_mark + 60 <= ts) { // un point de mark par minute : dernier mid du bucket
            next_mark += 60;
            t.d.mark.push_back({next_mark, mid});
        }
        const int dir = (g() & 1) ? +1 : -1;
        const double u = -3.0 * std::log(uni()) * 1e-4; // Exp, moyenne 3 bps
        const double price = mid * (1.0 + dir * u);
        t.d.trades.push_back({ts, std::round(price * 100) / 100.0, 5.0, dir, false}); // tick 0.01, 5 unités
        if (informed) mid *= 1.0 + dir * kappa_bps * 1e-4;
    }
    t.d.mark.push_back({next_mark + 60, mid});
    return t;
}

MmParams tape_params() {
    MmParams p;
    p.delta_bps = 2.0;
    p.skew_frac = 1.0;
    p.leverage = 1.0;
    p.inv_frac = 1.0;
    p.order_frac = 0.02; // ordres de 20 de notionnel : beaucoup de fills, peu de sorties taker
    p.equity = 1000.0;
    p.fill_model = 0;
    return p;
}

void uninformed_flow_market_maker_wins() {
    const Tape t = make_tape(20000, false, 0, 7);
    const double t1 = t.d.trades.back().ts;
    const MmResult r = run_mm(t.d, tape_params(), T0, t1);
    const MmMetrics m = compute_metrics(r, t.d);
    std::printf("  non informé : %zu fills, capture %.2f bps, PnL net %+.3f (%.3f%%), markout 60 s achat %+.2f vente %+.2f bps\n",
                r.fills.size(), m.capture_bps, m.net_pnl, m.net_pct, m.buy.trade_proxy[2].mean_bps, m.sell.trade_proxy[2].mean_bps);
    assert(r.fills.size() > 1000);
    assert(m.capture_bps > 1.0 && m.capture_bps < 4.0); // ~ delta = 2 bps vs mark
    assert(m.net_pnl > 0);                               // spread 2 bps - frais 1.25 bps > 0, pas de dérive
    assert(m.buy.trade_proxy[2].mean_bps > -0.5 && m.sell.trade_proxy[2].mean_bps > -0.5); // markouts ~ nuls ou positifs
}

void informed_flow_market_maker_loses() {
    const Tape t = make_tape(20000, true, 6.0, 7);
    const double t1 = t.d.trades.back().ts;
    const MmResult r = run_mm(t.d, tape_params(), T0, t1);
    const MmMetrics m = compute_metrics(r, t.d);
    std::printf("  informé (kappa 6 bps) : %zu fills, capture %.2f bps, PnL net %+.3f (%.3f%%), markout 60 s achat %+.2f vente %+.2f bps\n",
                r.fills.size(), m.capture_bps, m.net_pnl, m.net_pct, m.buy.trade_proxy[2].mean_bps, m.sell.trade_proxy[2].mean_bps);
    assert(r.fills.size() > 500);
    assert(m.buy.trade_proxy[2].mean_bps < 0 && m.sell.trade_proxy[2].mean_bps < 0); // sélection adverse mesurée
    assert(m.buy.mark[0].mean_bps < 0 && m.sell.mark[0].mean_bps < 0);
    assert(m.net_pnl < 0);
}

// ── invariant : equity finale = initiale + capture + inventaire - frais - funding - coût des sorties ──
void accounting_identity() {
    size_t total_exits = 0;
    for (bool informed : {false, true}) {
        Tape t = make_tape(15000, informed, 4.0, 11);
        t.d.funding = {{T0 - 7200, 2e-5}, {T0 + 3600, -3e-5}, {T0 + 7200, 5e-5}};
        // deux réglages : ordres modestes, puis plafond très serré (50) avec ordres de 25 : des sorties taker
        const double order_fracs[2] = {0.1, 0.5}, inv_fracs[2] = {0.3, 0.05};
        for (int cfg = 0; cfg < 2; ++cfg) {
            MmParams p = tape_params();
            p.order_frac = order_fracs[cfg];
            p.inv_frac = inv_fracs[cfg];
            for (int model : {0, 1}) {
                p.fill_model = model;
                p.queue_ahead_notional = 50;
                const MmResult r = run_mm(t.d, p, T0, t.d.trades.back().ts);
                assert(!r.bust);
                total_exits += r.exits.size();
                const double rhs = r.start_equity + r.spread_capture + r.inventory_pnl - r.maker_fees - r.taker_fees -
                                   r.liq_fees - r.funding - r.exit_cost;
                CHECK_NEAR(r.end_equity, rhs, 1e-8);
                // et la somme des PnL nets par fill passif et par sortie, au mark final, redonne la variation d'equity
                double sum = 0;
                for (const auto& f : r.fills) sum += f.side * f.qty * (r.end_ref - f.price) - f.fee;
                for (const auto& e : r.exits) sum += e.side * e.qty * (r.end_ref - e.price) - e.fee;
                sum -= r.funding;
                CHECK_NEAR(r.end_equity - r.start_equity, sum, 1e-8);
                std::printf("  identité (informé=%d, réglage=%d, modèle=%d) : %zu fills, %zu sorties taker, equity %.4f\n", informed,
                            cfg, model, r.fills.size(), r.exits.size(), r.end_equity);
            }
        }
    }
    assert(total_exits > 0); // le chemin des sorties taker est bien exercé par l'invariant
}

void determinism_and_random_baseline() {
    const Tape t = make_tape(8000, true, 3.0, 5);
    const double t1 = t.d.trades.back().ts;
    MmParams p = tape_params();
    const MmResult a = run_mm(t.d, p, T0, t1), b = run_mm(t.d, p, T0, t1);
    assert(a.fills.size() == b.fills.size() && a.end_equity == b.end_equity);
    p.random_delta = true;
    p.random_deltas = {1, 2, 3, 5, 8};
    p.seed = 3;
    const MmResult r1 = run_mm(t.d, p, T0, t1), r2 = run_mm(t.d, p, T0, t1);
    assert(r1.end_equity == r2.end_equity && r1.fills.size() == r2.fills.size());
    p.seed = 4;
    assert(run_mm(t.d, p, T0, t1).end_equity != r1.end_equity);
}

// ── spread effectif : trades à 99.98 (vente) et 100.02 (achat) : 4 bps ──
void effective_spread() {
    MmData d = flat_data();
    for (int i = 0; i < 100; ++i) {
        d.trades.push_back({T0 + i * 10.0, 100.02, 1, +1, false});
        d.trades.push_back({T0 + i * 10.0 + 1, 99.98, 1, -1, false});
    }
    long n = 0;
    const double s = effective_spread_bps(d, T0, T0 + 1000, 60, -1, &n);
    CHECK_NEAR(s, 4.0, 1e-6); // (100.02 - 99.98) / 100 = 4 bps
    assert(n >= 15);
}

void session_rules() {
    assert(in_session("crypto", 1791028800.0) == 1);       // samedi : le crypto est ouvert
    assert(in_session("equity", 1791028800.0) == 0);       // samedi midi : action fermée
    assert(in_session("equity", 1791212400.0) == 1);       // lundi 15:00 UTC : séance
    assert(in_session("equity", 1791158400.0 + 13 * 3600) == 0); // lundi 13:00 : avant 13:30
    assert(in_session("index", 1790974800.0) == 0);        // vendredi 21:00 : fermé
    assert(in_session("index", 1790974800.0 - 60) == 1);   // vendredi 20:59 : ouvert
    assert(in_session("index", 1791151140.0) == 0);        // dimanche 21:59 : fermé
    assert(in_session("index", 1791151200.0) == 1);        // dimanche 22:00 : ouvert
}

void csv_loading() {
    const std::string tp = "test_mm_trades_tmp.csv", mp = "test_mm_mark_tmp.csv";
    {
        std::ofstream f(tp);
        f << "ts,trade_id,side,price,qty,settlement\n1791158400100,1,long,100.5,2,0\n1791158400050,2,short,100.4,1,0\n"
             "1791158400200,3,long,100.6,0,0\ngarbage\n1791158400300,4,short,100.3,3,1\n";
        std::ofstream g(mp);
        g << "ts,mark\n1791158340000,0\n1791158400000,100.25\n";
    }
    const auto t = load_trades_csv(tp, true);
    assert(t.size() == 3); // la ligne de quantité nulle et la ligne illisible sont ignorées
    assert(t[0].ts < t[1].ts && t[0].dir == -1 && t[1].dir == +1 && t[2].settlement);
    const auto flipped = load_trades_csv(tp, false);
    assert(flipped[0].dir == +1 && flipped[1].dir == -1);
    const auto m = load_mark_csv(mp);
    assert(m.size() == 1); // mark 0 : ignoré
    CHECK_NEAR(m[0].mark, 100.25, 0);
    std::remove(tp.c_str());
    std::remove(mp.c_str());
}

} // namespace

int main() {
    optimistic_hand_computed();
    conservative_hand_computed();
    queue_ahead_is_consumed_first();
    direction_of_fills();
    quotes_rounded_to_tick();
    funding_on_inventory();
    taker_exit_on_cap();
    liquidation();
    uninformed_flow_market_maker_wins();
    informed_flow_market_maker_loses();
    accounting_identity();
    determinism_and_random_baseline();
    effective_spread();
    session_rules();
    csv_loading();
    std::puts("test_mm OK");
}
