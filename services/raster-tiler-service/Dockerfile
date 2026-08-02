ARG PYTHON_BASE_IMAGE=python:3.12-slim-bookworm
FROM ${PYTHON_BASE_IMAGE}
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8088

# libexpat1 is required by rasterio/GDAL in the slim image.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libexpat1 \
 && rm -rf /var/lib/apt/lists/*

# PyPI is the default. CI/deployments may inject an internal mirror without
# editing this Dockerfile. Build-only arguments are intentionally not persisted
# as runtime ENV values.
# Alibaba override: --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_EXTRA_INDEX_URL=
ARG PIP_TRUSTED_HOST=
RUN set -eu; \
    extra_args=""; \
    if [ -n "${PIP_EXTRA_INDEX_URL}" ]; then \
      extra_args="${extra_args} --extra-index-url ${PIP_EXTRA_INDEX_URL}"; \
    fi; \
    if [ -n "${PIP_TRUSTED_HOST}" ]; then \
      extra_args="${extra_args} --trusted-host ${PIP_TRUSTED_HOST}"; \
    fi; \
    pip install --timeout 300 --retries 10 \
      --index-url "${PIP_INDEX_URL}" \
      ${extra_args} \
      "titiler.application>=0.20,<0.23" \
      "uvicorn[standard]>=0.30,<0.34"

COPY shared/ /app/shared/
COPY services/raster-tiler-service/main.py /app/main.py

# Immutable source identity: generated at image build, never overridden at runtime.
ARG SAHOOL_GIT_SHA
ARG SAHOOL_BUILD_ID
ARG SAHOOL_SOURCE_REPOSITORY=
ARG SAHOOL_SOURCE_REF=
RUN SAHOOL_GIT_SHA="${SAHOOL_GIT_SHA}" SAHOOL_BUILD_ID="${SAHOOL_BUILD_ID}" SAHOOL_SOURCE_REPOSITORY="${SAHOOL_SOURCE_REPOSITORY}" SAHOOL_SOURCE_REF="${SAHOOL_SOURCE_REF}" python - <<'PYID'
import json, os, re
from pathlib import Path
sha = os.environ['SAHOOL_GIT_SHA']
build_id = os.environ['SAHOOL_BUILD_ID']
if not re.fullmatch(r"[0-9a-f]{40}", sha):
    raise SystemExit("SAHOOL_GIT_SHA must be 40 lowercase hex characters")
if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", build_id):
    raise SystemExit("SAHOOL_BUILD_ID has invalid format")
Path("/app/.sahool-build-metadata.json").write_text(json.dumps({
    "service": 'raster-tiler-service',
    "git_sha": sha,
    "build_id": build_id,
    "source_repository": os.environ.get("SAHOOL_SOURCE_REPOSITORY", ""),
    "source_ref": os.environ.get("SAHOOL_SOURCE_REF", ""),
}, sort_keys=True) + "\n", encoding="utf-8")
PYID
RUN chmod 0444 /app/.sahool-build-metadata.json
LABEL org.opencontainers.image.revision="${SAHOOL_GIT_SHA}" \
      org.opencontainers.image.source="${SAHOOL_SOURCE_REPOSITORY}" \
      org.opencontainers.image.ref.name="${SAHOOL_SOURCE_REF}" \
      io.sahool.build-id="${SAHOOL_BUILD_ID}"

EXPOSE 8088

# No application tree is copied: TiTiler reads remote/local COGs at runtime.
# A locked, non-login user prevents accidental root execution.
RUN useradd --create-home --shell /usr/sbin/nologin sahool
USER sahool

CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8088}"]
