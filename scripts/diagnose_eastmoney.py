from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlencode, urlsplit
from urllib.request import ProxyHandler, Request, build_opener

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from digital_oracle.providers.astock import (  # noqa: E402
    _EASTMONEY_HEADERS,
    _eastmoney_candidate_urls,
    _fqt,
    _klt,
    _market_id_for_stock,
    _normalize_stock_code,
)


_PROXY_ENV_NAMES = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
)


@dataclass(frozen=True)
class Endpoint:
    name: str
    url: str
    params: Mapping[str, object]


@dataclass(frozen=True)
class Lane:
    name: str
    transport: str
    proxy: str | None = None


def _stock_endpoint(symbol: str, *, period: str, adjust: str, limit: int) -> Endpoint:
    code = _normalize_stock_code(symbol)
    return Endpoint(
        name="stock",
        url="https://push2his.eastmoney.com/api/qt/stock/kline/get",
        params={
            "secid": f"{_market_id_for_stock(code)}.{code}",
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
            "ut": "7eea3edcaed734bea9cbfc24409ed989",
            "klt": _klt(period),
            "fqt": _fqt(adjust),
            "beg": "19700101",
            "end": "20500101",
            "lmt": str(limit),
        },
    )


def _sectors_endpoint(*, limit: int) -> Endpoint:
    return Endpoint(
        name="sectors",
        url="https://push2.eastmoney.com/api/qt/clist/get",
        params={
            "pn": "1",
            "pz": str(limit),
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


def _sector_history_endpoint(sector_code: str, *, period: str, adjust: str, limit: int) -> Endpoint:
    return Endpoint(
        name="sector",
        url="https://push2his.eastmoney.com/api/qt/stock/kline/get",
        params={
            "secid": f"90.{sector_code.upper()}",
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
            "klt": _klt(period),
            "fqt": _fqt(adjust),
            "beg": "19700101",
            "end": "20500101",
            "lmt": str(limit),
        },
    )


def _lanes(proxy: str | None) -> list[Lane]:
    lanes = [
        Lane(name="curl-direct", transport="curl"),
        Lane(name="urllib-direct", transport="urllib"),
    ]
    if proxy:
        lanes.extend(
            [
                Lane(name="curl-proxy", transport="curl", proxy=proxy),
                Lane(name="urllib-proxy", transport="urllib", proxy=proxy),
            ]
        )
    return lanes


def _request_url(url: str, params: Mapping[str, object]) -> str:
    query = urlencode({k: v for k, v in params.items() if v is not None})
    return f"{url}?{query}"


def _fetch_curl(url: str, *, lane: Lane, timeout: float) -> tuple[int | None, Mapping[str, Any]]:
    curl_requests = __import__("curl_cffi.requests", fromlist=["requests"])
    kwargs: dict[str, Any] = {
        "headers": _EASTMONEY_HEADERS,
        "timeout": timeout,
        "impersonate": "chrome",
    }
    if lane.proxy:
        kwargs["proxies"] = {"http": lane.proxy, "https": lane.proxy}
    else:
        kwargs["proxies"] = {}
    saved_proxy_env = _without_proxy_env()
    try:
        with curl_requests.Session(trust_env=False) as session:
            response = session.get(url, **kwargs)
            status = getattr(response, "status_code", None)
            response.raise_for_status()
            data = response.json()
    finally:
        _restore_no_proxy(saved_proxy_env)
    if not isinstance(data, Mapping):
        raise TypeError("expected JSON object")
    return status, data


def _fetch_urllib(url: str, *, lane: Lane, timeout: float) -> tuple[int | None, Mapping[str, Any]]:
    if lane.proxy:
        opener = build_opener(ProxyHandler({"http": lane.proxy, "https": lane.proxy}))
        saved = _without_no_proxy()
    else:
        opener = build_opener(ProxyHandler({}))
        saved = None
    try:
        request = Request(url, headers=_EASTMONEY_HEADERS)
        with opener.open(request, timeout=timeout) as response:
            status = getattr(response, "status", None)
            payload = response.read().decode("utf-8", errors="replace")
        data = json.loads(payload)
        if not isinstance(data, Mapping):
            raise TypeError("expected JSON object")
        return status, data
    finally:
        if saved is not None:
            _restore_no_proxy(saved)


def _without_no_proxy() -> dict[str, str | None]:
    saved = {"NO_PROXY": os.environ.get("NO_PROXY"), "no_proxy": os.environ.get("no_proxy")}
    os.environ.pop("NO_PROXY", None)
    os.environ.pop("no_proxy", None)
    return saved


def _without_proxy_env() -> dict[str, str | None]:
    saved = {name: os.environ.get(name) for name in _PROXY_ENV_NAMES}
    for name in _PROXY_ENV_NAMES:
        os.environ.pop(name, None)
    return saved


def _apply_network_profile(args: argparse.Namespace) -> None:
    if args.proxy:
        return
    if args.network_profile == "china":
        for name in _PROXY_ENV_NAMES:
            os.environ.pop(name, None)
    elif args.network_profile == "global":
        # Keep shell proxy env vars intact; diagnose direct and proxy lanes separately.
        return


def _restore_no_proxy(saved: Mapping[str, str | None]) -> None:
    for name, value in saved.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value


def _row_count(endpoint: str, data: Mapping[str, Any]) -> int:
    payload = data.get("data")
    if not isinstance(payload, Mapping):
        return 0
    if endpoint == "sectors":
        diff = payload.get("diff")
        return len(diff) if isinstance(diff, list) else 0
    klines = payload.get("klines")
    return len(klines) if isinstance(klines, list) else 0


def _fields_ok(endpoint: str, data: Mapping[str, Any]) -> bool:
    payload = data.get("data")
    if not isinstance(payload, Mapping):
        return False
    if endpoint == "sectors":
        diff = payload.get("diff")
        if not isinstance(diff, list) or not diff:
            return False
        first = diff[0]
        return isinstance(first, Mapping) and all(k in first for k in ("f12", "f14", "f2", "f3"))
    klines = payload.get("klines")
    if not isinstance(klines, list) or not klines:
        return False
    return len(str(klines[0]).split(",")) >= 6


def _diagnose(endpoint: Endpoint, *, lanes: list[Lane], timeout: float, stop_on_success: bool) -> int:
    exit_code = 1
    candidates = _eastmoney_candidate_urls(endpoint.url)
    for lane in lanes:
        for candidate in candidates:
            host = urlsplit(candidate).netloc
            request_url = _request_url(candidate, endpoint.params)
            started = time.perf_counter()
            try:
                if lane.transport == "curl":
                    status, data = _fetch_curl(request_url, lane=lane, timeout=timeout)
                else:
                    status, data = _fetch_urllib(request_url, lane=lane, timeout=timeout)
                elapsed_ms = int((time.perf_counter() - started) * 1000)
                rows = _row_count(endpoint.name, data)
                fields_ok = _fields_ok(endpoint.name, data)
                ok = rows > 0 and fields_ok
                exit_code = 0 if ok else exit_code
                print(
                    f"endpoint={endpoint.name} lane={lane.name} host={host} "
                    f"ok={str(ok).lower()} status={status or 'n/a'} "
                    f"elapsed_ms={elapsed_ms} rows={rows} fields_ok={str(fields_ok).lower()}"
                )
                if ok and stop_on_success:
                    return 0
            except Exception as exc:
                elapsed_ms = int((time.perf_counter() - started) * 1000)
                print(
                    f"endpoint={endpoint.name} lane={lane.name} host={host} "
                    f"ok=false elapsed_ms={elapsed_ms} error={type(exc).__name__}: {exc}"
                )
    return exit_code


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnose Eastmoney transport lanes.")
    parser.add_argument(
        "--endpoint",
        choices=("stock", "sectors", "sector"),
        default="stock",
        help="Eastmoney endpoint family to diagnose.",
    )
    parser.add_argument("--symbol", default="600519", help="A-share stock symbol for stock endpoint.")
    parser.add_argument("--sector-code", default="BK1036", help="Eastmoney BK code for sector history.")
    parser.add_argument("--limit", type=int, default=5, help="Requested row count/page size.")
    parser.add_argument("--timeout", type=float, default=3.0, help="Per-request timeout in seconds.")
    parser.add_argument("--proxy", help="Explicit HTTP/S proxy, for example http://127.0.0.1:7890.")
    parser.add_argument(
        "--network-profile",
        choices=("auto", "china", "global"),
        default="auto",
        help=(
            "china clears proxy env vars before diagnosing; global preserves the "
            "shell proxy env vars; auto preserves current behavior."
        ),
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run every lane/host even after a successful response.",
    )
    args = parser.parse_args()
    _apply_network_profile(args)

    if args.endpoint == "stock":
        endpoint = _stock_endpoint(args.symbol, period="daily", adjust="", limit=args.limit)
    elif args.endpoint == "sectors":
        endpoint = _sectors_endpoint(limit=args.limit)
    else:
        endpoint = _sector_history_endpoint(
            args.sector_code,
            period="daily",
            adjust="",
            limit=args.limit,
        )
    return _diagnose(
        endpoint,
        lanes=_lanes(args.proxy),
        timeout=args.timeout,
        stop_on_success=not args.all,
    )


if __name__ == "__main__":
    raise SystemExit(main())
