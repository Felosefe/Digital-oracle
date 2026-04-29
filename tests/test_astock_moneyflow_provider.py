from __future__ import annotations

import unittest
from typing import Any, Mapping

from digital_oracle.providers.astock_moneyflow import (
    AStockMoneyFlowProvider,
    MoneyFlowQuery,
    _compute_consecutive_days,
    _records,
)
from digital_oracle.providers.base import ProviderParseError


SAMPLE_INDIVIDUAL_ROWS = [
    {
        "日期": "2026-04-23",
        "收盘价": 1600.0,
        "涨跌幅": 1.5,
        "主力净流入-净额": 50000000.0,
        "超大单净流入-净额": 30000000.0,
        "大单净流入-净额": 20000000.0,
        "中单净流入-净额": -10000000.0,
        "小单净流入-净额": -40000000.0,
    },
    {
        "日期": "2026-04-24",
        "收盘价": 1620.0,
        "涨跌幅": 1.25,
        "主力净流入-净额": 80000000.0,
        "超大单净流入-净额": 50000000.0,
        "大单净流入-净额": 30000000.0,
        "中单净流入-净额": -20000000.0,
        "小单净流入-净额": -60000000.0,
    },
    {
        "日期": "2026-04-25",
        "收盘价": 1610.0,
        "涨跌幅": -0.62,
        "主力净流入-净额": -30000000.0,
        "超大单净流入-净额": -20000000.0,
        "大单净流入-净额": -10000000.0,
        "中单净流入-净额": 15000000.0,
        "小单净流入-净额": 15000000.0,
    },
    {
        "日期": "2026-04-28",
        "收盘价": 1640.0,
        "涨跌幅": 1.86,
        "主力净流入-净额": 120000000.0,
        "超大单净流入-净额": 80000000.0,
        "大单净流入-净额": 40000000.0,
        "中单净流入-净额": -30000000.0,
        "小单净流入-净额": -90000000.0,
    },
]

SAMPLE_SECTOR_RANK_ROWS = [
    {
        "序号": 1,
        "名称": "半导体",
        "今日主力净流入-净额": 2_500_000_000.0,
    },
    {
        "序号": 2,
        "名称": "银行",
        "今日主力净流入-净额": 1_800_000_000.0,
    },
    {
        "序号": 3,
        "名称": "证券",
        "今日主力净流入-净额": -500_000_000.0,
    },
]

SAMPLE_SECTOR_HIST_ROWS = [
    {
        "日期": "2026-04-24",
        "收盘价": 3500.0,
        "涨跌幅": 2.0,
        "主力净流入-净额": 2_500_000_000.0,
    },
    {
        "日期": "2026-04-25",
        "收盘价": 3600.0,
        "涨跌幅": 2.86,
        "主力净流入-净额": 1_200_000_000.0,
    },
    {
        "日期": "2026-04-28",
        "收盘价": 3550.0,
        "涨跌幅": -1.39,
        "主力净流入-净额": -800_000_000.0,
    },
]


class FrameLike:
    def __init__(self, rows: list[Mapping[str, Any]]) -> None:
        self.rows = rows

    def to_dict(self, orient: str) -> list[Mapping[str, Any]]:
        return self.rows


class FakeMoneyFlowFetcher:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.individual_flow: Any = FrameLike(SAMPLE_INDIVIDUAL_ROWS)
        self.sector_flow_rank: Any = FrameLike(SAMPLE_SECTOR_RANK_ROWS)
        self.sector_flow_hist: Any = FrameLike(SAMPLE_SECTOR_HIST_ROWS)

    def fetch_individual_flow(self, *, symbol: str) -> Any:
        self.calls.append(("individual", {"symbol": symbol}))
        return self.individual_flow

    def fetch_sector_flow_rank(self, *, sector_type: str) -> Any:
        self.calls.append(("rank", {"sector_type": sector_type}))
        return self.sector_flow_rank

    def fetch_sector_flow_hist(self, *, sector: str) -> Any:
        self.calls.append(("hist", {"sector": sector}))
        return self.sector_flow_hist


class AStockMoneyFlowProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fetcher = FakeMoneyFlowFetcher()
        self.provider = AStockMoneyFlowProvider(fetcher=self.fetcher)

    # -- individual flow --

    def test_individual_flow_parses_all_fields(self) -> None:
        snap = self.provider.get_moneyflow(
            MoneyFlowQuery(symbol="600519", scope="individual", lookback_days=3)
        )

        self.assertEqual(snap.symbol, "600519")
        self.assertEqual(snap.scope, "individual")
        self.assertEqual(len(snap.history), 3)
        self.assertEqual(snap.history[-1].date, "2026-04-28")
        self.assertEqual(snap.history[-1].close, 1640.0)
        self.assertEqual(snap.history[-1].change_pct, 1.86)
        self.assertEqual(snap.history[-1].main_net_inflow, 120_000_000.0)
        self.assertEqual(snap.history[-1].super_large_net, 80_000_000.0)
        self.assertEqual(snap.history[-1].large_net, 40_000_000.0)
        self.assertEqual(snap.history[-1].medium_net, -30_000_000.0)
        self.assertEqual(snap.history[-1].small_net, -90_000_000.0)

    def test_individual_flow_latest_main_net(self) -> None:
        snap = self.provider.get_moneyflow(
            MoneyFlowQuery(symbol="600519", scope="individual", lookback_days=4)
        )

        self.assertEqual(snap.latest_main_net, 120_000_000.0)

    def test_individual_flow_consecutive_inflow_resets_after_outflow(self) -> None:
        snap = self.provider.get_moneyflow(
            MoneyFlowQuery(symbol="600519", scope="individual", lookback_days=4)
        )

        # History: +50M, +80M, -30M, +120M -> last day is inflow, but preceded by outflow
        # So consecutive_inflow_days = 1 (only last day), consecutive_outflow_days = 1 (2026-04-25)
        self.assertEqual(snap.consecutive_inflow_days, 1)
        self.assertEqual(snap.consecutive_outflow_days, 0)

    def test_individual_flow_all_inflow(self) -> None:
        fetcher = FakeMoneyFlowFetcher()
        fetcher.individual_flow = FrameLike([
            {"日期": "2026-04-24", "主力净流入-净额": 100.0},
            {"日期": "2026-04-25", "主力净流入-净额": 200.0},
            {"日期": "2026-04-28", "主力净流入-净额": 300.0},
        ])
        provider = AStockMoneyFlowProvider(fetcher=fetcher)
        snap = provider.get_moneyflow(
            MoneyFlowQuery(symbol="600519", scope="individual", lookback_days=3)
        )

        self.assertEqual(snap.consecutive_inflow_days, 3)
        self.assertEqual(snap.consecutive_outflow_days, 0)

    def test_individual_flow_all_outflow(self) -> None:
        fetcher = FakeMoneyFlowFetcher()
        fetcher.individual_flow = FrameLike([
            {"日期": "2026-04-24", "主力净流入-净额": -100.0},
            {"日期": "2026-04-25", "主力净流入-净额": -200.0},
            {"日期": "2026-04-28", "主力净流入-净额": -300.0},
        ])
        provider = AStockMoneyFlowProvider(fetcher=fetcher)
        snap = provider.get_moneyflow(
            MoneyFlowQuery(symbol="600519", scope="individual", lookback_days=3)
        )

        self.assertEqual(snap.consecutive_inflow_days, 0)
        self.assertEqual(snap.consecutive_outflow_days, 3)

    def test_individual_flow_lookback_limits_history(self) -> None:
        snap = self.provider.get_moneyflow(
            MoneyFlowQuery(symbol="600519", scope="individual", lookback_days=2)
        )

        self.assertEqual(len(snap.history), 2)
        self.assertEqual(snap.history[0].date, "2026-04-25")
        self.assertEqual(snap.history[1].date, "2026-04-28")

    def test_individual_flow_zero_lookback_returns_all(self) -> None:
        snap = self.provider.get_moneyflow(
            MoneyFlowQuery(symbol="600519", scope="individual", lookback_days=0)
        )

        self.assertEqual(len(snap.history), 4)

    def test_individual_flow_empty_raises(self) -> None:
        fetcher = FakeMoneyFlowFetcher()
        fetcher.individual_flow = FrameLike([])
        provider = AStockMoneyFlowProvider(fetcher=fetcher)

        with self.assertRaisesRegex(ProviderParseError, "no fund flow data"):
            provider.get_moneyflow(
                MoneyFlowQuery(symbol="000000", scope="individual")
            )

    def test_individual_flow_fetch_error_raises(self) -> None:
        class BrokenFetcher(FakeMoneyFlowFetcher):
            def fetch_individual_flow(self, *, symbol: str) -> Any:
                raise ProviderParseError("BJ exchange not covered")

        provider = AStockMoneyFlowProvider(fetcher=BrokenFetcher())

        with self.assertRaisesRegex(ProviderParseError, "BJ exchange"):
            provider.get_moneyflow(
                MoneyFlowQuery(symbol="920002", scope="individual")
            )

    def test_sector_rank_network_error_raises(self) -> None:
        class BrokenFetcher(FakeMoneyFlowFetcher):
            def fetch_sector_flow_rank(self, *, sector_type: str) -> Any:
                raise ProviderParseError("Connection aborted")

        provider = AStockMoneyFlowProvider(fetcher=BrokenFetcher())

        with self.assertRaisesRegex(ProviderParseError, "Connection aborted"):
            provider.list_top_flows(scope="industry", top_n=10)

    def test_sector_hist_network_error_raises(self) -> None:
        class BrokenFetcher(FakeMoneyFlowFetcher):
            def fetch_sector_flow_hist(self, *, sector: str) -> Any:
                raise ProviderParseError("Connection aborted")

        provider = AStockMoneyFlowProvider(fetcher=BrokenFetcher())

        with self.assertRaisesRegex(ProviderParseError, "Connection aborted"):
            provider.get_moneyflow(
                MoneyFlowQuery(symbol="半导体", scope="industry")
            )

    # -- industry / concept flow --

    def test_industry_flow_hist(self) -> None:
        snap = self.provider.get_moneyflow(
            MoneyFlowQuery(symbol="半导体", scope="industry", lookback_days=2)
        )

        self.assertEqual(snap.symbol, "半导体")
        self.assertEqual(snap.scope, "industry")
        self.assertEqual(len(snap.history), 2)
        self.assertEqual(snap.history[-1].main_net_inflow, -800_000_000.0)
        self.assertEqual(snap.latest_main_net, -800_000_000.0)
        self.assertEqual(snap.metadata["sector_type"], "行业资金流")

    def test_concept_flow_hist(self) -> None:
        snap = self.provider.get_moneyflow(
            MoneyFlowQuery(symbol="半导体", scope="concept", lookback_days=2)
        )

        self.assertEqual(snap.scope, "concept")
        self.assertEqual(snap.metadata["sector_type"], "概念资金流")

    def test_sector_flow_consecutive_days(self) -> None:
        # +2.5B, +1.2B, -0.8B -> last is outflow, preceded by 2 inflows
        snap = self.provider.get_moneyflow(
            MoneyFlowQuery(symbol="半导体", scope="industry", lookback_days=3)
        )

        self.assertEqual(snap.consecutive_inflow_days, 0)
        self.assertEqual(snap.consecutive_outflow_days, 1)

    # -- ranking --

    def test_list_top_flows_industry(self) -> None:
        results = self.provider.list_top_flows(scope="industry", top_n=2)

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].symbol, "半导体")
        self.assertEqual(results[0].latest_main_net, 2_500_000_000.0)
        self.assertEqual(results[1].symbol, "银行")
        self.assertEqual(results[1].latest_main_net, 1_800_000_000.0)

    def test_list_top_flows_concept(self) -> None:
        results = self.provider.list_top_flows(scope="concept", top_n=3)

        self.assertEqual(len(results), 3)
        self.assertEqual(results[2].symbol, "证券")
        self.assertEqual(results[2].latest_main_net, -500_000_000.0)

    def test_list_top_flows_invalid_scope(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported scope"):
            self.provider.list_top_flows(scope="individual", top_n=10)

    # -- error handling --

    def test_invalid_scope_raises(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported scope"):
            self.provider.get_moneyflow(
                MoneyFlowQuery(symbol="600519", scope="foobar")
            )

    def test_metadata(self) -> None:
        meta = self.provider.describe()

        self.assertEqual(meta.provider_id, "astock_moneyflow")
        self.assertIn("Fund Flow", meta.display_name)
        self.assertIn("astock_moneyflow", meta.capabilities)

    # -- unit: _records --

    def test_records_handles_dataframe(self) -> None:
        class Df:
            def to_dict(self, orient: str) -> list[dict[str, Any]]:
                return [{"a": 1}]

        rows = _records(Df())
        self.assertEqual(rows, [{"a": 1}])

    def test_records_handles_list(self) -> None:
        rows = _records([{"a": 1}])
        self.assertEqual(rows, [{"a": 1}])

    # -- unit: _compute_consecutive_days --

    def test_compute_consecutive_all_inflow(self) -> None:
        from digital_oracle.providers.astock_moneyflow import MoneyFlowDay

        days = tuple(
            MoneyFlowDay(date=f"2026-04-{d}", main_net_inflow=100.0)
            for d in range(24, 29)
        )
        inflow, outflow = _compute_consecutive_days(days)
        self.assertEqual(inflow, 5)
        self.assertEqual(outflow, 0)

    def test_compute_consecutive_mixed(self) -> None:
        from digital_oracle.providers.astock_moneyflow import MoneyFlowDay

        days = (
            MoneyFlowDay(date="2026-04-24", main_net_inflow=100.0),
            MoneyFlowDay(date="2026-04-25", main_net_inflow=50.0),
            MoneyFlowDay(date="2026-04-28", main_net_inflow=-30.0),
            MoneyFlowDay(date="2026-04-29", main_net_inflow=200.0),
        )
        inflow, outflow = _compute_consecutive_days(days)
        self.assertEqual(inflow, 1)
        self.assertEqual(outflow, 0)


if __name__ == "__main__":
    unittest.main()
