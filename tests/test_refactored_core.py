import pytest
import pandas as pd
from datetime import datetime, timezone
from src.core.interfaces import MarketDataRequest
from src.data.store import DataStore
from src.data.repository import DataRepository
from src.connectors.market.yfinance import YFinanceConnector

def test_datastore_initialization(tmp_path):
    pytest.importorskip("duckdb")
    db_path = tmp_path / "test.duckdb"
    store = DataStore(str(db_path))
    assert db_path.exists()

def test_market_data_request():
    req = MarketDataRequest(symbols=["AAPL"], timeframe="1d")
    assert req.symbols == ["AAPL"]
    assert req.timeframe == "1d"
    assert req.category == "market_data"

def test_yfinance_connector_caching(tmp_path, monkeypatch):
    pytest.importorskip("duckdb")
    db_path = tmp_path / "test.duckdb"
    store = DataStore(str(db_path))
    
    # Mock yfinance to avoid actual network calls
    mock_df = pd.DataFrame({
        "timestamp": [datetime.now(timezone.utc)],
        "open": [150.0],
        "high": [155.0],
        "low": [149.0],
        "close": [152.0],
        "volume": [1000000]
    })
    monkeypatch.setattr("yfinance.Ticker.history", lambda *_args, **_kwargs: mock_df)
    
    connector = YFinanceConnector({"enabled": True}, store=store)
    req = MarketDataRequest(symbols=["AAPL"], timeframe="1d")
    
    # First fetch (cold)
    res = connector.fetch_bars(req)
    assert "AAPL" in res
    assert not res["AAPL"].empty
    
    # Verify it's in the store
    cached = store.get_market_bars("AAPL", "1d", "yfinance", datetime.now(timezone.utc).replace(year=2000), datetime.now(timezone.utc))
    assert not cached.empty
