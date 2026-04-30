from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from digital_oracle import AStockEtfProvider, EtfQuery, EtfHistoryQuery  # noqa: E402

_PROXY_ENV_NAMES = (
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
    "http_proxy", "https_proxy", "all_proxy",
)


def _apply_network_profile(args: argparse.Namespace) -> None:
    if args.proxy:
        os.environ["DIGITAL_ORACLE_ASTOCK_PROXY"] = args.proxy
        return
    if args.network_profile == "china":
        os.environ["DIGITAL_ORACLE_ASTOCK_PROXY_MODE"] = "direct"
        for name in _PROXY_ENV_NAMES:
            os.environ.pop(name, None)


def _print_etf(snap) -> None:
    premium = "n/a" if snap.premium_pct is None else f"{snap.premium_pct:+.2f}%"
    change = "n/a" if snap.change_pct is None else f"{snap.change_pct:+.2f}%"
    amt = "n/a" if snap.amount is None else f"{snap.amount / 1e8:.2f}亿"
    shares = "n/a" if snap.shares_outstanding is None else f"{snap.shares_outstanding / 1e8:.2f}亿份"
    mcap = "n/a" if snap.market_cap is None else f"{snap.market_cap / 1e8:.2f}亿"
    inflow = "n/a" if snap.main_net_inflow is None else f"{snap.main_net_inflow / 1e4:.0f}万"
    print(
        f"  {snap.code} {snap.name} "
        f"price={snap.latest} change={change} premium={premium} "
        f"amount={amt} shares={shares} mcap={mcap} inflow={inflow}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch A-share ETF data.")
    parser.add_argument(
        "--view",
        choices=("search", "detail", "history"),
        default="search",
        help="What to fetch.",
    )
    parser.add_argument("--symbol", default="", help="ETF code.")
    parser.add_argument("--keyword", default="", help="Name keyword for search.")
    parser.add_argument("--top-n", type=int, default=0, help="Limit search results.")
    parser.add_argument("--limit", type=int, default=20, help="History bars.")
    parser.add_argument("--proxy", help="HTTP/S proxy.")
    parser.add_argument(
        "--network-profile",
        choices=("auto", "china", "global"),
        default="auto",
        help="Network route.",
    )
    args = parser.parse_args()
    _apply_network_profile(args)

    provider = AStockEtfProvider()

    if args.view == "history":
        bars = provider.get_history(EtfHistoryQuery(symbol=args.symbol, limit=args.limit))
        print(f"[etf history] symbol={args.symbol} bars={len(bars)}")
        for b in bars:
            chg = "n/a" if b.change_pct is None else f"{b.change_pct:+.2f}%"
            amt = "n/a" if b.amount is None else f"{b.amount / 1e8:.2f}亿"
            print(f"  {b.date} o={b.open} c={b.close} h={b.high} l={b.low} change={chg} amount={amt}")
        return 0

    result = provider.list_etfs(
        EtfQuery(
            symbol=args.symbol,
            name_keyword=args.keyword,
            top_n=args.top_n if args.top_n > 0 else None,
        )
    )

    print(f"[etf {args.view}] total={result.total_count} keyword={args.keyword!r}")
    for snap in result.snapshots:
        _print_etf(snap)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
