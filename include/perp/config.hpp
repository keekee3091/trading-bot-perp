// Configuration plate : une table (membre, clé, défaut) sert au chargement YAML,
// aux surcharges --set et au balayage de paramètres. Une clé inconnue est une erreur
// (une faute de frappe dans une grille ne doit pas passer silencieusement).
#pragma once

#include <map>
#include <string>

#include "perp/types.hpp"

namespace perp {

// X(membre, "clé yaml", défaut). Les sections yaml sont aplaties : backtest.x, instrument.x.
#define PERP_CONFIG_FIELDS(X)                                                                  \
    X(equity, "equity", 1000.0)                                                                \
    /* Signal */                                                                               \
    X(signal_threshold, "signal_threshold", 0.70)                                              \
    X(signal_lookback_seconds, "signal_lookback_seconds", 300.0)                               \
    X(vol_window_seconds, "vol_window_seconds", 900.0)                                         \
    X(signal_sensitivity, "signal_sensitivity", 1.5)                                           \
    X(sample_seconds, "sample_seconds", 5.0)                                                   \
    X(min_z_score, "min_z_score", 0.8)                                                         \
    X(ref_weight, "ref_weight", 0.6)                                                           \
    X(z_cap, "z_cap", 4.0)                                                                     \
    /* Edge et filtres */                                                                      \
    X(min_edge, "min_edge", 0.05)                                                              \
    X(max_spread_pct, "max_spread_pct", 0.001)                                                 \
    X(trading_hours_utc_start, "trading_hours_utc_start", -1.0)                                \
    X(trading_hours_utc_end, "trading_hours_utc_end", -1.0)                                    \
    /* Sorties */                                                                              \
    X(sl_pct_floor, "sl_pct_floor", 0.003)                                                     \
    X(sl_pct_cap, "sl_pct_cap", 0.03)                                                          \
    X(sl_vol_mult, "sl_vol_mult", 1.0)                                                         \
    X(tp_rr, "tp_rr", 1.5)                                                                     \
    X(trailing_activation_pct, "trailing_activation_pct", 0.006)                               \
    X(trailing_distance_pct, "trailing_distance_pct", 0.003)                                   \
    X(min_hold_seconds, "min_hold_seconds", 20.0)                                              \
    X(emergency_sl_mult, "emergency_sl_mult", 1.5)                                             \
    X(time_exit_seconds, "time_exit_seconds", 600.0)                                           \
    X(time_exit_min_pnl_pct, "time_exit_min_pnl_pct", 0.0)                                     \
    X(max_hold_seconds, "max_hold_seconds", 1800.0)                                            \
    X(liq_guard_pct, "liq_guard_pct", 0.002)                                                   \
    /* Risque et sizing */                                                                     \
    X(risk_per_trade_pct, "risk_per_trade_pct", 0.01)                                          \
    X(leverage, "leverage", 5.0)                                                               \
    X(liq_buffer_mult, "liq_buffer_mult", 2.0)                                                 \
    X(max_account_leverage, "max_account_leverage", 3.0)                                       \
    X(max_notional_per_trade, "max_notional_per_trade", 5000.0)                                \
    X(max_margin_pct, "max_margin_pct", 0.5)                                                   \
    X(min_notional, "min_notional", 10.0)                                                      \
    X(kelly_enabled, "kelly_enabled", 1.0)                                                     \
    X(kelly_window, "kelly_window", 30.0)                                                      \
    X(kelly_scaling, "kelly_scaling", 0.5)                                                     \
    X(kelly_base_fraction, "kelly_base_fraction", 0.25)                                        \
    X(kelly_min_mult, "kelly_min_mult", 0.3)                                                   \
    X(kelly_max_mult, "kelly_max_mult", 1.5)                                                   \
    /* sizing_mode 0 : par le risque (notionnel = risque / SL). 1 : par le levier de compte     \
       (notionnel = equity x levier, levier = account_leverage ou vol_target_annual / vol       \
       réalisée annualisée) ; les plafonds net, brut et max_notional ne s'appliquent pas. */    \
    X(sizing_mode, "sizing_mode", 0.0)                                                         \
    X(account_leverage, "account_leverage", 1.0)                                               \
    X(vol_target_annual, "vol_target_annual", 0.0)                                             \
    X(margin_frac, "margin_frac", 0.95)                                                        \
    X(apply_liq_cap, "apply_liq_cap", 1.0) /* mode 1 : plafonner le levier par liq_buffer */   \
    /* Circuit breakers (0 = désactivé quand c'est une limite) */                              \
    X(cooldown_after_loss_s, "cooldown_after_loss_s", 60.0)                                    \
    X(cooldown_after_win_s, "cooldown_after_win_s", 0.0)                                       \
    X(max_consecutive_losses, "max_consecutive_losses", 3.0)                                   \
    X(loss_streak_pause_s, "loss_streak_pause_s", 900.0)                                       \
    X(max_session_loss_pct, "max_session_loss_pct", 0.10)                                      \
    X(halt_report_pct, "halt_report_pct", 0.10) /* seuil du drapeau halt_breached (rapports) */ \
    X(daily_loss_lock_pct, "daily_loss_lock_pct", 0.05)                                        \
    X(daily_profit_lock_pct, "daily_profit_lock_pct", 0.0)                                     \
    X(max_entries_per_hour, "max_entries_per_hour", 12.0)                                      \
    X(max_entries_per_day, "max_entries_per_day", 0.0)                                         \
    X(max_net_exposure_pct, "max_net_exposure_pct", 2.0)                                       \
    X(max_gross_exposure_pct, "max_gross_exposure_pct", 4.0)                                   \
    /* Coûts simulés. taker_fee < 0 : tier de l'instrument. */                                 \
    X(slippage_pct, "slippage_pct", 0.0002)                                                    \
    X(default_spread_pct, "default_spread_pct", 0.0002)                                        \
    X(taker_fee, "taker_fee", -1.0)                                                            \
    X(bt_funding_rate_per_hour, "backtest.funding_rate_per_hour", 0.00001)                     \
    /* Instrument (surcharge locale ; à terme chargé depuis /v1/info/instruments) */           \
    X(inst_max_leverage, "instrument.max_leverage", 20.0)                                      \
    X(inst_min_notional, "instrument.min_notional", 10.0)                                      \
    X(inst_liquidation_fee, "instrument.liquidation_fee", 0.005)                               \
    X(inst_taker_fee, "instrument.taker_fee", 0.0004)                                          \
    X(inst_maker_fee, "instrument.maker_fee", 0.000125)                                        \
    X(inst_mmr, "instrument.mmr", 0.0)                                                         \
    X(mmr_factor, "mmr_factor", 0.5)                                                           \
    X(poll_seconds, "poll_seconds", 2.0) /* couche Python paper uniquement */                  \
    X(inst_qty_decimals, "instrument.qty_decimals", 4.0)

struct Config {
#define X(member, key, def) double member = def;
    PERP_CONFIG_FIELDS(X)
#undef X

    std::map<std::string, std::string> strs; // symbol, mode, ref_symbol

    // false si la clé est inconnue.
    bool set(const std::string& key, double v);
    bool get(const std::string& key, double& v) const;
    // Surcharge texte (--set cle=valeur) : symbol/mode/ref_symbol en chaîne, le reste en nombre.
    bool set_kv(const std::string& key, const std::string& value);

    // Charge un sous-ensemble de YAML (clé: valeur, sections d'un niveau, commentaires #).
    // Lève std::runtime_error sur clé inconnue ou valeur illisible.
    void apply_text(const std::string& yaml);
    void load_file(const std::string& path);

    std::string str(const std::string& key, const std::string& def = "") const;
    Instrument instrument() const;
};

} // namespace perp
