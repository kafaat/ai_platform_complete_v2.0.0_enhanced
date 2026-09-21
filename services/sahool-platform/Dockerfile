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
# RAILWAY_DEPLOYMENT_ID arrived empty at build time (measured 2026-09-21, fdb7fee6), so an
# unpinned SAHOOL_BUILD_ID falls back to railway-<built commit[:12]>; all-empty still fails.
ARG RAILWAY_GIT_COMMIT_SHA=""
ARG RAILWAY_DEPLOYMENT_ID=""
LABEL org.opencontainers.image.revision=$SAHOOL_GIT_SHA \
      org.opencontainers.image.source=$SAHOOL_SOURCE_REPOSITORY \
      org.opencontainers.image.ref.name=$SAHOOL_SOURCE_REF \
      io.sahool.build-id=$SAHOOL_BUILD_ID \
      io.sahool.service=sahool-platform
RUN python -c "import json,re; trig='$RAILWAY_GIT_COMMIT_SHA'; sha='$SAHOOL_GIT_SHA' or trig; bid='$SAHOOL_BUILD_ID' or ('railway-'+'$RAILWAY_DEPLOYMENT_ID' if '$RAILWAY_DEPLOYMENT_ID' else ('railway-'+trig[:12] if trig else '')); assert re.fullmatch(r'[0-9a-f]{40}',sha), 'SAHOOL_GIT_SHA must be full 40-char SHA (set it, or build from a GitHub trigger so RAILWAY_GIT_COMMIT_SHA supplies it)'; assert re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,127}',bid), 'invalid SAHOOL_BUILD_ID'; assert not trig or trig==sha, 'SAHOOL_GIT_SHA '+sha+' contradicts the commit the platform built '+trig+' - unset the pinned variable or set it to the built commit'; open('/app/.sahool-build-metadata.json','w').write(json.dumps({'service':'sahool-platform','git_sha':sha,'build_id':bid,'source_repository':'$SAHOOL_SOURCE_REPOSITORY','source_ref':'$SAHOOL_SOURCE_REF'},sort_keys=True))"
RUN chmod 0444 /app/.sahool-build-metadata.json

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc curl \
    && rm -rf /var/lib/apt/lists/*

# المتطلّبات
COPY services/sahool-platform/api/requirements.txt /tmp/requirements.txt
# ── PyPI الرسمي افتراضياً؛ يمكن استخدام Alibaba mirror عبر build arg ──
# Alibaba override: --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_TRUSTED_HOST=
ENV PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST}
RUN pip install --no-cache-dir --timeout 300 --retries 10 -r /tmp/requirements.txt

# الكود: api/ + core/ + knowledge/ + data/ (main.py يستورد من core/)
COPY shared/ /app/shared/
COPY services/sahool-platform/ /app/

# المنطق في api/main.py → app
ENV PYTHONPATH=/app:/app/api
ENV PYTHONUNBUFFERED=1

RUN useradd -m sahool && chown -R sahool:sahool /app
USER sahool

EXPOSE 8000
HEALTHCHECK --interval=20s --timeout=5s --retries=3 \
    CMD curl -sf http://localhost:8000/healthz || exit 1

# main.py في api/ ويستورد api.* و core.* — نشغّل من /app
# N2: عامل واحد إلزاميّ ما دام _OFFLINE_QUEUE في الذاكرة — عاملان = طابوران
# منفصلان في عمليتين → تضارب بيانات (replay يخدم من طابور خاطئ). للتوسّع:
# انقل الطابور لـRedis ثمّ ارفع --workers (انظر تعليق _OFFLINE_QUEUE).
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
