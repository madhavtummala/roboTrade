from __future__ import annotations

import argparse
import json
import re
from typing import Any

from src.connectors.service import EOD_MARKET_CATEGORY, INTRADAY_MARKET_CATEGORY
from src.core.config import get_config, load_algorithms_config
from src.data.duckdb_store import clear_market_bars, market_bars_summary
from src.data.provider_cache import clear_cached_payloads


DEFAULT_BACKTEST_BUFFER_BARS = 10
DEFAULT_INTRADAY_LOOKBACK_BARS = 78
DEFAULT_INTRADAY_BAR_MINUTES = 15


def _algorithm_symbols() -> list[str]:
    raw = load_algorithms_config()
    algorithms = raw.get("algorithms", raw) if isinstance(raw, dict) else {}
    symbols: set[str] = set()
    for config in algorithms.values() if isinstance(algorithms, dict) else []:
        if not isinstance(config, dict):
            continue
        for key in (
            "risk_on_universe",
            "defensive_universe",
            "equity_income_universe",
            "crisis_hedge_universe",
            "symbols",
        ):
            values = config.get(key)
            if isinstance(values, list):
                symbols.update(str(value).strip().upper() for value in values if str(value).strip())
        for key in ("spy_symbol", "benchmark_symbol"):
            value = str(config.get(key) or "").strip().upper()
            if value:
                symbols.add(value)
    return sorted(symbols)


def _wanted_symbols(symbols: list[str] | None) -> list[str]:
    explicit = [symbol.strip().upper() for symbol in (symbols or []) if symbol.strip()]
    if explicit:
        return sorted(set(explicit))
    configured = _algorithm_symbols()
    if configured:
        return configured
    return sorted(set(get_config().symbols))


def _count_rows(bars_by_symbol: dict[str, Any]) -> dict[str, int]:
    return {symbol: int(0 if bars.empty else len(bars)) for symbol, bars in bars_by_symbol.items()}


def _default_eod_lookback_bars() -> int:
    period = str(getattr(get_config(), "backtest_period", "4m") or "4m").strip().lower()
    match = re.fullmatch(r"([1-9][0-9]*)m", period)
    months = int(match.group(1)) if match else 4
    return max(int(round(months * 22)) + DEFAULT_BACKTEST_BUFFER_BARS, 2)


def _clear_market_cache(symbols: list[str], *, provider: str, intraday_bar_minutes: int) -> dict[str, int]:
    deleted = {
        "eod_duckdb_rows": clear_market_bars(
            category=EOD_MARKET_CATEGORY,
            provider=provider,
            symbols=symbols,
            timeframe="1d",
        ),
        "intraday_duckdb_rows": clear_market_bars(
            category=INTRADAY_MARKET_CATEGORY,
            provider=provider,
            symbols=symbols,
            timeframe=f"{int(intraday_bar_minutes)}m",
        ),
    }
    prefixes = [f"{symbol.upper()}:{int(intraday_bar_minutes)}:" for symbol in symbols]
    deleted["intraday_payload_rows"] = clear_cached_payloads(
        category=INTRADAY_MARKET_CATEGORY,
        provider=provider,
        cache_key_prefixes=prefixes,
    )
    return deleted


def warm_market_data_cache(
    symbols: list[str] | None = None,
    *,
    provider: str = "yfinance",
    eod_lookback_bars: int | None = None,
    intraday_lookback_bars: int | None = None,
    intraday_bar_minutes: int = DEFAULT_INTRADAY_BAR_MINUTES,
    clear: bool = False,
) -> dict[str, Any]:
    from src.connectors import fetch_eod_market_bars, fetch_intraday_market_bars

    wanted = _wanted_symbols(symbols)
    config = get_config()
    eod_lookback_bars = int(eod_lookback_bars or _default_eod_lookback_bars())
    intraday_lookback_bars = int(intraday_lookback_bars or DEFAULT_INTRADAY_LOOKBACK_BARS)
    deleted = _clear_market_cache(wanted, provider=provider, intraday_bar_minutes=intraday_bar_minutes) if clear else {}
    eod = fetch_eod_market_bars(
        wanted,
        config,
        lookback_bars=eod_lookback_bars,
        force_refresh=True,
        provider=provider,
    )
    intraday = fetch_intraday_market_bars(
        wanted,
        config,
        lookback_bars=intraday_lookback_bars,
        bar_minutes=intraday_bar_minutes,
        force_refresh=True,
        provider=provider,
    )
    return {
        "provider": provider,
        "symbols": wanted,
        "cleared": deleted,
        "fetched": {
            "eod_rows": _count_rows(eod),
            "intraday_rows": _count_rows(intraday),
        },
        "cache": market_bars_summary(
            provider=provider,
            symbols=wanted,
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Clear, warm, and verify local market-data cache.")
    parser.add_argument("--symbols", nargs="*", help="Symbols to warm. Defaults to configured algorithm universes.")
    parser.add_argument("--provider", default="yfinance")
    parser.add_argument("--eod-lookback-bars", default=None, type=int)
    parser.add_argument("--intraday-lookback-bars", default=DEFAULT_INTRADAY_LOOKBACK_BARS, type=int)
    parser.add_argument("--intraday-bar-minutes", default=DEFAULT_INTRADAY_BAR_MINUTES, type=int)
    parser.add_argument("--clear", action="store_true", help="Clear matching local cache rows before fetching.")
    args = parser.parse_args()
    print(
        json.dumps(
            warm_market_data_cache(
                args.symbols,
                provider=args.provider,
                eod_lookback_bars=args.eod_lookback_bars,
                intraday_lookback_bars=args.intraday_lookback_bars,
                intraday_bar_minutes=args.intraday_bar_minutes,
                clear=args.clear,
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
