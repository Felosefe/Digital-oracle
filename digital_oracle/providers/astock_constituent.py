from __future__ import annotations

import importlib
import os
import sys
import time
from dataclasses import dataclass, field
from statistics import median
from typing import Any, Mapping, Protocol

from ._coerce import _coerce_float, _coerce_int
from .base import ProviderParseError, SignalProvider

# Reuse the same network env setup as AStockProvider to bypass dead proxy env vars.
from .astock import _configure_astock_network_env, _eastmoney_get_json


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


def _patch_requests_for_astock() -> None:
    """Bypass Clash fake-IP DNS for Eastmoney and prevent stale system proxy."""
    import socket as _socket
    import os as _os

    _configure_astock_network_env()

    # DNS bypass
    _real_getaddrinfo = _socket.getaddrinfo

    def _patched_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
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

    _socket.getaddrinfo = _patched_getaddrinfo

    try:
        import urllib3.util.connection as _uconn
        _orig_create = _uconn.create_connection

        def _patched_create(address, *args, **kwargs):
            host, port = address
            if host in _EASTMONEY_HOSTS:
                addresses = [(ip, port) for ip in _EASTMONEY_REAL_IPS[host]]
                last_err = None
                for addr in addresses:
                    try:
                        return _orig_create(addr, *args, **kwargs)
                    except OSError as e:
                        last_err = e
                if last_err:
                    raise last_err
            return _orig_create(address, *args, **kwargs)

        _uconn.create_connection = _patched_create
    except ImportError:
        pass

    # Stale proxy bypass
    mode = _os.environ.get("DIGITAL_ORACLE_ASTOCK_PROXY_MODE", "direct").strip().lower()
    if _os.environ.get("DIGITAL_ORACLE_ASTOCK_PROXY", "").strip():
        _os.environ.pop("NO_PROXY", None)
        _os.environ.pop("no_proxy", None)
        return
    if mode == "direct":
        _os.environ["NO_PROXY"] = "*"
        _os.environ["no_proxy"] = "*"

    try:
        import requests as _r
        _r.utils.get_environ_proxies.cache_clear()
    except (ImportError, AttributeError):
        pass


@dataclass(frozen=True)
class ConstituentQuery:
    symbol: str
    scope: str = "industry"
    sort_by: str = "change_pct"
    top_n: int | None = None


@dataclass
class StockConstituent:
    code: str | None
    name: str
    latest: float | None = None
    change_pct: float | None = None
    change_amount: float | None = None
    volume: float | None = None
    amount: float | None = None
    turnover_rate: float | None = None
    total_market_cap: float | None = None
    circulating_market_cap: float | None = None
    pe_dynamic: float | None = None
    pb: float | None = None
    weight: float | None = None


@dataclass
class ConstituentList:
    symbol: str
    name: str
    scope: str
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
    average_market_cap: float | None = None
    constituents: tuple[StockConstituent, ...] = ()
    metadata: dict[str, object] = field(default_factory=dict, repr=False)


class ConstituentFetcher(Protocol):
    def fetch_industry_constituents(self, *, symbol: str) -> Any: ...
    def fetch_concept_constituents(self, *, symbol: str) -> Any: ...
    def fetch_index_constituents(self, *, symbol: str) -> Any: ...


class _AkShareConstituentFetcher:
    def __init__(self) -> None:
        _patch_requests_for_astock()
        try:
            self._ak = importlib.import_module("akshare")
            return
        except ImportError:
            pass

        deps = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            os.pardir,
            os.pardir,
            ".deps",
        )
        if os.path.isdir(deps) and deps not in sys.path:
            sys.path.insert(0, deps)

        try:
            self._ak = importlib.import_module("akshare")
        except ImportError as exc:
            raise ImportError(
                "akshare is required for AStockConstituentProvider but is not installed.\n"
                "Install it with: uv pip install akshare"
            ) from exc

    @staticmethod
    def _fetch_constituent_data(fs_filter: str, fields: str) -> list[Mapping[str, Any]]:
        """Fetch constituent data, trying push2his if push2 is rate-limited."""
        # Try push2 first
        data = _eastmoney_get_json(
            "https://push2.eastmoney.com/api/qt/clist/get",
            {
                "pn": "1", "pz": "500", "po": "1", "np": "1",
                "ut": "bd1d9ddb04089700cf9c27f6f7426281",
                "fltt": "2", "invt": "2", "fid": "f3",
                "fs": fs_filter,
                "fields": fields,
            },
        )
        payload = data.get("data")
        diff = payload.get("diff") if isinstance(payload, Mapping) else None
        if isinstance(diff, list):
            return _map_constituent_rows(diff, _row_source(data, "eastmoney_direct"))

        # push2 rate-limited — try push2his (different rate-limit pool)
        data = _eastmoney_get_json(
            "https://push2his.eastmoney.com/api/qt/clist/get",
            {
                "pn": "1", "pz": "500", "po": "1", "np": "1",
                "ut": "bd1d9ddb04089700cf9c27f6f7426281",
                "fltt": "2", "invt": "2", "fid": "f3",
                "fs": fs_filter,
                "fields": fields,
            },
        )
        payload = data.get("data")
        diff = payload.get("diff") if isinstance(payload, Mapping) else None
        if isinstance(diff, list):
            return _map_constituent_rows(diff, _row_source(data, "eastmoney_direct"))

        raise ProviderParseError("constituent fetch failed on both push2 and push2his")

    def fetch_industry_constituents(self, *, symbol: str) -> Any:
        code, did_search = self._find_board_code_cached(symbol, t="2")
        if did_search:
            time.sleep(8.0)  # hard rate-limit window after API pagination
        return self._fetch_constituent_data(
            fs_filter=f"b:BK{code}",
            fields=(
                "f2,f3,f4,f5,f6,f8,f9,f10,f12,f14,f15,f16,f17,f18,"
                "f20,f21,f23,f24,f25,f62,f104,f105,f115,f128,f136,f152,"
                "f124,f107,f140,f141,f207,f208,f209,f222"
            ),
        )

    def fetch_concept_constituents(self, *, symbol: str) -> Any:
        code, did_search = self._find_board_code_cached(symbol, t="3")
        if did_search:
            time.sleep(5.0)
        return self._fetch_constituent_data(
            fs_filter=f"b:BK{code}",
            fields="f2,f3,f4,f8,f12,f14,f15,f16,f17,f18,f20,f21,f24,f25,f62,f104,f105,f128,f124,f107,f136",
        )

    # Hardcoded mapping of common sector/concept names → Eastmoney BK codes.
    # Avoids pagination + rate limiting for the most frequently used boards.
    _KNOWN_BOARDS: dict[str, str] = {
        # Industry sectors
        "2:半导体": "BK1036", "2:芯片": "BK1036", "2:银行": "BK0475",
        "2:证券": "BK0473", "2:保险": "BK0474", "2:白酒": "BK0477",
        "2:医药": "BK0465", "2:军工": "BK0482", "2:煤炭行业": "BK0437",
        "2:电力行业": "BK0428", "2:公用事业": "BK0427", "2:有色金属": "BK0478",
        "2:钢铁": "BK0479", "2:房地产": "BK0451", "2:汽车": "BK0481",
        "2:家电": "BK0456", "2:食品饮料": "BK0438", "2:纺织服装": "BK0453",
        "2:计算机": "BK0447", "2:通信": "BK0448", "2:电子": "BK0449",
        "2:传媒": "BK0458", "2:建筑装饰": "BK0445", "2:建材": "BK0455",
        "2:交通运输": "BK0429", "2:石油石化": "BK0461", "2:化工": "BK0464",
        "2:机械设备": "BK0463", "2:农林牧渔": "BK0476", "2:环保": "BK0466",
        "2:新能源": "BK0493", "2:锂电池": "BK0573", "2:光伏": "BK0472",
        "2:风电": "BK0572", "2:储能": "BK1013", "2:充电桩": "BK0568",
        "2:人工智能": "BK0800", "2:大数据": "BK0637", "2:云计算": "BK0579",
        "2:物联网": "BK0576", "2:5G": "BK0557", "2:机器人": "BK0592",
        # Concept sectors
        "3:芯片": "BK1036", "3:半导体": "BK1036", "3:人工智能": "BK0800",
        "3:新能源车": "BK0900", "3:锂电池": "BK0573", "3:光伏": "BK0472",
        "3:储能": "BK1013", "3:氢能": "BK0864", "3:机器人": "BK0592",
        "3:数字经济": "BK1075", "3:信创": "BK1078", "3:东数西算": "BK1107",
        "3:元宇宙": "BK1090", "3:预制菜": "BK1096", "3:新冠药物": "BK1083",
    }

    # Cache populated at runtime (lazy).
    _board_cache: dict[str, str] = {}

    @classmethod
    def _find_board_code_cached(cls, symbol: str, *, t: str) -> tuple[str, bool]:
        """Return (board_code, did_search). did_search=True means API pagination ran."""
        cache_key = f"{t}:{symbol}"

        # Check hardcoded mapping first.
        known = cls._KNOWN_BOARDS.get(cache_key)
        if known:
            return known, False

        # Check runtime cache.
        cached = cls._board_cache.get(cache_key)
        if cached:
            return cached, False

        # Fallback: paginated API search. Slow and risks rate limiting.
        for pn in range(1, 7):
            data = _eastmoney_get_json(
                "https://push2.eastmoney.com/api/qt/clist/get",
                {
                    "pn": str(pn), "pz": "100", "po": "1", "np": "1",
                    "ut": "bd1d9ddb04089700cf9c27f6f7426281",
                    "fltt": "2", "invt": "2", "fid": "f3",
                    "fs": f"m:90 t:{t} f:!50",
                    "fields": "f12,f14",
                },
            )
            payload = data.get("data")
            diff = payload.get("diff") if isinstance(payload, Mapping) else None
            if not isinstance(diff, list) or not diff:
                break
            for row in diff:
                if isinstance(row, Mapping):
                    name = str(row.get("f14", ""))
                    cd = row.get("f12")
                    if name and cd:
                        cls._board_cache[f"{t}:{name}"] = str(cd)
            cached = cls._board_cache.get(cache_key)
            if cached:
                return cached, True

        raise ProviderParseError(f"unknown board: {symbol!r}")

    def fetch_index_constituents(self, *, symbol: str) -> Any:
        try:
            data = self._ak.index_stock_cons_weight_csindex(symbol=symbol)
            if hasattr(data, "to_dict"):
                return data
        except Exception:
            pass
        try:
            return self._ak.index_stock_cons(symbol=symbol)
        except Exception as exc:
            raise ProviderParseError(
                f"failed to fetch index constituents for {symbol!r}: {exc}"
            ) from exc


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


def _map_constituent_rows(
    rows: list[Mapping[str, Any]], source: str
) -> list[Mapping[str, Any]]:
    """Convert Eastmoney ``clist/get`` field codes to named keys for constituents."""
    out: list[Mapping[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        out.append(
            {
                "代码": row.get("f12"),
                "名称": row.get("f14"),
                "最新价": row.get("f2"),
                "涨跌幅": row.get("f3"),
                "涨跌额": row.get("f4"),
                "成交量": row.get("f5"),
                "成交额": row.get("f6"),
                "换手率": row.get("f8"),
                "市盈率-动态": row.get("f9"),
                "市净率": row.get("f23"),
                "总市值": row.get("f20"),
                "流通市值": row.get("f21"),
                "主力净流入-净额": row.get("f62"),
                "_source": source,
            }
        )
    return out


def _row_source(data: Mapping[str, Any], default: str) -> str:
    source = data.get("_source")
    return str(source) if source else default


def _get(row: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row:
            return row[key]
    return None


def _sort_key(sort_by: str):
    field_map = {
        "change_pct": "change_pct",
        "amount": "amount",
        "volume": "volume",
        "market_cap": "total_market_cap",
        "turnover_rate": "turnover_rate",
        "pe": "pe_dynamic",
        "pb": "pb",
        "weight": "weight",
    }
    attr = field_map.get(sort_by, "change_pct")

    def key(c: StockConstituent) -> float:
        value = getattr(c, attr, None)
        if value is None:
            return float("-inf")
        return float(value)

    return key


class AStockConstituentProvider(SignalProvider):
    provider_id = "astock_constituent"
    display_name = "A-Share Index/Sector/Concept Constituents"
    capabilities = ("astock_constituents",)

    def __init__(self, *, fetcher: ConstituentFetcher | None = None) -> None:
        self._fetcher = fetcher or _AkShareConstituentFetcher()

    # -- public API --

    def get_constituents(self, query: ConstituentQuery) -> ConstituentList:
        scope = query.scope.strip().lower()

        if scope == "industry":
            rows = _records(
                self._fetcher.fetch_industry_constituents(symbol=query.symbol)
            )
        elif scope == "concept":
            rows = _records(
                self._fetcher.fetch_concept_constituents(symbol=query.symbol)
            )
        elif scope == "index":
            rows = _records(
                self._fetcher.fetch_index_constituents(symbol=query.symbol)
            )
        else:
            raise ValueError(
                f"unsupported scope: {query.scope!r} "
                f"(use 'industry', 'concept', or 'index')"
            )

        if not rows:
            raise ProviderParseError(
                f"no constituents returned for {query.symbol!r} (scope={scope})"
            )

        constituents = self._parse_constituents(rows)

        # Deduplicate by (code, name), keeping first occurrence.
        seen: set[tuple[str, str]] = set()
        deduped: list[StockConstituent] = []
        for c in constituents:
            key = (c.code or "", c.name)
            if key not in seen:
                seen.add(key)
                deduped.append(c)
        constituents = deduped

        # Extract a readable name from the data when available.
        display_name = query.symbol
        for row in rows:
            index_name = _get(row, "指数名称")
            if index_name:
                display_name = str(index_name)
                break

        if query.sort_by:
            constituents.sort(key=_sort_key(query.sort_by), reverse=True)
        if query.top_n is not None and query.top_n >= 0:
            constituents = constituents[: query.top_n]

        snapshot = self._build_list(
            symbol=query.symbol,
            name=display_name,
            scope=scope,
            constituents=constituents,
            source=_source_from_rows(rows, f"stock_board_{scope}_cons"),
        )
        return snapshot

    # -- internals --

    @staticmethod
    def _parse_constituents(
        rows: list[Mapping[str, Any]],
    ) -> list[StockConstituent]:
        constituents: list[StockConstituent] = []
        for row in rows:
            code = _get(row, "代码", "品种代码", "成分券代码", "code")
            name = _get(row, "名称", "品种名称", "成分券名称", "name")
            if name is None:
                continue
            constituents.append(
                StockConstituent(
                    code=str(code).strip() if code else None,
                    name=str(name),
                    latest=_coerce_float(_get(row, "最新价", "最新")),
                    change_pct=_coerce_float(_get(row, "涨跌幅")),
                    change_amount=_coerce_float(_get(row, "涨跌额")),
                    volume=_coerce_float(_get(row, "成交量")),
                    amount=_coerce_float(_get(row, "成交额")),
                    turnover_rate=_coerce_float(_get(row, "换手率")),
                    total_market_cap=_coerce_float(_get(row, "总市值", "市值")),
                    circulating_market_cap=_coerce_float(_get(row, "流通市值")),
                    pe_dynamic=_coerce_float(_get(row, "市盈率-动态", "市盈率")),
                    pb=_coerce_float(_get(row, "市净率")),
                    weight=_coerce_float(_get(row, "权重")),
                )
            )
        return constituents

    @staticmethod
    def _build_list(
        *,
        symbol: str,
        name: str,
        scope: str,
        constituents: list[StockConstituent],
        source: str,
    ) -> ConstituentList:
        changes: list[float] = []
        total_amount = 0.0
        total_volume = 0.0
        amount_count = 0
        volume_count = 0
        market_caps: list[float] = []
        up_count = 0
        down_count = 0
        flat_count = 0
        limit_up_count = 0
        limit_down_count = 0

        for c in constituents:
            if c.change_pct is not None:
                changes.append(c.change_pct)
                if c.change_pct > 0:
                    up_count += 1
                elif c.change_pct < 0:
                    down_count += 1
                else:
                    flat_count += 1
                if c.change_pct >= 9.8:
                    limit_up_count += 1
                if c.change_pct <= -9.8:
                    limit_down_count += 1
            if c.amount is not None:
                total_amount += c.amount
                amount_count += 1
            if c.volume is not None:
                total_volume += c.volume
                volume_count += 1
            if c.total_market_cap is not None:
                market_caps.append(c.total_market_cap)

        return ConstituentList(
            symbol=symbol,
            name=name,
            scope=scope,
            total_count=len(constituents),
            up_count=up_count,
            down_count=down_count,
            flat_count=flat_count,
            limit_up_count=limit_up_count,
            limit_down_count=limit_down_count,
            total_amount=total_amount if amount_count else None,
            total_volume=total_volume if volume_count else None,
            average_change_pct=sum(changes) / len(changes) if changes else None,
            median_change_pct=median(changes) if changes else None,
            average_market_cap=sum(market_caps) / len(market_caps) if market_caps else None,
            constituents=tuple(constituents),
            metadata={
                "source": source,
                "amount_count": amount_count,
                "volume_count": volume_count,
                "change_count": len(changes),
                "market_cap_count": len(market_caps),
            },
        )


def _source_from_rows(rows: list[Mapping[str, Any]], default: str) -> str:
    for row in rows:
        source = row.get("_source")
        if source:
            return str(source)
    return default
