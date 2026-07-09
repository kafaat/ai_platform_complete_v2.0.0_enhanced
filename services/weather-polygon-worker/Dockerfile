FROM python:3.11-slim-bookworm
WORKDIR /app
COPY services/weather-polygon-worker/requirements.txt /tmp/req.txt
# ── PyPI الرسمي افتراضياً؛ يمكن استخدام Alibaba mirror عبر build arg ──
# Alibaba override: --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_TRUSTED_HOST=
ENV PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST}
RUN pip install --timeout 300 --retries 10 --no-cache-dir -r /tmp/req.txt
# نواة التراكب النقيّة المشترَكة (تُختبَر في وظيفة Platform Unit Tests).
COPY services/sahool-platform/core/thresholds.py /app/core/thresholds.py
COPY services/sahool-platform/core/weather_overlay.py /app/core/weather_overlay.py
COPY services/sahool-platform/core/weather_signals.py /app/core/weather_signals.py
COPY services/sahool-platform/core/weather_overlay_pipeline.py /app/core/weather_overlay_pipeline.py
RUN touch /app/core/__init__.py
COPY services/weather-polygon-worker/src/ /app/
COPY services/weather-polygon-worker/worker_health_probe.py /app/worker_health_probe.py
# مستخدم غير جذري (SEC-2 — محاذاةً لباقي الخدمات)
RUN useradd -m sahool && chown -R sahool:sahool /app
USER sahool
CMD ["python", "main.py"]
