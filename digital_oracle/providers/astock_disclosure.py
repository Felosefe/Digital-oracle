from __future__ import annotations

import importlib
import os
import sys
from dataclasses import dataclass, field
from datetime import date as date_type
from typing import Any, Mapping, Protocol

from .base import ProviderParseError, SignalProvider

from .astock import _configure_astock_network_env, _eastmoney_get_json


@dataclass(frozen=True)
class DisclosureQuery:
    symbol: str = ""           # stock code, empty = all
    date: str = ""             # YYYYMMDD, empty = today
    keyword: str = ""          # keyword in title
    category: str = ""         # notice category filter
    top_n: int | None = None


@dataclass
class StockNotice:
    code: str
    name: str
    title: str
    category: str
    date: str
    url: str


@dataclass
class NoticeList:
    total_count: int = 0
    notices: tuple[StockNotice, ...] = ()
    metadata: dict[str, object] = field(default_factory=dict, repr=False)


class DisclosureFetcher(Protocol):
    def fetch_notices(self, *, symbol: str, date: str) -> Any: ...


class _AkShareDisclosureFetcher:
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
                "akshare is required for AStockDisclosureProvider but is not installed.\n"
                "Install it with: uv pip install akshare"
            ) from exc

    def fetch_notices(self, *, symbol: str, date: str) -> Any:
        """Fallback: akshare (fetches all pages, may be slow)."""
        try:
            return self._ak.stock_notice_report(symbol=symbol, date=date)
        except Exception as exc:
            raise ProviderParseError(
                f"failed to fetch notices: {exc}"
            ) from exc


class _EastmoneyDisclosureFetcher:
    """Direct Eastmoney HTTP layer — faster, pagination-controllable."""

    def __init__(self) -> None:
        _configure_astock_network_env()

    def fetch_page(self, *, date: str, page_index: int, page_size: int = 100) -> Any:
        from datetime import date as dt
        d = dt.today().isoformat() if not date else (
            f"{date[:4]}-{date[4:6]}-{date[6:]}" if len(date) == 8 else date
        )
        data = _eastmoney_get_json(
            "https://np-anotice-stock.eastmoney.com/api/security/ann",
            {
                "sr": "-1",
                "page_size": str(page_size),
                "page_index": str(page_index),
                "ann_type": "A",
                "client_source": "web",
                "f_node": "0",
                "s_node": "0",
                "begin_time": d,
                "end_time": d,
            },
        )
        payload = data.get("data")
        if not isinstance(payload, dict):
            raise ProviderParseError("missing notice data in response")
        return payload


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


def _parse_notice_category(columns_raw: object) -> str:
    """Parse Eastmoney notice columns JSON into a readable category."""
    if not isinstance(columns_raw, str) or not columns_raw:
        return ""
    import json as _json
    try:
        cols = _json.loads(columns_raw)
        if isinstance(cols, list) and cols:
            return str(cols[0].get("column_name", ""))
    except (_json.JSONDecodeError, TypeError, KeyError):
        pass
    return ""


def _parse_notice_codes(codes_raw: object) -> tuple[str, str]:
    """Parse Eastmoney notice codes JSON into (stock_code, stock_name)."""
    if not isinstance(codes_raw, str) or not codes_raw:
        return "", ""
    import json as _json
    try:
        codes = _json.loads(codes_raw.replace("'", '"'))
        if isinstance(codes, list) and codes:
            c = codes[0]
            return (
                str(c.get("stock_code", "") or c.get("inner_code", "") or ""),
                str(c.get("short_name", "") or ""),
            )
    except (_json.JSONDecodeError, TypeError, KeyError):
        pass
    return "", ""


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


class AStockDisclosureProvider(SignalProvider):
    provider_id = "astock_disclosure"
    display_name = "A-Share Disclosures & Events"
    capabilities = ("astock_disclosure",)

    def __init__(self, *, fetcher: DisclosureFetcher | None = None) -> None:
        self._fetcher = fetcher or _AkShareDisclosureFetcher()
        self._direct = _EastmoneyDisclosureFetcher()

    def list_notices(self, query: DisclosureQuery | None = None) -> NoticeList:
        query = query or DisclosureQuery()

        symbol = query.symbol.strip() or "全部"
        date_str = query.date.strip()
        if not date_str:
            date_str = date_type.today().strftime("%Y%m%d")

        keyword = query.keyword.strip().lower()
        category = query.category.strip().lower()
        specified_symbol = symbol != "全部"

        top_n = query.top_n

        # Use direct Eastmoney API with capped pagination.
        notices: list[StockNotice] = []
        total_hits = 0
        max_pages = 5 if (keyword or specified_symbol or category) else 3

        for page in range(1, max_pages + 1):
            payload = self._direct.fetch_page(date=date_str, page_index=page)
            total_hits = payload.get("total_hits", 0)
            items = payload.get("list")
            if not isinstance(items, list) or not items:
                break

            for item in items:
                if not isinstance(item, dict):
                    continue

                title = str(item.get("title_ch", "") or item.get("title", ""))
                cat = _parse_notice_category(item.get("columns", ""))

                if keyword and keyword not in title.lower():
                    continue
                if category and category not in cat.lower():
                    continue

                code, name = _parse_notice_codes(item.get("codes", ""))
                if specified_symbol and code != symbol:
                    continue

                art = str(item.get("art_code", "") or "")
                url = (
                    f"https://data.eastmoney.com/notices/detail/"
                    f"{code}/{art}.html"
                ) if (code and art) else ""
                d = _normalize_date(item.get("notice_date", ""))

                notices.append(
                    StockNotice(
                        code=code,
                        name=name,
                        title=title,
                        category=cat,
                        date=d or date_str,
                        url=url,
                    )
                )

                if top_n is not None and top_n >= 0 and len(notices) >= top_n:
                    break

            if top_n is not None and top_n >= 0 and len(notices) >= top_n:
                break

            if page >= total_hits / 100:
                break

        # Trim to top_n if we overshot
        if top_n is not None and top_n >= 0:
            notices = notices[:top_n]

        return NoticeList(
            total_count=len(notices),
            notices=tuple(notices),
            metadata={
                "source": "np-anotice-stock",
                "date": date_str,
                "raw_total": total_hits,
                "keyword": query.keyword,
                "category": query.category,
            },
        )
