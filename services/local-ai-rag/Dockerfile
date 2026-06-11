FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends     gcc curl && rm -rf /var/lib/apt/lists/*
COPY services/local-ai-rag/requirements.txt /tmp/requirements.txt
# ── PyPI الرسمي هو الافتراضي فعليّاً (يعمل عالميّاً، لا اعتماد على مرآة طرف ثالث) ──
# للمرآة الصينيّة (تسريع داخل الصين) مرّر:
#   --build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
#   --build-arg PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn
# (أو علي بابا: https://mirrors.aliyun.com/pypi/simple/)
ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_TRUSTED_HOST=pypi.org
ENV PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST}
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY shared/ /app/shared/
COPY services/local-ai-rag/ /app/
RUN useradd -m sahool && chown -R sahool:sahool /app
USER sahool
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --retries=3   CMD curl -sf http://localhost:8000/healthz || exit 1
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
