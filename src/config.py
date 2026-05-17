from __future__ import annotations
import os
from dataclasses import dataclass, field

from .universe import load_symbol_universe

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


SYMBOLS: list[str] = [
    "SPY",
    "QQQ",
    "IWM",
    "RSP",
    "VTI",
    "VT",
    "IEFA",
    "IEMG",
    "VGK",
    "INDA",
    "QUAL",
    "USMV",
    "VLUE",
    "VIG",
    "NOBL",
    "AIA",
    "PBW",
    "XBI",
    "XOP",
    "XRT",
    "XSD",
    "GTEK",
    "IBIT",
    "GLD",
    "SLV",
    "USO",
    "DBA",
    "CPER",
    "BND",
    "SHY",
    "IEF",
    "TLT",
    "HYG",
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
PAPER_TRADING = True
KILL_SWITCH = False
HISTORY_EXTRA_BUFFER_DAYS = 250
LOG_FILE = "logs/trading.log"
SOCIAL_TRENDS_CSV = ""
TRADABLES_CSV = "tradable_etfs.csv"
UNIVERSE_CSV = "tradable_universe.csv"
ALPACA_DATA_FEED = "iex"
ALPHA_VANTAGE_NEWS_CSV = "data/social_trends.csv"
ALPHA_VANTAGE_NEWS_LOOKBACK_DAYS = 30
ALPHA_VANTAGE_NEWS_LIMIT = 50
ALPHA_VANTAGE_MAX_SYMBOLS = 20
ALPHA_VANTAGE_REQUEST_DELAY_SECONDS = 0.0


def _str_to_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _parse_symbols(value: str | None, default: list[str]) -> list[str]:
    if value is None:
        return list(default)
    symbols = [item.strip().upper() for item in value.split(",") if item.strip()]
    return symbols or list(default)


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    return int(value)


def _float_env(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    return float(value)


@dataclass(frozen=True)
class Config:
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
    paper_trading: bool = PAPER_TRADING
    kill_switch: bool = KILL_SWITCH
    alpaca_api_key: str = ""
    alpaca_api_secret: str = ""
    alpaca_base_url: str = ""
    alpaca_data_feed: str = ALPACA_DATA_FEED
    history_extra_buffer_days: int = HISTORY_EXTRA_BUFFER_DAYS
    log_file: str = LOG_FILE
    social_trends_csv: str = SOCIAL_TRENDS_CSV
    tradables_csv: str = TRADABLES_CSV
    universe_csv: str = UNIVERSE_CSV
    alpha_vantage_api_key: str = ""
    alpha_vantage_news_csv: str = ALPHA_VANTAGE_NEWS_CSV
    alpha_vantage_news_lookback_days: int = ALPHA_VANTAGE_NEWS_LOOKBACK_DAYS
    alpha_vantage_news_limit: int = ALPHA_VANTAGE_NEWS_LIMIT
    alpha_vantage_max_symbols: int = ALPHA_VANTAGE_MAX_SYMBOLS
    alpha_vantage_request_delay_seconds: float = ALPHA_VANTAGE_REQUEST_DELAY_SECONDS


def get_config() -> Config:
    paper_trading = _str_to_bool(os.getenv("PAPER_TRADING"), True)
    kill_switch = _str_to_bool(os.getenv("KILL_SWITCH"), False)
    api_key = os.getenv("ALPACA_API_KEY", "")
    api_secret = os.getenv("ALPACA_API_SECRET", "")
    base_url = os.getenv(
        "ALPACA_BASE_URL",
        "https://paper-api.alpaca.markets" if paper_trading else "https://api.alpaca.markets",
    )
    symbols_env = os.getenv("SYMBOLS")
    universe_csv = os.getenv("UNIVERSE_CSV", UNIVERSE_CSV)
    tradables_csv = os.getenv("TRADABLES_CSV", TRADABLES_CSV)
    symbols = (
        _parse_symbols(symbols_env, SYMBOLS)
        if symbols_env is not None
        else load_symbol_universe(universe_csv, tradables_csv, SYMBOLS)
    )

    return Config(
        symbols=symbols,
        momentum_lookback_days=_int_env("MOMENTUM_LOOKBACK_DAYS", MOMENTUM_LOOKBACK_DAYS),
        short_momentum_lookback_days=_int_env("SHORT_MOMENTUM_LOOKBACK_DAYS", SHORT_MOMENTUM_LOOKBACK_DAYS),
        long_ma_days=_int_env("LONG_MA_DAYS", LONG_MA_DAYS),
        volume_lookback_days=_int_env("VOLUME_LOOKBACK_DAYS", VOLUME_LOOKBACK_DAYS),
        social_lookback_days=_int_env("SOCIAL_LOOKBACK_DAYS", SOCIAL_LOOKBACK_DAYS),
        max_weight_per_symbol=_float_env("MAX_WEIGHT_PER_SYMBOL", MAX_WEIGHT_PER_SYMBOL),
        max_portfolio_exposure=_float_env("MAX_PORTFOLIO_EXPOSURE", MAX_PORTFOLIO_EXPOSURE),
        max_longs=_int_env("MAX_LONGS", MAX_LONGS),
        min_composite_score=_float_env("MIN_COMPOSITE_SCORE", MIN_COMPOSITE_SCORE),
        price_momentum_weight=_float_env("PRICE_MOMENTUM_WEIGHT", PRICE_MOMENTUM_WEIGHT),
        social_momentum_weight=_float_env("SOCIAL_MOMENTUM_WEIGHT", SOCIAL_MOMENTUM_WEIGHT),
        volume_momentum_weight=_float_env("VOLUME_MOMENTUM_WEIGHT", VOLUME_MOMENTUM_WEIGHT),
        target_annual_vol=_float_env("TARGET_ANNUAL_VOL", TARGET_ANNUAL_VOL),
        cash_buffer=_float_env("CASH_BUFFER", CASH_BUFFER),
        min_trade_dollars=_float_env("MIN_TRADE_DOLLARS", MIN_TRADE_DOLLARS),
        rebalance_threshold=_float_env("REBALANCE_THRESHOLD", REBALANCE_THRESHOLD),
        transaction_cost_bps=_float_env("TRANSACTION_COST_BPS", TRANSACTION_COST_BPS),
        paper_trading=paper_trading,
        kill_switch=kill_switch,
        alpaca_api_key=api_key,
        alpaca_api_secret=api_secret,
        alpaca_base_url=base_url,
        alpaca_data_feed=os.getenv("ALPACA_DATA_FEED", ALPACA_DATA_FEED),
        history_extra_buffer_days=_int_env("HISTORY_EXTRA_BUFFER_DAYS", HISTORY_EXTRA_BUFFER_DAYS),
        log_file=os.getenv("LOG_FILE", LOG_FILE),
        social_trends_csv=os.getenv("SOCIAL_TRENDS_CSV", SOCIAL_TRENDS_CSV),
        tradables_csv=tradables_csv,
        universe_csv=universe_csv,
        alpha_vantage_api_key=os.getenv("ALPHA_VANTAGE_API_KEY", ""),
        alpha_vantage_news_csv=os.getenv("ALPHA_VANTAGE_NEWS_CSV", ALPHA_VANTAGE_NEWS_CSV),
        alpha_vantage_news_lookback_days=_int_env(
            "ALPHA_VANTAGE_NEWS_LOOKBACK_DAYS",
            ALPHA_VANTAGE_NEWS_LOOKBACK_DAYS,
        ),
        alpha_vantage_news_limit=_int_env("ALPHA_VANTAGE_NEWS_LIMIT", ALPHA_VANTAGE_NEWS_LIMIT),
        alpha_vantage_max_symbols=_int_env("ALPHA_VANTAGE_MAX_SYMBOLS", ALPHA_VANTAGE_MAX_SYMBOLS),
        alpha_vantage_request_delay_seconds=_float_env(
            "ALPHA_VANTAGE_REQUEST_DELAY_SECONDS",
            ALPHA_VANTAGE_REQUEST_DELAY_SECONDS,
        ),
    )
