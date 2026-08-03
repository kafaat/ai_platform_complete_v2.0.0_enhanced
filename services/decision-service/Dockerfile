# decision-service — INTERIM non-authoritative mirror (dual-path d201527).
# sahool-platform is the authoritative Source-of-Record and performs the real DB write,
# then best-effort mirrors here. This service has NO database yet (honest stub →
# persisted:false); it needs no DB driver, so no build toolchain beyond curl (healthcheck).
FROM python:3.11-slim-bookworm
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
COPY services/decision-service/requirements.txt /tmp/requirements.txt
# ── PyPI الرسمي افتراضياً؛ يمكن استخدام Alibaba mirror عبر build arg ──
# Alibaba override: --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_TRUSTED_HOST=
ENV PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST}
RUN pip install --no-cache-dir --timeout 300 --retries 10 -r /tmp/requirements.txt
COPY shared/ /app/shared/
COPY services/decision-service/ /app/

# Immutable source identity: generated at image build, never overridden at runtime.
ARG SAHOOL_GIT_SHA
ARG SAHOOL_BUILD_ID
ARG SAHOOL_SOURCE_REPOSITORY=
ARG SAHOOL_SOURCE_REF=
RUN SAHOOL_GIT_SHA="${SAHOOL_GIT_SHA}" SAHOOL_BUILD_ID="${SAHOOL_BUILD_ID}" SAHOOL_SOURCE_REPOSITORY="${SAHOOL_SOURCE_REPOSITORY}" SAHOOL_SOURCE_REF="${SAHOOL_SOURCE_REF}" python - <<'PYID'
import json, os, re
from pathlib import Path
sha = os.environ['SAHOOL_GIT_SHA']
build_id = os.environ['SAHOOL_BUILD_ID']
if not re.fullmatch(r"[0-9a-f]{40}", sha):
    raise SystemExit("SAHOOL_GIT_SHA must be 40 lowercase hex characters")
if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", build_id):
    raise SystemExit("SAHOOL_BUILD_ID has invalid format")
Path("/app/.sahool-build-metadata.json").write_text(json.dumps({
    "service": 'decision-service',
    "git_sha": sha,
    "build_id": build_id,
    "source_repository": os.environ.get("SAHOOL_SOURCE_REPOSITORY", ""),
    "source_ref": os.environ.get("SAHOOL_SOURCE_REF", ""),
}, sort_keys=True) + "\n", encoding="utf-8")
PYID
RUN chmod 0444 /app/.sahool-build-metadata.json
LABEL org.opencontainers.image.revision="${SAHOOL_GIT_SHA}" \
      org.opencontainers.image.source="${SAHOOL_SOURCE_REPOSITORY}" \
      org.opencontainers.image.ref.name="${SAHOOL_SOURCE_REF}" \
      io.sahool.build-id="${SAHOOL_BUILD_ID}"

RUN useradd -m sahool && chown -R sahool:sahool /app
USER sahool
EXPOSE 8160
HEALTHCHECK --interval=20s --timeout=5s --retries=3 CMD curl -sf http://localhost:8160/healthz || exit 1
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8160", "--workers", "2"]
