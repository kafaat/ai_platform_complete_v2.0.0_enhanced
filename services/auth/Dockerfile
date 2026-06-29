FROM python:3.11-slim-bookworm
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*
COPY services/auth/requirements.txt /tmp/requirements.txt
# ── PyPI الرسمي (افتراضي، يعمل عالميّاً) — للمرآة الصينيّة مرّر --build-arg ──
# البديل: https://mirrors.aliyun.com/pypi/simple/ (علي بابا)
ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_TRUSTED_HOST=
ENV PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST}
RUN pip install --no-cache-dir --timeout 300 --retries 10 -r /tmp/requirements.txt
COPY shared/ /app/shared/
COPY services/auth/main.py /app/main.py
# تفكيك المسارات (#557): main.py يستورد `from router_registry import register_routers`
# الذي يضمّ وحدات routers/. غير منسوخة ⇒ ModuleNotFoundError: 'router_registry' عند
# الإقلاع ⇒ تعطّل auth (unhealthy). نسخها إلزاميّ (نفس درس otp.py أدناه).
COPY services/auth/router_registry.py /app/router_registry.py
COPY services/auth/routers/ /app/routers/
# otp.py وحدة شقيقة نقيّة (مفصولة عن fastapi للاختبار في CI) يستوردها main.py:
# `from otp import …`. كانت غير منسوخة ⇒ ModuleNotFoundError: No module named 'otp'
# عند الإقلاع. نسخها إلزاميّ.
COPY services/auth/otp.py /app/otp.py
RUN useradd -m sahool && chown -R sahool:sahool /app
USER sahool
EXPOSE 8000
HEALTHCHECK --interval=20s --timeout=5s CMD curl -sf http://localhost:8000/readyz || exit 1
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
