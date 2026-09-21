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
COPY services/raster-tiler-service/requirements.txt /app/requirements.txt
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
      -r /app/requirements.txt

COPY shared/ /app/shared/
COPY services/raster-tiler-service/main.py /app/main.py

# Immutable source identity: generated at image build, never overridden at runtime.
ARG SAHOOL_GIT_SHA
ARG SAHOOL_BUILD_ID
ARG SAHOOL_SOURCE_REPOSITORY=
ARG SAHOOL_SOURCE_REF=
# Railway sets RAILWAY_GIT_COMMIT_SHA on GitHub-triggered builds (empty on config-triggered
# ones): a hand-set SAHOOL_GIT_SHA that contradicts it fails the build instead of stamping
# a stale identity. When SAHOOL_GIT_SHA is unset the stamp derives from RAILWAY_GIT_COMMIT_SHA:
# pinning the variable broke every autodeploy after each merge (measured 2026-09-21).
# RAILWAY_DEPLOYMENT_ID arrived empty at build time (measured 2026-09-21, fdb7fee6), so an
# unpinned SAHOOL_BUILD_ID falls back to railway-<built commit[:12]>; all-empty still fails.
ARG RAILWAY_GIT_COMMIT_SHA=
ARG RAILWAY_DEPLOYMENT_ID=
RUN SAHOOL_GIT_SHA="${SAHOOL_GIT_SHA}" SAHOOL_BUILD_ID="${SAHOOL_BUILD_ID}" SAHOOL_SOURCE_REPOSITORY="${SAHOOL_SOURCE_REPOSITORY}" SAHOOL_SOURCE_REF="${SAHOOL_SOURCE_REF}" RAILWAY_GIT_COMMIT_SHA="${RAILWAY_GIT_COMMIT_SHA}" RAILWAY_DEPLOYMENT_ID="${RAILWAY_DEPLOYMENT_ID}" python - <<'PYID'
import json, os, re
from pathlib import Path
trig = os.environ.get("RAILWAY_GIT_COMMIT_SHA", "")
sha = os.environ.get("SAHOOL_GIT_SHA") or trig
deployment = os.environ.get("RAILWAY_DEPLOYMENT_ID", "")
build_id = os.environ.get("SAHOOL_BUILD_ID") or (
    f"railway-{deployment}" if deployment else (f"railway-{trig[:12]}" if trig else "")
)
if not re.fullmatch(r"[0-9a-f]{40}", sha):
    raise SystemExit("SAHOOL_GIT_SHA must be 40 lowercase hex characters (set it, or build from a GitHub trigger so RAILWAY_GIT_COMMIT_SHA supplies it)")
if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", build_id):
    raise SystemExit("SAHOOL_BUILD_ID has invalid format")
if trig and trig != sha:
    raise SystemExit(f"SAHOOL_GIT_SHA {sha} contradicts the commit the platform built {trig} - unset the pinned variable or set it to the built commit")
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
