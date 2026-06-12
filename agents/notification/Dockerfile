FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y gcc && rm -rf /var/lib/apt/lists/*
COPY agents/notification/requirements.txt /tmp/requirements.txt
# ── مرآة pip صينيّة (PyPI محجوب/بطيء) — قابلة للتجاوز بـ--build-arg ──
# البديل: https://mirrors.aliyun.com/pypi/simple/ (علي بابا)
ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_TRUSTED_HOST=pypi.org
ENV PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST}
RUN pip install --no-cache-dir --timeout 120 --retries 5 -r /tmp/requirements.txt
COPY shared/ /app/shared/
COPY agents/base_agent.py /app/base_agent.py
COPY agents/notification/ /app/
RUN useradd -m sahool && chown -R sahool:sahool /app
USER sahool
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD curl -sf http://localhost:8000/healthz || curl -sf http://localhost:8123/health || exit 1
CMD ["python", "agent.py"]
