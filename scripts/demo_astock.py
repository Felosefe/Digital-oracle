from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from digital_oracle import (  # noqa: E402
    AStockBreadthQuery,
    AStockHistoryQuery,
    AStockIndexQuery,
    AStockNorthboundQuery,
    AStockProvider,
    AStockSectorBreadthQuery,
    AStockSectorHistoryQuery,
)


_PROXY_ENV_NAMES = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
)


def _apply_network_profile(args: argparse.Namespace) -> None:
    if args.prefer_domestic:
        args.network_profile = "china"

    if args.proxy:
        os.environ["DIGITAL_ORACLE_ASTOCK_PROXY"] = args.proxy
        os.environ.pop("DIGITAL_ORACLE_ASTOCK_PROXY_MODE", None)
        return

    if args.proxy_mode:
        os.environ["DIGITAL_ORACLE_ASTOCK_PROXY_MODE"] = args.proxy_mode
        os.environ.pop("DIGITAL_ORACLE_ASTOCK_PROXY", None)
        return

    if args.network_profile == "china":
        os.environ.pop("DIGITAL_ORACLE_ASTOCK_PROXY", None)
        os.environ["DIGITAL_ORACLE_ASTOCK_PROXY_MODE"] = "direct"
        for name in _PROXY_ENV_NAMES:
            os.environ.pop(name, None)
        return

    if args.network_profile == "global":
        os.environ.pop("DIGITAL_ORACLE_ASTOCK_PROXY", None)
        os.environ["DIGITAL_ORACLE_ASTOCK_PROXY_MODE"] = "env"
        return

    os.environ.pop("DIGITAL_ORACLE_ASTOCK_PROXY", None)


def _print_history(title: str, history) -> None:
    source = history.metadata.get("source", "unknown")
    print(
        f"[{title}] symbol={history.symbol} raw_symbol={history.raw_symbol} "
        f"interval={history.interval} bars={len(history.bars)} source={source}"
    )
    for bar in history.bars:
        volume = "n/a" if bar.volume is None else f"{bar.volume:.0f}"
        print(
            f"  {bar.date} o={bar.open:.4f} h={bar.high:.4f} "
            f"l={bar.low:.4f} c={bar.close:.4f} v={volume}"
        )
    latest = history.latest
    if latest:
        print(f"[latest] {latest.date} close={latest.close:.4f}")


def _print_breadth(title: str, breadth) -> None:
    source = breadth.metadata.get("source", "unknown")
    level = breadth.metadata.get("breadth_level", "unknown")
    amount = "n/a" if breadth.total_amount is None else f"{breadth.total_amount:.0f}"
    volume = "n/a" if breadth.total_volume is None else f"{breadth.total_volume:.0f}"
    average = (
        "n/a"
        if breadth.average_change_pct is None
        else f"{breadth.average_change_pct:.2f}%"
    )
    median_change = (
        "n/a" if breadth.median_change_pct is None else f"{breadth.median_change_pct:.2f}%"
    )
    print(
        f"[{title}] scope={breadth.scope} symbol={breadth.symbol or 'all'} "
        f"name={breadth.name or 'n/a'} source={source} level={level}"
    )
    print(
        f"  total={breadth.total_count} up={breadth.up_count} "
        f"down={breadth.down_count} flat={breadth.flat_count} "
        f"limit_up={breadth.limit_up_count} limit_down={breadth.limit_down_count}"
    )
    print(f"  amount={amount} volume={volume} avg={average} median={median_change}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch and normalize China A-share market data.")
    parser.add_argument(
        "--view",
        choices=("stock", "index", "sectors", "sector", "breadth", "sector-breadth", "northbound"),
        default="stock",
        help="Which A-share view to print.",
    )
    parser.add_argument("--symbol", default="600519", help="Stock/index/sector symbol or name.")
    parser.add_argument("--limit", type=int, default=5, help="Number of trailing rows to print.")
    parser.add_argument("--start-date", help="Optional inclusive start date, YYYY-MM-DD.")
    parser.add_argument("--end-date", help="Optional inclusive end date, YYYY-MM-DD.")
    parser.add_argument(
        "--mainboard-only",
        action="store_true",
        help="Restrict stock history/snapshots to Shanghai/Shenzhen mainboard codes.",
    )
    parser.add_argument(
        "--proxy",
        help=(
            "HTTP/S proxy for Eastmoney A-share APIs, "
            "for example http://127.0.0.1:7890."
        ),
    )
    parser.add_argument(
        "--proxy-mode",
        choices=("direct", "env"),
        help=(
            "Network route for Eastmoney fallback: direct bypasses proxy env vars; "
            "env honors HTTP_PROXY/HTTPS_PROXY from the shell."
        ),
    )
    parser.add_argument(
        "--network-profile",
        choices=("auto", "china", "global"),
        default="auto",
        help=(
            "Network profile: china clears proxy env vars and prefers domestic direct "
            "routes for Eastmoney; global honors shell proxy env vars; auto keeps the "
            "provider default unless --proxy/--proxy-mode is supplied."
        ),
    )
    parser.add_argument(
        "--prefer-domestic",
        action="store_true",
        help="Shortcut for --network-profile china.",
    )
    args = parser.parse_args()

    _apply_network_profile(args)

    provider = AStockProvider()

    if args.view == "stock":
        history = provider.get_history(
            AStockHistoryQuery(
                symbol=args.symbol,
                start_date=args.start_date,
                end_date=args.end_date,
                limit=args.limit,
                mainboard_only=args.mainboard_only,
            )
        )
        _print_history("astock stock", history)
        return 0

    if args.view == "index":
        history = provider.get_index_history(
            AStockIndexQuery(
                symbol=args.symbol,
                start_date=args.start_date,
                end_date=args.end_date,
                limit=args.limit,
            )
        )
        _print_history("astock index", history)
        return 0

    if args.view == "sectors":
        sectors = provider.list_sector_snapshots()
        print(f"[astock sectors] rows={len(sectors)}")
        for sector in sectors[: args.limit]:
            latest = "n/a" if sector.latest is None else f"{sector.latest:.4f}"
            pct = "n/a" if sector.change_pct is None else f"{sector.change_pct:.2f}%"
            amount = "n/a" if sector.amount is None else f"{sector.amount:.0f}"
            source = sector.metadata.get("source", "unknown")
            print(
                f"  {sector.code or 'n/a'} {sector.name} latest={latest} "
                f"change={pct} amount={amount} source={source}"
            )
        return 0

    if args.view == "sector":
        history = provider.get_sector_history(
            AStockSectorHistoryQuery(
                symbol=args.symbol,
                start_date=args.start_date,
                end_date=args.end_date,
                limit=args.limit,
            )
        )
        _print_history("astock sector", history)
        return 0

    if args.view == "breadth":
        breadth = provider.get_market_breadth(
            AStockBreadthQuery(mainboard_only=args.mainboard_only)
        )
        _print_breadth("astock breadth", breadth)
        return 0

    if args.view == "sector-breadth":
        breadth = provider.get_sector_breadth(AStockSectorBreadthQuery(symbol=args.symbol))
        _print_breadth("astock sector breadth", breadth)
        return 0

    flows = provider.get_northbound_flow(AStockNorthboundQuery(limit=args.limit))
    print(f"[astock northbound] rows={len(flows)}")
    for flow in flows:
        net = "n/a" if flow.net_buy_amount is None else f"{flow.net_buy_amount:.2f}"
        total = (
            "n/a"
            if flow.cumulative_net_buy_amount is None
            else f"{flow.cumulative_net_buy_amount:.2f}"
        )
        hs300 = "n/a" if flow.hs300_change_pct is None else f"{flow.hs300_change_pct:.2f}%"
        print(f"  {flow.date} net_buy={net} cumulative={total} hs300={hs300}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
