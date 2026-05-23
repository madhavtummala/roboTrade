FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    TRADING_CONFIG_FILE=/config/trading_bot.yaml \
    TRADING_ACCOUNTS_FILE=/config/accounts.yaml \
    TRADING_CONNECTORS_FILE=/config/connectors.yaml \
    TRADING_ALGORITHM_BOT_FILE=/config/algorithm_bot.yaml \
    TRADING_OPTIONS_BOT_FILE=/config/options_bot.yaml \
    TRADING_DCA_BOT_FILE=/config/dca_bot.yaml \
    TRADING_UNIVERSE_FILE=/config/universe.yaml \
    STATE_DB_PATH=/data/trading_bot.sqlite \
    TRADABLES_CSV=/app/data/tradable_etfs.csv \
    ALPHA_VANTAGE_NEWS_CSV=/data/social_trends.csv \
    LOG_FILE=/logs/trading.log

WORKDIR /app

ARG APP_UID=1000
ARG APP_GID=1000

RUN addgroup --gid ${APP_GID} app && adduser --uid ${APP_UID} --gid ${APP_GID} --disabled-password --gecos "" app \
    && mkdir -p /config /data /logs \
    && chown -R app:app /config /data /logs /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY web ./web
COPY data/tradable_etfs.csv ./data/tradable_etfs.csv
COPY --chown=app:app deploy/examples/trading_bot.yaml /config/trading_bot.yaml
COPY --chown=app:app deploy/examples/accounts.yaml /config/accounts.yaml
COPY --chown=app:app deploy/examples/connectors.yaml /config/connectors.yaml
COPY --chown=app:app deploy/examples/algorithm_bot.yaml /config/algorithm_bot.yaml
COPY --chown=app:app deploy/examples/options_bot.yaml /config/options_bot.yaml
COPY --chown=app:app deploy/examples/dca_bot.yaml /config/dca_bot.yaml
COPY --chown=app:app deploy/examples/universe.yaml /config/universe.yaml

USER app
EXPOSE 8000
VOLUME ["/config", "/data", "/logs"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT', '8000') + '/api/status', timeout=3).read()" || exit 1

CMD ["sh", "-c", "uvicorn src.api_app:app --host 0.0.0.0 --port ${PORT:-8000}"]
