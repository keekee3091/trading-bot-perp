#include "perp/mm.hpp"

#include <algorithm>
#include <cmath>
#include <fstream>
#include <limits>
#include <map>
#include <random>
#include <sstream>
#include <stdexcept>

namespace perp {

namespace {

std::vector<std::string> split_line(const std::string& line) {
    std::vector<std::string> out;
    std::string cur;
    std::istringstream ss(line);
    while (std::getline(ss, cur, ',')) {
        while (!cur.empty() && (cur.back() == '\r' || cur.back() == ' ')) cur.pop_back();
        out.push_back(cur);
    }
    return out;
}

constexpr double kInf = std::numeric_limits<double>::infinity();
constexpr double kNaN = std::numeric_limits<double>::quiet_NaN();

double floor_tick(double x, double tick) { return std::floor(x / tick + 1e-9) * tick; }
double ceil_tick(double x, double tick) { return std::ceil(x / tick - 1e-9) * tick; }

} // namespace

std::vector<Trade> load_trades_csv(const std::string& path, bool long_is_buyer) {
    std::ifstream f(path);
    if (!f) throw std::runtime_error("trades illisibles : " + path);
    std::string line;
    std::getline(f, line); // en-tête
    std::vector<Trade> out;
    while (std::getline(f, line)) {
        const auto r = split_line(line);
        if (r.size() < 6) continue;
        try {
            Trade t;
            t.ts = std::stod(r[0]) / 1000.0;
            t.dir = (r[2] == "long") == long_is_buyer ? +1 : -1;
            t.price = std::stod(r[3]);
            t.qty = std::stod(r[4]);
            t.settlement = r[5] == "1";
            if (t.price > 0 && t.qty > 0) out.push_back(t);
        } catch (const std::exception&) {
            continue;
        }
    }
    std::stable_sort(out.begin(), out.end(), [](const Trade& a, const Trade& b) { return a.ts < b.ts; });
    return out;
}

std::vector<MarkPoint> load_mark_csv(const std::string& path) {
    std::ifstream f(path);
    if (!f) throw std::runtime_error("mark illisible : " + path);
    std::string line;
    std::getline(f, line);
    std::vector<MarkPoint> out;
    while (std::getline(f, line)) {
        const auto r = split_line(line);
        if (r.size() < 2) continue;
        try {
            MarkPoint m;
            m.ts = std::stod(r[0]) / 1000.0;
            m.mark = std::stod(r[1]);
            if (m.mark > 0) out.push_back(m);
        } catch (const std::exception&) {
            continue;
        }
    }
    std::sort(out.begin(), out.end(), [](const MarkPoint& a, const MarkPoint& b) { return a.ts < b.ts; });
    return out;
}

int in_session(const std::string& category, double ts) {
    if (category == "crypto") return 1;
    const long day = static_cast<long>(std::floor(ts / 86400.0));
    const int dow = static_cast<int>(((day % 7) + 7 + 3) % 7); // 1970-01-01 : jeudi ; lundi = 0
    const int hm = static_cast<int>((ts - static_cast<double>(day) * 86400.0) / 60.0);
    if (category == "index" || category == "commodity") {
        if (dow == 5 || (dow == 4 && hm >= 21 * 60) || (dow == 6 && hm < 22 * 60)) return 0;
        return 1;
    }
    if (category == "equity") return (dow < 5 && hm >= 13 * 60 + 30 && hm < 20 * 60) ? 1 : 0;
    return 1;
}

// ── Moteur ────────────────────────────────────────────────────────────────

namespace {

struct Engine {
    const MmData& d;
    const MmParams& p;
    MmResult r;
    double cash = 0, q = 0, ref = 0;
    size_t mark_next = 0, fund_idx = 0;
    double next_requote = 0, next_fund = 0;
    // quotes courantes
    double bid_px = 0, ask_px = 0, bid_rem = 0, ask_rem = 0, bid_queue = 0, ask_queue = 0;
    double period_start = 0;
    bool period_present = false, started = false;
    std::mt19937_64 rng;

    Engine(const MmData& data, const MmParams& params) : d(data), p(params), rng(params.seed) {}

    double equity() const { return cash + q * ref; }
    double mark_time(size_t i) const { return d.mark[i].ts + d.mark_interval_s; }
    double uni() { return static_cast<double>(rng() >> 11) * (1.0 / 9007199254740992.0); }

    void init(double t0) {
        // mark connu à t0 : dernier bucket terminé
        mark_next = 0;
        while (mark_next < d.mark.size() && mark_time(mark_next) <= t0) ++mark_next;
        ref = mark_next > 0 ? d.mark[mark_next - 1].mark : 0.0;
        cash = p.equity;
        next_requote = t0;
        next_fund = (std::floor(t0 / 3600.0) + 1.0) * 3600.0;
        r.t0 = t0;
        r.start_equity = p.equity;
    }

    void close_period(double t) {
        if (!started) return;
        const double dt = std::max(0.0, t - period_start);
        if (period_present) r.presence_s += dt;
    }

    void fill(int side, double price, double qty, double t) {
        const double fee = qty * price * p.maker_fee_bps / 1e4;
        cash -= side * qty * price + fee;
        q += side * qty;
        r.maker_fees += fee;
        r.spread_capture += side * qty * (ref - price);
        r.fills.push_back({t, price, qty, side, ref, fee, in_session(d.category, t)});
    }

    // Sortie taker : on ramène |notionnel| à target_notional.
    void taker_reduce(double qty, double t, bool liquidation) {
        if (qty <= 0) return;
        const int side = q > 0 ? -1 : +1;
        const double c = (p.exit_half_spread_bps + p.slippage_bps) / 1e4;
        const double price = ref * (1.0 + (side > 0 ? c : -c));
        const double rate = p.taker_fee_bps / 1e4 + (liquidation ? d.inst.liquidation_fee : 0.0);
        const double fee = qty * price * rate;
        cash -= side * qty * price + fee;
        q += side * qty;
        r.exit_cost += qty * std::fabs(price - ref);
        r.taker_fees += qty * price * p.taker_fee_bps / 1e4;
        if (liquidation) r.liq_fees += qty * price * d.inst.liquidation_fee;
        r.exits.push_back({t, price, qty, ref, side, fee, qty * std::fabs(price - ref), liquidation});
    }

    bool risk_checks(double t) {
        if (ref <= 0) return true;
        const double eq = equity();
        if (eq <= 0) {
            r.bust = true;
            return false;
        }
        // liquidation : equity <= marge de maintenance
        if (q != 0 && eq <= std::fabs(q) * ref * d.inst.mmr()) {
            taker_reduce(std::fabs(q), t, true);
            ++r.liquidations;
            bid_rem = ask_rem = 0;
            if (cash <= 0) {
                cash = 0;
                r.bust = true;
                return false;
            }
            return true;
        }
        // plafond d'inventaire dépassé : sortie taker vers exit_to_frac x plafond
        const double cap = p.leverage * p.inv_frac * eq;
        if (std::fabs(q * ref) > cap) {
            taker_reduce((std::fabs(q * ref) - p.exit_to_frac * cap) / ref, t, false);
        }
        return true;
    }

    void apply_mark(size_t i) {
        const double nm = d.mark[i].mark;
        if (ref > 0) r.inventory_pnl += q * (nm - ref);
        ref = nm;
    }

    void requote(double t) {
        close_period(t);
        started = true;
        period_start = t;
        period_present = false;
        bid_px = ask_px = bid_rem = ask_rem = 0;
        if (ref <= 0) return;
        const double eq = equity();
        r.curve.push_back({t, eq, 0.0, in_session(d.category, t)});
        if (eq <= 0) {
            r.bust = true;
            return;
        }
        if (!risk_checks(t) || r.bust) return;
        const double eq2 = equity();
        const double cap = p.leverage * p.inv_frac * eq2;
        const double n = q * ref;
        r.curve.back().inv_over_cap = cap > 0 ? n / cap : 0.0;
        r.curve.back().equity = eq2;
        const double order_notional = p.order_frac * cap;
        if (order_notional < std::max(d.inst.min_notional, 10.0)) return;
        const double s = std::max(-1.0, std::min(1.0, cap > 0 ? n / cap : 0.0));
        double db = p.delta_bps, da = p.delta_bps;
        if (p.random_delta && !p.random_deltas.empty()) {
            db = p.random_deltas[static_cast<size_t>(uni() * static_cast<double>(p.random_deltas.size())) % p.random_deltas.size()];
            da = p.random_deltas[static_cast<size_t>(uni() * static_cast<double>(p.random_deltas.size())) % p.random_deltas.size()];
        }
        // plus on est long (s > 0), plus on éloigne le bid et rapproche le ask
        const double bid_off = std::max(0.1, db + p.skew_frac * db * s);
        const double ask_off = std::max(0.1, da - p.skew_frac * da * s);
        const bool bid_ok = n + order_notional <= cap;
        const bool ask_ok = -n + order_notional <= cap;
        const double qty = order_notional / ref;
        const double q_ahead = p.fill_model == 1 ? p.queue_ahead_notional / ref : 0.0;
        if (bid_ok) {
            bid_px = floor_tick(ref * (1.0 - bid_off / 1e4), d.tick);
            bid_rem = qty;
            bid_queue = q_ahead;
        }
        if (ask_ok) {
            ask_px = ceil_tick(ref * (1.0 + ask_off / 1e4), d.tick);
            ask_rem = qty;
            ask_queue = q_ahead;
        }
        if (bid_ok && ask_ok && bid_px >= ask_px) { // tick trop gros : on garde un spread d'un tick
            bid_px = floor_tick(ref - d.tick / 2, d.tick);
            ask_px = bid_px + d.tick;
        }
        period_present = bid_ok && ask_ok && bid_off <= 20.0 && ask_off <= 20.0;
    }

    // Traite tous les événements (mark, funding, requote) de date <= t, dans cet ordre en cas d'égalité.
    // strict : date < t (fin de fenêtre).
    void events_until(double t, bool strict) {
        for (;;) {
            const double tm = mark_next < d.mark.size() ? mark_time(mark_next) : kInf;
            const double te = std::min({tm, next_fund, next_requote});
            if (te > t || (strict && te >= t) || r.bust) return;
            if (te == tm) {
                apply_mark(mark_next++);
                if (!risk_checks(te)) return;
            } else if (te == next_fund) {
                const double rate = d.funding.empty() ? 0.0 : funding_at(d.funding, fund_idx, te);
                const double charge = q * ref * rate;
                cash -= charge;
                r.funding += charge;
                next_fund += 3600.0;
            } else {
                requote(te);
                next_requote += p.requote_s;
            }
        }
    }

    void on_trade(const Trade& tr) {
        if (r.bust || ref <= 0 || tr.settlement) return;
        const double eps = 1e-12;
        // notre bid : servi par un agresseur vendeur
        if (bid_rem > 0 && (!p.require_side || tr.dir < 0)) {
            const bool ok = p.fill_model == 0 ? tr.price <= bid_px + eps : tr.price < bid_px - eps;
            if (ok) {
                double take = tr.qty;
                if (p.fill_model == 1 && bid_queue > 0) {
                    take = std::max(0.0, tr.qty - bid_queue);
                    bid_queue = std::max(0.0, bid_queue - tr.qty);
                }
                const double f = std::min(bid_rem, take);
                if (f > 0) {
                    fill(+1, bid_px, f, tr.ts);
                    bid_rem -= f;
                    risk_checks(tr.ts);
                }
            }
        }
        if (ask_rem > 0 && (!p.require_side || tr.dir > 0)) {
            const bool ok = p.fill_model == 0 ? tr.price >= ask_px - eps : tr.price > ask_px + eps;
            if (ok) {
                double take = tr.qty;
                if (p.fill_model == 1 && ask_queue > 0) {
                    take = std::max(0.0, tr.qty - ask_queue);
                    ask_queue = std::max(0.0, ask_queue - tr.qty);
                }
                const double f = std::min(ask_rem, take);
                if (f > 0) {
                    fill(-1, ask_px, f, tr.ts);
                    ask_rem -= f;
                    risk_checks(tr.ts);
                }
            }
        }
    }
};

} // namespace

MmResult run_mm(const MmData& data, const MmParams& p, double t0, double t1) {
    Engine e(data, p);
    e.init(t0);
    auto it = std::lower_bound(data.trades.begin(), data.trades.end(), t0,
                               [](const Trade& t, double x) { return t.ts < x; });
    for (; it != data.trades.end() && it->ts < t1 && !e.r.bust; ++it) {
        e.events_until(it->ts, false);
        e.on_trade(*it);
    }
    e.events_until(t1, true);
    e.close_period(t1);
    e.r.t1 = t1;
    e.r.end_equity = e.equity();
    e.r.end_inventory_units = e.q;
    e.r.end_ref = e.ref;
    return e.r;
}

// ── Métriques ─────────────────────────────────────────────────────────────

namespace {

// Mid proxy construit sur les trades : moyenne du dernier prix d'achat agresseur et du dernier prix
// de vente agresseur dans les 60 s ; à défaut le dernier prix. NaN s'il n'y a aucun trade avant t.
double trade_mid_proxy(const std::vector<Trade>& tr, double t) {
    auto it = std::upper_bound(tr.begin(), tr.end(), t, [](double x, const Trade& a) { return x < a.ts; });
    double lb = kNaN, la = kNaN, last = kNaN;
    int scanned = 0;
    while (it != tr.begin() && scanned < 400) {
        --it;
        ++scanned;
        if (std::isnan(last)) last = it->price;
        if (t - it->ts > 60.0) break;
        if (it->dir < 0 && std::isnan(lb)) lb = it->price;
        if (it->dir > 0 && std::isnan(la)) la = it->price;
        if (!std::isnan(lb) && !std::isnan(la)) break;
    }
    if (!std::isnan(lb) && !std::isnan(la)) return 0.5 * (lb + la);
    return last;
}

double mark_at(const std::vector<MarkPoint>& m, double interval, double t) {
    // dernier bucket terminé à t : ts + interval <= t
    auto it = std::upper_bound(m.begin(), m.end(), t - interval, [](double x, const MarkPoint& a) { return x < a.ts; });
    return it == m.begin() ? kNaN : (it - 1)->mark;
}

void add(Markout& m, double x) {
    m.mean_bps = (m.mean_bps * static_cast<double>(m.n) + x) / static_cast<double>(m.n + 1);
    ++m.n;
}

} // namespace

MmMetrics compute_metrics(const MmResult& r, const MmData& d) {
    MmMetrics m;
    m.days = (r.t1 - r.t0) / 86400.0;
    if (m.days <= 0) return m;
    double notional = 0, capture = 0;
    double cap_in = 0, cap_off = 0, not_in = 0, not_off = 0;
    const double hs[4] = {1.0, 10.0, 60.0, 300.0};
    const double tape_end = d.trades.empty() ? 0.0 : d.trades.back().ts;
    for (const MmFill& f : r.fills) {
        const double n = f.qty * f.price;
        const double cap = f.side * f.qty * (f.ref - f.price);
        notional += n;
        capture += cap;
        (f.session ? cap_in : cap_off) += cap;
        (f.session ? not_in : not_off) += n;
        SideStats& s = f.side > 0 ? m.buy : m.sell;
        ++s.fills;
        s.notional += n;
        for (int k = 0; k < 4; ++k) {
            if (f.ts + hs[k] > tape_end) continue;
            const double mid = trade_mid_proxy(d.trades, f.ts + hs[k]);
            if (std::isnan(mid)) continue;
            add(s.trade_proxy[k], f.side * (mid - f.price) / f.price * 1e4);
        }
        for (int k = 0; k < 2; ++k) {
            const double mk = mark_at(d.mark, d.mark_interval_s, f.ts + hs[k + 2]);
            if (std::isnan(mk) || f.ts + hs[k + 2] > r.t1 + 3600) continue;
            add(s.mark[k], f.side * (mk - f.price) / f.price * 1e4);
        }
    }
    m.fills_per_day = static_cast<double>(r.fills.size()) / m.days;
    m.notional_per_day = notional / m.days;
    m.capture_bps = notional > 0 ? capture / notional * 1e4 : 0.0;
    m.in_session.fills = m.off_session.fills = 0;
    for (const MmFill& f : r.fills) (f.session ? m.in_session : m.off_session).fills++;
    m.in_session.notional = not_in;
    m.off_session.notional = not_off;
    m.in_session.capture_bps = not_in > 0 ? cap_in / not_in * 1e4 : 0.0;
    m.off_session.capture_bps = not_off > 0 ? cap_off / not_off * 1e4 : 0.0;
    m.net_pnl = r.end_equity - r.start_equity;
    m.net_pct = r.start_equity > 0 ? 100.0 * m.net_pnl / r.start_equity : 0.0;
    m.exit_cost = r.exit_cost;
    m.exit_fees = r.taker_fees + r.liq_fees;
    m.exit_count = static_cast<long>(r.exits.size());

    // courbe : drawdown, inventaire, session
    double peak = r.start_equity, dd = 0;
    std::vector<double> inv;
    long at_cap = 0;
    for (size_t i = 0; i < r.curve.size(); ++i) {
        const MmPoint& pt = r.curve[i];
        peak = std::max(peak, pt.equity);
        if (peak > 0) dd = std::max(dd, (peak - pt.equity) / peak);
        inv.push_back(std::fabs(pt.inv_over_cap));
        at_cap += std::fabs(pt.inv_over_cap) >= 0.95 ? 1 : 0;
        const double next_t = i + 1 < r.curve.size() ? r.curve[i + 1].ts : r.t1;
        const double next_e = i + 1 < r.curve.size() ? r.curve[i + 1].equity : r.end_equity;
        SessionStats& ss = pt.session ? m.in_session : m.off_session;
        ss.pnl += next_e - pt.equity;
        ss.days += (next_t - pt.ts) / 86400.0;
    }
    m.max_dd_pct = dd * 100.0;
    if (!inv.empty()) {
        double s = 0;
        for (double x : inv) s += x;
        m.inv_mean_abs = s / static_cast<double>(inv.size());
        std::sort(inv.begin(), inv.end());
        m.inv_p95_abs = inv[static_cast<size_t>(0.95 * static_cast<double>(inv.size() - 1))];
        m.inv_at_cap_share = static_cast<double>(at_cap) / static_cast<double>(r.curve.size());
    }
    // Sharpe journalier : dernier point de chaque jour UTC
    std::map<long, double> day_eq;
    for (const MmPoint& pt : r.curve) day_eq[static_cast<long>(std::floor(pt.ts / 86400.0))] = pt.equity;
    std::vector<double> rets;
    double prev = r.start_equity;
    for (const auto& kv : day_eq) {
        if (prev > 0) rets.push_back(kv.second / prev - 1.0);
        prev = kv.second;
    }
    m.n_days = static_cast<int>(rets.size());
    if (rets.size() >= 3) {
        double mu = 0;
        for (double x : rets) mu += x;
        mu /= static_cast<double>(rets.size());
        double v = 0;
        for (double x : rets) v += (x - mu) * (x - mu);
        const double sd = std::sqrt(v / static_cast<double>(rets.size() - 1));
        m.daily_sharpe = sd > 0 ? mu / sd * std::sqrt(365.0) : 0.0;
    }
    // part de volume et seuil d'éligibilité de 1 % sur 7 jours (volume de trades = volume maker)
    double tape = 0;
    auto lo = std::lower_bound(d.trades.begin(), d.trades.end(), r.t0, [](const Trade& t, double x) { return t.ts < x; });
    for (; lo != d.trades.end() && lo->ts < r.t1; ++lo) tape += lo->price * lo->qty;
    m.tape_notional_per_day = tape / m.days;
    m.volume_share = tape > 0 ? notional / tape : 0.0;
    m.threshold_1pct_7d = 0.01 * 7.0 * m.tape_notional_per_day;
    m.presence_frac = r.t1 > r.t0 ? r.presence_s / (r.t1 - r.t0) : 0.0;
    return m;
}

std::map<long, double> daily_returns(const MmResult& r) {
    std::map<long, double> day_eq, out;
    for (const MmPoint& pt : r.curve) day_eq[static_cast<long>(std::floor(pt.ts / 86400.0))] = pt.equity;
    double prev = r.start_equity;
    for (const auto& kv : day_eq) {
        if (prev > 0) out[kv.first] = kv.second / prev - 1.0;
        prev = kv.second;
    }
    return out;
}

double effective_spread_bps(const MmData& d, double t0, double t1, double window_s, int session, long* n_windows) {
    struct Acc { double sb = 0, ss = 0; long nb = 0, ns = 0; };
    std::map<long, Acc> w;
    auto lo = std::lower_bound(d.trades.begin(), d.trades.end(), t0, [](const Trade& t, double x) { return t.ts < x; });
    for (; lo != d.trades.end() && lo->ts < t1; ++lo) {
        if (lo->settlement) continue;
        if (session >= 0 && in_session(d.category, lo->ts) != session) continue;
        Acc& a = w[static_cast<long>(std::floor(lo->ts / window_s))];
        if (lo->dir > 0) { a.sb += lo->price; ++a.nb; }
        else { a.ss += lo->price; ++a.ns; }
    }
    std::vector<double> sp;
    for (const auto& kv : w) {
        const Acc& a = kv.second;
        if (a.nb < 1 || a.ns < 1) continue;
        const double pb = a.sb / static_cast<double>(a.nb), ps = a.ss / static_cast<double>(a.ns);
        const double mid = 0.5 * (pb + ps);
        if (mid > 0) sp.push_back((pb - ps) / mid * 1e4);
    }
    if (n_windows) *n_windows = static_cast<long>(sp.size());
    if (sp.empty()) return kNaN;
    std::sort(sp.begin(), sp.end());
    return sp[sp.size() / 2];
}

} // namespace perp
