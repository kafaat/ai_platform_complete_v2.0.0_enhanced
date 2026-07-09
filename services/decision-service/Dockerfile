# decision-service — INTERIM non-authoritative mirror (dual-path d201527).
# sahool-platform is the authoritative Source-of-Record and performs the real DB write,
# then best-effort mirrors here. This service has NO database yet (honest stub →
# persisted:false); it needs no DB driver, so no build toolchain beyond curl (healthcheck).
FROM python:3.11-slim-bookworm
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
COPY services/decision-service/requirements.txt /tmp/requirements.txt
# ── PyPI الرسميّ (تمّ التبديل من مرآة Tencent — كانت تُقدِّم حزمة pip بتجزئة مغلوطة) ──
# للتبديل إلى مرآة بديلة: --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ أو https://mirrors.cloud.tencent.com/pypi/simple/
ARG PIP_INDEX_URL=https://pypi.org/simple/
ARG PIP_TRUSTED_HOST=
ENV PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST}
RUN pip install --no-cache-dir --timeout 300 --retries 10 -r /tmp/requirements.txt
COPY services/decision-service/ /app/
RUN useradd -m sahool && chown -R sahool:sahool /app
USER sahool
EXPOSE 8160
HEALTHCHECK --interval=20s --timeout=5s --retries=3 CMD curl -sf http://localhost:8160/healthz || exit 1
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8160", "--workers", "2"]
