FROM python:3.12-slim
WORKDIR /app
# rasterio يحتاج GDAL (نظام)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gdal-bin libgdal-dev && rm -rf /var/lib/apt/lists/*
COPY services/raster-service/requirements.txt /tmp/requirements.txt
# ── PyPI الرسمي (افتراضي، يعمل عالميّاً) — للمرآة الصينيّة مرّر --build-arg ──
# البديل: https://mirrors.aliyun.com/pypi/simple/ (علي بابا)
ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_TRUSTED_HOST=
ENV PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST}
RUN pip install --no-cache-dir --timeout 120 --retries 5 -r /tmp/requirements.txt
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
