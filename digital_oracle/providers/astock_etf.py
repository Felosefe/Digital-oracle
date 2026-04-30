from __future__ import annotations

import importlib
import os
import sys
from dataclasses import dataclass, field
from statistics import median
from typing import Any, Mapping, Protocol

from ._coerce import _coerce_float
from .base import ProviderParseError, SignalProvider

from .astock import _configure_astock_network_env


@dataclass(frozen=True)
class EtfQuery:
    symbol: str = ""
    name_keyword: str = ""
    top_n: int | None = None


@dataclass(frozen=True)
class EtfHistoryQuery:
    symbol: str
    start_date: str | None = None
    end_date: str | None = None
    limit: int | None = None


@dataclass
class EtfSnapshot:
    code: str
    name: str
    latest: float | None = None
    iopv: float | None = None                  # IOPV 实时净值
    premium_pct: float | None = None            # 折溢价率
    change_pct: float | None = None
    change_amount: float | None = None
    volume: float | None = None
    amount: float | None = None
    turnover_rate: float | None = None
    shares_outstanding: float | None = None     # 最新份额
    market_cap: float | None = None             # 总市值
    main_net_inflow: float | None = None        # 主力净流入-净额
    main_net_pct: float | None = None           # 主力净流入-净占比
    update_time: str | None = None
    metadata: dict[str, object] = field(default_factory=dict, repr=False)


@dataclass
class EtfHistoryBar:
    date: str
    open: float | None = None
    close: float | None = None
    high: float | None = None
    low: float | None = None
    volume: float | None = None
    amount: float | None = None
    change_pct: float | None = None
    turnover_rate: float | None = None


@dataclass
class EtfList:
    total_count: int = 0
    snapshots: tuple[EtfSnapshot, ...] = ()
    metadata: dict[str, object] = field(default_factory=dict, repr=False)


class EtfFetcher(Protocol):
    def fetch_etf_spot(self) -> Any: ...
    def fetch_etf_history(self, *, symbol: str, period: str, start_date: str | None, end_date: str | None) -> Any: ...


class _AkShareEtfFetcher:
    def __init__(self) -> None:
        _configure_astock_network_env()
        try:
            self._ak = importlib.import_module("akshare")
            return
        except ImportError:
            pass

        deps = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            os.pardir, os.pardir, ".deps",
        )
        if os.path.isdir(deps) and deps not in sys.path:
            sys.path.insert(0, deps)

        try:
            self._ak = importlib.import_module("akshare")
        except ImportError as exc:
            raise ImportError(
                "akshare is required for AStockEtfProvider but is not installed.\n"
                "Install it with: uv pip install akshare"
            ) from exc

    def fetch_etf_spot(self) -> Any:
        try:
            return self._ak.fund_etf_spot_em()
        except Exception as exc:
            raise ProviderParseError(
                f"failed to fetch ETF spot data: {exc}"
            ) from exc

    def fetch_etf_history(self, *, symbol: str, period: str, start_date: str | None, end_date: str | None) -> Any:
        try:
            return self._ak.fund_etf_hist_em(
                symbol=symbol,
                period=period,
                start_date=start_date or "19700101",
                end_date=end_date or "20500101",
            )
        except Exception as exc:
            raise ProviderParseError(
                f"failed to fetch ETF history for {symbol!r}: {exc}"
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


def _premium_pct(latest: float | None, iopv: float | None) -> float | None:
    if latest and iopv and iopv != 0:
        return (latest - iopv) / iopv * 100
    return None


class AStockEtfProvider(SignalProvider):
    provider_id = "astock_etf"
    display_name = "A-Share ETF Data"
    capabilities = ("astock_etf",)

    def __init__(self, *, fetcher: EtfFetcher | None = None) -> None:
        self._fetcher = fetcher or _AkShareEtfFetcher()

    # -- ETF list / search --

    def list_etfs(self, query: EtfQuery | None = None) -> EtfList:
        query = query or EtfQuery()
        rows = _records(self._fetcher.fetch_etf_spot())
        if not rows:
            raise ProviderParseError("no ETF spot data returned")

        snaps = self._parse_etf_snapshots(rows, query)
        return EtfList(
            total_count=len(snaps),
            snapshots=tuple(snaps),
            metadata={"source": "fund_etf_spot_em", "query_keyword": query.name_keyword},
        )

    # -- ETF history --

    def get_history(self, query: EtfHistoryQuery) -> list[EtfHistoryBar]:
        rows = _records(
            self._fetcher.fetch_etf_history(
                symbol=query.symbol,
                period="daily",
                start_date=query.start_date,
                end_date=query.end_date,
            )
        )
        bars: list[EtfHistoryBar] = []
        for row in rows:
            date = _normalize_date(_get(row, "日期", "date"))
            if date is None:
                continue
            bars.append(
                EtfHistoryBar(
                    date=date,
                    open=_coerce_float(_get(row, "开盘")),
                    close=_coerce_float(_get(row, "收盘")),
                    high=_coerce_float(_get(row, "最高")),
                    low=_coerce_float(_get(row, "最低")),
                    volume=_coerce_float(_get(row, "成交量")),
                    amount=_coerce_float(_get(row, "成交额")),
                    change_pct=_coerce_float(_get(row, "涨跌幅")),
                    turnover_rate=_coerce_float(_get(row, "换手率")),
                )
            )

        bars.sort(key=lambda b: b.date)
        if query.limit is not None and query.limit >= 0:
            bars = bars[-query.limit:]
        return bars

    # -- internals --

    @staticmethod
    def _parse_etf_snapshots(
        rows: list[Mapping[str, Any]], query: EtfQuery
    ) -> list[EtfSnapshot]:
        keyword = query.name_keyword.strip().lower()
        by_symbol = query.symbol.strip()

        snaps: list[EtfSnapshot] = []
        for row in rows:
            code = str(row.get("代码", "") or "")
            name = str(row.get("名称", "") or "")
            if by_symbol and code != by_symbol:
                continue
            if keyword and keyword not in name.lower():
                continue

            latest = _coerce_float(_get(row, "最新价"))
            iopv = _coerce_float(_get(row, "IOPV实时净值"))
            update = _get(row, "更新时间")
            update_str = str(update) if update is not None else None

            snaps.append(
                EtfSnapshot(
                    code=code,
                    name=name,
                    latest=latest,
                    iopv=iopv,
                    premium_pct=(
                        _coerce_float(_get(row, "折溢价率"))
                        or _premium_pct(latest, iopv)
                    ),
                    change_pct=_coerce_float(_get(row, "涨跌幅")),
                    change_amount=_coerce_float(_get(row, "涨跌额")),
                    volume=_coerce_float(_get(row, "成交量")),
                    amount=_coerce_float(_get(row, "成交额")),
                    turnover_rate=_coerce_float(_get(row, "换手率")),
                    shares_outstanding=_coerce_float(_get(row, "最新份额")),
                    market_cap=_coerce_float(_get(row, "总市值")),
                    main_net_inflow=_coerce_float(
                        _get(row, "主力净流入-净额", "主力净流入")
                    ),
                    main_net_pct=_coerce_float(
                        _get(row, "主力净流入-净占比", "主力净流入-占成交额比例")
                    ),
                    update_time=update_str,
                    metadata={"source": "fund_etf_spot_em"},
                )
            )

        if query.top_n is not None and query.top_n >= 0:
            snaps = snaps[: query.top_n]
        return snaps
