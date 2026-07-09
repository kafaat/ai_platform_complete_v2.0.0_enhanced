# SAHOOL v9 — vegetation-analysis-service Dockerfile (build context = project root)
FROM python:3.11-slim-bookworm
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev curl && rm -rf /var/lib/apt/lists/*
COPY services/vegetation-analysis-service/requirements.txt /tmp/requirements.txt
# ── PyPI الرسميّ (تمّ التبديل من مرآة Tencent — كانت تُقدِّم حزمة pip بتجزئة مغلوطة) ──
# للتبديل إلى مرآة بديلة: --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ أو https://mirrors.cloud.tencent.com/pypi/simple/
ARG PIP_INDEX_URL=https://pypi.org/simple/
ARG PIP_TRUSTED_HOST=
ENV PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST}
RUN pip install --no-cache-dir --timeout 300 --retries 10 -r /tmp/requirements.txt
# FIXED: shared/ copy works because context is project root
COPY shared/ /app/shared/
COPY services/vegetation-analysis-service/main.py /app/main.py
# تفكيك المسارات: main.py يستورد router_registry الذي يضمّ routers/. غير منسوخة ⇒
# ModuleNotFoundError: 'router_registry' عند الإقلاع ⇒ تعطّل الخدمة. نسخها إلزاميّ.
COPY services/vegetation-analysis-service/router_registry.py /app/router_registry.py
COPY services/vegetation-analysis-service/routers/ /app/routers/
RUN useradd -m sahool && chown -R sahool:sahool /app
USER sahool
HEALTHCHECK --interval=20s --timeout=5s CMD curl -sf http://localhost:8000/healthz || exit 1
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
