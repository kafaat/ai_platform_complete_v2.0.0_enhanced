FROM python:3.11-slim-bookworm
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends     gcc curl && rm -rf /var/lib/apt/lists/*
COPY services/local-ai-rag/requirements.txt /tmp/requirements.txt
# ── PyPI الرسمي هو الافتراضي فعليّاً (HTTPS، لا اعتماد على مرآة طرف ثالث) ──
# لا نضبط trusted-host افتراضيّاً (غير ضروريّ مع HTTPS، وضبطه يُضعِف أمان TLS).
# للمرآة الصينيّة (تسريع داخل الصين) مرّر كليهما صراحةً:
#   --build-arg PIP_INDEX_URL=https://pypi.org/simple \
#   --build-arg PIP_TRUSTED_HOST=pypi.org
# (أو علي بابا: https://mirrors.aliyun.com/pypi/simple/)
ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_TRUSTED_HOST=
ENV PIP_INDEX_URL=${PIP_INDEX_URL}
# trusted-host فقط إن مُرِّر (مرآة تتطلّبه) — وإلّا لا نخفّض أمان TLS.
RUN if [ -n "${PIP_TRUSTED_HOST}" ]; then \
        pip install --no-cache-dir --timeout 300 --retries 10 --trusted-host "${PIP_TRUSTED_HOST}" -r /tmp/requirements.txt; \
    else \
        pip install --no-cache-dir --timeout 300 --retries 10 -r /tmp/requirements.txt; \
    fi
COPY shared/ /app/shared/
COPY services/local-ai-rag/ /app/
RUN useradd -m sahool && chown -R sahool:sahool /app
USER sahool
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --retries=3   CMD curl -sf http://localhost:8000/healthz || exit 1
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
