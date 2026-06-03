from __future__ import annotations

import pandas as pd
import yfinance as yf
from typing import Dict
from ..base import BaseMarketConnector
from ...core.interfaces import MarketDataRequest

class YFinanceConnector(BaseMarketConnector):
    """Yahoo Finance connector implementing standardized fetch logic."""

    def _execute_fetch(self, request: MarketDataRequest) -> Dict[str, pd.DataFrame]:
        results = {}
        # Map timeframe to yfinance intervals
        # e.g., '1m', '5m', '15m', '1h', '1d'
        interval = request.timeframe
        
        for symbol in request.symbols:
            ticker = yf.Ticker(symbol)
            # Simplified fetching logic
            df = ticker.history(period="1mo", interval=interval)
            
            if not df.empty:
                df = df.reset_index()
                # Normalize columns to standard OHLCV
                df = df.rename(columns={
                    "Date": "timestamp",
                    "Datetime": "timestamp",
                    "Open": "open",
                    "High": "high",
                    "Low": "low",
                    "Close": "close",
                    "Volume": "volume"
                })
                df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
                results[symbol.upper()] = df[["timestamp", "open", "high", "low", "close", "volume"]]
        
        return results
