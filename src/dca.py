from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from .state_store import load_state, save_state
from .universe import resolve_project_path

DCA_PLAN_PATH = "data/dca_plan.json"
DCA_PLAN_STATE_KEY = "dca_plan"
DCA_MAX_ITEM_AMOUNT = 50.0

DEFAULT_DCA_PLAN: dict[str, Any] = {
    "enabled": False,
    "frequency": "weekly",
    "schedule_pattern": "0 12 * * 1-5",
    "next_run_date": "",
    "max_item_amount": DCA_MAX_ITEM_AMOUNT,
    "accumulate": {
        "enabled": True,
        "amount": 100.0,
        "items": [
            {"symbol": "SPY", "amount": 25.0},
            {"symbol": "QQQ", "amount": 20.0},
            {"symbol": "GLD", "amount": 15.0},
            {"symbol": "TLT", "amount": 10.0},
        ],
    },
    "sell": {
        "enabled": False,
        "amount": 0.0,
        "items": [],
    },
}

FREQUENCIES = {"daily", "weekly", "biweekly", "monthly"}
BUCKETS = ("accumulate", "sell")


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return max(parsed, 0.0)


def _as_unit_float(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return min(max(parsed, -1.0), 1.0)


def _universe_lookup(universe_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(row["symbol"]).upper(): row for row in universe_rows if row.get("symbol")}


def sanitize_dca_plan(plan: dict[str, Any] | None, universe_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Normalize a DCA plan and keep only symbols present in the configured universe."""
    raw_plan = deepcopy(DEFAULT_DCA_PLAN)
    if plan:
        raw_plan.update({key: value for key, value in plan.items() if key not in BUCKETS})
        for bucket in BUCKETS:
            if isinstance(plan.get(bucket), dict):
                raw_plan[bucket].update(plan[bucket])

    universe = _universe_lookup(universe_rows)
    sanitized = {
        "enabled": _as_bool(raw_plan.get("enabled")),
        "frequency": raw_plan.get("frequency") if raw_plan.get("frequency") in FREQUENCIES else "weekly",
        "schedule_pattern": str(raw_plan.get("schedule_pattern") or DEFAULT_DCA_PLAN["schedule_pattern"])[:80],
        "next_run_date": str(raw_plan.get("next_run_date") or ""),
        "max_item_amount": min(
            max(_as_float(raw_plan.get("max_item_amount"), default=DCA_MAX_ITEM_AMOUNT), 1.0),
            DCA_MAX_ITEM_AMOUNT,
        ),
    }

    for bucket in BUCKETS:
        bucket_plan = raw_plan.get(bucket, {})
        raw_items = bucket_plan.get("items", [])
        fallback_amounts = _legacy_item_amounts(raw_items, _as_float(bucket_plan.get("amount"), default=0.0))
        assigned_symbols: set[str] = set()
        items: list[dict[str, Any]] = []
        for index, item in enumerate(raw_items):
            symbol = str(item.get("symbol", "")).strip().upper()
            if not symbol or symbol not in universe or symbol in assigned_symbols:
                continue
            assigned_symbols.add(symbol)
            amount = min(
                _as_float(item.get("amount"), default=fallback_amounts.get(index, 0.0)),
                sanitized["max_item_amount"],
                DCA_MAX_ITEM_AMOUNT,
            )
            sanitized_item = {
                "symbol": symbol,
                "name": universe[symbol].get("name", ""),
                "bucket": universe[symbol].get("bucket", ""),
                "amount": amount,
            }
            position = item.get("position")
            if isinstance(position, dict) and ("x" in position or "y" in position):
                sanitized_item["position"] = {
                    "x": _as_unit_float(position.get("x")),
                    "y": _as_unit_float(position.get("y")),
                }
            items.append(sanitized_item)

        sanitized[bucket] = {
            "enabled": _as_bool(bucket_plan.get("enabled"), default=bucket == "accumulate"),
            "amount": sum(item["amount"] for item in items),
            "items": items,
        }

    return sanitized


def load_dca_plan(universe_rows: list[dict[str, Any]], path: str = DCA_PLAN_PATH) -> dict[str, Any]:
    if path == DCA_PLAN_PATH:
        return sanitize_dca_plan(load_state(DCA_PLAN_STATE_KEY, DEFAULT_DCA_PLAN, legacy_path=DCA_PLAN_PATH), universe_rows)

    plan_path = resolve_project_path(path)
    if not plan_path.exists():
        return sanitize_dca_plan(DEFAULT_DCA_PLAN, universe_rows)

    with plan_path.open(encoding="utf-8") as handle:
        raw_plan = json.load(handle)
    return sanitize_dca_plan(raw_plan, universe_rows)


def save_dca_plan(plan: dict[str, Any], universe_rows: list[dict[str, Any]], path: str = DCA_PLAN_PATH) -> dict[str, Any]:
    sanitized = sanitize_dca_plan(plan, universe_rows)
    if path == DCA_PLAN_PATH:
        save_state(DCA_PLAN_STATE_KEY, sanitized)
        return sanitized

    plan_path = resolve_project_path(path)
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(json.dumps(sanitized, indent=2, sort_keys=True), encoding="utf-8")
    return sanitized


def allocation_preview(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """Create planned DCA order rows from exact per-symbol dollar amounts."""
    rows: list[dict[str, Any]] = []
    if not plan.get("enabled"):
        return rows

    for bucket in BUCKETS:
        bucket_plan = plan.get(bucket, {})
        items = bucket_plan.get("items", [])
        bucket_total = sum(_as_float(item.get("amount")) for item in items)
        if not bucket_plan.get("enabled") or bucket_total <= 0 or not items:
            continue

        for index, item in enumerate(items):
            notional = _as_float(item.get("amount"))
            if notional <= 0:
                continue
            weight = notional / bucket_total if bucket_total else 0.0
            rows.append(
                {
                    "bucket": bucket,
                    "action": "buy" if bucket == "accumulate" else "sell",
                    "symbol": item["symbol"],
                    "name": item.get("name", ""),
                    "theme": item.get("bucket", ""),
                    "rank": index + 1,
                    "weight": weight,
                    "notional": notional,
                    "frequency": plan.get("frequency", "weekly"),
                    "next_run_date": plan.get("next_run_date", ""),
                }
            )
    return rows


def _legacy_item_amounts(items: list[dict[str, Any]], bucket_amount: float) -> dict[int, float]:
    if not items or bucket_amount <= 0:
        return {}
    if any("amount" in item for item in items):
        return {}
    total_priority = sum(range(1, len(items) + 1))
    return {
        index: bucket_amount * ((len(items) - index) / total_priority)
        for index in range(len(items))
    }
