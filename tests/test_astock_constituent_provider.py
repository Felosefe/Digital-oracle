from __future__ import annotations

import unittest
from typing import Any, Mapping

from digital_oracle.providers.astock_constituent import (
    AStockConstituentProvider,
    ConstituentList,
    ConstituentQuery,
    StockConstituent,
)
from digital_oracle.providers.base import ProviderParseError

# -- sample data --

SAMPLE_INDUSTRY_ROWS = [
    {
        "代码": "688981",
        "名称": "中芯国际",
        "最新价": 50.0,
        "涨跌幅": 3.5,
        "涨跌额": 1.7,
        "成交量": 50000000,
        "成交额": 2_500_000_000,
        "换手率": 2.1,
        "市盈率-动态": 35.0,
        "市净率": 2.5,
        "总市值": 400_000_000_000,
        "流通市值": 300_000_000_000,
    },
    {
        "代码": "688012",
        "名称": "中微公司",
        "最新价": 120.0,
        "涨跌幅": -1.2,
        "涨跌额": -1.5,
        "成交量": 20000000,
        "成交额": 2_400_000_000,
        "换手率": 1.5,
        "市盈率-动态": 45.0,
        "市净率": 3.0,
        "总市值": 600_000_000_000,
        "流通市值": 500_000_000_000,
    },
    {
        "代码": "603501",
        "名称": "韦尔股份",
        "最新价": 95.0,
        "涨跌幅": 10.0,
        "涨跌额": 8.6,
        "成交量": 35000000,
        "成交额": 3_200_000_000,
        "换手率": 4.2,
        "市盈率-动态": 28.0,
        "市净率": 4.0,
        "总市值": 500_000_000_000,
        "流通市值": 450_000_000_000,
    },
    {
        "代码": "002371",
        "名称": "北方华创",
        "最新价": 300.0,
        "涨跌幅": 0.0,
        "涨跌额": 0.0,
        "成交量": 5000000,
        "成交额": 1_500_000_000,
        "换手率": 0.5,
        "市盈率-动态": 50.0,
        "市净率": 5.0,
        "总市值": 1_000_000_000_000,
        "流通市值": 800_000_000_000,
    },
    {
        "代码": "688111",
        "名称": "金山办公",
        "最新价": None,
        "涨跌幅": None,
        "成交额": None,
        "总市值": None,
        "流通市值": None,
    },
]

SAMPLE_CONCEPT_ROWS = [
    {
        "代码": "688981",
        "名称": "中芯国际",
        "最新价": 50.0,
        "涨跌幅": 3.5,
        "成交额": 2_500_000_000,
        "总市值": 400_000_000_000,
    },
    {
        "代码": "688012",
        "名称": "中微公司",
        "最新价": 120.0,
        "涨跌幅": -1.2,
        "成交额": 2_400_000_000,
        "总市值": 600_000_000_000,
    },
]

SAMPLE_INDEX_ROWS = [
    {
        "品种代码": "600519",
        "品种名称": "贵州茅台",
    },
    {
        "品种代码": "601318",
        "品种名称": "中国平安",
    },
    {
        "品种代码": "600036",
        "品种名称": "招商银行",
    },
]


class FrameLike:
    def __init__(self, rows: list[Mapping[str, Any]]) -> None:
        self.rows = rows

    def to_dict(self, orient: str) -> list[Mapping[str, Any]]:
        return self.rows


class FakeConstituentFetcher:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.industry_rows: Any = FrameLike(SAMPLE_INDUSTRY_ROWS)
        self.concept_rows: Any = FrameLike(SAMPLE_CONCEPT_ROWS)
        self.index_rows: Any = FrameLike(SAMPLE_INDEX_ROWS)

    def fetch_industry_constituents(self, *, symbol: str) -> Any:
        self.calls.append(("industry", {"symbol": symbol}))
        return self.industry_rows

    def fetch_concept_constituents(self, *, symbol: str) -> Any:
        self.calls.append(("concept", {"symbol": symbol}))
        return self.concept_rows

    def fetch_index_constituents(self, *, symbol: str) -> Any:
        self.calls.append(("index", {"symbol": symbol}))
        return self.index_rows


class AStockConstituentProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fetcher = FakeConstituentFetcher()
        self.provider = AStockConstituentProvider(fetcher=self.fetcher)

    # -- industry --

    def test_industry_constituents_parses_all_fields(self) -> None:
        result = self.provider.get_constituents(
            ConstituentQuery(symbol="半导体", scope="industry")
        )

        self.assertEqual(result.symbol, "半导体")
        self.assertEqual(result.scope, "industry")
        self.assertEqual(result.total_count, 5)
        self.assertEqual(result.up_count, 2)
        self.assertEqual(result.down_count, 1)
        self.assertEqual(result.flat_count, 1)
        self.assertEqual(result.limit_up_count, 1)
        self.assertEqual(result.limit_down_count, 0)

        self.assertEqual(len(result.constituents), 5)

        c0 = result.constituents[0]
        self.assertEqual(c0.code, "603501")
        self.assertEqual(c0.change_pct, 10.0)
        self.assertEqual(c0.amount, 3_200_000_000.0)
        self.assertEqual(c0.pe_dynamic, 28.0)
        self.assertEqual(c0.pb, 4.0)

        # Last one has all None values (停牌/无数据)
        c_last = result.constituents[-1]
        self.assertEqual(c_last.name, "金山办公")
        self.assertIsNone(c_last.latest)
        self.assertIsNone(c_last.change_pct)

    def test_industry_constituents_aggregate_stats(self) -> None:
        result = self.provider.get_constituents(
            ConstituentQuery(symbol="半导体", scope="industry")
        )

        self.assertAlmostEqual(result.average_change_pct, (3.5 - 1.2 + 10.0 + 0.0) / 4)
        self.assertAlmostEqual(result.median_change_pct, 1.75)
        self.assertEqual(result.total_amount, 2_500_000_000 + 2_400_000_000 + 3_200_000_000 + 1_500_000_000)

    def test_industry_constituents_sorting(self) -> None:
        # Default sort by change_pct desc
        result = self.provider.get_constituents(
            ConstituentQuery(symbol="半导体", scope="industry", sort_by="change_pct")
        )
        changes = [c.change_pct for c in result.constituents]
        self.assertEqual(changes, [10.0, 3.5, 0.0, -1.2, None])

    def test_industry_constituents_sort_by_amount(self) -> None:
        result = self.provider.get_constituents(
            ConstituentQuery(symbol="半导体", scope="industry", sort_by="amount")
        )
        amounts = [c.amount for c in result.constituents if c.amount is not None]
        self.assertEqual(amounts, [3_200_000_000.0, 2_500_000_000.0, 2_400_000_000.0, 1_500_000_000.0])

    def test_industry_constituents_top_n(self) -> None:
        result = self.provider.get_constituents(
            ConstituentQuery(symbol="半导体", scope="industry", top_n=2)
        )

        self.assertEqual(len(result.constituents), 2)
        # Aggregate stats still computed from the filtered set
        self.assertEqual(result.total_count, 2)

    # -- concept --

    def test_concept_constituents(self) -> None:
        result = self.provider.get_constituents(
            ConstituentQuery(symbol="芯片", scope="concept")
        )

        self.assertEqual(result.scope, "concept")
        self.assertEqual(result.total_count, 2)
        self.assertEqual(result.up_count, 1)
        self.assertEqual(result.down_count, 1)

        self.assertEqual(self.fetcher.calls[-1][0], "concept")
        self.assertEqual(self.fetcher.calls[-1][1]["symbol"], "芯片")

    # -- index --

    def test_index_constituents_basic(self) -> None:
        result = self.provider.get_constituents(
            ConstituentQuery(symbol="000300", scope="index")
        )

        self.assertEqual(result.scope, "index")
        self.assertEqual(result.total_count, 3)
        self.assertEqual(result.constituents[0].code, "600519")
        self.assertEqual(result.constituents[0].name, "贵州茅台")
        self.assertEqual(result.constituents[2].code, "600036")

        self.assertEqual(self.fetcher.calls[-1][0], "index")
        self.assertEqual(self.fetcher.calls[-1][1]["symbol"], "000300")

    def test_index_constituents_no_price_data(self) -> None:
        result = self.provider.get_constituents(
            ConstituentQuery(symbol="000300", scope="index")
        )

        # Index constituents typically only have code/name, no price data
        for c in result.constituents:
            self.assertIsNone(c.change_pct)
            self.assertIsNone(c.amount)

        self.assertEqual(result.average_change_pct, None)
        self.assertEqual(result.total_amount, None)

    # -- error handling --

    def test_invalid_scope_raises(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported scope"):
            self.provider.get_constituents(
                ConstituentQuery(symbol="600519", scope="foobar")
            )

    def test_empty_raises(self) -> None:
        fetcher = FakeConstituentFetcher()
        fetcher.industry_rows = FrameLike([])
        provider = AStockConstituentProvider(fetcher=fetcher)

        with self.assertRaisesRegex(ProviderParseError, "no constituents"):
            provider.get_constituents(
                ConstituentQuery(symbol="不存在板块", scope="industry")
            )

    def test_fetch_error_propagates(self) -> None:
        class BrokenFetcher(FakeConstituentFetcher):
            def fetch_industry_constituents(self, *, symbol: str) -> Any:
                raise ProviderParseError("Eastmoney unreachable")

        provider = AStockConstituentProvider(fetcher=BrokenFetcher())

        with self.assertRaisesRegex(ProviderParseError, "Eastmoney"):
            provider.get_constituents(
                ConstituentQuery(symbol="半导体", scope="industry")
            )

    def test_metadata(self) -> None:
        meta = self.provider.describe()

        self.assertEqual(meta.provider_id, "astock_constituent")
        self.assertIn("astock_constituents", meta.capabilities)

    # -- unit: ConstituentList --

    def test_constituent_list_fields(self) -> None:
        cl = ConstituentList(
            symbol="test",
            name="测试",
            scope="industry",
            total_count=10,
            up_count=6,
            down_count=3,
            flat_count=1,
            total_amount=100.0,
        )

        self.assertEqual(cl.total_count, 10)
        self.assertEqual(cl.up_count, 6)


if __name__ == "__main__":
    unittest.main()
