from __future__ import annotations

import importlib
import os
import sys
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol

from ._coerce import _coerce_float
from .base import ProviderParseError, SignalProvider

# Reuse AStockProvider's network env setup (DNS bypass + NO_PROXY).
from .astock import _configure_astock_network_env


@dataclass(frozen=True)
class MarginQuery:
    lookback_days: int = 20
    exchange: str = "both"  # sh | sz | both


@dataclass
class MarginDay:
    date: str
    financing_balance: float | None = None   # 融资余额
    financing_buy: float | None = None        # 融资买入额
    short_balance: float | None = None        # 融券余额
    short_sell: float | None = None           # 融券卖出量
    short_volume: float | None = None         # 融券余量
    total_balance: float | None = None        # 融资融券余额


@dataclass
class MarketMargin:
    exchange: str
    lookback_days: int
    latest_date: str | None = None
    latest_financing_balance: float | None = None
    latest_financing_buy: float | None = None
    latest_short_balance: float | None = None
    latest_total_balance: float | None = None
    days: tuple[MarginDay, ...] = ()
    metadata: dict[str, object] = field(default_factory=dict, repr=False)


class MarginFetcher(Protocol):
    def fetch_sh_margin(self) -> Any: ...
    def fetch_sz_margin(self) -> Any: ...


class _AkShareMarginFetcher:
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
                "akshare is required for AStockMarginProvider but is not installed.\n"
                "Install it with: uv pip install akshare"
            ) from exc

    def fetch_sh_margin(self) -> Any:
        try:
            return self._ak.macro_china_market_margin_sh()
        except Exception as exc:
            raise ProviderParseError(
                f"failed to fetch Shanghai margin data: {exc}"
            ) from exc

    def fetch_sz_margin(self) -> Any:
        try:
            return self._ak.macro_china_market_margin_sz()
        except Exception as exc:
            raise ProviderParseError(
                f"failed to fetch Shenzhen margin data: {exc}"
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


class AStockMarginProvider(SignalProvider):
    provider_id = "astock_margin"
    display_name = "A-Share Margin Trading"
    capabilities = ("astock_margin",)

    def __init__(self, *, fetcher: MarginFetcher | None = None) -> None:
        self._fetcher = fetcher or _AkShareMarginFetcher()

    def get_market_margin(self, query: MarginQuery | None = None) -> MarketMargin:
        query = query or MarginQuery()
        exchange = query.exchange.strip().lower()

        if exchange not in ("sh", "sz", "both"):
            raise ValueError(
                f"unsupported exchange: {query.exchange!r} (use 'sh', 'sz', or 'both')"
            )

        sh_days: list[MarginDay] = []
        sz_days: list[MarginDay] = []

        if exchange in ("sh", "both"):
            sh_rows = _records(self._fetcher.fetch_sh_margin())
            sh_days = self._parse_margin_rows(sh_rows, "sh", query.lookback_days)

        if exchange in ("sz", "both"):
            sz_rows = _records(self._fetcher.fetch_sz_margin())
            sz_days = self._parse_margin_rows(sz_rows, "sz", query.lookback_days)

        all_days = sorted(sh_days + sz_days, key=lambda d: (d.date, d.financing_balance or 0))

        latest_sh = sh_days[-1] if sh_days else None
        latest_sz = sz_days[-1] if sz_days else None

        sh_balance = latest_sh.financing_balance if latest_sh else None
        sz_balance = latest_sz.financing_balance if latest_sz else None
        total_balance = (
            (sh_balance or 0) + (sz_balance or 0)
            if (sh_balance or sz_balance) else None
        )

        sh_buy = latest_sh.financing_buy if latest_sh else None
        sz_buy = latest_sz.financing_buy if latest_sz else None

        return MarketMargin(
            exchange=query.exchange,
            lookback_days=query.lookback_days,
            latest_date=(
                latest_sh.date if latest_sh else (latest_sz.date if latest_sz else None)
            ),
            latest_financing_balance=total_balance,
            latest_financing_buy=(sh_buy or 0) + (sz_buy or 0) if (sh_buy or sz_buy) else None,
            latest_short_balance=(
                ((latest_sh.short_balance if latest_sh else 0)
                 + (latest_sz.short_balance if latest_sz else 0))
                if (latest_sh or latest_sz) else None
            ),
            latest_total_balance=(
                ((latest_sh.total_balance if latest_sh else 0)
                 + (latest_sz.total_balance if latest_sz else 0))
                if (latest_sh or latest_sz) else None
            ),
            days=tuple(all_days),
            metadata={
                "source": "macro_china_market_margin",
                "sh_latest_date": latest_sh.date if latest_sh else None,
                "sz_latest_date": latest_sz.date if latest_sz else None,
            },
        )

    @staticmethod
    def _parse_margin_rows(
        rows: list[Mapping[str, Any]], exchange: str, lookback_days: int
    ) -> list[MarginDay]:
        days: list[MarginDay] = []
        for row in rows:
            date = _normalize_date(_get(row, "日期", "date"))
            if date is None:
                continue
            days.append(
                MarginDay(
                    date=date,
                    financing_balance=_coerce_float(_get(row, "融资余额")),
                    financing_buy=_coerce_float(_get(row, "融资买入额")),
                    short_balance=_coerce_float(_get(row, "融券余额")),
                    short_sell=_coerce_float(_get(row, "融券卖出量")),
                    short_volume=_coerce_float(_get(row, "融券余量")),
                    total_balance=_coerce_float(_get(row, "融资融券余额")),
                )
            )

        days.sort(key=lambda d: d.date)
        if lookback_days > 0:
            days = days[-lookback_days:]
        return days
