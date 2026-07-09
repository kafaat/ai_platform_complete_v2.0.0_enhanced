FROM python:3.11-slim-bookworm
WORKDIR /app

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
