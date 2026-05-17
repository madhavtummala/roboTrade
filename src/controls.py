from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from .universe import resolve_project_path

CONTROLS_PATH = "data/trading_controls.json"

DEFAULT_CONTROLS: dict[str, Any] = {
    "algorithm_enabled": True,
    "options_trading_enabled": False,
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
    return {
        "algorithm_enabled": _as_bool(raw.get("algorithm_enabled"), default=True),
        "options_trading_enabled": _as_bool(raw.get("options_trading_enabled"), default=False),
    }


def load_controls(path: str = CONTROLS_PATH) -> dict[str, Any]:
    controls_path = resolve_project_path(path)
    if not controls_path.exists():
        return sanitize_controls(DEFAULT_CONTROLS)

    with controls_path.open(encoding="utf-8") as handle:
        raw_controls = json.load(handle)
    return sanitize_controls(raw_controls)


def save_controls(controls: dict[str, Any], path: str = CONTROLS_PATH) -> dict[str, Any]:
    sanitized = sanitize_controls(controls)
    controls_path = resolve_project_path(path)
    controls_path.parent.mkdir(parents=True, exist_ok=True)
    controls_path.write_text(json.dumps(sanitized, indent=2, sort_keys=True), encoding="utf-8")
    return sanitized
