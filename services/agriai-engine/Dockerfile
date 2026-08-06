FROM python:3.12-slim-bookworm
WORKDIR /app
ARG SAHOOL_GIT_SHA
ARG SAHOOL_BUILD_ID
ARG SAHOOL_SOURCE_REPOSITORY=""
ARG SAHOOL_SOURCE_REF=""
LABEL org.opencontainers.image.revision=$SAHOOL_GIT_SHA \
      org.opencontainers.image.version=$SAHOOL_BUILD_ID
RUN python - <<'PY'
import json
import os
import re

sha = os.environ.get("SAHOOL_GIT_SHA", "")
bid = os.environ.get("SAHOOL_BUILD_ID", "")
if not re.fullmatch(r"[0-9a-f]{40}", sha):
    raise SystemExit("SAHOOL_GIT_SHA must be full 40-char SHA")
if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", bid):
    raise SystemExit("invalid SAHOOL_BUILD_ID")

payload = {
    "service": "agriai-engine",
    "git_sha": sha,
    "build_id": bid,
    "source_repository": os.environ.get("SAHOOL_SOURCE_REPOSITORY", ""),
    "source_ref": os.environ.get("SAHOOL_SOURCE_REF", ""),
}
with open("/app/.sahool-build-metadata.json", "w", encoding="utf-8") as f:
    json.dump(payload, f, sort_keys=True)
PY
RUN chmod 0444 /app/.sahool-build-metadata.json
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*
COPY services/agriai-engine/requirements.txt /tmp/
# ── PyPI الرسمي افتراضياً؛ يمكن استخدام Alibaba mirror عبر build arg ──
# Alibaba override: --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_TRUSTED_HOST=
ENV PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST}
RUN pip install --no-cache-dir --timeout 300 --retries 10 -r /tmp/requirements.txt
COPY shared/ /app/shared/
COPY services/agriai-engine/ /app/
RUN useradd -m sahool && chown -R sahool:sahool /app
USER sahool
ENV PYTHONUNBUFFERED=1 PYTHONPATH=/app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -sf http://localhost:8000/healthz || exit 1
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
