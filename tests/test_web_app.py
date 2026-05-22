from __future__ import annotations

from pathlib import Path

from src.web_app import controls_payload, dca_payload, status_payload, universe_payload


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_status_payload_redacts_secret_values() -> None:
    payload = status_payload()

    assert isinstance(payload["config"]["alpaca_api_key"], bool)
    assert isinstance(payload["config"]["alpaca_api_secret"], bool)
    assert isinstance(payload["config"]["alpha_vantage_api_key"], bool)


def test_universe_payload_returns_configured_rows() -> None:
    payload = universe_payload()

    assert payload["count"] > 0
    assert {"symbol", "name", "bucket", "tradable", "enabled"} <= set(payload["rows"][0])


def test_dca_payload_returns_plan_and_preview_shape() -> None:
    payload = dca_payload()

    assert "plan" in payload
    assert "available" in payload
    assert "preview" in payload
    assert {"enabled", "frequency", "accumulate", "sell"} <= set(payload["plan"])


def test_controls_payload_returns_switches() -> None:
    payload = controls_payload()

    assert {"algorithm_enabled", "options_trading_enabled"} <= set(payload["controls"])


def test_frontend_uses_six_month_backtests_and_refresh_button() -> None:
    app_js = (PROJECT_ROOT / "web/static/app.js").read_text(encoding="utf-8")
    index_html = (PROJECT_ROOT / "web/index.html").read_text(encoding="utf-8")

    assert 'const BACKTEST_PERIOD = "6m";' in app_js
    assert 'const BACKTEST_STORAGE_KEY = "tradingBot.backtests.6m.v3";' in app_js
    assert "6M" in app_js
    assert "Ending equity =" in app_js
    assert "cash cap" not in app_js
    assert "${money(backtest.ending_equity)} end" not in app_js
    assert "cumulative turnover" in app_js
    assert "chart-crosshair" in app_js
    assert "Invested ${money(row.invested)}" in app_js
    assert "Running" not in app_js
    assert "app.js?v=20260521-universe-review" in index_html
