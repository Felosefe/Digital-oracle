from __future__ import annotations

import importlib
import os
import sys
from dataclasses import dataclass, field
from statistics import median
from typing import Any, Mapping, Protocol

from ._coerce import _coerce_float, _coerce_int
from .base import ProviderParseError, SignalProvider

# Reuse the same network env setup as AStockProvider.
from .astock import _configure_astock_network_env


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
        _configure_astock_network_env()
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

    def fetch_industry_constituents(self, *, symbol: str) -> Any:
        try:
            return self._ak.stock_board_industry_cons_em(symbol=symbol)
        except Exception as exc:
            raise ProviderParseError(
                f"failed to fetch industry constituents for {symbol!r}: {exc}"
            ) from exc

    def fetch_concept_constituents(self, *, symbol: str) -> Any:
        try:
            return self._ak.stock_board_concept_cons_em(symbol=symbol)
        except Exception as exc:
            raise ProviderParseError(
                f"failed to fetch concept constituents for {symbol!r}: {exc}"
            ) from exc

    def fetch_index_constituents(self, *, symbol: str) -> Any:
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
        if query.sort_by:
            constituents.sort(key=_sort_key(query.sort_by), reverse=True)
        if query.top_n is not None and query.top_n >= 0:
            constituents = constituents[: query.top_n]

        snapshot = self._build_list(
            symbol=query.symbol,
            name=query.symbol,
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
