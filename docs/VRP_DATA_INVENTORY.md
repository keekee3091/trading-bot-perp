# H_VRP, phase 0 : inventaire des données, 2026-10-10

Aucun ordre, aucun compte créé, rien acheté. Cadre : dépôt de recherche, usage personnel et non commercial. Vérification faite le **2026-10-10** (date réelle, `date -u`). Mention « NON VÉRIFIÉ » = non établi par une page officielle lue, jamais supposé.
Fichiers téléchargés : sous `data/vrp/` (ligne `data/vrp/` ajoutée à `.gitignore`, vérifié par `git check-ignore`). Rien de brut n'est copié dans `docs/` ni `results/`. Sur ces fichiers, **seuls ont été relevés** : colonnes, nombre de lignes, première et dernière date, pas entre dates. Aucun rendement, alpha ni régression d'un indice de stratégie n'a été calculé.

## 1. Conditions d'usage lues, et ce qui a été téléchargé

- Conditions d'utilisation des sites Cboe (https://www.cboe.com/terms, mise à jour du 2022-11-16, lues le 2026-10-10 par extrait) : « You may view, print and download one copy of the Materials for your personal non-commercial use in connection with products and services offered by Cboe » ; interdits sans accord écrit : copier, stocker dans un système de récupération électronique, redistribuer, créer une oeuvre dérivée (par exemple un produit financier ou un indice). **Aucune clause sur les robots ou scrapers trouvée dans l'extrait** : texte intégral NON VÉRIFIÉ. La fourniture de certaines parties du site relève d'autres accords (feed d'indices, DataShop, accord d'abonné : licence « Non-Professional » pour usage personnel, redistribution interdite).
- Les fichiers `…/daily_prices/<TICKER>_History.csv` sont les liens « Historical Data » publics des pages Cboe (page https://www.cboe.com/tradable-products/vix/vix-historical-data pour la volatilité ; pour les indices de stratégie le lien est celui du tableau de bord de l'indice, NON VÉRIFIÉ page par page). Lecture retenue : **un exemplaire de chaque fichier, usage personnel de recherche, autorisé** ; zone grise : la clause de stockage électronique, d'où : un seul exemplaire par fichier, aucune redistribution, aucune série brute dans le dépôt versionné, aucun produit dérivé.
- Téléchargement fait avec un User-Agent honnête (`research-personal-bot (<contact>; personal research, 1 request at a time)`), **une requête à la fois, 2 s entre deux requêtes**, 26 requêtes Cboe au total (21 fichiers d'indices conservés, 4 refus 403, 1 fichier de futures supprimé) et 2 archives French, une seule fois chacun.
- Kenneth French (déjà utilisé dans le dépôt, https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html) : « Copyright Eugene F. Fama and Kenneth R. French », pas de licence explicite lue, usage de recherche courant avec citation : **toléré, usage personnel** (inchangé par rapport à `data/under/MANIFEST.txt`).

## 2. (a) Indices de stratégie Cboe, gratuits : téléchargés et vérifiés (dates et colonnes seulement)

Les trois dernières colonnes sont des constats sur les fichiers (2026-10-10). Source des définitions : fiche et méthodologie Cboe (https://cdn.cboe.com/api/global/us_indices/governance/Cboe_PutWrite_Indices_Methodology.pdf, https://cdn.cboe.com/resources/indices/factsheet/CboeGlobalIndices_PUTY-Index.pdf, lues le 2026-10-10).

| Ticker | Stratégie (source Cboe) | Première date du CSV | Lignes | Remarque |
|---|---|---|---|---|
| **PUT** | vente d'un put SPX à la monnaie, mensuel, bons du Trésor 1 mois en collatéral | 1991-03-04 | 4 981 | **quotidien seulement depuis 2007-01-03** (avant : une poignée de points isolés, trous jusqu'à 1 159 jours) ; la fiche dit « daily closing values beginning January 03, 2007 » |
| **PUTY** | vente d'un put SPX 2 % hors de la monnaie, mensuel | 1986-06-30 | 10 145 | historique quotidien depuis 1986, **dont une part reconstruite** (« back-tested » avant la date de lancement, NON VÉRIFIÉ laquelle) |
| **WPUT** | put SPX à la monnaie, hebdomadaire | 2006-01-31 | 5 203 | |
| **CNDR** | condor de fer SPX (put delta ≈ -0,15 et call hors de la monnaie vendus, mensuel) | 1986-06-20 | 10 149 | reconstruit avant lancement (NON VÉRIFIÉ lequel) |
| BXM | covered call SPX à la monnaie | 2002-03-22 | 6 175 | secondaire (équivalent par parité put-call, cf. AQR en recherche, non lu) |
| BXMD | covered call SPX delta 30 | 1986-06-20 | 10 149 | secondaire |
| BXY | covered call 2 % hors de la monnaie | 1988-06-01 | 9 657 | secondaire |
| PUTR | put RUT (Russell 2000) à la monnaie, mensuel | 2001-01-31 | 6 458 | hors échantillon |
| PTLT | put TLT (iShares 20+ Year Treasury) à la monnaie, mensuel | 2005-01-21 | 5 464 | hors échantillon |
| BXN | covered call Nasdaq-100 | 2009-09-18 | 4 288 | hors échantillon (covered call, pas put-write) |
| BXR | covered call Russell 2000 | 2000-12-29 | 6 479 | secondaire |

Prix d'exécution **dans** les indices (méthodologie lue) : pour PUT et PUTY, le put vendu est valorisé à la **moyenne pondérée par le volume (VWAP) des transactions OPRA entre 11 h 30 et 12 h, heure de l'Est** (à défaut, dernier bid) ; PTLT : dernier NBBO bid de la journée ; mise à jour quotidienne au milieu bid-ask. **Aucun spread payé à la vente (hors VWAP), aucune commission, aucun slippage** : un surcoût doit être modélisé en sensibilité (voir `docs/VRP_PREREG.md`). Les indices ne sont **pas** des prix proxys de type Black-Scholes : ce sont des prix d'options réels (transactions), contrairement à la piste E.
**Non téléchargeables à l'URL essayée (HTTP 403)** : PXEF, PYEF, BXEF (MSCI Emerging Markets), PUTN : le chemin ou le ticker est autre ou l'accès est restreint, NON VÉRIFIÉ ; PDEF non essayé. Pas d'indice put-write sur l'or trouvé (GLDTI est un buy-write sur GLD, GLDBUF/GLDPRO sont des résultats cibles ; fichiers non essayés, NON VÉRIFIÉ). WPTR (Russell hebdomadaire) existe selon la méthodologie, non essayé.

## 3. (b) Volatilité, skew, futures VIX

| Série | Source | Couverture constatée | Gratuit ? | Réserves |
|---|---|---|---|---|
| VIX (OHLC) | https://cdn-api.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv | 1990-01-02 -> 2026-10-09, 9 291 lignes | oui (même régime d'usage que ci-dessus) | aussi en dépôt via FRED (`FRED_VIXCLS.csv`) |
| VVIX | idem | 2006-03-06 -> 2026-10-09, 5 122 | oui | |
| SKEW | idem | 1990-01-02 -> 2026-10-09, 9 245 | oui | |
| VIX9D, VIX3M | idem | 2011-01-04 / 2009-09-18 -> 2026-10-09 | oui | |
| VXN, RVX, VXEEM, GVZ, VXTLT | idem | VXN 2009-09-14, RVX 2009-09-16, VXEEM 2011-03-16, GVZ 2009-09-18, VXTLT 2004-01-02 -> 2026-10-09 | oui | indices de volatilité implicite des sous-jacents hors échantillon (NDX, RUT, EEM, or, TLT) |
| Futures VIX (VX), règlement quotidien par contrat | `https://cdn.cboe.com/data/us/futures/market_statistics/historical_data/VX/VX_<AAAA-MM-JJ>.csv` (un fichier par échéance ; 1 fichier testé : colonnes Trade Date, Futures, Open, High, Low, Close, Settle, Change, Total Volume, EFP, Open Interest, rempli puis supprimé) ; page https://www.cboe.com/us/futures/market_statistics/historical_data/ | page : « Daily Volume and Open Interest from 2004 to Current », règlements « from 2013 onward », archive 2004-2013 | oui selon la page | **les échéances 2004-2013 et le bon chemin pour chaque année : NON VÉRIFIÉ** ; conditions propres à CFE : NON VÉRIFIÉ (on suppose les mêmes que cboe.com/terms) |
| Tick par tick des futures VIX | https://datashop.cboe.com/cfe-vix-volatility-index-futures-trades-quotes | avril 2004 -> février 2018 | payant (prix NON VÉRIFIÉ) | |

## 4. (c) Chaînes d'options historiques réelles (SPX / SPY)

Gratuit aujourd'hui : **rien de vérifié** à profondeur utile. Alpha Vantage (options historiques) : couverture, SPX inclus, quotas NON VÉRIFIÉS (page de documentation lue, endpoint tronqué, produit présenté comme premium). Tiingo : aucun produit d'options trouvé, NON VÉRIFIÉ (non consulté pour les options). Massive (ex Polygon) : offre gratuite **de 2 ans** d'historique avec 5 appels par minute (https://massive.com/pricing), index SPX inclus ? NON VÉRIFIÉ. Yahoo Finance : exclu (pas d'API publique officielle, règle du dépôt).

| Fournisseur | Couverture | Profondeur | Licence | Coût (page lue le 2026-10-10) | Source |
|---|---|---|---|---|---|
| **Cboe DataShop**, Option EOD Summary (tout le marché) | EOD, bid/ask, volume, intérêt ouvert | depuis janvier 2012 | abonné, usage selon accord ; redistribution interdite | 50 $ par jour, plafond 300 $ par mois, 1 500 $ par an, **archive 2012 à aujourd'hui 7 200 $** | https://datashop.cboe.com/option-eod-summary |
| **Cboe DataShop**, ^SPX seul (comparaison tierce) | EOD, SPX + SPXW | 2012 -> 2026 | idem | environ **2 200 $** (plafond atteint à 4 ans) sans les grecques, 3 385 $ avec | https://concretumgroup.substack.com/p/spx-options-database-databento-vs (source secondaire, prix NON VÉRIFIÉS sur le site Cboe, calculés dynamiquement dans le panier) |
| **Databento**, OPRA (SPX.OPT, SPXW.OPT) | quotes, trades ; pas d'IV | depuis au moins 2012 | usage selon plan | **environ 6 123 $** pour 2012-2026 en facturation à l'usage (source tierce) ; page de prix : Standard 199 $/mois, Plus 1 750 $, Unlimited 4 500 $, 125 $ de crédit gratuit à l'ouverture d'un compte (**non utilisé : pas de compte**) ; **profondeur selon plan contradictoire entre la page de prix et la source tierce : NON VÉRIFIÉ** | https://databento.com/pricing |
| **ORATS** | EOD options, IV, grecques, SPX et SPY | 2007 -> aujourd'hui (« 15+ years ») | plans individuels | **199 $/mois** (Delayed Data API), pas d'essai gratuit, échantillons sur « ORATS University » ; limites d'accès à l'historique complet et conditions d'export : NON VÉRIFIÉES | https://orats.com/data |
| **ThetaData** | options, index US, EOD et tick | Value 6 ans, Standard 10 ans, Pro 14 ans | « Individual Personal use only, no redistribution or business use » | **40 / 80 / 160 $ par mois** (Value / Standard / Pro) ; bid/ask EOD des options **sur indice SPX** sur la période : NON VÉRIFIÉ (la page annonce « 100 % market coverage » pour les indices US) | https://thetadata.net/pricing |
| **Massive (ex Polygon)** | options US | Basic gratuit 2 ans EOD ; Developer 79 $/mois **4 ans** ; Advanced 199 $/mois **5 ans et plus** (page options) | plans individuels « non-pros only » | gratuit à 199 $/mois | https://massive.com/pricing?product=options ; options sur indice (SPX) : NON VÉRIFIÉ |
| **OptionMetrics Ivy DB US** (référence académique) | options listées US et indices, IV, grecques | **depuis janvier 1996** | institutions (WRDS) ; accès individuel : NON VÉRIFIÉ | **prix non publiés** (« contact ») ; gratuit seulement via une université abonnée (WRDS) : pas disponible ici (affiliation de l'utilisateur NON VÉRIFIÉE) | https://optionmetrics.com/data-products/ |
| Cboe Global Indices (feed) | flux d'indices | historique par DataShop | abonnement | « custom pricing » ; une source tierce parle de frais à partir de 1 000 $/mois, NON VÉRIFIÉ sur le site | https://www.cboe.com/data/global-indices-feed/ |

## 5. (d) Autres sous-jacents, hors échantillon réel

| Sous-jacent | Indice de stratégie gratuit | Statut |
|---|---|---|
| Russell 2000 (RUT) | PUTR (2001-01-31 ->), BXR ; VIX-équivalent RVX | **téléchargé** ; série de prix RUT pour le bêta : NON VÉRIFIÉE (absente du dépôt ; repli : facteurs French SMB et Mkt-RF) |
| Nasdaq-100 (NDX) | BXN (covered call, 2009-09-18 ->) ; pas de PutWrite NDX trouvé (PUTN : 403) ; VXN | téléchargé ; bêta : `FRED_NASDAQ100.csv` (indice de prix) déjà en dépôt |
| Obligations 20 ans+ (TLT) | **PTLT** (put TLT à la monnaie, 2005-01-21 ->) ; VXTLT | **téléchargé** ; bêta : TLT par Tiingo (plan gratuit, clé existante), non téléchargé ici |
| Marchés émergents (EEM / MSCI EM) | PXEF, PYEF, PDEF (MSCI EM PutWrite, annoncés par Cboe) : **fichiers non obtenus (403)** ; VXEEM téléchargé | **NON VÉRIFIÉ**, ne pas supposer l'accès gratuit |
| Or (GLD) | aucun put-write Cboe trouvé (GLDTI = buy-write sur GLD) ; GVZ téléchargé | **non disponible gratuitement** pour un put-write ; chaînes GLD : payant (voir section 4) |

## 6. Facteurs Fama-French (Kenneth French), vérifiés par téléchargement

`F-F_Research_Data_Factors_CSV.zip` : **mensuel, Mkt-RF, SMB, HML, RF, 1926-07 -> 2026-08** (1 202 lignes mensuelles, plus des lignes annuelles non comptées). `F-F_Momentum_Factor_CSV.zip` : **Mom mensuel, 1927-01 -> 2026-08** (1 196 lignes). Fichiers dans `data/vrp/ff3.zip` et `data/vrp/mom.zip`. Le dernier mois est **2026-08** : le mois courant (2026-10) et septembre n'y sont pas encore. Les facteurs sont des rendements de marché américain total (CRSP), pas du S&P 500 ; l'écart est acceptable pour un bêta mensuel mais est déclaré. Les valeurs sont en pourcentage.

## 7. Ce qui est gratuit, ce qui ne l'est pas, et la liste d'achat

| Catégorie | Gratuit aujourd'hui | Payant |
|---|---|---|
| Indices de stratégie (PUT, PUTY, WPUT, CNDR, BXM, BXMD, PUTR, PTLT, BXN) | **oui, vérifié** | rien à acheter pour la phase 1 |
| VIX, VVIX, SKEW, VIX9D, VIX3M, indices de volatilité sectoriels | oui | |
| Futures VIX (règlement quotidien par contrat) | oui selon la page, mais le chemin des années 2004-2013 n'est **pas vérifié** | tick : DataShop, prix non vérifié |
| Facteurs Fama-French et momentum | oui | |
| Chaînes d'options réelles SPX/SPY | **non** (2 ans gratuits chez Massive, SPX NON VÉRIFIÉ) | voir ci-dessous |
| EEM, or | indices de volatilité seulement | chaînes payantes |

**Liste chiffrée, de la moins chère à la plus chère** (aucun achat fait ; tous les prix sont ceux des pages lues, sauf mention) :

| Option | Coût | Apporte | À vérifier avant d'acheter |
|---|---|---|---|
| ThetaData Options Standard ou Pro, **un mois** | 80 ou 160 $ | EOD ou tick sur 10 ou 14 ans, usage personnel | SPX/SPXW bid/ask EOD inclus, export complet en un mois, 14 ans = depuis environ 2012 |
| ORATS, **un mois** | 199 $ | IV, grecques, SPX, depuis 2007 (couvre 2008) | limite d'export de l'historique complet, droits de conservation après résiliation |
| Massive Developer ou Advanced, un mois | 79 ou 199 $ | 4 à 5+ ans seulement | SPX non vérifié ; profondeur insuffisante pour 2008 et 2020 |
| Cboe DataShop, ^SPX seul | environ 2 200 $ (3 385 $ avec grecques), 2012-2026 | chaîne officielle la plus propre | prix réel dans le panier DataShop |
| Databento, usage | environ 6 123 $ (tiers) | quotes OPRA brutes, pas d'IV | idem, calcul des IV à faire soi-même |
| Cboe DataShop, archive tout marché | 7 200 $ | tout le marché 2012-2026 | surdimensionné pour SPX |
| OptionMetrics (WRDS) | non publié, accès universitaire | 1996 -> aujourd'hui, référence académique | accès personnel : sans doute inaccessible |

**Sans achat** : la phase 1 se fait entièrement ; la prime et sa tenue sont mesurées sur 1986 ou 2007 -> 2026 avec des **prix de transaction réels** (VWAP), mais sans bid/ask : ni spread, ni commission, ni slippage observés. **Avec 80 à 200 $ (un mois de ThetaData ou d'ORATS)** on obtiendrait la phase 2 sur 2012 (ThetaData) ou 2007 (ORATS) -> 2026 : tout ceci reste à vérifier avant l'achat, et l'achat est une décision de l'utilisateur.

## 8. Conclusion

- **Phase 1 (indices Cboe, rendements mensuels) : faisable gratuitement**, données déjà téléchargées (PUT quotidien depuis 2007, PUTY et CNDR depuis 1986, WPUT depuis 2006), facteurs French jusqu'en 2026-08.
- **Phase 2 (chaînes réelles avec bid/ask) : exige un achat** (plus petit coût plausible : 80 à 200 $ pour un mois, non vérifié ; sûr mais plus cher : 2 200 $ chez DataShop). Les offres gratuites vérifiées couvrent 2 ans au plus, et SPX n'y est pas confirmé.
- Hors échantillon gratuit : RUT (PUTR), TLT (PTLT), NDX (BXN, covered call). EEM et or : **non disponibles gratuitement**.
- Points NON VÉRIFIÉS : conditions d'accès automatisé du site Cboe (texte intégral), lancement et part reconstruite de PUTY et CNDR, chemins des futures VIX 2004-2013, tout accès gratuit aux MSCI EM PutWrite, présence de SPX et SPXW dans les offres ThetaData, Massive, Alpha Vantage, profondeur réelle par plan de Databento, prix de DataShop dans le panier, prix d'OptionMetrics, série de prix RUT.
