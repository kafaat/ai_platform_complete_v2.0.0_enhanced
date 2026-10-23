FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SAHOOL_REALTIME_ENABLED=0 \
    REALTIME_SQLITE_PATH=/data/realtime.sqlite3

WORKDIR /app
COPY services/realtime-session/requirements.txt /tmp/requirements.txt
# Official PyPI by default; select a mirror explicitly at build time.
# Alibaba override: --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_TRUSTED_HOST=
ENV PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST}
RUN python -m pip install --no-cache-dir --timeout 300 --retries 10 -r /tmp/requirements.txt \
    && groupadd --gid 10001 realtime \
    && useradd --uid 10001 --gid realtime --no-create-home realtime \
    && mkdir /data \
    && chown realtime:realtime /data \
    && chmod 0700 /data

COPY services/realtime-session/realtime_session/ /app/realtime_session/
COPY services/realtime-session/main.py /app/main.py
USER 10001:10001
EXPOSE 8000

# Process health only; readiness separately enforces feature/config/dependency gates.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3).close()"

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]
