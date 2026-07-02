FROM python:3.11-slim-bookworm
WORKDIR /app
COPY services/weather-signal-engine/requirements.txt /tmp/req.txt
RUN pip install --no-cache-dir -r /tmp/req.txt
# نواة التراكب النقيّة المشترَكة (تُختبَر في وظيفة Platform Unit Tests).
COPY services/sahool-platform/core/thresholds.py /app/core/thresholds.py
COPY services/sahool-platform/core/weather_overlay.py /app/core/weather_overlay.py
COPY services/sahool-platform/core/weather_signals.py /app/core/weather_signals.py
COPY services/sahool-platform/core/weather_overlay_pipeline.py /app/core/weather_overlay_pipeline.py
RUN touch /app/core/__init__.py
COPY services/weather-signal-engine/src/ /app/
COPY services/weather-signal-engine/worker_health_probe.py /app/worker_health_probe.py
# مستخدم غير جذري (SEC-2 — محاذاةً لباقي الخدمات)
RUN useradd -m sahool && chown -R sahool:sahool /app
USER sahool
CMD ["python", "main.py"]
