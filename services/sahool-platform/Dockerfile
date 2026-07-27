FROM python:3.11-slim-bookworm
WORKDIR /app

# Immutable source/build identity. These values are embedded into the image layer and
# OCI config; runtime environment variables cannot alter /runtime-identity.
ARG SAHOOL_GIT_SHA
ARG SAHOOL_BUILD_ID
ARG SAHOOL_SOURCE_REPOSITORY=""
ARG SAHOOL_SOURCE_REF=""
LABEL org.opencontainers.image.revision=$SAHOOL_GIT_SHA \
      org.opencontainers.image.source=$SAHOOL_SOURCE_REPOSITORY \
      org.opencontainers.image.ref.name=$SAHOOL_SOURCE_REF \
      io.sahool.build-id=$SAHOOL_BUILD_ID \
      io.sahool.service=sahool-platform
RUN python -c "import json,re; sha='$SAHOOL_GIT_SHA'; bid='$SAHOOL_BUILD_ID'; assert re.fullmatch(r'[0-9a-f]{40}',sha), 'SAHOOL_GIT_SHA must be full 40-char SHA'; assert re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,127}',bid), 'invalid SAHOOL_BUILD_ID'; open('/app/.sahool-build-metadata.json','w').write(json.dumps({'service':'sahool-platform','git_sha':sha,'build_id':bid,'source_repository':'$SAHOOL_SOURCE_REPOSITORY','source_ref':'$SAHOOL_SOURCE_REF'},sort_keys=True))"
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
