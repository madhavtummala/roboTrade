from __future__ import annotations

import csv
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SYMBOL_COLUMNS = ("ticker", "symbol")


def resolve_project_path(path: str) -> Path:
    csv_path = Path(path)
    if csv_path.is_absolute():
        return csv_path
    return PROJECT_ROOT / csv_path


def load_symbols_from_csv(path: str) -> list[str]:
    """Load symbols from a CSV that contains a Ticker or Symbol column."""
    csv_path = resolve_project_path(path)
    if not csv_path.exists():
        logger.warning("Universe CSV does not exist: %s", csv_path)
        return []

    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            return []

        field_lookup = {field.lower(): field for field in reader.fieldnames}
        symbol_field = next((field_lookup[column] for column in SYMBOL_COLUMNS if column in field_lookup), None)
        if symbol_field is None:
            raise ValueError(f"{csv_path} must contain a Ticker or Symbol column.")

        symbols: list[str] = []
        seen: set[str] = set()
        for row in reader:
            symbol = str(row.get(symbol_field, "")).strip().upper()
            if not symbol or symbol in seen:
                continue
            seen.add(symbol)
            symbols.append(symbol)
        return symbols


def load_symbol_universe(
    universe_csv: str,
    tradables_csv: str,
    fallback_symbols: list[str],
) -> list[str]:
    """Load the configured universe and keep only symbols present in the master tradables CSV."""
    symbols = load_symbols_from_csv(universe_csv) if universe_csv else []
    if not symbols:
        symbols = list(fallback_symbols)

    tradables = set(load_symbols_from_csv(tradables_csv)) if tradables_csv else set()
    if not tradables:
        return symbols

    filtered = [symbol for symbol in symbols if symbol in tradables]
    removed = sorted(set(symbols) - tradables)
    if removed:
        logger.warning("Dropping symbols not found in tradables CSV: %s", ", ".join(removed))
    if not filtered:
        raise ValueError("Configured trading universe has no symbols present in the tradables CSV.")
    return filtered
