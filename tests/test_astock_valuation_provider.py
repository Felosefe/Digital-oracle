from __future__ import annotations

import unittest
from typing import Any, Mapping

from digital_oracle.providers.astock_valuation import (
    AStockValuationProvider,
    FinancialQuery,
    ValuationQuery,
)
from digital_oracle.providers.base import ProviderParseError

SAMPLE_PE_ROWS = [
    {
        "日期": "2026-04-25",
        "指数": 4750.0,
        "动态市盈率": 13.80,
        "动态市盈率分位": 20.50,
        "静态市盈率": 13.70,
        "静态市盈率分位": 21.00,
        "加权动态市盈率": 36.50,
    },
    {
        "日期": "2026-04-28",
        "指数": 4760.0,
        "动态市盈率": 13.95,
        "动态市盈率分位": 21.55,
        "静态市盈率": 13.81,
        "静态市盈率分位": 21.13,
        "加权动态市盈率": 36.80,
    },
    {
        "日期": "2026-04-29",
        "指数": 4810.35,
        "动态市盈率": 14.10,
        "动态市盈率分位": 22.36,
        "静态市盈率": 13.90,
        "静态市盈率分位": 21.22,
        "加权动态市盈率": 36.81,
    },
]

SAMPLE_PB_ROWS = [
    {"日期": "2026-04-25", "指数": 4750.0, "市净率": 1.46, "加权市净率": 3.88, "市净率分位": 2.30},
    {"日期": "2026-04-28", "指数": 4760.0, "市净率": 1.47, "加权市净率": 3.89, "市净率分位": 2.40},
    {"日期": "2026-04-29", "指数": 4810.35, "市净率": 1.47, "加权市净率": 3.92, "市净率分位": 2.40},
]

SAMPLE_FINANCIAL_ROWS = [
    {
        "日期": "2025-12-31",
        "基本每股收益(元)": 68.50,
        "净资产收益率(%)": 30.10,
        "主营业务收入增长率(%)": 15.80,
        "净利润增长率(%)": 14.20,
        "销售毛利率(%)": 79.50,
        "销售净利率(%)": 52.30,
        "资产负债率(%)": 12.10,
        "流动比率": 7.06,
        "速动比率": 5.48,
        "每股净资产_调整后(元)": 224.50,
        "每股经营现金流(元)": 21.49,
        "总资产(元)": 319918844905.58,
    },
    {
        "日期": "2026-03-31",
        "基本每股收益(元)": 22.48,
        "净资产收益率(%)": 8.80,
        "主营业务收入增长率(%)": 6.54,
        "净利润增长率(%)": 1.37,
        "销售毛利率(%)": 80.10,
        "销售净利率(%)": 52.22,
        "资产负债率(%)": 12.12,
        "流动比率": 7.06,
        "速动比率": 5.48,
        "每股净资产_调整后(元)": 224.50,
        "每股经营现金流(元)": 21.49,
        "总资产(元)": 319918844905.58,
    },
]


class FrameLike:
    def __init__(self, rows: list[Mapping[str, Any]]) -> None:
        self.rows = rows

    def to_dict(self, orient: str) -> list[Mapping[str, Any]]:
        return self.rows


class FakeValuationFetcher:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.pe_data: Any = FrameLike(SAMPLE_PE_ROWS)
        self.pb_data: Any = FrameLike(SAMPLE_PB_ROWS)
        self.fin_data: Any = FrameLike(SAMPLE_FINANCIAL_ROWS)

    def fetch_index_pe(self, *, symbol: str) -> Any:
        self.calls.append(("pe", {"symbol": symbol}))
        return self.pe_data

    def fetch_index_pb(self, *, symbol: str) -> Any:
        self.calls.append(("pb", {"symbol": symbol}))
        return self.pb_data

    def fetch_financial_indicators(self, *, symbol: str, start_year: str) -> Any:
        self.calls.append(("fin", {"symbol": symbol, "start_year": start_year}))
        return self.fin_data


class AStockValuationProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fetcher = FakeValuationFetcher()
        self.provider = AStockValuationProvider(fetcher=self.fetcher)

    # -- index valuation --

    def test_index_valuation_combined(self) -> None:
        result = self.provider.get_index_valuation(ValuationQuery(lookback_days=2))

        self.assertEqual(result.symbol, "沪深300")
        self.assertEqual(result.latest_date, "2026-04-29")
        self.assertAlmostEqual(result.latest_pe, 14.10)
        self.assertAlmostEqual(result.latest_pe_percentile, 22.36)
        self.assertAlmostEqual(result.latest_pb, 1.47)
        self.assertAlmostEqual(result.latest_pb_percentile, 2.40)
        self.assertAlmostEqual(result.latest_index_level, 4810.35)

    def test_index_valuation_history(self) -> None:
        result = self.provider.get_index_valuation(ValuationQuery(lookback_days=3))

        self.assertEqual(len(result.days), 3)
        self.assertEqual(result.days[0].date, "2026-04-25")
        self.assertAlmostEqual(result.days[0].pe_dynamic, 13.80)
        self.assertAlmostEqual(result.days[0].pb, 1.46)

    def test_index_valuation_custom_symbol(self) -> None:
        result = self.provider.get_index_valuation(ValuationQuery(symbol="上证50", lookback_days=1))

        self.assertEqual(result.symbol, "上证50")
        self.assertEqual(self.fetcher.calls[0], ("pe", {"symbol": "上证50"}))
        self.assertEqual(self.fetcher.calls[1], ("pb", {"symbol": "上证50"}))

    # -- financials --

    def test_financials_latest_quarter(self) -> None:
        result = self.provider.get_financials(FinancialQuery(symbol="600519", start_year="2024"))

        self.assertEqual(result.symbol, "600519")
        self.assertEqual(result.report_date, "2026-03-31")
        self.assertAlmostEqual(result.eps, 22.48)
        self.assertAlmostEqual(result.roe, 8.80)
        self.assertAlmostEqual(result.revenue_growth, 6.54)
        self.assertAlmostEqual(result.gross_margin, 80.10)
        self.assertAlmostEqual(result.net_margin, 52.22)
        self.assertAlmostEqual(result.debt_ratio, 12.12)
        self.assertAlmostEqual(result.current_ratio, 7.06)

    def test_financials_full_year(self) -> None:
        # Request start_year=2025 to get the 2025-12-31 annual report
        fetcher = FakeValuationFetcher()
        # Only return the 2025 annual
        fetcher.fin_data = FrameLike([SAMPLE_FINANCIAL_ROWS[0]])
        provider = AStockValuationProvider(fetcher=fetcher)
        result = provider.get_financials(FinancialQuery(symbol="600519", start_year="2025"))

        self.assertEqual(result.report_date, "2025-12-31")
        self.assertAlmostEqual(result.eps, 68.50)
        self.assertAlmostEqual(result.roe, 30.10)
        self.assertAlmostEqual(result.revenue_growth, 15.80)

    # -- error handling --

    def test_partial_failure_still_returns_data(self) -> None:
        """PE fails but PB succeeds → return partial result with error metadata."""
        class BrokenFetcher(FakeValuationFetcher):
            def fetch_index_pe(self, *, symbol: str) -> Any:
                raise ProviderParseError("pe network error")

        provider = AStockValuationProvider(fetcher=BrokenFetcher())
        result = provider.get_index_valuation()

        # Should still return PB data
        self.assertIsNone(result.latest_pe)
        self.assertAlmostEqual(result.latest_pb, 1.47)
        self.assertIn("pe network error", result.metadata["pe_error"])
        self.assertIsNone(result.metadata["pb_error"])

    def test_both_pe_and_pb_fail_raises(self) -> None:
        class BrokenFetcher(FakeValuationFetcher):
            def fetch_index_pe(self, *, symbol: str) -> Any:
                raise ProviderParseError("pe error")
            def fetch_index_pb(self, *, symbol: str) -> Any:
                raise ProviderParseError("pb error")

        provider = AStockValuationProvider(fetcher=BrokenFetcher())
        with self.assertRaisesRegex(ProviderParseError, "failed to fetch both"):
            provider.get_index_valuation()

    def test_financial_empty_raises(self) -> None:
        fetcher = FakeValuationFetcher()
        fetcher.fin_data = FrameLike([])
        provider = AStockValuationProvider(fetcher=fetcher)
        with self.assertRaisesRegex(ProviderParseError, "no financial data"):
            provider.get_financials(FinancialQuery(symbol="000000", start_year="2024"))

    # -- metadata --

    def test_metadata(self) -> None:
        meta = self.provider.describe()
        self.assertEqual(meta.provider_id, "astock_valuation")
        self.assertIn("astock_valuation", meta.capabilities)
        self.assertIn("astock_fundamentals", meta.capabilities)


if __name__ == "__main__":
    unittest.main()
