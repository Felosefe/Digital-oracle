from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from digital_oracle import AStockValuationProvider, ValuationQuery, FinancialQuery  # noqa: E402

_PROXY_ENV_NAMES = (
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
    "http_proxy", "https_proxy", "all_proxy",
)


def _apply_network_profile(args: argparse.Namespace) -> None:
    if args.proxy:
        os.environ["DIGITAL_ORACLE_ASTOCK_PROXY"] = args.proxy
    if args.network_profile == "china":
        os.environ["DIGITAL_ORACLE_ASTOCK_PROXY_MODE"] = "direct"
        for name in _PROXY_ENV_NAMES:
            os.environ.pop(name, None)


def _print_valuation(result) -> None:
    print(f"[{result.symbol}] date={result.latest_date} level={result.latest_index_level}")
    pe = "n/a" if result.latest_pe is None else f"{result.latest_pe:.2f}"
    pe_pct = "n/a" if result.latest_pe_percentile is None else f"{result.latest_pe_percentile:.1f}%"
    pb = "n/a" if result.latest_pb is None else f"{result.latest_pb:.2f}"
    pb_pct = "n/a" if result.latest_pb_percentile is None else f"{result.latest_pb_percentile:.1f}%"
    print(f"  PE={pe}  PE分位={pe_pct}  PB={pb}  PB分位={pb_pct}")

    if result.days:
        print(f"  history ({len(result.days)} days):")
        for d in result.days[-5:]:
            pe_s = "n/a" if d.pe_dynamic is None else f"{d.pe_dynamic:.1f}"
            pe_p = "n/a" if d.pe_dynamic_percentile is None else f"{d.pe_dynamic_percentile:.1f}%"
            pb_s = "n/a" if d.pb is None else f"{d.pb:.2f}"
            pb_p = "n/a" if d.pb_percentile is None else f"{d.pb_percentile:.1f}%"
            print(f"    {d.date}  PE={pe_s}({pe_p})  PB={pb_s}({pb_p})  idx={d.index_level}")


def _print_financials(fin) -> None:
    print(f"[{fin.symbol}] report={fin.report_date}")
    eps = "n/a" if fin.eps is None else f"{fin.eps:.2f}"
    roe = "n/a" if fin.roe is None else f"{fin.roe:.2f}%"
    rev = "n/a" if fin.revenue_growth is None else f"{fin.revenue_growth:+.2f}%"
    profit = "n/a" if fin.profit_growth is None else f"{fin.profit_growth:+.2f}%"
    gross = "n/a" if fin.gross_margin is None else f"{fin.gross_margin:.2f}%"
    net = "n/a" if fin.net_margin is None else f"{fin.net_margin:.2f}%"
    debt = "n/a" if fin.debt_ratio is None else f"{fin.debt_ratio:.2f}%"
    book = "n/a" if fin.book_value_per_share is None else f"{fin.book_value_per_share:.2f}"
    cash = "n/a" if fin.cash_flow_per_share is None else f"{fin.cash_flow_per_share:.2f}"
    print(f"  EPS={eps}  ROE={roe}  book={book}")
    print(f"  revenue_growth={rev}  profit_growth={profit}")
    print(f"  gross_margin={gross}  net_margin={net}")
    print(f"  debt_ratio={debt}  current_ratio={fin.current_ratio}  quick_ratio={fin.quick_ratio}")
    print(f"  cash_flow/share={cash}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch A-share valuation & fundamentals.")
    parser.add_argument(
        "--view",
        choices=("index", "financials"),
        default="index",
        help="What to fetch.",
    )
    parser.add_argument("--symbol", default="沪深300", help="Index name or stock code.")
    parser.add_argument("--lookback", type=int, default=252, help="Trading days.")
    parser.add_argument("--start-year", default="2024", help="Start year for financials.")
    parser.add_argument("--proxy", help="HTTP/S proxy.")
    parser.add_argument("--network-profile", choices=("auto", "china"), default="auto")
    args = parser.parse_args()
    _apply_network_profile(args)

    provider = AStockValuationProvider()

    if args.view == "financials":
        fin = provider.get_financials(FinancialQuery(symbol=args.symbol, start_year=args.start_year))
        _print_financials(fin)
        return 0

    result = provider.get_index_valuation(ValuationQuery(symbol=args.symbol, lookback_days=args.lookback))
    _print_valuation(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
