FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y gcc curl && rm -rf /var/lib/apt/lists/*
COPY services/supervisor-agent/requirements.txt /tmp/req.txt
# ── PyPI الرسمي (افتراضي، يعمل عالميّاً) — للمرآة الصينيّة مرّر --build-arg ──
# البديل: https://mirrors.aliyun.com/pypi/simple/ (علي بابا)
ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_TRUSTED_HOST=pypi.org
ENV PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST}
RUN pip install --no-cache-dir --timeout 120 --retries 5 -r /tmp/req.txt
COPY shared/ /app/shared/
COPY services/supervisor-agent/ /app/
HEALTHCHECK --interval=30s CMD curl -sf http://localhost:8000/readyz || exit 1
RUN useradd -m sahool && chown -R sahool:sahool /app 2>/dev/null || true
USER sahool
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
