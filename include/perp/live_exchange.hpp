// Exécution live Polymarket Perps : NON IMPLÉMENTÉE volontairement. Aucun ordre réel n'est
// branché tant que backtest puis paper n'ont pas montré un Sharpe positif net de frais.
//
// Faits de la doc (2026-10-05) pour le futur adaptateur :
//   REST https://api.perpetuals.polymarket.com, WS wss://ws.perpetuals.polymarket.com/v1/ws
//   auth EIP-712 CreateProxy (Polygon 137) puis POST /v1/account/proxy -> proxy_secret
//   ordre POST /v1/trade/orders {op:{type:"createOrders",args:[{iid,buy,p,qty,tif,po,ro,c}]},sig,salt,ts}
//   tif ioc|gtc|fok, ro reduce-only, po post-only
// À vérifier avant : /perps/account-management, /perps/errors, signature via le SDK, mise minimale.
// Il suffit d'implémenter IExchange ; le bot n'en dépend pas d'autre.
#pragma once

#include <stdexcept>

#include "perp/exchange.hpp"

namespace perp {

class LiveExchange final : public IExchange {
public:
    LiveExchange() {
        throw std::logic_error("LiveExchange non implemente : valider backtest puis paper d'abord");
    }
    double equity() const override { return nope(); }
    Position* position(int) override { nope(); return nullptr; }
    std::vector<ClosedTrade> on_tick(const Instrument&, const Tick&) override { nope(); return {}; }
    Position* market_open(const Instrument&, Side, double, double, const Tick&) override {
        nope();
        return nullptr;
    }
    std::optional<ClosedTrade> market_close(const Instrument&, const Tick&,
                                            const std::string&) override {
        nope();
        return std::nullopt;
    }
    double round_trip_cost(const Instrument&, const Tick&, Side, double) const override {
        return nope();
    }

private:
    static double nope() { throw std::logic_error("LiveExchange non implemente"); }
};

} // namespace perp
