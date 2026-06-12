FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*
COPY services/qdrant-seed/requirements.txt /tmp/req.txt
# ── PyPI الرسمي (افتراضي، يعمل عالميّاً) — للمرآة الصينيّة مرّر --build-arg ──
# البديل: https://mirrors.aliyun.com/pypi/simple/ (علي بابا)
ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_TRUSTED_HOST=
ENV PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST}
RUN pip install --no-cache-dir --timeout 120 --retries 5 -r /tmp/req.txt
COPY services/qdrant-seed/seed.py /app/seed.py
RUN useradd -m sahool && chown -R sahool /app
USER sahool
HEALTHCHECK --interval=30s --timeout=10s --retries=3 CMD curl -sf http://localhost:6333/healthz || echo "waiting"
CMD ["python", "seed.py"]
