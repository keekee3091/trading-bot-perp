#include "check.hpp"
#include "perp/validate.hpp"

using namespace perp;

static Config cfg0() {
    Config c;
    c.apply_text("symbol: BTC-USD\n");
    return c;
}

// Découpe chronologique 60/20/20 : ordre préservé, aucune bougie perdue ni partagée.
static void split_is_chronological() {
    const auto c = synthetic(1000, 60, 100, 5);
    const Split s = split_chrono(c);
    assert(s.train.size() == 600 && s.val.size() == 200 && s.test.size() == 200);
    assert(s.train.back().ts < s.val.front().ts && s.val.back().ts < s.test.front().ts);
    assert(s.train.front().ts == c.front().ts && s.test.back().ts == c.back().ts);
}

// Buy and hold sans coûts : 999 / 100 = 9.99 unités achetées à 100, vendues à 110 :
// PnL = 9.99 x 10 = 99.9, equity finale 1099.9.
static void buy_and_hold_hand_computed() {
    Config c = cfg0();
    c.slippage_pct = 0;
    c.default_spread_pct = 0;
    c.taker_fee = 0;
    const std::vector<Candle> cs = {{0, 100, 100, 100, 100}, {60, 100, 110, 100, 110}};
    const BacktestResult r = run_buy_hold(c, cs, 60, nullptr);
    CHECK_NEAR(r.end_equity, 1099.9, 1e-9);
    assert(r.trades.size() == 1 && r.trades[0].reason == "buy_and_hold_end");
    CHECK_NEAR(r.metrics().return_pct, 9.99, 1e-9);
}

// Avec coûts : slippage 0.1 %, spread 0, taker 0.04 %. Achat 100 x 1.001 = 100.1, vente 110 x 0.999 = 109.89.
// qté = floor(999 / (100.1 x 1.0004), 4 déc.) = 9.9760 ; net = 9.976 x (109.89 - 100.1) - frais.
static void buy_and_hold_with_costs_matches_identity() {
    Config c = cfg0();
    c.slippage_pct = 0.001;
    c.default_spread_pct = 0;
    const std::vector<Candle> cs = {{0, 100, 100, 100, 100}, {60, 100, 110, 100, 110}};
    const BacktestResult r = run_buy_hold(c, cs, 60, nullptr);
    const ClosedTrade& t = r.trades[0];
    CHECK_NEAR(t.qty, 9.976, 1e-9);
    CHECK_NEAR(t.pnl, t.qty * (109.89 - 100.1) - t.fees, 1e-9);
    CHECK_NEAR(r.end_equity, 1000 + t.pnl, 1e-9);
}

// Funding réel : taux publié à ts+37 ms, appliqué dès l'heure pile ; avant le premier point : 0.
static void funding_lookup() {
    const std::vector<FundingPoint> f = {{3600.037, 1e-4}, {7200.02, -2e-4}};
    size_t i = 0;
    CHECK_NEAR(funding_at(f, i, 100), 0.0, 0);
    CHECK_NEAR(funding_at(f, i, 3600.0), 1e-4, 0);   // tick à l'heure pile : le taux de cette heure
    CHECK_NEAR(funding_at(f, i, 5000), 1e-4, 0);
    CHECK_NEAR(funding_at(f, i, 7200.0), -2e-4, 0);
    CHECK_NEAR(funding_at(f, i, 1e9), -2e-4, 0);
}

// Une série de funding constante égale à la constante de config donne exactement le même backtest.
static void funding_series_equals_constant() {
    Config c = cfg0();
    c.signal_threshold = 0.6;
    c.min_edge = 0;
    c.bt_funding_rate_per_hour = 3e-5;
    const auto cs = synthetic(5000, 60, 100, 9);
    std::vector<FundingPoint> f;
    for (double t = cs.front().ts - 7200; t < cs.back().ts + 7200; t += 3600) f.push_back({t, 3e-5});
    RunOptions o;
    o.funding = &f;
    const auto a = run_backtest(c, cs, 60), b = run_backtest(c, cs, 60, o);
    assert(a.trades.size() > 0 && a.trades.size() == b.trades.size());
    assert(a.end_equity == b.end_equity);
    // un funding différent change bien le résultat
    for (auto& p : f) p.rate = 5e-4;
    const auto d = run_backtest(c, cs, 60, o);
    assert(d.end_equity != a.end_equity && d.funding != a.funding);
}

// Entrées aléatoires : déterministes par graine, comptabilité intacte, rythme calibré sur la cible.
static void random_baseline() {
    Config c = cfg0();
    const auto cs = synthetic(20000, 60, 100, 4);
    const auto strat = run_backtest(c, cs, 60);
    const double target = 60;
    RunOptions o;
    o.random_prob = 0.002;
    o.seed = 5;
    const auto a = run_backtest(c, cs, 60, o), b = run_backtest(c, cs, 60, o);
    assert(a.trades.size() > 0 && a.end_equity == b.end_equity);
    double sum = 0;
    for (const auto& t : a.trades) sum += t.pnl;
    CHECK_NEAR(a.end_equity, a.start_equity + sum, 1e-9);
    o.seed = 6;
    assert(run_backtest(c, cs, 60, o).end_equity != a.end_equity);

    const RandomStats st = run_random_baseline(c, cs, 60, nullptr, target, strat.end_equity - strat.start_equity, 24, 1, 4);
    assert(st.runs == 24 && st.p5 <= st.p50 && st.p50 <= st.p95);
    assert(st.mean_trades > 0.6 * target && st.mean_trades < 1.4 * target); // même rythme
    assert(st.frac_ge >= 0 && st.frac_ge <= 1);
    const RandomStats again = run_random_baseline(c, cs, 60, nullptr, target, 0, 24, 1, 1);
    CHECK_NEAR(again.mean_pnl, st.mean_pnl, 1e-9);   // indépendant du nombre de threads
}

static void metrics_gross_and_halt() {
    Config c = cfg0();
    c.signal_threshold = 0.6;
    c.min_edge = 0;
    const auto r = run_backtest(c, synthetic(8000, 60, 100, 2), 60);
    const Metrics m = r.metrics();
    assert(m.trades > 0);
    // brut - frais - funding = net (pas de shortfall attendu ici)
    CHECK_NEAR(m.gross_pnl - m.fees - m.funding, m.pnl, 1e-6);
}

int main() {
    split_is_chronological();
    buy_and_hold_hand_computed();
    buy_and_hold_with_costs_matches_identity();
    funding_lookup();
    funding_series_equals_constant();
    random_baseline();
    metrics_gross_and_halt();
    std::puts("test_validate OK");
}
