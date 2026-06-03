from __future__ import annotations
import logging
from math import floor
from uuid import uuid4

from src.brokerages.alpaca_client import submit_market_order
from src.notifications.service import request_trade_approval

logger = logging.getLogger(__name__)


def plan_position_orders(
    latest_prices: dict[str, float],
    current_positions: dict[str, int],
    target_weights: dict[str, float],
    equity: float,
    cash_buffer: float = 0.02,
    min_trade_dollars: float = 50.0,
    rebalance_threshold: float = 0.02,
) -> list[dict[str, str | int | float]]:
    """Build ordered market orders needed to move current positions toward target weights."""
    planned_orders: list[dict[str, str | int | float]] = []
    investable_equity = equity * max(0.0, min(1.0, 1.0 - cash_buffer))
    min_rebalance_dollars = max(min_trade_dollars, equity * max(rebalance_threshold, 0.0))

    symbols = sorted(set(target_weights) | set(current_positions))
    for symbol in symbols:
        target_weight = target_weights.get(symbol, 0.0)
        price = latest_prices.get(symbol)
        if price is None or price <= 0:
            logger.warning("Skipping %s because latest price is invalid: %s", symbol, price)
            continue

        target_dollar = investable_equity * max(target_weight, 0.0)
        target_shares = floor(target_dollar / price)
        current_shares = current_positions.get(symbol, 0)
        diff = target_shares - current_shares
        trade_dollars = abs(diff) * price

        if diff == 0 or trade_dollars < min_rebalance_dollars:
            logger.info(
                "No trade required for %s: target_shares=%s current_shares=%s drift_dollars=%.2f",
                symbol,
                target_shares,
                current_shares,
                trade_dollars,
            )
            continue

        side = "buy" if diff > 0 else "sell"
        quantity = abs(diff)
        planned_orders.append(
            {
                "symbol": symbol,
                "action": side,
                "quantity": quantity,
                "target_weight": target_weight,
                "target_shares": target_shares,
                "current_shares": current_shares,
                "trade_dollars": trade_dollars,
            }
        )

    return sorted(planned_orders, key=lambda order: 0 if order["action"] == "sell" else 1)


def _approval_skips(planned_orders: list[dict[str, str | int | float]], approval_id: str) -> list[dict[str, str | int | float]]:
    return [
        {
            **planned_order,
            "action": "skip",
            "quantity": 0,
            "approval_id": approval_id,
            "approval_status": "not_approved",
        }
        for planned_order in planned_orders
    ]


def submit_planned_orders(
    trading_client,
    planned_orders: list[dict[str, str | int | float]],
) -> list[dict[str, str | int | float]]:
    """Submit a precomputed order plan."""
    order_results: list[dict[str, str | int | float]] = []
    for desired_order in planned_orders:
        symbol = str(desired_order["symbol"])
        side = str(desired_order["action"])
        quantity = int(desired_order["quantity"])
        logger.info("Submitting %s order for %s qty=%s", side, symbol, quantity)
        order = submit_market_order(trading_client, symbol, side, quantity)
        order_results.append(
            {
                "symbol": symbol,
                "action": side,
                "quantity": quantity,
                "target_weight": desired_order["target_weight"],
                "target_shares": desired_order["target_shares"],
                "current_shares": desired_order["current_shares"],
                "trade_dollars": desired_order["trade_dollars"],
                "order_id": getattr(order, "id", "unknown"),
            }
        )

    return order_results


def sync_positions_to_targets(
    trading_client,
    latest_prices: dict[str, float],
    current_positions: dict[str, int],
    target_weights: dict[str, float],
    equity: float,
    cash_buffer: float = 0.02,
    min_trade_dollars: float = 50.0,
    rebalance_threshold: float = 0.02,
    require_approval: bool = False,
    approval_timeout_seconds: int = 300,
    approval_poll_seconds: int = 5,
) -> list[dict[str, str | int | float]]:
    """Send market orders to move current positions toward target weights."""
    planned_orders = plan_position_orders(
        latest_prices,
        current_positions,
        target_weights,
        equity,
        cash_buffer=cash_buffer,
        min_trade_dollars=min_trade_dollars,
        rebalance_threshold=rebalance_threshold,
    )
    if not planned_orders:
        return []

    if require_approval:
        approval_id = uuid4().hex[:10]
        approved = request_trade_approval(
            planned_orders,
            approval_id=approval_id,
            timeout_seconds=approval_timeout_seconds,
            poll_seconds=approval_poll_seconds,
        )
        if not approved:
            logger.warning("Trade approval %s was denied or timed out; skipping %s planned order(s)", approval_id, len(planned_orders))
            return _approval_skips(planned_orders, approval_id)

    return submit_planned_orders(trading_client, planned_orders)
