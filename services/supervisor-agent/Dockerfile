FROM python:3.11-slim-bookworm
WORKDIR /app
ARG SAHOOL_GIT_SHA
ARG SAHOOL_BUILD_ID
ARG SAHOOL_SOURCE_REPOSITORY=
ARG SAHOOL_SOURCE_REF=
RUN python -c "import json,re; sha='${SAHOOL_GIT_SHA}'; bid='${SAHOOL_BUILD_ID}'; assert re.fullmatch(r'[0-9a-f]{40}',sha), 'SAHOOL_GIT_SHA must be full 40-char SHA'; assert re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,127}',bid), 'invalid SAHOOL_BUILD_ID'; open('/app/.sahool-build-metadata.json','w').write(json.dumps({'service':'supervisor-agent','git_sha':sha,'build_id':bid,'source_repository':'${SAHOOL_SOURCE_REPOSITORY}','source_ref':'${SAHOOL_SOURCE_REF}'},sort_keys=True))"
RUN chmod 0444 /app/.sahool-build-metadata.json
LABEL org.opencontainers.image.revision="${SAHOOL_GIT_SHA}" \
      org.opencontainers.image.source="${SAHOOL_SOURCE_REPOSITORY}" \
      org.opencontainers.image.ref.name="${SAHOOL_SOURCE_REF}" \
      io.sahool.build-id="${SAHOOL_BUILD_ID}"
RUN apt-get update && apt-get install -y --no-install-recommends gcc curl \
    && rm -rf /var/lib/apt/lists/*
COPY services/supervisor-agent/requirements.txt /tmp/req.txt
# ── PyPI الرسمي افتراضياً؛ يمكن استخدام Alibaba mirror عبر build arg ──
# Alibaba override: --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_TRUSTED_HOST=
ENV PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST}
RUN pip install --no-cache-dir --timeout 300 --retries 10 -r /tmp/req.txt
COPY shared/ /app/shared/
COPY services/supervisor-agent/ /app/
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -sf http://localhost:8000/healthz || exit 1
RUN useradd -m sahool && chown -R sahool:sahool /app 2>/dev/null || true
USER sahool
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
