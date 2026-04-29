from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from digital_oracle import (  # noqa: E402
    AStockConstituentProvider,
    ConstituentQuery,
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


def _print_result(result) -> None:
    source = result.metadata.get("source", "unknown")
    amount = "n/a" if result.total_amount is None else f"{result.total_amount / 1e8:.2f}亿"
    avg = "n/a" if result.average_change_pct is None else f"{result.average_change_pct:.2f}%"
    med = "n/a" if result.median_change_pct is None else f"{result.median_change_pct:.2f}%"
    avg_mcap = "n/a" if result.average_market_cap is None else f"{result.average_market_cap / 1e8:.2f}亿"

    print(
        f"[{result.scope}] symbol={result.symbol} name={result.name} "
        f"source={source}"
    )
    print(
        f"  total={result.total_count} up={result.up_count} "
        f"down={result.down_count} flat={result.flat_count} "
        f"limit_up={result.limit_up_count} limit_down={result.limit_down_count}"
    )
    print(
        f"  amount={amount} avg={avg} median={med} avg_mcap={avg_mcap}"
    )
    print()

    for i, c in enumerate(result.constituents, 1):
        code = c.code or "n/a"
        latest = "n/a" if c.latest is None else f"{c.latest:.2f}"
        change = "n/a" if c.change_pct is None else f"{c.change_pct:+.2f}%"
        amt = "n/a" if c.amount is None else f"{c.amount / 1e8:.2f}亿"
        pe = "n/a" if c.pe_dynamic is None else f"{c.pe_dynamic:.1f}"
        pb = "n/a" if c.pb is None else f"{c.pb:.2f}"
        mcap = "n/a" if c.total_market_cap is None else f"{c.total_market_cap / 1e8:.2f}亿"
        w = f" {c.weight:.2f}%" if c.weight is not None else ""
        print(
            f"  {i:>3}. {code} {c.name} "
            f"latest={latest} change={change} amount={amt} "
            f"pe={pe} pb={pb} mcap={mcap}{w}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch A-share index/sector/concept constituents.")
    parser.add_argument(
        "--view",
        choices=("industry", "concept", "index"),
        default="industry",
        help="Constituent scope.",
    )
    parser.add_argument("--symbol", default="半导体", help="Sector/concept name or index code.")
    parser.add_argument(
        "--sort-by",
        choices=("change_pct", "amount", "volume", "market_cap", "turnover_rate", "pe", "pb", "weight"),
        default="change_pct",
        help="Sort constituents by this field (descending).",
    )
    parser.add_argument("--top-n", type=int, default=0, help="Limit to top N (0 = all).")
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

    provider = AStockConstituentProvider()

    result = provider.get_constituents(
        ConstituentQuery(
            symbol=args.symbol,
            scope=args.view,
            sort_by=args.sort_by,
            top_n=args.top_n if args.top_n > 0 else None,
        )
    )
    _print_result(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
