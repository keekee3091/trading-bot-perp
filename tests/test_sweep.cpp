#include <sstream>
#include <stdexcept>

#include "check.hpp"
#include "perp/sweep.hpp"

using namespace perp;

static bool throws(const char* spec) {
    try {
        parse_axis(spec);
    } catch (const std::runtime_error&) {
        return true;
    }
    return false;
}

static void axis_parsing() {
    const Axis a = parse_axis("signal_threshold=0.6,0.7,0.8");
    assert(a.key == "signal_threshold" && a.values.size() == 3);
    CHECK_NEAR(a.values[2], 0.8, 0);
    const Axis r = parse_axis("leverage=1:5:1");
    assert(r.values.size() == 5);
    CHECK_NEAR(r.values[4], 5, 0);
    const Axis f = parse_axis("signal_threshold=0.6:0.8:0.05"); // 5 valeurs malgré l'erreur flottante
    assert(f.values.size() == 5);
    CHECK_NEAR(f.values[4], 0.8, 1e-12);
    assert(parse_axis("tp_rr=2").values.size() == 1);
    assert(throws("pas_une_cle=1,2"));
    assert(throws("leverage=1,abc"));
    assert(throws("leverage=5:1:1"));
    assert(throws("leverage=1:5:0"));
    assert(throws("leverage"));
}

// Le résultat ne dépend pas du nombre de threads, et suit l'ordre de la grille (dernier axe rapide).
static void threads_do_not_change_results() {
    Config cfg;
    cfg.min_edge = 0;
    const auto candles = synthetic(4000, 60, 100, 21);
    const std::vector<Axis> axes = {parse_axis("signal_threshold=0.6,0.7"), parse_axis("tp_rr=1,1.5,2"),
                                    parse_axis("leverage=2,5")};
    assert(grid_size(axes) == 12);
    const auto one = run_sweep(cfg, axes, candles, 60, 1);
    const auto many = run_sweep(cfg, axes, candles, 60, 4);
    assert(one.size() == 12 && many.size() == 12);
    for (size_t i = 0; i < one.size(); ++i) {
        assert(one[i].params == many[i].params);
        assert(one[i].m.trades == many[i].m.trades);
        assert(one[i].m.pnl == many[i].m.pnl && one[i].m.sharpe == many[i].m.sharpe);
        assert(one[i].m.by_reason.size() == many[i].m.by_reason.size());
    }
    // ordre : le dernier axe varie le plus vite
    CHECK_NEAR(one[0].params[2], 2, 0);
    CHECK_NEAR(one[1].params[2], 5, 0);
    CHECK_NEAR(one[2].params[1], 1.5, 0);
    CHECK_NEAR(one[11].params[0], 0.7, 0);

    // chaque point = le backtest direct avec ces paramètres
    Config direct = cfg;
    direct.signal_threshold = 0.7;
    direct.tp_rr = 2;
    direct.leverage = 5;
    const BacktestResult r = run_backtest(direct, candles, 60);
    assert(r.end_equity - r.start_equity == one[11].m.pnl);
    // les paramètres varient bien les résultats
    bool varies = false;
    for (size_t i = 1; i < one.size(); ++i) varies = varies || one[i].m.pnl != one[0].m.pnl;
    assert(varies);
}

static void csv_output() {
    Config cfg;
    const auto candles = synthetic(1500, 60, 100, 3);
    const std::vector<Axis> axes = {parse_axis("leverage=2,3")};
    const auto rows = run_sweep(cfg, axes, candles, 60, 2);
    std::ostringstream os;
    write_sweep_csv(os, axes, rows);
    const std::string s = os.str();
    assert(s.rfind("leverage,trades,win_rate,pnl,", 0) == 0);
    assert(s.find("pnl_stop_loss") != std::string::npos && s.find("pnl_liquidation") != std::string::npos);
    size_t lines = 0;
    for (char ch : s) lines += ch == '\n';
    assert(lines == 3); // en-tête + 2 points
}

static void bad_grid_is_rejected() {
    Axis empty;
    empty.key = "leverage";
    bool threw = false;
    try {
        grid_size({empty});
    } catch (const std::runtime_error&) {
        threw = true;
    }
    assert(threw);
}

int main() {
    axis_parsing();
    threads_do_not_change_results();
    csv_output();
    bad_grid_is_rejected();
    std::puts("test_sweep OK");
}
