FROM python:3.12-slim-bookworm

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY services/mcp_servers/requirements.txt .
# ── PyPI الرسمي (افتراضي، يعمل عالميّاً) — للمرآة الصينيّة مرّر --build-arg ──
# البديل: https://mirrors.aliyun.com/pypi/simple/ (علي بابا)
ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_TRUSTED_HOST=
ENV PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST}
RUN pip install --no-cache-dir --timeout 300 --retries 10 -r requirements.txt

# Merge BOTH shared packages into a single importable `shared.*` package:
#   - project-root shared/      → helpers.py, logging_config.py, __init__.py
#   - services/mcp_servers/shared/ → oauth_middleware.py, streamable_http.py
# The servers import `from shared.helpers ...` AND
# `from shared.oauth_middleware ...` / `from shared.streamable_http ...`,
# so all four modules must live under one /app/shared/ package.
COPY shared/ /app/shared/
COPY services/mcp_servers/shared/ /app/shared/
COPY services/mcp_servers/sentinel_hub_server.py /app/
COPY services/mcp_servers/weather_server.py /app/
COPY services/mcp_servers/wofost_server.py /app/
COPY services/mcp_servers/market_server.py /app/
COPY services/mcp_servers/generic_context_server.py /app/

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD curl -sf http://localhost:8000/healthz || exit 1
RUN useradd -m sahool && chown -R sahool:sahool /app 2>/dev/null || true
USER sahool
CMD ["sh", "-c", "python -m uvicorn ${MCP_SERVER_MODULE:-sentinel_hub_server}:app --host 0.0.0.0 --port 8000"]
