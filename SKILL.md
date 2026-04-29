---
name: digital-oracle
version: 1.0.3
description: "Answer prediction questions using market trading data, not opinions. Use when the user asks probability questions about geopolitics, economics, markets, industries, or any topic where real money is being traded on the outcome. Examples: 'What's the probability of WW3?', 'Will there be a recession?', 'Is AI in a bubble?', 'When will the Russia-Ukraine war end?', 'Is it a good time to buy gold?', 'Will SPY drop 5% this month?', 'Is NVDA options premium overpriced?'. The skill reads prices from prediction markets, commodities, equities, options chains, derivatives, yield curves, and currencies, then cross-validates multiple signals to produce a structured probability report."
metadata: { "openclaw": { "emoji": "📈", "requires": { "bins": ["uv"] } } }
---

# digital-oracle

> Markets are efficient. Price contains all public information. Reading price = reading market consensus.

## Methodology

**Answer questions using only market trading data — no news, opinions, or statistical reports as causal evidence.** If something is true, some market has already priced it in.

Five iron rules:

1. **Trading data only** — prices, volume, open interest, spreads, premiums. Never cite analyst opinions.
2. **Explicit reasoning from price to judgment** — explain clearly "why this price answers this question."
3. **Multi-signal cross-validation** — never conclude from a single signal. At least 3 independent dimensions.
4. **Label the time horizon of each signal** — options price 3 months, equipment orders price 3 years — don't mix them in the same vote.
5. **Structured output** — the final report must follow the Step 5 template: layered signal tables → contradiction analysis → probability scenarios → signal consistency assessment. Do not substitute prose for structured reporting.

## Workflow

### Step 1: Understand the question

Decompose the user's question into:
- **Core variable**: What event or trend?
- **Time window**: Is the user asking about 3 months, 1 year, or 5 years?
- **Priceability**: Is there real money being traded on this outcome?

### Step 2: Select signals

Based on question type, select from the signal menu below. **Don't use just one category — cover at least 3.**

#### Geopolitical conflict / War risk
- Polymarket: Search for related event contracts (ceasefire, invasion, regime change, declaration of war)
- Kalshi: Search for related binary contracts
- Safe-haven assets: Gold (GC=F), silver (SI=F), Swiss franc (USDCHF=X)
- Conflict proxies: Crude oil (CL=F), natural gas (NG=F), wheat (ZW=F), defense ETF (ITA), defense stocks
- Risk ratios: Copper/Gold ratio (risk-off indicator), Gold/Silver ratio
- CFTC COT: Institutional positioning changes in crude/gold/wheat (which direction is smart money betting)
- BIS: Central bank policy rate trends in relevant countries
- FearGreedProvider: CNN Fear & Greed Index (composite of 7 price signals)
- Web search: VIX, MOVE index, sovereign CDS, war risk premiums, BDI freight rates, high-yield OAS
- Currencies: Currency pairs of relevant countries (e.g. USDRUB=X, USDCNY=X)
- Country ETFs: Asset flows in relevant countries (e.g. FXI, EWY)

#### Economic recession / Macro cycle
- Treasury: Yield curve shape (10Y-2Y spread, 10Y-3M spread), real rates, breakeven inflation
- YahooPriceProvider: SPY, copper (HG=F), crude oil (CL=F), price trends
- Risk ratios: Copper/Gold ratio
- CFTC COT: Speculative net positions in copper/crude (is managed money bullish or bearish)
- BIS: Credit-to-GDP gap (credit overheating = late cycle), policy rate directions
- World Bank: GDP growth rate historical trends, cross-country comparisons
- Deribit: BTC futures basis (risk appetite proxy)
- CoinGecko: Crypto total market cap + BTC dominance (risk appetite proxy)
- FearGreedProvider: CNN Fear & Greed Index (7 price signals composite → 0-100)
- CMEFedWatchProvider: Market-implied FOMC rate change probabilities from futures
- Polymarket: Recession-related contracts, central bank rate path
- Currencies: DXY/dollar strength, emerging market currencies
- Web search: High-yield bond spread (HY OAS), TED spread, MOVE index, TTF gas, BDI freight rates

#### Industry cycle / Bubble assessment
- YahooPriceProvider: Industry leader stock trends, sector ETFs
- Find the industry's "single-purpose commodity" (e.g. GPU rental price → AI, rebar → construction)
- Upstream equipment maker orders/stock price (e.g. ASML → semiconductors)
- Leader company valuation discount (e.g. TSMC vs peers → Taiwan Strait risk pricing)
- EDGAR: Industry leader insider trading cadence (Form 4) — concentrated selling = bearish signal
- CFTC COT: Institutional positioning changes in related commodities
- CoinGecko: For crypto industry, look at BTC/ETH/altcoin market cap distribution
- Web search: VC funding concentration, leveraged ETF concentration, margin debt levels
- Deribit: Implied volatility of related crypto assets

#### Asset pricing / Whether to buy
- YahooPriceProvider: Target asset price trend (daily/weekly/monthly)
- Relative price changes of correlated assets (divergence between two commodities = structural signal)
- Treasury: Risk-free rate as valuation anchor
- YFinance: Options chain (IV, put/call ratio, max pain, Greeks, implied move)
- EDGAR: Insider selling cadence (heavy Form 4 selling = insiders bearish)
- CFTC COT: Speculative vs commercial net position divergence for commodity assets
- CoinGecko: For crypto assets, check market cap, ATH/ATL distance, 24h volatility
- Deribit: Crypto options chain (implied volatility = market's expected range)
- Polymarket/Kalshi: Probability pricing of related events
- FearGreedProvider: CNN Fear & Greed composite score (momentum, breadth, VIX, put/call, junk bond demand, volatility, safe haven)
- Web search: VIX, corporate bond issuance volume, analyst rating distribution

#### China A-share allocation
- AStockProvider: all A-share stock history, index history, sector snapshots/history, market breadth, sector breadth, turnover, northbound flow
- Core indices: 上证指数 (`sh000001`), 沪深300 (`sh000300`), 上证50 (`sh000016`), 中证500 (`sh000905`)
- Sector rotation: 银行, 证券, 保险, 白酒, 煤炭行业, 电力行业, 公用事业, 军工, 半导体, 医药, 有色金属
- A-share leaders: 600519, 601318, 600036, 601398, 600900, 600030, 600276, 600150, 300750, 300760, 688981, 688111
- RMB and offshore risk: USDCNY, USDCHF, DXY web search, China ETFs (FXI/KWEB as external proxies only)
- Global macro validation: US Treasury yield curve, copper/gold ratio, crude oil, gold, CFTC COT for copper/gold/crude
- Risk appetite validation: SPY/QQQ trend, VIX/FearGreed, BTC/ETH market cap and Deribit BTC futures basis
- AStockMoneyFlowProvider: industry/concept/individual stock fund flow — main net inflow direction, consecutive flow days, super-large/large/medium/small order breakdowns
- AStockConstituentProvider: sector/concept/index constituent lists — ranked by change/amount/cap, with aggregate breadth stats (up/down/limit-up/limit-down counts)
- Northbound flow: use as foreign institutional allocation signal; sustained net inflow supports large-cap A-share risk appetite

#### Stock/Options analysis / Crash probability
- YFinance: Options chain → ATM IV (expected volatility), IV skew (upside/downside fear asymmetry), put/call ratio (bull/bear sentiment), max pain (market maker profit zone), implied move (expected price range), Greeks (delta ≈ ITM probability)
- YahooPriceProvider: Underlying historical price → realized volatility (compare vs implied volatility to judge options premium)
- Kalshi: SPY/NASDAQ price range markets → direct probability pricing
- CFTC COT: S&P 500/VIX futures positioning → institutional direction
- Defensive rotation: XLY (cyclical) vs XLP (defensive) vs XLU (utilities) relative performance → market defensiveness
- Treasury: Yield curve shape → recession signal
- FearGreedProvider: CNN Fear & Greed Index
- Web search: VIX level, margin debt level, leveraged ETF concentration

**Available trading symbols directory:** See [references/symbols.md](references/symbols.md)
**Provider API reference:** See [references/providers.md](references/providers.md)

### Step 3: Signal routing

Before fetching data, evaluate each candidate signal from Step 2 against three criteria:

1. **Relevance**: Can this signal actually answer the user's specific question? (e.g., asking about Taiwan → skip CoinGecko)
2. **Time match**: Does the signal's pricing horizon match the question's time window? (e.g., asking about 3 months → skip World Bank GDP which lags 1-2 years)
3. **Information increment**: Does this signal provide an independent perspective not already covered by other signals? Avoid redundancy, keep complementary signals.

Only keep signals that pass all three checks. This reduces noise, saves fetch time, and produces cleaner analysis.

### Step 4: Fetch data

Use digital-oracle's Python providers to fetch structured data, calling all sources in parallel with `gather()` (including web search):

```python
from digital_oracle import (
    PolymarketProvider, PolymarketEventQuery,
    KalshiProvider, KalshiMarketQuery,
    YahooPriceProvider, PriceHistoryQuery,   # requires uv pip install yfinance
    DeribitProvider, DeribitFuturesCurveQuery,
    USTreasuryProvider, YieldCurveQuery,
    WebSearchProvider,
    CftcCotProvider, CftcCotQuery,
    CoinGeckoProvider, CoinGeckoPriceQuery,
    EdgarProvider, EdgarInsiderQuery,
    BisProvider, BisRateQuery,
    WorldBankProvider, WorldBankQuery,
    YFinanceProvider, OptionsChainQuery,      # requires uv pip install yfinance
    AStockProvider, AStockHistoryQuery, AStockIndexQuery,
    AStockBreadthQuery, AStockSectorBreadthQuery,
    AStockSectorHistoryQuery, AStockNorthboundQuery,  # requires uv pip install akshare; baostock recommended
    AStockMoneyFlowProvider, MoneyFlowQuery,           # requires uv pip install akshare
    AStockConstituentProvider, ConstituentQuery,       # requires uv pip install akshare
    FearGreedProvider,
    CMEFedWatchProvider,
    gather,
)

pm = PolymarketProvider()
kalshi = KalshiProvider()
yahoo = YahooPriceProvider()  # requires uv pip install yfinance
deribit = DeribitProvider()
treasury = USTreasuryProvider()
web = WebSearchProvider()
cftc = CftcCotProvider()
coingecko = CoinGeckoProvider()
edgar = EdgarProvider(user_email="you@example.com")  # SEC requires email in User-Agent, otherwise 403
bis = BisProvider()
wb = WorldBankProvider()
yf = YFinanceProvider()  # requires uv pip install yfinance
astock = AStockProvider()  # requires uv pip install akshare; baostock recommended for stock-history fallback
moneyflow = AStockMoneyFlowProvider()  # requires uv pip install akshare
constituent = AStockConstituentProvider()  # requires uv pip install akshare
fear_greed = FearGreedProvider()
fedwatch = CMEFedWatchProvider()

result = gather({
    "pm_events": lambda: pm.list_events(PolymarketEventQuery(slug_contains="...", limit=10)),
    "yield_curve": lambda: treasury.latest_yield_curve(),
    "gold": lambda: yahoo.get_history(PriceHistoryQuery(symbol="GC=F", limit=30)),
    # Institutional positioning
    "gold_cot": lambda: cftc.list_reports(CftcCotQuery(commodity_name="GOLD", limit=4)),
    # Crypto market sentiment
    "crypto": lambda: coingecko.get_prices(CoinGeckoPriceQuery(coin_ids=("bitcoin", "ethereum"))),
    # Insider trades
    "insider": lambda: edgar.get_insider_transactions(EdgarInsiderQuery(ticker="AAPL", limit=10)),
    # Central bank policy rates
    "rates": lambda: bis.get_policy_rates(BisRateQuery(countries=("US", "CN"), start_year=2023)),
    # GDP data
    "gdp": lambda: wb.get_indicator(WorldBankQuery(indicator="NY.GDP.MKTP.CD", countries=("US", "CN"))),
    # BTC futures term structure (risk appetite proxy)
    "btc_futures": lambda: deribit.get_futures_term_structure(DeribitFuturesCurveQuery(currency="BTC")),
    # Kalshi event markets (use event_ticker or series_ticker, not keyword search)
    "kalshi_fed": lambda: kalshi.list_markets(KalshiMarketQuery(series_ticker="KXFED", limit=10)),
    # Options chain (with Greeks)
    "spy_options": lambda: yf.get_chain(OptionsChainQuery(ticker="SPY", expiration="2026-04-17")),
    # CNN Fear & Greed (composite of 7 price signals)
    "fear_greed": lambda: fear_greed.get_index(),
    # CME FedWatch (implied rate probabilities from futures)
    "fedwatch": lambda: fedwatch.get_probabilities(),
    # China A-share signals
    "a_shanghai": lambda: astock.get_index_history(AStockIndexQuery(symbol="sh000001", limit=60)),
    "a_breadth": lambda: astock.get_market_breadth(AStockBreadthQuery()),
    "a_banks": lambda: astock.get_sector_history(AStockSectorHistoryQuery(symbol="银行", limit=60)),
    "a_banks_breadth": lambda: astock.get_sector_breadth(AStockSectorBreadthQuery(symbol="银行")),
    "northbound": lambda: astock.get_northbound_flow(AStockNorthboundQuery(limit=30)),
    # Fund flow — where money is actually going
    "flow_600519": lambda: moneyflow.get_moneyflow(MoneyFlowQuery(symbol="600519", scope="individual", lookback_days=5)),
    "flow_semi": lambda: moneyflow.get_moneyflow(MoneyFlowQuery(symbol="半导体", scope="industry", lookback_days=5)),
    "flow_rank": lambda: moneyflow.list_top_flows(scope="industry", top_n=10),
    # Constituent analysis — who's driving the sector
    "semi_constituents": lambda: constituent.get_constituents(
        ConstituentQuery(symbol="半导体", scope="industry", sort_by="change_pct")
    ),
    "hs300_cons": lambda: constituent.get_constituents(ConstituentQuery(symbol="000300", scope="index")),
    # Web search runs in parallel with structured providers
    "vix": lambda: web.search("VIX index current level"),
    "hy_spread": lambda: web.search("US high yield bond spread OAS"),
})

# Partial failures don't affect other results
curve = result.get("yield_curve")
vix_info = result.get_or("vix", None)  # WebSearchResult — use .text() to render

# Options data usage
chain = result.get_or("spy_options", None)
if chain:
    print(f"ATM IV: {chain.atm_iv:.1%}, Implied move: {chain.implied_move():.1%}")
    print(f"Put/Call OI ratio: {chain.put_call_oi_ratio:.2f}")
    print(f"Max pain: {chain.max_pain()}")
```

**All 15 Providers:**

| Provider | Data Type | Purpose | Dependency |
|----------|-----------|---------|------------|
| PolymarketProvider | Prediction market contracts | Event probability pricing | stdlib |
| KalshiProvider | Binary contracts | US regulated event contracts | stdlib |
| YahooPriceProvider | Price history | Stocks/ETFs/FX/Commodities | yfinance |
| DeribitProvider | Crypto derivatives | Futures term structure, options IV | stdlib |
| USTreasuryProvider | Treasury yields | Yield curves, inflation expectations | stdlib |
| WebSearchProvider | Web search | VIX/MOVE/CDS/BDI supplementary data | stdlib |
| CftcCotProvider | Futures positioning | Institutional direction (smart money) | stdlib |
| CoinGeckoProvider | Crypto spot | BTC/ETH price, market cap, dominance | stdlib |
| EdgarProvider | SEC filings | Insider trades Form 4, filing search | stdlib |
| BisProvider | Central bank data | Policy rates, credit-to-GDP gap | stdlib |
| WorldBankProvider | Development indicators | GDP, population, trade, macro data | stdlib |
| YFinanceProvider | US options chains | IV, Greeks, put/call ratio, max pain | yfinance |
| AStockProvider | China A-share market | Indices, all A-share stocks, sectors, market/sector breadth, turnover, northbound flow | akshare; baostock recommended |
| AStockMoneyFlowProvider | A-share fund flow | Industry/concept/individual main inflow, order-size breakdown, consecutive flow days | akshare |
| AStockConstituentProvider | A-share constituents | Sector/concept/index member lists ranked by price change/amount/cap, with breadth stats | akshare |
| **FearGreedProvider** | **Market sentiment** | **CNN 7-signal composite → 0-100 score** | **stdlib** |
| **CMEFedWatchProvider** | **Rate probabilities** | **FOMC rate change implied from futures** | **stdlib** |

> 12 out of 17 providers have zero external dependencies and zero API keys. YahooPriceProvider and YFinanceProvider require `pip install yfinance`. AStockProvider, AStockMoneyFlowProvider, and AStockConstituentProvider require `pip install akshare`; install `baostock` to enable domestic stock-history fallback for AStockProvider.

**WebSearchProvider usage:**
- `web.search("query")` → returns `WebSearchResult` (search summary) — render with `.text()`
- `web.fetch_page("url")` → returns `WebPageContent` (page body extraction)
- Search engine is DuckDuckGo, zero API keys needed

**Data not available via structured providers — use web search instead:** VIX, MOVE, CDS spreads, TTF natural gas, BDI freight rates, war risk premiums, high-yield OAS — these need to be fetched from financial web pages. They are still trading data and comply with the methodology.

### Step 5: Data analysis

This is the key to report quality. Don't just summarize data — derive judgment from data.

Four analysis dimensions:

1. **Signal interpretation**: What is each data point saying? Derive meaning from price. Not "gold up 3%" but "the market is pricing in tail risk." e.g., Copper/Gold ratio declining → industrial demand weaker than safe-haven demand → risk-off.

2. **Cross-validation**: Which signals point in the same direction (resonance)? Which signals disagree (divergence)? Divergence itself is a high-value signal. e.g., gold says "disaster" but equities say "fine" → two markets pricing different time windows.

3. **Time alignment**: Group signals by their pricing horizon. Don't mix signals from different time windows in the same vote.
   - Short-term (3-12mo): Prediction market contracts, VIX/MOVE, price reaction patterns, executive selling
   - Medium-term (1-3yr): Leader revenue consensus, CapEx plans, VC concentration, leverage concentration
   - Long-term (3-10yr): Equipment maker orders, irreversible capital allocation, ultra-long infrastructure investment
   - Short-term bearish + long-term bullish ≠ contradiction, = S-curve inflection

4. **Weight judgment**: Not all signals are equally reliable. Signals backed by real money > surveys. Liquid markets > illiquid markets. Direct pricing > indirect proxies. e.g., Polymarket high-liquidity contract > CDS quotes (slow updates, low liquidity).

**Core principle: Don't vote by majority.** When signals diverge:
- Check the time dimension first — different signals price different future windows
- Look for "two things happening at once" — old economy Japanification + new economy boom can coexist
- Consider "direction right but timing wrong" — long-term bullish but short-term overheated → wait for a pullback

### Step 6: Output report

**Must follow this structure.** You can adjust the number of layers and wording, but the four main sections (data summary, analysis, probability estimates, conclusion) cannot be omitted or merged into prose paragraphs:

```markdown
# [Question Title]: Multi-Signal Synthesis

## Data Summary

### Layer 1: [Most direct signal source]
| Signal | Data | What it's saying |
|--------|------|-----------------|
(table, one signal per row, third column is reasoning from price to meaning)

### Layer 2: [Secondary signal source]
(same format)

### Layer N: ...
(as needed, typically 3-5 layers)

## Analysis

### Resonance signals
(which signals point in the same direction, and what judgment they form)

### Key divergences
(A says X, B says Y → explain why + who is more credible)

### Time stratification
(what do short-term / medium-term / long-term signals each point to)

## Probability Estimates
| Scenario | Probability | Basis |
|----------|-------------|-------|

### Most likely path: [one-sentence summary]
**Core logic chain:** (2-3 paragraphs, reasoning from data to conclusion)

## Conclusion

> [One-sentence summary, preferably including a specific probability estimate]

### Sub-conclusions
| Dimension | Judgment | Confidence |
|-----------|----------|------------|
| Short-term (6-12mo) | ... | High/Medium/Low |
| Medium-term (1-3yr) | ... | High/Medium/Low |
| Long-term (3-5yr) | ... | High/Medium/Low |
| Systemic risk | ... | High/Medium/Low |
(adjust dimensions to match the question — e.g., replace "systemic risk" with whatever dimension is most relevant)

### Risk factors
- **Upside risk:** what scenario would make things better than expected
- **Downside risk:** what scenario would make things worse than expected

### Signals to monitor
| Signal | Current value | Threshold | Meaning |
|--------|--------------|-----------|---------|
| ... | ... | if crosses X | then Y |
(3-5 concrete signals with specific trigger levels and what they would imply)

---
*Data sources: [list all structured and web data sources]*
*Fetched at: [date]*
```

## Notes

- Polymarket `slug_contains` search is fuzzy — filter results by title keywords after fetching
- YahooPriceProvider uses Yahoo Finance symbols: futures use `=F` suffix (e.g. `GC=F`, `CL=F`, `HG=F`), forex uses `=X` suffix (e.g. `EURUSD=X`), US stocks/ETFs use plain tickers (e.g. `SPY`, `LMT`)
- YahooPriceProvider requires `yfinance` — install with `uv pip install --target .deps yfinance`
- European stocks available on Yahoo Finance with exchange suffix (e.g. `RHM.DE` for Rheinmetall, `BA.L` for BAE Systems)
- Prediction market contracts vary in liquidity — contracts with volume < $100K should be discounted
- Different signals update at different frequencies: prediction markets real-time, Yahoo Finance daily delayed, Treasury weekly
- CFTC COT updates Tuesday, published Friday. commodity_name uses uppercase ("GOLD", "CRUDE OIL", "S&P 500")
- CoinGecko free API has rate limits (~10-30 req/min) — don't pack too many CoinGecko calls in gather
- EDGAR requires `EdgarProvider(user_email="you@example.com")` — SEC requires email in User-Agent, otherwise 403. First call parses ticker→CIK mapping, slightly slow
- BIS data updates infrequently (monthly/quarterly) — suitable for long-term trends, not short-term trading
- World Bank GDP data typically lags 1-2 years — latest year may return `None`
- YFinance requires `uv pip install yfinance` (auto-installs pandas). After-hours IV may be inaccurate (bid/ask = 0) — use during market hours
- AStockProvider requires `uv pip install akshare`; install `uv pip install baostock` to enable domestic A-share stock-history fallback before Yahoo. It covers China A-share stock history, index history, sector snapshots/history, market breadth, sector breadth, turnover, and northbound flow. By default it includes all A-share boards; pass `mainboard_only=True` only when the user explicitly wants mainboard-only analysis
- For A-share investment analysis, always include market breadth before stock picking: `get_market_breadth(AStockBreadthQuery())` for all-A up/down/flat/limit-up/limit-down counts and total turnover, and `get_sector_breadth(AStockSectorBreadthQuery(symbol="..."))` for the target sector when available. Prefer `breadth.metadata["breadth_level"] == "stock"`; `source=stock_zh_a_spot_sina` is acceptable as a full-A stock-level fallback when Eastmoney full-market snapshots fail. If `breadth.metadata["breadth_level"] == "sector_proxy"`, state that breadth is sector-level fallback rather than stock-level breadth. Treat weak breadth with strong index gains as a narrowing-market warning
- AStockConstituentProvider requires `uv pip install akshare`. Provides `get_constituents(ConstituentQuery(symbol=..., scope="industry"/"concept"/"index", sort_by="change_pct"/"amount"/"market_cap", top_n=...))` returning a `ConstituentList` with ranked `StockConstituent` entries plus aggregate breadth stats (up/down/flat/limit-up/limit-down counts, total amount, average/median change, average market cap). For industry/concept scope, `symbol` is the Chinese name ("半导体"); for index scope, `symbol` is the index code ("000300"). Use this to check if a sector rally is broad-based or driven by a few heavyweights — if `average_change_pct > median_change_pct` by a wide margin, large-caps are pulling the index while small-caps lag
- AStockMoneyFlowProvider requires `uv pip install akshare`. Provides `get_moneyflow(MoneyFlowQuery(symbol=..., scope=..., lookback_days=5))` for individual/industry/concept history with consecutive inflow/outflow day tracking, and `list_top_flows(scope="industry"/"concept", top_n=20)` for ranking. For individual stocks, `symbol` is the stock code ("600519"); for industry/concept, use the Chinese name ("半导体"). Money flow data is same-day T+0 — it reflects the current session's capital movements. Always cross-check flow direction with price direction: rising price + net outflow = distribution warning; falling price + net inflow = accumulation signal
- AStockProvider's optional mainboard filter keeps `600/601/603/605` and `000/001/002/003`, and excludes ChiNext, STAR Market, and Beijing Stock Exchange codes
- For A-share data collection, prefer `scripts/demo_astock.py --network-profile china` or an equivalent direct domestic route. When a global proxy/VPN route is active, Eastmoney may fail and AStockProvider should fall back to BaoStock/Yahoo; treat `history.metadata["source"]` as part of the evidence quality note
- Before A-share analysis in a local agent environment, run `E:\Project\digital-oracle\.venv-eastmoney\Scripts\python.exe E:\Project\digital-oracle\scripts\audit_agent_sources.py --network-profile china --limit 5 --require-venv` and include its source audit output in the report. If `venv_ok=false` or any critical check fails, fix the execution environment before analysis
- For A-share-only investment questions, do not recommend US stocks, Hong Kong stocks, crypto, or non-A-share assets as purchasable assets unless the user explicitly permits them. Use them only as external risk and liquidity signals
- YFinance `get_chain()` auto-computes Black-Scholes Greeks (pure stdlib `math.erf`, no scipy needed)
- Absolute value of put delta ≈ probability of that strike being ITM at expiration (rough estimate)
- Put/Call ratio > 1.5 is typically bearish, but as a contrarian indicator, extreme values (> 3) may signal a bottom
- Max pain is the strike price maximizing market maker profit — actual expiration price often converges toward max pain
- Kalshi does NOT support keyword search — use `series_ticker` or `event_ticker` to filter markets. Find tickers by browsing [kalshi.com](https://kalshi.com) or listing markets without filters first. Common series: `KXFED` (Fed rates), `KXINX` (S&P 500 range), `KXGDP` (GDP)
- Deribit futures method is `get_futures_term_structure()`, not `get_futures_curve()`. Option chain method is `get_option_chain()`
- FearGreedProvider has no API key requirement. Returns a single composite score (0-100) synthesizing 7 market price signals: stock momentum, breadth, VIX, put/call ratio, junk bond demand, volatility, safe haven demand. Score < 25 = Extreme Fear, > 75 = Extreme Greed
- CMEFedWatchProvider has no API key requirement. Returns implied rate change probabilities for upcoming FOMC meetings, derived from 30-day Fed Funds futures prices. Note: the CME endpoint may occasionally be unavailable or change format — if it fails, fall back to Kalshi `KXFED` series for rate probabilities
- When reporting dollar amounts, use `USD` instead of `$` to avoid markdown renderers interpreting `$...$` as LaTeX
