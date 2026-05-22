from __future__ import annotations
import logging
from datetime import datetime, timedelta, timezone

try:
    import pandas as pd
except ImportError:  # type: ignore
    pd = None

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest
from alpaca.data.enums import DataFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

from .config import Config


logger = logging.getLogger(__name__)


def create_trading_client(config: Config) -> TradingClient:
    return TradingClient(
        api_key=config.alpaca_api_key,
        secret_key=config.alpaca_api_secret,
        paper=False,
        url_override=config.alpaca_base_url or None,
    )


def create_data_client(config: Config) -> StockHistoricalDataClient:
    return StockHistoricalDataClient(
        api_key=config.alpaca_api_key,
        secret_key=config.alpaca_api_secret,
    )


def get_account_equity(trading_client: TradingClient) -> float:
    account = trading_client.get_account()
    return float(account.equity)


def get_positions(trading_client: TradingClient) -> dict[str, int]:
    positions = trading_client.get_all_positions()
    parsed: dict[str, int] = {}
    for position in positions:
        try:
            parsed[position.symbol] = int(float(position.qty))
        except (TypeError, ValueError):
            parsed[position.symbol] = 0
    return parsed


def _iter_bars(bars, symbol: str | None = None):
    if hasattr(bars, "data"):
        if symbol is not None:
            return bars.data.get(symbol, [])
        records = []
        for symbol_bars in bars.data.values():
            records.extend(symbol_bars)
        return records
    if isinstance(bars, dict):
        if symbol is not None:
            return bars.get(symbol, [])
        records = []
        for symbol_bars in bars.values():
            records.extend(symbol_bars)
        return records
    return bars


def _resolve_data_feed(data_feed: str | DataFeed | None) -> DataFeed | None:
    if data_feed is None:
        return None
    if isinstance(data_feed, DataFeed):
        return data_feed
    return DataFeed(data_feed.lower())


def _timestamp_to_utc(timestamp) -> "pd.Timestamp":
    parsed = pd.to_datetime(timestamp)
    if parsed.tzinfo is None:
        return parsed.tz_localize("UTC")
    return parsed.tz_convert("UTC")


def _parse_bars_to_df(bars, symbol: str | None = None) -> "pd.DataFrame":
    if pd is None:
        raise ImportError("pandas is required to parse Alpaca bar data")

    records = []
    for bar in _iter_bars(bars, symbol):
        records.append(
            {
                "timestamp": _timestamp_to_utc(bar.timestamp),
                "open": float(bar.open),
                "high": float(bar.high),
                "low": float(bar.low),
                "close": float(bar.close),
                "volume": int(bar.volume),
            }
        )
    df = pd.DataFrame.from_records(records)
    if df.empty:
        return df
    return df.sort_values("timestamp").reset_index(drop=True)


def get_latest_price(
    symbol: str,
    data_client: StockHistoricalDataClient,
    end_date: datetime | None = None,
    data_feed: str | DataFeed | None = "iex",
) -> float:
    end = end_date or datetime.now(timezone.utc)
    request = StockBarsRequest(
        symbol_or_symbols=[symbol],
        timeframe=TimeFrame.Day,
        end=end,
        limit=1,
        feed=_resolve_data_feed(data_feed),
    )
    bars = data_client.get_stock_bars(request)
    df = _parse_bars_to_df(bars, symbol)
    if df.empty:
        raise RuntimeError(f"No latest bar found for {symbol}")
    return float(df["close"].iloc[-1])


def get_historical_daily_bars(
    symbols: list[str],
    lookback_days: int,
    extra_buffer_days: int = 250,
    data_client: StockHistoricalDataClient | None = None,
    end_date: datetime | None = None,
    start_date: datetime | None = None,
    data_feed: str | DataFeed | None = "iex",
) -> dict[str, "pd.DataFrame"]:
    if data_client is None:
        raise ValueError("data_client is required")

    end = end_date or datetime.now(timezone.utc)
    if start_date is None:
        total_days = lookback_days + extra_buffer_days
        start = end - timedelta(days=total_days * 2)
    else:
        start = start_date

    bars_by_symbol: dict[str, pd.DataFrame] = {}
    for symbol in symbols:
        request = StockBarsRequest(
            symbol_or_symbols=[symbol],
            timeframe=TimeFrame.Day,
            start=start,
            end=end,
            limit=1000,
            feed=_resolve_data_feed(data_feed),
        )
        bars = data_client.get_stock_bars(request)
        df = _parse_bars_to_df(bars, symbol)
        bars_by_symbol[symbol] = df
        logger.debug("Fetched %s bars for %s", len(df), symbol)

    return bars_by_symbol


def submit_market_order(trading_client: TradingClient, symbol: str, side: str, qty: int):
    side = side.lower()
    if side not in {"buy", "sell"}:
        raise ValueError("side must be 'buy' or 'sell'")
    if qty <= 0:
        raise ValueError("qty must be a positive integer")
    order = MarketOrderRequest(
        symbol=symbol,
        qty=qty,
        side=OrderSide.BUY if side == "buy" else OrderSide.SELL,
        time_in_force=TimeInForce.DAY,
    )
    return trading_client.submit_order(order_data=order)
