FROM python:3.11-slim-bookworm
WORKDIR /app

# Immutable source/build identity. These values are embedded into the image layer and
# OCI config; runtime environment variables cannot alter /runtime-identity.
ARG SAHOOL_GIT_SHA
ARG SAHOOL_BUILD_ID
ARG SAHOOL_SOURCE_REPOSITORY=""
ARG SAHOOL_SOURCE_REF=""
# Railway sets RAILWAY_GIT_COMMIT_SHA on GitHub-triggered builds (empty on config-triggered
# ones): a hand-set SAHOOL_GIT_SHA that contradicts it fails the build instead of stamping
# a stale identity. When SAHOOL_GIT_SHA is unset the stamp derives from RAILWAY_GIT_COMMIT_SHA:
# pinning the variable broke every autodeploy after each merge (measured 2026-09-21).
ARG RAILWAY_GIT_COMMIT_SHA=""
ARG RAILWAY_DEPLOYMENT_ID=""
LABEL org.opencontainers.image.revision=$SAHOOL_GIT_SHA \
      org.opencontainers.image.source=$SAHOOL_SOURCE_REPOSITORY \
      org.opencontainers.image.ref.name=$SAHOOL_SOURCE_REF \
      io.sahool.build-id=$SAHOOL_BUILD_ID \
      io.sahool.service=soil-service
RUN python -c "import json,re; trig='$RAILWAY_GIT_COMMIT_SHA'; sha='$SAHOOL_GIT_SHA' or trig; bid='$SAHOOL_BUILD_ID' or ('railway-'+'$RAILWAY_DEPLOYMENT_ID' if '$RAILWAY_DEPLOYMENT_ID' else ''); assert re.fullmatch(r'[0-9a-f]{40}',sha), 'SAHOOL_GIT_SHA must be full 40-char SHA (set it, or build from a GitHub trigger so RAILWAY_GIT_COMMIT_SHA supplies it)'; assert re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,127}',bid), 'invalid SAHOOL_BUILD_ID'; assert not trig or trig==sha, 'SAHOOL_GIT_SHA '+sha+' contradicts the commit the platform built '+trig+' - unset the pinned variable or set it to the built commit'; open('/app/.sahool-build-metadata.json','w').write(json.dumps({'service':'soil-service','git_sha':sha,'build_id':bid,'source_repository':'$SAHOOL_SOURCE_REPOSITORY','source_ref':'$SAHOOL_SOURCE_REF'},sort_keys=True))"
RUN chmod 0444 /app/.sahool-build-metadata.json
RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev curl && rm -rf /var/lib/apt/lists/*
COPY services/soil-service/requirements.txt /tmp/requirements.txt
# ── PyPI الرسمي افتراضياً؛ يمكن استخدام Alibaba mirror عبر build arg ──
# Alibaba override: --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_TRUSTED_HOST=
ENV PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST}
RUN pip install --no-cache-dir --timeout 300 --retries 10 -r /tmp/requirements.txt
COPY shared/ /app/shared/
COPY services/soil-service/ /app/
RUN useradd -m sahool && chown -R sahool:sahool /app
USER sahool
EXPOSE 8000
HEALTHCHECK --interval=20s --timeout=5s --retries=3 CMD curl -sf http://localhost:8000/healthz || exit 1
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
