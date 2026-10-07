// Interface d'exécution et exchange papier. Le même PerpBot tourne sur PaperExchange
// (backtest et paper) et, plus tard, sur un adaptateur réel (LiveExchange, stub).
#pragma once

#include <optional>
#include <string>
#include <unordered_map>
#include <vector>

#include "perp/types.hpp"

namespace perp {

class IExchange {
public:
    virtual ~IExchange() = default;
    virtual double equity() const = 0;
    virtual Position* position(int iid) = 0; // nullptr si flat
    // Funding horaire puis liquidation. Retourne les trades clos par l'exchange.
    virtual std::vector<ClosedTrade> on_tick(const Instrument& inst, const Tick& tick) = 0;
    // Ordre marché IOC. nullptr si rejeté (marge insuffisante, notionnel trop petit, levier hors bornes).
    virtual Position* market_open(const Instrument& inst, Side side, double qty, double leverage,
                                  const Tick& tick) = 0;
    virtual std::optional<ClosedTrade> market_close(const Instrument& inst, const Tick& tick,
                                                    const std::string& reason) = 0;
    // Coût aller-retour en fraction du prix, selon le MÊME modèle que les fills.
    virtual double round_trip_cost(const Instrument& inst, const Tick& tick, Side side,
                                   double hold_s) const = 0;
};

// Modèle de fill : spread (demi de chaque côté), slippage de chaque côté, frais taker,
// funding prélevé à chaque passage d'heure epoch (notionnel au prix courant x taux, les longs
// paient si taux > 0), liquidation isolée (perte plafonnée à la marge).
class PaperExchange final : public IExchange {
public:
    // taker_fee_override < 0 : tier de l'instrument.
    PaperExchange(double balance, double slippage_pct, double default_spread_pct,
                  double taker_fee_override = -1.0)
        : balance_(balance), slippage_(slippage_pct), spread_(default_spread_pct),
          taker_override_(taker_fee_override) {}

    double equity() const override;
    Position* position(int iid) override;
    std::vector<ClosedTrade> on_tick(const Instrument& inst, const Tick& tick) override;
    Position* market_open(const Instrument& inst, Side side, double qty, double leverage,
                          const Tick& tick) override;
    std::optional<ClosedTrade> market_close(const Instrument& inst, const Tick& tick,
                                            const std::string& reason) override;
    double round_trip_cost(const Instrument& inst, const Tick& tick, Side side,
                           double hold_s) const override;

    double balance() const { return balance_; }
    double total_fees() const { return total_fees_; }
    double total_funding() const { return total_funding_; }
    int liquidations() const { return liquidations_; }
    // Pertes au-delà de la marge absorbées par l'exchange (liquidation gappée) ; 0 si jamais.
    double shortfall() const { return shortfall_; }
    const std::vector<ClosedTrade>& closed() const { return closed_; }

private:
    void bid_ask(const Tick& t, double& bid, double& ask) const;
    double fill_price(Side side, bool opening, const Tick& t) const; // opening long = achat
    double fee_rate(const Instrument& inst) const;
    ClosedTrade finish(const Position& pos, double exit_price, double ts, const std::string& reason,
                       double returned, double entry_fee);

    double balance_, slippage_, spread_, taker_override_;
    double total_fees_ = 0, total_funding_ = 0, shortfall_ = 0;
    int liquidations_ = 0;
    std::unordered_map<int, Position> positions_;
    std::unordered_map<int, double> last_mark_;
    std::vector<ClosedTrade> closed_;
};

} // namespace perp
