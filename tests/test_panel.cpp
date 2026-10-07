#include "check.hpp"
#include "perp/panel.hpp"

using namespace perp;

static PanelInstrument make(const std::string& sym, int n, unsigned seed, size_t drop_first = 0) {
    PanelInstrument pi;
    pi.symbol = sym;
    pi.cfg.strs["symbol"] = sym;
    pi.cfg.signal_threshold = 0.6;
    pi.cfg.min_edge = 0;
    pi.candles = synthetic(n, 60, 100, seed);
    pi.candles.erase(pi.candles.begin(), pi.candles.begin() + static_cast<std::ptrdiff_t>(drop_first));
    return pi;
}

// Dates de référence : 2000-03-01 = 11017 jours, 2026-10-05 = 20731 jours depuis 1970-01-01.
static void date_parsing() {
    CHECK_NEAR(parse_date("1970-01-01"), 0, 0);
    CHECK_NEAR(parse_date("2000-03-01"), 951868800, 0);
    CHECK_NEAR(parse_date("2026-10-05"), 1791158400, 0); // 20 731 jours x 86 400
    bool threw = false;
    try {
        parse_date("2026/10/05");
    } catch (const std::exception&) {
        threw = true;
    }
    assert(threw);
}

// Un seul instrument : le portefeuille est ce sleeve (mêmes rendements horaires, même equity finale).
static void single_instrument_portfolio_equals_sleeve() {
    const std::vector<PanelInstrument> panel = {make("A", 6000, 3)};
    Window w;
    w.start = panel[0].candles.front().ts;
    const PanelRun r = run_panel(panel, {}, w, 1);
    assert(r.inst[0].res.trades.size() > 0);
    CHECK_NEAR(r.port.end_equity, r.inst[0].res.end_equity, 1e-9);
    assert(r.n_active == 1);
    double e = r.port.start_equity;
    for (double x : r.port_ret) e *= 1 + x;
    CHECK_NEAR(e, r.inst[0].res.end_equity, 1e-6);
}

// Deux instruments dont le second démarre plus tard : equity du portefeuille = moyenne des sleeves,
// le sleeve non listé reste en cash.
static void late_listing_stays_cash() {
    const std::vector<PanelInstrument> panel = {make("A", 6000, 3), make("B", 6000, 4, 3000)};
    Window w;
    w.start = panel[0].candles.front().ts;
    const PanelRun r = run_panel(panel, {}, w, 2);
    const double b_start = panel[1].candles.front().ts;
    CHECK_NEAR(r.port.end_equity, 0.5 * (r.inst[0].res.end_equity + r.inst[1].res.end_equity), 1e-9);
    assert(r.n_active == 2);
    // le marché équipondéré n'a que A avant la cotation de B : son rendement est celui de A
    const size_t h_early = 5;
    assert(r.hour_ts[h_early] + 3600 < b_start);
    double a_prev = 0, a_cur = 0;
    for (const auto& c : panel[0].candles) {
        if (c.ts < r.hour_ts[h_early]) a_prev = c.c;
        if (c.ts < r.hour_ts[h_early] + 3600) a_cur = c.c;
    }
    CHECK_NEAR(r.mkt_ret[h_early], a_cur / a_prev - 1, 1e-12);
}

// Préchauffage : aucune entrée avant start, la courbe commence à start, et le résultat ne dépend pas
// du nombre de threads.
static void warmup_and_threads() {
    const std::vector<PanelInstrument> panel = {make("A", 8000, 5), make("B", 8000, 6)};
    Window w;
    w.start = panel[0].candles[4000].ts;
    w.warmup_s = 3 * 3600;
    const PanelRun a = run_panel(panel, {}, w, 1), b = run_panel(panel, {}, w, 4);
    assert(a.port.end_equity == b.port.end_equity && a.pm.trades == b.pm.trades);
    for (const auto& ir : a.inst) {
        assert(ir.window.front().ts >= w.start);
        for (const auto& t : ir.res.trades) assert(t.opened_ts >= w.start);
        assert(ir.res.candle_ts.size() == ir.window.size());
    }
    // sans préchauffage la première entrée ne peut pas être antérieure : même bornes, trades différents
    Window cold = w;
    cold.warmup_s = 0;
    const PanelRun c = run_panel(panel, {}, cold, 1);
    for (const auto& ir : c.inst)
        for (const auto& t : ir.res.trades) assert(t.opened_ts >= w.start);
}

// Paramètres communs : le jeu s'applique à tous les instruments.
static void params_apply_to_all() {
    const std::vector<PanelInstrument> panel = {make("A", 5000, 7), make("B", 5000, 8)};
    Window w;
    w.start = panel[0].candles.front().ts;
    const PanelRun lo = run_panel(panel, {{"signal_threshold", 0.6}}, w, 1);
    const PanelRun hi = run_panel(panel, {{"signal_threshold", 0.95}}, w, 1);
    for (size_t i = 0; i < 2; ++i) assert(hi.inst[i].res.trades.size() <= lo.inst[i].res.trades.size());
    bool threw = false;
    try {
        run_panel(panel, {{"pas_une_cle", 1}}, w, 1);
    } catch (const std::exception&) {
        threw = true;
    }
    assert(threw);
}

static void random_panel_baseline() {
    const std::vector<PanelInstrument> panel = {make("A", 12000, 9), make("B", 12000, 10)};
    Window w;
    w.start = panel[0].candles.front().ts;
    const PanelRun s = run_panel(panel, {}, w, 1);
    const PanelRandom r = run_panel_random(panel, {}, w, s, 12, 3, 4);
    assert(r.sharpe.size() == 12 && r.inst_pnl.size() == 2 && r.inst_pnl[0].size() == 12);
    assert(r.entry_prob[0] > 0 && r.entry_prob[0] <= 1);
    const PanelRandom again = run_panel_random(panel, {}, w, s, 12, 3, 1);
    assert(again.sharpe == r.sharpe); // indépendant des threads
}

int main() {
    date_parsing();
    single_instrument_portfolio_equals_sleeve();
    late_listing_stays_cash();
    warmup_and_threads();
    params_apply_to_all();
    random_panel_baseline();
    std::puts("test_panel OK");
}
