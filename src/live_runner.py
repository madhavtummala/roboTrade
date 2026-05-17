from __future__ import annotations
import logging
from .config import get_config
from .controls import load_controls
from .alpaca_client import (
    create_data_client,
    create_trading_client,
    get_account_equity,
    get_positions,
    get_latest_price,
)
from .data import fetch_daily_bars
from .logging_utils import configure_logging, log_signals, log_portfolio, log_orders
from .orders import sync_positions_to_targets
from .portfolio import compute_target_weights
from .signals import compute_signals_for_universe
from .social import load_social_trends_csv

logger = logging.getLogger(__name__)


def main() -> None:
    config = get_config()
    configure_logging(config.log_file)

    logger.info("Starting live runner in %s mode", "PAPER" if config.paper_trading else "LIVE")

    if config.kill_switch:
        logger.warning("Kill switch is enabled. Exiting without sending orders.")
        return

    controls = load_controls()
    if not controls["algorithm_enabled"]:
        logger.warning("Algorithm trading is disabled in dashboard controls. Exiting without sending orders.")
        return

    trading_client = create_trading_client(config)
    data_client = create_data_client(config)

    equity = get_account_equity(trading_client)
    current_positions = get_positions(trading_client)

    bars_by_symbol = fetch_daily_bars(
        config.symbols,
        config.momentum_lookback_days,
        ma_days=config.long_ma_days,
        extra_buffer_days=config.history_extra_buffer_days,
        alpaca_data_client=data_client,
        data_feed=config.alpaca_data_feed,
    )
    social_by_symbol = load_social_trends_csv(config.social_trends_csv, config.symbols)

    signals = compute_signals_for_universe(
        bars_by_symbol,
        config.momentum_lookback_days,
        config.long_ma_days,
        short_lookback_days=config.short_momentum_lookback_days,
        volume_lookback_days=config.volume_lookback_days,
        social_by_symbol=social_by_symbol,
        social_lookback_days=config.social_lookback_days,
        price_momentum_weight=config.price_momentum_weight,
        social_momentum_weight=config.social_momentum_weight,
        volume_momentum_weight=config.volume_momentum_weight,
        min_composite_score=config.min_composite_score,
    )
    target_weights = compute_target_weights(
        signals,
        config.max_weight_per_symbol,
        max_portfolio_exposure=config.max_portfolio_exposure,
        max_longs=config.max_longs,
        target_annual_vol=config.target_annual_vol,
    )
    latest_prices = {
        symbol: get_latest_price(symbol, data_client, data_feed=config.alpaca_data_feed)
        for symbol in config.symbols
    }

    log_signals(signals, latest_prices)
    log_portfolio(target_weights, equity)
    order_results = sync_positions_to_targets(
        trading_client,
        latest_prices,
        current_positions,
        target_weights,
        equity,
        cash_buffer=config.cash_buffer,
        min_trade_dollars=config.min_trade_dollars,
        rebalance_threshold=config.rebalance_threshold,
    )
    log_orders(order_results)


if __name__ == "__main__":
    main()
