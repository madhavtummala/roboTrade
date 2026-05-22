# Social + Momentum Trading Bot

A Docker-ready FastAPI dashboard and trading bot for Alpaca. It supports DCA planning, strategy signal inspection, cached 6-month backtests, and a trading runner built around a configurable tradable universe.

This is research infrastructure, not a profit guarantee. Point `ALPACA_BASE_URL` at the account endpoint you intend to use, review generated orders, and use `KILL_SWITCH=true` whenever you want the app to be read-only.

## What Runs In The Container

The default container command starts the web app:

```text
uvicorn src.api_app:app --host 0.0.0.0 --port 8000
```

The image intentionally does not include your secrets, SQLite state, logs, or generated social data. Provide those at runtime:

- `/config` - mounted writable YAML config, normally `trading_bot.yaml`
- `/data` - mounted writable app state, SQLite DB, cached backtests, and optional social trend CSV
- `/logs` - mounted writable logs
- environment variables or `.env` - Alpaca keys and runtime paths

## Runtime Files

Create this layout on the machine that will run the app:

```text
runtime/
  config/
    trading_bot.yaml
  data/
  logs/
.env
```

Starter examples are in `deploy/examples/`:

```bash
mkdir -p runtime/config runtime/data runtime/logs
cp deploy/examples/env.example .env
cp deploy/examples/trading_bot.yaml runtime/config/trading_bot.yaml
```

Edit `.env` and replace the Alpaca values:

```bash
ALPACA_API_KEY=your_key_here
ALPACA_API_SECRET=your_secret_here
ALPACA_BASE_URL=https://paper-api.alpaca.markets
ALPACA_DATA_FEED=iex
KILL_SWITCH=false
```

The provided Docker setup uses these container paths:

```bash
STATE_DB_PATH=/data/trading_bot.sqlite
TRADING_CONFIG_FILE=/config/trading_bot.yaml
ALPHA_VANTAGE_NEWS_CSV=/data/social_trends.csv
LOG_FILE=/logs/trading.log
```

Do not commit `.env`, `runtime/`, `config/`, `data/*.sqlite`, logs, or generated social/backtest files. They are ignored by `.gitignore`.

The master tradables file is bundled inside the image at `/app/tradable_etfs.csv`. The smaller deployment universe lives directly in `trading_bot.yaml` under `tradable_universe.symbols`, and dashboard universe refreshes write back to that YAML file. Social trends are app-managed/generated data in `/data/social_trends.csv`; users are not expected to provide them as ground truth.

## Run Locally With Docker Compose

Build and start:

```bash
docker compose up --build -d
```

Open:

```text
http://127.0.0.1:8000
```

View logs:

```bash
docker compose logs -f trading-bot
```

Stop:

```bash
docker compose down
```

## Build The Image Manually

```bash
docker build -t trading-bot:local .
```

Run it:

```bash
docker run --rm -p 8000:8000 \
  --env-file .env \
  -v "$PWD/runtime/config:/config" \
  -v "$PWD/runtime/data:/data" \
  -v "$PWD/runtime/logs:/logs" \
  trading-bot:local
```

## Publish To GitHub Container Registry

This repo includes `.github/workflows/docker-publish.yml`. When pushed to `main`, GitHub Actions builds and pushes:

```text
ghcr.io/<owner>/<repo>:latest
ghcr.io/<owner>/<repo>:main
ghcr.io/<owner>/<repo>:sha-<commit>
```

Tagged releases like `v1.0.0` also publish a matching tag.

Before relying on GHCR:

1. Push the repository to GitHub.
2. Make sure GitHub Actions is enabled.
3. Push to `main`.
4. In GitHub, open `Packages` and confirm the image exists.
5. If your repo/package is private, log in on the deployment host:

```bash
echo "$GHCR_TOKEN" | docker login ghcr.io -u <github-user> --password-stdin
```

The token needs permission to read packages.

## Deploy From GHCR On A Server

On your server:

```bash
mkdir -p trading-bot/runtime/config trading-bot/runtime/data trading-bot/runtime/logs
cd trading-bot
```

Create `.env` using `deploy/examples/env.example` as a template, or paste the same values manually. Then edit the YAML config:

```bash
nano .env
nano runtime/config/trading_bot.yaml
```

Run the published image:

```bash
docker run -d --name trading-bot \
  --restart unless-stopped \
  -p 8000:8000 \
  --env-file .env \
  -v "$PWD/runtime/config:/config" \
  -v "$PWD/runtime/data:/data" \
  -v "$PWD/runtime/logs:/logs" \
  ghcr.io/<owner>/<repo>:latest
```

Upgrade later:

```bash
docker pull ghcr.io/<owner>/<repo>:latest
docker stop trading-bot
docker rm trading-bot
docker run -d --name trading-bot \
  --restart unless-stopped \
  -p 8000:8000 \
  --env-file .env \
  -v "$PWD/runtime/config:/config" \
  -v "$PWD/runtime/data:/data" \
  -v "$PWD/runtime/logs:/logs" \
  ghcr.io/<owner>/<repo>:latest
```

Your app state survives upgrades because it lives in `runtime/data`, not inside the image.

## Run One-Shot Jobs From The Same Image

Run a backtest:

```bash
docker run --rm \
  --env-file .env \
  -v "$PWD/runtime/config:/config" \
  -v "$PWD/runtime/data:/data" \
  -v "$PWD/runtime/logs:/logs" \
  ghcr.io/<owner>/<repo>:latest \
  python -m src.backtest
```

Run the trading worker once, for manual testing or legacy scheduled operation:

```bash
docker run --rm \
  --env-file .env \
  -v "$PWD/runtime/config:/config" \
  -v "$PWD/runtime/data:/data" \
  -v "$PWD/runtime/logs:/logs" \
  ghcr.io/<owner>/<repo>:latest \
  python -m src.live_runner
```

For normal use, leave the dashboard running and use the DCA or Algorithm tab power buttons to control the backend bot loops. Keep `KILL_SWITCH=true` until you are ready for order submission.

## Configuration Reference

Required for Alpaca:

```bash
ALPACA_API_KEY=
ALPACA_API_SECRET=
ALPACA_BASE_URL=https://paper-api.alpaca.markets
ALPACA_DATA_FEED=iex
KILL_SWITCH=false
```

`ALPACA_BASE_URL` controls where trading calls are sent; the example points at Alpaca's paper endpoint. Change it only when you intentionally want a different brokerage endpoint. `KILL_SWITCH=true` keeps the app able to show data/backtests/signals while preventing the trading runner from submitting orders. `ALPACA_DATA_FEED=iex` requests Alpaca's IEX market data feed; change it only if your Alpaca plan and account are configured for another feed.

YAML config:

```bash
TRADING_CONFIG_FILE=/config/trading_bot.yaml
```

`trading_bot.yaml` contains account placeholders, `tradable_universe.symbols`, and nested knobs for each server-side algorithm. `TRADABLES_CSV` defaults to the internal `/app/tradable_etfs.csv` in Docker. Override it only if you intentionally want a custom master tradables file.

Risk controls:

```bash
MAX_WEIGHT_PER_SYMBOL=0.25
MAX_PORTFOLIO_EXPOSURE=0.95
MAX_LONGS=5
TARGET_ANNUAL_VOL=0.18
CASH_BUFFER=0.02
REBALANCE_THRESHOLD=0.02
MIN_TRADE_DOLLARS=50
BACKTEST_STARTING_EQUITY=10000
ALGORITHM_EQUITY_CAP=0
```

`BACKTEST_STARTING_EQUITY` is the simulated cash account size used by backtests. `ALGORITHM_EQUITY_CAP` is optional for live/paper order sizing; leave it at `0` to use the full account equity, or set it to a dollar amount such as `10000` to cap algorithm sizing to that amount.

Optional Alpha Vantage support for app-managed social data:

```bash
ALPHA_VANTAGE_API_KEY=
ALPHA_VANTAGE_NEWS_CSV=/data/social_trends.csv
ALPHA_VANTAGE_NEWS_LOOKBACK_DAYS=30
ALPHA_VANTAGE_NEWS_LIMIT=50
ALPHA_VANTAGE_MAX_SYMBOLS=20
```

Persistence:

```bash
STATE_DB_PATH=/data/trading_bot.sqlite
LOG_FILE=/logs/trading.log
```

## Non-Docker Development

Install dependencies:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

Create `.env` in the project root. For local non-Docker development, paths may stay relative:

```bash
TRADING_CONFIG_FILE=config/trading_bot.yaml
STATE_DB_PATH=data/trading_bot.sqlite
LOG_FILE=logs/trading.log
```

Run the dashboard:

```bash
uvicorn src.api_app:app --host 0.0.0.0 --port 8000
```

Run tests:

```bash
pytest
```

## Project Layout

- `src/api_app.py` - FastAPI API and static web app server
- `src/api_payloads.py` - API payload builders, cached backtests, signals, and config updates
- `src/config.py` - YAML-first runtime config
- `src/state_store.py` - SQLite state persistence
- `src/dca.py` - DCA plan validation and allocation preview
- `src/signals.py` - momentum/social signal engine
- `src/portfolio.py` - target weight calculation
- `src/live_runner.py` - one-shot trading worker
- `web/` - dashboard HTML, CSS, and JavaScript
- `deploy/examples/` - safe example runtime files
- `Dockerfile` - production image
- `docker-compose.yml` - local container run helper
- `.github/workflows/docker-publish.yml` - GHCR publisher

## Safety Notes

- `ALPACA_BASE_URL=https://paper-api.alpaca.markets` is the default and recommended starting point.
- `KILL_SWITCH=true` prevents order submission.
- Treat generated signals and backtests as decision support, not instructions.
- Backtests are approximate and do not guarantee live execution quality.
