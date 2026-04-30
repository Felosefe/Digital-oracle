from __future__ import annotations

import importlib
import contextlib
import io
import json
import math
import os
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from statistics import median
from typing import Any, Mapping, Protocol
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import ProxyHandler, Request, build_opener

from .base import ProviderParseError, SignalProvider
from .prices import PriceBar, PriceHistory


_PERIOD_MAP = {
    "d": "daily",
    "daily": "daily",
    "w": "weekly",
    "weekly": "weekly",
    "m": "monthly",
    "monthly": "monthly",
}

_ASTOCK_NO_PROXY_HOSTS = (
    "eastmoney.com",
    ".eastmoney.com",
    "push2.eastmoney.com",
    "push2his.eastmoney.com",
)
_ASTOCK_PROXY_ENV = "DIGITAL_ORACLE_ASTOCK_PROXY"
_ASTOCK_PROXY_MODE_ENV = "DIGITAL_ORACLE_ASTOCK_PROXY_MODE"
_EASTMONEY_TIMEOUT_ENV = "DIGITAL_ORACLE_EASTMONEY_TIMEOUT"
_EASTMONEY_DEFAULT_TIMEOUT_SECONDS = 6.0

_EASTMONEY_HEADERS = {
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Connection": "close",
    "Referer": "https://quote.eastmoney.com/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
}

_SECTOR_PROXY_ALIASES = {
    "\u534a\u5bfc\u4f53": ("\u534a\u5bfc\u4f53", "\u7535\u5b50\u5668\u4ef6", "\u7535\u5b50\u4fe1\u606f"),
    "\u82af\u7247": ("\u534a\u5bfc\u4f53", "\u7535\u5b50\u5668\u4ef6", "\u7535\u5b50\u4fe1\u606f"),
    "\u8bc1\u5238": ("\u8bc1\u5238", "\u8bc1\u5238\u884c\u4e1a"),
    "\u767d\u9152": ("\u767d\u9152", "\u917f\u9152\u884c\u4e1a", "\u767d\u9152\u2161", "\u767d\u9152\u2162", "\u975e\u767d\u9152"),
    "\u94f6\u884c": ("\u94f6\u884c",),
    "\u533b\u836f": ("\u533b\u836f", "\u5316\u5b66\u5236\u836f", "\u4e2d\u836f", "\u751f\u7269\u5236\u54c1", "\u533b\u7597\u5668\u68b0", "\u533b\u836f\u5546\u4e1a"),
    "\u519b\u5de5": ("\u519b\u5de5", "\u56fd\u9632\u519b\u5de5", "\u519b\u5de5\u7535\u5b50"),
    "\u65b0\u80fd\u6e90": ("\u65b0\u80fd\u6e90", "\u5149\u4f0f", "\u98ce\u7535", "\u50a8\u80fd", "\u65b0\u80fd\u6e90\u6c7d\u8f66"),
}

# Real IPs for Eastmoney CDN hosts \u2014 bypass Clash fake-IP DNS (198.18.0.x).
_EASTMONEY_REAL_IPS: dict[str, tuple[str, ...]] = {
    "push2.eastmoney.com": ("120.79.191.232", "119.3.232.150", "120.76.218.228"),
    "push2his.eastmoney.com": ("120.79.191.232", "119.3.232.150"),
    "82.push2.eastmoney.com": ("120.79.191.232", "119.3.232.150"),
    "17.push2.eastmoney.com": ("120.79.191.232", "119.3.232.150"),
    "56.push2.eastmoney.com": ("120.79.191.232", "119.3.232.150"),
    "7.push2his.eastmoney.com": ("120.79.191.232", "119.3.232.150"),
    "33.push2his.eastmoney.com": ("120.79.191.232", "119.3.232.150"),
}
_EASTMONEY_HOSTS = frozenset(_EASTMONEY_REAL_IPS)
_DNS_PATCHED = False

@dataclass(frozen=True)
class AStockHistoryQuery:
    symbol: str
    start_date: str | None = None
    end_date: str | None = None
    interval: str = "d"
    adjust: str = ""
    limit: int | None = None
    mainboard_only: bool = False


@dataclass(frozen=True)
class AStockIndexQuery:
    symbol: str = "sh000001"
    start_date: str | None = None
    end_date: str | None = None
    limit: int | None = None


@dataclass(frozen=True)
class AStockSectorHistoryQuery:
    symbol: str
    start_date: str | None = None
    end_date: str | None = None
    interval: str = "d"
    adjust: str = ""
    limit: int | None = None


@dataclass(frozen=True)
class AStockNorthboundQuery:
    symbol: str = "鍖楀悜璧勯噾"
    limit: int | None = None


@dataclass(frozen=True)
class AStockBreadthQuery:
    mainboard_only: bool = False
    limit_like_threshold: float = 9.8


@dataclass(frozen=True)
class AStockSectorBreadthQuery:
    symbol: str
    limit_like_threshold: float = 9.8


@dataclass
class AStockSnapshot:
    code: str | None
    name: str
    latest: float | None = None
    change_pct: float | None = None
    change_amount: float | None = None
    volume: float | None = None
    amount: float | None = None
    turnover_rate: float | None = None
    pe_dynamic: float | None = None
    pb: float | None = None
    total_market_cap: float | None = None
    circulating_market_cap: float | None = None
    metadata: dict[str, object] = field(default_factory=dict, repr=False)


@dataclass
class AStockNorthboundFlow:
    date: str
    net_buy_amount: float | None = None
    buy_amount: float | None = None
    sell_amount: float | None = None
    cumulative_net_buy_amount: float | None = None
    hs300_change_pct: float | None = None
    metadata: dict[str, object] = field(default_factory=dict, repr=False)


@dataclass
class AStockBreadthSnapshot:
    scope: str
    symbol: str | None = None
    name: str | None = None
    total_count: int = 0
    up_count: int = 0
    down_count: int = 0
    flat_count: int = 0
    limit_up_count: int = 0
    limit_down_count: int = 0
    total_amount: float | None = None
    total_volume: float | None = None
    average_change_pct: float | None = None
    median_change_pct: float | None = None
    metadata: dict[str, object] = field(default_factory=dict, repr=False)


class AStockFetcher(Protocol):
    def fetch_stock_history(
        self,
        *,
        symbol: str,
        period: str,
        start_date: str | None,
        end_date: str | None,
        adjust: str,
        limit: int | None = None,
    ) -> Any: ...

    def fetch_index_history(
        self,
        *,
        symbol: str,
        start_date: str | None,
        end_date: str | None,
        limit: int | None = None,
    ) -> Any: ...

    def fetch_stock_snapshots(self) -> Any: ...

    def fetch_sector_snapshots(self) -> Any: ...

    def fetch_sector_constituents(self, *, symbol: str) -> Any: ...

    def fetch_sector_history(
        self,
        *,
        symbol: str,
        period: str,
        start_date: str | None,
        end_date: str | None,
        adjust: str,
        limit: int | None = None,
    ) -> Any: ...

    def fetch_northbound_flow(self, *, symbol: str) -> Any: ...


class _EastmoneyClient:
    def fetch_stock_history(
        self,
        *,
        symbol: str,
        period: str,
        start_date: str | None,
        end_date: str | None,
        adjust: str,
        limit: int | None = None,
    ) -> Any:
        return _fetch_stock_history_direct(
            symbol=symbol,
            period=period,
            start_date=start_date,
            end_date=end_date,
            adjust=adjust,
            limit=limit,
        )

    def fetch_stock_snapshots(self) -> Any:
        return _fetch_stock_snapshots_direct()

    def fetch_index_history(
        self,
        *,
        symbol: str,
        start_date: str | None,
        end_date: str | None,
        limit: int | None = None,
    ) -> Any:
        return _fetch_index_history_direct(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )

    def fetch_sector_snapshots(self) -> Any:
        return _fetch_sector_snapshots_direct()

    def fetch_sector_constituents(self, *, symbol: str) -> Any:
        raise ProviderParseError("Eastmoney direct sector constituents are not configured")

    def fetch_sector_history(
        self,
        *,
        symbol: str,
        period: str,
        start_date: str | None,
        end_date: str | None,
        adjust: str,
        limit: int | None = None,
    ) -> Any:
        return _fetch_sector_history_direct(
            symbol=symbol,
            period=period,
            start_date=start_date,
            end_date=end_date,
            adjust=adjust,
            limit=limit,
        )


class _AkShareFetcher:
    def __init__(self) -> None:
        _configure_astock_network_env()
        self._eastmoney = _EastmoneyClient()
        try:
            self._ak = importlib.import_module("akshare")
            return
        except ImportError:
            pass

        deps = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), os.pardir, os.pardir, ".deps"
        )
        if os.path.isdir(deps) and deps not in sys.path:
            sys.path.insert(0, deps)

        try:
            self._ak = importlib.import_module("akshare")
        except ImportError as exc:
            raise ImportError(
                "akshare is required for AStockProvider but is not installed.\n"
                "Install it with: uv pip install akshare"
            ) from exc

    def fetch_stock_history(
        self,
        *,
        symbol: str,
        period: str,
        start_date: str | None,
        end_date: str | None,
        adjust: str,
        limit: int | None = None,
    ) -> Any:
        try:
            return self._eastmoney.fetch_stock_history(
                symbol=symbol,
                period=period,
                start_date=start_date,
                end_date=end_date,
                adjust=adjust,
                limit=limit,
            )
        except Exception:
            try:
                return _fetch_stock_history_baostock(
                    symbol=symbol,
                    period=period,
                    start_date=start_date,
                    end_date=end_date,
                    adjust=adjust,
                    limit=limit,
                )
            except Exception:
                return _fetch_stock_history_yahoo(
                    symbol=symbol,
                    period=period,
                    start_date=start_date,
                    end_date=end_date,
                    limit=limit,
                )

    def fetch_index_history(
        self,
        *,
        symbol: str,
        start_date: str | None,
        end_date: str | None,
        limit: int | None = None,
    ) -> Any:
        try:
            return self._eastmoney.fetch_index_history(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                limit=limit,
            )
        except Exception:
            pass

        try:
            return self._ak.stock_zh_index_daily_em(
                symbol=symbol,
                start_date=start_date or "19700101",
                end_date=end_date or "20500101",
            )
        except TypeError:
            try:
                return self._ak.stock_zh_index_daily_em(symbol=symbol)
            except Exception:
                return _fetch_index_history_yahoo(
                    symbol=symbol,
                    start_date=start_date,
                    end_date=end_date,
                    limit=limit,
                )
        except Exception:
            return _fetch_index_history_yahoo(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                limit=limit,
            )

    def fetch_stock_snapshots(self) -> Any:
        try:
            return _normalize_stock_snapshot_records(
                self._ak.stock_zh_a_spot_em(), "stock_zh_a_spot_em"
            )
        except Exception:
            pass
        if hasattr(self._ak, "stock_zh_a_spot"):
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                return _normalize_stock_snapshot_records(
                    self._ak.stock_zh_a_spot(), "stock_zh_a_spot_sina"
                )
        raise ProviderParseError(
            "Eastmoney stock snapshot clients failed and AkShare has no Sina full-market fallback"
        )

    def fetch_sector_snapshots(self) -> Any:
        try:
            return self._eastmoney.fetch_sector_snapshots()
        except Exception:
            return _tag_records(self._ak.stock_sector_spot(), "stock_sector_spot")

    def fetch_sector_constituents(self, *, symbol: str) -> Any:
        # Use direct Eastmoney HTTP layer to bypass stale proxy / fake-IP DNS.
        try:
            return _fetch_sector_constituents_direct(symbol=symbol)
        except Exception:
            return _tag_records(
                self._ak.stock_board_industry_cons_em(symbol=symbol),
                "stock_board_industry_cons_em",
            )

    def fetch_sector_history(
        self,
        *,
        symbol: str,
        period: str,
        start_date: str | None,
        end_date: str | None,
        adjust: str,
        limit: int | None = None,
    ) -> Any:
        try:
            return self._eastmoney.fetch_sector_history(
                symbol=symbol,
                period=period,
                start_date=start_date,
                end_date=end_date,
                adjust=adjust,
                limit=limit,
            )
        except Exception:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(
                io.StringIO()
            ):
                return _tag_records(
                    self._ak.stock_board_industry_index_ths(
                        symbol=symbol,
                        start_date=start_date or "19700101",
                        end_date=end_date or "20500101",
                    ),
                    "stock_board_industry_index_ths",
                )

    def fetch_northbound_flow(self, *, symbol: str) -> Any:
        return self._ak.stock_hsgt_hist_em(symbol=symbol)


class AStockProvider(SignalProvider):
    provider_id = "astock"
    display_name = "A-Share Market Data"
    capabilities = (
        "astock_price_history",
        "astock_indices",
        "astock_sectors",
        "astock_market_breadth",
        "northbound_flow",
    )

    def __init__(self, *, fetcher: AStockFetcher | None = None) -> None:
        self._fetcher = fetcher or _AkShareFetcher()

    def get_history(self, query: AStockHistoryQuery) -> PriceHistory:
        symbol = _normalize_stock_code(query.symbol)
        if query.mainboard_only and not _is_mainboard_code(symbol):
            raise ValueError(f"not an A-share mainboard symbol: {query.symbol!r}")
        period = _period(query.interval)
        rows = _records(
            self._fetcher.fetch_stock_history(
                symbol=symbol,
                period=period,
                start_date=_compact_date(query.start_date),
                end_date=_compact_date(query.end_date),
                adjust=query.adjust,
                limit=query.limit,
            )
        )
        return _parse_price_history(
            rows,
            symbol=symbol,
            raw_symbol=query.symbol,
            interval=query.interval,
            provider_id=self.provider_id,
            start_date=query.start_date,
            end_date=query.end_date,
            limit=query.limit,
            source="stock_zh_a_hist",
        )

    def get_index_history(self, query: AStockIndexQuery | None = None) -> PriceHistory:
        query = query or AStockIndexQuery()
        rows = _records(
            self._fetcher.fetch_index_history(
                symbol=query.symbol,
                start_date=_compact_date(query.start_date),
                end_date=_compact_date(query.end_date),
                limit=query.limit,
            )
        )
        return _parse_price_history(
            rows,
            symbol=query.symbol,
            raw_symbol=query.symbol,
            interval="d",
            provider_id=self.provider_id,
            start_date=query.start_date,
            end_date=query.end_date,
            limit=query.limit,
            source="stock_zh_index_daily_em",
        )

    def list_stock_snapshots(self, *, mainboard_only: bool = False) -> list[AStockSnapshot]:
        rows = _records(self._fetcher.fetch_stock_snapshots())
        snapshots = [_parse_snapshot(row, source="stock_zh_a_spot_em") for row in rows]
        if mainboard_only:
            snapshots = [
                snapshot
                for snapshot in snapshots
                if snapshot.code is not None and _is_mainboard_code(snapshot.code)
            ]
        return snapshots

    def list_sector_snapshots(self) -> list[AStockSnapshot]:
        rows = _records(self._fetcher.fetch_sector_snapshots())
        return [_parse_snapshot(row, source="stock_board_industry_name_em") for row in rows]

    def get_market_breadth(
        self, query: AStockBreadthQuery | None = None
    ) -> AStockBreadthSnapshot:
        query = query or AStockBreadthQuery()
        proxy_reason: str | None = None
        try:
            rows = _records(self._fetcher.fetch_stock_snapshots())
            scope = "market"
            name = "\u5168A"
            source = "stock_zh_a_spot_em"
        except Exception as exc:
            proxy_reason = f"{type(exc).__name__}: {exc}"
            rows = _records(self._fetcher.fetch_sector_snapshots())
            scope = "market_sector_proxy"
            name = "\u5168\u5e02\u573a\u884c\u4e1a\u4ee3\u7406"
            source = "stock_board_industry_name_em"
        if query.mainboard_only and scope == "market":
            rows = [
                row
                for row in rows
                if (code := _get(row, "\u4ee3\u7801", "浠ｇ爜", "code")) is not None
                and _is_mainboard_code(str(code))
            ]
        breadth = _parse_breadth(
            rows,
            scope=scope,
            symbol=None,
            name=name,
            limit_like_threshold=query.limit_like_threshold,
            source=source,
        )
        if proxy_reason:
            breadth.metadata["breadth_level"] = "sector_proxy"
            breadth.metadata["proxy_reason"] = proxy_reason
        else:
            breadth.metadata["breadth_level"] = "stock"
        return breadth

    def get_sector_breadth(
        self, query: AStockSectorBreadthQuery
    ) -> AStockBreadthSnapshot:
        proxy_reason: str | None = None
        try:
            rows = _records(self._fetcher.fetch_sector_constituents(symbol=query.symbol))
            scope = "sector"
            source = "stock_board_industry_cons_em"
        except Exception as exc:
            proxy_reason = f"{type(exc).__name__}: {exc}"
            sector_rows = _records(self._fetcher.fetch_sector_snapshots())
            rows = _filter_sector_snapshot_rows(sector_rows, query.symbol)
            if not rows:
                raise ProviderParseError(
                    f"no sector breadth or sector snapshot rows returned for {query.symbol!r}"
                ) from exc
            scope = "sector_snapshot_proxy"
            source = "stock_board_industry_name_em"
        breadth = _parse_breadth(
            rows,
            scope=scope,
            symbol=query.symbol,
            name=query.symbol,
            limit_like_threshold=query.limit_like_threshold,
            source=source,
        )
        if proxy_reason:
            breadth.metadata["breadth_level"] = "sector_snapshot_proxy"
            breadth.metadata["proxy_reason"] = proxy_reason
        else:
            breadth.metadata["breadth_level"] = "stock"
        return breadth

    def get_sector_history(self, query: AStockSectorHistoryQuery) -> PriceHistory:
        rows = _records(
            self._fetcher.fetch_sector_history(
                symbol=query.symbol,
                period=_period(query.interval),
                start_date=_compact_date(query.start_date),
                end_date=_compact_date(query.end_date),
                adjust=query.adjust,
                limit=query.limit,
            )
        )
        return _parse_price_history(
            rows,
            symbol=query.symbol,
            raw_symbol=query.symbol,
            interval=query.interval,
            provider_id=self.provider_id,
            start_date=query.start_date,
            end_date=query.end_date,
            limit=query.limit,
            source="stock_board_industry_hist_em",
        )

    def get_northbound_flow(
        self,
        query: AStockNorthboundQuery | None = None,
        *,
        limit: int | None = None,
    ) -> list[AStockNorthboundFlow]:
        query = query or AStockNorthboundQuery()
        effective_limit = limit if limit is not None else query.limit
        rows = _records(self._fetcher.fetch_northbound_flow(symbol=query.symbol))
        flows = [_parse_northbound_flow(row) for row in rows]
        flows.sort(key=lambda flow: flow.date)
        if effective_limit is not None and effective_limit >= 0:
            flows = flows[-effective_limit:]
        return flows


def _period(interval: str) -> str:
    period = _PERIOD_MAP.get(interval.lower().strip())
    if period is None:
        raise ValueError(f"unsupported interval: {interval!r} (use 'd', 'w', or 'm')")
    return period


def _ensure_astock_no_proxy() -> None:
    """Keep China A-share data endpoints off broken local proxy env vars.

    requests/akshare honors HTTP_PROXY/HTTPS_PROXY/ALL_PROXY. When a desktop
    proxy is turned off, those variables can still point to a dead localhost
    proxy, causing ProxyError for Eastmoney APIs that should be reachable
    directly.
    """
    existing = os.environ.get("NO_PROXY") or os.environ.get("no_proxy") or ""
    parts = [part.strip() for part in existing.split(",") if part.strip()]
    lower = {part.lower() for part in parts}
    for host in _ASTOCK_NO_PROXY_HOSTS:
        if host.lower() not in lower:
            parts.append(host)
    value = ",".join(parts)
    os.environ["NO_PROXY"] = value
    os.environ["no_proxy"] = value


def _astock_proxy_mode() -> str:
    if os.environ.get(_ASTOCK_PROXY_ENV, "").strip():
        return "explicit"
    mode = os.environ.get(_ASTOCK_PROXY_MODE_ENV, "direct").strip().lower()
    if mode in {"env", "system", "auto"}:
        return "env"
    return "direct"


def _patch_eastmoney_dns() -> None:
    """Monkey-patch ``socket.getaddrinfo`` to resolve Eastmoney CDN hosts
    to real IPs, bypassing Clash fake-IP DNS (198.18.0.x)."""
    import socket as _socket

    _real_getaddrinfo = _socket.getaddrinfo

    def _patched(host, port, family=0, type=0, proto=0, flags=0):
        if isinstance(port, int) and host in _EASTMONEY_HOSTS:
            results: list[tuple] = []
            for ip in _EASTMONEY_REAL_IPS[host]:
                try:
                    ai = _real_getaddrinfo(
                        ip, port, family=_socket.AF_INET,
                        type=_socket.SOCK_STREAM, proto=6, flags=flags,
                    )
                    results.extend(ai)
                except _socket.gaierror:
                    continue
            if results:
                return results
        return _real_getaddrinfo(host, port, family, type, proto, flags)

    _socket.getaddrinfo = _patched


def _configure_astock_network_env() -> None:
    global _DNS_PATCHED
    mode = _astock_proxy_mode()
    if mode == "explicit":
        proxy = os.environ[_ASTOCK_PROXY_ENV].strip()
        for name in (
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "ALL_PROXY",
            "http_proxy",
            "https_proxy",
            "all_proxy",
        ):
            os.environ[name] = proxy
        os.environ.pop("NO_PROXY", None)
        os.environ.pop("no_proxy", None)
        return
    if mode == "direct":
        _clear_proxy_env()
        _ensure_astock_no_proxy()
        # Prevent requests/urllib from reading stale Windows registry proxy.
        os.environ["NO_PROXY"] = "*"
        os.environ["no_proxy"] = "*"
        # Bypass Clash fake-IP DNS (198.18.0.x → real Alibaba Cloud IPs).
        if not _DNS_PATCHED:
            _patch_eastmoney_dns()
            _DNS_PATCHED = True


def _clear_proxy_env() -> None:
    for name in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ):
        os.environ.pop(name, None)


def _eastmoney_opener() -> tuple[Any, bool, str]:
    mode = _astock_proxy_mode()
    if mode == "explicit":
        proxy = os.environ[_ASTOCK_PROXY_ENV].strip()
        return (
            build_opener(ProxyHandler({"http": proxy, "https": proxy})),
            True,
            f"explicit proxy {proxy}",
        )
    if mode == "env":
        return build_opener(), False, "environment proxy"

    _ensure_astock_no_proxy()
    return build_opener(ProxyHandler({})), False, "direct connection"


def _without_no_proxy_enabled(enabled: bool) -> dict[str, str | None]:
    saved = {"NO_PROXY": os.environ.get("NO_PROXY"), "no_proxy": os.environ.get("no_proxy")}
    if enabled:
        os.environ.pop("NO_PROXY", None)
        os.environ.pop("no_proxy", None)
    return saved


def _without_proxy_env_enabled(enabled: bool) -> dict[str, str | None]:
    names = (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    )
    saved = {name: os.environ.get(name) for name in names}
    if enabled:
        for name in names:
            os.environ.pop(name, None)
    return saved


def _restore_env(saved: Mapping[str, str | None]) -> None:
    for name, value in saved.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value


def _eastmoney_get_json(
    url: str,
    params: Mapping[str, object],
    *,
    timeout_seconds: float | None = None,
) -> Mapping[str, Any]:
    timeout_seconds = timeout_seconds or _eastmoney_timeout_seconds()
    query = urlencode({k: v for k, v in params.items() if v is not None})
    errors: list[str] = []
    candidates = _eastmoney_candidate_urls(url)

    curl_data, curl_errors, last_error = _eastmoney_get_json_with_curl_cffi(
        candidates,
        query,
        timeout_seconds=timeout_seconds,
    )
    if curl_data is not None:
        return _tag_mapping(curl_data, "eastmoney_curl_cffi")
    errors.extend(curl_errors)

    opener, ignore_no_proxy, route_label = _eastmoney_opener()
    saved_no_proxy = _without_no_proxy_enabled(ignore_no_proxy)
    try:
        for candidate in candidates:
            request_url = f"{candidate}?{query}"
            request = Request(request_url, headers=_EASTMONEY_HEADERS)
            try:
                with opener.open(request, timeout=timeout_seconds) as response:
                    payload = response.read().decode("utf-8", errors="replace")
                data = json.loads(payload)
                if not isinstance(data, Mapping):
                    raise ProviderParseError(f"expected Eastmoney JSON object: {candidate}")
                return _tag_mapping(data, "eastmoney_urllib")
            except Exception as exc:
                last_error = exc
                errors.append(f"{candidate}: {type(exc).__name__}: {exc}")
                continue
    finally:
        _restore_env(saved_no_proxy)

    details = "; ".join(errors[-3:]) if errors else "no response"
    raise ProviderParseError(
        f"Eastmoney request failed via {route_label}: {url}. "
        "If direct access is blocked, enable the virtual adapter or pass "
        "--proxy http://127.0.0.1:7890 to scripts/demo_astock.py. "
        f"Last errors: {details}"
    ) from last_error


def _eastmoney_timeout_seconds() -> float:
    value = os.environ.get(_EASTMONEY_TIMEOUT_ENV, "").strip()
    if value:
        try:
            timeout = float(value)
        except ValueError:
            timeout = _EASTMONEY_DEFAULT_TIMEOUT_SECONDS
        return max(1.0, min(timeout, 30.0))
    return _EASTMONEY_DEFAULT_TIMEOUT_SECONDS


def _eastmoney_get_json_with_curl_cffi(
    candidates: list[str],
    query: str,
    *,
    timeout_seconds: float,
) -> tuple[Mapping[str, Any] | None, list[str], Exception | None]:
    try:
        curl_requests = importlib.import_module("curl_cffi.requests")
    except ImportError:
        return None, [], None

    mode = _astock_proxy_mode()
    kwargs: dict[str, Any] = {
        "headers": _EASTMONEY_HEADERS,
        "timeout": timeout_seconds,
        "impersonate": "chrome",
    }
    if mode == "explicit":
        proxy = os.environ[_ASTOCK_PROXY_ENV].strip()
        kwargs["proxies"] = {"http": proxy, "https": proxy}
    elif mode == "direct":
        kwargs["proxies"] = {}

    errors: list[str] = []
    last_error: Exception | None = None
    saved_proxy_env = _without_proxy_env_enabled(mode in {"direct", "explicit"})
    try:
        with curl_requests.Session(trust_env=(mode == "env")) as session:
            for candidate in candidates:
                request_url = f"{candidate}?{query}"
                try:
                    response = session.get(request_url, **kwargs)
                    response.raise_for_status()
                    data = response.json()
                    if not isinstance(data, Mapping):
                        raise ProviderParseError(f"expected Eastmoney JSON object: {candidate}")
                    return data, errors, None
                except Exception as exc:
                    last_error = exc
                    errors.append(f"{candidate} [curl_cffi]: {type(exc).__name__}: {exc}")
                    continue
    finally:
        _restore_env(saved_proxy_env)
    return None, errors, last_error


def _eastmoney_candidate_urls(url: str) -> list[str]:
    parsed = urlsplit(url)
    hosts: tuple[str, ...]
    if "push2his.eastmoney.com" in parsed.netloc:
        hosts = (
            parsed.netloc,
            "push2his.eastmoney.com",
            "7.push2his.eastmoney.com",
            "33.push2his.eastmoney.com",
        )
    elif "push2.eastmoney.com" in parsed.netloc:
        hosts = (
            parsed.netloc,
            "push2.eastmoney.com",
            "82.push2.eastmoney.com",
            "17.push2.eastmoney.com",
            "56.push2.eastmoney.com",
        )
    else:
        hosts = (parsed.netloc,)

    urls: list[str] = []
    seen: set[str] = set()
    for host in hosts:
        candidate = urlunsplit((parsed.scheme, host, parsed.path, "", ""))
        if candidate not in seen:
            seen.add(candidate)
            urls.append(candidate)
    return urls


def _market_id_for_stock(symbol: str) -> str:
    code = _normalize_stock_code(symbol)
    if code.startswith(("5", "6", "9")):
        return "1"
    return "0"


def _klt(period: str) -> str:
    return {"daily": "101", "weekly": "102", "monthly": "103"}[period]


def _fqt(adjust: str) -> str:
    return {"": "0", "qfq": "1", "hfq": "2"}.get(adjust, "0")


def _parse_kline_items(items: object) -> list[dict[str, object]]:
    if not isinstance(items, list):
        return []
    rows: list[dict[str, object]] = []
    for item in items:
        parts = str(item).split(",")
        if len(parts) < 6:
            continue
        rows.append(
            {
                "date": parts[0],
                "open": parts[1],
                "close": parts[2],
                "high": parts[3],
                "low": parts[4],
                "volume": parts[5],
                "amount": parts[6] if len(parts) > 6 else None,
                "change_pct": parts[8] if len(parts) > 8 else None,
                "turnover_rate": parts[10] if len(parts) > 10 else None,
            }
        )
    return rows


def _fetch_stock_history_direct(
    *,
    symbol: str,
    period: str,
    start_date: str | None,
    end_date: str | None,
    adjust: str,
    limit: int | None = None,
) -> list[dict[str, object]]:
    data = _eastmoney_get_json(
        "https://push2his.eastmoney.com/api/qt/stock/kline/get",
        {
            "secid": f"{_market_id_for_stock(symbol)}.{_normalize_stock_code(symbol)}",
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
            "ut": "7eea3edcaed734bea9cbfc24409ed989",
            "klt": _klt(period),
            "fqt": _fqt(adjust),
            "beg": start_date or "19700101",
            "end": end_date or "20500101",
            "lmt": _eastmoney_limit(limit),
        },
    )
    payload = data.get("data")
    klines = payload.get("klines") if isinstance(payload, Mapping) else None
    rows = _parse_kline_items(klines)
    if not rows:
        raise ProviderParseError(f"no Eastmoney stock kline rows returned for {symbol!r}")
    return _tag_records(rows, _row_source(data, "eastmoney_direct"))


def _fetch_index_history_direct(
    *,
    symbol: str,
    start_date: str | None,
    end_date: str | None,
    limit: int | None = None,
) -> list[dict[str, object]]:
    data = _eastmoney_get_json(
        "https://push2his.eastmoney.com/api/qt/stock/kline/get",
        {
            "secid": _eastmoney_index_secid(symbol),
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
            "ut": "7eea3edcaed734bea9cbfc24409ed989",
            "klt": "101",
            "fqt": "0",
            "beg": start_date or "19700101",
            "end": end_date or "20500101",
            "lmt": _eastmoney_limit(limit),
        },
    )
    payload = data.get("data")
    klines = payload.get("klines") if isinstance(payload, Mapping) else None
    rows = _parse_kline_items(klines)
    if not rows:
        raise ProviderParseError(f"no Eastmoney index kline rows returned for {symbol!r}")
    return _tag_records(rows, _row_source(data, "eastmoney_direct"))


def _fetch_stock_history_yahoo(
    *,
    symbol: str,
    period: str,
    start_date: str | None,
    end_date: str | None,
    limit: int | None = None,
) -> list[dict[str, object]]:
    try:
        yf = importlib.import_module("yfinance")
    except ImportError as exc:
        raise ProviderParseError(
            "A-share Eastmoney history failed and yfinance fallback is not installed"
        ) from exc

    _configure_yfinance_cache(yf)

    ticker = _yahoo_symbol_for_astock(symbol)
    kwargs: dict[str, object] = {
        "interval": _yahoo_interval(period),
        "auto_adjust": False,
        "actions": False,
    }
    if start_date:
        kwargs["start"] = _hyphen_date(start_date)
    if end_date:
        kwargs["end"] = _hyphen_date(end_date)
    if not start_date and not end_date:
        kwargs["period"] = _yahoo_period_for_limit(limit)

    frame = yf.Ticker(ticker).history(**kwargs)
    if getattr(frame, "empty", True):
        raise ProviderParseError(f"no Yahoo A-share history rows returned for {ticker!r}")

    rows: list[dict[str, object]] = []
    for index, row in frame.iterrows():
        rows.append(
            {
                "date": _normalize_date(index),
                "open": row.get("Open"),
                "high": row.get("High"),
                "low": row.get("Low"),
                "close": row.get("Close"),
                "volume": row.get("Volume"),
                "_source": "yahoo_finance",
                "yahoo_symbol": ticker,
            }
        )
    return rows


def _fetch_index_history_yahoo(
    *,
    symbol: str,
    start_date: str | None,
    end_date: str | None,
    limit: int | None = None,
) -> list[dict[str, object]]:
    try:
        yf = importlib.import_module("yfinance")
    except ImportError as exc:
        raise ProviderParseError(
            "A-share index fallback requires yfinance. Install it with: "
            "python -m pip install yfinance"
        ) from exc

    _configure_yfinance_cache(yf)

    ticker = _yahoo_symbol_for_astock_index(symbol)
    kwargs: dict[str, object] = {
        "interval": "1d",
        "auto_adjust": False,
        "actions": False,
    }
    if start_date:
        kwargs["start"] = _hyphen_date(start_date)
    if end_date:
        kwargs["end"] = _hyphen_date(end_date)
    if not start_date and not end_date:
        kwargs["period"] = _yahoo_period_for_limit(limit)

    frame = yf.Ticker(ticker).history(**kwargs)
    if getattr(frame, "empty", True):
        raise ProviderParseError(f"no Yahoo A-share index rows returned for {ticker!r}")

    rows: list[dict[str, object]] = []
    for index, row in frame.iterrows():
        rows.append(
            {
                "date": _normalize_date(index),
                "open": row.get("Open"),
                "high": row.get("High"),
                "low": row.get("Low"),
                "close": row.get("Close"),
                "volume": row.get("Volume"),
                "_source": "yahoo_finance",
                "yahoo_symbol": ticker,
            }
        )
    return rows


def _configure_yfinance_cache(yf: Any) -> None:
    cache_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        ".cache",
        "yfinance",
    )
    os.makedirs(cache_dir, exist_ok=True)
    if hasattr(yf, "set_tz_cache_location"):
        yf.set_tz_cache_location(cache_dir)


def _fetch_stock_history_baostock(
    *,
    symbol: str,
    period: str,
    start_date: str | None,
    end_date: str | None,
    adjust: str,
    limit: int | None = None,
) -> list[dict[str, object]]:
    try:
        bs = importlib.import_module("baostock")
    except ImportError as exc:
        raise ProviderParseError(
            "A-share BaoStock fallback is not installed. Install it with: "
            "python -m pip install baostock"
        ) from exc

    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        login_result = bs.login()
    if getattr(login_result, "error_code", "0") != "0":
        raise ProviderParseError(
            f"BaoStock login failed: {getattr(login_result, 'error_msg', '')}"
        )

    try:
        query_start = _hyphen_date(start_date) if start_date else _baostock_start_date(period, limit)
        query_end = _hyphen_date(end_date) if end_date else date.today().isoformat()
        result = bs.query_history_k_data_plus(
            _baostock_symbol(symbol),
            "date,code,open,high,low,close,volume,amount,turn,pctChg",
            start_date=query_start,
            end_date=query_end,
            frequency=_baostock_frequency(period),
            adjustflag=_baostock_adjustflag(adjust),
        )
        if getattr(result, "error_code", "0") != "0":
            raise ProviderParseError(
                f"BaoStock history query failed: {getattr(result, 'error_msg', '')}"
            )

        rows: list[dict[str, object]] = []
        fields = list(getattr(result, "fields", []))
        while result.next():
            raw = result.get_row_data()
            row = dict(zip(fields, raw))
            rows.append(
                {
                    "date": row.get("date"),
                    "open": row.get("open"),
                    "high": row.get("high"),
                    "low": row.get("low"),
                    "close": row.get("close"),
                    "volume": row.get("volume"),
                    "amount": row.get("amount"),
                    "turnover_rate": row.get("turn"),
                    "change_pct": row.get("pctChg"),
                    "_source": "baostock",
                    "baostock_symbol": row.get("code"),
                }
            )
    finally:
        with contextlib.suppress(Exception):
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(
                io.StringIO()
            ):
                bs.logout()

    if not rows:
        raise ProviderParseError(f"no BaoStock A-share history rows returned for {symbol!r}")
    if limit is not None and limit >= 0:
        rows = rows[-limit:]
    return rows


def _baostock_symbol(symbol: str) -> str:
    code = _normalize_stock_code(symbol)
    if code.startswith(("5", "6", "9")):
        return f"sh.{code}"
    if code.startswith(("0", "1", "2", "3")):
        return f"sz.{code}"
    if code.startswith(("4", "8")):
        return f"bj.{code}"
    raise ProviderParseError(f"cannot map A-share symbol to BaoStock: {symbol!r}")


def _baostock_frequency(period: str) -> str:
    return {"daily": "d", "weekly": "w", "monthly": "m"}[period]


def _baostock_adjustflag(adjust: str) -> str:
    return {"": "3", "qfq": "2", "hfq": "1"}.get(adjust, "3")


def _baostock_start_date(period: str, limit: int | None) -> str:
    if limit is None or limit < 0:
        return "1990-01-01"
    multiplier = {"daily": 3, "weekly": 10, "monthly": 40}[period]
    days = max(120, limit * multiplier)
    return (date.today() - timedelta(days=days)).isoformat()


def _yahoo_symbol_for_astock(symbol: str) -> str:
    code = _normalize_stock_code(symbol)
    if code.startswith(("5", "6", "9")):
        return f"{code}.SS"
    if code.startswith(("0", "1", "2", "3")):
        return f"{code}.SZ"
    if code.startswith(("4", "8")):
        return f"{code}.BJ"
    raise ProviderParseError(f"cannot map A-share symbol to Yahoo: {symbol!r}")


def _yahoo_symbol_for_astock_index(symbol: str) -> str:
    lowered = symbol.strip().lower()
    code = _normalize_stock_code(symbol)
    if lowered.startswith("sz") or code.startswith("399"):
        return f"{code}.SZ"
    return f"{code}.SS"


def _eastmoney_index_secid(symbol: str) -> str:
    lowered = symbol.strip().lower()
    code = _normalize_stock_code(symbol)
    if lowered.startswith("sz") or code.startswith("399"):
        return f"0.{code}"
    return f"1.{code}"


def _yahoo_interval(period: str) -> str:
    return {"daily": "1d", "weekly": "1wk", "monthly": "1mo"}[period]


def _yahoo_period_for_limit(limit: int | None) -> str:
    if limit is None or limit < 0:
        return "max"
    if limit <= 30:
        return "3mo"
    if limit <= 90:
        return "1y"
    if limit <= 260:
        return "2y"
    if limit <= 1500:
        return "10y"
    return "max"


def _hyphen_date(value: str) -> str:
    if len(value) == 8 and value.isdigit():
        return f"{value[:4]}-{value[4:6]}-{value[6:]}"
    return value


def _fetch_stock_snapshots_direct() -> list[dict[str, object]]:
    data = _eastmoney_get_json(
        "https://push2.eastmoney.com/api/qt/clist/get",
        {
            "pn": "1",
            "pz": "10000",
            "po": "1",
            "np": "1",
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": "2",
            "invt": "2",
            "fid": "f12",
            "fs": "m:0 t:6,m:0 t:80,m:1 t:2,m:1 t:23,m:0 t:81 s:2048",
            "fields": "f2,f3,f4,f5,f6,f8,f9,f12,f14,f20,f21,f23",
        },
    )
    payload = data.get("data")
    diff = payload.get("diff") if isinstance(payload, Mapping) else None
    if not isinstance(diff, list) or not diff:
        raise ProviderParseError("missing Eastmoney stock snapshot rows")
    total = payload.get("total") if isinstance(payload, Mapping) else None
    if isinstance(total, (int, float)) and int(total) > len(diff) * 5:
        # Eastmoney caps pz at 100 regardless of what we request.
        # Fall back to Sina / akshare which return all ~5500 rows at once.
        raise ProviderParseError(
            f"Eastmoney returned only {len(diff)} of {int(total)} stocks"
        )
    return _tag_records(
        [
        {
            "code": row.get("f12"),
            "name": row.get("f14"),
            "latest": row.get("f2"),
            "change_pct": row.get("f3"),
            "change_amount": row.get("f4"),
            "volume": row.get("f5"),
            "amount": row.get("f6"),
            "turnover_rate": row.get("f8"),
            "pe_dynamic": row.get("f9"),
            "pb": row.get("f23"),
            "total_market_cap": row.get("f20"),
            "circulating_market_cap": row.get("f21"),
        }
        for row in diff
        if isinstance(row, Mapping)
        ],
        _row_source(data, "eastmoney_direct"),
    )


def _fetch_sector_snapshots_direct() -> list[dict[str, object]]:
    data = _eastmoney_get_json(
        "https://push2.eastmoney.com/api/qt/clist/get",
        {
            "pn": "1",
            "pz": "500",
            "po": "1",
            "np": "1",
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": "2",
            "invt": "2",
            "fid": "f3",
            "fs": "m:90 t:2 f:!50",
            "fields": "f2,f3,f4,f5,f6,f8,f12,f14,f20,f104,f105",
        },
    )
    payload = data.get("data")
    diff = payload.get("diff") if isinstance(payload, Mapping) else None
    if not isinstance(diff, list):
        raise ProviderParseError("missing Eastmoney sector snapshot rows")
    return _tag_records(
        [
        {
            "code": row.get("f12"),
            "name": row.get("f14"),
            "latest": row.get("f2"),
            "change_pct": row.get("f3"),
            "change_amount": row.get("f4"),
            "volume": row.get("f5"),
            "amount": row.get("f6"),
            "turnover_rate": row.get("f8"),
            "total_market_cap": row.get("f20"),
            "up_count": row.get("f104"),
            "down_count": row.get("f105"),
        }
        for row in diff
        if isinstance(row, Mapping)
        ],
        _row_source(data, "eastmoney_direct"),
    )


def _fetch_sector_constituents_direct(
    *, symbol: str
) -> list[dict[str, object]]:
    """Fetch industry board constituents via direct Eastmoney HTTP layer."""
    # 1. Find the board code via paginated search, respecting aliases.
    aliases = _SECTOR_PROXY_ALIASES.get(symbol, (symbol,))
    sector_code = None
    for pn in range(1, 7):
        data = _eastmoney_get_json(
            "https://push2.eastmoney.com/api/qt/clist/get",
            {
                "pn": str(pn), "pz": "100", "po": "1", "np": "1",
                "ut": "bd1d9ddb04089700cf9c27f6f7426281",
                "fltt": "2", "invt": "2", "fid": "f3",
                "fs": "m:90 t:2 f:!50",
                "fields": "f12,f14",
            },
        )
        payload = data.get("data")
        diff = payload.get("diff") if isinstance(payload, Mapping) else None
        if not isinstance(diff, list) or not diff:
            break
        for row in diff:
            if isinstance(row, Mapping) and str(row.get("f14", "")) in aliases:
                sector_code = row.get("f12")
                if sector_code:
                    sector_code = str(sector_code)
                break
        if sector_code:
            break

    if sector_code is None:
        raise ProviderParseError(
            f"unknown A-share sector: {symbol!r}"
        )

    # 2. Fetch constituents for that board.
    data = _eastmoney_get_json(
        "https://push2.eastmoney.com/api/qt/clist/get",
        {
            "pn": "1", "pz": "500", "po": "1", "np": "1",
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": "2", "invt": "2", "fid": "f3",
            "fs": f"b:{sector_code}",
            "fields": (
                "f2,f3,f4,f5,f6,f8,f12,f14,f20,f62,f104,f105"
            ),
        },
    )
    payload = data.get("data")
    diff = payload.get("diff") if isinstance(payload, Mapping) else None
    if not isinstance(diff, list):
        raise ProviderParseError(
            f"missing Eastmoney constituent rows for {symbol!r}"
        )
    return _tag_records(
        [
        {
            "code": row.get("f12"),
            "name": row.get("f14"),
            "latest": row.get("f2"),
            "change_pct": row.get("f3"),
            "change_amount": row.get("f4"),
            "volume": row.get("f5"),
            "amount": row.get("f6"),
            "turnover_rate": row.get("f8"),
            "total_market_cap": row.get("f20"),
            "main_net_inflow": row.get("f62"),
            "up_count": row.get("f104"),
            "down_count": row.get("f105"),
        }
        for row in diff
        if isinstance(row, Mapping)
        ],
        _row_source(data, "eastmoney_direct"),
    )


def _sector_code(symbol: str) -> str:
    if symbol.upper().startswith("BK"):
        return symbol.upper()
    for row in _fetch_sector_snapshots_direct():
        if str(row.get("name")) == symbol:
            code = row.get("code")
            if code is not None:
                return str(code)
    raise ProviderParseError(f"unknown A-share sector: {symbol!r}")


def _fetch_sector_history_direct(
    *,
    symbol: str,
    period: str,
    start_date: str | None,
    end_date: str | None,
    adjust: str,
    limit: int | None = None,
) -> list[dict[str, object]]:
    code = _sector_code(symbol)
    data = _eastmoney_get_json(
        "https://push2his.eastmoney.com/api/qt/stock/kline/get",
        {
            "secid": f"90.{code}",
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
            "klt": _klt(period),
            "fqt": _fqt(adjust),
            "beg": start_date or "19700101",
            "end": end_date or "20500101",
            "lmt": _eastmoney_limit(limit),
        },
    )
    payload = data.get("data")
    klines = payload.get("klines") if isinstance(payload, Mapping) else None
    rows = _parse_kline_items(klines)
    if not rows:
        raise ProviderParseError(f"no Eastmoney sector kline rows returned for {symbol!r}")
    return _tag_records(rows, _row_source(data, "eastmoney_direct"))


def _eastmoney_limit(limit: int | None) -> str:
    if limit is not None and limit >= 0:
        return str(max(limit, 1))
    return "1000000"


def _tag_mapping(data: Mapping[str, Any], source: str) -> Mapping[str, Any]:
    copy = dict(data)
    copy.setdefault("_source", source)
    return copy


def _tag_records(data: Any, source: str) -> list[Mapping[str, Any]]:
    tagged: list[Mapping[str, Any]] = []
    for row in _records(data):
        copy = dict(row)
        copy.setdefault("_source", source)
        tagged.append(copy)
    return tagged


def _normalize_stock_snapshot_records(data: Any, source: str) -> list[Mapping[str, Any]]:
    rows: list[Mapping[str, Any]] = []
    for row in _records(data):
        rows.append(
            {
                "code": _get(row, "\u4ee3\u7801", "code"),
                "name": _get(row, "\u540d\u79f0", "name"),
                "latest": _get(row, "\u6700\u65b0\u4ef7", "trade", "latest"),
                "change_pct": _get(row, "\u6da8\u8dcc\u5e45", "changepercent", "change_pct"),
                "change_amount": _get(row, "\u6da8\u8dcc\u989d", "pricechange", "change_amount"),
                "volume": _get(row, "\u6210\u4ea4\u91cf", "volume"),
                "amount": _get(row, "\u6210\u4ea4\u989d", "amount"),
                "turnover_rate": _get(row, "\u6362\u624b\u7387", "turnoverratio", "turnover_rate"),
                "pe_dynamic": _get(row, "\u5e02\u76c8\u7387-\u52a8\u6001", "per", "pe_dynamic"),
                "pb": _get(row, "\u5e02\u51c0\u7387", "pb"),
                "total_market_cap": _get(row, "\u603b\u5e02\u503c", "mktcap", "total_market_cap"),
                "circulating_market_cap": _get(row, "\u6d41\u901a\u5e02\u503c", "nmc", "circulating_market_cap"),
                "_source": _row_source(row, source),
            }
        )
    return rows


def _row_source(row: Mapping[str, Any], default: str) -> str:
    source = row.get("_source")
    return str(source) if source else default


def _source_from_rows(rows: list[Mapping[str, Any]], default: str) -> str:
    for row in rows:
        source = row.get("_source")
        if source:
            return str(source)
    return default


def _records(data: Any) -> list[Mapping[str, Any]]:
    if hasattr(data, "to_dict"):
        raw = data.to_dict("records")
    else:
        raw = data
    if not isinstance(raw, list):
        raise ProviderParseError("expected tabular provider payload")
    records: list[Mapping[str, Any]] = []
    for item in raw:
        if not isinstance(item, Mapping):
            raise ProviderParseError("expected rows to be mappings")
        records.append(item)
    return records


def _filter_sector_snapshot_rows(
    rows: list[Mapping[str, Any]], symbol: str
) -> list[Mapping[str, Any]]:
    target = symbol.strip().lower()
    targets = {
        value.strip().lower()
        for value in _SECTOR_PROXY_ALIASES.get(symbol.strip(), (symbol,))
        if value.strip()
    }
    targets.add(target)
    matches: list[Mapping[str, Any]] = []
    for row in rows:
        code = _get(row, "\u677f\u5757\u4ee3\u7801", "鏉垮潡浠ｇ爜", "code", "label")
        name = _get(row, "\u677f\u5757\u540d\u79f0", "\u677f\u5757", "鏉垮潡鍚嶇О", "鏉垮潡", "name")
        values = {str(value).strip().lower() for value in (code, name) if value is not None}
        if targets.intersection(values):
            matches.append(row)
    return matches


def _get(row: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row:
            return row[key]
    return None


def _coerce_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return None if math.isnan(number) or math.isinf(number) else number
    if isinstance(value, str):
        cleaned = (
            value.replace(",", "")
            .replace("%", "")
            .replace("\u4ebf", "")
            .replace("\u4e07", "")
            .strip()
        )
        if cleaned in {"", "-", "--", "None", "nan"}:
            return None
        try:
            number = float(cleaned)
        except ValueError:
            return None
        return None if math.isnan(number) or math.isinf(number) else number
    return None


def _normalize_date(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    text = str(value).strip()
    if not text:
        return None
    text = text[:10]
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    return text


def _compact_date(value: str | None) -> str | None:
    if not value:
        return None
    return value.replace("-", "")


def _normalize_stock_code(symbol: str) -> str:
    code = symbol.strip().lower()
    if code.startswith(("sh", "sz", "bj")) and len(code) >= 8:
        code = code[2:]
    if "." in code:
        code = code.split(".", 1)[0]
    return code.upper()


def _is_mainboard_code(symbol: str) -> bool:
    code = _normalize_stock_code(symbol)
    return code.startswith(("600", "601", "603", "605", "000", "001", "002", "003"))


def _parse_price_history(
    rows: list[Mapping[str, Any]],
    *,
    symbol: str,
    raw_symbol: str,
    interval: str,
    provider_id: str,
    start_date: str | None,
    end_date: str | None,
    limit: int | None,
    source: str,
) -> PriceHistory:
    effective_source = _source_from_rows(rows, source)
    bars: list[PriceBar] = []
    for row in rows:
        date = _normalize_date(_get(row, "\u65e5\u671f", "date", "\u65f6\u95f4", "day"))
        if date is None:
            continue
        if start_date and date < start_date:
            continue
        if end_date and date > end_date:
            continue

        open_price = _coerce_float(_get(row, "\u5f00\u76d8", "\u5f00\u76d8\u4ef7", "open"))
        high_price = _coerce_float(_get(row, "\u6700\u9ad8", "\u6700\u9ad8\u4ef7", "high"))
        low_price = _coerce_float(_get(row, "\u6700\u4f4e", "\u6700\u4f4e\u4ef7", "low"))
        close_price = _coerce_float(_get(row, "\u6536\u76d8", "\u6536\u76d8\u4ef7", "close"))
        if any(v is None for v in (open_price, high_price, low_price, close_price)):
            continue

        bars.append(
            PriceBar(
                date=date,
                open=open_price,
                high=high_price,
                low=low_price,
                close=close_price,
                volume=_coerce_float(_get(row, "\u6210\u4ea4\u91cf", "volume", "amount")),
            )
        )

    bars.sort(key=lambda bar: bar.date)
    if limit is not None and limit >= 0:
        bars = bars[-limit:]
    if not bars:
        raise ProviderParseError(f"no A-share price rows returned for {raw_symbol!r}")
    return PriceHistory(
        symbol=symbol,
        raw_symbol=raw_symbol,
        interval=interval.lower().strip(),
        provider_id=provider_id,
        bars=tuple(bars),
        metadata={"source": effective_source},
    )


def _parse_snapshot(row: Mapping[str, Any], *, source: str) -> AStockSnapshot:
    effective_source = _row_source(row, source)
    code = _get(row, "\u4ee3\u7801", "\u677f\u5757\u4ee3\u7801", "code", "label")
    code_text = str(code).strip() if code is not None else None
    name = _get(row, "\u540d\u79f0", "\u677f\u5757\u540d\u79f0", "name", "\u677f\u5757")
    if name is None:
        raise ProviderParseError("missing A-share snapshot name")
    return AStockSnapshot(
        code=code_text,
        name=str(name),
        latest=_coerce_float(_get(row, "\u6700\u65b0\u4ef7", "latest", "\u5e73\u5747\u4ef7\u683c")),
        change_pct=_coerce_float(_get(row, "\u6da8\u8dcc\u5e45", "change_pct")),
        change_amount=_coerce_float(_get(row, "\u6da8\u8dcc\u989d", "change_amount")),
        volume=_coerce_float(_get(row, "\u6210\u4ea4\u91cf", "volume", "\u603b\u6210\u4ea4\u91cf")),
        amount=_coerce_float(_get(row, "\u6210\u4ea4\u989d", "amount", "\u603b\u6210\u4ea4\u989d")),
        turnover_rate=_coerce_float(_get(row, "\u6362\u624b\u7387", "turnover_rate")),
        pe_dynamic=_coerce_float(_get(row, "\u5e02\u76c8\u7387-\u52a8\u6001", "\u52a8\u6001\u5e02\u76c8\u7387", "pe_dynamic")),
        pb=_coerce_float(_get(row, "\u5e02\u51c0\u7387", "pb")),
        total_market_cap=_coerce_float(_get(row, "\u603b\u5e02\u503c", "total_market_cap")),
        circulating_market_cap=_coerce_float(_get(row, "\u6d41\u901a\u5e02\u503c", "circulating_market_cap")),
        metadata={"source": effective_source},
    )


def _parse_breadth(
    rows: list[Mapping[str, Any]],
    *,
    scope: str,
    symbol: str | None,
    name: str | None,
    limit_like_threshold: float,
    source: str,
) -> AStockBreadthSnapshot:
    effective_source = _source_from_rows(rows, source)
    changes: list[float] = []
    total_amount = 0.0
    total_volume = 0.0
    amount_count = 0
    volume_count = 0
    up_count = 0
    down_count = 0
    flat_count = 0
    limit_up_count = 0
    limit_down_count = 0
    missing_change_count = 0

    for row in rows:
        change_pct = _coerce_float(_get(row, "\u6da8\u8dcc\u5e45", "change_pct", "pctChg"))
        if change_pct is None:
            missing_change_count += 1
        else:
            changes.append(change_pct)
            if change_pct > 0:
                up_count += 1
            elif change_pct < 0:
                down_count += 1
            else:
                flat_count += 1
            if change_pct >= limit_like_threshold:
                limit_up_count += 1
            if change_pct <= -limit_like_threshold:
                limit_down_count += 1

        amount = _coerce_float(_get(row, "\u6210\u4ea4\u989d", "amount", "\u603b\u6210\u4ea4\u989d"))
        if amount is not None:
            total_amount += amount
            amount_count += 1

        volume = _coerce_float(_get(row, "\u6210\u4ea4\u91cf", "volume", "\u603b\u6210\u4ea4\u91cf"))
        if volume is not None:
            total_volume += volume
            volume_count += 1

    average_change_pct = sum(changes) / len(changes) if changes else None
    median_change_pct = median(changes) if changes else None
    return AStockBreadthSnapshot(
        scope=scope,
        symbol=symbol,
        name=name,
        total_count=len(rows),
        up_count=up_count,
        down_count=down_count,
        flat_count=flat_count,
        limit_up_count=limit_up_count,
        limit_down_count=limit_down_count,
        total_amount=total_amount if amount_count else None,
        total_volume=total_volume if volume_count else None,
        average_change_pct=average_change_pct,
        median_change_pct=median_change_pct,
        metadata={
            "source": effective_source,
            "amount_count": amount_count,
            "volume_count": volume_count,
            "change_count": len(changes),
            "missing_change_count": missing_change_count,
            "limit_like_threshold": limit_like_threshold,
        },
    )


def _parse_northbound_flow(row: Mapping[str, Any]) -> AStockNorthboundFlow:
    date = _normalize_date(_get(row, "\u65e5\u671f", "date"))
    if date is None:
        raise ProviderParseError("missing northbound flow date")
    return AStockNorthboundFlow(
        date=date,
        net_buy_amount=_coerce_float(
            _get(row, "\u5f53\u65e5\u6210\u4ea4\u51c0\u4e70\u989d", "\u5f53\u65e5\u51c0\u4e70\u989d", "net_buy_amount")
        ),
        buy_amount=_coerce_float(_get(row, "\u4e70\u5165\u6210\u4ea4\u989d", "buy_amount")),
        sell_amount=_coerce_float(_get(row, "\u5356\u51fa\u6210\u4ea4\u989d", "sell_amount")),
        cumulative_net_buy_amount=_coerce_float(
            _get(row, "\u5386\u53f2\u7d2f\u8ba1\u51c0\u4e70\u989d", "\u7d2f\u8ba1\u51c0\u4e70\u989d", "cumulative_net_buy_amount")
        ),
        hs300_change_pct=_coerce_float(
            _get(row, "\u6caa\u6df1300\u6da8\u8dcc\u5e45", "\u6caa\u6df1300-\u6da8\u8dcc\u5e45", "hs300_change_pct")
        ),
        metadata={"source": "stock_hsgt_hist_em"},
    )


