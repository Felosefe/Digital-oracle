from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from digital_oracle import (  # noqa: E402
    AStockMoneyFlowProvider,
    MoneyFlowQuery,
)

_PROXY_ENV_NAMES = (
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
    "http_proxy", "https_proxy", "all_proxy",
)


def _apply_network_profile(args: argparse.Namespace) -> None:
    if args.proxy:
        os.environ["DIGITAL_ORACLE_ASTOCK_PROXY"] = args.proxy
        os.environ.pop("DIGITAL_ORACLE_ASTOCK_PROXY_MODE", None)
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


def _print_snapshot(snap) -> None:
    source = snap.metadata.get("source", "unknown")
    main_net = "n/a" if snap.latest_main_net is None else f"{snap.latest_main_net / 1e8:.2f}亿"
    print(
        f"[{snap.scope}] symbol={snap.symbol} name={snap.name} "
        f"latest_main_net={main_net} inflow_days={snap.consecutive_inflow_days} "
        f"outflow_days={snap.consecutive_outflow_days} source={source}"
    )
    for day in snap.history:
        net = "n/a" if day.main_net_inflow is None else f"{day.main_net_inflow / 1e8:.2f}亿"
        close = "n/a" if day.close is None else f"{day.close:.2f}"
        change = "n/a" if day.change_pct is None else f"{day.change_pct:+.2f}%"
        print(
            f"  {day.date} close={close} change={change} "
            f"main_net={net} super_large={day.super_large_net} large={day.large_net}"
        )


def _print_rank(results) -> None:
    print(f"[rank] rows={len(results)}")
    for i, snap in enumerate(results, 1):
        main_net = "n/a" if snap.latest_main_net is None else f"{snap.latest_main_net / 1e8:.2f}亿"
        print(f"  {i:>2}. {snap.name} main_net={main_net}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch A-share fund flow data.")
    parser.add_argument(
        "--view",
        choices=("individual", "industry", "concept", "rank-industry", "rank-concept"),
        default="rank-industry",
        help="What to fetch.",
    )
    parser.add_argument("--symbol", default="600519", help="Stock code or sector name.")
    parser.add_argument("--lookback", type=int, default=5, help="Number of trading days to look back.")
    parser.add_argument("--top-n", type=int, default=10, help="Number of top entries for ranking.")
    parser.add_argument(
        "--proxy",
        help="HTTP/S proxy for A-share APIs, e.g. http://127.0.0.1:7890.",
    )
    parser.add_argument(
        "--network-profile",
        choices=("auto", "china", "global"),
        default="auto",
        help="Network route for Eastmoney/akshare.",
    )
    args = parser.parse_args()

    _apply_network_profile(args)

    provider = AStockMoneyFlowProvider()

    if args.view in ("rank-industry", "rank-concept"):
        scope = "industry" if args.view == "rank-industry" else "concept"
        results = provider.list_top_flows(scope=scope, top_n=args.top_n)
        _print_rank(results)
        return 0

    snap = provider.get_moneyflow(
        MoneyFlowQuery(
            symbol=args.symbol,
            scope=args.view,
            lookback_days=args.lookback,
        )
    )
    _print_snapshot(snap)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
