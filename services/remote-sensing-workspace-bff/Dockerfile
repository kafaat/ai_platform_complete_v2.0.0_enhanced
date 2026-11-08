FROM python:3.12-slim
WORKDIR /app
ARG DEBIAN_MIRROR=
RUN if [ -n "${DEBIAN_MIRROR}" ]; then \
        sed -i \
            -e "s|http://deb.debian.org/debian-security|${DEBIAN_MIRROR%/}/debian-security|g" \
            -e "s|http://deb.debian.org/debian|${DEBIAN_MIRROR%/}/debian|g" \
            /etc/apt/sources.list.d/debian.sources; \
    fi \
    && apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
# Alibaba override: --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_TRUSTED_HOST=
ENV PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST}
COPY services/remote-sensing-workspace-bff/requirements.txt .
RUN pip install --no-cache-dir --timeout 300 --retries 10 -r requirements.txt
COPY services/remote-sensing-workspace-bff/main.py .
COPY shared/__init__.py /app/shared/__init__.py
COPY shared/security/ /app/shared/security/
RUN useradd -m sahool && chown -R sahool:sahool /app
USER sahool
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8185"]
