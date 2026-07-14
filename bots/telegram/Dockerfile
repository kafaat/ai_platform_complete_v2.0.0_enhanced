FROM python:3.12-slim-bookworm

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY bots/telegram/requirements.txt .
# ── مرآة pip صينيّة (PyPI محجوب/بطيء) — قابلة للتجاوز بـ--build-arg ──
# Alibaba override: --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_TRUSTED_HOST=
ENV PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST}
RUN pip install --no-cache-dir --timeout 300 --retries 10 -r requirements.txt

COPY bots/telegram/ /app/

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# V21 §2.3: فحص جاهزيّة قادر على الإدراك (getMe مقبول + حداثة نبضة) بدل pgrep
# الذي يُثبِت وجود العمليّة لا جاهزيّتها. (compose قد يتجاوزه بفحصه الخاصّ.)
HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=45s \
    CMD python /app/bot_readiness.py check --max-age 90 || exit 1
RUN useradd -m sahool && chown -R sahool:sahool /app 2>/dev/null || true
USER sahool
CMD ["python", "main.py"]
