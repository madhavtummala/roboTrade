from __future__ import annotations

from src.web_app import controls_payload, dca_payload, status_payload, universe_payload


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
