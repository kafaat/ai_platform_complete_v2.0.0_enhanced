FROM python:3.11-slim-bookworm
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends gcc curl \
    && rm -rf /var/lib/apt/lists/*
COPY services/supervisor-agent/requirements.txt /tmp/req.txt
# ── مرآة Tencent Cloud (افتراضي — أكثر موثوقيّة في شبكتنا؛ pypi.org يفشل حتى مع VPN) ──
# للرجوع إلى PyPI الرسميّ عالميّاً: --build-arg PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_INDEX_URL=https://mirrors.cloud.tencent.com/pypi/simple/
ARG PIP_TRUSTED_HOST=
ENV PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST}
RUN pip install --no-cache-dir --timeout 300 --retries 10 -r /tmp/req.txt
COPY shared/ /app/shared/
COPY services/supervisor-agent/ /app/
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -sf http://localhost:8000/readyz || exit 1
RUN useradd -m sahool && chown -R sahool:sahool /app 2>/dev/null || true
USER sahool
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
