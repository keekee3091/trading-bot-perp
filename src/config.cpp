#include "perp/config.hpp"

#include <cstdlib>
#include <fstream>
#include <sstream>
#include <stdexcept>

namespace perp {

bool Config::set(const std::string& key, double v) {
#define X(member, k, def) \
    if (key == k) { member = v; return true; }
    PERP_CONFIG_FIELDS(X)
#undef X
    return false;
}

bool Config::get(const std::string& key, double& v) const {
#define X(member, k, def) \
    if (key == k) { v = member; return true; }
    PERP_CONFIG_FIELDS(X)
#undef X
    return false;
}

bool Config::set_kv(const std::string& key, const std::string& value) {
    if (key == "symbol" || key == "mode" || key == "ref_symbol") {
        strs[key] = value;
        return true;
    }
    char* end = nullptr;
    const double v = std::strtod(value.c_str(), &end);
    return end != value.c_str() && *end == '\0' && set(key, v);
}

static std::string trim(const std::string& s) {
    const char* ws = " \t\r\n";
    const size_t a = s.find_first_not_of(ws);
    if (a == std::string::npos) return "";
    return s.substr(a, s.find_last_not_of(ws) - a + 1);
}

void Config::apply_text(const std::string& yaml) {
    std::istringstream in(yaml);
    std::string line, section;
    int lineno = 0;
    while (std::getline(in, line)) {
        ++lineno;
        const size_t hash = line.find('#');
        if (hash != std::string::npos) line.erase(hash); // ponytail: pas de '#' dans les valeurs
        const std::string body = trim(line);
        if (body.empty()) continue;
        const bool indented = line[0] == ' ' || line[0] == '\t';
        const size_t colon = body.find(':');
        if (colon == std::string::npos)
            throw std::runtime_error("ligne " + std::to_string(lineno) + " : ':' attendu");
        std::string key = trim(body.substr(0, colon));
        std::string val = trim(body.substr(colon + 1));
        if (!indented) section.clear();
        if (val.empty() && !indented) { // en-tête de section (ou valeur vide : ignorée)
            section = key;
            continue;
        }
        if (val.empty() || val == "null" || val == "~") continue; // reste au défaut
        if (indented && !section.empty()) key = section + "." + key;

        if (val == "true" || val == "false") {
            if (!set(key, val == "true" ? 1.0 : 0.0))
                throw std::runtime_error("cle inconnue : " + key);
            continue;
        }
        char* end = nullptr;
        const double d = std::strtod(val.c_str(), &end);
        if (end != val.c_str() && *end == '\0') {
            if (!set(key, d)) throw std::runtime_error("cle inconnue : " + key);
            continue;
        }
        if (val.size() >= 2 && (val.front() == '"' || val.front() == '\'') && val.back() == val.front())
            val = val.substr(1, val.size() - 2);
        if (key == "symbol" || key == "mode" || key == "ref_symbol")
            strs[key] = val;
        else
            throw std::runtime_error("cle inconnue ou non numerique : " + key);
    }
}

void Config::load_file(const std::string& path) {
    std::ifstream f(path);
    if (!f) throw std::runtime_error("config illisible : " + path);
    std::stringstream ss;
    ss << f.rdbuf();
    apply_text(ss.str());
}

std::string Config::str(const std::string& key, const std::string& def) const {
    auto it = strs.find(key);
    return it == strs.end() ? def : it->second;
}

Instrument Config::instrument() const {
    Instrument i;
    i.symbol = str("symbol", "BTC-USD");
    i.max_leverage = inst_max_leverage;
    i.min_notional = inst_min_notional;
    i.qty_decimals = static_cast<int>(inst_qty_decimals);
    i.liquidation_fee = inst_liquidation_fee;
    i.taker_fee = inst_taker_fee;
    i.maker_fee = inst_maker_fee;
    i.maintenance_margin_rate = inst_mmr;
    i.mmr_factor = mmr_factor;
    return i;
}

} // namespace perp
