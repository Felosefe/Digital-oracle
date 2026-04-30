from __future__ import annotations

import unittest
from typing import Any, Mapping

from digital_oracle.providers.astock_margin import (
    AStockMarginProvider,
    MarginQuery,
    MarginDay,
    MarketMargin,
)
from digital_oracle.providers.base import ProviderParseError

SAMPLE_SH_ROWS = [
    {
        "日期": "2026-04-25",
        "融资买入额": 50000000000.0,
        "融资余额": 960000000000.0,
        "融券卖出量": 12000000.0,
        "融券余量": 50000000.0,
        "融券余额": 4200000000.0,
        "融资融券余额": 964200000000.0,
    },
    {
        "日期": "2026-04-28",
        "融资买入额": 65000000000.0,
        "融资余额": 970000000000.0,
        "融券卖出量": 10000000.0,
        "融券余量": 48000000.0,
        "融券余额": 4100000000.0,
        "融资融券余额": 974100000000.0,
    },
    {
        "日期": "2026-04-29",
        "融资买入额": 72000000000.0,
        "融资余额": 980000000000.0,
        "融券卖出量": 15000000.0,
        "融券余量": 52000000.0,
        "融券余额": 4300000000.0,
        "融资融券余额": 984300000000.0,
    },
]

SAMPLE_SZ_ROWS = [
    {
        "日期": "2026-04-25",
        "融资买入额": 68000000000.0,
        "融资余额": 1020000000000.0,
        "融券卖出量": 8000000.0,
        "融券余量": 35000000.0,
        "融券余额": 3100000000.0,
        "融资融券余额": 1023100000000.0,
    },
    {
        "日期": "2026-04-28",
        "融资买入额": 81000000000.0,
        "融资余额": 1040000000000.0,
        "融券卖出量": 7000000.0,
        "融券余额": 3000000000.0,
        "融资融券余额": 1043000000000.0,
    },
    {
        "日期": "2026-04-29",
        "融资买入额": 95000000000.0,
        "融资余额": 1060000000000.0,
        "融券卖出量": 11000000.0,
        "融券余额": 3500000000.0,
        "融资融券余额": 1063500000000.0,
    },
]


class FrameLike:
    def __init__(self, rows: list[Mapping[str, Any]]) -> None:
        self.rows = rows

    def to_dict(self, orient: str) -> list[Mapping[str, Any]]:
        return self.rows


class FakeMarginFetcher:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.sh_data: Any = FrameLike(SAMPLE_SH_ROWS)
        self.sz_data: Any = FrameLike(SAMPLE_SZ_ROWS)

    def fetch_sh_margin(self) -> Any:
        self.calls.append(("sh", {}))
        return self.sh_data

    def fetch_sz_margin(self) -> Any:
        self.calls.append(("sz", {}))
        return self.sz_data


class AStockMarginProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fetcher = FakeMarginFetcher()
        self.provider = AStockMarginProvider(fetcher=self.fetcher)

    # -- both exchanges --

    def test_both_exchanges_combined(self) -> None:
        result = self.provider.get_market_margin(MarginQuery(lookback_days=2))

        self.assertEqual(result.exchange, "both")
        self.assertEqual(result.lookback_days, 2)
        self.assertEqual(result.latest_date, "2026-04-29")

        # Combined financing balance: 980 + 1060 = 2040 billion
        self.assertAlmostEqual(result.latest_financing_balance, 2040000000000.0)
        # Combined financing buy: 72 + 95 = 167 billion
        self.assertAlmostEqual(result.latest_financing_buy, 167000000000.0)
        # Combined short balance: 4.3 + 3.5 = 7.8 billion
        self.assertAlmostEqual(result.latest_short_balance, 7800000000.0)
        # Total margin: 984.3 + 1063.5 = 2047.8 billion
        self.assertAlmostEqual(result.latest_total_balance, 2047800000000.0)

        # 2 lookback * 2 exchanges = 4 days
        self.assertEqual(len(result.days), 4)

    # -- sh only --

    def test_sh_only(self) -> None:
        result = self.provider.get_market_margin(
            MarginQuery(exchange="sh", lookback_days=2)
        )

        self.assertEqual(result.exchange, "sh")
        self.assertEqual(result.latest_date, "2026-04-29")
        self.assertAlmostEqual(result.latest_financing_balance, 980000000000.0)
        self.assertAlmostEqual(result.latest_financing_buy, 72000000000.0)

    # -- sz only --

    def test_sz_only(self) -> None:
        result = self.provider.get_market_margin(
            MarginQuery(exchange="sz", lookback_days=1)
        )

        self.assertEqual(result.exchange, "sz")
        self.assertAlmostEqual(result.latest_financing_balance, 1060000000000.0)
        self.assertAlmostEqual(result.latest_financing_buy, 95000000000.0)

    # -- lookback --

    def test_lookback_zero_returns_all(self) -> None:
        result = self.provider.get_market_margin(MarginQuery(lookback_days=0))

        self.assertEqual(len(result.days), 6)  # 3 sh + 3 sz

    def test_lookback_one(self) -> None:
        result = self.provider.get_market_margin(MarginQuery(lookback_days=1))

        self.assertEqual(len(result.days), 2)

    # -- margin day fields --

    def test_margin_day_all_fields(self) -> None:
        result = self.provider.get_market_margin(MarginQuery(exchange="sh", lookback_days=1))
        day = result.days[0]

        self.assertEqual(day.date, "2026-04-29")
        self.assertAlmostEqual(day.financing_balance, 980000000000.0)
        self.assertAlmostEqual(day.financing_buy, 72000000000.0)
        self.assertAlmostEqual(day.short_balance, 4300000000.0)
        self.assertAlmostEqual(day.short_sell, 15000000.0)
        self.assertAlmostEqual(day.short_volume, 52000000.0)
        self.assertAlmostEqual(day.total_balance, 984300000000.0)

    # -- error handling --

    def test_invalid_exchange_raises(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported exchange"):
            self.provider.get_market_margin(MarginQuery(exchange="bj"))

    def test_fetch_error_propagates(self) -> None:
        class BrokenFetcher(FakeMarginFetcher):
            def fetch_sh_margin(self) -> Any:
                raise ProviderParseError("network error")

        provider = AStockMarginProvider(fetcher=BrokenFetcher())

        with self.assertRaisesRegex(ProviderParseError, "network error"):
            provider.get_market_margin(MarginQuery(exchange="sh"))

    # -- metadata --

    def test_metadata(self) -> None:
        meta = self.provider.describe()

        self.assertEqual(meta.provider_id, "astock_margin")
        self.assertIn("astock_margin", meta.capabilities)

    # -- default query --

    def test_default_query(self) -> None:
        result = self.provider.get_market_margin()

        self.assertEqual(result.exchange, "both")
        self.assertEqual(result.lookback_days, 20)


if __name__ == "__main__":
    unittest.main()
