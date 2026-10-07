// Types de base du moteur perps. Aucun I/O, aucun état global.
#pragma once

#include <algorithm>
#include <cmath>
#include <string>

namespace perp {

enum class Side { Long, Short };

inline int sign(Side s) { return s == Side::Long ? 1 : -1; }
inline const char* side_name(Side s) { return s == Side::Long ? "long" : "short"; }

struct Instrument {
    int iid = 1;
    std::string symbol = "BTC-USD";
    double max_leverage = 10.0;
    double min_notional = 10.0;
    int qty_decimals = 4;
    double liquidation_fee = 0.005; // fraction du notionnel liquidé
    double taker_fee = 0.0004;      // tier 0
    double maker_fee = 0.000125;    // tier 0 (non utilisé : le bot n'envoie que des ordres marché)
    // Taux de marge de maintenance. 0 = défaut mmr_factor / max_leverage ;
    // à remplacer par le tier réel de risk_tiers (hypothèse tant que non chargé).
    double maintenance_margin_rate = 0.0;
    double mmr_factor = 0.5;

    double mmr() const {
        if (maintenance_margin_rate > 0) return maintenance_margin_rate;
        return mmr_factor / std::max(max_leverage, 1.0);
    }
    // Arrondi vers le bas : on ne dépasse jamais la marge disponible.
    double round_qty(double qty) const {
        const double f = std::pow(10.0, qty_decimals);
        return std::floor(qty * f + 1e-9) / f;
    }
};

// Snapshot de marché. bid/ask à 0 : l'exchange applique le spread par défaut.
struct Tick {
    double ts = 0;           // secondes epoch
    double mark = 0;
    double index = 0;
    double bid = 0;
    double ask = 0;
    double funding_rate = 0; // taux horaire, positif : les longs paient les shorts
    double ref_price = 0;    // prix de référence externe optionnel (ex. Binance)
    bool warmup = false;     // préchauffage de l'historique : pas d'entrée
    bool tradable = true;    // false : hors session, pas d'entrée (les sorties restent possibles)

    double px() const { return index > 0 ? index : mark; }
};

struct Position {
    int iid = 0;
    std::string symbol;
    Side side = Side::Long;
    double entry_price = 0;
    double qty = 0; // unités de base, > 0
    double leverage = 1;
    double margin = 0; // collatéral isolé bloqué (hors frais d'entrée)
    double mmr = 0;
    double liq_fee = 0; // fraction du notionnel, facturée au fill de liquidation
    double opened_ts = 0;
    long funding_hour = 0;   // dernière heure epoch dont le funding a été prélevé
    double funding_paid = 0; // cumul, positif = payé
    double fees_paid = 0;
    // Gestion de sortie (renseignés par le PositionManager)
    double sl_price = 0;
    double tp_price = 0;
    double high_water = 0;
    bool trail_active = false;
    double trail_price = 0;

    double notional() const { return qty * entry_price; }

    // Seuil de déclenchement de la liquidation : equity = marge de maintenance
    // (mmr x notionnel au prix courant), avec equity = marge - funding + PnL.
    //   long  : C + q(P-E) = m q P  =>  P = (qE - C) / (q(1-m))
    //   short : C + q(E-P) = m q P  =>  P = (qE + C) / (q(1+m))
    // Les frais de liquidation ne changent pas le seuil, ils sont facturés au fill.
    double liq_price() const {
        const double c = margin - funding_paid;
        return side == Side::Long ? (qty * entry_price - c) / (qty * (1.0 - mmr))
                                  : (qty * entry_price + c) / (qty * (1.0 + mmr));
    }
    double pnl(double price) const { return sign(side) * qty * (price - entry_price); }
    double pnl_pct_underlying(double price) const {
        return sign(side) * (price - entry_price) / entry_price;
    }
    double equity(double price) const { return margin + pnl(price) - funding_paid; }
    // Distance relative positive entre le prix courant et la liquidation.
    double liq_distance_pct(double price) const {
        return side == Side::Long ? (price - liq_price()) / price : (liq_price() - price) / price;
    }
};

struct ClosedTrade {
    std::string symbol;
    Side side = Side::Long;
    double entry_price = 0;
    double exit_price = 0;
    double qty = 0;
    double leverage = 0;
    double margin = 0;
    double pnl = 0;     // net : frais (entrée, sortie) et funding inclus
    double pnl_pct = 0; // sur la marge engagée
    double fees = 0;
    double funding = 0;
    std::string reason;
    double held_s = 0;
    double opened_ts = 0;
    double closed_ts = 0;
};

struct Signal {
    Side side = Side::Long;
    double probability = 0;
    double z_score = 0;
    double volatility = 0; // vol relative ramenée à l'horizon du lookback
    double price = 0;
};

// Probabilité minimale de toucher le TP avant le SL pour une espérance nulle,
// coûts aller-retour c inclus (fractions du prix) :
//   p (tp - c) - (1 - p)(sl + c) = 0  =>  p = (sl + c) / (sl + tp)
inline double breakeven_prob(double sl_pct, double tp_pct, double cost_pct) {
    const double denom = sl_pct + tp_pct;
    if (denom <= 0) return 1.0;
    return std::min(1.0, std::max(0.0, (sl_pct + cost_pct) / denom));
}

} // namespace perp
