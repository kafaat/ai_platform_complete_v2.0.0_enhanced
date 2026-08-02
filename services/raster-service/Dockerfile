FROM python:3.11-slim-bookworm
WORKDIR /app
# rasterio يحتاج GDAL (نظام)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gdal-bin libgdal-dev && rm -rf /var/lib/apt/lists/*
COPY services/raster-service/requirements.txt /tmp/requirements.txt
# ── PyPI الرسمي افتراضياً؛ يمكن استخدام Alibaba mirror عبر build arg ──
# Alibaba override: --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_TRUSTED_HOST=
ENV PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST}
RUN pip install --no-cache-dir --timeout 300 --retries 10 -r /tmp/requirements.txt

# هويّة المصدر/البناء غير القابلة للتغيير. القيَم تُدفَن في طبقة الصورة وفي إعداد OCI،
# فمتغيّرات وقت التشغيل لا تستطيع تغيير ما يُعيده `/runtime-identity`.
#
# **الموضع متأخّر عمداً، بخلاف الخدمات الثلاث الأخرى.** ARG يتغيّر مع كلّ التزام،
# وكلّ ما بعده يفقد ذاكرة البناء المؤقّتة. في weather/soil/platform الكتلة في الأعلى
# ولا يكلّف ذلك شيئاً يُذكَر؛ هنا فوقها طبقتا GDAL وتثبيت الاعتماديّات — أثقل طبقتين
# في المستودع. ووضعها هنا لا يُضعِف شيئاً: ما يليها (`COPY services/raster-service/`)
# يتغيّر مع كلّ التزام أصلاً، فالإبطال يقع هناك حتماً. والحارس المعماريّ يفحص وجود
# السلاسل لا ترتيبها.
ARG SAHOOL_GIT_SHA
ARG SAHOOL_BUILD_ID
ARG SAHOOL_SOURCE_REPOSITORY=""
ARG SAHOOL_SOURCE_REF=""
LABEL org.opencontainers.image.revision=$SAHOOL_GIT_SHA \
      org.opencontainers.image.source=$SAHOOL_SOURCE_REPOSITORY \
      org.opencontainers.image.ref.name=$SAHOOL_SOURCE_REF \
      io.sahool.build-id=$SAHOOL_BUILD_ID \
      io.sahool.service=raster-service
RUN python -c "import json,re; sha='$SAHOOL_GIT_SHA'; bid='$SAHOOL_BUILD_ID'; assert re.fullmatch(r'[0-9a-f]{40}',sha), 'SAHOOL_GIT_SHA must be full 40-char SHA'; assert re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,127}',bid), 'invalid SAHOOL_BUILD_ID'; open('/app/.sahool-build-metadata.json','w').write(json.dumps({'service':'raster-service','git_sha':sha,'build_id':bid,'source_repository':'$SAHOOL_SOURCE_REPOSITORY','source_ref':'$SAHOOL_SOURCE_REF'},sort_keys=True))"
RUN chmod 0444 /app/.sahool-build-metadata.json

COPY shared/ /app/shared/
COPY services/raster-service/ /app/
# P1-3: مستخدم غير جذري (محاذاةً لباقي الخدمات الـ17)
RUN useradd -m -u 10001 appuser \
    && mkdir -p /data/rasters \
    && chown -R appuser:appuser /app /data/rasters
USER appuser
EXPOSE 8001
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import httpx; httpx.get('http://localhost:8001/healthz')"
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
