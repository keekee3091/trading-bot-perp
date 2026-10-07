// Backtest passif de market making sur l'historique de trades (aucun historique de carnet n'existe).
//
// On rejoue les trades publics en ordre chronologique. Deux fois par minute au plus, nos quotes
// sont recalculées autour du prix de référence (mark) : bid = ref (1 - (delta + decalage)), ask =
// ref (1 + (delta - decalage)), le décalage dépendant de l'inventaire (esprit Avellaneda-Stoikov
// simplifié : plus on est long, plus on baisse les deux quotes). Les quotes sont post-only (frais
// maker) et arrondies au tick (bid vers le bas, ask vers le haut).
//
// CE QUI EST MESURÉ : les trades (prix, quantité, temps, sens de l'agresseur après vérification),
// le mark, le funding, les frais documentés. CE QUI EST SUPPOSÉ : la règle de fill (deux bornes), la
// file d'attente devant nous, le prix des sorties taker (mark +- demi-spread effectif estimé sur les
// trades + slippage). NON IDENTIFIABLE sans carnet historique : notre position réelle dans la file,
// le vrai spread passé, la profondeur.
#pragma once

#include <cstdint>
#include <map>
#include <string>
#include <vector>

#include "perp/backtest.hpp"
#include "perp/types.hpp"

namespace perp {

struct Trade {
    double ts = 0;       // secondes epoch
    double price = 0, qty = 0;
    int dir = 0;         // +1 : l'agresseur achète (prend le ask) ; -1 : il vend (prend le bid)
    bool settlement = false;
};

struct MarkPoint {
    double ts = 0;       // début du bucket (s)
    double mark = 0;     // DERNIER mark du bucket : connu seulement à ts + interval
};

struct MmData {
    std::string symbol, category;
    Instrument inst;
    double tick = 0.01;  // pas de prix (10^-price_decimals)
    double mark_interval_s = 60;
    std::vector<Trade> trades;
    std::vector<MarkPoint> mark;
    std::vector<FundingPoint> funding;
};

// ts(ms),trade_id,side,price,qty,settlement. long_is_buyer : vrai si side=long désigne l'agresseur
// acheteur (à établir par mesure, voir tools/side_semantics.py). Trié, sans ligne illisible.
std::vector<Trade> load_trades_csv(const std::string& path, bool long_is_buyer);
// ts(ms),mark ; les lignes à mark <= 0 (pas encore de mark) sont ignorées.
std::vector<MarkPoint> load_mark_csv(const std::string& path);

// Session du sous-jacent (mêmes règles que tools/sessions.py) : 1 ouvert, 0 fermé.
int in_session(const std::string& category, double ts);

struct MmParams {
    double delta_bps = 2.0;
    double skew_frac = 0.5;        // décalage à inventaire plein = skew_frac x delta
    double leverage = 3.0;
    double inv_frac = 0.25;        // part de l'equity engagée en marge à inventaire plein
    double order_frac = 0.25;      // taille d'un ordre = order_frac x plafond d'inventaire (notionnel)
    double requote_s = 60.0;
    double maker_fee_bps = 1.25;   // post-only, palier 0 (doc)
    double taker_fee_bps = 4.0;
    double slippage_bps = 2.0;     // sorties taker (supposé)
    double exit_half_spread_bps = 2.0; // sorties taker : demi-spread effectif (estimé sur les trades)
    double exit_to_frac = 0.5;     // après dépassement du plafond, retour à cette fraction du plafond
    int fill_model = 0;            // 0 optimiste (prix >= quote), 1 conservatrice (strictement au-delà)
    double queue_ahead_notional = 0; // file devant nous, modèle conservateur (volume à consommer d'abord)
    bool require_side = true;      // un bid n'est servi que par un agresseur vendeur, un ask par un acheteur
    double equity = 1000.0;
    bool random_delta = false;     // baseline : delta tiré au hasard à chaque requote et chaque côté
    std::vector<double> random_deltas;
    std::uint64_t seed = 1;
};

struct MmFill {
    double ts = 0, price = 0, qty = 0;
    int side = 0;                  // +1 : notre bid exécuté (on achète), -1 : notre ask exécuté
    double ref = 0;                // mark en vigueur au moment du fill
    double fee = 0;
    int session = 1;
};

struct MmExit {
    double ts = 0, price = 0, qty = 0, ref = 0;
    int side = 0;                  // +1 : on achète (on était short), -1 : on vend
    double fee = 0, cost = 0;      // cost = qty x |price - ref|
    bool liquidation = false;
};

struct MmPoint {
    double ts = 0, equity = 0;
    double inv_over_cap = 0;       // inventaire signé / plafond, au moment de l'échantillon
    int session = 1;
};

struct MmResult {
    double t0 = 0, t1 = 0;
    double start_equity = 0, end_equity = 0;
    std::vector<MmFill> fills;
    std::vector<MmExit> exits;
    std::vector<MmPoint> curve;    // un point par requote
    // Décomposition : end - start = capture + inventaire - frais - funding - coût des sorties
    double spread_capture = 0;     // somme s x qty x (ref - prix) sur les fills passifs
    double inventory_pnl = 0;      // somme inventaire x variation du mark
    double maker_fees = 0, taker_fees = 0, liq_fees = 0, funding = 0, exit_cost = 0;
    int liquidations = 0;
    bool bust = false;             // equity épuisée : simulation arrêtée
    double presence_s = 0, quoted_s = 0; // temps avec deux quotes à <= 20 bps du mark / temps total simulé
    double end_inventory_units = 0, end_ref = 0;
};

// Rejoue les trades de data dans [t0, t1).
MmResult run_mm(const MmData& data, const MmParams& p, double t0, double t1);

// ── Métriques ─────────────────────────────────────────────────────────────

struct Markout {
    double mean_bps = 0;
    long n = 0;
};

struct SideStats {
    long fills = 0;
    double notional = 0;
    Markout trade_proxy[4]; // 1 s, 10 s, 60 s, 300 s : mid proxy construit sur les trades
    Markout mark[2];        // 60 s, 300 s : mark connu à t + h
};

struct SessionStats {
    long fills = 0;
    double notional = 0;
    double capture_bps = 0;   // spread capturé vs mark, pondéré par le notionnel
    double pnl = 0;           // variation d'equity attribuée à cette session
    double days = 0;          // durée simulée dans cette session, en jours
};

struct MmMetrics {
    double days = 0;
    double fills_per_day = 0, notional_per_day = 0;
    double capture_bps = 0;                // spread capturé vs mark, bps du notionnel exécuté
    double net_pnl = 0, net_pct = 0;       // equity finale - initiale, et en % de l'equity initiale
    SideStats buy, sell;                   // buy : notre bid exécuté
    SessionStats in_session, off_session;
    double inv_mean_abs = 0, inv_p95_abs = 0, inv_at_cap_share = 0; // |inventaire| / plafond
    double max_dd_pct = 0, daily_sharpe = 0;
    int n_days = 0;
    double exit_cost = 0, exit_fees = 0;
    long exit_count = 0;
    double volume_share = 0;               // notre notionnel / notionnel total des trades de la période
    double tape_notional_per_day = 0;
    double threshold_1pct_7d = 0;          // 1 % du volume maker supposé = notionnel des trades sur 7 jours
    double presence_frac = 0;
};

MmMetrics compute_metrics(const MmResult& r, const MmData& d);

// Rendement de chaque jour UTC (dernier point du jour / dernier point du jour précédent, le premier jour
// part de l'equity initiale). Clé : numéro de jour depuis l'epoch.
std::map<long, double> daily_returns(const MmResult& r);

// Spread effectif estimé sur les trades : par fenêtre de window_s contenant au moins un trade de
// chaque sens, (prix moyen des achats agresseurs - prix moyen des ventes agresseurs) / mid, en bps ;
// médiane sur les fenêtres. session : -1 toutes, 0 ou 1 filtre. n_windows reçoit le nombre de fenêtres.
double effective_spread_bps(const MmData& d, double t0, double t1, double window_s, int session, long* n_windows);

} // namespace perp
