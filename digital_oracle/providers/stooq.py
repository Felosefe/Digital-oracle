from __future__ import annotations

import csv
import re
import os
from datetime import datetime
from io import StringIO
from dataclasses import dataclass, field
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .base import ProviderParseError, SignalProvider
from .prices import PriceBar, PriceHistory, PriceHistoryQuery
from .yahoo import PriceFetcher, YahooPriceProvider

_STOOQ_SYMBOL_MAP = {
    "cb.c": "BZ=F",
    "cl.c": "CL=F",
    "eurusd": "EURUSD=X",
    "gbpusd": "GBPUSD=X",
    "hg.c": "HG=F",
    "ng.c": "NG=F",
    "usdchf": "USDCHF=X",
    "usdcny": "USDCNY=X",
    "usdjpy": "USDJPY=X",
    "usdrub": "USDRUB=X",
    "usdtwd": "USDTWD=X",
    "xagusd": "SI=F",
    "xauusd": "GC=F",
    "zc.c": "ZC=F",
    "zs.c": "ZS=F",
    "zw.c": "ZW=F",
}


def _to_yahoo_symbol(symbol: str) -> str:
    normalized = symbol.strip()
    lowered = normalized.lower()
    if lowered in _STOOQ_SYMBOL_MAP:
        return _STOOQ_SYMBOL_MAP[lowered]

    if lowered.endswith(".us"):
        return lowered[:-3].upper()

    if len(lowered) == 6 and lowered.isalpha():
        return f"{lowered.upper()}=X"

    return normalized.upper()


def _compact_date(value: str | None) -> str | None:
    if not value:
        return None
    return value.replace("-", "")


def _to_float(value: str | None) -> float | None:
    if value is None or value in ("", "N/D", "-"):
        return None
    return float(value.replace(",", "").strip())


def _parse_stooq_date(value: str) -> str:
    value = " ".join(value.split())
    try:
        return datetime.strptime(value, "%d %b %Y").strftime("%Y-%m-%d")
    except ValueError:
        return value


def _strip_tags(value: str) -> str:
    return re.sub(r"<[^>]+>", "", value).replace("&nbsp;", " ").strip()


def _parse_stooq_html_table(payload: str, query: PriceHistoryQuery) -> PriceHistory:
    bars: list[PriceBar] = []
    for row_html in re.findall(r"<tr[^>]*>(.*?)</tr>", payload, flags=re.IGNORECASE | re.DOTALL):
        cells = [
            _strip_tags(cell)
            for cell in re.findall(r"<td[^>]*>(.*?)</td>", row_html, flags=re.IGNORECASE | re.DOTALL)
        ]
        if len(cells) < 7:
            continue
        if not cells[0].isdigit():
            continue

        open_price = _to_float(cells[2])
        high_price = _to_float(cells[3])
        low_price = _to_float(cells[4])
        close_price = _to_float(cells[5])
        if any(v is None for v in (open_price, high_price, low_price, close_price)):
            continue

        date = _parse_stooq_date(cells[1])
        if query.start_date and date < query.start_date:
            continue
        if query.end_date and date > query.end_date:
            continue

        bars.append(
            PriceBar(
                date=date,
                open=open_price,
                high=high_price,
                low=low_price,
                close=close_price,
                volume=_to_float(cells[7]) if len(cells) > 7 else None,
            )
        )

    bars.sort(key=lambda bar: bar.date)
    if query.limit is not None and query.limit >= 0:
        bars = bars[-query.limit:]

    if not bars:
        raise ProviderParseError(f"no Stooq HTML price rows returned for {query.symbol!r}")

    return PriceHistory(
        symbol=query.symbol.strip().lower(),
        raw_symbol=query.symbol,
        interval=query.interval.lower().strip(),
        provider_id="stooq",
        bars=tuple(bars),
        metadata={"source": "stooq_html"},
    )


def _fetch_stooq_history(query: PriceHistoryQuery) -> PriceHistory:
    interval = query.interval.lower().strip()
    if interval not in {"d", "w", "m"}:
        raise ValueError(f"unsupported interval: {query.interval!r} (use 'd', 'w', or 'm')")

    params: dict[str, str] = {
        "s": query.symbol.strip().lower(),
        "i": interval,
    }
    api_key = os.environ.get("STOOQ_API_KEY")
    if api_key:
        params["apikey"] = api_key
    start_date = _compact_date(query.start_date)
    end_date = _compact_date(query.end_date)
    if start_date:
        params["d1"] = start_date
    if end_date:
        params["d2"] = end_date

    url = f"https://stooq.com/q/d/l/?{urlencode(params)}"
    request = Request(url, headers={"User-Agent": "digital-oracle/0.1"})
    with urlopen(request, timeout=20.0) as response:
        payload = response.read().decode("utf-8-sig")

    if "Get your apikey" in payload:
        html_params: dict[str, str] = {
            "s": query.symbol.strip().lower(),
        }
        html_url = f"https://stooq.com/q/d/?{urlencode(html_params)}"
        html_request = Request(html_url, headers={"User-Agent": "digital-oracle/0.1"})
        with urlopen(html_request, timeout=20.0) as response:
            html_payload = response.read().decode("utf-8", errors="replace")
        return _parse_stooq_html_table(html_payload, query)

    rows = list(csv.DictReader(StringIO(payload)))
    bars: list[PriceBar] = []
    for row in rows:
        date = row.get("Date")
        open_price = _to_float(row.get("Open"))
        high_price = _to_float(row.get("High"))
        low_price = _to_float(row.get("Low"))
        close_price = _to_float(row.get("Close"))
        if not date or any(v is None for v in (open_price, high_price, low_price, close_price)):
            continue

        bars.append(
            PriceBar(
                date=date,
                open=open_price,
                high=high_price,
                low=low_price,
                close=close_price,
                volume=_to_float(row.get("Volume")),
            )
        )

    if query.limit is not None and query.limit >= 0:
        bars = bars[-query.limit:]

    if not bars:
        raise ProviderParseError(f"no Stooq price rows returned for {query.symbol!r}")

    return PriceHistory(
        symbol=query.symbol.strip().lower(),
        raw_symbol=query.symbol,
        interval=interval,
        provider_id="stooq",
        bars=tuple(bars),
        metadata={"source": "stooq_csv"},
    )


@dataclass
class StooqProvider(SignalProvider):
    """Backward-compatible price provider backed by Yahoo Finance."""

    provider_id: str = "stooq"
    display_name: str = "Stooq (compat via Yahoo Finance)"
    capabilities: tuple[str, ...] = ("price_history",)
    _provider: YahooPriceProvider = field(init=False, repr=False)

    def __init__(
        self,
        *,
        fetcher: PriceFetcher | None = None,
        yahoo_provider: YahooPriceProvider | None = None,
    ) -> None:
        object.__setattr__(
            self,
            "_provider",
            yahoo_provider or YahooPriceProvider(fetcher=fetcher),
        )

    def get_history(self, query: PriceHistoryQuery) -> PriceHistory:
        mapped_symbol = _to_yahoo_symbol(query.symbol)
        try:
            delegated = self._provider.get_history(
                PriceHistoryQuery(
                    symbol=mapped_symbol,
                    interval=query.interval,
                    start_date=query.start_date,
                    end_date=query.end_date,
                    limit=query.limit,
                )
            )
            return PriceHistory(
                symbol=delegated.symbol,
                raw_symbol=query.symbol,
                interval=delegated.interval,
                provider_id=self.provider_id,
                bars=delegated.bars,
                metadata={
                    **delegated.metadata,
                    "source_symbol": query.symbol,
                    "yahoo_symbol": mapped_symbol,
                    "source": "yahoo",
                },
            )
        except Exception:
            return _fetch_stooq_history(query)
