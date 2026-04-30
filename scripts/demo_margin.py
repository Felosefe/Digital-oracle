from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from digital_oracle import AStockMarginProvider, MarginQuery  # noqa: E402

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


def _print_margin(result) -> None:
    source = result.metadata.get("source", "unknown")
    sh_date = result.metadata.get("sh_latest_date", "n/a")
    sz_date = result.metadata.get("sz_latest_date", "n/a")

    fin_bal = "n/a" if result.latest_financing_balance is None else f"{result.latest_financing_balance / 1e8:.2f}亿"
    fin_buy = "n/a" if result.latest_financing_buy is None else f"{result.latest_financing_buy / 1e8:.2f}亿"
    short_bal = "n/a" if result.latest_short_balance is None else f"{result.latest_short_balance / 1e8:.2f}亿"
    total_bal = "n/a" if result.latest_total_balance is None else f"{result.latest_total_balance / 1e8:.2f}亿"

    leverage = "n/a"
    if result.latest_financing_balance and result.latest_financing_buy and result.latest_financing_balance > 0:
        ratio = result.latest_financing_buy / result.latest_financing_balance * 100
        leverage = f"{ratio:.2f}%"

    print(
        f"[margin] exchange={result.exchange} source={source} "
        f"sh_date={sh_date} sz_date={sz_date}"
    )
    print(
        f"  financing_balance={fin_bal} financing_buy={fin_buy} "
        f"short_balance={short_bal} total_balance={total_bal}"
    )
    print(f"  buy/balance_ratio={leverage}")

    if result.days:
        print()
        for day in result.days:
            fb = "n/a" if day.financing_balance is None else f"{day.financing_balance / 1e8:.0f}亿"
            buy = "n/a" if day.financing_buy is None else f"{day.financing_buy / 1e8:.0f}亿"
            sb = "n/a" if day.short_balance is None else f"{day.short_balance / 1e8:.0f}亿"
            print(f"  {day.date} 融资余额={fb} 买入={buy} 融券={sb}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch A-share margin trading data.")
    parser.add_argument(
        "--exchange",
        choices=("sh", "sz", "both"),
        default="both",
        help="Which exchange to query.",
    )
    parser.add_argument("--lookback", type=int, default=10, help="Number of trading days.")
    parser.add_argument(
        "--proxy",
        help="HTTP/S proxy for A-share APIs, e.g. http://127.0.0.1:7890.",
    )
    parser.add_argument(
        "--network-profile",
        choices=("auto", "china", "global"),
        default="auto",
        help="Network route for akshare.",
    )
    args = parser.parse_args()

    _apply_network_profile(args)

    provider = AStockMarginProvider()
    result = provider.get_market_margin(
        MarginQuery(exchange=args.exchange, lookback_days=args.lookback)
    )
    _print_margin(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
