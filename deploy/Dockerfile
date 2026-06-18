FROM python:3.12-slim AS base

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    sqlite3 curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

FROM base AS deps
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e . && \
    pip install --no-cache-dir --upgrade pip

FROM base AS runtime
COPY --from=deps /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin

COPY src/ ./src/
COPY config/ ./config/
RUN mkdir -p /app/data && \
    useradd -m -u 1000 godfather && \
    chown -R godfather:godfather /app/data

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONPATH=/app

USER godfather

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import os,sys; sys.exit(0 if os.path.exists('/app/src/main.py') else 1)" || exit 1

ENTRYPOINT ["python", "-m", "src.main"]
