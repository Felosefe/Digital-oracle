from __future__ import annotations

import importlib
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol

from ._coerce import _coerce_float, _coerce_int
from .base import ProviderParseError, SignalProvider

# Reuse AStockProvider's battle-tested HTTP layer.
from .astock import (
    _configure_astock_network_env,
    _eastmoney_get_json,
    _market_id_for_stock,
    _normalize_stock_code,
    _parse_kline_items,
)


# Real IPs for Eastmoney CDN hosts, resolved via public DNS to bypass
# Clash fake-IP DNS (198.18.0.x) when the proxy is not forwarding Eastmoney.
_EASTMONEY_REAL_IPS: dict[str, tuple[str, ...]] = {
    "push2.eastmoney.com": ("120.79.191.232", "119.3.232.150", "120.76.218.228"),
    "push2his.eastmoney.com": ("120.79.191.232", "119.3.232.150"),
    # Alternate CDN nodes — map to the same pool.
    "82.push2.eastmoney.com": ("120.79.191.232", "119.3.232.150"),
    "17.push2.eastmoney.com": ("120.79.191.232", "119.3.232.150"),
    "56.push2.eastmoney.com": ("120.79.191.232", "119.3.232.150"),
    "7.push2his.eastmoney.com": ("120.79.191.232", "119.3.232.150"),
    "33.push2his.eastmoney.com": ("120.79.191.232", "119.3.232.150"),
}
_EASTMONEY_HOSTS = frozenset(_EASTMONEY_REAL_IPS)


def _patch_requests_for_astock() -> None:
    """Bypass Clash fake-IP DNS for Eastmoney and prevent stale system proxy.

    Two fixes applied:
    1. Monkey-patch ``socket.getaddrinfo`` to return real IPs for Eastmoney
       CDN hosts, bypassing the Clash fake-IP DNS (198.18.0.x).
    2. Set ``NO_PROXY=*`` so ``requests`` does not pick up a dead system
       proxy from the Windows registry.
    """
    import socket as _socket
    import os as _os

    _configure_astock_network_env()

    # -- 1. DNS bypass -------------------------------------------------------
    _real_getaddrinfo = _socket.getaddrinfo

    def _patched_getaddrinfo(  # noqa: D417
        host, port, family=0, type=0, proto=0, flags=0
    ):
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
    # Also patch the create_connection helper used by urllib3/requests.
    try:
        import urllib3.util.connection as _uconn
        _orig_create = _uconn.create_connection

        def _patched_create(address, *args, **kwargs):
            host, port = address
            if host in _EASTMONEY_HOSTS:
                addresses = []
                for ip in _EASTMONEY_REAL_IPS[host]:
                    addresses.append((ip, port))
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

    # -- 2. Stale proxy bypass ----------------------------------------------
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
class MoneyFlowQuery:
    """Query for a single entity's fund flow history.

    ``symbol`` is the stock code (e.g. "600519") for individual scope,
    or the sector name (e.g. "半导体") for industry/concept scope.
    """

    symbol: str
    scope: str = "individual"  # individual | industry | concept
    lookback_days: int = 5


@dataclass
class MoneyFlowDay:
    date: str
    close: float | None = None
    change_pct: float | None = None
    main_net_inflow: float | None = None
    super_large_net: float | None = None
    large_net: float | None = None
    medium_net: float | None = None
    small_net: float | None = None


@dataclass
class MoneyFlowSnapshot:
    symbol: str
    name: str
    scope: str
    latest_main_net: float | None = None
    total_main_net: float | None = None
    consecutive_inflow_days: int = 0
    consecutive_outflow_days: int = 0
    main_strength_pct: float | None = None
    history: tuple[MoneyFlowDay, ...] = ()
    metadata: dict[str, object] = field(default_factory=dict, repr=False)


class MoneyFlowFetcher(Protocol):
    def fetch_individual_flow(self, *, symbol: str) -> Any: ...
    def fetch_sector_flow_rank(self, *, sector_type: str) -> Any: ...
    def fetch_sector_flow_hist(self, *, sector: str) -> Any: ...


def _market_for_stock(symbol: str) -> str:
    code = symbol.strip()
    if code.startswith(("5", "6", "9")):
        return "sh"
    if code.startswith(("0", "1", "2", "3")):
        return "sz"
    if code.startswith(("4", "8")):
        return "bj"
    raise ProviderParseError(f"cannot determine market for stock: {symbol!r}")


class _AkShareMoneyFlowFetcher:
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
                "akshare is required for AStockMoneyFlowProvider but is not installed.\n"
                "Install it with: uv pip install akshare"
            ) from exc

    def fetch_individual_flow(self, *, symbol: str) -> Any:
        market_id = _market_id_for_stock(symbol)
        data = _eastmoney_get_json(
            "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get",
            {
                "secid": f"{market_id}.{_normalize_stock_code(symbol)}",
                "fields1": "f1,f2,f3,f4",
                "fields2": "f51,f52,f53,f54,f55,f56,f57",
                "lmt": "60",
                "klt": "101",
            },
        )
        payload = data.get("data")
        klines = payload.get("klines") if isinstance(payload, Mapping) else None
        if not klines:
            raise ProviderParseError(
                f"no fund flow data available for {symbol!r} — "
                f"this stock may not be covered (e.g. BJ exchange or newly listed)"
            )
        return _parse_fflow_klines(klines, _row_source(data, "eastmoney_direct"))

    def fetch_sector_flow_rank(self, *, sector_type: str) -> Any:
        t = "2" if "行业" in sector_type else "3"
        data = _eastmoney_get_json(
            "https://push2.eastmoney.com/api/qt/clist/get",
            {
                "pn": "1", "pz": "100", "po": "1", "np": "1",
                "ut": "b2884a393a59ad64002292a3e90d46a5",
                "fltt": "2", "invt": "2", "fid0": "f62",
                "fs": f"m:90 t:{t}",
                "stat": "1",
                "fields": "f12,f14,f2,f3,f62,f184,f66,f69,f72,f75,f78,f81,f84,f87,f204,f205,f124",
            },
        )
        payload = data.get("data")
        diff = payload.get("diff") if isinstance(payload, Mapping) else None
        if not isinstance(diff, list):
            raise ProviderParseError("missing sector fund flow rank rows")
        return _map_clist_rows(diff, _row_source(data, "eastmoney_direct"))

    def fetch_sector_flow_hist(self, *, sector: str) -> Any:
        # Look up sector code via paginated clist/get.
        sector_code = None
        for pn in range(1, 7):
            search = _eastmoney_get_json(
                "https://push2.eastmoney.com/api/qt/clist/get",
                {
                    "pn": str(pn), "pz": "100", "po": "1", "np": "1",
                    "ut": "bd1d9ddb04089700cf9c27f6f7426281",
                    "fltt": "2", "invt": "2", "fid": "f3",
                    "fs": "m:90 t:2 f:!50",
                    "fields": "f12,f14",
                },
            )
            s_payload = search.get("data")
            s_diff = s_payload.get("diff") if isinstance(s_payload, Mapping) else None
            if not isinstance(s_diff, list) or not s_diff:
                break
            for row in s_diff:
                if isinstance(row, Mapping) and str(row.get("f14", "")) == sector:
                    sector_code = row.get("f12")
                    break
            if sector_code:
                break
        if sector_code is None:
            raise ProviderParseError(f"unknown A-share sector: {sector!r}")

        time.sleep(0.6)  # avoid rate limiting after pagination
        data = _eastmoney_get_json(
            "https://push2his.eastmoney.com/api/qt/stock/kline/get",
            {
                "secid": f"90.{sector_code}",
                "fields1": "f1,f2,f3,f4,f5,f6",
                "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
                "klt": "101",
                "fqt": "0",
                "beg": "19700101",
                "end": "20500101",
                "lmt": "100",
            },
        )
        k_payload = data.get("data")
        klines = k_payload.get("klines") if isinstance(k_payload, Mapping) else None
        return _parse_kline_items(klines)


def _parse_fflow_klines(
    items: object, source: str
) -> list[Mapping[str, Any]]:
    """Parse Eastmoney fflow/daykline kline items into named rows.

    fields2 ordering from akshare: f51=date, f52=main_net, f53=small_net,
    f54=medium_net, f55=large_net, f56=super_large_net, f57=main_net_pct.
    """
    if not isinstance(items, list):
        return []
    rows: list[Mapping[str, Any]] = []
    for item in items:
        parts = str(item).split(",")
        if len(parts) < 7:
            continue
        rows.append(
            {
                "日期": parts[0],          # f51 date
                "主力净流入-净额": parts[1],  # f52 main_net_inflow
                "小单净流入-净额": parts[2],  # f53 small_net
                "中单净流入-净额": parts[3],  # f54 medium_net
                "大单净流入-净额": parts[4],  # f55 large_net
                "超大单净流入-净额": parts[5],  # f56 super_large_net
                "主力净流入-净占比": parts[6],  # f57 main_net_pct
                "_source": source,
            }
        )
    return rows


def _map_clist_rows(
    rows: list[Mapping[str, Any]], source: str
) -> list[Mapping[str, Any]]:
    """Convert Eastmoney ``clist/get`` field codes to named keys."""
    out: list[Mapping[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        out.append(
            {
                "code": row.get("f12"),
                "名称": row.get("f14"),
                "最新价": row.get("f2"),
                "涨跌幅": row.get("f3"),
                "主力净流入-净额": row.get("f62"),
                "主力净流入-净占比": row.get("f184"),
                "超大单净流入-净额": row.get("f66"),
                "超大单净流入-净占比": row.get("f69"),
                "大单净流入-净额": row.get("f72"),
                "大单净流入-净占比": row.get("f75"),
                "中单净流入-净额": row.get("f78"),
                "中单净流入-净占比": row.get("f81"),
                "小单净流入-净额": row.get("f84"),
                "小单净流入-净占比": row.get("f87"),
                "_source": source,
            }
        )
    return out


def _row_source(data: Mapping[str, Any], default: str) -> str:
    source = data.get("_source")
    return str(source) if source else default


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


def _get(row: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row:
            return row[key]
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


def _compute_consecutive_days(history: tuple[MoneyFlowDay, ...]) -> tuple[int, int]:
    inflow_days = 0
    outflow_days = 0
    for day in reversed(history):
        net = day.main_net_inflow
        if net is None:
            break
        if net > 0:
            if outflow_days > 0:
                break
            inflow_days += 1
        elif net < 0:
            if inflow_days > 0:
                break
            outflow_days += 1
        else:
            break
    return inflow_days, outflow_days


class AStockMoneyFlowProvider(SignalProvider):
    provider_id = "astock_moneyflow"
    display_name = "A-Share Fund Flow"
    capabilities = ("astock_moneyflow",)

    def __init__(self, *, fetcher: MoneyFlowFetcher | None = None) -> None:
        self._fetcher = fetcher or _AkShareMoneyFlowFetcher()

    def get_moneyflow(self, query: MoneyFlowQuery) -> MoneyFlowSnapshot:
        scope = query.scope.strip().lower()

        if scope == "individual":
            return self._get_individual_flow(query)
        if scope in ("industry", "concept"):
            return self._get_sector_flow(query, sector_type=self._sector_type(scope))

        raise ValueError(
            f"unsupported scope: {query.scope!r} (use 'individual', 'industry', or 'concept')"
        )

    def list_top_flows(
        self, *, scope: str = "industry", top_n: int = 20
    ) -> list[MoneyFlowSnapshot]:
        scope = scope.strip().lower()
        if scope not in ("industry", "concept"):
            raise ValueError(
                f"unsupported scope: {scope!r} (use 'industry' or 'concept')"
            )

        rows = _records(
            self._fetcher.fetch_sector_flow_rank(sector_type=self._sector_type(scope))
        )
        snapshots: list[MoneyFlowSnapshot] = []
        for row in rows[:top_n]:
            name = _get(row, "名称") or _get(row, "name") or ""
            if not name:
                continue
            snapshots.append(
                MoneyFlowSnapshot(
                    symbol=str(name),
                    name=str(name),
                    scope=scope,
                    latest_main_net=_coerce_float(
                        _get(row, "今日主力净流入-净额", "主力净流入-净额")
                    ),
                    total_main_net=_coerce_float(
                        _get(row, "今日主力净流入-净额", "主力净流入-净额")
                    ),
                    metadata={"source": "stock_sector_fund_flow_rank"},
                )
            )
        return snapshots

    def _get_individual_flow(self, query: MoneyFlowQuery) -> MoneyFlowSnapshot:
        rows = _records(self._fetcher.fetch_individual_flow(symbol=query.symbol))
        if not rows:
            raise ProviderParseError(
                f"no fund flow data returned for {query.symbol!r}"
            )

        history = self._parse_flow_rows(rows, query.lookback_days)
        inflow_days, outflow_days = _compute_consecutive_days(history)
        latest = history[-1] if history else None

        latest_main = latest.main_net_inflow if latest else None

        # Calculate main strength = latest main_net / latest amount
        # We approximate "amount" from the average of net flows
        main_strength = None
        total_main = sum(
            (day.main_net_inflow or 0.0)
            for day in history
            if day.main_net_inflow is not None
        )
        abs_total = sum(abs(day.main_net_inflow or 0.0) for day in history)

        return MoneyFlowSnapshot(
            symbol=query.symbol,
            name=query.symbol,
            scope="individual",
            latest_main_net=latest_main,
            total_main_net=total_main if history else None,
            consecutive_inflow_days=inflow_days,
            consecutive_outflow_days=outflow_days,
            main_strength_pct=main_strength,
            history=history,
            metadata={"source": "stock_individual_fund_flow", "lookback_days": query.lookback_days},
        )

    def _get_sector_flow(
        self, query: MoneyFlowQuery, *, sector_type: str
    ) -> MoneyFlowSnapshot:
        rows = _records(self._fetcher.fetch_sector_flow_hist(sector=query.symbol))
        if not rows:
            raise ProviderParseError(
                f"no fund flow data returned for sector {query.symbol!r}"
            )

        history = self._parse_flow_rows(rows, query.lookback_days)
        inflow_days, outflow_days = _compute_consecutive_days(history)
        latest = history[-1] if history else None

        return MoneyFlowSnapshot(
            symbol=query.symbol,
            name=query.symbol,
            scope=query.scope,
            latest_main_net=latest.main_net_inflow if latest else None,
            total_main_net=sum(
                (day.main_net_inflow or 0.0) for day in history
            ) if history else None,
            consecutive_inflow_days=inflow_days,
            consecutive_outflow_days=outflow_days,
            history=history,
            metadata={
                "source": "stock_sector_fund_flow_hist",
                "lookback_days": query.lookback_days,
                "sector_type": sector_type,
            },
        )

    @staticmethod
    def _parse_flow_rows(
        rows: list[Mapping[str, Any]], lookback_days: int
    ) -> tuple[MoneyFlowDay, ...]:
        days: list[MoneyFlowDay] = []
        for row in rows:
            date = _normalize_date(_get(row, "日期", "date"))
            if date is None:
                continue

            days.append(
                MoneyFlowDay(
                    date=date,
                    close=_coerce_float(_get(row, "收盘价", "close")),
                    change_pct=_coerce_float(_get(row, "涨跌幅", "change_pct", "pctChg")),
                    main_net_inflow=_coerce_float(
                        _get(row, "主力净流入-净额", "主力净流入")
                    ),
                    super_large_net=_coerce_float(
                        _get(row, "超大单净流入-净额", "超大单净流入")
                    ),
                    large_net=_coerce_float(
                        _get(row, "大单净流入-净额", "大单净流入")
                    ),
                    medium_net=_coerce_float(
                        _get(row, "中单净流入-净额", "中单净流入")
                    ),
                    small_net=_coerce_float(
                        _get(row, "小单净流入-净额", "小单净流入")
                    ),
                )
            )

        days.sort(key=lambda d: d.date)
        if lookback_days > 0:
            days = days[-lookback_days:]
        return tuple(days)

    @staticmethod
    def _sector_type(scope: str) -> str:
        if scope == "industry":
            return "行业资金流"
        if scope == "concept":
            return "概念资金流"
        raise ValueError(f"unsupported scope: {scope!r}")
