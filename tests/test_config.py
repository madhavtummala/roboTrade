from __future__ import annotations

from src.config import get_config


def test_get_config_reads_yaml_accounts_and_knobs(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "trading_bot.yaml"
    config_path.write_text(
        """
accounts:
  default: paper
  items:
    paper:
      label: Paper Desk
      api_key_env: TEST_ALPACA_KEY
      api_secret_env: TEST_ALPACA_SECRET
      base_url: https://paper-api.alpaca.markets
      data_feed: iex
    second:
      label: Second Desk
      api_key_env: TEST_SECOND_KEY
      api_secret_env: TEST_SECOND_SECRET
      base_url: https://example.invalid
      data_feed: sip
tradable_universe:
  tradables_csv: missing_tradables.csv
  symbols:
    - AAA
    - BBB
algorithms:
  momentum_social:
    momentum_lookback_days: 42
    max_longs: 3
runtime:
  kill_switch: true
alpha_vantage:
  news_csv: data/custom_social.csv
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("TRADING_CONFIG_FILE", str(config_path))
    monkeypatch.setenv("TEST_ALPACA_KEY", "paper-key")
    monkeypatch.setenv("TEST_ALPACA_SECRET", "paper-secret")
    monkeypatch.delenv("KILL_SWITCH", raising=False)
    monkeypatch.delenv("ALPHA_VANTAGE_NEWS_CSV", raising=False)

    config = get_config()

    assert config.account_id == "paper"
    assert config.account_label == "Paper Desk"
    assert config.alpaca_api_key == "paper-key"
    assert config.alpaca_api_secret == "paper-secret"
    assert config.symbols == ["AAA", "BBB"]
    assert config.momentum_lookback_days == 42
    assert config.max_longs == 3
    assert config.kill_switch is True
    assert config.social_trends_csv == "data/custom_social.csv"
    assert config.alpha_vantage_news_csv == "data/custom_social.csv"
    assert "momentum_social" in config.algorithm_configs
    assert config.account_options == [
        {"id": "paper", "label": "Paper Desk"},
        {"id": "second", "label": "Second Desk"},
    ]
