#include "check.hpp"
#include "perp/signal.hpp"

using namespace perp;

// Série à tendance bruitée, un point toutes les 5 s : drift +-1e-4 par pas, bruit alterné +-2e-4.
// Rendements point à point ~ +5e-4 / -3e-4 (écart-type 4e-4) ; sur 60 pas (300 s), rendement
// ~ 0.6 %, vol d'horizon ~ 4e-4 x sqrt(60) = 0.31 %, soit z ~ 1.9 et p = sigmoid(1.5 z) ~ 0.95.
static PriceHistory series(int n, double drift, double base = 100.0) {
    PriceHistory h(3600, 0);
    for (int i = 0; i < n; ++i) {
        const double noise = (i % 2 ? 1 : -1) * 2e-4;
        h.add(5.0 * i, base * (1 + drift * i + noise));
    }
    return h;
}

static void sigmoid_basics() {
    CHECK_NEAR(sigmoid(0), 0.5, 1e-15);
    CHECK_NEAR(sigmoid(1), 0.7310585786300049, 1e-12);
    CHECK_NEAR(sigmoid(1e9), 1.0, 1e-12);  // pas de débordement
    CHECK_NEAR(sigmoid(-1e9), 0.0, 1e-12);
}

static void history_sampling_and_trim() {
    PriceHistory h(10, 5);
    h.add(0, 100);
    h.add(2, 101); // < min_step : remplace le dernier point
    assert(h.size() == 1 && h.last() == 101);
    h.add(5, 102);
    h.add(10, 103);
    h.add(15, 104); // 15 - 0 > 10 : le point 0 sort
    assert(h.size() == 3);
    assert(*h.price_ago(15, 5) == 103);   // dernier point à ou avant t = 10
    assert(*h.price_ago(15, 0) == 104);
    assert(!h.price_ago(15, 12));         // t = 3 est avant le premier point conservé (5)
    h.add(20, -1);                        // prix invalide ignoré
    assert(h.last() == 104);
}

static void no_signal_when_flat_or_short() {
    SignalEngine e({});
    PriceHistory flat(3600, 0);
    for (int i = 0; i < 200; ++i) flat.add(5.0 * i, 100.0);
    assert(!e.compute(995, flat));
    const PriceHistory shortH = series(50, 1e-4); // 245 s < lookback 300
    assert(!e.compute(245, shortH));
}

static void long_and_short_signals() {
    SignalEngine e({});
    const double now = 5.0 * 199;
    const auto up = e.compute(now, series(200, 1e-4));
    assert(up && up->side == Side::Long);
    assert(up->z_score > 1.5 && up->probability > 0.9);
    assert(up->volatility > 0.002 && up->volatility < 0.005);
    const auto dn = e.compute(now, series(200, -1e-4));
    assert(dn && dn->side == Side::Short);
    assert(dn->z_score < -1.5 && dn->probability > 0.9);
}

static void threshold_filters() {
    SignalEngine::Params p;
    p.threshold = 0.99;
    SignalEngine e(p);
    assert(!e.compute(5.0 * 199, series(200, 1e-4)));
}

// Fusion 40/60 : une référence plate dilue le z ; avec un poids de 0.9, plus de signal.
static void reference_fusion() {
    const double now = 5.0 * 199;
    const PriceHistory up = series(200, 1e-4), flat = series(200, 0.0);
    SignalEngine::Params p;
    p.ref_weight = 0.0;
    const double z0 = SignalEngine(p).compute(now, up)->z_score;
    p.ref_weight = 0.6;
    const auto mid = SignalEngine(p).compute(now, up, &flat); // z = 0.4 z0 + 0.6 z_flat
    assert(!mid || mid->z_score < z0 * 0.5);
    p.ref_weight = 0.9;
    assert(!SignalEngine(p).compute(now, up, &flat));
    p.ref_weight = 0.6;
    const auto both = SignalEngine(p).compute(now, up, &up); // même z des deux côtés
    assert(both);
    CHECK_NEAR(both->z_score, z0, 1e-9);
    // référence vide : ignorée
    const PriceHistory empty;
    assert(SignalEngine(p).compute(now, up, &empty));
}

int main() {
    sigmoid_basics();
    history_sampling_and_trim();
    no_signal_when_flat_or_short();
    long_and_short_signals();
    threshold_filters();
    reference_fusion();
    std::puts("test_signal OK");
}
