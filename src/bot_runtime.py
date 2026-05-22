from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import date, datetime, timezone
from math import floor
from typing import Any

from .alpaca_client import create_data_client, create_trading_client, get_latest_price, submit_market_order
from .config import get_config
from .controls import load_controls
from .dca import allocation_preview, load_dca_plan
from .live_runner import run_once

logger = logging.getLogger(__name__)

CHECK_SECONDS = 300


@dataclass
class RuntimeState:
    enabled: bool = False
    running: bool = False
    account_id: str = ""
    last_started_at: str | None = None
    last_finished_at: str | None = None
    last_error: str = ""
    last_run_date: str = ""


class _RuntimeLoop:
    def __init__(self, name: str, enabled_fn, run_fn) -> None:
        self.name = name
        self._enabled_fn = enabled_fn
        self._run_fn = run_fn
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._state = RuntimeState()

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._loop, name=f"dashboard-{self.name}-runtime", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    def wake(self) -> None:
        self.start()
        with self._lock:
            self._state.last_run_date = ""
        self._wake.set()

    def snapshot(self) -> dict[str, Any]:
        controls = load_controls()
        with self._lock:
            state = self._state.__dict__.copy()
        state["enabled"] = self._enabled_fn(controls)
        state["account_id"] = str(controls.get("trading_account_id") or state.get("account_id") or "")
        return state

    def _loop(self) -> None:
        while not self._stop.is_set():
            controls = load_controls()
            account_id = str(controls.get("trading_account_id") or "")
            enabled = self._enabled_fn(controls)
            with self._lock:
                self._state.enabled = enabled
                self._state.account_id = account_id
            if enabled and self._should_run_today():
                self._run_guarded(account_id)
            self._wake.wait(CHECK_SECONDS)
            self._wake.clear()

    def _should_run_today(self) -> bool:
        today = date.today().isoformat()
        with self._lock:
            return self._state.last_run_date != today

    def _run_guarded(self, account_id: str) -> None:
        with self._lock:
            if self._state.running:
                return
            self._state.running = True
            self._state.last_started_at = datetime.now(timezone.utc).isoformat()
            self._state.last_error = ""
        try:
            self._run_fn(account_id or None)
            with self._lock:
                self._state.last_run_date = date.today().isoformat()
        except Exception as exc:  # pragma: no cover - surfaced via status payload.
            logger.exception("%s runtime failed", self.name)
            with self._lock:
                self._state.last_error = str(exc)
        finally:
            with self._lock:
                self._state.running = False
                self._state.last_finished_at = datetime.now(timezone.utc).isoformat()


def _algorithm_enabled(controls: dict[str, Any]) -> bool:
    return bool(controls.get("algorithm_enabled")) and str(controls.get("active_strategy") or "none") != "none"


def _dca_enabled(_controls: dict[str, Any]) -> bool:
    config = get_config()
    from .api_payloads import universe_payload

    plan = load_dca_plan(universe_payload()["rows"])
    return bool(plan.get("enabled")) and not config.kill_switch


def _run_algorithm(account_id: str | None) -> None:
    run_once(account_id=account_id)


def _run_dca(account_id: str | None) -> None:
    from .api_payloads import universe_payload

    config = get_config(account_id=account_id)
    if config.kill_switch:
        logger.warning("Kill switch is enabled. Exiting DCA runtime without sending orders.")
        return

    plan = load_dca_plan(universe_payload()["rows"])
    preview = allocation_preview(plan)
    if not preview:
        return

    trading_client = create_trading_client(config)
    data_client = create_data_client(config)
    for row in preview:
        symbol = str(row["symbol"])
        side = str(row["action"])
        price = get_latest_price(symbol, data_client, data_feed=config.alpaca_data_feed)
        quantity = floor(float(row["notional"]) / price) if price > 0 else 0
        if quantity <= 0:
            logger.info("Skipping DCA %s for %s because notional is below one share", side, symbol)
            continue
        logger.info("Submitting DCA %s order for %s qty=%s", side, symbol, quantity)
        submit_market_order(trading_client, symbol, side, quantity)


class BotRuntime:
    def __init__(self) -> None:
        self.algorithm = _RuntimeLoop("algorithm", _algorithm_enabled, _run_algorithm)
        self.dca = _RuntimeLoop("dca", _dca_enabled, _run_dca)

    def start(self) -> None:
        self.algorithm.start()
        self.dca.start()

    def stop(self) -> None:
        self.algorithm.stop()
        self.dca.stop()

    def wake_algorithm(self) -> None:
        self.algorithm.wake()

    def wake_dca(self) -> None:
        self.dca.wake()

    def snapshot(self) -> dict[str, Any]:
        return {
            "algorithm": self.algorithm.snapshot(),
            "dca": self.dca.snapshot(),
        }


bot_runtime = BotRuntime()
