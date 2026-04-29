from __future__ import annotations

import unittest
import os
from unittest.mock import patch

import digital_oracle.providers.astock as astock_module
from digital_oracle.providers.astock import (
    AStockBreadthQuery,
    AStockHistoryQuery,
    AStockIndexQuery,
    AStockNorthboundQuery,
    AStockProvider,
    AStockSectorBreadthQuery,
    AStockSectorHistoryQuery,
    _AkShareFetcher,
    _ensure_astock_no_proxy,
    _eastmoney_candidate_urls,
    _fetch_stock_history_baostock,
    _fetch_index_history_direct,
    _fetch_index_history_yahoo,
    _fetch_sector_history_direct,
    _fetch_sector_snapshots_direct,
    _fetch_stock_history_direct,
    _fetch_stock_history_yahoo,
    _yahoo_symbol_for_astock,
)


class FrameLike:
    def __init__(self, rows):
        self.rows = rows

    def to_dict(self, orient):
        self.orient = orient
        return self.rows


class FakeAStockFetcher:
    def __init__(self):
        self.calls = []
        self.stock_history = FrameLike(
            [
                {
                    "日期": "2026-04-20",
                    "开盘": 10.0,
                    "最高": 10.5,
                    "最低": 9.9,
                    "收盘": 10.3,
                    "成交量": 1000,
                    "成交额": 10200,
                },
                {
                    "日期": "2026-04-21",
                    "开盘": 10.3,
                    "最高": 10.8,
                    "最低": 10.2,
                    "收盘": 10.7,
                    "成交量": 2000,
                    "成交额": 21100,
                },
                {
                    "日期": "2026-04-22",
                    "开盘": 10.7,
                    "最高": 11.1,
                    "最低": 10.6,
                    "收盘": 11.0,
                    "成交量": 3000,
                    "成交额": 32600,
                },
            ]
        )
        self.index_history = [
            {
                "date": "2026-04-20",
                "open": 3000.0,
                "high": 3020.0,
                "low": 2990.0,
                "close": 3010.0,
                "volume": 123456,
            }
        ]
        self.stock_snapshots = [
            {
                "代码": "600519",
                "名称": "贵州茅台",
                "最新价": 1600.0,
                "涨跌幅": 1.5,
                "成交额": 1000000000.0,
                "换手率": 0.3,
                "市盈率-动态": 25.0,
                "市净率": 8.0,
                "总市值": 2000000000000.0,
            },
            {"代码": "300750", "名称": "宁德时代", "最新价": 200.0},
            {"代码": "688981", "名称": "中芯国际", "最新价": 50.0},
            {"代码": "920002", "名称": "万达轴承", "最新价": 80.0},
        ]
        self.stock_snapshots[0].update(
            {"change_pct": 1.5, "amount": 1_000_000_000.0, "volume": 120_000}
        )
        self.stock_snapshots[1].update(
            {"change_pct": -0.4, "amount": 2_000_000_000.0, "volume": 220_000}
        )
        self.stock_snapshots[2].update(
            {"change_pct": 10.1, "amount": 3_000_000_000.0, "volume": 320_000}
        )
        self.stock_snapshots[3].update(
            {"change_pct": 0.0, "amount": 4_000_000_000.0, "volume": 420_000}
        )
        self.sector_constituents = [
            {"code": "688981", "name": "SMIC", "change_pct": 2.0, "amount": 30_000_000},
            {"code": "688012", "name": "AMEC", "change_pct": -1.0, "amount": 20_000_000},
            {"code": "603501", "name": "Will", "change_pct": 10.2, "amount": 10_000_000},
        ]
        self.sector_snapshots = [
            {
                "板块代码": "BK0475",
                "板块名称": "银行",
                "最新价": 1200.0,
                "涨跌幅": 0.7,
                "成交额": 4560000000.0,
                "换手率": 0.8,
                "上涨家数": 30,
            }
        ]
        self.sector_snapshots[0].update({"change_pct": 0.7, "amount": 4_560_000_000.0})
        self.sector_history = [
            {
                "日期": "2026-04-21",
                "开盘": 1000.0,
                "最高": 1025.0,
                "最低": 995.0,
                "收盘": 1020.0,
                "成交量": 9999,
            }
        ]
        self.northbound = [
            {
                "日期": "2026-04-21",
                "当日成交净买额": 12.5,
                "买入成交额": 120.0,
                "卖出成交额": 107.5,
                "历史累计净买额": 18000.0,
                "沪深300涨跌幅": 0.9,
            },
            {
                "日期": "2026-04-22",
                "当日成交净买额": -3.2,
                "买入成交额": 98.0,
                "卖出成交额": 101.2,
                "历史累计净买额": 17996.8,
                "沪深300涨跌幅": -0.2,
            },
        ]

    def fetch_stock_history(self, **kwargs):
        self.calls.append(("stock_history", kwargs))
        return self.stock_history

    def fetch_index_history(self, **kwargs):
        self.calls.append(("index_history", kwargs))
        return self.index_history

    def fetch_stock_snapshots(self):
        self.calls.append(("stock_snapshots", {}))
        return self.stock_snapshots

    def fetch_sector_snapshots(self):
        self.calls.append(("sector_snapshots", {}))
        return self.sector_snapshots

    def fetch_sector_constituents(self, **kwargs):
        self.calls.append(("sector_constituents", kwargs))
        return self.sector_constituents

    def fetch_sector_history(self, **kwargs):
        self.calls.append(("sector_history", kwargs))
        return self.sector_history

    def fetch_northbound_flow(self, **kwargs):
        self.calls.append(("northbound", kwargs))
        return self.northbound


class AStockProviderTests(unittest.TestCase):
    def setUp(self):
        self.fetcher = FakeAStockFetcher()
        self.provider = AStockProvider(fetcher=self.fetcher)

    def test_akshare_missing_error_is_clear(self):
        with patch.object(
            astock_module.importlib,
            "import_module",
            side_effect=ImportError(),
        ):
            with self.assertRaisesRegex(ImportError, "uv pip install akshare"):
                _AkShareFetcher()

    def test_astock_endpoints_bypass_dead_proxy_env(self):
        with patch.dict(
            os.environ,
            {
                "HTTP_PROXY": "http://127.0.0.1:9",
                "HTTPS_PROXY": "http://127.0.0.1:9",
                "NO_PROXY": "localhost,127.0.0.1",
            },
            clear=False,
        ):
            _ensure_astock_no_proxy()

            no_proxy = os.environ["NO_PROXY"]
            self.assertIn("localhost", no_proxy)
            self.assertIn("eastmoney.com", no_proxy)
            self.assertIn(".eastmoney.com", no_proxy)
            self.assertEqual(os.environ["no_proxy"], no_proxy)

    def test_explicit_astock_proxy_configures_akshare_env(self):
        with patch.dict(
            os.environ,
            {
                "DIGITAL_ORACLE_ASTOCK_PROXY": "http://127.0.0.1:7890",
                "NO_PROXY": "localhost,127.0.0.1",
            },
            clear=False,
        ):
            with patch.object(astock_module.importlib, "import_module", return_value=object()):
                _AkShareFetcher()

            self.assertEqual(os.environ["HTTP_PROXY"], "http://127.0.0.1:7890")
            self.assertEqual(os.environ["HTTPS_PROXY"], "http://127.0.0.1:7890")
            self.assertNotIn("NO_PROXY", os.environ)

    def test_explicit_proxy_ignores_no_proxy_during_eastmoney_request(self):
        captured_no_proxy = []

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return b'{"data": {}}'

        class FakeOpener:
            def open(self, request, timeout):
                captured_no_proxy.append(os.environ.get("NO_PROXY"))
                return FakeResponse()

        with patch.dict(
            os.environ,
            {
                "DIGITAL_ORACLE_ASTOCK_PROXY": "http://127.0.0.1:7890",
                "NO_PROXY": "eastmoney.com",
            },
            clear=False,
        ):
            with patch.object(astock_module.importlib, "import_module", side_effect=ImportError):
                build_patch = patch.object(astock_module, "build_opener", return_value=FakeOpener())
                with build_patch:
                    data = astock_module._eastmoney_get_json(
                        "https://push2.eastmoney.com/api/qt/clist/get",
                        {"pn": "1"},
                    )

            self.assertEqual(data["data"], {})
            self.assertEqual(data["_source"], "eastmoney_urllib")
            self.assertEqual(captured_no_proxy, [None])
            self.assertEqual(os.environ["NO_PROXY"], "eastmoney.com")

    def test_eastmoney_get_json_prefers_curl_cffi_when_available(self):
        calls = []

        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {"data": {"ok": True}}

        class FakeCurlRequests:
            class Session:
                def __init__(self, **kwargs):
                    self.kwargs = kwargs

                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, tb):
                    return False

                def get(self, url, **kwargs):
                    calls.append((url, kwargs, self.kwargs))
                    return FakeResponse()

            @staticmethod
            def get(url, **kwargs):
                calls.append((url, kwargs))
                return FakeResponse()

        with patch.object(
            astock_module.importlib,
            "import_module",
            return_value=FakeCurlRequests,
        ):
            data = astock_module._eastmoney_get_json(
                "https://push2.eastmoney.com/api/qt/clist/get",
                {"pn": "1"},
            )

        self.assertEqual(data["data"], {"ok": True})
        self.assertEqual(data["_source"], "eastmoney_curl_cffi")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1]["impersonate"], "chrome")
        self.assertEqual(calls[0][2]["trust_env"], False)

    def test_fetcher_prefers_eastmoney_client_before_akshare(self):
        class FakeAk:
            def __init__(self):
                self.calls = 0

            def stock_zh_a_hist(self, **kwargs):
                self.calls += 1
                raise AssertionError("AkShare should not be called when Eastmoney succeeds")

        fake_ak = FakeAk()
        with patch.object(astock_module.importlib, "import_module", return_value=fake_ak):
            fetcher = _AkShareFetcher()

        with patch.object(
            astock_module,
            "_fetch_stock_history_direct",
            return_value=[{"date": "2026-04-24", "close": "10", "_source": "eastmoney_curl_cffi"}],
        ):
            rows = fetcher.fetch_stock_history(
                symbol="600519",
                period="daily",
                start_date=None,
                end_date=None,
                adjust="",
            )

        self.assertEqual(rows[0]["_source"], "eastmoney_curl_cffi")
        self.assertEqual(fake_ak.calls, 0)

    def test_fetcher_skips_akshare_eastmoney_after_direct_history_failure(self):
        class FakeAk:
            def stock_zh_a_hist(self, **kwargs):
                raise AssertionError("AkShare Eastmoney history should be skipped")

        def fake_import(name):
            if name == "akshare":
                return FakeAk()
            raise ImportError(name)

        with patch.object(astock_module.importlib, "import_module", side_effect=fake_import):
            fetcher = _AkShareFetcher()

            with patch.object(
                astock_module,
                "_fetch_stock_history_direct",
                side_effect=astock_module.ProviderParseError("eastmoney failed"),
            ):
                with patch.object(
                    astock_module,
                    "_fetch_stock_history_baostock",
                    return_value=[{"date": "2026-04-24", "close": "10", "_source": "baostock"}],
                ):
                    rows = fetcher.fetch_stock_history(
                        symbol="600519",
                        period="daily",
                        start_date=None,
                        end_date=None,
                        adjust="",
                    )

        self.assertEqual(rows[0]["_source"], "baostock")

    def test_fetcher_uses_akshare_stock_snapshot_after_direct_failure(self):
        class FakeEastmoney:
            @staticmethod
            def fetch_stock_snapshots():
                raise astock_module.ProviderParseError("eastmoney failed")

        class FakeAk:
            @staticmethod
            def stock_zh_a_spot_em():
                return [{"code": "600519", "name": "Kweichow Moutai"}]

        fetcher = object.__new__(_AkShareFetcher)
        fetcher._eastmoney = FakeEastmoney()
        fetcher._ak = FakeAk()

        rows = fetcher.fetch_stock_snapshots()

        self.assertEqual(rows[0]["_source"], "stock_zh_a_spot_em")
        self.assertEqual(rows[0]["code"], "600519")

    def test_fetcher_uses_sina_full_market_snapshot_after_eastmoney_failures(self):
        class FakeEastmoney:
            @staticmethod
            def fetch_stock_snapshots():
                raise astock_module.ProviderParseError("eastmoney failed")

        class FakeAk:
            @staticmethod
            def stock_zh_a_spot_em():
                raise astock_module.ProviderParseError("akshare eastmoney failed")

            @staticmethod
            def stock_zh_a_spot():
                return [
                    {
                        "代码": "600519",
                        "名称": "贵州茅台",
                        "最新价": 1405.0,
                        "涨跌幅": 1.2,
                        "成交量": 12345,
                        "成交额": 67890,
                    }
                ]

        fetcher = object.__new__(_AkShareFetcher)
        fetcher._eastmoney = FakeEastmoney()
        fetcher._ak = FakeAk()

        rows = fetcher.fetch_stock_snapshots()

        self.assertEqual(rows[0]["_source"], "stock_zh_a_spot_sina")
        self.assertEqual(rows[0]["code"], "600519")
        self.assertEqual(rows[0]["change_pct"], 1.2)

    def test_fetcher_uses_yahoo_after_direct_and_baostock_fail(self):
        class FakeFrame:
            empty = False

            def iterrows(self):
                return iter(
                    [
                        (
                            "2026-04-24",
                            {
                                "Open": 10.0,
                                "High": 11.0,
                                "Low": 9.0,
                                "Close": 10.5,
                                "Volume": 1000,
                            },
                        )
                    ]
                )

        class FakeYFinance:
            @staticmethod
            def set_tz_cache_location(path):
                return None

            @staticmethod
            def Ticker(ticker):
                class Ticker:
                    def history(self, **kwargs):
                        return FakeFrame()

                return Ticker()

        class FakeAk:
            pass

        def fake_import(name):
            if name == "akshare":
                return FakeAk()
            if name == "yfinance":
                return FakeYFinance
            raise ImportError(name)

        with patch.object(astock_module.importlib, "import_module", side_effect=fake_import):
            fetcher = _AkShareFetcher()

            with patch.object(
                astock_module,
                "_fetch_stock_history_direct",
                side_effect=astock_module.ProviderParseError("eastmoney failed"),
            ):
                with patch.object(
                    astock_module,
                    "_fetch_stock_history_baostock",
                    side_effect=astock_module.ProviderParseError("baostock failed"),
                ):
                    rows = fetcher.fetch_stock_history(
                        symbol="600519",
                        period="daily",
                        start_date=None,
                        end_date=None,
                        adjust="",
                    )

        self.assertEqual(rows[0]["_source"], "yahoo_finance")

    def test_eastmoney_candidate_urls_include_alternate_hosts(self):
        urls = _eastmoney_candidate_urls("https://push2.eastmoney.com/api/qt/clist/get")

        self.assertIn("https://push2.eastmoney.com/api/qt/clist/get", urls)
        self.assertIn("https://82.push2.eastmoney.com/api/qt/clist/get", urls)

    def test_direct_stock_history_fallback_parses_eastmoney_klines(self):
        def fake_get_json(url, params):
            self.assertIn("stock/kline/get", url)
            self.assertEqual(params["secid"], "0.300750")
            return {
                "data": {
                    "klines": [
                        "2026-04-24,210.0,215.5,216.0,209.8,12345,266600000,2.1,1.4,3.0,1.2"
                    ]
                }
            }

        with patch.object(astock_module, "_eastmoney_get_json", side_effect=fake_get_json):
            rows = _fetch_stock_history_direct(
                symbol="300750",
                period="daily",
                start_date=None,
                end_date=None,
                adjust="",
            )

        self.assertEqual(rows[0]["date"], "2026-04-24")
        self.assertEqual(rows[0]["close"], "215.5")
        self.assertEqual(rows[0]["volume"], "12345")
        self.assertEqual(rows[0]["_source"], "eastmoney_direct")

    def test_direct_index_history_fallback_parses_eastmoney_klines(self):
        def fake_get_json(url, params):
            self.assertIn("stock/kline/get", url)
            self.assertEqual(params["secid"], "1.000001")
            self.assertEqual(params["lmt"], "5")
            return {
                "data": {
                    "klines": [
                        "2026-04-24,3000.0,3010.5,3020.0,2990.0,12345,266600000,2.1,1.4,3.0,1.2"
                    ]
                }
            }

        with patch.object(astock_module, "_eastmoney_get_json", side_effect=fake_get_json):
            rows = _fetch_index_history_direct(
                symbol="sh000001",
                start_date=None,
                end_date=None,
                limit=5,
            )

        self.assertEqual(rows[0]["date"], "2026-04-24")
        self.assertEqual(rows[0]["close"], "3010.5")
        self.assertEqual(rows[0]["_source"], "eastmoney_direct")

    def test_astock_etf_symbol_maps_to_shenzhen_for_fallbacks(self):
        self.assertEqual(astock_module._baostock_symbol("159813"), "sz.159813")
        self.assertEqual(_yahoo_symbol_for_astock("159813"), "159813.SZ")

    def test_baostock_stock_history_fallback_maps_rows(self):
        calls = []

        class FakeLogin:
            error_code = "0"
            error_msg = ""

        class FakeResult:
            error_code = "0"
            error_msg = ""
            fields = [
                "date",
                "code",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "amount",
                "turn",
                "pctChg",
            ]

            def __init__(self):
                self.rows = [
                    ["2026-04-23", "sh.600519", "10", "11", "9", "10.5", "100", "1050", "0.1", "1.0"],
                    ["2026-04-24", "sh.600519", "11", "12", "10", "11.5", "200", "2300", "0.2", "2.0"],
                ]
                self.index = -1

            def next(self):
                self.index += 1
                return self.index < len(self.rows)

            def get_row_data(self):
                return self.rows[self.index]

        class FakeBaoStock:
            @staticmethod
            def login():
                calls.append(("login",))
                return FakeLogin()

            @staticmethod
            def logout():
                calls.append(("logout",))

            @staticmethod
            def query_history_k_data_plus(code, fields, **kwargs):
                calls.append(("query", code, fields, kwargs))
                return FakeResult()

        with patch.object(astock_module.importlib, "import_module", return_value=FakeBaoStock):
            rows = _fetch_stock_history_baostock(
                symbol="600519",
                period="daily",
                start_date="20260420",
                end_date="20260427",
                adjust="",
                limit=1,
            )

        self.assertEqual(rows[0]["date"], "2026-04-24")
        self.assertEqual(rows[0]["close"], "11.5")
        self.assertEqual(rows[0]["_source"], "baostock")
        self.assertEqual(calls[1][1], "sh.600519")
        self.assertEqual(calls[1][3]["start_date"], "2026-04-20")
        self.assertEqual(calls[1][3]["adjustflag"], "3")

    def test_yahoo_stock_history_fallback_maps_astock_symbol(self):
        class FakeFrame:
            empty = False

            def iterrows(self):
                return iter(
                    [
                        (
                            "2026-04-24 00:00:00+08:00",
                            {
                                "Open": 100.0,
                                "High": 110.0,
                                "Low": 99.0,
                                "Close": 108.0,
                                "Volume": 123456,
                            },
                        )
                    ]
                )

        class FakeTicker:
            def __init__(self, ticker):
                self.ticker = ticker

            def history(self, **kwargs):
                self.kwargs = kwargs
                return FakeFrame()

        created = []

        class FakeYFinance:
            @staticmethod
            def set_tz_cache_location(path):
                created.append(("cache", path))

            @staticmethod
            def Ticker(ticker):
                created.append(("ticker", ticker))
                return FakeTicker(ticker)

        with patch.object(astock_module.importlib, "import_module", return_value=FakeYFinance):
            rows = _fetch_stock_history_yahoo(
                symbol="688981",
                period="daily",
                start_date="20260420",
                end_date="20260427",
            )

        self.assertIn(("ticker", "688981.SS"), created)
        self.assertEqual(rows[0]["date"], "2026-04-24")
        self.assertEqual(rows[0]["close"], 108.0)
        self.assertEqual(rows[0]["_source"], "yahoo_finance")

    def test_yahoo_index_history_fallback_maps_astock_index_symbol(self):
        class FakeFrame:
            empty = False

            def iterrows(self):
                return iter(
                    [
                        (
                            "2026-04-24 00:00:00+08:00",
                            {
                                "Open": 3000.0,
                                "High": 3020.0,
                                "Low": 2990.0,
                                "Close": 3010.0,
                                "Volume": 123456,
                            },
                        )
                    ]
                )

        class FakeTicker:
            def __init__(self, ticker):
                self.ticker = ticker

            def history(self, **kwargs):
                self.kwargs = kwargs
                return FakeFrame()

        created = []

        class FakeYFinance:
            @staticmethod
            def Ticker(ticker):
                created.append(("ticker", ticker))
                return FakeTicker(ticker)

        with patch.object(astock_module.importlib, "import_module", return_value=FakeYFinance):
            rows = _fetch_index_history_yahoo(
                symbol="sh000300",
                start_date="20260420",
                end_date="20260427",
            )

        self.assertIn(("ticker", "000300.SS"), created)
        self.assertEqual(rows[0]["close"], 3010.0)
        self.assertEqual(rows[0]["_source"], "yahoo_finance")

    def test_direct_sector_snapshot_fallback_parses_eastmoney_diff(self):
        with patch.object(
            astock_module,
            "_eastmoney_get_json",
            return_value={
                "data": {
                    "diff": [
                        {
                            "f12": "BK1036",
                            "f14": "半导体",
                            "f2": 1000,
                            "f3": 2.3,
                            "f4": 22,
                            "f6": 123000000,
                            "f8": 1.8,
                            "f20": 999000000,
                        }
                    ]
                }
            },
        ):
            rows = _fetch_sector_snapshots_direct()

        self.assertEqual(rows[0]["code"], "BK1036")
        self.assertEqual(rows[0]["name"], "半导体")
        self.assertEqual(rows[0]["change_pct"], 2.3)

    def test_direct_sector_history_fallback_maps_name_to_code(self):
        def fake_get_json(url, params):
            if "clist/get" in url:
                return {"data": {"diff": [{"f12": "BK1036", "f14": "半导体"}]}}
            return {
                "data": {
                    "klines": [
                        "2026-04-24,1000,1010,1020,990,8888,90000000,3,1,10,2"
                    ]
                }
            }

        with patch.object(astock_module, "_eastmoney_get_json", side_effect=fake_get_json):
            rows = _fetch_sector_history_direct(
                symbol="半导体",
                period="daily",
                start_date=None,
                end_date=None,
                adjust="",
            )

        self.assertEqual(rows[0]["date"], "2026-04-24")
        self.assertEqual(rows[0]["close"], "1010")

    def test_get_history_maps_chinese_columns_and_filters(self):
        history = self.provider.get_history(
            AStockHistoryQuery(
                symbol="sh600519",
                start_date="2026-04-20",
                end_date="2026-04-22",
                limit=2,
            )
        )

        self.assertEqual(history.symbol, "600519")
        self.assertEqual(history.raw_symbol, "sh600519")
        self.assertEqual(history.provider_id, "astock")
        self.assertEqual([bar.date for bar in history.bars], ["2026-04-21", "2026-04-22"])
        self.assertEqual(history.bars[-1].close, 11.0)
        self.assertEqual(history.bars[-1].volume, 3000.0)
        self.assertEqual(history.metadata["source"], "stock_zh_a_hist")
        _, kwargs = self.fetcher.calls[0]
        self.assertEqual(kwargs["symbol"], "600519")
        self.assertEqual(kwargs["period"], "daily")
        self.assertEqual(kwargs["start_date"], "20260420")

    def test_accepts_non_mainboard_history_by_default(self):
        history = self.provider.get_history(AStockHistoryQuery(symbol="300750", limit=1))

        self.assertEqual(history.symbol, "300750")

    def test_can_reject_non_mainboard_history_when_requested(self):
        with self.assertRaisesRegex(ValueError, "mainboard"):
            self.provider.get_history(AStockHistoryQuery(symbol="300750", mainboard_only=True))

    def test_list_stock_snapshots_includes_all_boards_by_default(self):
        snapshots = self.provider.list_stock_snapshots()

        self.assertEqual([snapshot.code for snapshot in snapshots], ["600519", "300750", "688981", "920002"])
        self.assertEqual(snapshots[0].name, "贵州茅台")
        self.assertEqual(snapshots[0].change_pct, 1.5)
        self.assertEqual(snapshots[0].pe_dynamic, 25.0)

    def test_list_stock_snapshots_can_filter_to_mainboard(self):
        snapshots = self.provider.list_stock_snapshots(mainboard_only=True)

        self.assertEqual([snapshot.code for snapshot in snapshots], ["600519"])

    def test_market_breadth_summarizes_all_a_share_snapshots(self):
        breadth = self.provider.get_market_breadth(AStockBreadthQuery())

        self.assertEqual(breadth.scope, "market")
        self.assertEqual(breadth.name, "全A")
        self.assertEqual(breadth.total_count, 4)
        self.assertEqual(breadth.up_count, 2)
        self.assertEqual(breadth.down_count, 1)
        self.assertEqual(breadth.flat_count, 1)
        self.assertEqual(breadth.limit_up_count, 1)
        self.assertEqual(breadth.limit_down_count, 0)
        self.assertEqual(breadth.total_amount, 10_000_000_000.0)
        self.assertEqual(breadth.total_volume, 1_080_000.0)
        self.assertEqual(breadth.metadata["source"], "stock_zh_a_spot_em")

    def test_market_breadth_can_filter_to_mainboard(self):
        breadth = self.provider.get_market_breadth(AStockBreadthQuery(mainboard_only=True))

        self.assertEqual(breadth.total_count, 1)
        self.assertEqual(breadth.up_count, 1)
        self.assertEqual(breadth.total_amount, 1_000_000_000.0)

    def test_market_breadth_falls_back_to_sector_proxy(self):
        class SectorProxyFetcher(FakeAStockFetcher):
            def fetch_stock_snapshots(self):
                raise astock_module.ProviderParseError("stock snapshots unavailable")

        fetcher = SectorProxyFetcher()
        provider = AStockProvider(fetcher=fetcher)

        breadth = provider.get_market_breadth(AStockBreadthQuery())

        self.assertEqual(breadth.scope, "market_sector_proxy")
        self.assertEqual(breadth.total_count, 1)
        self.assertEqual(breadth.up_count, 1)
        self.assertEqual(breadth.total_amount, 4_560_000_000.0)
        self.assertEqual(breadth.metadata["breadth_level"], "sector_proxy")
        self.assertIn("proxy_reason", breadth.metadata)

    def test_sector_breadth_summarizes_constituents(self):
        breadth = self.provider.get_sector_breadth(AStockSectorBreadthQuery(symbol="半导体"))

        self.assertEqual(breadth.scope, "sector")
        self.assertEqual(breadth.symbol, "半导体")
        self.assertEqual(breadth.total_count, 3)
        self.assertEqual(breadth.up_count, 2)
        self.assertEqual(breadth.down_count, 1)
        self.assertEqual(breadth.limit_up_count, 1)
        self.assertEqual(breadth.total_amount, 60_000_000.0)
        self.assertEqual(self.fetcher.calls[-1][0], "sector_constituents")

    def test_sector_breadth_falls_back_to_sector_snapshot_proxy(self):
        class SectorSnapshotProxyFetcher(FakeAStockFetcher):
            def __init__(self):
                super().__init__()
                self.sector_snapshots = [
                    {
                        "code": "BK1036",
                        "name": "半导体",
                        "change_pct": 1.2,
                        "amount": 9_000_000_000.0,
                    }
                ]

            def fetch_sector_constituents(self, **kwargs):
                raise astock_module.ProviderParseError("constituents unavailable")

        fetcher = SectorSnapshotProxyFetcher()
        provider = AStockProvider(fetcher=fetcher)

        breadth = provider.get_sector_breadth(AStockSectorBreadthQuery(symbol="半导体"))

        self.assertEqual(breadth.scope, "sector_snapshot_proxy")
        self.assertEqual(breadth.total_count, 1)
        self.assertEqual(breadth.up_count, 1)
        self.assertEqual(breadth.total_amount, 9_000_000_000.0)
        self.assertEqual(breadth.metadata["breadth_level"], "sector_snapshot_proxy")

    def test_sector_breadth_snapshot_proxy_uses_semiconductor_aliases(self):
        class SectorAliasFetcher(FakeAStockFetcher):
            def __init__(self):
                super().__init__()
                self.sector_snapshots = [
                    {"code": "new_dzqj", "name": "电子器件", "change_pct": 2.0, "amount": 7.0},
                    {"code": "new_dzxx", "name": "电子信息", "change_pct": -1.0, "amount": 3.0},
                    {"code": "new_fdc", "name": "房地产", "change_pct": 5.0, "amount": 99.0},
                ]

            def fetch_sector_constituents(self, **kwargs):
                raise astock_module.ProviderParseError("constituents unavailable")

        provider = AStockProvider(fetcher=SectorAliasFetcher())

        breadth = provider.get_sector_breadth(AStockSectorBreadthQuery(symbol="半导体"))

        self.assertEqual(breadth.total_count, 2)
        self.assertEqual(breadth.up_count, 1)
        self.assertEqual(breadth.down_count, 1)
        self.assertEqual(breadth.total_amount, 10.0)

    def test_index_history_maps_english_columns(self):
        history = self.provider.get_index_history(AStockIndexQuery(symbol="sh000001", limit=1))

        self.assertEqual(history.symbol, "sh000001")
        self.assertEqual(history.bars[0].close, 3010.0)
        self.assertEqual(history.bars[0].volume, 123456.0)

    def test_sector_snapshot_and_history(self):
        snapshots = self.provider.list_sector_snapshots()
        history = self.provider.get_sector_history(AStockSectorHistoryQuery(symbol="银行", limit=1))

        self.assertEqual(snapshots[0].code, "BK0475")
        self.assertEqual(snapshots[0].name, "银行")
        self.assertEqual(snapshots[0].amount, 4560000000.0)
        self.assertEqual(snapshots[0].metadata["source"], "stock_board_industry_name_em")
        self.assertEqual(history.symbol, "银行")
        self.assertEqual(history.bars[0].close, 1020.0)

    def test_sector_history_parses_ths_columns(self):
        fetcher = FakeAStockFetcher()
        fetcher.sector_history = [
            {
                "日期": "2026-04-24",
                "开盘价": 1000.0,
                "最高价": 1020.0,
                "最低价": 990.0,
                "收盘价": 1010.0,
                "成交量": 8888,
            }
        ]
        provider = AStockProvider(fetcher=fetcher)

        history = provider.get_sector_history(AStockSectorHistoryQuery(symbol="半导体", limit=1))

        self.assertEqual(history.bars[0].close, 1010.0)
        self.assertEqual(history.bars[0].volume, 8888.0)

    def test_sector_snapshot_parses_stock_sector_spot_columns(self):
        snapshot = astock_module._parse_snapshot(
            {
                "label": "new_bdt",
                "板块": "半导体",
                "平均价格": 20.5,
                "涨跌幅": 1.2,
                "涨跌额": 0.3,
                "总成交量": 123456,
                "总成交额": 987654321,
            },
            source="stock_sector_spot",
        )

        self.assertEqual(snapshot.code, "new_bdt")
        self.assertEqual(snapshot.name, "半导体")
        self.assertEqual(snapshot.latest, 20.5)
        self.assertEqual(snapshot.amount, 987654321.0)
        self.assertEqual(snapshot.metadata["source"], "stock_sector_spot")

    def test_tagged_price_rows_override_default_source(self):
        fetcher = FakeAStockFetcher()
        fetcher.stock_history = [
            {
                "日期": "2026-04-24",
                "开盘": 100.0,
                "最高": 110.0,
                "最低": 99.0,
                "收盘": 108.0,
                "_source": "yahoo_finance",
            }
        ]
        provider = AStockProvider(fetcher=fetcher)

        history = provider.get_history(AStockHistoryQuery(symbol="600519", limit=1))

        self.assertEqual(history.metadata["source"], "yahoo_finance")

    def test_northbound_flow_limit_and_parse(self):
        flows = self.provider.get_northbound_flow(AStockNorthboundQuery(limit=1))

        self.assertEqual(len(flows), 1)
        self.assertEqual(flows[0].date, "2026-04-22")
        self.assertEqual(flows[0].net_buy_amount, -3.2)
        self.assertEqual(flows[0].cumulative_net_buy_amount, 17996.8)

    def test_northbound_flow_limit_keyword(self):
        flows = self.provider.get_northbound_flow(limit=1)

        self.assertEqual(len(flows), 1)
        self.assertEqual(flows[0].date, "2026-04-22")

    def test_metadata(self):
        meta = self.provider.describe()

        self.assertEqual(meta.provider_id, "astock")
        self.assertIn("astock_sectors", meta.capabilities)


if __name__ == "__main__":
    unittest.main()
