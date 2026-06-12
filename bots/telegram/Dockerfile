FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY bots/telegram/requirements.txt .
# ── مرآة pip صينيّة (PyPI محجوب/بطيء) — قابلة للتجاوز بـ--build-arg ──
# البديل: https://mirrors.aliyun.com/pypi/simple/ (علي بابا)
ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_TRUSTED_HOST=pypi.org
ENV PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST}
RUN pip install --no-cache-dir --timeout 120 --retries 5 -r requirements.txt

COPY bots/telegram/ /app/

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD pgrep -f "python main.py" || exit 1
RUN useradd -m sahool && chown -R sahool:sahool /app 2>/dev/null || true
USER sahool
CMD ["python", "main.py"]
