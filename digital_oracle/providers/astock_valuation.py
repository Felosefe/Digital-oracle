from __future__ import annotations

import importlib
import os
import sys
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol

from ._coerce import _coerce_float
from .base import ProviderParseError, SignalProvider

from .astock import _configure_astock_network_env


@dataclass(frozen=True)
class ValuationQuery:
    symbol: str = "沪深300"
    lookback_days: int = 252  # ~1 year of trading days


@dataclass(frozen=True)
class FinancialQuery:
    symbol: str
    start_year: str = "2024"


@dataclass
class PePbDay:
    date: str
    index_level: float | None = None
    pe_dynamic: float | None = None          # 动态市盈率
    pe_dynamic_percentile: float | None = None  # 动态市盈率分位 (%)
    pe_static: float | None = None            # 静态市盈率
    pe_static_percentile: float | None = None   # 静态市盈率分位 (%)
    pb: float | None = None                   # 市净率
    pb_percentile: float | None = None         # 市净率分位 (%)
    weighted_pe: float | None = None          # 加权市盈率
    weighted_pb: float | None = None          # 加权市净率


@dataclass
class IndexValuation:
    symbol: str
    latest_date: str | None = None
    latest_pe: float | None = None
    latest_pe_percentile: float | None = None
    latest_pb: float | None = None
    latest_pb_percentile: float | None = None
    latest_index_level: float | None = None
    days: tuple[PePbDay, ...] = ()
    metadata: dict[str, object] = field(default_factory=dict, repr=False)


@dataclass
class StockFinancials:
    symbol: str
    report_date: str | None = None
    eps: float | None = None                   # 基本每股收益
    roe: float | None = None                    # 净资产收益率(%)
    revenue_growth: float | None = None          # 营业收入增长率(%)
    profit_growth: float | None = None           # 净利润增长率(%)
    gross_margin: float | None = None            # 销售毛利率(%)
    net_margin: float | None = None              # 销售净利率(%)
    debt_ratio: float | None = None              # 资产负债率(%)
    current_ratio: float | None = None           # 流动比率
    quick_ratio: float | None = None             # 速动比率
    book_value_per_share: float | None = None    # 每股净资产
    cash_flow_per_share: float | None = None     # 每股经营现金流
    total_assets: float | None = None            # 总资产
    metadata: dict[str, object] = field(default_factory=dict, repr=False)


class ValuationFetcher(Protocol):
    def fetch_index_pe(self, *, symbol: str) -> Any: ...
    def fetch_index_pb(self, *, symbol: str) -> Any: ...
    def fetch_financial_indicators(self, *, symbol: str, start_year: str) -> Any: ...


class _AkShareValuationFetcher:
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
                "akshare is required for AStockValuationProvider but is not installed.\n"
                "Install it with: uv pip install akshare"
            ) from exc

    def fetch_index_pe(self, *, symbol: str) -> Any:
        try:
            return self._ak.stock_index_pe_lg(symbol=symbol)
        except Exception as exc:
            raise ProviderParseError(
                f"failed to fetch index PE for {symbol!r}: {exc}"
            ) from exc

    def fetch_index_pb(self, *, symbol: str) -> Any:
        try:
            return self._ak.stock_index_pb_lg(symbol=symbol)
        except Exception as exc:
            raise ProviderParseError(
                f"failed to fetch index PB for {symbol!r}: {exc}"
            ) from exc

    def fetch_financial_indicators(self, *, symbol: str, start_year: str) -> Any:
        try:
            return self._ak.stock_financial_analysis_indicator(
                symbol=symbol, start_year=start_year,
            )
        except Exception as exc:
            raise ProviderParseError(
                f"failed to fetch financial indicators for {symbol!r}: {exc}"
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


class AStockValuationProvider(SignalProvider):
    provider_id = "astock_valuation"
    display_name = "A-Share Valuation & Fundamentals"
    capabilities = ("astock_valuation", "astock_fundamentals")

    def __init__(self, *, fetcher: ValuationFetcher | None = None) -> None:
        self._fetcher = fetcher or _AkShareValuationFetcher()

    # -- index valuation --

    def get_index_valuation(self, query: ValuationQuery | None = None) -> IndexValuation:
        query = query or ValuationQuery()
        symbol = query.symbol

        pe_rows: list[Mapping[str, Any]] = []
        pb_rows: list[Mapping[str, Any]] = []
        pe_error: str | None = None
        pb_error: str | None = None

        try:
            pe_rows = _records(self._fetcher.fetch_index_pe(symbol=symbol))
        except Exception as exc:
            pe_error = str(exc)

        try:
            pb_rows = _records(self._fetcher.fetch_index_pb(symbol=symbol))
        except Exception as exc:
            pb_error = str(exc)

        if not pe_rows and not pb_rows:
            raise ProviderParseError(
                f"failed to fetch both PE and PB for {symbol!r}"
            )

        # Build date-keyed maps for merging
        pb_by_date: dict[str, Mapping[str, Any]] = {}
        for r in pb_rows:
            d = _normalize_date(_get(r, "日期", "date"))
            if d:
                pb_by_date[d] = r

        pe_by_date: dict[str, Mapping[str, Any]] = {}
        for r in pe_rows:
            d = _normalize_date(_get(r, "日期", "date"))
            if d:
                pe_by_date[d] = r

        # Merge all unique dates from both PE and PB
        all_dates = sorted(set(list(pe_by_date) + list(pb_by_date)))

        days: list[PePbDay] = []
        for d in all_dates:
            pe_row = pe_by_date.get(d, {})
            pb_row = pb_by_date.get(d, {})
            days.append(
                PePbDay(
                    date=d,
                    index_level=_coerce_float(_get(pe_row, "指数") or _get(pb_row, "指数")),
                    pe_dynamic=_coerce_float(_get(pe_row, "动态市盈率")),
                    pe_dynamic_percentile=_coerce_float(_get(pe_row, "动态市盈率分位")),
                    pe_static=_coerce_float(_get(pe_row, "静态市盈率")),
                    pe_static_percentile=_coerce_float(_get(pe_row, "静态市盈率分位")),
                    weighted_pe=_coerce_float(
                        _get(pe_row, "加权静态市盈率", "加权动态市盈率")
                    ),
                    pb=_coerce_float(_get(pb_row, "市净率")),
                    pb_percentile=_coerce_float(_get(pb_row, "市净率分位")),
                    weighted_pb=_coerce_float(_get(pb_row, "加权市净率")),
                )
            )

        days.sort(key=lambda d: d.date)
        if query.lookback_days > 0:
            days = days[-query.lookback_days:]

        latest_pe_val = next((d.pe_dynamic for d in reversed(days) if d.pe_dynamic is not None), None)
        latest_pe_pct = next((d.pe_dynamic_percentile for d in reversed(days) if d.pe_dynamic_percentile is not None), None)
        latest_pb_val = next((d.pb for d in reversed(days) if d.pb is not None), None)
        latest_pb_pct = next((d.pb_percentile for d in reversed(days) if d.pb_percentile is not None), None)
        latest_idx = next((d.index_level for d in reversed(days) if d.index_level is not None), None)
        latest_date_str = days[-1].date if days else None

        return IndexValuation(
            symbol=symbol,
            latest_date=latest_date_str,
            latest_pe=latest_pe_val,
            latest_pe_percentile=latest_pe_pct,
            latest_pb=latest_pb_val,
            latest_pb_percentile=latest_pb_pct,
            latest_index_level=latest_idx,
            days=tuple(days),
            metadata={
                "source": "stock_index_pe_lg/stock_index_pb_lg",
                "pe_error": pe_error,
                "pb_error": pb_error,
            },
        )

    # -- stock financials --

    def get_financials(self, query: FinancialQuery) -> StockFinancials:
        rows = _records(
            self._fetcher.fetch_financial_indicators(
                symbol=query.symbol, start_year=query.start_year,
            )
        )
        if not rows:
            raise ProviderParseError(
                f"no financial data returned for {query.symbol!r}"
            )

        latest = rows[-1]
        return StockFinancials(
            symbol=query.symbol,
            report_date=_normalize_date(_get(latest, "日期", "date")),
            eps=_coerce_float(_get(latest, "基本每股收益(元)", "摊薄每股收益(元)")),
            roe=_coerce_float(_get(latest, "净资产收益率(%)")),
            revenue_growth=_coerce_float(_get(latest, "主营业务收入增长率(%)")),
            profit_growth=_coerce_float(_get(latest, "净利润增长率(%)")),
            gross_margin=_coerce_float(_get(latest, "销售毛利率(%)")),
            net_margin=_coerce_float(_get(latest, "销售净利率(%)")),
            debt_ratio=_coerce_float(_get(latest, "资产负债率(%)")),
            current_ratio=_coerce_float(_get(latest, "流动比率")),
            quick_ratio=_coerce_float(_get(latest, "速动比率")),
            book_value_per_share=_coerce_float(
                _get(latest, "每股净资产_调整后(元)")
            ),
            cash_flow_per_share=_coerce_float(
                _get(latest, "每股经营现金流(元)")
            ),
            total_assets=_coerce_float(_get(latest, "总资产(元)")),
            metadata={"source": "stock_financial_analysis_indicator"},
        )
