#include <cstdio>
#include <fstream>
#include <string>

#include "check.hpp"
#include "perp/backtest.hpp"
#include "perp/bot.hpp"

using namespace perp;

static Config test_cfg() {
    Config c;
    c.apply_text("symbol: BTC-USD\n");
    return c;
}

static bool same_trades(const std::vector<ClosedTrade>& a, const std::vector<ClosedTrade>& b) {
    if (a.size() != b.size()) return false;
    for (size_t i = 0; i < a.size(); ++i)
        if (a[i].pnl != b[i].pnl || a[i].reason != b[i].reason || a[i].entry_price != b[i].entry_price ||
            a[i].closed_ts != b[i].closed_ts)
            return false;
    return true;
}

static void candle_tick_order() {
    const Candle up{1000, 100, 103, 99, 102}; // haussière : o, l, h, c
    auto t = candle_ticks(up, 60, 1e-5);
    CHECK_NEAR(t[0].px(), 100, 0);
    CHECK_NEAR(t[1].px(), 99, 0);
    CHECK_NEAR(t[2].px(), 103, 0);
    CHECK_NEAR(t[3].px(), 102, 0);
    CHECK_NEAR(t[3].ts, 1000 + 45, 1e-12);
    CHECK_NEAR(t[0].funding_rate, 1e-5, 0);
    const Candle dn{1000, 100, 101, 97, 98}; // baissière : o, h, l, c
    t = candle_ticks(dn, 60, 0);
    CHECK_NEAR(t[1].px(), 101, 0);
    CHECK_NEAR(t[2].px(), 97, 0);
}

static void synthetic_is_reproducible() {
    const auto a = synthetic(2000, 60, 100, 7), b = synthetic(2000, 60, 100, 7), c = synthetic(2000, 60, 100, 8);
    assert(a.size() == 2000);
    bool same = true, differs = false;
    for (size_t i = 0; i < a.size(); ++i) {
        same = same && a[i].c == b[i].c && a[i].h == b[i].h && a[i].l == b[i].l;
        differs = differs || a[i].c != c[i].c;
        assert(a[i].h >= std::max(a[i].o, a[i].c) && a[i].l <= std::min(a[i].o, a[i].c));
    }
    assert(same && differs);
}

static void csv_roundtrip() {
    const std::string path = "test_backtest_tmp.csv";
    {
        std::ofstream f(path);
        f << "ts,open,high,low,close,volume\r\n"
             "1760000060000,101,102,100,101.5,3\r\n"   // millisecondes, désordonné
             "1760000000000,100,101,99,100.5,2\r\n"
             "1760000000000,100,101,99,100.5,2\r\n"    // doublon
             "1760000120000,0,1,1,1,1\r\n"             // prix nul : rejeté
             "garbage\r\n";
    }
    const auto c = load_csv(path);
    std::remove(path.c_str());
    assert(c.size() == 2);
    CHECK_NEAR(c[0].ts, 1760000000, 0);
    CHECK_NEAR(c[1].c, 101.5, 0);
    bool threw = false;
    try {
        load_csv("n_existe_pas.csv");
    } catch (const std::exception&) {
        threw = true;
    }
    assert(threw);
}

// Même entrée, même sortie, bit à bit.
static void backtest_is_deterministic() {
    const Config cfg = test_cfg();
    const auto candles = synthetic(6000, 60, 100, 11);
    const auto a = run_backtest(cfg, candles, 60), b = run_backtest(cfg, candles, 60);
    assert(a.trades.size() > 0); // la plomberie produit des trades
    assert(same_trades(a.trades, b.trades));
    assert(a.end_equity == b.end_equity && a.equity_curve == b.equity_curve);
}

// Invariants sur un backtest complet : equity finale = initiale + somme des PnL nets ;
// la ventilation par raison somme au PnL total ; chaque trade respecte l'identité
// pnl = side x qty x (sortie - entrée) - frais - funding, et la perte est plafonnée à la marge.
static void accounting_invariants() {
    for (unsigned seed : {1u, 2u, 3u, 4u}) {
        Config cfg = test_cfg();
        cfg.signal_threshold = 0.6; // plus d'activité
        cfg.min_edge = 0.0;
        cfg.bt_funding_rate_per_hour = 5e-5;
        const auto candles = synthetic(8000, 60, 100, seed);
        const BacktestResult r = run_backtest(cfg, candles, 60);
        double sum = 0, by_reason = 0;
        for (const auto& t : r.trades) {
            sum += t.pnl;
            const double gross = sign(t.side) * t.qty * (t.exit_price - t.entry_price);
            assert(t.pnl >= -(t.margin + t.fees) - 1e-9);                    // isolation
            if (r.shortfall == 0) CHECK_NEAR(t.pnl, gross - t.fees - t.funding, 1e-9);
            assert(t.closed_ts >= t.opened_ts);
        }
        CHECK_NEAR(r.end_equity, r.start_equity + sum, 1e-9);
        CHECK_NEAR(r.equity_curve.back(), r.end_equity, 1e-9);
        const Metrics m = r.metrics();
        for (const auto& kv : m.by_reason) by_reason += kv.second.pnl;
        CHECK_NEAR(by_reason, sum, 1e-9);
        CHECK_NEAR(m.pnl, sum, 1e-9);
        assert(m.trades == static_cast<long>(r.trades.size()));
        assert(r.equity_curve.size() == candles.size() + 1);
        assert(m.max_drawdown_pct >= 0 && m.max_drawdown_pct <= 100);
        std::printf("  seed %u : %ld trades, equity %.2f -> %.2f\n", seed, m.trades, r.start_equity,
                    r.end_equity);
    }
}

// Aucun trade : equity inchangée, métriques nulles, pas de division par zéro.
static void no_trades() {
    Config cfg = test_cfg();
    cfg.signal_threshold = 0.9999;
    const auto r = run_backtest(cfg, synthetic(1500, 60, 100, 5), 60);
    const Metrics m = r.metrics();
    assert(m.trades == 0 && r.end_equity == r.start_equity);
    CHECK_NEAR(m.sharpe, 0, 0);
    assert(m.skips.count("no_signal") || m.skips.count("z_low"));
    assert(run_backtest(cfg, {}, 60).trades.empty());
}

// Scénario scripté sur le bot : tendance haussière -> entrée long, puis chute -> stop loss.
static void scripted_entry_and_stop_loss() {
    Config cfg = test_cfg();
    cfg.min_edge = 0;
    cfg.min_z_score = 0;
    cfg.trailing_activation_pct = 0;
    cfg.slippage_pct = 0.001;
    PaperExchange ex(cfg.equity, cfg.slippage_pct, cfg.default_spread_pct);
    RiskManager risk(cfg, cfg.equity);
    PerpBot bot(cfg, cfg.instrument(), ex, risk);
    int opened = 0, closed = 0;
    bot.set_on_open([&](const Position& p) { ++opened; assert(p.side == Side::Long); });
    bot.set_on_trade([&](const ClosedTrade&) { ++closed; });

    double ts = 1'760'000'000.0;
    int i = 0;
    for (; i < 200 && ex.position(1) == nullptr; ++i) {
        Tick t;
        t.ts = ts + 5.0 * i;
        t.mark = t.index = 100.0 * (1 + 1e-4 * i + (i % 2 ? 1 : -1) * 2e-4);
        bot.on_tick(t);
    }
    assert(opened == 1 && bot.state() == State::Holding);
    const Position* p = ex.position(1);
    assert(p && p->sl_price < p->entry_price && p->tp_price > p->entry_price);
    assert(risk.net_exposure() > 0);
    const double sl = p->sl_price;

    // Chute de 5 % après la période de grâce : sortie "stop_loss" au prix de marché (au-delà du SL)
    Tick crash;
    crash.ts = ts + 5.0 * i + 60;
    crash.mark = crash.index = sl * 0.95;
    const auto out = bot.on_tick(crash);
    assert(out.size() == 1 && out[0].reason == "stop_loss");
    CHECK_NEAR(out[0].exit_price, crash.px() * (1 - 0.0001) * (1 - 0.001), 1e-9); // demi-spread + slippage
    assert(out[0].pnl < 0 && closed == 1);
    assert(bot.state() == State::Idle && ex.position(1) == nullptr);
    CHECK_NEAR(risk.net_exposure(), 0, 1e-12);
    CHECK_NEAR(ex.equity(), cfg.equity + out[0].pnl, 1e-9);
    assert(risk.pause_until() > crash.ts); // cooldown après perte
}

// Hors session : le flag est lu du csv, propagé aux ticks, bloque l'entrée et n'alimente pas l'historique.
static void off_session_blocks_entries() {
    const std::string path = "test_session_tmp.csv";
    {
        std::ofstream f(path);
        f << "ts,open,high,low,close,session\n1760000000000,100,101,99,100.5,0\n1760000060000,100,101,99,100.5,1\n";
    }
    const auto c = load_csv(path);
    std::remove(path.c_str());
    assert(c.size() == 2 && !c[0].session && c[1].session);
    assert(!candle_ticks(c[0], 60, 0)[2].tradable && candle_ticks(c[1], 60, 0)[2].tradable);

    Config cfg = test_cfg();
    cfg.min_edge = 0;
    cfg.min_z_score = 0;
    PaperExchange ex(cfg.equity, cfg.slippage_pct, cfg.default_spread_pct);
    RiskManager risk(cfg, cfg.equity);
    PerpBot bot(cfg, cfg.instrument(), ex, risk);
    for (int i = 0; i < 300; ++i) { // la même tendance qui déclenche une entrée en session
        Tick t;
        t.ts = 1'760'000'000.0 + 5.0 * i;
        t.mark = t.index = 100.0 * (1 + 1e-4 * i + (i % 2 ? 1 : -1) * 2e-4);
        t.tradable = false;
        bot.on_tick(t);
    }
    assert(ex.position(1) == nullptr && bot.skips().count("off_session") && bot.skips().at("off_session") == 300);
}

int main() {
    off_session_blocks_entries();
    candle_tick_order();
    synthetic_is_reproducible();
    csv_roundtrip();
    backtest_is_deterministic();
    accounting_invariants();
    no_trades();
    scripted_entry_and_stop_loss();
    std::puts("test_backtest OK");
}
