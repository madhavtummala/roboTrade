from __future__ import annotations

from datetime import datetime, timezone

from src.alpaca_client import get_historical_daily_bars, get_latest_price


class FakeDataClient:
    def __init__(self) -> None:
        self.requests = []

    def get_stock_bars(self, request):
        self.requests.append(request)
        return {"SPY": []}


def test_get_latest_price_builds_current_stock_bars_request() -> None:
    client = FakeDataClient()

    try:
        get_latest_price("SPY", client, end_date=datetime(2026, 5, 16, tzinfo=timezone.utc))
    except RuntimeError:
        pass

    assert client.requests[0].symbol_or_symbols == ["SPY"]
    assert client.requests[0].feed.value == "iex"


def test_get_historical_daily_bars_builds_current_stock_bars_request() -> None:
    client = FakeDataClient()

    get_historical_daily_bars(
        ["SPY"],
        lookback_days=10,
        extra_buffer_days=0,
        data_client=client,
        end_date=datetime(2026, 5, 16, tzinfo=timezone.utc),
    )

    assert client.requests[0].symbol_or_symbols == ["SPY"]
    assert client.requests[0].feed.value == "iex"
