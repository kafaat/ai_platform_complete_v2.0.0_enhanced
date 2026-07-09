FROM python:3.12-slim-bookworm

# Build-time PyPI mirror control. These two services previously relied on the
# Docker image/pip defaults while the rest of the monorepo made the index
# explicit. With compose --no-cache this could resolve against an incomplete
# mirror and fail with: "No matching distribution found for fastapi==0.136.3".
# Alibaba override: --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_EXTRA_INDEX_URL=
ENV PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_EXTRA_INDEX_URL=${PIP_EXTRA_INDEX_URL} \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY services/knowledge-graph/requirements.txt .
RUN python -m pip install --timeout 300 --retries 10 --no-cache-dir --upgrade pip setuptools wheel \
    && python -m pip install --timeout 300 --retries 10 --no-cache-dir -r requirements.txt
COPY services/sahool-platform/core /app/core
# SEC-3: shared gateway-trusted identity helpers (shared.security.gateway_deps).
# Must be copied or the container crashes at import (ModuleNotFoundError: shared).
COPY shared /app/shared
COPY services/knowledge-graph/main.py /app/main.py
ENV PYTHONPATH=/app KG_SQLITE_PATH=/data/kg.sqlite
# مستخدم غير جذري (SEC-2). /data قابل للكتابة (KG_SQLITE_PATH) — يُنشأ ويُملَّك قبل
# VOLUME كي تُحفظ الملكيّة في نقطة التركيب (تغييرات ما بعد VOLUME تُهمَل عند البناء).
RUN useradd -m sahool && mkdir -p /data && chown -R sahool:sahool /app /data
USER sahool
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz', timeout=3)"
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
