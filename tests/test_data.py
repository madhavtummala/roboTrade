from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from src import data


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
    monkeypatch.setattr("src.alpaca_client.get_historical_daily_bars", fake_historical_bars)

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
    monkeypatch.setattr("src.alpaca_client.get_historical_daily_bars", fail_historical_bars)

    result = data.refresh_market_data_cache(
        ["SPY"],
        lookback_days=1,
        ma_days=0,
        extra_buffer_days=0,
        end_date=datetime(2024, 1, 4, tzinfo=timezone.utc),
        data_feed="iex",
    )

    assert result["SPY"]["timestamp"].dt.strftime("%Y-%m-%d").tolist() == ["2024-01-02"]
