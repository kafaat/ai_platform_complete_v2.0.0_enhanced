FROM python:3.11-slim-bookworm
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*
COPY services/qdrant-seed/requirements.txt /tmp/req.txt
# ── مرآة Tencent Cloud (افتراضي — أكثر موثوقيّة في شبكتنا؛ pypi.org يفشل حتى مع VPN) ──
# للرجوع إلى PyPI الرسميّ عالميّاً: --build-arg PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_INDEX_URL=https://mirrors.cloud.tencent.com/pypi/simple/
ARG PIP_TRUSTED_HOST=
ENV PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST}
RUN pip install --no-cache-dir --timeout 300 --retries 10 -r /tmp/req.txt
COPY services/qdrant-seed/seed.py /app/seed.py
RUN useradd -m sahool && chown -R sahool /app
USER sahool
# لا HEALTHCHECK: مهمّة بذرة لمرّة واحدة (restart: "no"). الفحص السابق كان مُضلِّلاً
# (يفحص localhost:6333 وqdrant في حاوية أخرى، و|| echo يجعله ينجح دائماً).
CMD ["python", "seed.py"]
