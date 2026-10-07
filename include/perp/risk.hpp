// Gestion du risque : Kelly glissant, sizing par risque, plafond de levier lié à la
// liquidation, circuit breakers, exposition nette signée et brute multi-actifs.
#pragma once

#include <deque>
#include <map>
#include <string>

#include "perp/config.hpp"
#include "perp/types.hpp"

namespace perp {

struct SizeDecision {
    double notional = 0;
    double margin = 0;
    double leverage = 1;
    double risk_usdc = 0;
    double kelly_mult = 1;
};

class RiskManager {
public:
    RiskManager(const Config& cfg, double start_equity) : cfg_(cfg), start_equity_(start_equity) {}

    double kelly_mult() const;

    // Levier cible, plafonné par max_leverage et pour que la liquidation reste à une distance
    // >= liq_buffer_mult x SL + frais de liquidation + liq_guard_pct (le garde-fou doit se
    // déclencher après le SL et avant la liquidation). Formule exacte, côté par côté :
    //   long  : 1/L = mmr + D (1 - mmr)      short : 1/L = mmr + D (1 + mmr)
    double choose_leverage(const Instrument& inst, double sl_pct, Side side) const;

    // Levier maximal qui garde la liquidation à la distance D ci-dessus (formule de choose_leverage).
    double liq_leverage_cap(const Instrument& inst, double sl_pct, Side side) const;

    // notional == 0 signifie « trop petit, pas d'entrée ». ann_vol : volatilité réalisée annualisée
    // (rendement relatif), utilisée seulement avec sizing_mode 1 et vol_target_annual > 0.
    SizeDecision size(double equity, const Instrument& inst, double sl_pct, Side side,
                      double ann_vol = 0.0) const;

    // Exposition par symbole (notionnel signé).
    void set_exposure(const std::string& symbol, Side side, double notional);
    void clear_exposure(const std::string& symbol) { net_.erase(symbol); }
    double net_exposure() const;
    double gross_exposure() const;

    // nullptr si l'entrée est autorisée, sinon la raison du refus.
    const char* check_entry(double now, Side side, double notional, double equity);
    void on_entry(double now) { entries_.push_back(now); }
    void record_trade(const ClosedTrade& t, double now);

    bool halted() const { return halted_; }
    double session_pnl() const { return session_pnl_; }
    double pause_until() const { return pause_until_; }

private:
    Config cfg_;
    double start_equity_;
    double session_pnl_ = 0, day_pnl_ = 0;
    bool day_set_ = false;
    long day_ = 0;
    int consec_losses_ = 0;
    double pause_until_ = 0;
    bool halted_ = false;
    std::deque<bool> win_;
    std::deque<double> pnl_pct_;
    std::map<std::string, double> net_;
    std::deque<double> entries_;
};

} // namespace perp
