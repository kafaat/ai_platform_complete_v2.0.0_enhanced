ARG PYTHON_BASE_IMAGE=python:3.12-slim-bookworm
FROM ${PYTHON_BASE_IMAGE}

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

EXPOSE 8088

# No application tree is copied: TiTiler reads remote/local COGs at runtime.
# A locked, non-login user prevents accidental root execution.
RUN useradd --create-home --shell /usr/sbin/nologin sahool
USER sahool

CMD ["sh", "-c", "exec uvicorn titiler.application.main:app --host 0.0.0.0 --port ${PORT:-8088}"]
