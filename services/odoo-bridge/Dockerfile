FROM python:3.11-slim-bookworm
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends     gcc curl && rm -rf /var/lib/apt/lists/*
COPY services/odoo-bridge/requirements.txt /tmp/requirements.txt
# ── PyPI الرسميّ (تمّ التبديل من مرآة Tencent — كانت تُقدِّم حزمة pip بتجزئة مغلوطة) ──
# للتبديل إلى مرآة بديلة: --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ أو https://mirrors.cloud.tencent.com/pypi/simple/
ARG PIP_INDEX_URL=https://pypi.org/simple/
ARG PIP_TRUSTED_HOST=
ENV PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST}
RUN pip install --no-cache-dir --timeout 300 --retries 10 -r /tmp/requirements.txt
COPY shared/ /app/shared/
COPY services/odoo-bridge/ /app/
RUN useradd -m sahool && chown -R sahool:sahool /app
USER sahool
EXPOSE 8126
HEALTHCHECK --interval=30s --timeout=10s --retries=3   CMD curl -sf http://localhost:8126/healthz || exit 1
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8126", "--workers", "1"]
