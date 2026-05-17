from __future__ import annotations

from src.dca import allocation_preview, sanitize_dca_plan


UNIVERSE = [
    {"symbol": "SPY", "name": "SPY", "bucket": "Broad", "enabled": True},
    {"symbol": "QQQ", "name": "QQQ", "bucket": "Growth", "enabled": True},
    {"symbol": "GLD", "name": "GLD", "bucket": "Gold", "enabled": True},
]


def test_sanitize_dca_plan_keeps_only_universe_symbols() -> None:
    plan = {
        "enabled": True,
        "frequency": "daily",
        "accumulate": {"enabled": True, "amount": 100, "items": [{"symbol": "SPY"}, {"symbol": "BAD"}]},
        "sell": {"enabled": True, "amount": 50, "items": [{"symbol": "QQQ"}, {"symbol": "SPY"}]},
    }

    sanitized = sanitize_dca_plan(plan, UNIVERSE)

    assert [item["symbol"] for item in sanitized["accumulate"]["items"]] == ["SPY"]
    assert [item["symbol"] for item in sanitized["sell"]["items"]] == ["QQQ"]


def test_allocation_preview_uses_exact_item_amounts() -> None:
    plan = sanitize_dca_plan(
        {
            "enabled": True,
            "frequency": "weekly",
            "max_item_amount": 100,
            "accumulate": {
                "enabled": True,
                "items": [
                    {"symbol": "SPY", "amount": 60},
                    {"symbol": "QQQ", "amount": 30},
                    {"symbol": "GLD", "amount": 10},
                ],
            },
            "sell": {"enabled": False, "amount": 0, "items": []},
        },
        UNIVERSE,
    )

    preview = allocation_preview(plan)

    assert [row["symbol"] for row in preview] == ["SPY", "QQQ", "GLD"]
    assert [round(row["notional"], 2) for row in preview] == [60.0, 30.0, 10.0]


def test_sanitize_dca_plan_clamps_item_amount_to_max() -> None:
    plan = sanitize_dca_plan(
        {
            "max_item_amount": 100,
            "accumulate": {"items": [{"symbol": "SPY", "amount": 140}]},
            "sell": {"items": []},
        },
        UNIVERSE,
    )

    assert plan["accumulate"]["items"][0]["amount"] == 100


def test_sanitize_dca_plan_preserves_clamped_symbol_position() -> None:
    plan = sanitize_dca_plan(
        {
            "accumulate": {"items": [{"symbol": "SPY", "amount": 40, "position": {"x": 2, "y": -0.25}}]},
            "sell": {"items": []},
        },
        UNIVERSE,
    )

    assert plan["accumulate"]["items"][0]["position"] == {"x": 1.0, "y": -0.25}
