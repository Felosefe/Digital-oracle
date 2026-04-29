from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from digital_oracle import (  # noqa: E402
    AStockBreadthQuery,
    AStockHistoryQuery,
    AStockIndexQuery,
    AStockProvider,
    AStockSectorBreadthQuery,
    AStockSectorHistoryQuery,
    PriceHistoryQuery,
    StooqProvider,
)


EXPECTED_VENV = PACKAGE_ROOT / ".venv-eastmoney" / "Scripts" / "python.exe"
PROXY_ENV_NAMES = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
)


def _apply_network_profile(profile: str) -> None:
    os.environ.pop("DIGITAL_ORACLE_ASTOCK_PROXY", None)
    if profile == "china":
        os.environ["DIGITAL_ORACLE_ASTOCK_PROXY_MODE"] = "direct"
        for name in PROXY_ENV_NAMES:
            os.environ.pop(name, None)
    elif profile == "global":
        os.environ["DIGITAL_ORACLE_ASTOCK_PROXY_MODE"] = "env"
    else:
        os.environ.pop("DIGITAL_ORACLE_ASTOCK_PROXY_MODE", None)


def _check_history(label: str, func) -> dict[str, Any]:
    try:
        history = func()
        latest = history.latest
        return {
            "label": label,
            "ok": True,
            "source": history.metadata.get("source", "unknown"),
            "bars": len(history.bars),
            "latest_date": latest.date if latest else None,
            "latest_close": latest.close if latest else None,
        }
    except Exception as exc:
        return {
            "label": label,
            "ok": False,
            "source": None,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }


def _check_sector_snapshots(provider: AStockProvider, *, limit: int) -> dict[str, Any]:
    try:
        sectors = provider.list_sector_snapshots()
        source = sectors[0].metadata.get("source", "unknown") if sectors else "unknown"
        return {
            "label": "astock.sectors",
            "ok": True,
            "source": source,
            "rows": len(sectors),
            "sample": [
                {
                    "code": sector.code,
                    "name": sector.name,
                    "change_pct": sector.change_pct,
                }
                for sector in sectors[:limit]
            ],
        }
    except Exception as exc:
        return {
            "label": "astock.sectors",
            "ok": False,
            "source": None,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }


def _check_breadth(label: str, func) -> dict[str, Any]:
    try:
        breadth = func()
        return {
            "label": label,
            "ok": True,
            "source": breadth.metadata.get("source", "unknown"),
            "breadth": True,
            "total": breadth.total_count,
            "up": breadth.up_count,
            "down": breadth.down_count,
            "flat": breadth.flat_count,
            "limit_up": breadth.limit_up_count,
            "limit_down": breadth.limit_down_count,
            "amount": breadth.total_amount,
            "median_change_pct": breadth.median_change_pct,
            "breadth_level": breadth.metadata.get("breadth_level"),
        }
    except Exception as exc:
        return {
            "label": label,
            "ok": False,
            "source": None,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }


def _render_text(report: dict[str, Any]) -> str:
    lines = [
        "[agent source audit]",
        f"cwd={report['environment']['cwd']}",
        f"python={report['environment']['python']}",
        f"expected_python={report['environment']['expected_python']}",
        f"venv_ok={str(report['environment']['venv_ok']).lower()}",
        f"network_profile={report['environment']['network_profile']}",
    ]
    proxy_env = report["environment"]["proxy_env"]
    if proxy_env:
        lines.append(f"proxy_env={proxy_env}")
    else:
        lines.append("proxy_env={}")

    lines.append("")
    for item in report["checks"]:
        if item["ok"]:
            if "bars" in item:
                lines.append(
                    f"[ok] {item['label']} source={item['source']} "
                    f"bars={item['bars']} latest={item['latest_date']} close={item['latest_close']}"
                )
            elif item.get("breadth"):
                lines.append(
                    f"[ok] {item['label']} source={item['source']} "
                    f"total={item['total']} up={item['up']} down={item['down']} "
                    f"flat={item['flat']} amount={item['amount']} "
                    f"level={item.get('breadth_level') or 'unknown'}"
                )
            else:
                lines.append(
                    f"[ok] {item['label']} source={item['source']} rows={item['rows']}"
                )
        else:
            lines.append(
                f"[fail] {item['label']} {item['error_type']}: {item['error']}"
            )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit which data sources an agent actually uses before analysis."
    )
    parser.add_argument(
        "--network-profile",
        choices=("auto", "china", "global"),
        default="china",
        help="AStock network profile to apply before provider construction.",
    )
    parser.add_argument("--limit", type=int, default=5, help="Trailing bars/rows to fetch.")
    parser.add_argument(
        "--astock-symbols",
        nargs="*",
        default=("159813", "600519", "300750", "688981"),
        help="A-share stock symbols to audit.",
    )
    parser.add_argument(
        "--index-symbols",
        nargs="*",
        default=("sh000001", "sh000300", "sh000905"),
        help="A-share index symbols to audit.",
    )
    parser.add_argument(
        "--sector",
        default="半导体",
        help="A-share sector name/code to audit.",
    )
    parser.add_argument(
        "--stooq-symbols",
        nargs="*",
        default=("spy.us", "xauusd", "hg.c"),
        help="Stooq symbols to audit.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format.",
    )
    parser.add_argument(
        "--require-venv",
        action="store_true",
        help="Exit non-zero if the current Python is not .venv-eastmoney.",
    )
    args = parser.parse_args()

    _apply_network_profile(args.network_profile)

    python_path = Path(sys.executable).resolve()
    expected_python = EXPECTED_VENV.resolve()
    venv_ok = python_path == expected_python
    proxy_env = {
        name: value
        for name in PROXY_ENV_NAMES
        if (value := os.environ.get(name))
    }

    checks: list[dict[str, Any]] = []
    astock = AStockProvider()
    for symbol in args.astock_symbols:
        checks.append(
            _check_history(
                f"astock.stock.{symbol}",
                lambda symbol=symbol: astock.get_history(
                    AStockHistoryQuery(symbol=symbol, limit=args.limit)
                ),
            )
        )

    for symbol in args.index_symbols:
        checks.append(
            _check_history(
                f"astock.index.{symbol}",
                lambda symbol=symbol: astock.get_index_history(
                    AStockIndexQuery(symbol=symbol, limit=args.limit)
                ),
            )
        )

    checks.append(
        _check_history(
            f"astock.sector.{args.sector}",
            lambda: astock.get_sector_history(
                AStockSectorHistoryQuery(symbol=args.sector, limit=args.limit)
            ),
        )
    )
    checks.append(_check_sector_snapshots(astock, limit=args.limit))
    checks.append(
        _check_breadth(
            "astock.breadth.market",
            lambda: astock.get_market_breadth(AStockBreadthQuery()),
        )
    )
    checks.append(
        _check_breadth(
            f"astock.breadth.sector.{args.sector}",
            lambda: astock.get_sector_breadth(AStockSectorBreadthQuery(symbol=args.sector)),
        )
    )

    stooq = StooqProvider()
    for symbol in args.stooq_symbols:
        checks.append(
            _check_history(
                f"stooq.{symbol}",
                lambda symbol=symbol: stooq.get_history(
                    PriceHistoryQuery(symbol=symbol, limit=args.limit)
                ),
            )
        )

    report = {
        "environment": {
            "cwd": str(Path.cwd()),
            "python": str(python_path),
            "expected_python": str(expected_python),
            "venv_ok": venv_ok,
            "network_profile": args.network_profile,
            "proxy_env": proxy_env,
        },
        "checks": checks,
    }

    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(_render_text(report))

    if args.require_venv and not venv_ok:
        return 2
    if any(not check["ok"] for check in checks):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
