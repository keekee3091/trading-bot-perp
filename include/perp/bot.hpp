// PerpBot : machine à états par instrument (IDLE <-> HOLDING), pilotée tick par tick,
// identique en backtest, paper et live (via IExchange).
//
// Entrée : signal -> filtres (heures, z, spread, edge vs breakeven) -> sizing risque
// -> contrôle d'exposition -> ordre marché. Sortie : PositionManager.
#pragma once

#include <functional>
#include <cstdint>
#include <map>
#include <random>
#include <string>
#include <vector>

#include "perp/config.hpp"
#include "perp/exchange.hpp"
#include "perp/position_manager.hpp"
#include "perp/risk.hpp"
#include "perp/signal.hpp"

namespace perp {

enum class State { Idle, Holding };

class PerpBot {
public:
    PerpBot(const Config& cfg, const Instrument& inst, IExchange& ex, RiskManager& risk);

    void set_on_trade(std::function<void(const ClosedTrade&)> cb) { on_trade_ = std::move(cb); }
    void set_on_open(std::function<void(const Position&)> cb) { on_open_ = std::move(cb); }

    // Ligne de base : remplace la décision d'entrée par un tirage (côté à pile ou face, probabilité
    // prob par tick libre), en gardant spread, sizing, exposition, sorties et coûts identiques.
    void set_random_entries(double prob, std::uint64_t seed);

    // Retourne les trades clos pendant ce tick.
    std::vector<ClosedTrade> on_tick(const Tick& tick);

    State state() const { return state_; }
    const std::map<std::string, long>& skips() const { return skips_; }

private:
    void try_enter(const Tick& tick);
    void after_close(const ClosedTrade& t, const Tick& tick);
    void skip(const std::string& why) { ++skips_[why]; }
    bool in_trading_hours(double ts) const;

    Config cfg_;
    Instrument inst_;
    IExchange& ex_;
    RiskManager& risk_;
    PositionManager pm_;
    PriceHistory hist_, ref_hist_;
    SignalEngine engine_;
    State state_ = State::Idle;
    bool random_ = false;
    double random_prob_ = 0;
    std::mt19937_64 rng_;
    std::map<std::string, long> skips_;
    std::function<void(const ClosedTrade&)> on_trade_;
    std::function<void(const Position&)> on_open_;
};

} // namespace perp
