from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

from .config import LONG_MA_DAYS


def fetch_daily_bars(
    symbols: list[str],
    lookback_days: int,
    ma_days: int = LONG_MA_DAYS,
    extra_buffer_days: int = 250,
    alpaca_data_client=None,
    end_date: datetime | None = None,
    data_feed: str | None = "iex",
) -> dict[str, pd.DataFrame]:
    """Fetch enough daily bars for a momentum signal and moving average calculation."""
    from .alpaca_client import get_historical_daily_bars

    total_lookback = lookback_days + ma_days + extra_buffer_days
    bars_by_symbol = get_historical_daily_bars(
        symbols=symbols,
        lookback_days=total_lookback,
        extra_buffer_days=extra_buffer_days,
        data_client=alpaca_data_client,
        end_date=end_date,
        data_feed=data_feed,
    )

    normalized: dict[str, pd.DataFrame] = {}
    for symbol, df in bars_by_symbol.items():
        if not df.empty:
            df = df.copy()
            df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.tz_convert("UTC")
            df = df.sort_values("timestamp").reset_index(drop=True)
        normalized[symbol] = df
    return normalized
