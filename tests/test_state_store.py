from __future__ import annotations

from src.state_store import load_state, save_state


def test_state_store_round_trips_json_payload(tmp_path) -> None:
    db_path = tmp_path / "state.sqlite"
    payload = {"enabled": True, "items": [{"symbol": "SPY", "amount": 25}]}

    save_state("dca_plan", payload, db_path=str(db_path))

    assert load_state("dca_plan", {}, db_path=str(db_path)) == payload


def test_state_store_migrates_legacy_json(tmp_path) -> None:
    db_path = tmp_path / "state.sqlite"
    legacy_path = tmp_path / "legacy.json"
    legacy_path.write_text('{"active_strategy": "none"}', encoding="utf-8")

    migrated = load_state("controls", {}, legacy_path=str(legacy_path), db_path=str(db_path))

    assert migrated == {"active_strategy": "none"}
    assert load_state("controls", {}, db_path=str(db_path)) == migrated
