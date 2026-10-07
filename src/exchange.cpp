#include "perp/exchange.hpp"

#include <algorithm>
#include <cmath>

namespace perp {

void PaperExchange::bid_ask(const Tick& t, double& bid, double& ask) const {
    if (t.bid > 0 && t.ask > 0) {
        bid = t.bid;
        ask = t.ask;
    } else {
        bid = t.px() * (1 - spread_ / 2);
        ask = t.px() * (1 + spread_ / 2);
    }
}

double PaperExchange::fill_price(Side side, bool opening, const Tick& t) const {
    double bid, ask;
    bid_ask(t, bid, ask);
    const bool buy = (side == Side::Long) == opening;
    return buy ? ask * (1 + slippage_) : bid * (1 - slippage_);
}

double PaperExchange::fee_rate(const Instrument& inst) const {
    return taker_override_ >= 0 ? taker_override_ : inst.taker_fee;
}

double PaperExchange::equity() const {
    double e = balance_;
    for (const auto& kv : positions_) {
        const Position& p = kv.second;
        auto m = last_mark_.find(p.iid);
        e += p.equity(m == last_mark_.end() ? p.entry_price : m->second);
    }
    return e;
}

Position* PaperExchange::position(int iid) {
    auto it = positions_.find(iid);
    return it == positions_.end() ? nullptr : &it->second;
}

double PaperExchange::round_trip_cost(const Instrument& inst, const Tick& tick, Side side,
                                      double hold_s) const {
    const double px = tick.px();
    const double entry = fill_price(side, true, tick), exit = fill_price(side, false, tick);
    const double slip_spread = sign(side) * (entry - exit) / px; // demi-spread + slippage, x2
    const double fees = fee_rate(inst) * (entry + exit) / px;
    const double funding = std::max(0.0, sign(side) * tick.funding_rate) * hold_s / 3600.0;
    return slip_spread + fees + funding;
}

Position* PaperExchange::market_open(const Instrument& inst, Side side, double qty, double leverage,
                                     const Tick& tick) {
    if (positions_.count(inst.iid) || qty <= 0 || leverage < 1.0 || leverage > inst.max_leverage)
        return nullptr;
    const double fill = fill_price(side, true, tick);
    const double notional = qty * fill;
    if (notional < inst.min_notional) return nullptr;
    const double margin = notional / leverage;
    const double fee = notional * fee_rate(inst);
    if (margin + fee > balance_) return nullptr;

    balance_ -= margin + fee;
    total_fees_ += fee;
    Position p;
    p.iid = inst.iid;
    p.symbol = inst.symbol;
    p.side = side;
    p.entry_price = fill;
    p.qty = qty;
    p.leverage = leverage;
    p.margin = margin;
    p.mmr = inst.mmr();
    p.liq_fee = inst.liquidation_fee;
    p.opened_ts = tick.ts;
    p.funding_hour = static_cast<long>(std::floor(tick.ts / 3600.0));
    p.fees_paid = fee;
    last_mark_[inst.iid] = tick.px();
    return &(positions_[inst.iid] = p);
}

ClosedTrade PaperExchange::finish(const Position& pos, double exit_price, double ts,
                                  const std::string& reason, double returned, double entry_fee) {
    // PnL net = collatéral récupéré - (marge + frais d'entrée) : frais et funding inclus.
    const double net = returned - pos.margin - entry_fee;
    ClosedTrade t;
    t.symbol = pos.symbol;
    t.side = pos.side;
    t.entry_price = pos.entry_price;
    t.exit_price = exit_price;
    t.qty = pos.qty;
    t.leverage = pos.leverage;
    t.margin = pos.margin;
    t.pnl = net;
    t.pnl_pct = pos.margin > 0 ? net / pos.margin : 0.0;
    t.fees = pos.fees_paid;
    t.funding = pos.funding_paid;
    t.reason = reason;
    t.held_s = ts - pos.opened_ts;
    t.opened_ts = pos.opened_ts;
    t.closed_ts = ts;
    positions_.erase(pos.iid);
    closed_.push_back(t);
    return t;
}

std::optional<ClosedTrade> PaperExchange::market_close(const Instrument& inst, const Tick& tick,
                                                       const std::string& reason) {
    auto it = positions_.find(inst.iid);
    if (it == positions_.end()) return std::nullopt;
    Position pos = it->second;
    const double fill = fill_price(pos.side, false, tick);
    const double fee = pos.qty * fill * fee_rate(inst);
    const double entry_fee = pos.fees_paid;
    pos.fees_paid += fee;
    total_fees_ += fee;
    // Isolation : la perte est plafonnée à la marge.
    const double raw = pos.margin + pos.pnl(fill) - pos.funding_paid - fee;
    shortfall_ += std::max(0.0, -raw);
    const double returned = std::max(0.0, raw);
    balance_ += returned;
    return finish(pos, fill, tick.ts, reason, returned, entry_fee);
}

std::vector<ClosedTrade> PaperExchange::on_tick(const Instrument& inst, const Tick& tick) {
    std::vector<ClosedTrade> out;
    const double px = tick.px();
    last_mark_[inst.iid] = px;
    auto it = positions_.find(inst.iid);
    if (it == positions_.end()) return out;
    Position& pos = it->second;

    // Funding : une charge par passage d'heure epoch, au notionnel courant.
    const long hour = static_cast<long>(std::floor(tick.ts / 3600.0));
    if (hour > pos.funding_hour) {
        const double charge =
            static_cast<double>(hour - pos.funding_hour) * sign(pos.side) * pos.qty * px * tick.funding_rate;
        pos.funding_paid += charge;
        total_funding_ += charge;
        pos.funding_hour = hour;
    }

    // Liquidation : seuil = equity égale marge de maintenance. Fill au prix observé (pire cas
    // si le tick a sauté le seuil) ; les frais de liquidation sont facturés ici, au fill.
    const double liq = pos.liq_price();
    const bool hit = pos.side == Side::Long ? px <= liq : px >= liq;
    if (hit) {
        const double fill = px;
        // Doc liquidation-mechanics : FillFee = Notional x (taux maker/taker + taux de liquidation).
        const double fee = pos.qty * fill * (fee_rate(inst) + pos.liq_fee);
        const double entry_fee = pos.fees_paid;
        pos.fees_paid += fee;
        total_fees_ += fee;
        const double raw = pos.margin + pos.pnl(fill) - pos.funding_paid - fee;
        shortfall_ += std::max(0.0, -raw);
        const double returned = std::max(0.0, raw);
        balance_ += returned;
        ++liquidations_;
        out.push_back(finish(pos, fill, tick.ts, "liquidation", returned, entry_fee));
    }
    return out;
}

} // namespace perp
