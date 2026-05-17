# Social + Momentum Trading Bot with Alpaca-Python

A daily long-only bot that uses Alpaca's official Python SDK (`alpaca-py`) to trade liquid US ETFs/stocks in the PAPER trading environment. It combines price momentum, long-term trend, volume confirmation, optional social trend data, volatility-aware sizing, and basic execution controls.

This is not a profit guarantee. Treat it as research infrastructure: paper trade first, review backtests, and keep real-money sizing small until live behavior matches expectations.

## Features

- Composite daily signal using:
  - N-day and short-term momentum
  - 200-day trend filter
  - volume spike confirmation
  - optional social mentions/sentiment/trend score
- Score and volatility-aware long allocation
- Caps on position weight, number of holdings, and total exposure
- Cash buffer, rebalance threshold, and minimum trade size
- Backtest that rebalances on the next open using prior-close signals
- Paper trading by default
- Vendor-neutral social trend CSV support
- Tradable universe constrained to a curated subset of `tradable_etfs.csv`

## Setup

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Create a `.env` file in the project root with your Alpaca paper account credentials:

```bash
ALPACA_API_KEY=your_key_here
ALPACA_API_SECRET=your_secret_here
ALPACA_DATA_FEED=iex
PAPER_TRADING=true
KILL_SWITCH=false
```

3. Optionally, configure the universe and risk settings:

```bash
SYMBOLS=SPY,QQQ,IWM,XBI,XSD,GLD,TLT
MAX_WEIGHT_PER_SYMBOL=0.25
MAX_PORTFOLIO_EXPOSURE=0.95
MAX_LONGS=5
TARGET_ANNUAL_VOL=0.18
CASH_BUFFER=0.02
REBALANCE_THRESHOLD=0.02
MIN_TRADE_DOLLARS=50
```

By default, the bot uses `tradable_universe.csv` and validates it against `tradable_etfs.csv`.

```bash
TRADABLES_CSV=tradable_etfs.csv
UNIVERSE_CSV=tradable_universe.csv
```

Use `SYMBOLS=SPY,QQQ,IWM` only when you want a direct override for a one-off run.

4. Optionally, add social trend data:

```bash
SOCIAL_TRENDS_CSV=data/social_trends.csv
ALPHA_VANTAGE_API_KEY=your_alpha_vantage_key_here
ALPHA_VANTAGE_NEWS_CSV=data/social_trends.csv
ALPHA_VANTAGE_NEWS_LOOKBACK_DAYS=30
ALPHA_VANTAGE_NEWS_LIMIT=50
ALPHA_VANTAGE_MAX_SYMBOLS=20
```

The CSV should include `symbol` or `ticker`, `timestamp` or `date`, and at least one of:

- `mentions`, `mention_count`, `post_count`, `volume`, or `social_volume`
- `sentiment`, `sentiment_score`, or `bullish_sentiment`
- `social_score` or `trend_score`

To build `data/social_trends.csv` from Alpha Vantage news sentiment:

```bash
python -m src.alpha_vantage
```

For a small quota-friendly test pull:

```bash
python -m src.alpha_vantage --symbols SPY,QQQ --max-symbols 2 --limit 5
```

## Run the backtest

```bash
python -m src.backtest
```

This will fetch historical daily bars for the configured symbols, compute daily momentum signals, simulate rebalancing, and print final performance statistics.

## Run the dashboard

```bash
python -m src.web_app
```

Then open:

```text
http://127.0.0.1:8000
```

The dashboard is a single-page DCA control surface built around two reactive bubbles: buy and sell. Double-click empty space inside a bubble to add a symbol, drag symbols anywhere inside a bubble, drag them across bubbles to move between buy and sell, and use the mouse wheel over a symbol to resize its scheduled amount from `$0` to `$100`. Invalid symbols turn red and fade away. The stats panel shows DCA/algorithm/options controls, equity, cash, day P/L, total P/L, portfolio growth, today's open orders, and current positions. The setup saves to `data/dca_plan.json`, but it does not submit DCA orders yet.

## Run the live paper trading runner

```bash
python -m src.live_runner
```

The live runner will:

- load config and Alpaca clients
- fetch recent daily bars
- load optional social trend data
- compute composite momentum/social signals
- compute risk-aware target weights
- submit market orders to align positions with targets

> Keep `PAPER_TRADING=true` while developing. Use `KILL_SWITCH=true` to prevent live order submission.

## Run tests

```bash
pytest
```

## Project layout

- `src/config.py` — configuration, environment loading, Alpaca mode selection
- `src/universe.py` — CSV universe loading and tradables validation
- `src/alpaca_client.py` — Alpaca trading and market data wrapper
- `src/data.py` — daily bar fetcher
- `src/social.py` — optional social trend CSV loader
- `src/alpha_vantage.py` — Alpha Vantage news sentiment ingester
- `src/dca.py` — DCA plan validation and allocation preview
- `src/web_app.py` — local web dashboard
- `src/signals.py` — composite momentum/social signal engine
- `src/portfolio.py` — score/risk target weight calculator
- `src/orders.py` — order sync logic
- `src/backtest.py` — backtest runner
- `src/live_runner.py` — live paper trading entry point
- `src/logging_utils.py` — logging helpers
- `web/` — dashboard HTML, CSS, and JavaScript

## Notes

- This bot uses the Alpaca PAPER environment by default.
- Use cron or a scheduler to run `python -m src.live_runner` once per day after market close.
- Backtest results are approximate and use integer share rounding.
