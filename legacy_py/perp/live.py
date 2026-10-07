"""
Execution live Polymarket Perps : NON IMPLEMENTEE volontairement.

Ce qui est confirme par la doc (2026-10-05) :
  - REST  https://api.perpetuals.polymarket.com   WS wss://ws.perpetuals.polymarket.com/v1/ws
  - Auth  EIP-712 CreateProxy (Polygon 137) -> POST /v1/account/proxy -> proxy_secret
          en-tetes REST : polymarket-proxy / polymarket-secret ; WS : frame {"req":"post","op":{"type":"auth",...}}
  - SDK   Python `polymarket` : AsyncSecureClient.create(private_key, wallet), open_perps_session()
  - Ordre POST /v1/trade/orders  corps {"op":{"type":"createOrders","args":[{iid,buy,p,qty,tif,po,ro,c}]},
          "sig":..., "salt":..., "ts":...}  tif in ioc|gtc|fok ; ro = reduce-only ; po = post-only
  - Annulation DELETE /v1/trade/orders (ou /orders-coid)

A faire avant de brancher : lire /perps/account-management (positions, solde), /perps/errors,
valider la signature des ordres avec le SDK, tester avec une mise minimale (min_notional ~10 pUSD).
Le bot ne depend que du Protocol `Exchange` de perp/exchange.py : il suffit d'implementer
market_open / market_close / on_tick / equity / positions ici.
"""


class LiveExchange:
    def __init__(self, *_, **__):
        raise NotImplementedError(
            "Execution live non implementee. Valider d'abord backtest puis paper (voir README)."
        )
