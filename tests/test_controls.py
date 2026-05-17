from __future__ import annotations

from src.controls import load_controls, sanitize_controls, save_controls


def test_sanitize_controls_defaults_and_bools() -> None:
    controls = sanitize_controls({"algorithm_enabled": "false", "options_trading_enabled": "yes"})

    assert controls == {
        "algorithm_enabled": False,
        "options_trading_enabled": True,
    }


def test_save_and_load_controls(tmp_path) -> None:
    controls_path = tmp_path / "controls.json"

    saved = save_controls(
        {"algorithm_enabled": False, "options_trading_enabled": True},
        path=str(controls_path),
    )

    assert saved == load_controls(path=str(controls_path))
