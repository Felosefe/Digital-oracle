from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from digital_oracle import AStockDisclosureProvider, DisclosureQuery  # noqa: E402

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


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch A-share notices and disclosures.")
    parser.add_argument("--symbol", default="全部", help="Stock code or 全部 for all.")
    parser.add_argument("--date", default="", help="Date in YYYYMMDD format, empty=today.")
    parser.add_argument("--keyword", default="", help="Keyword in title (e.g. 减持, 回购, 业绩).")
    parser.add_argument("--category", default="", help="Notice category (定期报告, 减持, 回购...).")
    parser.add_argument("--top-n", type=int, default=50, help="Limit results.")
    parser.add_argument("--proxy", help="HTTP/S proxy.")
    parser.add_argument("--network-profile", choices=("auto", "china"), default="auto")
    args = parser.parse_args()
    _apply_network_profile(args)

    provider = AStockDisclosureProvider()

    result = provider.list_notices(
        DisclosureQuery(
            symbol=args.symbol,
            date=args.date,
            keyword=args.keyword,
            category=args.category,
            top_n=args.top_n,
        )
    )

    raw = result.metadata.get("raw_total", "?")
    print(
        f"[notices] symbol={args.symbol} date={args.date or 'today'} "
        f"keyword={args.keyword!r} category={args.category!r} "
        f"filtered={result.total_count} raw_total={raw}"
    )
    for n in result.notices:
        print(f"  {n.code} {n.name} [{n.category}] {n.date}")
        print(f"    {n.title}")
        if n.url:
            print(f"    {n.url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
