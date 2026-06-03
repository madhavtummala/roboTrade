from __future__ import annotations

import json
import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
import pandas as pd

logger = logging.getLogger(__name__)

DUCKDB_PATH = os.getenv("STATE_DUCKDB_PATH", "data/trading_bot.duckdb")

def _duckdb():
    import duckdb
    return duckdb

class DataStore:
    def __init__(self, db_path: str = DUCKDB_PATH):
        self.db_path = db_path
        self._initialize_schema()

    def _connect(self):
        # Ensure directory exists
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        return _duckdb().connect(self.db_path)

    def _initialize_schema(self):
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS market_bars (
                    symbol VARCHAR,
                    timeframe VARCHAR,
                    category VARCHAR,
                    provider VARCHAR,
                    timestamp TIMESTAMPTZ,
                    open DOUBLE,
                    high DOUBLE,
                    low DOUBLE,
                    close DOUBLE,
                    volume DOUBLE,
                    fetched_at TIMESTAMPTZ,
                    expires_at TIMESTAMPTZ,
                    PRIMARY KEY (symbol, timeframe, category, provider, timestamp)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sentiment_records (
                    symbol VARCHAR,
                    provider VARCHAR,
                    timestamp TIMESTAMPTZ,
                    sentiment DOUBLE,
                    mentions DOUBLE,
                    social_score DOUBLE,
                    title VARCHAR,
                    url VARCHAR,
                    raw_json VARCHAR,
                    fetched_at TIMESTAMPTZ,
                    expires_at TIMESTAMPTZ,
                    PRIMARY KEY (symbol, provider, timestamp, title)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS provider_status (
                    provider VARCHAR PRIMARY KEY,
                    category VARCHAR,
                    last_success TIMESTAMPTZ,
                    last_failure TIMESTAMPTZ,
                    error_message VARCHAR,
                    is_limited BOOLEAN DEFAULT FALSE,
                    limited_until TIMESTAMPTZ
                )
            """)

    def get_market_bars(self, symbol: str, timeframe: str, provider: str, start: datetime, end: datetime) -> pd.DataFrame:
        query = """
            SELECT timestamp, open, high, low, close, volume
            FROM market_bars
            WHERE symbol = ? AND timeframe = ? AND provider = ?
            AND timestamp >= ? AND timestamp <= ?
            AND (expires_at IS NULL OR expires_at > ?)
            ORDER BY timestamp ASC
        """
        now = datetime.now(timezone.utc)
        with self._connect() as conn:
            return conn.execute(query, [symbol.upper(), timeframe, provider, start, end, now]).fetchdf()

    def write_market_bars(self, symbol: str, timeframe: str, category: str, provider: str, df: pd.DataFrame, ttl_seconds: int = 3600):
        if df.empty:
            return
        
        fetched_at = datetime.now(timezone.utc)
        expires_at = fetched_at + timedelta(seconds=ttl_seconds)
        
        # Prepare rows for insertion
        rows = []
        for _, row in df.iterrows():
            rows.append((
                symbol.upper(), timeframe, category, provider,
                row['timestamp'], row['open'], row['high'], row['low'], row['close'], row['volume'],
                fetched_at, expires_at
            ))
            
        with self._connect() as conn:
            conn.executemany("""
                INSERT OR REPLACE INTO market_bars 
                (symbol, timeframe, category, provider, timestamp, open, high, low, close, volume, fetched_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, rows)

    def cleanup_expired(self):
        now = datetime.now(timezone.utc)
        with self._connect() as conn:
            conn.execute("DELETE FROM market_bars WHERE expires_at <= ?", [now])
            conn.execute("DELETE FROM sentiment_records WHERE expires_at <= ?", [now])
