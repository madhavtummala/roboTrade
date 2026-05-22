from __future__ import annotations
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .universe import load_tradable_names

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    import yaml
except ImportError:  # pragma: no cover - exercised when PyYAML is not installed.
    yaml = None


SYMBOLS: list[str] = [
    "SPY",
    "QQQ",
    "IBIT",
    "GLD",
    "TLT",
]
MOMENTUM_LOOKBACK_DAYS = 63
SHORT_MOMENTUM_LOOKBACK_DAYS = 21
LONG_MA_DAYS = 200
VOLUME_LOOKBACK_DAYS = 20
SOCIAL_LOOKBACK_DAYS = 30
MAX_WEIGHT_PER_SYMBOL = 0.25
MAX_PORTFOLIO_EXPOSURE = 0.95
MAX_LONGS = 5
MIN_COMPOSITE_SCORE = 0.05
PRICE_MOMENTUM_WEIGHT = 0.55
SOCIAL_MOMENTUM_WEIGHT = 0.30
VOLUME_MOMENTUM_WEIGHT = 0.15
TARGET_ANNUAL_VOL = 0.18
CASH_BUFFER = 0.02
MIN_TRADE_DOLLARS = 50.0
REBALANCE_THRESHOLD = 0.02
TRANSACTION_COST_BPS = 1.0
BACKTEST_STARTING_EQUITY = 10_000.0
ALGORITHM_EQUITY_CAP = 0.0
KILL_SWITCH = False
ALPACA_BASE_URL = "https://paper-api.alpaca.markets"
HISTORY_EXTRA_BUFFER_DAYS = 250
LOG_FILE = "logs/trading.log"
TRADABLES_CSV = "tradable_etfs.csv"
ALPACA_DATA_FEED = "iex"
ALPHA_VANTAGE_NEWS_CSV = "data/social_trends.csv"
ALPHA_VANTAGE_NEWS_LOOKBACK_DAYS = 30
ALPHA_VANTAGE_NEWS_LIMIT = 50
ALPHA_VANTAGE_MAX_SYMBOLS = 20
ALPHA_VANTAGE_REQUEST_DELAY_SECONDS = 0.0
CONFIG_FILE = "config/trading_bot.yaml"


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _resolve_path(path: str | None) -> Path:
    if not path:
        return _project_root() / CONFIG_FILE
    candidate = Path(path)
    return candidate if candidate.is_absolute() else _project_root() / candidate


def _load_yaml_config(path: str | None = None) -> dict[str, Any]:
    config_path = config_file_path(path)
    if not config_path.exists():
        return {}
    content = config_path.read_text(encoding="utf-8")
    loaded = yaml.safe_load(content) if yaml is not None else _parse_simple_yaml(content)
    loaded = loaded or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"YAML config must contain a mapping at {config_path}")
    return loaded


def config_file_path(path: str | None = None) -> Path:
    return _resolve_path(path or os.getenv("TRADING_CONFIG_FILE", CONFIG_FILE))


def load_raw_config(path: str | None = None) -> dict[str, Any]:
    return _load_yaml_config(path)


def save_raw_config(config: dict[str, Any], path: str | None = None) -> Path:
    config_path = config_file_path(path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    if yaml is not None:
        content = yaml.safe_dump(config, sort_keys=False)
    else:
        content = _dump_simple_yaml(config)
    config_path.write_text(content, encoding="utf-8")
    return config_path


def save_universe_symbols(symbols: list[str], path: str | None = None) -> Path:
    raw_config = load_raw_config(path)
    universe = raw_config.setdefault("tradable_universe", {})
    if not isinstance(universe, dict):
        universe = {}
        raw_config["tradable_universe"] = universe
    universe["symbols"] = [str(symbol).strip().upper() for symbol in symbols if str(symbol).strip()]
    return save_raw_config(raw_config, path)


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if value in {"", "''", '""'}:
        return ""
    if value == "[]":
        return []
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def _parse_simple_yaml(content: str) -> dict[str, Any]:
    root: dict[str, Any] = {}
    stack: list[dict[str, Any]] = [{"indent": -1, "container": root, "parent": None, "key": None}]
    for raw_line in content.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()
        while stack and indent <= stack[-1]["indent"]:
            stack.pop()
        if stripped.startswith("- "):
            entry = stack[-1]
            container = entry["container"]
            if isinstance(container, dict) and not container and entry["parent"] is not None:
                container = []
                entry["parent"][entry["key"]] = container
                entry["container"] = container
            if isinstance(container, list):
                container.append(_parse_scalar(stripped[2:]))
            continue
        if ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        parent = stack[-1]["container"]
        if not isinstance(parent, dict):
            continue
        if value.strip():
            parent[key.strip()] = _parse_scalar(value)
        else:
            child: dict[str, Any] = {}
            parent[key.strip()] = child
            stack.append({"indent": indent, "container": child, "parent": parent, "key": key.strip()})
    return root


def _format_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if value == "":
        return '""'
    text = str(value)
    if any(char in text for char in [":", "#", "{", "}", "[", "]"]) or text.strip() != text:
        return f'"{text}"'
    return text


def _dump_simple_yaml(value: Any, indent: int = 0) -> str:
    lines: list[str] = []
    prefix = " " * indent
    if isinstance(value, dict):
        for key, item in value.items():
            if item == []:
                lines.append(f"{prefix}{key}: []")
                continue
            if isinstance(item, (dict, list)):
                lines.append(f"{prefix}{key}:")
                lines.append(_dump_simple_yaml(item, indent + 2))
            else:
                lines.append(f"{prefix}{key}: {_format_scalar(item)}")
    elif isinstance(value, list):
        if not value:
            lines.append(f"{prefix}[]")
        for item in value:
            if isinstance(item, (dict, list)):
                lines.append(f"{prefix}-")
                lines.append(_dump_simple_yaml(item, indent + 2))
            else:
                lines.append(f"{prefix}- {_format_scalar(item)}")
    return "\n".join(line for line in lines if line != "") + ("\n" if indent == 0 else "")


def _section(config: dict[str, Any], name: str) -> dict[str, Any]:
    value = config.get(name, {})
    return value if isinstance(value, dict) else {}


def _env_ref(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        return os.getenv(value[2:-1], default)
    return str(value)


def _config_value(section: dict[str, Any], key: str, env_name: str, default: Any) -> Any:
    if env_name in os.environ:
        return os.getenv(env_name)
    return section.get(key, default)


def _str_to_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _parse_symbols(value: str | None, default: list[str]) -> list[str]:
    if value is None:
        return list(default)
    symbols = [item.strip().upper() for item in value.split(",") if item.strip()]
    return symbols or list(default)


def _as_int(value: Any, default: int) -> int:
    if value is None or value == "":
        return default
    return int(value)


def _as_float(value: Any, default: float) -> float:
    if value is None or value == "":
        return default
    return float(value)


@dataclass(frozen=True)
class Config:
    account_id: str = "default"
    account_label: str = "Default"
    algorithm_id: str = "momentum_social"
    symbols: list[str] = field(default_factory=lambda: list(SYMBOLS))
    momentum_lookback_days: int = MOMENTUM_LOOKBACK_DAYS
    short_momentum_lookback_days: int = SHORT_MOMENTUM_LOOKBACK_DAYS
    long_ma_days: int = LONG_MA_DAYS
    volume_lookback_days: int = VOLUME_LOOKBACK_DAYS
    social_lookback_days: int = SOCIAL_LOOKBACK_DAYS
    max_weight_per_symbol: float = MAX_WEIGHT_PER_SYMBOL
    max_portfolio_exposure: float = MAX_PORTFOLIO_EXPOSURE
    max_longs: int = MAX_LONGS
    min_composite_score: float = MIN_COMPOSITE_SCORE
    price_momentum_weight: float = PRICE_MOMENTUM_WEIGHT
    social_momentum_weight: float = SOCIAL_MOMENTUM_WEIGHT
    volume_momentum_weight: float = VOLUME_MOMENTUM_WEIGHT
    target_annual_vol: float = TARGET_ANNUAL_VOL
    cash_buffer: float = CASH_BUFFER
    min_trade_dollars: float = MIN_TRADE_DOLLARS
    rebalance_threshold: float = REBALANCE_THRESHOLD
    transaction_cost_bps: float = TRANSACTION_COST_BPS
    backtest_starting_equity: float = BACKTEST_STARTING_EQUITY
    algorithm_equity_cap: float = ALGORITHM_EQUITY_CAP
    kill_switch: bool = KILL_SWITCH
    alpaca_api_key: str = ""
    alpaca_api_secret: str = ""
    alpaca_base_url: str = ALPACA_BASE_URL
    alpaca_data_feed: str = ALPACA_DATA_FEED
    history_extra_buffer_days: int = HISTORY_EXTRA_BUFFER_DAYS
    log_file: str = LOG_FILE
    social_trends_csv: str = ALPHA_VANTAGE_NEWS_CSV
    tradables_csv: str = TRADABLES_CSV
    alpha_vantage_api_key: str = ""
    alpha_vantage_news_csv: str = ALPHA_VANTAGE_NEWS_CSV
    alpha_vantage_news_lookback_days: int = ALPHA_VANTAGE_NEWS_LOOKBACK_DAYS
    alpha_vantage_news_limit: int = ALPHA_VANTAGE_NEWS_LIMIT
    alpha_vantage_max_symbols: int = ALPHA_VANTAGE_MAX_SYMBOLS
    alpha_vantage_request_delay_seconds: float = ALPHA_VANTAGE_REQUEST_DELAY_SECONDS
    account_options: list[dict[str, str]] = field(default_factory=list)
    algorithm_configs: dict[str, dict[str, Any]] = field(default_factory=dict)


def get_config(account_id: str | None = None, strategy_id: str | None = None) -> Config:
    raw_config = _load_yaml_config()
    accounts = _section(raw_config, "accounts")
    account_items = _section(accounts, "items")
    default_account_id = str(accounts.get("default") or os.getenv("TRADING_ACCOUNT_ID") or "default")
    selected_account_id = str(account_id or os.getenv("TRADING_ACCOUNT_ID") or default_account_id)
    account_config = _section(account_items, selected_account_id)
    if not account_config and account_items:
        selected_account_id = default_account_id if default_account_id in account_items else next(iter(account_items))
        account_config = _section(account_items, selected_account_id)

    universe = _section(raw_config, "tradable_universe")
    legacy_algorithm = _section(raw_config, "algorithm")
    algorithm_configs = _section(raw_config, "algorithms")
    selected_strategy_id = str(strategy_id or "momentum_social")
    algorithm = {**legacy_algorithm, **_section(algorithm_configs, selected_strategy_id)}
    runtime = _section(raw_config, "runtime")
    social = _section(raw_config, "social")
    alpha_vantage = _section(raw_config, "alpha_vantage")

    kill_switch = _str_to_bool(str(_config_value(runtime, "kill_switch", "KILL_SWITCH", KILL_SWITCH)), KILL_SWITCH)
    api_key = _env_ref(account_config.get("api_key", account_config.get("api_key_env")), os.getenv("ALPACA_API_KEY", ""))
    if str(account_config.get("api_key_env", "")).strip():
        api_key = os.getenv(str(account_config["api_key_env"]).strip(), api_key)
    api_secret = _env_ref(
        account_config.get("api_secret", account_config.get("api_secret_env")),
        os.getenv("ALPACA_API_SECRET", ""),
    )
    if str(account_config.get("api_secret_env", "")).strip():
        api_secret = os.getenv(str(account_config["api_secret_env"]).strip(), api_secret)
    base_url = str(
        _config_value(account_config, "base_url", "ALPACA_BASE_URL", ALPACA_BASE_URL)
    ).strip() or ALPACA_BASE_URL
    symbols_env = os.getenv("SYMBOLS")
    tradables_csv = str(_config_value(universe, "tradables_csv", "TRADABLES_CSV", TRADABLES_CSV))
    yaml_symbols = universe.get("symbols")
    if symbols_env is not None:
        symbols = _parse_symbols(symbols_env, SYMBOLS)
    elif isinstance(yaml_symbols, list) and yaml_symbols:
        symbols = [str(item).strip().upper() for item in yaml_symbols if str(item).strip()]
    else:
        tradable_names = load_tradable_names(tradables_csv)
        symbols = list(SYMBOLS)
        if tradable_names:
            symbols = [symbol for symbol in symbols if symbol in tradable_names]
    if not symbols:
        raise ValueError("Configured trading universe must include at least one symbol.")
    alpha_vantage_api_key = _env_ref(
        alpha_vantage.get("api_key", alpha_vantage.get("api_key_env")),
        os.getenv("ALPHA_VANTAGE_API_KEY", ""),
    )
    if str(alpha_vantage.get("api_key_env", "")).strip():
        alpha_vantage_api_key = os.getenv(str(alpha_vantage["api_key_env"]).strip(), alpha_vantage_api_key)
    account_options = [
        {"id": str(key), "label": str(_section(account_items, str(key)).get("label") or key)}
        for key in account_items
    ] or [{"id": selected_account_id, "label": str(account_config.get("label") or "Default")}]
    alpha_vantage_news_csv = str(_config_value(alpha_vantage, "news_csv", "ALPHA_VANTAGE_NEWS_CSV", ALPHA_VANTAGE_NEWS_CSV))
    social_trends_csv = str(social.get("trends_csv") or alpha_vantage_news_csv)

    return Config(
        account_id=selected_account_id,
        account_label=str(account_config.get("label") or selected_account_id),
        algorithm_id=selected_strategy_id,
        symbols=symbols,
        momentum_lookback_days=_as_int(_config_value(algorithm, "momentum_lookback_days", "MOMENTUM_LOOKBACK_DAYS", MOMENTUM_LOOKBACK_DAYS), MOMENTUM_LOOKBACK_DAYS),
        short_momentum_lookback_days=_as_int(_config_value(algorithm, "short_momentum_lookback_days", "SHORT_MOMENTUM_LOOKBACK_DAYS", SHORT_MOMENTUM_LOOKBACK_DAYS), SHORT_MOMENTUM_LOOKBACK_DAYS),
        long_ma_days=_as_int(_config_value(algorithm, "long_ma_days", "LONG_MA_DAYS", LONG_MA_DAYS), LONG_MA_DAYS),
        volume_lookback_days=_as_int(_config_value(algorithm, "volume_lookback_days", "VOLUME_LOOKBACK_DAYS", VOLUME_LOOKBACK_DAYS), VOLUME_LOOKBACK_DAYS),
        social_lookback_days=_as_int(_config_value(algorithm, "social_lookback_days", "SOCIAL_LOOKBACK_DAYS", SOCIAL_LOOKBACK_DAYS), SOCIAL_LOOKBACK_DAYS),
        max_weight_per_symbol=_as_float(_config_value(algorithm, "max_weight_per_symbol", "MAX_WEIGHT_PER_SYMBOL", MAX_WEIGHT_PER_SYMBOL), MAX_WEIGHT_PER_SYMBOL),
        max_portfolio_exposure=_as_float(_config_value(algorithm, "max_portfolio_exposure", "MAX_PORTFOLIO_EXPOSURE", MAX_PORTFOLIO_EXPOSURE), MAX_PORTFOLIO_EXPOSURE),
        max_longs=_as_int(_config_value(algorithm, "max_longs", "MAX_LONGS", MAX_LONGS), MAX_LONGS),
        min_composite_score=_as_float(_config_value(algorithm, "min_composite_score", "MIN_COMPOSITE_SCORE", MIN_COMPOSITE_SCORE), MIN_COMPOSITE_SCORE),
        price_momentum_weight=_as_float(_config_value(algorithm, "price_momentum_weight", "PRICE_MOMENTUM_WEIGHT", PRICE_MOMENTUM_WEIGHT), PRICE_MOMENTUM_WEIGHT),
        social_momentum_weight=_as_float(_config_value(algorithm, "social_momentum_weight", "SOCIAL_MOMENTUM_WEIGHT", SOCIAL_MOMENTUM_WEIGHT), SOCIAL_MOMENTUM_WEIGHT),
        volume_momentum_weight=_as_float(_config_value(algorithm, "volume_momentum_weight", "VOLUME_MOMENTUM_WEIGHT", VOLUME_MOMENTUM_WEIGHT), VOLUME_MOMENTUM_WEIGHT),
        target_annual_vol=_as_float(_config_value(algorithm, "target_annual_vol", "TARGET_ANNUAL_VOL", TARGET_ANNUAL_VOL), TARGET_ANNUAL_VOL),
        cash_buffer=_as_float(_config_value(algorithm, "cash_buffer", "CASH_BUFFER", CASH_BUFFER), CASH_BUFFER),
        min_trade_dollars=_as_float(_config_value(algorithm, "min_trade_dollars", "MIN_TRADE_DOLLARS", MIN_TRADE_DOLLARS), MIN_TRADE_DOLLARS),
        rebalance_threshold=_as_float(_config_value(algorithm, "rebalance_threshold", "REBALANCE_THRESHOLD", REBALANCE_THRESHOLD), REBALANCE_THRESHOLD),
        transaction_cost_bps=_as_float(_config_value(algorithm, "transaction_cost_bps", "TRANSACTION_COST_BPS", TRANSACTION_COST_BPS), TRANSACTION_COST_BPS),
        backtest_starting_equity=_as_float(_config_value(algorithm, "backtest_starting_equity", "BACKTEST_STARTING_EQUITY", BACKTEST_STARTING_EQUITY), BACKTEST_STARTING_EQUITY),
        algorithm_equity_cap=_as_float(_config_value(algorithm, "algorithm_equity_cap", "ALGORITHM_EQUITY_CAP", ALGORITHM_EQUITY_CAP), ALGORITHM_EQUITY_CAP),
        kill_switch=kill_switch,
        alpaca_api_key=api_key,
        alpaca_api_secret=api_secret,
        alpaca_base_url=base_url,
        alpaca_data_feed=str(_config_value(account_config, "data_feed", "ALPACA_DATA_FEED", ALPACA_DATA_FEED)),
        history_extra_buffer_days=_as_int(_config_value(algorithm, "history_extra_buffer_days", "HISTORY_EXTRA_BUFFER_DAYS", HISTORY_EXTRA_BUFFER_DAYS), HISTORY_EXTRA_BUFFER_DAYS),
        log_file=str(_config_value(runtime, "log_file", "LOG_FILE", LOG_FILE)),
        social_trends_csv=social_trends_csv,
        tradables_csv=tradables_csv,
        alpha_vantage_api_key=alpha_vantage_api_key,
        alpha_vantage_news_csv=alpha_vantage_news_csv,
        alpha_vantage_news_lookback_days=_as_int(_config_value(alpha_vantage, "news_lookback_days", "ALPHA_VANTAGE_NEWS_LOOKBACK_DAYS", ALPHA_VANTAGE_NEWS_LOOKBACK_DAYS), ALPHA_VANTAGE_NEWS_LOOKBACK_DAYS),
        alpha_vantage_news_limit=_as_int(_config_value(alpha_vantage, "news_limit", "ALPHA_VANTAGE_NEWS_LIMIT", ALPHA_VANTAGE_NEWS_LIMIT), ALPHA_VANTAGE_NEWS_LIMIT),
        alpha_vantage_max_symbols=_as_int(_config_value(alpha_vantage, "max_symbols", "ALPHA_VANTAGE_MAX_SYMBOLS", ALPHA_VANTAGE_MAX_SYMBOLS), ALPHA_VANTAGE_MAX_SYMBOLS),
        alpha_vantage_request_delay_seconds=_as_float(_config_value(alpha_vantage, "request_delay_seconds", "ALPHA_VANTAGE_REQUEST_DELAY_SECONDS", ALPHA_VANTAGE_REQUEST_DELAY_SECONDS), ALPHA_VANTAGE_REQUEST_DELAY_SECONDS),
        account_options=account_options,
        algorithm_configs=algorithm_configs,
    )
