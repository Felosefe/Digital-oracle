# Provider API 速查

所有 provider 零 API key。YahooPriceProvider 和 YFinanceProvider 需要 `pip install yfinance`；AStockProvider 需要 `pip install akshare`，个股历史国内兜底建议安装 `pip install baostock`。

```python
from digital_oracle import (
    PolymarketProvider, PolymarketEventQuery,
    KalshiProvider, KalshiMarketQuery,
    YahooPriceProvider, PriceHistoryQuery,   # pip install yfinance
    DeribitProvider, DeribitFuturesCurveQuery, DeribitOptionChainQuery,
    USTreasuryProvider, YieldCurveQuery, ExchangeRateQuery,
    WebSearchProvider,
    CftcCotProvider, CftcCotQuery,
    CoinGeckoProvider, CoinGeckoPriceQuery, CoinGeckoMarketQuery,
    EdgarProvider, EdgarInsiderQuery, EdgarSearchQuery,
    BisProvider, BisRateQuery, BisCreditGapQuery,
    WorldBankProvider, WorldBankQuery,
    YFinanceProvider, OptionsChainQuery,      # pip install yfinance
    AStockProvider, AStockHistoryQuery, AStockBreadthQuery, AStockSectorBreadthQuery,  # pip install akshare baostock
    AStockMoneyFlowProvider, MoneyFlowQuery,  # pip install akshare
    AStockConstituentProvider, ConstituentQuery,  # pip install akshare
    AStockMarginProvider, MarginQuery,  # pip install akshare
    AStockEtfProvider, EtfQuery, EtfHistoryQuery,  # pip install akshare
    AStockValuationProvider, ValuationQuery, FinancialQuery,  # pip install akshare
    AStockDisclosureProvider, DisclosureQuery,  # pip install akshare
    FearGreedProvider,
    CMEFedWatchProvider,
)
```

## AStockProvider

A 股市场数据。第一版覆盖全 A 股个股日线、指数日线、行业板块快照、行业板块日线、市场广度、成交额汇总、北向资金历史。**需要 `pip install akshare`；建议同时安装 `pip install baostock` 作为个股历史兜底。**

```python
from digital_oracle import (
    AStockProvider,
    AStockHistoryQuery,
    AStockBreadthQuery,
    AStockSectorBreadthQuery,
    AStockIndexQuery,
    AStockSectorHistoryQuery,
    AStockNorthboundQuery,
)

a = AStockProvider()

# 个股历史行情（默认覆盖全 A 股）
history = a.get_history(AStockHistoryQuery(symbol="600519", limit=60))
# 返回 PriceHistory；history.bars -> tuple[PriceBar, ...]
# history.metadata["source"] 会显示 eastmoney_curl_cffi / eastmoney_urllib / baostock / yahoo_finance

# 如需只允许主板代码，可显式传 mainboard_only=True
mainboard = a.get_history(AStockHistoryQuery(symbol="600519", limit=60, mainboard_only=True))

# 指数历史行情
sh = a.get_index_history(AStockIndexQuery(symbol="sh000001", limit=60))
hs300 = a.get_index_history(AStockIndexQuery(symbol="sh000300", limit=60))

# 全 A 股实时快照
stocks = a.list_stock_snapshots()
# 返回 list[AStockSnapshot]
# snapshot.code, snapshot.name, snapshot.latest, snapshot.change_pct
# snapshot.amount, snapshot.turnover_rate, snapshot.pe_dynamic, snapshot.pb

# 全市场广度 + 成交额
breadth = a.get_market_breadth(AStockBreadthQuery())
# breadth.total_count, breadth.up_count, breadth.down_count, breadth.flat_count
# breadth.limit_up_count, breadth.limit_down_count, breadth.total_amount
# breadth.metadata["breadth_level"] 为 stock 时是全 A 个股级广度；为 sector_proxy 时是行业代理广度

# 行业板块
sectors = a.list_sector_snapshots()
banks = a.get_sector_history(AStockSectorHistoryQuery(symbol="银行", limit=60))
semis_breadth = a.get_sector_breadth(AStockSectorBreadthQuery(symbol="半导体"))

# 北向资金
northbound = a.get_northbound_flow(AStockNorthboundQuery(limit=30))
# flow.date, flow.net_buy_amount, flow.cumulative_net_buy_amount, flow.hs300_change_pct
```

**可选主板过滤规则：**
- 保留沪市主板：`600`, `601`, `603`, `605`
- 保留深市主板：`000`, `001`, `002`, `003`
- 排除创业板 `300/301`、科创板 `688/689`、北交所 `4/8/9`

**A 股分析建议：** 默认覆盖全 A 股，包括主板、创业板、科创板、北交所；用 AStockProvider 作为本土资产层，用 StooqProvider 的黄金、铜、原油、美元和 USTreasuryProvider 的美元利率作为外围宏观验证。

**网络档位建议：**

```powershell
# A 股优先，清理代理环境，尽量走 Eastmoney direct；失败后落到 BaoStock
python scripts\demo_astock.py --network-profile china --view stock --symbol 600519 --limit 5
python scripts\demo_astock.py --network-profile china --view breadth
python scripts\demo_astock.py --network-profile china --view sector-breadth --symbol 半导体

# 开着代理做全局/海外数据联动时可用；A 股可能落到 BaoStock
python scripts\demo_astock.py --network-profile global --view stock --symbol 600519 --limit 5
```

`source=eastmoney_curl_cffi` / `source=eastmoney_urllib` 表示 Eastmoney direct 成功；`source=stock_zh_a_spot_sina` 表示全 A 快照走新浪兜底；`source=baostock` 表示国内个股历史兜底成功；`source=yahoo_finance` 表示最后才走 Yahoo。

Agent 正式分析前建议先跑 source 审计：

```powershell
E:\Project\digital-oracle\.venv-eastmoney\Scripts\python.exe E:\Project\digital-oracle\scripts\audit_agent_sources.py --network-profile china --limit 5 --require-venv
```

审计输出里的 `venv_ok`、`python`、`source` 是判断 agent 是否用对环境和数据源的依据。

## PolymarketProvider

预测市场。搜索事件合约，获取概率定价和 orderbook。

```python
p = PolymarketProvider()

# 搜索事件（slug_contains 很模糊，搜到后要按标题关键词二次过滤）
events = p.list_events(PolymarketEventQuery(
    slug_contains="russia",    # 模糊搜索
    limit=20,                  # 返回条数
    active=True,               # 仅活跃事件
    closed=False,              # 排除已关闭
))
# 返回 list[PolymarketEvent]
# event.title, event.slug, event.volume, event.markets
# market.question, market.yes_probability, market.outcomes

# 按 slug 精确获取单个事件
event = p.get_event("russia-x-ukraine-ceasefire-by-march-31-2026")
# 返回 PolymarketEvent | None

# 获取 orderbook（需要 token_id，从 market.outcomes[i].token_id 获取）
book = p.get_order_book(token_id="...")
# book.best_bid, book.best_ask, book.spread
```

## KalshiProvider

美国监管的事件合约市场。按 series/event ticker 组织。

```python
k = KalshiProvider()

# 列出市场（按 series_ticker 过滤）
markets = k.list_markets(KalshiMarketQuery(series_ticker="KXFED", limit=10))
# 返回 list[KalshiMarket]
# market.ticker, market.title, market.yes_probability, market.volume

# 单个市场详情
market = k.get_market("KXFED-27APR-T4.25")

# 事件（包含多个阶梯式市场）
event = k.get_event("KXFED-27APR")
# event.markets -> 该事件下所有市场

# Orderbook
book = k.get_order_book("KXFED-27APR-T4.25", depth=10)
# book.best_yes_ask, book.best_no_ask
```

## YahooPriceProvider

全球价格历史。股票、ETF、外汇、商品、指数。**需要 `pip install yfinance`。**

```python
yahoo = YahooPriceProvider()

hist = yahoo.get_history(PriceHistoryQuery(
    symbol="GC=F",       # 见 symbols.md
    interval="m",        # d=日线 w=周线 m=月线
    limit=12,            # 最近 N 根 bar
))
# 返回 PriceHistory
# hist.bars -> list[PriceBar]
# bar.date, bar.open, bar.high, bar.low, bar.close, bar.volume
# hist.latest -> 最新 bar
# hist.earliest -> 最早 bar
```

**符号命名规则（Yahoo Finance）：**
- 美股/ETF: `SPY`, `LMT`, `CCJ`, `ITA`
- 外汇: `EURUSD=X`, `USDJPY=X`, `USDCHF=X`
- 商品期货: `HG=F`, `NG=F`, `ZW=F`, `CL=F`, `BZ=F`
- 贵金属: `GC=F`（黄金）, `SI=F`（白银）
- 欧洲股票: `RHM.DE`, `BA.L`

## DeribitProvider

加密衍生品。期货 term structure、期权链、orderbook。

```python
d = DeribitProvider()

# 期货 term structure（contango/backwardation = 市场情绪）
ts = d.get_futures_term_structure(DeribitFuturesCurveQuery(currency="BTC"))
# ts.points -> list[DeribitFutureTermPoint]
# point.instrument_name, point.mark_price, point.basis_vs_perpetual, point.annualized_basis_vs_perpetual
# ts.perpetual() -> 永续合约数据

# 期权链（隐含波动率 = 市场预期波动范围）
chain = d.get_option_chain(DeribitOptionChainQuery(
    currency="BTC",
    expiration_label="27MAR26",  # 可选，不填取最近到期
))
# chain.strikes, chain.underlying_price, chain.atm_strike()

# Orderbook
book = d.get_order_book("BTC-PERPETUAL", depth=5)
# book.best_bid, book.best_ask, book.spread, book.mark_price, book.index_price
```

## USTreasuryProvider

美国国债收益率曲线 + 财政部汇率数据。

```python
t = USTreasuryProvider()

# 收益率曲线
snapshots = t.list_yield_curve(YieldCurveQuery(
    year=2026,
    curve_kind="nominal",   # nominal | real | bill | long_term
))
# 返回 list[YieldCurveSnapshot]，按日期排列
# snap.date, snap.points -> list[YieldPoint]
# point.tenor ("1M", "3M", "2Y", "10Y", "30Y"), point.value (百分比)

# 快捷方法
snap = t.latest_yield_curve(YieldCurveQuery(year=2026, curve_kind="nominal"))
y10 = snap.yield_for("10Y")  # -> float | None
spread = snap.spread("10Y", "2Y")  # -> float | None (百分比差)

# 盈亏平衡通胀 = nominal - real
nominal = t.latest_yield_curve(YieldCurveQuery(year=2026, curve_kind="nominal"))
real = t.latest_yield_curve(YieldCurveQuery(year=2026, curve_kind="real"))
breakeven_10y = nominal.yield_for("10Y") - real.yield_for("10Y")

# 汇率
rates = t.list_exchange_rates(ExchangeRateQuery(country=("China", "Japan")))
# 返回 list[ExchangeRateRecord]
# record.country, record.currency, record.exchange_rate
```

## WebSearchProvider

网页搜索 + 页面抓取。DuckDuckGo 搜索，零 API key。

```python
web = WebSearchProvider()

# 搜索（返回摘要列表）
result = web.search("VIX index current level")
# 返回 WebSearchResult
# result.snippets -> tuple[WebSearchSnippet, ...]
# snippet.title, snippet.url, snippet.snippet
# result.text() -> 渲染为可读文本块

# 也可传 WebSearchQuery 控制结果数
from digital_oracle import WebSearchQuery
result = web.search(WebSearchQuery(query="US high yield OAS spread", max_results=3))

# 抓取页面正文
page = web.fetch_page("https://example.com/article")
# 返回 WebPageContent
# page.title, page.text, page.truncated
# 默认截断 8000 字符，可通过 WebPageQuery(url=..., max_chars=16000) 调整
```

## CftcCotProvider

CFTC 持仓报告。机构期货仓位（smart money 方向）。

```python
cftc = CftcCotProvider()

# 拉取最近 COT 报告
reports = cftc.list_reports(CftcCotQuery(commodity_name="GOLD", limit=4))
# 返回 list[CftcCotReport]
# report.report_date, report.commodity, report.market_name
# report.mm_long, report.mm_short, report.mm_spread  (Managed Money)
# report.prod_long, report.prod_short                 (Producer/Merchant)
# report.swap_long, report.swap_short, report.swap_spread (Swap Dealer)
# report.open_interest
# report.mm_net  -> mm_long - mm_short (净投机仓位)
# report.prod_net -> prod_long - prod_short (净商业仓位)

# 不传 commodity_name 则返回所有商品的最新报告
reports = cftc.list_reports(CftcCotQuery(limit=20))
```

**常用 commodity_name：** `"GOLD"`, `"CRUDE OIL"`, `"NATURAL GAS"`, `"COPPER"`, `"S&P 500"`, `"WHEAT"`, `"CORN"`, `"SOYBEANS"`, `"EURO FX"`, `"JAPANESE YEN"`

## CoinGeckoProvider

加密货币现货数据。价格、市值、BTC dominance。

```python
cg = CoinGeckoProvider()

# 获取价格
prices = cg.get_prices(CoinGeckoPriceQuery(
    coin_ids=("bitcoin", "ethereum", "solana"),
    include_market_cap=True,
    include_24h_vol=True,
))
# 返回 list[CoinGeckoPrice]
# price.coin_id, price.price_usd, price.market_cap_usd
# price.volume_24h_usd, price.price_change_24h_pct

# 全球市场概览
g = cg.get_global()
# g.total_market_cap_usd, g.btc_dominance_pct, g.eth_dominance_pct
# g.market_cap_change_24h_pct, g.active_cryptocurrencies

# 市值排名列表
markets = cg.list_markets(CoinGeckoMarketQuery(per_page=10, page=1))
# 返回 list[CoinGeckoMarket]
# m.coin_id, m.symbol, m.name, m.current_price, m.market_cap
# m.market_cap_rank, m.total_volume, m.ath, m.atl
```

## EdgarProvider

SEC EDGAR 公告检索 + 内部人交易（Form 4）。

```python
edgar = EdgarProvider()

# 内部人交易（Form 4 减持/增持）
summary = edgar.get_insider_transactions(EdgarInsiderQuery(ticker="NVDA", limit=20))
# 返回 EdgarInsiderSummary
# summary.ticker, summary.company_name, summary.cik
# summary.total_form4_count
# summary.recent_form4s -> tuple[EdgarFiling, ...]
# filing.filing_date, filing.report_date, filing.accession_number

# 全文检索 SEC 公告
hits = edgar.search_filings(EdgarSearchQuery(
    query="artificial intelligence risk",
    forms="10-K",            # 可选：限定表格类型
    date_start="2025-01-01", # 可选
    date_end="2026-03-01",   # 可选
    limit=10,
))
# 返回 list[EdgarSearchHit]
# hit.entity_name, hit.file_date, hit.form_type, hit.description
```

## BisProvider

国际清算银行。央行政策利率 + 信贷/GDP 缺口。

```python
bis = BisProvider()

# 央行政策利率
rates = bis.get_policy_rates(BisRateQuery(
    countries=("US", "CN", "JP", "GB", "EU"),
    start_year=2020,
))
# 返回 list[BisPolicyRate]
# rate.country ("US"), rate.period ("2026-01"), rate.rate (5.5)

# 信贷/GDP 缺口（信用泡沫指标）
gaps = bis.get_credit_to_gdp(BisCreditGapQuery(
    countries=("US", "CN"),
    start_year=2015,
))
# 返回 list[BisCreditGap]
# gap.country, gap.period ("2025-Q3"), gap.gap_pct
# gap_pct > 10 = 信用过热警告（BIS 阈值）
```

**国家代码：** `"US"`, `"CN"`, `"JP"`, `"GB"`, `"EU"`, `"DE"`, `"KR"`, `"BR"`, `"IN"`, `"AU"`

## WorldBankProvider

世界银行。GDP、人口、贸易等发展指标。

```python
wb = WorldBankProvider()

# 获取指标数据
result = wb.get_indicator(WorldBankQuery(
    indicator="NY.GDP.MKTP.CD",  # GDP (current US$)
    countries=("US", "CN", "JP"),
    date_range="2015:2025",
    per_page=500,
))
# 返回 WorldBankResult
# result.indicator_id, result.indicator_name
# result.points -> tuple[WorldBankDataPoint, ...]
# point.country_code, point.country_name, point.date, point.value
# 注意：最新年份 value 可能为 None（数据尚未发布）
```

**常用指标 ID：**
- `NY.GDP.MKTP.CD` — GDP (current US$)
- `NY.GDP.MKTP.KD.ZG` — GDP growth (annual %)
- `FP.CPI.TOTL.ZG` — Inflation, consumer prices (annual %)
- `NE.TRD.GNFS.ZS` — Trade (% of GDP)
- `BN.CAB.XOKA.CD` — Current account balance (BoP, current US$)
- `SP.POP.TOTL` — Population, total

## YFinanceProvider

US 股票期权链 + Black-Scholes Greeks。**需要 `pip install yfinance`。**

```python
yf = YFinanceProvider()

# 列出所有到期日
exps = yf.get_expirations("SPY")
# 返回 OptionsExpirations
# exps.ticker, exps.expirations -> tuple[str, ...]

# 获取期权链（自动计算 Greeks）
chain = yf.get_chain(OptionsChainQuery(
    ticker="SPY",
    expiration="2026-04-17",  # 不填则取最近到期日
    risk_free_rate=0.045,     # 无风险利率，默认 4.5%
    compute_greeks=True,      # 默认 True
))
# 返回 OptionsChain
# chain.ticker, chain.expiration, chain.underlying_price
# chain.calls -> tuple[OptionContract, ...]
# chain.puts  -> tuple[OptionContract, ...]

# OptionContract 字段：
# c.contract_symbol, c.option_type ("call"/"put"), c.expiration
# c.strike, c.last_price, c.bid, c.ask, c.mid
# c.volume, c.open_interest, c.implied_volatility, c.in_the_money
# c.greeks -> OptionGreeks | None
#   greeks.delta  (call: 0~1, put: -1~0; |delta| ≈ P(ITM))
#   greeks.gamma  (delta 对标的价格的敏感度)
#   greeks.theta  (每日时间衰减)
#   greeks.vega   (IV 每变 1% 的价格变化)

# 便捷属性
chain.atm_strike                # ATM 行权价
chain.atm_call                  # ATM call 合约
chain.atm_put                   # ATM put 合约
chain.atm_iv                    # ATM 隐含波动率
chain.implied_move()            # 市场隐含波动幅度（ATM straddle / 标的价）
chain.put_call_volume_ratio     # 看跌/看涨成交量比
chain.put_call_oi_ratio         # 看跌/看涨持仓量比
chain.total_volume              # 总成交量
chain.total_open_interest       # 总持仓量
chain.max_pain()                # 最大痛点行权价

# 独立使用 Black-Scholes Greeks
from digital_oracle import black_scholes_greeks
g = black_scholes_greeks(S=150, K=145, T=0.1, r=0.045, sigma=0.25, option_type="call")
# g.delta, g.gamma, g.theta, g.vega
```

**分析技巧：**
- `|put delta|` ≈ 该 strike 到期时 ITM 的概率（粗略但实用）
- `put_call_volume_ratio > 1.5` = 看空情绪；极端值 `> 3` 作为逆向指标反而看多
- `implied_move()` = 市场对到期前涨跌幅的共识预期
- `atm_iv` vs 历史实际波动率 → IV 溢价/折价判断（期权"贵不贵"）
- `max_pain` = 到期时价格常向此收敛（做市商利益最大化）
- IV skew：比较同 delta 的 OTM put IV vs OTM call IV → 市场对下跌的恐惧程度

## FearGreedProvider

CNN Fear & Greed Index。7 个价格信号的加权合成，不是观点聚合。

```python
fg = FearGreedProvider()

snap = fg.get_index()
# 返回 FearGreedSnapshot
# snap.score          # 0-100 (0=Extreme Fear, 100=Extreme Greed)
# snap.rating         # "Extreme Fear", "Fear", "Neutral", "Greed", "Extreme Greed"
# snap.timestamp      # ISO timestamp
# snap.previous_close # 前一交易日收盘值
# snap.one_week_ago   # 一周前
# snap.one_month_ago  # 一个月前
# snap.one_year_ago   # 一年前
```

**7 个组成信号：** 股票价格动量（S&P 500 vs 125日均线）、股票价格强度（52周新高/新低）、股票价格波幅（VIX）、Put/Call期权比率、垃圾债需求（高收益vs投资级利差）、市场波动率（VIX偏离度）、避险需求（股票vs债券收益率差）

## CMEFedWatchProvider

CME FedWatch 利率期货隐含概率。从 30 天联邦基金利率期货价格推算。

```python
fw = CMEFedWatchProvider()

meetings = fw.get_probabilities()
# 返回 list[FedMeetingProbability]
# m.meeting_date          # e.g. "2026-05-07"
# m.current_target_low    # e.g. 4.25
# m.current_target_high   # e.g. 4.50
# m.probabilities         # tuple[FedRateProb, ...]
#   p.target_low, p.target_high  # e.g. 4.00, 4.25
#   p.probability                # 0.0 to 1.0
```

**注意：** CME endpoint 可能偶尔不可用。如果失败，可用 Kalshi `KXFED` 系列作为备选获取利率概率。

## AStockMoneyFlowProvider

A 股行业/概念/个股资金流。主力净流入方向、连续天数、超大单/大单/中单/小单分拆。**需要 `pip install akshare`。**

```python
from digital_oracle import AStockMoneyFlowProvider, MoneyFlowQuery

mf = AStockMoneyFlowProvider()

# 个股资金流历史
snap = mf.get_moneyflow(MoneyFlowQuery(symbol="600519", scope="individual", lookback_days=5))
# 返回 MoneyFlowSnapshot
# snap.symbol                      # "600519"
# snap.latest_main_net             # 最新一日主力净流入
# snap.consecutive_inflow_days     # 连续净流入天数
# snap.consecutive_outflow_days    # 连续净流出天数
# snap.history                     # tuple[MoneyFlowDay, ...]
#   day.date                       # YYYY-MM-DD
#   day.close                      # 收盘价
#   day.change_pct                 # 涨跌幅
#   day.main_net_inflow            # 主力净流入
#   day.super_large_net            # 超大单净流入
#   day.large_net                  # 大单净流入
#   day.medium_net                 # 中单净流入
#   day.small_net                  # 小单净流入

# 行业资金流历史
snap = mf.get_moneyflow(MoneyFlowQuery(symbol="半导体", scope="industry", lookback_days=5))

# 概念资金流历史
snap = mf.get_moneyflow(MoneyFlowQuery(symbol="半导体", scope="concept", lookback_days=5))

# 行业资金流排名（今日）
ranks = mf.list_top_flows(scope="industry", top_n=20)
# 返回 list[MoneyFlowSnapshot]
# ranks[0].name, ranks[0].latest_main_net

# 概念资金流排名（今日）
ranks = mf.list_top_flows(scope="concept", top_n=20)
```

**分析技巧：**
- `consecutive_inflow_days >= 3` = 持续主力吸筹信号
- `consecutive_outflow_days >= 3` = 持续主力撤退信号
- 价涨 + 主力净流出 = 疑似出货，需要警惕
- 价跌 + 主力净流入 = 疑似吸筹，关注反转
- 超大单/大单净流入 vs 中小单净流出 = 机构进场、散户离场，偏看涨
- 小单净流入占主导 = 散户行情，缺乏持续性
- 行业排名中主力净流入前 5 + 个股主力净流入靠前 = 板块主线正在被资金追逐

## AStockConstituentProvider

A 股行业/概念板块成分股 + 指数成分股。个股排名、涨跌统计、市值分布。**需要 `pip install akshare`。**

```python
from digital_oracle import AStockConstituentProvider, ConstituentQuery

ac = AStockConstituentProvider()

# 行业成分股（涨跌幅降序）
result = ac.get_constituents(
    ConstituentQuery(symbol="半导体", scope="industry", sort_by="change_pct", top_n=10)
)
# 返回 ConstituentList
# result.total_count              # 成分股总数
# result.up_count / down_count / flat_count / limit_up_count / limit_down_count
# result.total_amount             # 板块总成交额
# result.average_change_pct       # 平均涨跌幅
# result.median_change_pct        # 中位数涨跌幅
# result.average_market_cap       # 平均总市值
# result.constituents             # tuple[StockConstituent, ...]（已排序）
#   c.code                        # 股票代码
#   c.name                        # 股票名称
#   c.latest                      # 最新价
#   c.change_pct                  # 涨跌幅
#   c.amount                      # 成交额
#   c.turnover_rate               # 换手率
#   c.total_market_cap            # 总市值
#   c.pe_dynamic                  # 动态市盈率
#   c.pb                          # 市净率

# 概念板块成分股
result = ac.get_constituents(
    ConstituentQuery(symbol="芯片", scope="concept", sort_by="amount", top_n=20)
)

# 指数成分股（沪深300、中证500等）
result = ac.get_constituents(
    ConstituentQuery(symbol="000300", scope="index")
)
# 指数成分股通常只有 code/name，没有价格数据
```

**分析技巧：**
- `average_change_pct` vs `median_change_pct`：平均值远大于中位数 → 权重股拉指数，小盘股跟涨乏力
- `limit_up_count >= 5` → 板块炒作火热，注意短期情绪见顶
- `up_count / total_count > 0.8` → 全面普涨，强趋势；`< 0.3` → 极度悲观或熊市
- 对比行业排名前 5 的成分股成交额占比 vs 总成交额 → 资金是否过度集中
- 指数成分股列表提供权重股名单，配合个股资金流判断指数方向

## AStockMarginProvider

A 股融资融券数据。两市融资余额、买入额、融券余额、杠杆率。**需要 `pip install akshare`。**

```python
from digital_oracle import AStockMarginProvider, MarginQuery

m = AStockMarginProvider()

result = m.get_market_margin(MarginQuery(exchange="both", lookback_days=20))
# 返回 MarketMargin
# result.latest_financing_balance  # 两市融资余额
# result.latest_financing_buy       # 当日融资买入额
# result.latest_short_balance       # 融券余额
# result.days                       # tuple[MarginDay, ...]
#   day.financing_balance / day.financing_buy / day.short_balance / day.total_balance
```

**分析技巧：**
- `financing_buy / financing_balance > 10%` = 杠杆买入激进，情绪过热
- 融资余额下降 + 指数上涨 = 背离，涨势衰减
- A 股融券余额通常 < 融资的 1%，突然飙升看空

## AStockEtfProvider

A 股 ETF 实时行情、折溢价、份额、资金流、历史日线。**需要 `pip install akshare`。**

```python
from digital_oracle import AStockEtfProvider, EtfQuery, EtfHistoryQuery

e = AStockEtfProvider()

# 关键词搜索 ETF
result = e.list_etfs(EtfQuery(name_keyword="半导体", top_n=10))
# snap.code, snap.name, snap.latest, snap.iopv
# snap.premium_pct (正=溢价), snap.shares_outstanding (份额)
# snap.market_cap, snap.main_net_inflow, snap.turnover_rate

# 单只 ETF 历史
bars = e.get_history(EtfHistoryQuery(symbol="159813", limit=20))
# bar.date, bar.open, bar.close, bar.volume, bar.amount
```

**分析技巧：**
- 溢价 > 2% = 买入过旺；折价 < -2% = 恐慌
- 份额增加 + 价格上涨 = 资金真实流入
- 份额不变 + 价格上涨 = 短期投机

## AStockValuationProvider

指数 PE/PB 分位 + 个股财务指标。**需要 `pip install akshare`。**

```python
from digital_oracle import AStockValuationProvider, ValuationQuery, FinancialQuery

v = AStockValuationProvider()

# 指数估值分位
result = v.get_index_valuation(ValuationQuery(symbol="沪深300", lookback_days=252))
# result.latest_pe / result.latest_pe_percentile (0-100)
# result.latest_pb / result.latest_pb_percentile
# result.days → tuple[PePbDay] (PE/PB/分位/指数点位)

# 个股财务
fin = v.get_financials(FinancialQuery(symbol="600519", start_year="2025"))
# fin.eps, fin.roe, fin.revenue_growth, fin.profit_growth
# fin.gross_margin, fin.net_margin, fin.debt_ratio
# fin.current_ratio, fin.book_value_per_share
```

**分析技巧：**
- PE 分位 < 20% = 低估，> 80% = 高估
- ROE > 15% + 利润增速 > 10% + 负债率 < 40% = 优质

## AStockDisclosureProvider

A 股公告搜索。按关键词/个股/类型检索每日公告。**需要 `pip install akshare`。**

```python
from digital_oracle import AStockDisclosureProvider, DisclosureQuery

d = AStockDisclosureProvider()

result = d.list_notices(DisclosureQuery(keyword="减持", top_n=20))
# n.code, n.name, n.title, n.category, n.date, n.url
```

**分析技巧：**
- 减持 = 利空；回购 = 利好；业绩预告 = 盈利拐点信号

