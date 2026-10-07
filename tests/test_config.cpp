#include <stdexcept>

#include "check.hpp"
#include "perp/config.hpp"

using namespace perp;

static bool throws(const char* yaml) {
    Config c;
    try {
        c.apply_text(yaml);
    } catch (const std::runtime_error&) {
        return true;
    }
    return false;
}

static void parse_values() {
    Config c;
    c.apply_text(
        "# commentaire\n"
        "symbol: BTC-USD   # fin de ligne\n"
        "equity: 2500\n"
        "signal_threshold: 0.65\n"
        "trading_hours_utc_start: null\n"
        "kelly_enabled: false\n"
        "backtest:\n"
        "  funding_rate_per_hour: 0.0001\n"
        "instrument:\n"
        "  max_leverage: 50\n"
        "  mmr: 0.02\n"
        "leverage: 3\n"
        "mode: \"paper\"\n");
    assert(c.str("symbol") == "BTC-USD" && c.str("mode") == "paper");
    CHECK_NEAR(c.equity, 2500, 0);
    CHECK_NEAR(c.signal_threshold, 0.65, 0);
    CHECK_NEAR(c.trading_hours_utc_start, -1, 0); // null : défaut
    CHECK_NEAR(c.kelly_enabled, 0, 0);
    CHECK_NEAR(c.bt_funding_rate_per_hour, 0.0001, 0);
    CHECK_NEAR(c.leverage, 3, 0); // la section est refermée par la clé non indentée
    const Instrument i = c.instrument();
    CHECK_NEAR(i.max_leverage, 50, 0);
    CHECK_NEAR(i.mmr(), 0.02, 0);
}

static void errors() {
    assert(throws("funding_bias: 0.5\n"));          // retiré en v1 : une clé morte doit se voir
    assert(throws("equity: abc\n"));                // texte dans un champ numérique
    assert(throws("backtest:\n  nope: 1\n"));       // clé de section inconnue
    assert(throws("sans deux points\n"));
}

static void set_and_get() {
    Config c;
    assert(c.set("tp_rr", 2.5));
    double v = 0;
    assert(c.get("tp_rr", v) && v == 2.5);
    assert(!c.set("nope", 1) && !c.get("nope", v));
    assert(c.set("instrument.max_leverage", 7) && c.instrument().max_leverage == 7);
}

// Le config.yaml livré doit rester chargeable (clé renommée ou retirée = test rouge).
static void shipped_config_loads() {
    Config c;
    c.load_file(std::string(PERP_SOURCE_DIR) + "/config.yaml");
    assert(c.str("symbol") == "BTC-USD");
    CHECK_NEAR(c.leverage, 5, 0);
}

int main() {
    parse_values();
    errors();
    set_and_get();
    shipped_config_loads();
    std::puts("test_config OK");
}
