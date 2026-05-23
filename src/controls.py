from __future__ import annotations

from copy import deepcopy
from typing import Any

from .config import (
    load_algorithms_config,
    load_options_bot_config,
    load_raw_config,
    save_raw_config,
    save_algorithm_bot_config,
    save_options_bot_config,
)

CONTROLS_SECTION = "algorithmic_trading"
LEGACY_CONTROLS_SECTION = "trading_controls"

DEFAULT_CONTROLS: dict[str, Any] = {
    "trading_account_id": "",
    "equities": {
        "enabled": False,
        "strategy": "momentum_social",
    },
    "options": {
        "enabled": False,
        "strategy": "none",
        "account_id": "",
    },
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
        raw.update({key: value for key, value in controls.items() if key not in {"algorithm", "options_trading", "equities", "options"}})
        if isinstance(controls.get("equities"), dict):
            raw["equities"].update(controls["equities"])
        if isinstance(controls.get("options"), dict):
            raw["options"].update(controls["options"])
        if isinstance(controls.get("algorithm"), dict):
            raw["equities"].update(controls["algorithm"])
        if isinstance(controls.get("options_trading"), dict):
            raw["options"].update(controls["options_trading"])
        if "active_strategy" in controls:
            raw["equities"]["strategy"] = controls.get("active_strategy")
        if "algorithm_enabled" in controls:
            raw["equities"]["enabled"] = controls.get("algorithm_enabled")
        if "options_strategy" in controls:
            raw["options"]["strategy"] = controls.get("options_strategy")
        if "options_trading_enabled" in controls:
            raw["options"]["enabled"] = controls.get("options_trading_enabled")
        if "options_trading_account_id" in controls:
            raw["options"]["account_id"] = controls.get("options_trading_account_id")

    algorithm_strategy = str(raw["equities"].get("strategy") or DEFAULT_CONTROLS["equities"]["strategy"])[:80]
    algorithm_enabled = _as_bool(raw["equities"].get("enabled"), default=False) and algorithm_strategy != "none"
    options_strategy = str(raw["options"].get("strategy") or DEFAULT_CONTROLS["options"]["strategy"])[:80]
    options_enabled = _as_bool(raw["options"].get("enabled"), default=False) and options_strategy != "none"
    options_account_id = str(raw["options"].get("account_id") or raw.get("trading_account_id") or "")[:80]
    return {
        "trading_account_id": str(raw.get("trading_account_id") or "")[:80],
        "equities": {
            "enabled": algorithm_enabled,
            "strategy": algorithm_strategy,
        },
        "options": {
            "enabled": options_enabled,
            "strategy": options_strategy,
            "account_id": options_account_id,
        },
        "algorithm": {
            "enabled": algorithm_enabled,
            "strategy": algorithm_strategy,
        },
        "options_trading": {
            "enabled": options_enabled,
            "strategy": options_strategy,
            "account_id": options_account_id,
        },
        "algorithm_enabled": algorithm_enabled,
        "active_strategy": algorithm_strategy,
        "options_trading_enabled": options_enabled,
        "options_strategy": options_strategy,
        "options_trading_account_id": options_account_id,
    }


def _raw_controls_from_config(raw_config: dict[str, Any]) -> dict[str, Any]:
    section = raw_config.get(CONTROLS_SECTION)
    if isinstance(section, dict):
        return section
    legacy_section = raw_config.get(LEGACY_CONTROLS_SECTION)
    if isinstance(legacy_section, dict):
        return legacy_section
    legacy_keys = {
        "algorithm_enabled",
        "active_strategy",
        "options_trading_enabled",
        "options_strategy",
        "options_trading_account_id",
    }
    if any(key in raw_config for key in set(DEFAULT_CONTROLS) | {"algorithm", "options_trading"} | legacy_keys):
        return raw_config
    return DEFAULT_CONTROLS


def _raw_controls_from_bot_configs(path: str | None = None) -> dict[str, Any]:
    algorithm_config = load_algorithms_config(path)
    options_config = load_options_bot_config(path)
    raw: dict[str, Any] = {}
    algorithm_bot = algorithm_config.get("algorithm_bot") if isinstance(algorithm_config.get("algorithm_bot"), dict) else {}
    options_bot = options_config.get("options_bot") if isinstance(options_config.get("options_bot"), dict) else {}
    if algorithm_bot:
        raw["trading_account_id"] = algorithm_bot.get("trading_account_id", "")
        raw["equities"] = {
            "enabled": algorithm_bot.get("enabled", False),
            "strategy": algorithm_bot.get("strategy", "momentum_social"),
        }
    if options_bot:
        raw["options"] = {
            "enabled": options_bot.get("enabled", False),
            "strategy": options_bot.get("strategy", "none"),
            "account_id": options_bot.get("account_id", raw.get("trading_account_id", "")),
        }
    return raw


def load_controls(path: str | None = None) -> dict[str, Any]:
    bot_controls = _raw_controls_from_bot_configs(path)
    if bot_controls:
        return sanitize_controls(bot_controls)
    return sanitize_controls(_raw_controls_from_config(load_raw_config(path)))


def save_controls(controls: dict[str, Any], path: str | None = None) -> dict[str, Any]:
    sanitized = sanitize_controls(controls)
    if path is not None:
        raw_config = load_raw_config(path)
        raw_config.pop(LEGACY_CONTROLS_SECTION, None)
        raw_config[CONTROLS_SECTION] = {
            "trading_account_id": sanitized["trading_account_id"],
            "equities": sanitized["equities"],
            "options": sanitized["options"],
        }
        save_raw_config(raw_config, path)
        return sanitized

    algorithm_config = load_algorithms_config(path)
    algorithm_bot = algorithm_config.setdefault("algorithm_bot", {})
    if not isinstance(algorithm_bot, dict):
        algorithm_bot = {}
        algorithm_config["algorithm_bot"] = algorithm_bot
    algorithm_bot.update(
        {
            "trading_account_id": sanitized["trading_account_id"],
            "enabled": sanitized["equities"]["enabled"],
            "strategy": sanitized["equities"]["strategy"],
        }
    )
    save_algorithm_bot_config(algorithm_config, path)

    options_config = load_options_bot_config(path)
    options_bot = options_config.setdefault("options_bot", {})
    if not isinstance(options_bot, dict):
        options_bot = {}
        options_config["options_bot"] = options_bot
    options_bot.update(
        {
            "enabled": sanitized["options"]["enabled"],
            "strategy": sanitized["options"]["strategy"],
            "account_id": sanitized["options"]["account_id"],
        }
    )
    save_options_bot_config(options_config, path)
    return sanitized
