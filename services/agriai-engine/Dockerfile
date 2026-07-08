FROM python:3.12-slim-bookworm
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*
COPY services/agriai-engine/requirements.txt /tmp/
# ── مرآة Tencent Cloud (افتراضي — أكثر موثوقيّة في شبكتنا؛ pypi.org يفشل حتى مع VPN) ──
# للرجوع إلى PyPI الرسميّ عالميّاً: --build-arg PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_INDEX_URL=https://mirrors.cloud.tencent.com/pypi/simple/
ARG PIP_TRUSTED_HOST=
ENV PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST}
RUN pip install --no-cache-dir --timeout 300 --retries 10 -r /tmp/requirements.txt
COPY shared/ /app/shared/
COPY services/agriai-engine/ /app/
RUN useradd -m sahool && chown -R sahool:sahool /app
USER sahool
ENV PYTHONUNBUFFERED=1 PYTHONPATH=/app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -sf http://localhost:8000/healthz || exit 1
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
