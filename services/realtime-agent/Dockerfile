FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SAHOOL_REALTIME_VOICE_ENABLED=0 \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    HF_HUB_DISABLE_TELEMETRY=1
WORKDIR /app
COPY services/realtime-agent/requirements.txt /tmp/requirements.txt
ARG PIP_INDEX_URL=https://pypi.org/simple
# Optional operator override: --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
ARG PIP_TRUSTED_HOST=
ENV PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST}
RUN apt-get update \
    && apt-get install -y --no-install-recommends libportaudio2 \
    && rm -rf /var/lib/apt/lists/* \
    && python -m pip install --no-cache-dir --timeout 300 --retries 10 -r /tmp/requirements.txt \
    && groupadd --gid 10001 realtime \
    && useradd --uid 10001 --gid realtime --no-create-home realtime
COPY services/realtime-agent/realtime_agent/ /app/realtime_agent/
COPY services/realtime-agent/main.py /app/main.py
USER 10001:10001
CMD ["python", "main.py", "start"]
