from __future__ import annotations

from src.controls import load_controls, sanitize_controls, save_controls


def test_sanitize_controls_defaults_and_bools() -> None:
    controls = sanitize_controls({"algorithm_enabled": "false", "options_trading_enabled": "yes"})

    assert controls == {
        "trading_account_id": "",
        "algorithm_enabled": False,
        "algorithm_power_confirmed": False,
        "options_trading_enabled": True,
        "active_strategy": "momentum_social",
        "backtest_strategy": "",
        "options_strategy": "none",
    }


def test_save_and_load_controls(tmp_path) -> None:
    controls_path = tmp_path / "controls.json"

    saved = save_controls(
        {"algorithm_enabled": False, "options_trading_enabled": True, "active_strategy": "breakout"},
        path=str(controls_path),
    )

    assert saved == load_controls(path=str(controls_path))
    assert saved["active_strategy"] == "breakout"


def test_old_algorithm_enabled_state_migrates_to_power_off() -> None:
    controls = sanitize_controls({"algorithm_enabled": True, "active_strategy": "breakout"})

    assert controls["algorithm_enabled"] is False
    assert controls["algorithm_power_confirmed"] is False


def test_load_controls_tolerates_trailing_corruption(tmp_path) -> None:
    controls_path = tmp_path / "controls.json"
    controls_path.write_text(
        '{"active_strategy": "none", "algorithm_enabled": false, "options_trading_enabled": false}junk',
        encoding="utf-8",
    )

    loaded = load_controls(path=str(controls_path))

    assert loaded["active_strategy"] == "none"
    assert loaded["algorithm_enabled"] is False
