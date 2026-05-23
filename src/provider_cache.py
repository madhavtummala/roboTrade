from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd

from .state_store import STATE_DB_PATH
from .universe import resolve_project_path


def _connect(db_path: str = STATE_DB_PATH) -> sqlite3.Connection:
    resolved = resolve_project_path(db_path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(resolved)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA busy_timeout=5000")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS api_cache (
            category TEXT NOT NULL,
            provider TEXT NOT NULL,
            cache_key TEXT NOT NULL,
            payload TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            PRIMARY KEY (category, provider, cache_key)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS api_provider_state (
            provider TEXT PRIMARY KEY,
            category TEXT NOT NULL,
            request_count INTEGER NOT NULL DEFAULT 0,
            window_started_at TEXT NOT NULL,
            limited_until TEXT,
            last_error TEXT,
            updated_at TEXT NOT NULL
        )
        """
    )
    return connection


def _now() -> pd.Timestamp:
    return pd.Timestamp.now(tz="UTC")


def _timestamp(value: str | None) -> pd.Timestamp | None:
    if not value:
        return None
    parsed = pd.to_datetime(value, utc=True, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed


def load_cached_payload(
    category: str,
    provider: str,
    cache_key: str,
    *,
    db_path: str = STATE_DB_PATH,
) -> Any | None:
    now = _now()
    with _connect(db_path) as connection:
        row = connection.execute(
            """
            SELECT payload, expires_at
            FROM api_cache
            WHERE category = ? AND provider = ? AND cache_key = ?
            """,
            (category, provider, cache_key),
        ).fetchone()
    if not row:
        return None
    expires_at = _timestamp(row[1])
    if expires_at is None or expires_at <= now:
        return None
    try:
        return json.loads(row[0])
    except json.JSONDecodeError:
        return None


def save_cached_payload(
    category: str,
    provider: str,
    cache_key: str,
    payload: Any,
    ttl_seconds: int,
    *,
    db_path: str = STATE_DB_PATH,
) -> None:
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=max(int(ttl_seconds), 0))
    with _connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO api_cache (category, provider, cache_key, payload, fetched_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(category, provider, cache_key) DO UPDATE SET
                payload = excluded.payload,
                fetched_at = excluded.fetched_at,
                expires_at = excluded.expires_at
            """,
            (
                category,
                provider,
                cache_key,
                json.dumps(payload, sort_keys=True, default=str),
                now.isoformat(),
                expires_at.isoformat(),
            ),
        )


def provider_is_limited(provider: str, *, db_path: str = STATE_DB_PATH) -> bool:
    with _connect(db_path) as connection:
        row = connection.execute(
            "SELECT limited_until FROM api_provider_state WHERE provider = ?",
            (provider,),
        ).fetchone()
    if not row:
        return False
    limited_until = _timestamp(row[0])
    return bool(limited_until is not None and limited_until > _now())


def record_provider_success(category: str, provider: str, *, db_path: str = STATE_DB_PATH) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO api_provider_state
                (provider, category, request_count, window_started_at, limited_until, last_error, updated_at)
            VALUES (?, ?, 1, ?, NULL, NULL, ?)
            ON CONFLICT(provider) DO UPDATE SET
                category = excluded.category,
                request_count = api_provider_state.request_count + 1,
                limited_until = NULL,
                last_error = NULL,
                updated_at = excluded.updated_at
            """,
            (provider, category, now, now),
        )


def record_provider_limited(
    category: str,
    provider: str,
    error: str,
    *,
    retry_after_seconds: int = 3600,
    db_path: str = STATE_DB_PATH,
) -> None:
    now_dt = datetime.now(timezone.utc)
    limited_until = now_dt + timedelta(seconds=max(int(retry_after_seconds), 60))
    now = now_dt.isoformat()
    with _connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO api_provider_state
                (provider, category, request_count, window_started_at, limited_until, last_error, updated_at)
            VALUES (?, ?, 1, ?, ?, ?, ?)
            ON CONFLICT(provider) DO UPDATE SET
                category = excluded.category,
                request_count = api_provider_state.request_count + 1,
                limited_until = excluded.limited_until,
                last_error = excluded.last_error,
                updated_at = excluded.updated_at
            """,
            (provider, category, now, limited_until.isoformat(), error[:500], now),
        )
