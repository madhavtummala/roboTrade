from __future__ import annotations

from src.universe import load_symbol_universe


def test_load_symbol_universe_filters_to_master_tradables(tmp_path) -> None:
    universe_csv = tmp_path / "universe.csv"
    tradables_csv = tmp_path / "tradables.csv"
    universe_csv.write_text("Ticker,Name\nAAA,Keep\nBAD,Drop\nBBB,Keep\n", encoding="utf-8")
    tradables_csv.write_text("Ticker,Name\nAAA,Tradable\nBBB,Tradable\n", encoding="utf-8")

    symbols = load_symbol_universe(str(universe_csv), str(tradables_csv), ["FALLBACK"])

    assert symbols == ["AAA", "BBB"]


def test_load_symbol_universe_uses_fallback_when_subset_missing(tmp_path) -> None:
    tradables_csv = tmp_path / "tradables.csv"
    tradables_csv.write_text("Ticker,Name\nAAA,Tradable\nBBB,Tradable\n", encoding="utf-8")

    symbols = load_symbol_universe(str(tmp_path / "missing.csv"), str(tradables_csv), ["AAA", "BBB", "BAD"])

    assert symbols == ["AAA", "BBB"]
