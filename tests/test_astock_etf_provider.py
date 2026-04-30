from __future__ import annotations

import unittest
from typing import Any, Mapping

from digital_oracle.providers.astock_etf import (
    AStockEtfProvider,
    EtfHistoryQuery,
    EtfQuery,
)
from digital_oracle.providers.base import ProviderParseError

SAMPLE_SPOT_ROWS = [
    {
        "代码": "159813",
        "名称": "芯片ETF",
        "最新价": 1.284,
        "IOPV实时净值": 1.278,
        "折溢价率": 0.47,
        "涨跌幅": 4.99,
        "涨跌额": 0.063,
        "成交量": 3018196.0,
        "成交额": 393473585.09,
        "换手率": 6.91,
        "最新份额": 107101300.0,
        "总市值": 137196765.0,
        "主力净流入-净额": 481250.0,
        "主力净流入-净占比": 13.41,
        "更新时间": "2026-04-30 11:54:06",
    },
    {
        "代码": "512480",
        "名称": "半导体ETF",
        "最新价": 1.050,
        "IOPV实时净值": 1.048,
        "折溢价率": 0.19,
        "涨跌幅": 3.55,
        "涨跌额": 0.036,
        "成交量": 50000000.0,
        "成交额": 52500000.0,
        "换手率": 4.20,
        "最新份额": 500000000.0,
        "总市值": 525000000.0,
        "主力净流入-净额": 1200000.0,
        "主力净流入-净占比": 2.29,
        "更新时间": "2026-04-30 11:50:00",
    },
    {
        "代码": "510050",
        "名称": "上证50ETF",
        "最新价": 2.850,
        "IOPV实时净值": 2.845,
        "折溢价率": 0.18,
        "涨跌幅": 0.35,
        "涨跌额": 0.010,
        "成交量": 100000000.0,
        "成交额": 285000000.0,
        "换手率": 1.50,
        "最新份额": 2000000000.0,
        "总市值": 5700000000.0,
        "主力净流入-净额": None,
        "主力净流入-净占比": None,
        "更新时间": "2026-04-30 11:55:00",
    },
]

SAMPLE_HIST_ROWS = [
    {
        "日期": "2026-04-28",
        "开盘": 1.200,
        "收盘": 1.220,
        "最高": 1.230,
        "最低": 1.195,
        "成交量": 2000000.0,
        "成交额": 2440000.0,
        "涨跌幅": 1.67,
        "换手率": 3.50,
    },
    {
        "日期": "2026-04-29",
        "开盘": 1.220,
        "收盘": 1.250,
        "最高": 1.255,
        "最低": 1.215,
        "成交量": 3000000.0,
        "成交额": 3700000.0,
        "涨跌幅": 2.46,
        "换手率": 5.20,
    },
    {
        "日期": "2026-04-30",
        "开盘": 1.250,
        "收盘": 1.284,
        "最高": 1.300,
        "最低": 1.245,
        "成交量": 4000000.0,
        "成交额": 5000000.0,
        "涨跌幅": 2.72,
        "换手率": 6.91,
    },
]


class FrameLike:
    def __init__(self, rows: list[Mapping[str, Any]]) -> None:
        self.rows = rows

    def to_dict(self, orient: str) -> list[Mapping[str, Any]]:
        return self.rows


class FakeEtfFetcher:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.spot_data: Any = FrameLike(SAMPLE_SPOT_ROWS)
        self.hist_data: Any = FrameLike(SAMPLE_HIST_ROWS)

    def fetch_etf_spot(self) -> Any:
        self.calls.append(("spot", {}))
        return self.spot_data

    def fetch_etf_history(self, *, symbol: str, period: str, start_date: str | None, end_date: str | None) -> Any:
        self.calls.append(("hist", {"symbol": symbol, "period": period}))
        return self.hist_data


class AStockEtfProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fetcher = FakeEtfFetcher()
        self.provider = AStockEtfProvider(fetcher=self.fetcher)

    # -- list all --

    def test_list_all_etfs(self) -> None:
        result = self.provider.list_etfs()

        self.assertEqual(result.total_count, 3)
        self.assertEqual(len(result.snapshots), 3)
        self.assertEqual(result.metadata["source"], "fund_etf_spot_em")

    # -- name keyword filtering --

    def test_filter_by_keyword(self) -> None:
        result = self.provider.list_etfs(EtfQuery(name_keyword="芯片"))

        self.assertEqual(len(result.snapshots), 1)
        self.assertEqual(result.snapshots[0].code, "159813")

    def test_filter_by_symbol(self) -> None:
        result = self.provider.list_etfs(EtfQuery(symbol="512480"))

        self.assertEqual(len(result.snapshots), 1)
        self.assertEqual(result.snapshots[0].name, "半导体ETF")

    # -- snapshot fields --

    def test_snapshot_fields(self) -> None:
        result = self.provider.list_etfs(EtfQuery(symbol="159813"))
        snap = result.snapshots[0]

        self.assertAlmostEqual(snap.latest, 1.284)
        self.assertAlmostEqual(snap.iopv, 1.278)
        self.assertAlmostEqual(snap.premium_pct, 0.47)
        self.assertAlmostEqual(snap.change_pct, 4.99)
        self.assertAlmostEqual(snap.amount, 393473585.09)
        self.assertAlmostEqual(snap.shares_outstanding, 107101300.0)
        self.assertAlmostEqual(snap.market_cap, 137196765.0)
        self.assertAlmostEqual(snap.main_net_inflow, 481250.0)
        self.assertAlmostEqual(snap.turnover_rate, 6.91)

    def test_snapshot_null_money_flow(self) -> None:
        result = self.provider.list_etfs(EtfQuery(symbol="510050"))
        snap = result.snapshots[0]

        self.assertIsNone(snap.main_net_inflow)
        self.assertIsNone(snap.main_net_pct)

    # -- premium calculation fallback --

    def test_premium_calculated_when_field_missing(self) -> None:
        rows = [{"代码": "159900", "名称": "测试ETF", "最新价": 1.050, "IOPV实时净值": 1.000}]
        fetcher = FakeEtfFetcher()
        fetcher.spot_data = FrameLike(rows)
        provider = AStockEtfProvider(fetcher=fetcher)
        result = provider.list_etfs(EtfQuery(symbol="159900"))
        snap = result.snapshots[0]

        self.assertAlmostEqual(snap.premium_pct, 5.0)

    # -- ETF history --

    def test_history_all_fields(self) -> None:
        bars = self.provider.get_history(EtfHistoryQuery(symbol="159813", limit=2))

        self.assertEqual(len(bars), 2)
        self.assertEqual(bars[0].date, "2026-04-29")
        self.assertAlmostEqual(bars[0].close, 1.250)
        self.assertAlmostEqual(bars[0].change_pct, 2.46)
        self.assertEqual(bars[1].date, "2026-04-30")
        self.assertAlmostEqual(bars[1].close, 1.284)

    def test_history_limit_zero_returns_all(self) -> None:
        bars = self.provider.get_history(EtfHistoryQuery(symbol="159813", limit=0))
        self.assertEqual(len(bars), 3)

    # -- error handling --

    def test_fetch_error_propagates(self) -> None:
        class BrokenFetcher(FakeEtfFetcher):
            def fetch_etf_spot(self) -> Any:
                raise ProviderParseError("network error")

        provider = AStockEtfProvider(fetcher=BrokenFetcher())
        with self.assertRaisesRegex(ProviderParseError, "network error"):
            provider.list_etfs()

    # -- metadata --

    def test_metadata(self) -> None:
        meta = self.provider.describe()
        self.assertEqual(meta.provider_id, "astock_etf")
        self.assertIn("astock_etf", meta.capabilities)


if __name__ == "__main__":
    unittest.main()
