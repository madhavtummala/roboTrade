from __future__ import annotations

import argparse
import json
import logging
import mimetypes
import re
from dataclasses import asdict
from datetime import datetime, time, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import pandas as pd
from alpaca.common.enums import Sort
from alpaca.trading.enums import QueryOrderStatus
from alpaca.trading.requests import GetOrdersRequest, GetPortfolioHistoryRequest

from .alpha_vantage import collect_alpha_vantage_news, write_social_trends_csv
from .alpaca_client import create_trading_client
from .backtest import calculate_performance_metrics, run_backtest
from .config import get_config
from .controls import load_controls, save_controls
from .dca import allocation_preview, load_dca_plan, save_dca_plan
from .social import load_social_trends_csv
from .universe import load_symbols_from_csv, resolve_project_path

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = PROJECT_ROOT / "web"


def _redact(value: str) -> str:
    config = get_config()
    secrets = [
        config.alpaca_api_key,
        config.alpaca_api_secret,
        config.alpha_vantage_api_key,
    ]
    redacted = value
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, "[redacted]")
    redacted = re.sub(r"(apikey=)[^&\s]+", r"\1[redacted]", redacted, flags=re.IGNORECASE)
    return redacted


def _safe_error(error: Exception) -> dict[str, str]:
    return {"error": _redact(str(error))}


def _file_info(path: str) -> dict[str, Any]:
    resolved = resolve_project_path(path)
    if not resolved.exists():
        return {"path": path, "exists": False}
    return {
        "path": path,
        "exists": True,
        "updated_at": pd.Timestamp.fromtimestamp(resolved.stat().st_mtime, tz="UTC").isoformat(),
        "size_bytes": resolved.stat().st_size,
    }


def status_payload() -> dict[str, Any]:
    config = get_config()
    social_info = _file_info(config.social_trends_csv)
    social_rows = 0
    social_symbols: set[str] = set()
    latest_social_timestamp = None

    if social_info["exists"]:
        try:
            df = pd.read_csv(resolve_project_path(config.social_trends_csv))
            if not df.empty:
                social_rows = len(df)
                if "symbol" in df:
                    social_symbols = set(df["symbol"].dropna().astype(str).str.upper())
                if "timestamp" in df:
                    timestamps = pd.to_datetime(df["timestamp"], utc=True, errors="coerce").dropna()
                    if not timestamps.empty:
                        latest_social_timestamp = timestamps.max().isoformat()
        except Exception as exc:  # pragma: no cover - status should stay available.
            social_info["error"] = _redact(str(exc))

    config_summary = asdict(config)
    for secret_field in ("alpaca_api_key", "alpaca_api_secret", "alpha_vantage_api_key"):
        config_summary[secret_field] = bool(config_summary.get(secret_field))

    return {
        "mode": "PAPER" if config.paper_trading else "LIVE",
        "kill_switch": config.kill_switch,
        "config": config_summary,
        "universe": {
            "count": len(config.symbols),
            "symbols": config.symbols,
            "universe_csv": config.universe_csv,
            "tradables_csv": config.tradables_csv,
        },
        "social": {
            **social_info,
            "rows": social_rows,
            "symbol_count": len(social_symbols),
            "latest_timestamp": latest_social_timestamp,
        },
        "risk": {
            "max_weight_per_symbol": config.max_weight_per_symbol,
            "max_portfolio_exposure": config.max_portfolio_exposure,
            "max_longs": config.max_longs,
            "target_annual_vol": config.target_annual_vol,
            "cash_buffer": config.cash_buffer,
        },
        "logs": _file_info(config.log_file),
    }


def universe_payload() -> dict[str, Any]:
    config = get_config()
    universe_path = resolve_project_path(config.universe_csv)
    tradables = set(load_symbols_from_csv(config.tradables_csv))

    rows: list[dict[str, Any]] = []
    if universe_path.exists():
        df = pd.read_csv(universe_path)
        for _, row in df.iterrows():
            symbol = str(row.get("Ticker", row.get("Symbol", ""))).strip().upper()
            if not symbol:
                continue
            rows.append(
                {
                    "symbol": symbol,
                    "name": str(row.get("Name", "")),
                    "bucket": str(row.get("Bucket", "")),
                    "tradable": symbol in tradables,
                    "enabled": symbol in config.symbols,
                }
            )

    return {"rows": rows, "count": len(rows)}


def dca_payload() -> dict[str, Any]:
    universe = universe_payload()["rows"]
    plan = load_dca_plan(universe)
    assigned = {
        item["symbol"]
        for bucket in ("accumulate", "sell")
        for item in plan.get(bucket, {}).get("items", [])
    }
    available = [row for row in universe if row["enabled"] and row["symbol"] not in assigned]
    return {
        "plan": plan,
        "available": available,
        "preview": allocation_preview(plan),
    }


def save_dca_payload(body: dict[str, Any]) -> dict[str, Any]:
    universe = universe_payload()["rows"]
    plan = save_dca_plan(body.get("plan", body), universe)
    assigned = {
        item["symbol"]
        for bucket in ("accumulate", "sell")
        for item in plan.get(bucket, {}).get("items", [])
    }
    available = [row for row in universe if row["enabled"] and row["symbol"] not in assigned]
    return {
        "plan": plan,
        "available": available,
        "preview": allocation_preview(plan),
    }


def controls_payload() -> dict[str, Any]:
    return {"controls": load_controls()}


def save_controls_payload(body: dict[str, Any]) -> dict[str, Any]:
    return {"controls": save_controls(body.get("controls", body))}


def account_payload() -> dict[str, Any]:
    config = get_config()
    trading_client = create_trading_client(config)
    account = trading_client.get_account()
    positions = trading_client.get_all_positions()

    equity = float(getattr(account, "equity", 0.0) or 0.0)
    last_equity = float(getattr(account, "last_equity", 0.0) or 0.0)
    day_pl = equity - last_equity if last_equity else 0.0
    day_plpc = day_pl / last_equity if last_equity else 0.0

    position_rows: list[dict[str, Any]] = []
    total_unrealized_pl = 0.0
    total_market_value = 0.0
    total_cost_basis = 0.0
    for position in positions:
        market_value = float(getattr(position, "market_value", 0.0) or 0.0)
        cost_basis = float(getattr(position, "cost_basis", 0.0) or 0.0)
        unrealized_pl = float(getattr(position, "unrealized_pl", 0.0) or 0.0)
        total_market_value += market_value
        total_cost_basis += cost_basis
        total_unrealized_pl += unrealized_pl
        position_rows.append(
            {
                "symbol": getattr(position, "symbol", ""),
                "qty": float(getattr(position, "qty", 0.0) or 0.0),
                "market_value": market_value,
                "cost_basis": cost_basis,
                "current_price": float(getattr(position, "current_price", 0.0) or 0.0),
                "unrealized_pl": unrealized_pl,
                "unrealized_plpc": float(getattr(position, "unrealized_plpc", 0.0) or 0.0),
            }
        )

    return {
        "equity": equity,
        "last_equity": last_equity,
        "cash": float(getattr(account, "cash", 0.0) or 0.0),
        "buying_power": float(getattr(account, "buying_power", 0.0) or 0.0),
        "portfolio_value": float(getattr(account, "portfolio_value", equity) or equity),
        "day_pl": day_pl,
        "day_plpc": day_plpc,
        "open_pl": total_unrealized_pl,
        "open_plpc": total_unrealized_pl / total_cost_basis if total_cost_basis else 0.0,
        "total_pl": total_unrealized_pl,
        "total_plpc": total_unrealized_pl / total_cost_basis if total_cost_basis else 0.0,
        "market_value": total_market_value,
        "position_count": len(position_rows),
        "positions": sorted(position_rows, key=lambda row: row["market_value"], reverse=True),
    }


def _model_get(value: Any, field: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(field, default)
    return getattr(value, field, default)


def _clean_model_value(value: Any) -> Any:
    return getattr(value, "value", value)


def portfolio_history_payload() -> dict[str, Any]:
    config = get_config()
    trading_client = create_trading_client(config)
    request = GetPortfolioHistoryRequest(period="1M", timeframe="1D")
    history = trading_client.get_portfolio_history(request)
    timestamps = _model_get(history, "timestamp", []) or []
    equity = _model_get(history, "equity", []) or []
    profit_loss = _model_get(history, "profit_loss", []) or []
    profit_loss_pct = _model_get(history, "profit_loss_pct", []) or []

    rows: list[dict[str, Any]] = []
    for index, raw_timestamp in enumerate(timestamps):
        try:
            timestamp = pd.to_datetime(raw_timestamp, unit="s", utc=True)
        except (TypeError, ValueError, OverflowError):
            timestamp = pd.to_datetime(raw_timestamp, utc=True, errors="coerce")
        if pd.isna(timestamp):
            continue
        rows.append(
            {
                "timestamp": timestamp.isoformat(),
                "equity": float(equity[index]) if index < len(equity) and equity[index] is not None else None,
                "profit_loss": float(profit_loss[index])
                if index < len(profit_loss) and profit_loss[index] is not None
                else None,
                "profit_loss_pct": float(profit_loss_pct[index])
                if index < len(profit_loss_pct) and profit_loss_pct[index] is not None
                else None,
            }
        )

    return {"rows": rows}


def open_orders_payload() -> dict[str, Any]:
    config = get_config()
    trading_client = create_trading_client(config)
    local_midnight = datetime.combine(datetime.now().astimezone().date(), time.min).astimezone(timezone.utc)
    request = GetOrdersRequest(
        status=QueryOrderStatus.OPEN,
        after=local_midnight,
        limit=100,
        direction=Sort.DESC,
        nested=True,
    )
    orders = trading_client.get_orders(filter=request)

    rows: list[dict[str, Any]] = []
    for order in orders:
        client_order_id = str(_model_get(order, "client_order_id", "") or "")
        lowered_id = client_order_id.lower()
        if "dca" in lowered_id:
            source = "DCA"
        elif "strategy" in lowered_id or "algo" in lowered_id:
            source = "Algorithm"
        else:
            source = "Account"
        rows.append(
            {
                "id": str(_model_get(order, "id", "")),
                "client_order_id": client_order_id,
                "symbol": str(_model_get(order, "symbol", "")),
                "side": str(_clean_model_value(_model_get(order, "side", ""))),
                "type": str(_clean_model_value(_model_get(order, "type", ""))),
                "status": str(_clean_model_value(_model_get(order, "status", ""))),
                "qty": _model_get(order, "qty", None),
                "notional": _model_get(order, "notional", None),
                "filled_qty": _model_get(order, "filled_qty", None),
                "limit_price": _model_get(order, "limit_price", None),
                "submitted_at": str(_model_get(order, "submitted_at", "")),
                "source": source,
            }
        )

    return {"rows": rows, "count": len(rows)}


def social_payload(limit: int = 250) -> dict[str, Any]:
    config = get_config()
    social_by_symbol = load_social_trends_csv(config.social_trends_csv, config.symbols)
    summary: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []

    for symbol, df in social_by_symbol.items():
        if df.empty:
            continue
        work_df = df.copy()
        work_df["timestamp"] = pd.to_datetime(work_df["timestamp"], utc=True)
        latest = work_df.sort_values("timestamp").iloc[-1]
        summary.append(
            {
                "symbol": symbol,
                "latest_timestamp": latest["timestamp"].isoformat(),
                "mentions": float(latest.get("mentions", 0.0)),
                "sentiment": float(latest.get("sentiment", 0.0)),
                "social_score": float(latest.get("social_score", 0.0)),
            }
        )
        for _, row in work_df.tail(limit).iterrows():
            rows.append(
                {
                    "timestamp": row["timestamp"].isoformat(),
                    "symbol": symbol,
                    "mentions": float(row.get("mentions", 0.0)),
                    "sentiment": float(row.get("sentiment", 0.0)),
                    "social_score": float(row.get("social_score", 0.0)),
                }
            )

    rows.sort(key=lambda item: (item["timestamp"], item["symbol"]), reverse=True)
    summary.sort(key=lambda item: item["symbol"])
    return {"summary": summary, "rows": rows[:limit]}


def logs_payload(lines: int = 200) -> dict[str, Any]:
    config = get_config()
    log_path = resolve_project_path(config.log_file)
    if not log_path.exists():
        return {"lines": []}

    content = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    return {"lines": [_redact(line) for line in content[-lines:]]}


def refresh_social_payload(body: dict[str, Any]) -> dict[str, Any]:
    config = get_config()
    symbols = body.get("symbols") or config.symbols
    if isinstance(symbols, str):
        symbols = [symbol.strip().upper() for symbol in symbols.split(",") if symbol.strip()]

    limit = int(body.get("limit") or config.alpha_vantage_news_limit)
    max_symbols = int(body.get("max_symbols") or min(config.alpha_vantage_max_symbols, len(symbols)))
    lookback_days = int(body.get("lookback_days") or config.alpha_vantage_news_lookback_days)
    delay = float(body.get("delay") if body.get("delay") is not None else config.alpha_vantage_request_delay_seconds)
    output = str(body.get("output") or config.alpha_vantage_news_csv)

    df = collect_alpha_vantage_news(
        config.alpha_vantage_api_key,
        symbols,
        lookback_days=lookback_days,
        limit=limit,
        max_symbols=max_symbols,
        request_delay_seconds=delay,
    )
    csv_path = write_social_trends_csv(df, output)
    return {
        "rows": len(df),
        "symbols_requested": min(len(symbols), max_symbols),
        "output": str(csv_path.relative_to(PROJECT_ROOT)),
    }


def backtest_payload() -> dict[str, Any]:
    history_df = run_backtest()
    metrics = calculate_performance_metrics(history_df["equity"])
    tail = history_df.reset_index().tail(120).copy()
    for column in tail.columns:
        if pd.api.types.is_datetime64_any_dtype(tail[column]):
            tail[column] = tail[column].dt.strftime("%Y-%m-%d")
    return {
        "metrics": metrics,
        "starting_equity": float(history_df["equity"].iloc[0]),
        "ending_equity": float(history_df["equity"].iloc[-1]),
        "rows": json.loads(tail.to_json(orient="records")),
    }


class TradingBotHandler(BaseHTTPRequestHandler):
    server_version = "TradingBotWeb/1.0"

    def log_message(self, format: str, *args: Any) -> None:
        logger.info("%s - %s", self.address_string(), format % args)

    def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        encoded = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_static(self, path: Path) -> None:
        if not path.exists() or not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        encoded = path.read_bytes()
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        raw_body = self.rfile.read(length).decode("utf-8")
        return json.loads(raw_body) if raw_body else {}

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/":
                self._send_static(WEB_ROOT / "index.html")
            elif parsed.path.startswith("/static/"):
                static_path = (WEB_ROOT / parsed.path.removeprefix("/")).resolve()
                if WEB_ROOT.resolve() not in static_path.parents:
                    self.send_error(HTTPStatus.FORBIDDEN)
                else:
                    self._send_static(static_path)
            elif parsed.path == "/api/status":
                self._send_json(status_payload())
            elif parsed.path == "/api/universe":
                self._send_json(universe_payload())
            elif parsed.path == "/api/dca":
                self._send_json(dca_payload())
            elif parsed.path == "/api/controls":
                self._send_json(controls_payload())
            elif parsed.path == "/api/account":
                self._send_json(account_payload())
            elif parsed.path == "/api/portfolio-history":
                self._send_json(portfolio_history_payload())
            elif parsed.path == "/api/open-orders":
                self._send_json(open_orders_payload())
            elif parsed.path == "/api/social":
                limit = int(parse_qs(parsed.query).get("limit", ["250"])[0])
                self._send_json(social_payload(limit=limit))
            elif parsed.path == "/api/logs":
                lines = int(parse_qs(parsed.query).get("lines", ["200"])[0])
                self._send_json(logs_payload(lines=lines))
            else:
                self.send_error(HTTPStatus.NOT_FOUND)
        except Exception as exc:
            logger.exception("GET %s failed", parsed.path)
            self._send_json(_safe_error(exc), HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            body = self._read_json_body()
            if parsed.path == "/api/refresh-social":
                self._send_json(refresh_social_payload(body))
            elif parsed.path == "/api/backtest":
                self._send_json(backtest_payload())
            elif parsed.path == "/api/dca":
                self._send_json(save_dca_payload(body))
            elif parsed.path == "/api/controls":
                self._send_json(save_controls_payload(body))
            else:
                self.send_error(HTTPStatus.NOT_FOUND)
        except Exception as exc:
            logger.exception("POST %s failed", parsed.path)
            self._send_json(_safe_error(exc), HTTPStatus.INTERNAL_SERVER_ERROR)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the local trading bot dashboard.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s")
    args = _parse_args()
    server = ThreadingHTTPServer((args.host, args.port), TradingBotHandler)
    logger.info("Serving dashboard at http://%s:%s", args.host, args.port)
    server.serve_forever()


if __name__ == "__main__":
    main()
