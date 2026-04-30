from __future__ import annotations

import unittest
from typing import Any

from digital_oracle.providers.astock_disclosure import (
    AStockDisclosureProvider,
    DisclosureQuery,
)
from digital_oracle.providers.base import ProviderParseError

SAMPLE_PAGE_1 = {
    "page_index": 1,
    "page_size": 100,
    "total_hits": 4,
    "list": [
        {
            "art_code": "AN001",
            "codes": "[{'stock_code': '600519', 'short_name': 'Kweichow Moutai'}]",
            "columns": "[{'column_name': 'Periodic Report'}]",
            "notice_date": "2026-04-30 00:00:00",
            "title_ch": "600519: Q1 2026 Report",
        },
        {
            "art_code": "AN002",
            "codes": "[{'stock_code': '600519', 'short_name': 'Kweichow Moutai'}]",
            "columns": "[{'column_name': 'Buyback'}]",
            "notice_date": "2026-04-30 00:00:00",
            "title_ch": "600519: Buyback Completion Announcement",
        },
        {
            "art_code": "AN003",
            "codes": "[{'stock_code': '300750', 'short_name': 'CATL'}]",
            "columns": "[{'column_name': 'Reduction'}]",
            "notice_date": "2026-04-30 00:00:00",
            "title_ch": "300750: Major Shareholder Reduction Plan",
        },
        {
            "art_code": "AN004",
            "codes": "[{'stock_code': '002714', 'short_name': 'Muyuan Foods'}]",
            "columns": "[{'column_name': 'Survey'}]",
            "notice_date": "2026-04-30 00:00:00",
            "title_ch": "002714: Investor Survey 20260430",
        },
    ],
}


class FakeDirectFetcher:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.page_data: Any = SAMPLE_PAGE_1

    def fetch_page(self, *, date: str, page_index: int, page_size: int = 100) -> Any:
        self.calls.append({"date": date, "page_index": page_index, "page_size": page_size})
        if page_index == 1:
            return self.page_data
        return {"total_hits": 4, "list": []}


class AStockDisclosureProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = AStockDisclosureProvider.__new__(AStockDisclosureProvider)
        self.provider._direct = FakeDirectFetcher()

    # -- list all --

    def test_list_all_notices(self) -> None:
        result = self.provider.list_notices()

        self.assertEqual(result.total_count, 4)
        self.assertEqual(len(result.notices), 4)
        self.assertIn("np-anotice-stock", result.metadata["source"])

    # -- keyword filtering --

    def test_filter_by_keyword(self) -> None:
        result = self.provider.list_notices(DisclosureQuery(keyword="Reduction"))

        self.assertEqual(len(result.notices), 1)
        self.assertEqual(result.notices[0].code, "300750")
        self.assertIsNotNone(result.notices[0].category)

    def test_filter_by_symbol(self) -> None:
        result = self.provider.list_notices(DisclosureQuery(symbol="600519"))

        self.assertEqual(len(result.notices), 2)

    # -- notice fields --

    def test_notice_all_fields(self) -> None:
        result = self.provider.list_notices(DisclosureQuery(symbol="600519", keyword="Buyback"))

        self.assertEqual(len(result.notices), 1)
        n = result.notices[0]
        self.assertEqual(n.code, "600519")
        self.assertEqual(n.name, "Kweichow Moutai")
        self.assertIn("Buyback", n.title)
        self.assertIsNotNone(n.category)
        self.assertEqual(n.date, "2026-04-30")
        self.assertIn("eastmoney.com", n.url)

    # -- top_n --

    def test_top_n(self) -> None:
        result = self.provider.list_notices(DisclosureQuery(top_n=2))
        self.assertEqual(len(result.notices), 2)

    # -- empty --

    def test_empty_result(self) -> None:
        result = self.provider.list_notices(DisclosureQuery(keyword="NONEXISTENT_KEYWORD"))
        self.assertEqual(result.total_count, 0)

    # -- error handling --

    def test_fetch_error(self) -> None:
        class BrokenDirect:
            def fetch_page(self, *, date: str, page_index: int, page_size: int = 100) -> Any:
                raise ProviderParseError("network error")

        self.provider._direct = BrokenDirect()
        with self.assertRaisesRegex(ProviderParseError, "network error"):
            self.provider.list_notices()

    # -- metadata --

    def test_metadata(self) -> None:
        meta = self.provider.describe()
        self.assertEqual(meta.provider_id, "astock_disclosure")
        self.assertIn("astock_disclosure", meta.capabilities)


if __name__ == "__main__":
    unittest.main()
