FROM python:3.12-slim-bookworm
WORKDIR /app

ARG DEBIAN_MIRROR=
RUN if [ -n "${DEBIAN_MIRROR}" ]; then \
        sed -i \
            -e "s|http://deb.debian.org/debian-security|${DEBIAN_MIRROR%/}/debian-security|g" \
            -e "s|http://deb.debian.org/debian|${DEBIAN_MIRROR%/}/debian|g" \
            /etc/apt/sources.list.d/debian.sources; \
    fi \
    && apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY services/tts-service/requirements.txt /tmp/
# ── PyPI الرسمي افتراضياً؛ يمكن استخدام Alibaba mirror عبر build arg ──
# Alibaba override: --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_TRUSTED_HOST=
ENV PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST}
RUN pip install --no-cache-dir --timeout 300 --retries 10 -r /tmp/requirements.txt

# W3-11: optional local Arabic voice (Piper) so a tenant whose AI policy is local_only gets
# speech instead of a 503: edge-tts is an external provider and is never used for them
# (providers.select_provider_for_policy). OFF by default: the voice's model card gives its
# training-data license only as "See URL", so shipping it is the owner's decision. Enable with
#   --build-arg TTS_LOCAL_VOICE=ar_JO-kareem-medium
# Both files are fetched from a pinned rhasspy/piper-voices revision and verified by sha256
# (the .onnx digest equals the LFS oid Hugging Face publishes for that revision).
ARG TTS_LOCAL_VOICE=
COPY services/tts-service/requirements-piper.txt /tmp/
RUN set -eu; \
    if [ -z "${TTS_LOCAL_VOICE}" ]; then echo "local Piper voice not built in"; exit 0; fi; \
    if [ "${TTS_LOCAL_VOICE}" != "ar_JO-kareem-medium" ]; then \
        echo "unsupported TTS_LOCAL_VOICE=${TTS_LOCAL_VOICE}" >&2; exit 1; \
    fi; \
    pip install --no-cache-dir --timeout 300 --retries 10 -r /tmp/requirements-piper.txt; \
    revision=e9ab671f2a0e50a701b34361136ba3e6a3a9eb0c; \
    base="https://huggingface.co/rhasspy/piper-voices/resolve/${revision}/ar/ar_JO/kareem/medium"; \
    mkdir -p /opt/piper; \
    curl -fsSL --retry 5 -o /opt/piper/ar_JO-kareem-medium.onnx "${base}/ar_JO-kareem-medium.onnx"; \
    curl -fsSL --retry 5 -o /opt/piper/ar_JO-kareem-medium.onnx.json "${base}/ar_JO-kareem-medium.onnx.json"; \
    printf '%s  %s\n' \
        9e95cab07b679da603bba17c4dec7ab3111320571964ee95c0379603c086491e /opt/piper/ar_JO-kareem-medium.onnx \
        ea6d9b9d9076dbdb6bf5c98c6a141ef154959d2359709b37855727964e7d6c4d /opt/piper/ar_JO-kareem-medium.onnx.json \
        | sha256sum -c -
# Absent file (default build) => PiperProvider.available() is False => local_only gets a named 503.
ENV PIPER_VOICE_PATH=/opt/piper/ar_JO-kareem-medium.onnx

COPY shared/ /app/shared/
COPY services/tts-service/ /app/

RUN useradd -m sahool && chown -R sahool:sahool /app
USER sahool

ENV PYTHONUNBUFFERED=1 PYTHONPATH=/app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -sf http://localhost:8000/healthz || exit 1

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
