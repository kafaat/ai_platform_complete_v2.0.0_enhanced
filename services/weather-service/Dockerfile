FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends gcc curl && rm -rf /var/lib/apt/lists/*
COPY services/weather-service/requirements.txt /tmp/requirements.txt
# ── PyPI الرسمي (افتراضي، يعمل عالميّاً) — للمرآة الصينيّة مرّر --build-arg ──
# البديل: https://mirrors.aliyun.com/pypi/simple/ (علي بابا)
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ARG PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn
ENV PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST}
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY shared/ /app/shared/
COPY services/weather-service/ /app/
RUN useradd -m sahool && chown -R sahool:sahool /app
USER sahool
EXPOSE 8000
HEALTHCHECK --interval=20s --timeout=5s --retries=3 CMD curl -sf http://localhost:8000/readyz || exit 1
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
