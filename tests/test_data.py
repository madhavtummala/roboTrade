from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from src import data
from src.data import cache_warmup, duckdb_store, provider_cache


def _bars(dates: list[str], start_price: float = 100.0) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.to_datetime(dates, utc=True),
            "open": [start_price + index for index in range(len(dates))],
            "high": [start_price + index + 1 for index in range(len(dates))],
            "low": [start_price + index - 1 for index in range(len(dates))],
            "close": [start_price + index + 0.5 for index in range(len(dates))],
            "volume": [1_000_000 + index for index in range(len(dates))],
        }
    )


def test_market_data_cache_requests_only_missing_range(monkeypatch) -> None:
    saved = {}
    requests = []
    cache = {
        "version": data.MARKET_DATA_CACHE_VERSION,
        "items": {
            "iex:SPY": {
                "symbol": "SPY",
                "data_feed": "iex",
                "updated_at": "2024-01-01T00:00:00+00:00",
                "bars": data._bars_to_records(_bars(["2024-01-01", "2024-01-02"])),
            }
        },
    }

    def fake_historical_bars(symbols, lookback_days, extra_buffer_days, data_client, end_date, start_date, data_feed):
        requests.append(start_date)
        return {"SPY": _bars(["2024-01-03"], start_price=102.0)}

    monkeypatch.setattr(data, "_load_market_data_cache", lambda: cache)
    monkeypatch.setattr(data, "_save_market_data_cache", lambda payload: saved.update(payload))
    monkeypatch.setattr("src.brokerages.alpaca_client.get_historical_daily_bars", fake_historical_bars)

    result = data.refresh_market_data_cache(
        ["SPY"],
        lookback_days=1,
        ma_days=0,
        extra_buffer_days=0,
        end_date=datetime(2024, 1, 4, tzinfo=timezone.utc),
        data_feed="iex",
    )

    assert requests[0].date().isoformat() == "2024-01-03"
    assert result["SPY"]["timestamp"].dt.strftime("%Y-%m-%d").tolist() == ["2024-01-02", "2024-01-03"]
    assert saved["items"]["iex:SPY"]["bars"][-1]["timestamp"].startswith("2024-01-03")


def test_fresh_market_data_cache_does_not_call_api(monkeypatch) -> None:
    cache = {
        "version": data.MARKET_DATA_CACHE_VERSION,
        "items": {
            "iex:SPY": {
                "symbol": "SPY",
                "data_feed": "iex",
                "updated_at": pd.Timestamp.now(tz="UTC").isoformat(),
                "bars": data._bars_to_records(_bars(["2024-01-02"])),
            }
        },
    }

    def fail_historical_bars(*_args, **_kwargs):
        raise AssertionError("fresh cache should not hit the API")

    monkeypatch.setattr(data, "_load_market_data_cache", lambda: cache)
    monkeypatch.setattr(data, "_save_market_data_cache", lambda payload: None)
    monkeypatch.setattr("src.brokerages.alpaca_client.get_historical_daily_bars", fail_historical_bars)

    result = data.refresh_market_data_cache(
        ["SPY"],
        lookback_days=1,
        ma_days=0,
        extra_buffer_days=0,
        end_date=datetime(2024, 1, 4, tzinfo=timezone.utc),
        data_feed="iex",
    )

    assert result["SPY"]["timestamp"].dt.strftime("%Y-%m-%d").tolist() == ["2024-01-02"]


def test_clear_market_bars_is_targeted(tmp_path) -> None:
    db_path = str(tmp_path / "market.duckdb")
    bars = _bars(["2026-01-02"])
    duckdb_store.write_market_bars("eod_market_data", "yfinance", "SPY", "1d", bars, db_path=db_path)
    duckdb_store.write_market_bars("intraday_market_data", "yfinance", "SPY", "15m", bars, db_path=db_path)

    deleted = duckdb_store.clear_market_bars(
        category="eod_market_data",
        provider="yfinance",
        symbols=["SPY"],
        timeframe="1d",
        db_path=db_path,
    )

    assert deleted == 1
    summary = duckdb_store.market_bars_summary(provider="yfinance", symbols=["SPY"], db_path=db_path)
    assert [(row["category"], row["timeframe"], row["rows"]) for row in summary] == [
        ("intraday_market_data", "15m", 1)
    ]


def test_clear_cached_payloads_can_match_key_prefix(tmp_path) -> None:
    db_path = str(tmp_path / "state.duckdb")
    provider_cache.save_cached_payload("intraday_market_data", "yfinance", "SPY:15:78", [{"close": 1}], 60, db_path=db_path)
    provider_cache.save_cached_payload("intraday_market_data", "yfinance", "QQQ:15:78", [{"close": 2}], 60, db_path=db_path)

    deleted = provider_cache.clear_cached_payloads(
        category="intraday_market_data",
        provider="yfinance",
        cache_key_prefixes=["SPY:15:"],
        db_path=db_path,
    )

    assert deleted == 1
    assert provider_cache.load_cached_payload("intraday_market_data", "yfinance", "SPY:15:78", db_path=db_path) is None
    assert provider_cache.load_cached_payload("intraday_market_data", "yfinance", "QQQ:15:78", db_path=db_path) == [{"close": 2}]


def test_warm_market_data_cache_forces_yfinance_fetches(monkeypatch) -> None:
    calls = []
    bars = _bars(["2026-01-02"])

    def fake_eod(symbols, _config, *, lookback_bars, force_refresh, provider):
        calls.append(("eod", symbols, lookback_bars, force_refresh, provider))
        return {symbol: bars for symbol in symbols}

    def fake_intraday(symbols, _config, *, lookback_bars, bar_minutes, force_refresh, provider):
        calls.append(("intraday", symbols, lookback_bars, bar_minutes, force_refresh, provider))
        return {symbol: bars for symbol in symbols}

    monkeypatch.setattr(cache_warmup, "get_config", lambda: object())
    monkeypatch.setattr(cache_warmup, "_clear_market_cache", lambda *_args, **_kwargs: {"eod_duckdb_rows": 0})
    monkeypatch.setattr(cache_warmup, "market_bars_summary", lambda **_kwargs: [{"symbol": "SPY", "rows": 1}])
    monkeypatch.setattr("src.connectors.fetch_eod_market_bars", fake_eod)
    monkeypatch.setattr("src.connectors.fetch_intraday_market_bars", fake_intraday)

    result = cache_warmup.warm_market_data_cache(["SPY"], clear=True)

    assert result["fetched"]["eod_rows"] == {"SPY": 1}
    assert result["fetched"]["intraday_rows"] == {"SPY": 1}
    assert calls == [
        ("eod", ["SPY"], 98, True, "yfinance"),
        ("intraday", ["SPY"], 78, 15, True, "yfinance"),
    ]
