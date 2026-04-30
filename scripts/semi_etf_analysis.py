"""One-shot analysis: semiconductor ETF 159813 + sector health."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

# China network profile — clear proxies for Eastmoney direct
for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
    os.environ.pop(name, None)
os.environ["DIGITAL_ORACLE_ASTOCK_PROXY_MODE"] = "direct"

from digital_oracle import (
    AStockBreadthQuery,
    AStockIndexQuery,
    AStockNorthboundQuery,
    AStockProvider,
    AStockSectorBreadthQuery,
    AStockSectorHistoryQuery,
    AStockMoneyFlowProvider,
    MoneyFlowQuery,
    AStockConstituentProvider,
    ConstituentQuery,
    AStockMarginProvider,
    MarginQuery,
    AStockEtfProvider,
    EtfQuery,
    EtfHistoryQuery,
    AStockValuationProvider,
    ValuationQuery,
    AStockDisclosureProvider,
    DisclosureQuery,
    USTreasuryProvider,
    YieldCurveQuery,
    YahooPriceProvider,
    PriceHistoryQuery,
    FearGreedProvider,
    WebSearchProvider,
    gather,
)

def _f(val, fmt=".2f"):
    """Format nullable float with optional suffix."""
    if val is None:
        return "n/a"
    return f"{val:{fmt}}"

def fmt_pct(val):
    if val is None:
        return "n/a"
    return f"{val:+.2f}%"

def fmt_wan(val: float | None) -> str:
    if val is None:
        return "n/a"
    v = val / 1e4  # to 万元
    if abs(v) >= 1e4:
        return f"{v/1e4:.2f}亿"
    return f"{v:.0f}万"

def fmt_yi(val: float | None) -> str:
    if val is None:
        return "n/a"
    v = val / 1e8
    return f"{v:.2f}亿"

def main():
    print("=" * 80)
    print("半导体 ETF 159813 综合分析 — 数据采集")
    print("=" * 80)

    astock = AStockProvider()
    mf = AStockMoneyFlowProvider()
    ac = AStockConstituentProvider()
    margin = AStockMarginProvider()
    etf = AStockEtfProvider()
    valuation = AStockValuationProvider()
    disclosure = AStockDisclosureProvider()
    treasury = USTreasuryProvider()
    yahoo = YahooPriceProvider()
    fg = FearGreedProvider()
    web = WebSearchProvider()

    print("\n[1] Fetching all signals in parallel...\n")
    result = gather({
        "etf_list": lambda: etf.list_etfs(EtfQuery(name_keyword="半导体", top_n=10)),
        "etf_history": lambda: etf.get_history(EtfHistoryQuery(symbol="159813", limit=30)),
        "flow_semi_ind": lambda: mf.get_moneyflow(MoneyFlowQuery(symbol="半导体", scope="industry", lookback_days=10)),
        "flow_semi_concept": lambda: mf.get_moneyflow(MoneyFlowQuery(symbol="半导体", scope="concept", lookback_days=10)),
        "flow_top_ind": lambda: mf.list_top_flows(scope="industry", top_n=20),
        "semi_constituents": lambda: ac.get_constituents(
            ConstituentQuery(symbol="半导体", scope="industry", sort_by="change_pct")
        ),
        "market_margin": lambda: margin.get_market_margin(MarginQuery(exchange="both", lookback_days=20)),
        "market_breadth": lambda: astock.get_market_breadth(AStockBreadthQuery()),
        "semi_breadth": lambda: astock.get_sector_breadth(AStockSectorBreadthQuery(symbol="半导体")),
        "sh_index": lambda: astock.get_index_history(AStockIndexQuery(symbol="sh000001", limit=30)),
        "hs300": lambda: astock.get_index_history(AStockIndexQuery(symbol="sh000300", limit=30)),
        "semi_sector": lambda: astock.get_sector_history(AStockSectorHistoryQuery(symbol="半导体", limit=30)),
        "northbound": lambda: astock.get_northbound_flow(AStockNorthboundQuery(limit=20)),
        "hs300_val": lambda: valuation.get_index_valuation(ValuationQuery(symbol="沪深300", lookback_days=252)),
        "zz500_val": lambda: valuation.get_index_valuation(ValuationQuery(symbol="中证500", lookback_days=252)),
        "semi_disclosure": lambda: disclosure.list_notices(DisclosureQuery(keyword="半导体", top_n=30)),
        "yield_curve": lambda: treasury.latest_yield_curve(),
        "gold": lambda: yahoo.get_history(PriceHistoryQuery(symbol="GC=F", limit=30)),
        "copper": lambda: yahoo.get_history(PriceHistoryQuery(symbol="HG=F", limit=30)),
        "usdcny": lambda: yahoo.get_history(PriceHistoryQuery(symbol="USDCNY=X", limit=20)),
        "spy": lambda: yahoo.get_history(PriceHistoryQuery(symbol="SPY", limit=20)),
        "fear_greed": lambda: fg.get_index(),
        "vix": lambda: web.search("VIX index current level April 2026"),
    })

    # ============================================================
    # LAYER 1: ETF List
    # ============================================================
    print("\n" + "=" * 80)
    print("LAYER 1: 半导体 ETF 列表")
    print("=" * 80)
    etf_list = result.get("etf_list")
    if etf_list:
        print(f"  共 {etf_list.total_count} 只半导体ETF\n")
        for e in etf_list.snapshots:
            print(f"  {e.code} {e.name}")
            print(f"    价格={_f(e.latest)} | IOPV={_f(e.iopv)} | 折溢价={fmt_pct(e.premium_pct)}")
            print(f"    份额={fmt_wan(e.shares_outstanding)} | 市值={fmt_yi(e.market_cap)}")
            print(f"    主力净流入={fmt_wan(e.main_net_inflow)} | 换手率={_f(e.turnover_rate)}%")

    # ============================================================
    # LAYER 2: 159813 History
    # ============================================================
    print("\n" + "=" * 80)
    print("LAYER 2: 159813 鹏华半导体ETF 历史日线 (最近30日)")
    print("=" * 80)
    etf_hist = result.get("etf_history")
    if etf_hist:
        bars = etf_hist  # list[EtfHistoryBar]
        print(f"  共 {len(bars)} 根K线")
        if bars:
            latest = bars[-1]
            vol_str = f"{latest.volume:.0f}" if latest.volume else "n/a"
            print(f"  最新: {latest.date} C={_f(latest.close)} V={vol_str}")
            print(f"\n  {'日期':<12} {'开盘':>8} {'最高':>8} {'最低':>8} {'收盘':>8} {'成交量':>12}")
            print(f"  {'-'*12} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*12}")
            for bar in bars:
                vo = bar.volume if bar.volume else 0
                print(f"  {bar.date:<12} {_f(bar.open,'8.4f')} {_f(bar.high,'8.4f')} {_f(bar.low,'8.4f')} {_f(bar.close,'8.4f')} {vo:>12.0f}")

    # ============================================================
    # LAYER 3: Money Flow
    # ============================================================
    print("\n" + "=" * 80)
    print("LAYER 3: 半导体行业资金流 (最近10日)")
    print("=" * 80)
    flow_semi = result.get("flow_semi_ind")
    if flow_semi:
        print(f"  连续净流入天数: {flow_semi.consecutive_inflow_days}")
        print(f"  连续净流出天数: {flow_semi.consecutive_outflow_days}")
        print(f"  最新主力净流入: {fmt_wan(flow_semi.latest_main_net)}")
        print(f"  主力力度: {fmt_pct(flow_semi.main_strength_pct)}" if flow_semi.main_strength_pct else "")
        print(f"\n  {'日期':<12} {'涨跌':>8} {'主力净流入':>12} {'超大单':>12} {'大单':>12} {'中单':>12} {'小单':>12}")
        print(f"  {'-'*12} {'-'*8} {'-'*12} {'-'*12} {'-'*12} {'-'*12} {'-'*12}")
        for day in flow_semi.history:
            print(f"  {day.date:<12} {fmt_pct(day.change_pct):>8} {fmt_wan(day.main_net_inflow):>12} "
                  f"{fmt_wan(day.super_large_net):>12} {fmt_wan(day.large_net):>12} "
                  f"{fmt_wan(day.medium_net):>12} {fmt_wan(day.small_net):>12}")

    flow_semi_c = result.get("flow_semi_concept")
    if flow_semi_c:
        print(f"\n  --- 半导体概念资金流 ---")
        print(f"  连续净流入天数: {flow_semi_c.consecutive_inflow_days}")
        print(f"  最新主力净流入: {fmt_wan(flow_semi_c.latest_main_net)}")
        for day in flow_semi_c.history[:5]:
            print(f"  {day.date} 涨跌={fmt_pct(day.change_pct)} 主力={fmt_wan(day.main_net_inflow)}")

    top_ind = result.get("flow_top_ind")
    if top_ind:
        print(f"\n  --- 今日行业资金流排名 (Top 10) ---")
        for i, snap in enumerate(top_ind[:10]):
            print(f"  #{i+1} {snap.name:<8} 主力净流入={fmt_wan(snap.latest_main_net):>12}")

    # ============================================================
    # LAYER 4: Constituent Analysis
    # ============================================================
    print("\n" + "=" * 80)
    print("LAYER 4: 半导体行业成分股分析")
    print("=" * 80)
    semi_cons = result.get("semi_constituents")
    if semi_cons:
        print(f"  成分股总数: {semi_cons.total_count}")
        print(f"  上涨/下跌/平盘: {semi_cons.up_count}/{semi_cons.down_count}/{semi_cons.flat_count}")
        print(f"  涨停/跌停: {semi_cons.limit_up_count}/{semi_cons.limit_down_count}")
        print(f"  平均涨跌幅: {fmt_pct(semi_cons.average_change_pct)}")
        print(f"  中位数涨跌幅: {fmt_pct(semi_cons.median_change_pct)}")
        print(f"  总成交额: {fmt_yi(semi_cons.total_amount)}")
        print(f"  平均市值: {fmt_yi(semi_cons.average_market_cap)}")

        # Check if large caps pulling index
        if semi_cons.average_change_pct and semi_cons.median_change_pct:
            gap = semi_cons.average_change_pct - semi_cons.median_change_pct
            if gap > 0.5:
                print(f"  [!] 均值-中位数差距={gap:+.2f}% -> 大市值股拉指数，小市值跟涨弱")
            else:
                print(f"  均值-中位数差距={gap:+.2f}% -> 普涨格局")

        print(f"\n  --- 涨幅前10 ---")
        for c in semi_cons.constituents[:10]:
            print(f"  {c.code} {c.name:<8} 涨跌={fmt_pct(c.change_pct):>8} "
                  f"成交={fmt_yi(c.amount):>8} 市值={fmt_yi(c.total_market_cap):>8} PE={_f(c.pe_dynamic,'.1f')}")

        print(f"\n  --- 跌幅前5 ---")
        for c in semi_cons.constituents[-5:]:
            print(f"  {c.code} {c.name:<8} 涨跌={fmt_pct(c.change_pct):>8} "
                  f"成交={fmt_yi(c.amount):>8} 市值={fmt_yi(c.total_market_cap):>8} PE={_f(c.pe_dynamic,'.1f')}")

        # Top 5 by market cap
        sorted_by_cap = sorted(semi_cons.constituents, key=lambda x: x.total_market_cap or 0, reverse=True)
        print(f"\n  --- 市值前5大权重股 ---")
        for c in sorted_by_cap[:5]:
            print(f"  {c.code} {c.name:<8} 涨跌={fmt_pct(c.change_pct):>8} 市值={fmt_yi(c.total_market_cap):>8}")

    # ============================================================
    # LAYER 5: Margin
    # ============================================================
    print("\n" + "=" * 80)
    print("LAYER 5: 融资融券 (最近20日)")
    print("=" * 80)
    mm = result.get("market_margin")
    if mm:
        print(f"  最新日期: {mm.latest_date}")
        print(f"  融资余额: {fmt_yi(mm.latest_financing_balance)}")
        print(f"  融资买入额: {fmt_yi(mm.latest_financing_buy)}")
        print(f"  融券余额: {fmt_yi(mm.latest_short_balance)}")
        if mm.latest_financing_balance and mm.latest_financing_buy:
            ratio = mm.latest_financing_buy / mm.latest_financing_balance * 100
            flag = " [!] 过热!" if ratio > 10 else ""
            print(f"  买入/余额比: {ratio:.2f}%{flag}")
        print(f"\n  {'日期':<12} {'融资余额':>12} {'融资买入':>12} {'融券余额':>12}")
        print(f"  {'-'*12} {'-'*12} {'-'*12} {'-'*12}")
        for day in mm.days[:10]:
            print(f"  {day.date:<12} {fmt_yi(day.financing_balance):>12} "
                  f"{fmt_yi(day.financing_buy):>12} {fmt_yi(day.short_balance):>12}")

    # ============================================================
    # LAYER 6: Market Breadth
    # ============================================================
    print("\n" + "=" * 80)
    print("LAYER 6: 市场广度")
    print("=" * 80)
    mb = result.get("market_breadth")
    if mb:
        up_pct = mb.up_count / mb.total_count * 100 if mb.total_count else 0
        print(f"  全A股: total={mb.total_count} up={mb.up_count} down={mb.down_count} "
              f"flat={mb.flat_count} 涨跌比={up_pct:.1f}%")
        print(f"  涨停={mb.limit_up_count} 跌停={mb.limit_down_count}")
        print(f"  总成交额={fmt_yi(mb.total_amount)}")
        print(f"  平均涨跌幅={fmt_pct(mb.average_change_pct)} 中位数涨跌幅={fmt_pct(mb.median_change_pct)}")
        print(f"  source={mb.metadata.get('source')} level={mb.metadata.get('breadth_level')}")

    sb = result.get("semi_breadth")
    if sb:
        up_pct_s = sb.up_count / sb.total_count * 100 if sb.total_count else 0
        print(f"\n  半导体板块广度: total={sb.total_count} up={sb.up_count} down={sb.down_count} "
              f"flat={sb.flat_count} 上涨率={up_pct_s:.1f}%")
        print(f"  涨停={sb.limit_up_count} 跌停={sb.limit_down_count}")
        print(f"  平均涨跌幅={fmt_pct(sb.average_change_pct)} 中位数涨跌幅={fmt_pct(sb.median_change_pct)}")
        print(f"  成交额={fmt_yi(sb.total_amount)}")
        print(f"  source={sb.metadata.get('source')} level={sb.metadata.get('breadth_level')}")

    # ============================================================
    # LAYER 7: Index & Sector Trends
    # ============================================================
    print("\n" + "=" * 80)
    print("LAYER 7: 指数 & 半导体板块趋势")
    print("=" * 80)
    for label, hist in [("上证指数", result.get("sh_index")),
                         ("沪深300", result.get("hs300")),
                         ("半导体板块", result.get("semi_sector"))]:
        if hist:
            print(f"\n  [{label}] source={hist.metadata.get('source', 'unknown')}")
            bars = hist.bars
            if bars:
                latest = bars[-1]
                earliest = bars[0]
                chg = (latest.close - earliest.close) / earliest.close * 100 if earliest.close else 0
                print(f"  区间涨跌 ({earliest.date} -> {latest.date}): {chg:+.2f}%")
                print(f"  {'日期':<12} {'开盘':>8} {'收盘':>8} {'成交量':>12}")
                print(f"  {'-'*12} {'-'*8} {'-'*8} {'-'*12}")
                for bar in bars[-10:]:
                    vo = bar.volume if bar.volume else 0
                    print(f"  {bar.date:<12} {bar.open:>8.2f} {bar.close:>8.2f} {vo:>12.0f}")

    # ============================================================
    # LAYER 8: Northbound
    # ============================================================
    print("\n" + "=" * 80)
    print("LAYER 8: 北向资金 (最近20日)")
    print("=" * 80)
    nb = result.get_or("northbound", None)
    if nb:
        total_net = sum(f.net_buy_amount for f in nb if f.net_buy_amount) if nb else 0
        print(f"  区间累计净买入: {fmt_yi(total_net)}")
        for flow in nb[:10]:
            print(f"  {flow.date} | 净买入={fmt_wan(flow.net_buy_amount):>10} | "
                  f"累计={fmt_yi(flow.cumulative_net_buy_amount):>10} | "
                  f"沪深300={fmt_pct(flow.hs300_change_pct)}")

    # ============================================================
    # LAYER 9: Valuation
    # ============================================================
    print("\n" + "=" * 80)
    print("LAYER 9: 估值分位")
    print("=" * 80)
    for label, val in [("沪深300", result.get("hs300_val")),
                        ("中证500", result.get("zz500_val"))]:
        if val:
            print(f"\n  [{label}]")
            print(f"  最新PE(动态)={_f(val.latest_pe)} PE分位={_f(val.latest_pe_percentile,'.1f')}%")
            print(f"  最新PB={_f(val.latest_pb)} PB分位={_f(val.latest_pb_percentile,'.1f')}%")
            print(f"  最新指数点位={val.latest_index_level}")
            if val.days:
                print(f"  {'日期':<12} {'PE':>8} {'PE分位':>8} {'PB':>8} {'PB分位':>8} {'指数点位':>10}")
                print(f"  {'-'*12} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*10}")
                for d in val.days[-5:]:
                    print(f"  {d.date:<12} {_f(d.pe_dynamic,'8.2f')} {_f(d.pe_dynamic_percentile,'7.1f')}% "
                          f"{_f(d.pb,'8.2f')} {_f(d.pb_percentile,'7.1f')}% {_f(d.index_level,'10.2f')}")

    # ============================================================
    # LAYER 10: Disclosures
    # ============================================================
    print("\n" + "=" * 80)
    print("LAYER 10: 半导体相关公告")
    print("=" * 80)
    disc = result.get("semi_disclosure")
    if disc:
        print(f"  共 {disc.total_count} 条公告，显示前10条")
        for n in disc.notices[:10]:
            print(f"  {n.code} {n.name} | {n.title} | {n.date} | {n.category}")

    # ============================================================
    # LAYER 11: Global Macro
    # ============================================================
    print("\n" + "=" * 80)
    print("LAYER 11: 全球宏观验证")
    print("=" * 80)

    yc = result.get("yield_curve")
    if yc:
        y10 = yc.yield_for("10Y")
        y2 = yc.yield_for("2Y")
        y3m = yc.yield_for("3M")
        spread = yc.spread("10Y", "2Y") if y10 and y2 else None
        print(f"  美债: 10Y={_f(y10)}% 2Y={_f(y2)}% 3M={_f(y3m)}%")
        if spread is not None:
            flag = " [!] 倒挂!" if spread < 0 else ""
            print(f"  10Y-2Y利差: {_f(spread)}%{flag}")

    for label, key in [("黄金 GC=F", "gold"), ("铜 HG=F", "copper"),
                        ("USDCNY", "usdcny"), ("SPY", "spy")]:
        hist = result.get(key)
        if hist and hist.latest:
            earliest = hist.earliest
            if earliest and earliest.close and earliest.close != 0:
                chg = (hist.latest.close - earliest.close) / earliest.close * 100
                print(f"  {label}: latest={hist.latest.close:.4f} 区间涨跌={chg:+.2f}%")
            else:
                print(f"  {label}: latest={hist.latest.close:.4f}")

    # Copper/Gold ratio
    gold_hist = result.get("gold")
    copper_hist = result.get("copper")
    if gold_hist and copper_hist and gold_hist.latest and copper_hist.latest:
        ratio = copper_hist.latest.close / gold_hist.latest.close
        print(f"  铜金比: {ratio:.4f} (工业需求 vs 避险需求)")

    fg_data = result.get("fear_greed")
    if fg_data:
        print(f"\n  CNN Fear & Greed: {fg_data.score} ({fg_data.rating})")
        print(f"    前一日={fg_data.previous_close} 一周前={fg_data.one_week_ago} "
              f"一月前={fg_data.one_month_ago} 一年前={fg_data.one_year_ago}")

    vix_data = result.get("vix")
    if vix_data:
        print(f"\n  VIX搜索: {vix_data.text()[:400]}")

    # ============================================================
    # KEY SIGNALS SUMMARY
    # ============================================================
    print("\n" + "=" * 80)
    print("关键信号汇总")
    print("=" * 80)

    # 1. ETF flow
    if etf_list:
        for e in etf_list.snapshots:
            if e.code == "159813":
                print(f"[ETF 159813] 价格={_f(e.latest)} 折溢价={fmt_pct(e.premium_pct)} "
                      f"份额={fmt_wan(e.shares_outstanding)} 主力净流入={fmt_wan(e.main_net_inflow)}")
                break

    # 2. Cost basis check
    if etf_hist and len(etf_hist) > 0:
        cost = 1.298
        latest_price = etf_hist[-1].close
        if latest_price:
            pnl_pct = (latest_price - cost) / cost * 100
            print(f"[持仓盈亏] 成本={cost} 现价={latest_price:.4f} 盈亏={pnl_pct:+.2f}%")

    # 3. Money flow direction
    if flow_semi:
        direction = "流入" if flow_semi.consecutive_inflow_days > 0 else ("流出" if flow_semi.consecutive_outflow_days > 0 else "平衡")
        print(f"[行业资金] 连续{flow_semi.consecutive_inflow_days}天净流入 / {flow_semi.consecutive_outflow_days}天净流出 "
              f"-> 主力在{direction}")

    # 4. Breadth check
    if sb:
        breadth_health = "全面普涨" if (sb.up_count / sb.total_count * 100 > 80) else \
                        ("龙头拉指数" if (sb.average_change_pct and sb.median_change_pct and
                                          sb.average_change_pct - sb.median_change_pct > 0.5) else "温和分化")
        print(f"[板块广度] 上涨率={sb.up_count/sb.total_count*100:.1f}% -> {breadth_health}")

    # 5. Valuation
    hs300v = result.get("hs300_val")
    if hs300v and hs300v.latest_pe_percentile is not None:
        level = "低估" if hs300v.latest_pe_percentile < 20 else ("高估" if hs300v.latest_pe_percentile > 80 else "合理")
        print(f"[估值] 沪深300 PE分位={hs300v.latest_pe_percentile:.1f}% -> {level}")

    # 6. Margin
    if mm and mm.latest_financing_balance and mm.latest_financing_buy:
        lev = mm.latest_financing_buy / mm.latest_financing_balance * 100
        lev_status = "过热" if lev > 10 else ("温和" if lev > 5 else "偏低")
        print(f"[杠杆] 买入/余额={lev:.2f}% -> {lev_status}")

    print("\n数据采集完成")
    print("=" * 80)

if __name__ == "__main__":
    main()
