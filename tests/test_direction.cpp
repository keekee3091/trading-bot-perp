// Test de plomberie du SENS du signal : sur une série synthétique tendancielle sans bruit excessif,
// la stratégie momentum (configuration par défaut) doit gagner, les longs dans les régimes haussiers,
// les shorts dans les régimes baissiers, et basculer de côté au retournement.
// Un échec ici est un bug de signe, à signaler avant tout. On ne retourne JAMAIS le signal pour
// améliorer un résultat réel : ce serait du data mining.
#include <cmath>
#include <cstdio>
#include <vector>

#include "check.hpp"
#include "perp/backtest.hpp"

using namespace perp;

namespace {

constexpr double kInterval = 60;

struct Regime {
    int minutes;
    double drift_bps; // dérive par minute, en bps (positive : hausse)
};

// Bougies 1m : dérive déterministe + bruit pseudo-aléatoire borné (sd ~ 1 bp par minute) + petites
// mèches. RNG congruentiel maison : reproductible à l'identique partout.
std::vector<Candle> trending(const std::vector<Regime>& regimes, unsigned seed, double noise_bps = 1.0) {
    std::vector<Candle> out;
    unsigned s = seed;
    auto uni = [&]() {
        s = s * 1664525u + 1013904223u;
        return (static_cast<double>(s >> 8) / 16777216.0) - 0.5; // [-0.5, 0.5)
    };
    double px = 100.0, ts = 1'760'000'000.0;
    for (const Regime& r : regimes)
        for (int i = 0; i < r.minutes; ++i) {
            const double o = px;
            const double c = o * (1.0 + (r.drift_bps + noise_bps * 3.46 * uni()) * 1e-4); // 3.46 : sd d'une uniforme +-0.5 = 0.289
            const double h = std::max(o, c) * (1.0 + 0.2e-4), l = std::min(o, c) * (1.0 - 0.2e-4);
            out.push_back({ts, o, h, l, c});
            px = c;
            ts += kInterval;
        }
    return out;
}

Config cfg() {
    Config c; // paramètres par défaut du momentum court, funding constant par défaut
    c.apply_text("symbol: BTC-USD\n");
    c.max_session_loss_pct = 0; // pas de halt : on veut voir toute la série
    return c;
}

struct Split {
    double pnl_long = 0, pnl_short = 0;
    int n_long = 0, n_short = 0;
};

// Trades ouverts dans [t0, t1) : PnL net et nombre par côté.
Split by_side(const std::vector<ClosedTrade>& trades, double t0, double t1) {
    Split sp;
    for (const auto& t : trades) {
        if (t.opened_ts < t0 || t.opened_ts >= t1) continue;
        if (t.side == Side::Long) { sp.pnl_long += t.pnl; ++sp.n_long; }
        else { sp.pnl_short += t.pnl; ++sp.n_short; }
    }
    return sp;
}

// Hausse nette (4 bps/min), puis baisse nette, puis hausse : le momentum gagne, côté par côté.
void momentum_wins_with_correct_orientation() {
    const std::vector<Candle> c = trending({{1500, +4.0}, {1500, -4.0}, {1500, +4.0}}, 11);
    const BacktestResult r = run_backtest(cfg(), c, 60);
    const Metrics m = r.metrics();
    assert(m.trades >= 30); // la stratégie trade bien
    std::printf("  trades %ld, win %.0f%%, PnL net %+.2f, brut %+.2f, frais %.2f\n", m.trades, m.win_rate * 100, m.pnl,
                m.gross_pnl, m.fees);
    assert(m.pnl > 0);       // gagne net de frais, spread, slippage et funding
    assert(m.gross_pnl > 0); // et l'edge brut est positif : pas seulement des coûts négatifs
    assert(m.win_rate > 0.6);

    const double t_bear = c[1500].ts, t_bull2 = c[3000].ts;
    // marge de 15 min après chaque bascule : le signal a besoin de la fenêtre de lookback pour se retourner
    const Split bull1 = by_side(r.trades, c.front().ts, t_bear);
    const Split bear = by_side(r.trades, t_bear + 900, t_bull2);
    const Split bull2 = by_side(r.trades, t_bull2 + 900, c.back().ts + 1);

    assert(bull1.n_long > 0 && bull1.pnl_long > 0);
    assert(bull1.n_long > bull1.n_short);
    assert(bear.n_short > 0 && bear.pnl_short > 0);
    assert(bear.n_short > bear.n_long);
    assert(bull2.n_long > 0 && bull2.pnl_long > 0);
    assert(bull2.n_long > bull2.n_short);
    // le mauvais côté ne doit pas être le moteur du résultat
    assert(bull1.pnl_long > bull1.pnl_short && bear.pnl_short > bear.pnl_long && bull2.pnl_long > bull2.pnl_short);
}

// Retournement : après la bascule haussier -> baissier, la première entrée est un short, et tout trade
// ouvert plus de 15 min après la bascule va dans le sens de la nouvelle tendance.
void reversal_flips_the_side() {
    const std::vector<Candle> c = trending({{1500, +4.0}, {1500, -4.0}}, 23);
    const BacktestResult r = run_backtest(cfg(), c, 60);
    const double t_flip = c[1500].ts;
    const ClosedTrade* first_before = nullptr;
    const ClosedTrade* first_after = nullptr;
    for (const auto& t : r.trades) {
        if (t.opened_ts < t_flip) first_before = first_before ? first_before : &t;
        else if (t.opened_ts >= t_flip + 900 && !first_after) first_after = &t;
    }
    assert(first_before && first_after);
    assert(first_before->side == Side::Long);
    assert(first_after->side == Side::Short);
}

// Symétrie : la série miroir (baisse puis hausse) donne les côtés inverses, avec un résultat du même ordre.
void mirror_series_mirrors_the_sides() {
    const BacktestResult up = run_backtest(cfg(), trending({{2000, +4.0}}, 5), 60);
    const BacktestResult dn = run_backtest(cfg(), trending({{2000, -4.0}}, 5), 60);
    const Split su = by_side(up.trades, 0, 1e18), sd = by_side(dn.trades, 0, 1e18);
    assert(su.n_long > 0 && su.n_long > su.n_short && su.pnl_long > 0);
    assert(sd.n_short > 0 && sd.n_short > sd.n_long && sd.pnl_short > 0);
    // cumul : tendance pure, les deux sens gagnent, avec un ordre de grandeur comparable
    const double pu = up.end_equity - up.start_equity, pd = dn.end_equity - dn.start_equity;
    assert(pu > 0 && pd > 0);
    assert(pd > 0.3 * pu && pd < 3.0 * pu);
}

// Contrôle négatif : sur du bruit pur (aucune tendance), la stratégie ne doit PAS gagner de façon
// notable (frais et spread la font perdre). Garde-fou contre un test qui passerait trivialement.
void pure_noise_does_not_win() {
    const BacktestResult r = run_backtest(cfg(), trending({{6000, 0.0}}, 3, 3.0), 60);
    const Metrics m = r.metrics();
    std::printf("  bruit pur : %ld trades, PnL net %+.2f, brut %+.2f\n", m.trades, m.pnl, m.gross_pnl);
    assert(m.pnl < 0.02 * r.start_equity); // pas d'edge sur du bruit
}

} // namespace

int main() {
    std::puts("momentum sur régimes haussier / baissier / haussier");
    momentum_wins_with_correct_orientation();
    reversal_flips_the_side();
    mirror_series_mirrors_the_sides();
    pure_noise_does_not_win();
    std::puts("test_direction OK");
}
