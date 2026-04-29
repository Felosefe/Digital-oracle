from __future__ import annotations

import importlib
import os
import sys
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol

from ._coerce import _coerce_float, _coerce_int
from .base import ProviderParseError, SignalProvider

# Reuse the same network env setup as AStockProvider to bypass dead proxy env vars.
from .astock import _configure_astock_network_env


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
                "akshare is required for AStockMoneyFlowProvider but is not installed.\n"
                "Install it with: uv pip install akshare"
            ) from exc

    def fetch_individual_flow(self, *, symbol: str) -> Any:
        market = _market_for_stock(symbol)
        try:
            return self._ak.stock_individual_fund_flow(stock=symbol, market=market)
        except TypeError as exc:
            raise ProviderParseError(
                f"no fund flow data available for {symbol!r} "
                f"(market: {market}) — this stock may not be covered by Eastmoney "
                f"fund flow (e.g. BJ exchange or newly listed)"
            ) from exc
        except Exception as exc:
            raise ProviderParseError(
                f"failed to fetch individual fund flow for {symbol!r}: {exc}"
            ) from exc

    def fetch_sector_flow_rank(self, *, sector_type: str) -> Any:
        try:
            return self._ak.stock_sector_fund_flow_rank(
                indicator="今日", sector_type=sector_type
            )
        except Exception as exc:
            raise ProviderParseError(
                f"failed to fetch sector fund flow ranking ({sector_type!r}): {exc}"
            ) from exc

    def fetch_sector_flow_hist(self, *, sector: str) -> Any:
        try:
            return self._ak.stock_sector_fund_flow_hist(symbol=sector)
        except Exception as exc:
            raise ProviderParseError(
                f"failed to fetch sector fund flow history for {sector!r}: {exc}"
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
