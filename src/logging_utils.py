from __future__ import annotations
import logging
import os
from pathlib import Path


def configure_logging(log_file: str = "logs/trading.log") -> None:
    """Configure root logging to the console and a rotating file."""
    log_dir = Path(log_file).parent
    log_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.handlers = [console_handler]

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)


def log_signals(signals: dict[str, dict[str, float | int]], prices: dict[str, float]) -> None:
    logger = logging.getLogger(__name__)
    logger.info("Computed signals for universe")
    for symbol, info in signals.items():
        price = prices.get(symbol, float("nan"))
        logger.info(
            "%s signal=%s score=%.3f price=%.3f social=%.3f volume=%.3f ret_N=%s close=%.2f sma_long=%.2f",
            symbol,
            info.get("signal"),
            info.get("score", 0.0),
            info.get("price_score", 0.0),
            info.get("social_score", 0.0),
            info.get("volume_score", 0.0),
            info.get("ret_N"),
            price,
            info.get("sma_long"),
        )


def log_portfolio(target_weights: dict[str, float], equity: float) -> None:
    logger = logging.getLogger(__name__)
    logger.info("Target portfolio weights computed")
    logger.info("Account equity: %.2f", equity)
    for symbol, weight in target_weights.items():
        logger.info("  %s -> %.2f%%", symbol, weight * 100)


def log_orders(order_results: list[dict[str, str | int | float]]) -> None:
    logger = logging.getLogger(__name__)
    if not order_results:
        logger.info("No orders were generated.")
        return

    logger.info("Order summary")
    for order in order_results:
        logger.info(
            "  %s %s qty=%s target=%s current=%s order_id=%s",
            order.get("action"),
            order.get("symbol"),
            order.get("quantity"),
            order.get("target_shares"),
            order.get("current_shares"),
            order.get("order_id", "n/a"),
        )
