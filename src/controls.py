from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from .state_store import load_state, save_state
from .universe import resolve_project_path

CONTROLS_PATH = "data/trading_controls.json"
CONTROLS_STATE_KEY = "controls"

DEFAULT_CONTROLS: dict[str, Any] = {
    "trading_account_id": "",
    "algorithm_enabled": False,
    "algorithm_power_confirmed": False,
    "options_trading_enabled": False,
    "active_strategy": "momentum_social",
    "backtest_strategy": "",
    "options_strategy": "none",
}


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def sanitize_controls(controls: dict[str, Any] | None) -> dict[str, Any]:
    raw = deepcopy(DEFAULT_CONTROLS)
    if controls:
        raw.update(controls)
    algorithm_power_confirmed = _as_bool(raw.get("algorithm_power_confirmed"), default=False)
    return {
        "trading_account_id": str(raw.get("trading_account_id") or "")[:80],
        "algorithm_enabled": _as_bool(raw.get("algorithm_enabled"), default=False) and algorithm_power_confirmed,
        "algorithm_power_confirmed": algorithm_power_confirmed,
        "options_trading_enabled": _as_bool(raw.get("options_trading_enabled"), default=False),
        "active_strategy": str(raw.get("active_strategy") or DEFAULT_CONTROLS["active_strategy"])[:80],
        "backtest_strategy": str(raw.get("backtest_strategy") or "")[:80],
        "options_strategy": str(raw.get("options_strategy") or DEFAULT_CONTROLS["options_strategy"])[:80],
    }


def load_controls(path: str = CONTROLS_PATH) -> dict[str, Any]:
    if path == CONTROLS_PATH:
        return sanitize_controls(load_state(CONTROLS_STATE_KEY, DEFAULT_CONTROLS, legacy_path=CONTROLS_PATH))

    controls_path = resolve_project_path(path)
    if not controls_path.exists():
        return sanitize_controls(DEFAULT_CONTROLS)

    try:
        content = controls_path.read_text(encoding="utf-8")
        raw_controls = json.loads(content)
    except json.JSONDecodeError:
        try:
            raw_controls, _ = json.JSONDecoder().raw_decode(content)
        except json.JSONDecodeError:
            raw_controls = DEFAULT_CONTROLS
    return sanitize_controls(raw_controls)


def save_controls(controls: dict[str, Any], path: str = CONTROLS_PATH) -> dict[str, Any]:
    sanitized = sanitize_controls(controls)
    if path == CONTROLS_PATH:
        save_state(CONTROLS_STATE_KEY, sanitized)
        return sanitized

    controls_path = resolve_project_path(path)
    controls_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = controls_path.with_suffix(f"{controls_path.suffix}.tmp")
    tmp_path.write_text(json.dumps(sanitized, indent=2, sort_keys=True), encoding="utf-8")
    tmp_path.replace(controls_path)
    return sanitized
